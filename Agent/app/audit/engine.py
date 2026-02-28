import json
import re

from Agent.app.config import AppConfig
from Agent.app.legal.retrieval import retrieve_top_articles
from Agent.app.llm.openai_client import (
    chat_complete_with_usage,
    create_openai_client,
    ensure_json,
)
from Agent.app.audit.prompt import (
    build_chunk_user_prompt,
    build_summary_prompt,
    build_system_prompt,
    build_system_prompt_base,
    build_user_prompt,
    load_memory,
)
from Agent.app.logging_utils import get_logger, safe_json
from typing import List

from Agent.app.models import AuditResult, LegalArticle


def run_audit(
    contract_text: str,
    legal_articles: List[LegalArticle],
    config: AppConfig,
) -> AuditResult:
    if not contract_text.strip():
        raise ValueError("Contract text is empty")
    logger = get_logger("audit")
    mode_label = _law_retrieval_label(config.law_retrieval)
    logger.info(
        "audit_mode %s",
        safe_json({"mode": config.law_retrieval, "label": mode_label}),
    )
    if config.law_retrieval == 3:
        return _run_chunked_audit(contract_text, legal_articles, config)
    selected_articles = retrieve_top_articles(
        contract_text,
        legal_articles,
        config.max_articles,
        config,
    )
    legal_context = _format_legal_context(selected_articles)
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        contract_text,
        legal_context,
    )
    client = create_openai_client(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )
    response_text, token_usage = chat_complete_with_usage(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    json_text = ensure_json(response_text)
    json_text = _normalize_json(json_text)
    return AuditResult(raw_json=json_text, token_usage=token_usage)


def _run_chunked_audit(
    contract_text: str,
    legal_articles: List[LegalArticle],
    config: AppConfig,
) -> AuditResult:
    chunks = _chunk_contract_text(contract_text, config.contract_max_chars)
    if not chunks:
        raise ValueError("Contract text is empty")
    logger = get_logger("audit.chunked")
    system_prompt = build_system_prompt_base()
    memory = load_memory()
    client = create_openai_client(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )
    results: list[str] = []
    chunk_results: list[dict] = []
    total_usage = _empty_token_usage()
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        logger.info(
            "chunk_start %s",
            safe_json({"index": index, "total": total, "chars": len(chunk)}),
        )
        selected_articles = retrieve_top_articles(
            chunk,
            legal_articles,
            config.max_articles,
            config,
        )
        legal_context = _format_legal_context(selected_articles)
        previous_results = "\n\n".join(results)
        user_prompt = build_chunk_user_prompt(
            contract_text=chunk,
            legal_context=legal_context,
            memory=memory,
            previous_results=previous_results,
            chunk_index=index,
            chunk_total=total,
        )
        response_text, usage = chat_complete_with_usage(
            client=client,
            model=config.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        json_text = ensure_json(response_text)
        json_text = _normalize_json(json_text)
        results.append(json_text)
        chunk_data = json.loads(json_text)
        chunk_data["chunk_index"] = index
        chunk_data["chunk_total"] = total
        chunk_data["chunk_text"] = chunk
        chunk_results.append(chunk_data)
        _merge_token_usage(total_usage, usage)
        logger.info(
            "chunk_done %s",
            safe_json({"index": index, "total": total}),
        )
    summary_prompt = build_summary_prompt(results, memory)
    summary_text, summary_usage = chat_complete_with_usage(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=summary_prompt,
    )
    summary_json = ensure_json(summary_text)
    summary_json = _normalize_json(summary_json)
    summary_data = json.loads(summary_json)
    summary_data["chunk_results"] = chunk_results
    summary_json = json.dumps(summary_data, ensure_ascii=False)
    _merge_token_usage(total_usage, summary_usage)
    return AuditResult(raw_json=summary_json, token_usage=total_usage)


def _format_legal_context(articles: list[LegalArticle]) -> str:
    blocks = []
    for article in articles:
        block = (
            f"[{article.source_path}] {article.article_no}\n"
            f"{article.content.strip()}\n"
        )
        blocks.append(block)
    return "\n".join(blocks)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _chunk_contract_text(text: str, max_chars: int) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if max_chars <= 0:
        return [cleaned]
    if len(cleaned) <= max_chars:
        return [cleaned]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    if not paragraphs:
        return _split_long_text(cleaned, max_chars)
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_text(paragraph, max_chars))
            continue
        if not current:
            current = paragraph
            continue
        combined = f"{current}\n\n{paragraph}"
        if len(combined) <= max_chars:
            current = combined
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        return [text]
    pieces = []
    start = 0
    total = len(text)
    while start < total:
        end = min(start + max_chars, total)
        pieces.append(text[start:end])
        start = end
    return pieces


def _law_retrieval_label(mode: int) -> str:
    if mode == 1:
        return "full_contract_full_laws"
    if mode == 2:
        return "full_contract_retrieved_laws"
    if mode == 3:
        return "chunked_contract_retrieved_laws"
    return "unknown"


def _normalize_json(json_text: str) -> str:
    data = _safe_load_json(json_text)
    if not isinstance(data, dict):
        data = {}
    summary = data.get("summary")
    if not isinstance(summary, str):
        data["summary"] = _extract_summary(json_text)
    if "risks" not in data or not isinstance(data.get("risks"), list):
        data["risks"] = []
    if "raw_text" not in data and not data.get("summary"):
        data["raw_text"] = json_text
    return json.dumps(data, ensure_ascii=False)


def _safe_load_json(text: str) -> dict | list | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json_text(text)
        if repaired and repaired != text:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None
        return None


def _repair_json_text(text: str) -> str:
    cleaned = text.replace("\ufeff", "")
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    return cleaned


def _extract_summary(text: str) -> str:
    match = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
    if match:
        return match.group(1)
    match = re.search(r"summary\s*[:：]\s*([^\n\r]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def _empty_token_usage() -> dict[str, int]:
    return {"prompt_total": 0, "prompt_cached": 0, "prompt_uncached": 0, "completion": 0}


def _merge_token_usage(total: dict[str, int], delta: dict[str, int]) -> None:
    total["prompt_total"] += int(delta.get("prompt_total", 0) or 0)
    total["prompt_cached"] += int(delta.get("prompt_cached", 0) or 0)
    total["prompt_uncached"] += int(delta.get("prompt_uncached", 0) or 0)
    total["completion"] += int(delta.get("completion", 0) or 0)
