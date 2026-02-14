from collections import Counter
from typing import List
import math
import re

from Agent.app.config import AppConfig
from Agent.app.llm.openai_client import create_openai_client, embed_texts
from Agent.app.models import LegalArticle


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")


def retrieve_top_articles(
    contract_text: str,
    articles: List[LegalArticle],
    max_articles: int,
    config: AppConfig,
) -> List[LegalArticle]:
    if config.use_full_artical:
        return articles
    if not contract_text.strip():
        return articles[:max_articles]
    if not articles:
        return []
    query_tokens = _tokenize(contract_text)
    query_counts = Counter(query_tokens)
    doc_term_counts, doc_lengths, doc_freqs, avg_doc_length = _build_corpus_stats(
        articles
    )
    total_docs = len(articles)
    client = create_openai_client(
        api_key=config.embedding_api_key,
        base_url=config.embedding_base,
    )
    query_embedding = embed_texts(
        client=client,
        model=config.embedding_model,
        texts=[contract_text],
    )[0]
    article_embeddings = _get_article_embeddings(
        client=client,
        model=config.embedding_model,
        articles=articles,
    )
    bm25_scores = []
    for index, article in enumerate(articles):
        bm25_scores.append(
            _bm25_score(
                query_counts,
                doc_term_counts[index],
                doc_lengths[index],
                avg_doc_length,
                doc_freqs,
                total_docs,
            )
        )
    bm25_norm = _normalize_scores(bm25_scores)
    scored = []
    for index, (article, embedding) in enumerate(zip(articles, article_embeddings)):
        cosine = _cosine_similarity_vector(query_embedding, embedding)
        cosine_norm = (cosine + 1.0) / 2.0
        score = 0.6 * cosine_norm + 0.4 * bm25_norm[index]
        scored.append((score, article))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:max_articles]]


def _tokenize(text: str) -> List[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _build_corpus_stats(articles: List[LegalArticle]):
    doc_term_counts = []
    doc_lengths = []
    doc_freqs = Counter()
    for article in articles:
        tokens = _tokenize(article.content)
        counts = Counter(tokens)
        doc_term_counts.append(counts)
        doc_length = sum(counts.values())
        doc_lengths.append(doc_length)
        for term in counts.keys():
            doc_freqs[term] += 1
    avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0.0
    return doc_term_counts, doc_lengths, doc_freqs, avg_doc_length


def _bm25_score(
    query_counts: Counter,
    doc_counts: Counter,
    doc_len: int,
    avg_doc_len: float,
    doc_freqs: Counter,
    total_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if doc_len == 0 or avg_doc_len == 0 or total_docs == 0:
        return 0.0
    score = 0.0
    for term in query_counts.keys():
        tf = doc_counts.get(term, 0)
        if tf == 0:
            continue
        df = doc_freqs.get(term, 0)
        if df == 0:
            continue
        idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1.0 - b + b * doc_len / avg_doc_len)
        score += idf * (tf * (k1 + 1.0) / denom)
    return score


def _normalize_scores(scores: List[float]) -> List[float]:
    if not scores:
        return []
    max_value = max(scores)
    if max_value <= 0:
        return [0.0 for _ in scores]
    return [value / max_value for value in scores]


def _get_article_embeddings(
    client,
    model: str,
    articles: List[LegalArticle],
) -> List[List[float]]:
    stored = [article.embedding for article in articles]
    missing = [index for index, item in enumerate(stored) if not item]
    if not missing:
        return stored
    texts = [articles[index].content for index in missing]
    generated = embed_texts(client=client, model=model, texts=texts)
    generated_iter = iter(generated)
    resolved = []
    for index, item in enumerate(stored):
        if item:
            resolved.append(item)
            continue
        resolved.append(next(generated_iter))
    return resolved


def _cosine_similarity_vector(
    query_embedding: List[float],
    doc_embedding: List[float],
) -> float:
    if not query_embedding or not doc_embedding:
        return 0.0
    if len(query_embedding) != len(doc_embedding):
        return 0.0
    dot = 0.0
    query_norm_sq = 0.0
    doc_norm_sq = 0.0
    for q_value, d_value in zip(query_embedding, doc_embedding):
        dot += q_value * d_value
        query_norm_sq += q_value * q_value
        doc_norm_sq += d_value * d_value
    if query_norm_sq == 0.0 or doc_norm_sq == 0.0:
        return 0.0
    return dot / (math.sqrt(query_norm_sq) * math.sqrt(doc_norm_sq))
