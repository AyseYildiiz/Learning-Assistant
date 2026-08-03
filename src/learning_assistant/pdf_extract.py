from pathlib import Path

from pypdf import PdfReader


def extract_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"Unsupported file type: {path.suffix}. Only .pdf files are supported."
        )

    reader = PdfReader(path)
    page_texts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(page_texts).strip()
    return text
