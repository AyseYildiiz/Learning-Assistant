import json
from pathlib import Path

import httpx
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from learning_assistant.cli import run_pipeline
from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.settings import GatewaySettings


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


def test_run_pipeline_generates_five_questions(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_text_pdf(
        pdf_path, "Photosynthesis converts light energy into chemical energy."
    )

    responses = [
        '{"question":"What does photosynthesis convert?","options":["Light into energy","Water into air","Heat into sound","Soil into roots"],"correct_index":0}',
        '{"question":"What type of energy is produced?","options":["Chemical energy","Nuclear energy","Electrical energy","Thermal energy"],"correct_index":0}',
        '{"question":"What is the input source mentioned?","options":["Light","Coal","Wind","Metal"],"correct_index":0}',
        '{"question":"Which process is described?","options":["Photosynthesis","Evaporation","Fermentation","Combustion"],"correct_index":0}',
        '{"question":"What do plants use the converted energy for?","options":["Growth and life processes","Melting rocks","Making metal","Driving cars"],"correct_index":0}',
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "token-abc",
                    "token_type": "bearer",
                    "expires_in": 3600,
                },
            )

        if request.url.path == "/ai/infer":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["response_format"] == "json"
            assert payload["prompt"].startswith("You are generating question")
            return httpx.Response(
                200,
                json={
                    "ai_answer": responses.pop(0),
                    "language": "en-US",
                    "response_format": "json",
                    "response_time_ms": 10,
                },
            )

        return httpx.Response(404)

    settings = GatewaySettings.model_validate(
        {
            "KS_CLIENT_ID": "client-id",
            "KS_CLIENT_SECRET": "client-secret",
            "KS_BASE_URL": "https://gateway.example.test",
        }
    )
    client = KSGatewayClient(settings=settings, transport=httpx.MockTransport(handler))

    payload = run_pipeline(pdf_path=pdf_path, count=5, model=None, client=client)

    questions = payload["questions"]

    assert payload["source_pdf"] == str(pdf_path)
    assert payload["question_count"] == 5
    assert isinstance(questions, list)
    assert len(questions) == 5
