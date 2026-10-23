
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CodeGuard AI"

    # Allow the frontend running on Vite port 5178.
    frontend_origin: str = "http://127.0.0.1:5178"

    github_token: str = ""

    # none | openai | anthropic
    ai_provider: str = "none"

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    max_files: int = 80
    max_file_bytes: int = 250_000
    max_total_bytes: int = 3_000_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
