import os
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from learning_assistant.pdf_extract import extract_text


def _write_text_pdf(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
    )

    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 100 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(content)

    with path.open("wb") as output_file:
        writer.write(output_file)


def test_extract_text_returns_non_empty_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_text_pdf(pdf_path, "Hello world")

    extracted_text = extract_text(pdf_path)
    print(f"Extracted text: {extracted_text}")

    assert extracted_text != ""
    assert "Hello world" in extracted_text


def test_extract_text_rejects_non_pdf_file(tmp_path: Path) -> None:
    docx_like_file = tmp_path / "sample.docx"
    docx_like_file.write_text("not a real docx", encoding="utf-8")

    with pytest.raises(ValueError, match="Only \\.pdf files are supported"):
        extract_text(docx_like_file)


def test_extract_text_with_real_pdf_from_env() -> None:
    real_pdf_path = os.getenv("REAL_PDF_PATH")
    if not real_pdf_path:
        pytest.skip("REAL_PDF_PATH is not set")

    pdf_path = Path(real_pdf_path)
    if not pdf_path.exists():
        pytest.skip(f"REAL_PDF_PATH does not exist: {pdf_path}")

    extracted_text = extract_text(pdf_path)
    assert extracted_text != ""
