from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class LegalArticle:
    source_path: str
    source_title: str
    article_no: str
    content: str
    embedding: Optional[List[float]] = None


@dataclass(frozen=True)
class LegalArticleRef:
    source_path: str
    article_no: str
    quote: str


@dataclass(frozen=True)
class AuditResult:
    raw_json: str
    token_usage: Optional[dict[str, int]] = None
