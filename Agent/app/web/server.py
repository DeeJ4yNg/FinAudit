from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import json
import cgi

from Agent.app.audit.engine import run_audit
from Agent.app.cli import _load_legal_articles
from Agent.app.config import AppConfig
from Agent.app.preprocess.extract_text import extract_text
from Agent.app.tools.file_read import list_legal_files, read_legal_file


@dataclass(frozen=True)
class ServerConfig:
    legal_workspace: Path
    static_dir: Path
    contract_upload_dir: Path


class LegalWebHandler(BaseHTTPRequestHandler):
    server_version = "LegalWeb/1.0"

    def __init__(self, *args, config: ServerConfig, **kwargs):
        self.config = config
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._serve_static("index.html")
        if parsed.path == "/api/legal":
            return self._handle_legal_list()
        if parsed.path == "/api/legal/content":
            return self._handle_legal_content(parsed)
        if parsed.path == "/api/contract/list":
            return self._handle_contract_list()
        return self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/legal/upload":
            return self._handle_upload(
                dest_dir=self.config.legal_workspace,
                allowed_suffixes={".txt", ".md", ".pdf", ".docx"},
            )
        if parsed.path == "/api/contract/upload":
            return self._handle_upload(
                dest_dir=self.config.contract_upload_dir,
                allowed_suffixes={".pdf", ".docx"},
            )
        if parsed.path == "/api/audit/run":
            return self._handle_audit_run()
        return self._send_json({"error": "Not found"}, status=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/legal":
            return self._handle_legal_delete(parsed)
        return self._send_json({"error": "Not found"}, status=404)

    def _serve_static(self, name: str):
        target = self.config.static_dir / name
        if not target.exists():
            return self._send_json({"error": "Not found"}, status=404)
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_legal_list(self):
        workspace = self.config.legal_workspace.resolve()
        items = []
        for path in list_legal_files(workspace):
            stat = path.stat()
            relative = str(path.resolve().relative_to(workspace))
            items.append(
                {
                    "path": relative,
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )
        items.sort(key=lambda item: item["name"])
        return self._send_json({"files": items})

    def _handle_legal_content(self, parsed):
        params = parse_qs(parsed.query or "")
        path = params.get("path", [None])[0]
        if not path:
            return self._send_json({"error": "path is required"}, status=400)
        cleaned = path.strip().strip('"').strip("'")
        if cleaned.startswith("[") and cleaned.endswith("]") and len(cleaned) > 2:
            cleaned = cleaned[1:-1].strip()
        if cleaned.startswith("file://"):
            cleaned = cleaned.replace("file://", "", 1).lstrip("/")
        target = self._resolve_in_workspace(cleaned)
        if not target or not target.exists():
            target = self._find_legal_by_name(cleaned)
        if not target or not target.exists():
            return self._send_json({"error": "file not found"}, status=404)
        text = read_legal_file(target, self.config.legal_workspace)
        return self._send_json({"path": path, "content": text})

    def _handle_legal_delete(self, parsed):
        params = parse_qs(parsed.query or "")
        path = params.get("path", [None])[0]
        if not path:
            return self._send_json({"error": "path is required"}, status=400)
        target = self._resolve_in_workspace(path)
        if not target or not target.exists():
            return self._send_json({"error": "file not found"}, status=404)
        target.unlink()
        return self._send_json({"deleted": path})

    def _handle_contract_list(self):
        folder = self.config.contract_upload_dir.resolve()
        if not folder.exists():
            return self._send_json({"files": []})
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
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )
        items.sort(key=lambda item: item["modified"], reverse=True)
        return self._send_json({"files": items})

    def _handle_upload(self, dest_dir: Path, allowed_suffixes: set[str]):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self._send_json({"error": "multipart/form-data required"}, status=400)
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )
        if "file" not in form:
            return self._send_json({"error": "file is required"}, status=400)
        file_item = form["file"]
        if not file_item.filename:
            return self._send_json({"error": "invalid filename"}, status=400)
        filename = Path(file_item.filename).name
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed_suffixes:
            return self._send_json({"error": "unsupported file type"}, status=400)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / filename
        with target.open("wb") as handler:
            handler.write(file_item.file.read())
        return self._send_json(
            {
                "name": filename,
                "path": str(target.resolve()),
                "size": target.stat().st_size,
            }
        )

    def _resolve_in_workspace(self, input_path: str) -> Path | None:
        workspace = self.config.legal_workspace.resolve()
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

    def _find_legal_by_name(self, input_path: str) -> Path | None:
        name = Path(input_path).name
        if not name:
            return None
        workspace = self.config.legal_workspace.resolve()
        matches = [path for path in list_legal_files(workspace) if path.name == name]
        if not matches:
            stem = Path(name).stem
            matches = [
                path for path in list_legal_files(workspace) if path.stem == stem
            ]
            if not matches:
                return None
        return matches[0]

    def _resolve_in_contracts(self, input_path: str) -> Path | None:
        folder = self.config.contract_upload_dir.resolve()
        candidate = Path(input_path)
        if not candidate.is_absolute():
            candidate = folder / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(folder)
            return resolved
        except Exception:
            return None

    def _handle_audit_run(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._send_json({"error": "invalid json"}, status=400)
        contract = payload.get("contract")
        if not contract:
            return self._send_json({"error": "contract is required"}, status=400)
        target = self._resolve_in_contracts(contract)
        if not target or not target.exists():
            return self._send_json({"error": "contract not found"}, status=404)
        config = AppConfig.from_env(legal_workspace=self.config.legal_workspace, model=None)
        contract_text = extract_text(target)
        legal_articles = _load_legal_articles(self.config.legal_workspace, config)
        result = run_audit(contract_text, legal_articles, config)
        output = json.loads(result.raw_json)
        output["issues"] = self._filter_hallucinated_issues(output.get("issues", []))
        return self._send_json({"result": output})

    def _send_json(self, data: dict, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _filter_hallucinated_issues(self, issues: list[dict]) -> list[dict]:
        cleaned = []
        for issue in issues:
            citations = issue.get("legal_citations") or []
            if not citations:
                continue
            all_valid = True
            for citation in citations:
                source_path = (citation or {}).get("source_path", "")
                if not self._resolve_citation_path(source_path):
                    all_valid = False
                    break
            if all_valid:
                cleaned.append(issue)
        return cleaned

    def _resolve_citation_path(self, raw_path: str) -> Path | None:
        if not raw_path:
            return None
        cleaned = raw_path.strip().strip('"').strip("'")
        if cleaned.startswith("[") and cleaned.endswith("]") and len(cleaned) > 2:
            cleaned = cleaned[1:-1].strip()
        if cleaned.startswith("file://"):
            cleaned = cleaned.replace("file://", "", 1).lstrip("/")
        target = self._resolve_in_workspace(cleaned)
        if target and target.exists():
            return target
        target = self._find_legal_by_name(cleaned)
        if target and target.exists():
            return target
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
    handler = lambda *handler_args, **handler_kwargs: LegalWebHandler(
        *handler_args,
        config=config,
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
