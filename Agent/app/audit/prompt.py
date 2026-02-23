from pathlib import Path


def memory_path() -> Path:
    return Path(__file__).resolve().parent / "memory.md"


def load_memory() -> str:
    path = memory_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_system_prompt_base() -> str:
    return (
        "你是一名严谨的税务法律专家。你的任务是基于用户提供的合同文本和法规文本，"
        "对合同进行证据化审阅，识别法律与涉税风险，并给出可执行的修改建议。"
        "仅基于提供的文本作出判断，严禁臆测未提供事实。"
        "每个风险必须同时绑定合同证据与法规证据。"
        "仅输出JSON，不要包含多余文字。"
    )


def build_system_prompt() -> str:
    base = build_system_prompt_base()
    memory = load_memory()
    if not memory:
        return base
    return f"{base}\n\n持续改进记忆：\n{memory}"


def build_chunk_user_prompt(
    contract_text: str,
    legal_context: str,
    memory: str,
    previous_results: str,
    chunk_index: int,
    chunk_total: int,
) -> str:
    memory_block = f"持续改进记忆：\n{memory}\n" if memory else ""
    previous_block = f"已完成分片结果：\n{previous_results}\n" if previous_results else ""
    return (
        "任务：根据合同文本分片，结合参考法律条文，输出该分片的税务法律合规审查JSON。\n"
        "要求：\n"
        "1) 输出字段必须严格匹配JSON结构\n"
        "2) 每个风险必须包含合同证据与法规证据（source_path + law_ref_id + quote）\n"
        "3) 风险评分按 L(1-5) * I(1-5) 计算，分值1-25\n"
        "4) 风险等级映射：16-25=高，9-15=中，1-8=低\n"
        "5) 中高风险必须给出可直接替换的条款文本\n"
        "6) 不确定事项必须标记为待确认\n"
        "JSON结构：\n"
        f"{_json_schema()}\n"
        f"{memory_block}"
        f"{previous_block}"
        f"合同分片（{chunk_index}/{chunk_total}）：\n"
        f"{contract_text}\n"
        "参考法律条文：\n"
        f"{legal_context}\n"
    )


def build_summary_prompt(partial_results: list[str], memory: str) -> str:
    memory_block = f"持续改进记忆：\n{memory}\n" if memory else ""
    joined_results = "\n\n".join(partial_results)
    return (
        "任务：将多个分片审计结果合并为最终审计JSON，去重并合并相同风险。\n"
        "要求：\n"
        "1) 输出字段必须严格匹配JSON结构\n"
        "2) 风险列表需去重与合并，保留证据最充分版本\n"
        "3) 汇总风险数量与摘要，确保与风险列表一致\n"
        "JSON结构：\n"
        f"{_json_schema()}\n"
        f"{memory_block}"
        "分片审计结果：\n"
        f"{joined_results}\n"
    )


def _json_schema() -> str:
    return (
        "{\n"
        '  "summary": "一句话总结",\n'
        '  "overall": {\n'
        '    "risk_count": {"high": 0, "medium": 0, "low": 0}\n'
        "  },\n"
        '  "delta": {\n'
        '    "new_risks": [],\n'
        '    "changed_risks": [],\n'
        '    "closed_risks": [],\n'
        '    "clause_changes": []\n'
        "  },\n"
        '  "risks": [\n'
        "    {\n"
        '      "risk_id": "R-001",\n'
        '      "clause_id": "C-文档号-章节号-条款号",\n'
        '      "title": "风险标题",\n'
        '      "level": "高/中/低",\n'
        '      "score": 0,\n'
        '      "likelihood": 1,\n'
        '      "impact": 1,\n'
        '      "confidence": "高/中/低",\n'
        '      "tags": ["tax-burden"],\n'
        '      "contract_evidence": "合同原文证据片段",\n'
        '      "law_evidence": [\n'
        "        {\n"
        '          "source_path": "法律文件路径",\n'
        '          "law_ref_id": "L-文档号-章号-条号",\n'
        '          "quote": "引用条文原文"\n'
        "        }\n"
        "      ],\n"
        '      "risk_reason": "风险说明（1-3句）",\n'
        '      "trigger": "触发条件",\n'
        '      "impact_analysis": "影响分析",\n'
        '      "suggested_text": "建议替换文本",\n'
        '      "open_questions": ["需确认事项"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


def build_user_prompt(contract_text: str, legal_context: str) -> str:
    return (
        "任务：根据合同文本，结合参考法律条文，输出税务法律合规审查JSON。\n"
        "要求：\n"
        "1) 输出字段必须严格匹配JSON结构\n"
        "2) 每个风险必须包含合同证据与法规证据（source_path + law_ref_id + quote）\n"
        "3) 风险评分按 L(1-5) * I(1-5) 计算，分值1-25\n"
        "4) 风险等级映射：16-25=高，9-15=中，1-8=低\n"
        "5) 中高风险必须给出可直接替换的条款文本\n"
        "6) 不确定事项必须标记为待确认\n"
        "JSON结构：\n"
        f"{_json_schema()}"
        "合同文本：\n"
        f"{contract_text}\n"
        "参考法律条文：\n"
        f"{legal_context}\n"
    )
