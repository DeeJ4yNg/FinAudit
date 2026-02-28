from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

from Agent.app.logging_utils import setup_logging


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    openai_base_url: Optional[str]
    model: str
    legal_workspace: Path
    max_articles: int
    contract_max_chars: int
    memory_len: int = 1200
    embedding_api_key: str = ""
    embedding_base: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    use_full_artical: bool = False
    law_retrieval: int = 2

    @staticmethod
    def from_env(legal_workspace: Path, model: Optional[str]) -> "AppConfig":
        _load_dotenv()
        setup_logging()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL")
        selected_model = model or os.getenv("OPENAI_MODEL", "").strip()
        if not selected_model:
            selected_model = "gpt-4.1-mini"
        embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "").strip()
        if not embedding_model:
            embedding_model = "text-embedding-3-small"
        embedding_api_key = os.getenv("OPENAI_API_KEY_EMBEDDING", "").strip()
        embedding_base_url = os.getenv("OPENAI_API_BASE_EMBEDDING")
        if not embedding_api_key:
            embedding_api_key = api_key
        if not embedding_base_url:
            embedding_base_url = base_url
        law_retrieval_raw = os.getenv("LAW_RETRIEVAL", "").strip()
        law_retrieval = 2
        if law_retrieval_raw:
            try:
                value = int(law_retrieval_raw)
                if value in {1, 2, 3}:
                    law_retrieval = value
                else:
                    law_retrieval = 2
            except ValueError:
                law_retrieval = 2
        else:
            use_full_artical = os.getenv("USE_FULL_ARTICAL", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            law_retrieval = 1 if use_full_artical else 2
        use_full_artical = law_retrieval == 1
        memory_len_raw = os.getenv("MEMORY_LEN", "").strip()
        memory_len = 1200
        if memory_len_raw:
            try:
                memory_len = max(200, int(memory_len_raw))
            except ValueError:
                memory_len = 1200
        contract_max_chars_raw = os.getenv("CONTRACT_MAX_CHARS", "").strip()
        contract_max_chars = 20000
        if contract_max_chars_raw:
            try:
                contract_max_chars = max(200, int(contract_max_chars_raw))
            except ValueError:
                contract_max_chars = 20000
        return AppConfig(
            openai_api_key=api_key,
            openai_base_url=base_url,
            model=selected_model,
            legal_workspace=legal_workspace,
            max_articles=20,
            contract_max_chars=contract_max_chars,
            memory_len=memory_len,
            embedding_api_key=embedding_api_key,
            embedding_base=embedding_base_url,
            embedding_model=embedding_model,
            use_full_artical=use_full_artical,
            law_retrieval=law_retrieval,
        )


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
