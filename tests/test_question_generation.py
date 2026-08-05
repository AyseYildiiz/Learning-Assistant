import json

import httpx

from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.question_generation import (
    generate_fill_blank_questions,
    generate_multiple_choice_question,
)
from learning_assistant.settings import GatewaySettings


def test_question_generation_handles_fenced_json() -> None:
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
            assert payload["prompt"].startswith("You are generating question")
            return httpx.Response(
                200,
                json={
                    "ai_answer": (
                        "Here is the JSON:\n"
                        "```json\n"
                        '{"question":"Which planet is known as the Red Planet?","options":["Earth","Mars","Venus","Jupiter"],"correct_index":1}\n'
                        "```"
                    ),
                    "language": "en-US",
                    "response_format": "json",
                    "response_time_ms": 18,
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

    question = generate_multiple_choice_question(
        "Planets move around the Sun.", client=client
    )

    print("Raw AI answer:")
    print(
        "Here is the JSON:\n"
        "```json\n"
        '{"question":"Which planet is known as the Red Planet?","options":["Earth","Mars","Venus","Jupiter"],"correct_index":1}\n'
        "```"
    )
    print("Parsed question:", question.model_dump())

    assert question.question == "Which planet is known as the Red Planet?"
    assert question.options[1] == "Mars"
    assert question.correct_index == 1


def test_generate_fill_blank_questions_parses_response() -> None:
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
            assert "fill-in-the-blank question" in payload["prompt"]
            return httpx.Response(
                200,
                json={
                    "ai_answer": (
                        '{"question":"Plants convert light into _____ energy.",'
                        '"answer":"chemical"}'
                    ),
                    "language": "en-US",
                    "response_format": "json",
                    "response_time_ms": 12,
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

    questions = generate_fill_blank_questions(
        "Plants use sunlight to create chemical energy.", count=1, client=client
    )

    assert len(questions) == 1
    assert questions[0].answer == "chemical"
