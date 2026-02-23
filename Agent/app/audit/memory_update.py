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
    system_prompt = (
        "你是合同审计系统的持续改进记忆编辑器。"
        "你需要基于审计结果和用户反馈，根据现有记忆的格式总结并更新记忆内容。"
        "不要包含多余解释，不要包含具体和完整审计结果或ID。"
        "如果现有记忆中存在重复的内容，必须去除重复内容，保持简洁、清晰。"
        "如果是全新的记忆内容，则在现有记忆后添加。"
        f"保持整个Markdown的总长度不超过 {config.memory_len} 字符。"
    )
    user_prompt = (
        "现有记忆：\n"
        f"{memory}\n\n"
        "审计结果：\n"
        f"{json.dumps(audit_result, ensure_ascii=False, indent=2)}\n\n"
        "用户反馈：\n"
        f"{feedback}\n\n"
        "请输出更新后的记忆Markdown："
    )
    client = create_openai_client(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )
    updated_memory = chat_complete(
        client=client,
        model=config.model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0,
    ).strip()
    updated_memory = _truncate_text(updated_memory, config.memory_len).strip()
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
