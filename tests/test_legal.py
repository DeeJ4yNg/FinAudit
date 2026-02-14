import unittest
from pathlib import Path
from unittest.mock import patch

from Agent.app.config import AppConfig
from Agent.app.legal.parser import parse_legal_articles
from Agent.app.legal.retrieval import retrieve_top_articles


class TestLegalParsing(unittest.TestCase):
    def test_parse_articles(self):
        text = "第一条 甲方应当履行义务。第二条 乙方应当协助。"
        articles = parse_legal_articles(text, Path("law.txt"))
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].article_no, "第一条")
        self.assertEqual(articles[1].article_no, "第二条")

    def test_retrieve_top_articles(self):
        text = "支付 应当 义务"
        articles = parse_legal_articles(
            "第一条 付款应当及时。第二条 违约责任。",
            Path("law.txt"),
        )
        config = AppConfig(
            openai_api_key="test-key",
            openai_base_url=None,
            model="gpt-4.1-mini",
            legal_workspace=Path.cwd(),
            max_articles=5,
            contract_max_chars=1000,
        )

        def fake_embed_texts(client, model: str, texts: list[str]) -> list[list[float]]:
            embeddings = []
            for value in texts:
                if "付款" in value or "支付" in value:
                    embeddings.append([1.0, 0.0])
                else:
                    embeddings.append([0.0, 1.0])
            return embeddings

        with patch("Agent.app.legal.retrieval.create_openai_client", return_value=object()):
            with patch("Agent.app.legal.retrieval.embed_texts", side_effect=fake_embed_texts):
                top = retrieve_top_articles(text, articles, 1, config)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].article_no, "第一条")


if __name__ == "__main__":
    unittest.main()
