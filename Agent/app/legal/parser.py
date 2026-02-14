from pathlib import Path
from typing import List
import re

from Agent.app.models import LegalArticle


ARTICLE_PATTERN = re.compile(r"(第[一二三四五六七八九十百千0-9]+条)")


def parse_legal_articles(text: str, source_path: Path) -> List[LegalArticle]:
    source_title = source_path.stem
    matches = list(ARTICLE_PATTERN.finditer(text))
    if not matches:
        return _fallback_single_article(text, source_path, source_title)
    articles = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        article_no = match.group(1)
        content = text[start:end].strip()
        if not content:
            continue
        articles.append(
            LegalArticle(
                source_path=str(source_path),
                source_title=source_title,
                article_no=article_no,
                content=content,
            )
        )
    if not articles:
        return _fallback_single_article(text, source_path, source_title)
    return articles


def _fallback_single_article(
    text: str,
    source_path: Path,
    source_title: str,
) -> List[LegalArticle]:
    content = text.strip()
    if not content:
        return []
    return [
        LegalArticle(
            source_path=str(source_path),
            source_title=source_title,
            article_no="全文",
            content=content,
        )
    ]
