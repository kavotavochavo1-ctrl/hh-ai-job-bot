from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Threshold = Annotated[int, Field(ge=0, le=100)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: SecretStr
    telegram_user_id: int
    openrouter_api_key: SecretStr
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_scoring_model: str = "deepseek/deepseek-v4-flash"
    hh_web_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    database_url: str = "sqlite+aiosqlite:////data/bot.db"
    candidate_profile_path: Path = Path("candidate_profile.md")
    poll_interval_minutes: int = Field(default=10, ge=1)
    initial_sync_days: int = Field(default=7, ge=1, le=30)
    notification_threshold: Threshold = 70
    timezone: str = "Europe/Moscow"
    scoring_concurrency: int = Field(default=2, ge=1, le=10)
    hh_storage_state_path: Path = Path("/data/hh_storage_state.json")
    hh_apply_dry_run: bool = True
    hh_apply_timeout_seconds: int = Field(default=90, ge=30, le=300)
