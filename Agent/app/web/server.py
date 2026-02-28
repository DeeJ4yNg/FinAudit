from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import json
import tempfile

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from Agent.app.audit.engine import run_audit
from Agent.app.audit.memory_update import update_memory_from_feedback
from Agent.app.cli import _load_legal_articles
from Agent.app.config import AppConfig
from Agent.app.legal.reformat_law import reformat_law_text
from Agent.app.logging_utils import get_logger, safe_json
from Agent.app.preprocess.extract_text import extract_text
from Agent.app.tools.file_read import list_legal_files, read_legal_file


@dataclass(frozen=True)
class ServerConfig:
    legal_workspace: Path
    static_dir: Path
    contract_upload_dir: Path


def create_app(config: ServerConfig) -> FastAPI:
    app = FastAPI()
    logger = get_logger("api")
    if config.static_dir.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(config.static_dir)),
            name="static",
        )

    @app.get("/")
    async def serve_index():
        return _serve_index(config)

    @app.get("/index.html")
    async def serve_index_alias():
        return _serve_index(config)

    @app.get("/api/legal")
    async def legal_list():
        workspace = config.legal_workspace.resolve()
        items = []
        for path in list_legal_files(workspace):
            stat = path.stat()
            relative = str(path.resolve().relative_to(workspace))
            items.append(
                {
                    "path": relative,
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                        timespec="seconds"
                    ),
                }
            )
        items.sort(key=lambda item: item["name"])
        return JSONResponse({"files": items})

    @app.get("/api/legal/content")
    async def legal_content(path: str | None = None):
        if not path:
            return JSONResponse({"error": "path is required"}, status_code=400)
        cleaned = _clean_path(path)
        target = _resolve_in_workspace(config, cleaned)
        if not target or not target.exists():
            target = _find_legal_by_name(config, cleaned)
        if not target or not target.exists():
            return JSONResponse({"error": "file not found"}, status_code=404)
        text = read_legal_file(target, config.legal_workspace)
        return JSONResponse({"path": path, "content": text})

    @app.delete("/api/legal")
    async def legal_delete(path: str | None = None):
        if not path:
            return JSONResponse({"error": "path is required"}, status_code=400)
        target = _resolve_in_workspace(config, path)
        if not target or not target.exists():
            return JSONResponse({"error": "file not found"}, status_code=404)
        target.unlink()
        return JSONResponse({"deleted": path})

    @app.post("/api/legal/upload")
    async def legal_upload(file: UploadFile | None = File(None)):
        if file is None:
            return JSONResponse({"error": "file is required"}, status_code=400)
        return await _handle_upload(
            dest_dir=config.legal_workspace,
            allowed_suffixes={".txt", ".md", ".pdf", ".docx"},
            file=file,
        )

    @app.post("/api/legal/reformat")
    async def legal_reformat(request: Request):
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            payload = await _read_json_payload(request)
            if payload is None:
                return JSONResponse({"error": "invalid json"}, status_code=400)
            path = payload.get("path")
            if not path:
                return JSONResponse({"error": "path is required"}, status_code=400)
            target = _resolve_in_workspace(config, path)
            if not target or not target.exists():
                target = _find_legal_by_name(config, path)
            if not target or not target.exists():
                return JSONResponse({"error": "file not found"}, status_code=404)
            source_text = read_legal_file(target, config.legal_workspace)
            filename = target.name
        elif "multipart/form-data" in content_type:
            form = await request.form()
            form_file = form.get("file")
            if not isinstance(form_file, UploadFile):
                return JSONResponse({"error": "file is required"}, status_code=400)
            filename = Path(form_file.filename or "").name
            if not filename:
                return JSONResponse({"error": "invalid filename"}, status_code=400)
            suffix = Path(filename).suffix.lower()
            allowed_suffixes = {".txt", ".md", ".pdf", ".docx"}
            if suffix not in allowed_suffixes:
                return JSONResponse({"error": "unsupported file type"}, status_code=400)
            temp_path = None
            data = await form_file.read()
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                    temp.write(data)
                    temp_path = Path(temp.name)
                source_text = extract_text(temp_path)
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink(missing_ok=True)
        else:
            return JSONResponse({"error": "unsupported content type"}, status_code=400)
        if not source_text.strip():
            return JSONResponse({"error": "empty content"}, status_code=400)
        app_config = AppConfig.from_env(legal_workspace=config.legal_workspace, model=None)
        formatted = reformat_law_text(
            source_text=source_text,
            config=app_config,
            model=None,
            temperature=0,
        )
        return JSONResponse(
            {
                "name": filename,
                "suggested_name": _suggest_reformat_name(filename),
                "content": formatted,
            }
        )

    @app.post("/api/legal/reformat/confirm")
    async def legal_reformat_confirm(request: Request):
        payload = await _read_json_payload(request)
        if payload is None:
            return JSONResponse({"error": "invalid json"}, status_code=400)
        path = payload.get("path")
        content = payload.get("content", "")
        if not path:
            return JSONResponse({"error": "path is required"}, status_code=400)
        if not isinstance(content, str) or not content.strip():
            return JSONResponse({"error": "content is required"}, status_code=400)
        target = _resolve_in_workspace(config, path)
        if not target or not target.exists():
            target = _find_legal_by_name(config, path)
        if not target or not target.exists():
            return JSONResponse({"error": "file not found"}, status_code=404)
        save_path = config.legal_workspace.resolve() / _suggest_reformat_name(target.name)
        if save_path.resolve() == target.resolve():
            save_path.write_text(content, encoding="utf-8")
            return JSONResponse({"saved": save_path.name, "deleted": None})
        save_path.write_text(content, encoding="utf-8")
        target.unlink()
        return JSONResponse({"saved": save_path.name, "deleted": target.name})

    @app.get("/api/contract/list")
    async def contract_list():
        folder = config.contract_upload_dir.resolve()
        if not folder.exists():
            return JSONResponse({"files": []})
        items = []
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".docx"}:
                continue
            stat = path.stat()
            relative = str(path.resolve().relative_to(folder))
            items.append(
                {
                    "path": relative,
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                        timespec="seconds"
                    ),
                }
            )
        items.sort(key=lambda item: item["modified"], reverse=True)
        return JSONResponse({"files": items})

    @app.post("/api/contract/upload")
    async def contract_upload(file: UploadFile | None = File(None)):
        if file is None:
            return JSONResponse({"error": "file is required"}, status_code=400)
        return await _handle_upload(
            dest_dir=config.contract_upload_dir,
            allowed_suffixes={".pdf", ".docx"},
            file=file,
        )

    @app.post("/api/audit/run")
    async def audit_run(request: Request):
        payload = await _read_json_payload(request)
        if payload is None:
            logger.info("api_status %s", safe_json({"path": "/api/audit/run", "status": "error", "error": "invalid json"}))
            return JSONResponse({"error": "invalid json"}, status_code=400)
        contract = payload.get("contract")
        if not contract:
            logger.info("api_status %s", safe_json({"path": "/api/audit/run", "status": "error", "error": "contract is required"}))
            return JSONResponse({"error": "contract is required"}, status_code=400)
        target = _resolve_in_contracts(config, contract)
        if not target or not target.exists():
            logger.info("api_status %s", safe_json({"path": "/api/audit/run", "status": "error", "error": "contract not found"}))
            return JSONResponse({"error": "contract not found"}, status_code=404)
        logger.info("audit_request %s", safe_json({"contract": str(target)}))
        try:
            app_config = AppConfig.from_env(legal_workspace=config.legal_workspace, model=None)
            contract_text = extract_text(target)
            legal_articles = _load_legal_articles(config.legal_workspace, app_config)
            result = run_audit(contract_text, legal_articles, app_config)
            output = json.loads(result.raw_json)
            output["risks"] = _filter_hallucinated_risks(config, output.get("risks", []))
            logger.info("api_status %s", safe_json({"path": "/api/audit/run", "status": "success"}))
            return JSONResponse({"result": output, "token_usage": result.token_usage or {}})
        except Exception as exc:
            logger.error("api_status %s", safe_json({"path": "/api/audit/run", "status": "error", "error": str(exc)}))
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.post("/api/audit/feedback")
    async def audit_feedback(request: Request):
        payload = await _read_json_payload(request)
        if payload is None:
            logger.info("api_status %s", safe_json({"path": "/api/audit/feedback", "status": "error", "error": "invalid json"}))
            return JSONResponse({"error": "invalid json"}, status_code=400)
        feedback = payload.get("feedback", "")
        audit_result = payload.get("audit_result")
        error = _validate_feedback_payload(feedback, audit_result)
        if error:
            logger.info("api_status %s", safe_json({"path": "/api/audit/feedback", "status": "error", "error": error}))
            return JSONResponse({"error": error}, status_code=400)
        if isinstance(audit_result, str):
            audit_result = json.loads(audit_result)
        logger.info("feedback_request %s", safe_json({"length": len(feedback)}))
        try:
            app_config = AppConfig.from_env(legal_workspace=config.legal_workspace, model=None)
            updated_memory = update_memory_from_feedback(
                config=app_config,
                feedback=feedback,
                audit_result=audit_result,
            )
            logger.info("api_status %s", safe_json({"path": "/api/audit/feedback", "status": "success"}))
            return JSONResponse({"memory": updated_memory, "length": len(updated_memory)})
        except Exception as exc:
            logger.error("api_status %s", safe_json({"path": "/api/audit/feedback", "status": "error", "error": str(exc)}))
            return JSONResponse({"error": str(exc)}, status_code=500)

    return app


