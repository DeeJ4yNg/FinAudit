import tempfile
import unittest
from pathlib import Path

from Agent.app.preprocess.extract_text import extract_text


class TestExtractText(unittest.TestCase):
    def test_extract_text_from_txt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "contract.txt"
            file_path.write_text("合同内容", encoding="utf-8")
            self.assertEqual(extract_text(file_path), "合同内容")

    def test_extract_text_from_docx(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "contract.docx"
            if not self._write_docx(file_path, ["合同标题", "条款内容"]):
                self.skipTest("python-docx not installed")
            text = extract_text(file_path)
            self.assertIn("合同标题", text)
            self.assertIn("条款内容", text)

    def _write_docx(self, path: Path, lines):
        try:
            from docx import Document
        except Exception:
            return False

        document = Document()
        for line in lines:
            document.add_paragraph(line)
        document.save(str(path))
        return True


if __name__ == "__main__":
    unittest.main()
