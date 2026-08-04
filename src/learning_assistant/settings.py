from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    client_id: str = Field(default="", validation_alias="CLIENT_ID")
    client_secret: str = Field(default="", validation_alias="CLIENT_SECRET")
    base_url: str = Field(default="", validation_alias="BASE_URL")
    response_language: str = Field(default="en-US", validation_alias="RESPONSE_LANGUAGE")

    @model_validator(mode="after")
    def validate_required_values(self) -> "GatewaySettings":
        if not self.client_id.strip():
            raise ValueError("CLIENT_ID is required")
        if not self.client_secret.strip():
            raise ValueError("CLIENT_SECRET is required")
        if not self.base_url.strip():
            raise ValueError("BASE_URL is required")

        return self

    def normalized_base_url(self) -> str:
        value = self.base_url.strip().rstrip("/")
        if value.startswith(("http://", "https://")):
            return value

        return f"https://{value}"
