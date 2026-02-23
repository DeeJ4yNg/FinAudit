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
            "summary": "存在支付条款风险",
            "overall": {"risk_count": {"high": 0, "medium": 1, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": [
                {
                    "risk_id": "R-001",
                    "clause_id": "C-1-1-1",
                    "title": "付款条款风险",
                    "level": "中",
                    "score": 12,
                    "likelihood": 3,
                    "impact": 4,
                    "confidence": "中",
                    "tags": ["payment"],
                    "contract_evidence": "甲方应当在30日内支付服务费。",
                    "law_evidence": [
                        {
                            "source_path": "law.txt",
                            "law_ref_id": "L-1-1-1",
                            "quote": "合同当事人应当遵循公平原则。",
                        }
                    ],
                    "risk_reason": "支付条款未明确违约责任",
                    "trigger": "付款逾期",
                    "impact_analysis": "违约责任不明导致索赔困难",
                    "suggested_text": "补充逾期支付违约责任条款。",
                    "open_questions": ["是否约定逾期利率"],
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
        self.assertEqual(data["summary"], "存在支付条款风险")
        self.assertEqual(len(data["risks"]), 1)

    def test_run_audit_with_chunked_retrieval(self):
        contract_text = "甲方应当在30日内支付服务费。\n\n乙方应提供合法发票。"
        legal_articles = [
            LegalArticle(
                source_path="law.txt",
                source_title="法条",
                article_no="第一条",
                content="合同当事人应当遵循公平原则。",
            ),
            LegalArticle(
                source_path="tax.txt",
                source_title="税务条例",
                article_no="第二条",
                content="开票应当符合法律法规。",
            ),
        ]
        config = AppConfig(
            openai_api_key="test-key",
            openai_base_url=None,
            model="gpt-4.1-mini",
            legal_workspace=Path.cwd(),
            max_articles=5,
            contract_max_chars=20,
            law_retrieval=3,
        )
        chunk1_json = {
            "summary": "支付条款风险",
            "overall": {"risk_count": {"high": 0, "medium": 1, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": [
                {
                    "risk_id": "R-001",
                    "clause_id": "C-1-1-1",
                    "title": "付款条款风险",
                    "level": "中",
                    "score": 12,
                    "likelihood": 3,
                    "impact": 4,
                    "confidence": "中",
                    "tags": ["payment"],
                    "contract_evidence": "甲方应当在30日内支付服务费。",
                    "law_evidence": [
                        {
                            "source_path": "law.txt",
                            "law_ref_id": "L-1-1-1",
                            "quote": "合同当事人应当遵循公平原则。",
                        }
                    ],
                    "risk_reason": "支付条款未明确违约责任",
                    "trigger": "付款逾期",
                    "impact_analysis": "违约责任不明导致索赔困难",
                    "suggested_text": "补充逾期支付违约责任条款。",
                    "open_questions": ["是否约定逾期利率"],
                }
            ],
        }
        chunk2_json = {
            "summary": "发票条款风险",
            "overall": {"risk_count": {"high": 0, "medium": 1, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": [
                {
                    "risk_id": "R-002",
                    "clause_id": "C-1-2-1",
                    "title": "发票条款风险",
                    "level": "中",
                    "score": 10,
                    "likelihood": 2,
                    "impact": 5,
                    "confidence": "中",
                    "tags": ["invoice"],
                    "contract_evidence": "乙方应提供合法发票。",
                    "law_evidence": [
                        {
                            "source_path": "tax.txt",
                            "law_ref_id": "L-2-1-1",
                            "quote": "开票应当符合法律法规。",
                        }
                    ],
                    "risk_reason": "发票要求不完整",
                    "trigger": "开票不合规",
                    "impact_analysis": "可能影响进项抵扣",
                    "suggested_text": "补充发票类型、税率与开票时点。",
                    "open_questions": ["是否要求专票"],
                }
            ],
        }
        summary_json = {
            "summary": "存在付款与开票风险",
            "overall": {"risk_count": {"high": 0, "medium": 2, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": chunk1_json["risks"] + chunk2_json["risks"],
        }

        def fake_embed_texts(client, model: str, texts: list[str]) -> list[list[float]]:
            embeddings = []
            for value in texts:
                if "支付" in value or "服务费" in value:
                    embeddings.append([1.0, 0.0])
                else:
                    embeddings.append([0.0, 1.0])
            return embeddings

        with patch(
            "Agent.app.audit.engine.chat_complete",
            side_effect=[
                json.dumps(chunk1_json),
                json.dumps(chunk2_json),
                json.dumps(summary_json),
            ],
        ):
            with patch("Agent.app.audit.engine.create_openai_client", return_value=object()):
                with patch("Agent.app.legal.retrieval.create_openai_client", return_value=object()):
                    with patch(
                        "Agent.app.legal.retrieval.embed_texts",
                        side_effect=fake_embed_texts,
                    ):
                        result = run_audit(contract_text, legal_articles, config)
        data = json.loads(result.raw_json)
        self.assertEqual(data["summary"], "存在付款与开票风险")
        self.assertEqual(len(data["risks"]), 2)

    def test_run_audit_with_full_laws_mode(self):
        contract_text = "甲方应当在30日内支付服务费。\n乙方应提供合法发票。"
        legal_articles = [
            LegalArticle(
                source_path="law.txt",
                source_title="法条",
                article_no="第一条",
                content="合同当事人应当遵循公平原则。",
            ),
            LegalArticle(
                source_path="tax.txt",
                source_title="税务条例",
                article_no="第二条",
                content="开票应当符合法律法规。",
            ),
        ]
        config = AppConfig(
            openai_api_key="test-key",
            openai_base_url=None,
            model="gpt-4.1-mini",
            legal_workspace=Path.cwd(),
            max_articles=1,
            contract_max_chars=5,
            use_full_artical=True,
            law_retrieval=1,
        )
        mocked_json = {
            "summary": "存在支付条款风险",
            "overall": {"risk_count": {"high": 0, "medium": 1, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": [
                {
                    "risk_id": "R-001",
                    "clause_id": "C-1-1-1",
                    "title": "付款条款风险",
                    "level": "中",
                    "score": 12,
                    "likelihood": 3,
                    "impact": 4,
                    "confidence": "中",
                    "tags": ["payment"],
                    "contract_evidence": "甲方应当在30日内支付服务费。",
                    "law_evidence": [
                        {
                            "source_path": "law.txt",
                            "law_ref_id": "L-1-1-1",
                            "quote": "合同当事人应当遵循公平原则。",
                        }
                    ],
                    "risk_reason": "支付条款未明确违约责任",
                    "trigger": "付款逾期",
                    "impact_analysis": "违约责任不明导致索赔困难",
                    "suggested_text": "补充逾期支付违约责任条款。",
                    "open_questions": ["是否约定逾期利率"],
                }
            ],
        }
        captured_prompt = {}

        def fake_chat_complete(client, model, system_prompt, user_prompt, temperature=0):
            captured_prompt["user_prompt"] = user_prompt
            return json.dumps(mocked_json)

        with patch("Agent.app.audit.engine.chat_complete", side_effect=fake_chat_complete):
            with patch("Agent.app.audit.engine.create_openai_client", return_value=object()):
                result = run_audit(contract_text, legal_articles, config)
        data = json.loads(result.raw_json)
        self.assertEqual(data["summary"], "存在支付条款风险")
        self.assertIn("合同当事人应当遵循公平原则。", captured_prompt["user_prompt"])
        self.assertIn("开票应当符合法律法规。", captured_prompt["user_prompt"])
        self.assertIn("乙方应提供合法发票。", captured_prompt["user_prompt"])

    def test_run_audit_with_retrieved_laws_mode(self):
        contract_text = "甲方应当在30日内支付服务费。\n乙方应提供合法发票。"
        legal_articles = [
            LegalArticle(
                source_path="law.txt",
                source_title="法条",
                article_no="第一条",
                content="合同当事人应当遵循公平原则。",
            ),
            LegalArticle(
                source_path="tax.txt",
                source_title="税务条例",
                article_no="第二条",
                content="开票应当符合法律法规。",
            ),
        ]
        config = AppConfig(
            openai_api_key="test-key",
            openai_base_url=None,
            model="gpt-4.1-mini",
            legal_workspace=Path.cwd(),
            max_articles=1,
            contract_max_chars=5,
            law_retrieval=2,
        )
        mocked_json = {
            "summary": "存在支付条款风险",
            "overall": {"risk_count": {"high": 0, "medium": 1, "low": 0}},
            "delta": {"new_risks": [], "changed_risks": [], "closed_risks": [], "clause_changes": []},
            "risks": [
                {
                    "risk_id": "R-001",
                    "clause_id": "C-1-1-1",
                    "title": "付款条款风险",
                    "level": "中",
                    "score": 12,
                    "likelihood": 3,
                    "impact": 4,
                    "confidence": "中",
                    "tags": ["payment"],
                    "contract_evidence": "甲方应当在30日内支付服务费。",
                    "law_evidence": [
                        {
                            "source_path": "law.txt",
                            "law_ref_id": "L-1-1-1",
                            "quote": "合同当事人应当遵循公平原则。",
                        }
                    ],
                    "risk_reason": "支付条款未明确违约责任",
                    "trigger": "付款逾期",
                    "impact_analysis": "违约责任不明导致索赔困难",
                    "suggested_text": "补充逾期支付违约责任条款。",
                    "open_questions": ["是否约定逾期利率"],
                }
            ],
        }
        captured_prompt = {}

        def fake_chat_complete(client, model, system_prompt, user_prompt, temperature=0):
            captured_prompt["user_prompt"] = user_prompt
            return json.dumps(mocked_json)

        with patch("Agent.app.audit.engine.retrieve_top_articles", return_value=[legal_articles[0]]):
            with patch("Agent.app.audit.engine.chat_complete", side_effect=fake_chat_complete):
                with patch("Agent.app.audit.engine.create_openai_client", return_value=object()):
                    result = run_audit(contract_text, legal_articles, config)
        data = json.loads(result.raw_json)
        self.assertEqual(data["summary"], "存在支付条款风险")
        self.assertIn("合同当事人应当遵循公平原则。", captured_prompt["user_prompt"])
        self.assertNotIn("开票应当符合法律法规。", captured_prompt["user_prompt"])
        self.assertIn("乙方应提供合法发票。", captured_prompt["user_prompt"])


if __name__ == "__main__":
    unittest.main()
