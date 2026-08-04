import httpx
import pytest

from learning_assistant.ks_gateway import (
    KSGatewayClient,
    parse_multiple_choice_question,
)
from learning_assistant.settings import GatewaySettings


def test_real_gateway_integration() -> None:
    # Load settings from environment/.env using GatewaySettings.
    # If required values are missing, skip the integration test.
    try:
        settings = GatewaySettings()
    except ValueError:
        pytest.skip("Real gateway credentials not set in environment or .env")

    client = KSGatewayClient(settings=settings)

    try:
        prompt = (
            "You are generating exactly one multiple-choice question from a single paragraph. "
            'Return ONLY JSON using the schema {"question": str, "options": list[str], "correct_index": int}. '
            "Provide exactly 4 options. The correct_index must be zero-based.\n\nParagraph:\n"
            "A typical fluffy cloud actually weighs around one million tonnes."
            ##The Earth is the third planet from the Sun and is the only known planet to support life.
        )

        try:
            ai_answer = client.infer(prompt=prompt)
        except httpx.HTTPStatusError as e:
            resp = e.response
            print("Gateway HTTP error:", resp.status_code, resp.url)
            try:
                print("Response body:")
                print(resp.text)
            except Exception:
                pass
            pytest.fail(f"Gateway returned HTTP {resp.status_code}")

        print("Raw AI answer:")
        print(ai_answer)

        question = parse_multiple_choice_question(ai_answer)
        print("Parsed question:", question.model_dump())

        assert isinstance(question.question, str) and question.question
        assert isinstance(question.options, list) and len(question.options) == 4
        assert isinstance(question.correct_index, int)
        assert 0 <= question.correct_index < len(question.options)

    finally:
        client.close()
