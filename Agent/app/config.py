from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    openai_base_url: Optional[str]
    model: str
    legal_workspace: Path
    max_articles: int
    contract_max_chars: int
    embedding_api_key: str = ""
    embedding_base: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    use_full_artical: bool = False

    @staticmethod
    def from_env(legal_workspace: Path, model: Optional[str]) -> "AppConfig":
        _load_dotenv()
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
        use_full_artical = os.getenv("USE_FULL_ARTICAL", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return AppConfig(
            openai_api_key=api_key,
            openai_base_url=base_url,
            model=selected_model,
            legal_workspace=legal_workspace,
            max_articles=20,
            contract_max_chars=20000,
            embedding_api_key=embedding_api_key,
            embedding_base=embedding_base_url,
            embedding_model=embedding_model,
            use_full_artical=use_full_artical,
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
