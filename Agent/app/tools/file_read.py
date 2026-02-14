from pathlib import Path
from typing import List

from Agent.app.preprocess.extract_text import extract_text


def list_legal_files(workspace_dir: Path) -> List[Path]:
    workspace = workspace_dir.resolve()
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace}")
    allowed_suffixes = {".txt", ".md", ".pdf", ".docx"}
    files = []
    for path in workspace.rglob("*"):
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            files.append(path)
    return files


def read_legal_file(file_path: Path, workspace_dir: Path) -> str:
    target = file_path.resolve()
    workspace = workspace_dir.resolve()
    if not _is_within(target, workspace):
        raise PermissionError("file_read only allows access within legal workspace")
    try:
        return extract_text(target)
    except Exception as exc:
        raise ValueError(f"Failed to read legal file: {target}") from exc


def _is_within(target: Path, workspace: Path) -> bool:
    try:
        target.relative_to(workspace)
        return True
    except ValueError:
        return False
