import json

import httpx

from learning_assistant.ks_gateway import KSGatewayClient
from learning_assistant.question_generation import generate_multiple_choice_question
from learning_assistant.settings import GatewaySettings


def test_ks_gateway_error_includes_response_without_secrets() -> None:
    settings = GatewaySettings.model_validate(
        {
            "KS_CLIENT_ID": "client-id",
            "KS_CLIENT_SECRET": "client-secret",
            "KS_BASE_URL": "https://gateway.example.test",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "token-123",
                    "token_type": "bearer",
                    "expires_in": 3600,
                },
                request=request,
            )

        return httpx.Response(
            400,
            json={"detail": "model is not available"},
            request=request,
        )

    client = KSGatewayClient(settings=settings, transport=httpx.MockTransport(handler))

    try:
        client.infer("Generate a question", model="GPT-5.5")
    except RuntimeError as error:
        message = str(error)
    else:
        raise AssertionError("Expected a RuntimeError")

    assert "HTTP 400" in message
    assert "model is not available" in message
    assert "client-secret" not in message


def test_ks_gateway_client_caches_token_and_extracts_ai_answer() -> None:
    auth_calls = 0
    infer_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls, infer_calls

        if request.url.path == "/auth/token":
            auth_calls += 1
            return httpx.Response(
                200,
                json={
                    "access_token": "token-123",
                    "token_type": "bearer",
                    "expires_in": 3600,
                },
            )

        if request.url.path == "/ai/infer":
            infer_calls += 1
            assert request.headers["authorization"] == "Bearer token-123"
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["response_format"] == "json"
            return httpx.Response(
                200,
                json={
                    "ai_answer": '{"question":"What is 2 + 2?","options":["1","2","4","8"],"correct_index":2}',
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

    first_token = client.get_token()
    second_token = client.get_token()
    question = generate_multiple_choice_question(
        "The Earth orbits the Sun once every year.",
        client=client,
    )

    print("Raw AI answer:")
    print('{"question":"What is 2 + 2?","options":["1","2","4","8"],"correct_index":2}')
    print("Parsed question:", question.model_dump())

    assert first_token == "token-123"
    assert second_token == "token-123"
    assert auth_calls == 1
    assert infer_calls == 1
    assert question.question == "What is 2 + 2?"
    assert question.options == ["1", "2", "4", "8"]
    assert question.correct_index == 2
