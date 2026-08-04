from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from learning_assistant.settings import GatewaySettings


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int = 3600


class InferResponse(BaseModel):
    ai_answer: str


class MultipleChoiceQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int


@dataclass(slots=True)
class _TokenCache:
    access_token: str
    expires_at: datetime


class KSGatewayClient:
    def __init__(
        self,
        settings: GatewaySettings | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._settings = settings or GatewaySettings()
        self._client = httpx.Client(
            base_url=self._settings.normalized_base_url(),
            transport=transport,
            timeout=timeout,
        )
        self._token_cache: _TokenCache | None = None

    def close(self) -> None:
        self._client.close()

    def get_token(self) -> str:
        cache = self._token_cache
        if cache is not None and datetime.now(UTC) < cache.expires_at:
            return cache.access_token

        response = self._client.post(
            "/auth/token",
            json={
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret,
            },
        )
        response.raise_for_status()

        token_response = TokenResponse.model_validate(response.json())
        expires_at = datetime.now(UTC) + timedelta(seconds=max(token_response.expires_in - 30, 0))
        self._token_cache = _TokenCache(
            access_token=token_response.access_token,
            expires_at=expires_at,
        )
        return token_response.access_token

    def infer(self, prompt: str, model: str | None = None) -> str:
        token = self.get_token()
        payload: dict[str, Any] = {
            "prompt": prompt,
            "language": self._settings.response_language,
            "response_format": "json",
        }
        if model is not None:
            payload["model"] = model

        response = self._client.post(
            "/ai/infer",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()

        infer_response = InferResponse.model_validate(response.json())
        return infer_response.ai_answer


def _extract_json_candidate(raw_text: str) -> str:
    stripped_text = raw_text.strip()

    fenced_match = re.search(
        r"```(?:json)?\s*(.*?)\s*```",
        stripped_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced_match is not None:
        return fenced_match.group(1).strip()

    object_match = re.search(r"\{.*\}", stripped_text, flags=re.DOTALL)
    if object_match is not None:
        return object_match.group(0)

    return stripped_text


def parse_multiple_choice_question(raw_text: str) -> MultipleChoiceQuestion:
    candidate_text = _extract_json_candidate(raw_text)

    try:
        return MultipleChoiceQuestion.model_validate_json(candidate_text)
    except ValidationError:
        try:
            parsed_text = json.loads(candidate_text)
        except json.JSONDecodeError as decode_error:
            raise ValueError(
                "The gateway response could not be parsed as a multiple-choice question."
            ) from decode_error

        try:
            return MultipleChoiceQuestion.model_validate(parsed_text)
        except ValidationError as validation_error:
            raise ValueError(
                "The gateway response did not match the multiple-choice question schema."
            ) from validation_error
