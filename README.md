# Learning Assistant

--empty

## PDF extraction tests

Run all tests:

```powershell
uv run pytest -s
```

Run the real-file integration test by setting an environment variable to a real PDF:

```powershell
$env:REAL_PDF_PATH = "C:\\Users\\KSMATADOR\\Downloads\\sample.pdf"
uv run pytest -s tests/test_pdf_extract.py
```

Note: `.docx` files are not supported by `extract_text`; it currently accepts only `.pdf` files.
