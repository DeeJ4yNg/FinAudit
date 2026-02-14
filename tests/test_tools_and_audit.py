import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Agent.app.audit.engine import run_audit
from Agent.app.config import AppConfig
from Agent.app.models import LegalArticle
from Agent.app.tools.file_read import list_legal_files, read_legal_file


class TestToolsAndAudit(unittest.TestCase):
    def test_file_read_restricts_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "legal"
            workspace.mkdir()
            legal_file = workspace / "law.txt"
            legal_file.write_text("第一条 合同应当遵循公平原则。", encoding="utf-8")
            content = read_legal_file(legal_file, workspace)
            self.assertIn("公平原则", content)

            other_file = Path(temp_dir) / "outside.txt"
            other_file.write_text("不可读取", encoding="utf-8")
            with self.assertRaises(PermissionError):
                read_legal_file(other_file, workspace)

    def test_list_legal_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "law.txt").write_text("规则", encoding="utf-8")
            (workspace / "notes.md").write_text("说明", encoding="utf-8")
            (workspace / "ignore.bin").write_bytes(b"abc")
            files = list_legal_files(workspace)
            names = {path.name for path in files}
            self.assertIn("law.txt", names)
            self.assertIn("notes.md", names)
            self.assertNotIn("ignore.bin", names)

    def test_run_audit_with_mocked_llm(self):
        contract_text = "甲方应当在30日内支付服务费。"
        legal_articles = [
            LegalArticle(
                source_path="law.txt",
                source_title="法条",
                article_no="第一条",
                content="合同当事人应当遵循公平原则。",
            )
        ]
        config = AppConfig(
            openai_api_key="test-key",
            openai_base_url=None,
            model="gpt-4.1-mini",
            legal_workspace=Path.cwd(),
            max_articles=5,
            contract_max_chars=1000,
        )
        mocked_json = {
            "overall_risk_score": 35,
            "summary": "存在支付条款风险",
            "issues": [
                {
                    "clause_excerpt": "甲方应当在30日内支付服务费。",
                    "risk_level": "中",
                    "risk_reason": "支付条款未明确违约责任",
                    "legal_citations": [
                        {
                            "source_path": "law.txt",
                            "article_no": "第一条",
                            "quote": "合同当事人应当遵循公平原则。",
                        }
                    ],
                    "suggestion": "补充逾期支付违约责任条款。",
                }
            ],
        }

        def fake_embed_texts(client, model: str, texts: list[str]) -> list[list[float]]:
            embeddings = []
            for value in texts:
                if "支付" in value or "服务费" in value:
                    embeddings.append([1.0, 0.0])
                else:
                    embeddings.append([0.0, 1.0])
            return embeddings

        with patch("Agent.app.audit.engine.chat_complete", return_value=json.dumps(mocked_json)):
            with patch("Agent.app.audit.engine.create_openai_client", return_value=object()):
                with patch("Agent.app.legal.retrieval.create_openai_client", return_value=object()):
                    with patch(
                        "Agent.app.legal.retrieval.embed_texts",
                        side_effect=fake_embed_texts,
                    ):
                        result = run_audit(contract_text, legal_articles, config)
        data = json.loads(result.raw_json)
        self.assertEqual(data["overall_risk_score"], 35)
        self.assertEqual(len(data["issues"]), 1)


if __name__ == "__main__":
    unittest.main()
