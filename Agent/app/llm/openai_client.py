from typing import Any, Optional

from Agent.app.logging_utils import get_logger, is_llm_content_logging_enabled, safe_json


def create_openai_client(api_key: str, base_url: Optional[str]):
    from openai import OpenAI

    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    _ensure_ascii_header(api_key, "OPENAI_API_KEY")
    if base_url:
        _ensure_ascii_header(base_url, "OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def chat_complete(
    client,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0,
) -> str:
    logger = get_logger("llm.chat")
    payload = {
        "model": model,
        "temperature": temperature,
    }
    if is_llm_content_logging_enabled():
        payload["system_prompt"] = system_prompt
        payload["user_prompt"] = user_prompt
    logger.info("llm_request %s", safe_json(payload))
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        message = response.choices[0].message
        content = message.content if message else None
        if not content:
            raise ValueError("OpenAI response was empty")
        if is_llm_content_logging_enabled():
            logger.info("llm_response %s", safe_json({"content": content}))
        logger.info("llm_status %s", safe_json({"status": "success"}))
        return content
    except Exception as exc:
        logger.error("llm_status %s", safe_json({"status": "error", "error": str(exc)}))
        raise


def ensure_json(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    raise ValueError("No JSON object found in response")


def embed_texts(client, model: str, texts: list[str]) -> list[list[float]]:
    logger = get_logger("llm.embed")
    payload = {"model": model, "count": len(texts)}
    if is_llm_content_logging_enabled():
        payload["texts"] = texts
    logger.info("embedding_request %s", safe_json(payload))
    try:
        response = client.embeddings.create(
            model=model,
            input=texts,
        )
        embeddings = []
        for item in response.data:
            embeddings.append(item.embedding)
        logger.info("embedding_status %s", safe_json({"status": "success", "count": len(embeddings)}))
        return embeddings
    except Exception as exc:
        logger.error("embedding_status %s", safe_json({"status": "error", "error": str(exc)}))
        raise


def _ensure_ascii_header(value: str, name: str) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"{name} must be ASCII. Remove non-ASCII characters from the value."
        ) from exc
