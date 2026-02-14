def build_system_prompt() -> str:
    return (
        "你是法律合规审查助手，负责对合同文本进行合规性评估、风险评分与修订建议。"
        "必须引用法律条文并输出可追溯的条文编号与出处。"
        "仅输出JSON，不要包含多余文字。"
    )


def build_user_prompt(contract_text: str, legal_context: str) -> str:
    return (
        "任务：根据合同文本，结合参考法律条文，输出合规审查报告JSON。\n"
        "要求：\n"
        "1) 输出字段必须严格匹配JSON结构\n"
        "2) 每个问题必须引用法律条文（source_path + article_no + quote）\n"
        "3) 风险评分区间0-100，评分越高代表越高风险\n"
        "4) 修订意见应可直接用于修改合同条款\n"
        "JSON结构：\n"
        "{\n"
        '  "overall_risk_score": 0,\n'
        '  "summary": "一句话总结",\n'
        '  "issues": [\n'
        "    {\n"
        '      "clause_excerpt": "合同原文摘录",\n'
        '      "risk_level": "高/中/低",\n'
        '      "risk_reason": "风险原因",\n'
        '      "legal_citations": [\n'
        "        {\n"
        '          "source_path": "法律文件路径",\n'
        '          "article_no": "第X条",\n'
        '          "quote": "引用条文原文"\n'
        "        }\n"
        "      ],\n"
        '      "suggestion": "修订建议"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "合同文本：\n"
        f"{contract_text}\n"
        "参考法律条文：\n"
        f"{legal_context}\n"
    )
