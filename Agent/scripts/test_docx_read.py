from pathlib import Path
from Agent.app.preprocess.extract_text import extract_text
import zipfile


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    files = []
    for folder in [
        root / "data" / "legal",
        root / "data" / "mock" / "legal",
        root / "data" / "mock" / "contracts",
        root,
    ]:
        if folder.exists():
            files.extend(list(folder.rglob("*.docx")))
    if not files:
        print("No DOCX files found")
        return
    errors = []
    for path in files:
        try:
            if not zipfile.is_zipfile(path):
                raise ValueError("Not a valid DOCX (zip container)")
            text = extract_text(path)
            print(f"OK: {path.name} chars={len(text)}")
        except Exception as exc:
            print(f"ERR: {path.name} {exc}")
            errors.append((path, exc))
    if errors:
        print("\nFailed files:")
        for path, exc in errors:
            print(f"- {path}: {exc}")


if __name__ == "__main__":
    main()
