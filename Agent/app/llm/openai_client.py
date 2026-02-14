from typing import Any, Optional


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
    return content


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
    response = client.embeddings.create(
        model=model,
        input=texts,
    )
    embeddings = []
    for item in response.data:
        embeddings.append(item.embedding)
    return embeddings


def _ensure_ascii_header(value: str, name: str) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"{name} must be ASCII. Remove non-ASCII characters from the value."
        ) from exc
