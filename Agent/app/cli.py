from pathlib import Path
import argparse
import json
import sqlite3

from Agent.app.audit.engine import run_audit
from Agent.app.config import AppConfig
from Agent.app.legal.parser import parse_legal_articles
from Agent.app.llm.openai_client import create_openai_client, embed_texts
from Agent.app.models import LegalArticle
from Agent.app.preprocess.extract_text import extract_text
from Agent.app.tools.file_read import list_legal_files, read_legal_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--legal-workspace", required=True)
    parser.add_argument("--model")
    parser.add_argument("--output")
    args = parser.parse_args()

    contract_path = Path(args.contract).resolve()
    legal_workspace = Path(args.legal_workspace).resolve()
    config = AppConfig.from_env(legal_workspace=legal_workspace, model=args.model)

    contract_text = extract_text(contract_path)
    legal_articles = _load_legal_articles(legal_workspace, config)

    result = run_audit(contract_text, legal_articles, config)
    output_json = json.loads(result.raw_json)
    output_text = json.dumps(output_json, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")
    else:
        print(output_text)


def _load_legal_articles(workspace_dir: Path, config: AppConfig):
    articles, failures = _parse_legal_articles(workspace_dir)
    if not articles:
        if failures:
            detail = "\n".join(failures)
            raise ValueError(
                "No legal articles found. Failed files:\n" + detail
            )
        raise ValueError("No legal articles found in legal-workspace")
    db_path = workspace_dir / ".legal_articles.sqlite"
    snapshot = _compute_legal_snapshot(workspace_dir, config)
    if not _is_sqlite_current(db_path, snapshot):
        _write_articles_to_sqlite(db_path, articles, config, snapshot)
    return _read_articles_from_sqlite(db_path)


def _parse_legal_articles(workspace_dir: Path):
    legal_files = list_legal_files(workspace_dir)
    articles = []
    failures = []
    for file_path in legal_files:
        try:
            text = read_legal_file(file_path, workspace_dir)
            articles.extend(parse_legal_articles(text, file_path))
        except Exception as exc:
            failures.append(f"{file_path}: {exc}")
    return articles, failures


def _write_articles_to_sqlite(
    db_path: Path,
    articles: list[LegalArticle],
    config: AppConfig,
    snapshot: dict,
) -> None:
    if db_path.exists():
        db_path.unlink()
    client = create_openai_client(
        api_key=config.embedding_api_key,
        base_url=config.embedding_base,
    )
    embeddings = _embed_articles(client, config.embedding_model, articles)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE legal_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL,
                source_title TEXT NOT NULL,
                article_no TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE legal_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO legal_meta (key, value) VALUES (?, ?)",
            ("snapshot", json.dumps(snapshot, ensure_ascii=False)),
        )
        payload = [
            (
                article.source_path,
                article.source_title,
                article.article_no,
                article.content,
                json.dumps(embedding, ensure_ascii=False),
            )
            for article, embedding in zip(articles, embeddings)
        ]
        conn.executemany(
            """
            INSERT INTO legal_articles (
                source_path,
                source_title,
                article_no,
                content,
                embedding
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()
    finally:
        conn.close()


def _read_articles_from_sqlite(db_path: Path) -> list[LegalArticle]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_path, source_title, article_no, content, embedding
            FROM legal_articles
            ORDER BY id
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        LegalArticle(
            source_path=row[0],
            source_title=row[1],
            article_no=row[2],
            content=row[3],
            embedding=json.loads(row[4]),
        )
        for row in rows
    ]


def _compute_legal_snapshot(workspace_dir: Path, config: AppConfig) -> dict:
    legal_files = list_legal_files(workspace_dir)
    items = []
    for path in legal_files:
        stat = path.stat()
        items.append(
            {
                "path": str(path.resolve()),
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
        )
    items.sort(key=lambda item: item["path"])
    return {
        "files": items,
        "embedding_model": config.embedding_model,
        "embedding_base": config.embedding_base or "",
    }


def _is_sqlite_current(db_path: Path, snapshot: dict) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT value FROM legal_meta WHERE key = ?",
            ("snapshot",),
        ).fetchone()
        if not rows:
            return False
        stored = json.loads(rows[0])
    except Exception:
        return False
    finally:
        conn.close()
    return stored == snapshot


def _embed_articles(
    client,
    model: str,
    articles: list[LegalArticle],
    batch_size: int = 64,
) -> list[list[float]]:
    texts = [article.content for article in articles]
    embeddings = []
    start = 0
    total = len(texts)
    while start < total:
        end = min(start + batch_size, total)
        batch = texts[start:end]
        embeddings.extend(embed_texts(client=client, model=model, texts=batch))
        start = end
    return embeddings


if __name__ == "__main__":
    main()
