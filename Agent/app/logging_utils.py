from __future__ import annotations

from pathlib import Path
import json
import logging
import os
import threading

_lock = threading.Lock()
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    with _lock:
        if _configured:
            return
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        log_path = os.getenv("LOG_PATH", "").strip()
        if not log_path:
            log_path = str(Path.cwd() / "output" / "logs" / "fin_audit.log")
        handlers = []
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        if log_path:
            path = Path(log_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(path), encoding="utf-8")
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)
        logging.basicConfig(level=level, handlers=handlers)
        _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)


def is_llm_content_logging_enabled() -> bool:
    value = os.getenv("LOG_LLM_CONTENT", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def safe_json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)
