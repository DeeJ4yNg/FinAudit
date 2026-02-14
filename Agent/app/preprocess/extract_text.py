from pathlib import Path
from typing import Optional
import importlib


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".docx":
        return extract_text_from_docx(file_path)
    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_text_from_docx(file_path: Path) -> str:
    try:
        import zipfile
        if not zipfile.is_zipfile(file_path):
            raise ValueError("Not a valid DOCX (zip container)")
        from docx import Document
        document = Document(str(file_path))
    except Exception as exc:
        text = _extract_text_with_ooxml(file_path)
        if text and text.strip():
            return text
        raise ValueError(f"Failed to read DOCX: {file_path}") from exc
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join([text for text in paragraphs if text.strip()])


def extract_text_from_pdf(file_path: Path) -> str:
    try:
        module = importlib.import_module("mineru")
        text = _extract_text_with_mineru(module, file_path)
        if text and text.strip():
            return text
    except ModuleNotFoundError:
        pass
    text = _extract_text_with_pypdf(file_path)
    if not text or not text.strip():
        raise ValueError("PDF extracted empty text")
    return text


def _extract_text_with_pypdf(file_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("PDF extraction requires MinerU or pypdf") from exc
    reader = PdfReader(str(file_path))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n".join(pages)


def _extract_text_with_ooxml(file_path: Path) -> Optional[str]:
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return None
            xml_bytes = zf.read("word/document.xml")
    except Exception:
        return None

    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None

    def local(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    lines = []
    for p in root.iter():
        if local(p.tag) != "p":
            continue
        texts = []
        for node in p.iter():
            tag = local(node.tag)
            if tag in {"t", "delText", "instrText"}:
                if node.text:
                    texts.append(node.text)
            elif tag == "tab":
                texts.append("\t")
            elif tag == "br":
                texts.append("\n")
        line = "".join(texts).replace("\n", "").strip()
        if line:
            lines.append(line)
    return "\n".join(lines) if lines else None


def _extract_text_with_mineru(module, file_path: Path) -> Optional[str]:
    candidates = ["extract_text", "pdf_extract", "parse_pdf", "parse"]
    for name in candidates:
        func = getattr(module, name, None)
        if callable(func):
            result = func(str(file_path))
            if isinstance(result, str):
                return result
            return _normalize_result(result)
    classes = ["PDF", "PDFMiner", "MinerU", "Document"]
    for class_name in classes:
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        instance = cls(str(file_path))
        for method_name in ["extract_text", "parse", "text"]:
            method = getattr(instance, method_name, None)
            if callable(method):
                result = method()
                if isinstance(result, str):
                    return result
                return _normalize_result(result)
            if isinstance(method, str):
                return method
    raise ValueError("MinerU interface not recognized")


def _normalize_result(result) -> Optional[str]:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return "\n".join([str(item) for item in result if item])
    return None
