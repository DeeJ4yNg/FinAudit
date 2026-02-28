from __future__ import annotations

import json
from typing import Any

from Agent.app.audit.prompt import load_memory, memory_path
from Agent.app.config import AppConfig
from Agent.app.llm.openai_client import chat_complete, create_openai_client


def update_memory_from_feedback(
    config: AppConfig,
    feedback: str,
    audit_result: Any,
) -> str:
    memory = load_memory()
    client = create_openai_client(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )
    summary_max_len = _summary_max_len(memory, config.memory_len)
    new_summary = _summarize_feedback(
        client=client,
        config=config,
        memory=memory,
        feedback=feedback,
        audit_result=audit_result,
        max_len=summary_max_len,
    )
    appended_memory = _append_memory(memory, new_summary)
    if len(memory) < config.memory_len:
        updated_memory = appended_memory.strip()
    else:
        updated_memory = _compress_memory(
            client=client,
            config=config,
            memory=appended_memory,
        ).strip()
    path = memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_memory, encoding="utf-8")
    return updated_memory


def _truncate_text(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()


def _append_memory(memory: str, new_summary: str) -> str:
    base = memory.strip()
    addition = new_summary.strip()
    if not base:
        return addition
    if not addition:
        return base
    return f"{base}\n\n{addition}"


def _summary_max_len(memory: str, limit: int) -> int:
    if limit <= 0:
        return 0
    if not memory:
        return min(200, limit)
    remaining = limit - len(memory.strip()) - 2
    if remaining <= 0:
        return 50
    return min(200, remaining)


def _summarize_feedback(
    client,
    config: AppConfig,
    memory: str,
    feedback: str,
    audit_result: Any,
    max_len: int,
) -> str:
    system_prompt = (
        "你是合同审计系统的记忆提炼器。"
        "基于审计结果与用户反馈输出一段新增记忆。"
        "只输出Markdown片段，不要包含审计结果ID或完整原文。"
        "内容要简短、可执行，避免重复已有记忆。"
        f"长度不超过 {max_len} 字符。"
    )
    user_prompt = (
        "现有记忆：\n"
        f"{memory}\n\n"
        "审计结果：\n"
        f"{json.dumps(audit_result, ensure_ascii=False, indent=2)}\n\n"
        "用户反馈：\n"
        f"{feedback}\n\n"
        "请输出新增记忆Markdown："
    )
    return chat_complete(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
    ).strip()


def _compress_memory(client, config: AppConfig, memory: str) -> str:
    system_prompt = (
        "你是合同审计系统的记忆压缩器。"
        "需要在不丢失关键约束和改进点的前提下压缩记忆。"
        "去除重复内容，保留简洁清晰的Markdown格式。"
        f"输出长度不超过 {config.memory_len} 字符。"
    )
    user_prompt = (
        "现有记忆：\n"
        f"{memory}\n\n"
        "请输出压缩后的记忆Markdown："
    )
    compressed = chat_complete(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
    ).strip()
    return _truncate_text(compressed, config.memory_len).strip()
