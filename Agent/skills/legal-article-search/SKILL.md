---
name: legal-article-search
description: Finds and cites relevant legal articles for contract compliance analysis. Invoke when mapping contract clauses to laws or building citation-backed risk reviews.
---

# 法律条文检索指引

## 目标

根据合同文本定位相关法律条文，并输出可追溯的条文引用。

## 使用步骤

1. 使用 file_read 工具读取 workspace 下的法律条文文档
2. 将法律文档按“第X条”拆分为条文段
3. 结合合同文本提取关键词并筛选相关条文
4. 输出风险与修订建议时，逐条引用 source_path 与 article_no

## 输出要求

- 每条风险必须引用法律条文原文
- 引用字段包含 source_path、article_no、quote
- 风险结论与修订建议需与条文逻辑一致