def _serve_index(config: ServerConfig):
    target = config.static_dir / "index.html"
    if not target.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(target, media_type="text/html")


def _clean_path(raw_path: str) -> str:
    cleaned = raw_path.strip().strip('"').strip("'")
    if cleaned.startswith("[") and cleaned.endswith("]") and len(cleaned) > 2:
        cleaned = cleaned[1:-1].strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned.replace("file://", "", 1).lstrip("/")
    return cleaned


def _resolve_in_workspace(config: ServerConfig, input_path: str) -> Path | None:
    workspace = config.legal_workspace.resolve()
    candidate = Path(input_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(workspace)
        return resolved
    except Exception:
        resolved = candidate.resolve()
        resolved_str = str(resolved).lower()
        workspace_str = str(workspace).lower()
        if resolved_str == workspace_str:
            return resolved
        if resolved_str.startswith(workspace_str + "\\") or resolved_str.startswith(
            workspace_str + "/"
        ):
            return resolved
        return None


def _find_legal_by_name(config: ServerConfig, input_path: str) -> Path | None:
    name = Path(input_path).name
    if not name:
        return None
    workspace = config.legal_workspace.resolve()
    matches = [path for path in list_legal_files(workspace) if path.name == name]
    if not matches:
        stem = Path(name).stem
        matches = [path for path in list_legal_files(workspace) if path.stem == stem]
        if not matches:
            return None
    return matches[0]


def _resolve_in_contracts(config: ServerConfig, input_path: str) -> Path | None:
    folder = config.contract_upload_dir.resolve()
    candidate = Path(input_path)
    if not candidate.is_absolute():
        candidate = folder / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(folder)
        return resolved
    except Exception:
        return None


def _validate_feedback_payload(feedback: Any, audit_result: Any) -> str | None:
    if not isinstance(feedback, str):
        return "feedback must be string"
    feedback_text = feedback.strip()
    if not feedback_text:
        return "feedback is required"
    if len(feedback_text) < 10:
        return "feedback is too short"
    if len(feedback_text) > 2000:
        return "feedback is too long"
    if audit_result is None:
        return "audit_result is required"
    audit_value = audit_result
    if isinstance(audit_value, str):
        try:
            audit_value = json.loads(audit_value)
        except json.JSONDecodeError:
            return "audit_result must be json"
    if not isinstance(audit_value, dict):
        return "audit_result must be object"
    if len(json.dumps(audit_value, ensure_ascii=False)) > 20000:
        return "audit_result is too large"
    return None


async def _handle_upload(
    dest_dir: Path,
    allowed_suffixes: set[str],
    file: UploadFile,
) -> JSONResponse:
    filename = Path(file.filename or "").name
    if not filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        return JSONResponse({"error": "unsupported file type"}, status_code=400)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / filename
    data = await file.read()
    with target.open("wb") as handler:
        handler.write(data)
    return JSONResponse(
        {
            "name": filename,
            "path": str(target.resolve()),
            "size": target.stat().st_size,
        }
    )


def _filter_hallucinated_risks(
    config: ServerConfig, risks: list[dict]
) -> list[dict]:
    cleaned = []
    for risk in risks:
        citations = risk.get("law_evidence") or []
        if not citations:
            continue
        all_valid = True
        for citation in citations:
            source_path = (citation or {}).get("source_path", "")
            if not _resolve_citation_path(config, source_path):
                all_valid = False
                break
        if all_valid:
            cleaned.append(risk)
    return cleaned


def _resolve_citation_path(config: ServerConfig, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    cleaned = _clean_path(raw_path)
    target = _resolve_in_workspace(config, cleaned)
    if target and target.exists():
        return target
    target = _find_legal_by_name(config, cleaned)
    if target and target.exists():
        return target
    return None


def _suggest_reformat_name(filename: str) -> str:
    name = Path(filename).name
    if not name:
        return "reformatted.txt"
    stem = Path(name).stem
    if not stem:
        return "reformatted.txt"
    return f"{stem}_reformat.txt"




async def _read_json_payload(request: Request) -> dict[str, Any] | None:
    try:
        return await request.json()
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legal-workspace", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[3]
    static_dir = root / "Agent" / "app" / "web" / "static"
    upload_dir = root / "output" / "contracts"
    config = ServerConfig(
        legal_workspace=Path(args.legal_workspace).resolve(),
        static_dir=static_dir,
        contract_upload_dir=upload_dir,
    )
    app = create_app(config)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
