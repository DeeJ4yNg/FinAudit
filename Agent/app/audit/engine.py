import json

from Agent.app.config import AppConfig
from Agent.app.legal.retrieval import retrieve_top_articles
from Agent.app.llm.openai_client import chat_complete, create_openai_client, ensure_json
from Agent.app.audit.prompt import build_system_prompt, build_user_prompt
from typing import List

from Agent.app.models import AuditResult, LegalArticle


def run_audit(
    contract_text: str,
    legal_articles: List[LegalArticle],
    config: AppConfig,
) -> AuditResult:
    if not contract_text.strip():
        raise ValueError("Contract text is empty")
    selected_articles = retrieve_top_articles(
        contract_text,
        legal_articles,
        config.max_articles,
        config,
    )
    legal_context = _format_legal_context(selected_articles)
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(
        _truncate(contract_text, config.contract_max_chars),
        legal_context,
    )
    client = create_openai_client(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )
    response_text = chat_complete(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    json_text = ensure_json(response_text)
    _validate_json(json_text)
    return AuditResult(raw_json=json_text)


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


def _validate_json(json_text: str) -> None:
    data = json.loads(json_text)
    if "summary" not in data:
        raise ValueError("Missing summary")
    if "risks" not in data:
        raise ValueError("Missing risks")
