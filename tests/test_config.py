from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from hh_job_bot.config import Settings


def valid_values() -> dict[str, object]:
    return {
        "telegram_bot_token": "telegram-secret",
        "telegram_user_id": 12345,
        "openrouter_api_key": "openrouter-secret",
    }


def test_settings_have_approved_defaults() -> None:
    settings = Settings(**valid_values())
    assert settings.poll_interval_minutes == 10
    assert settings.initial_sync_days == 7
    assert settings.notification_threshold == 70
    assert settings.openrouter_model == "deepseek/deepseek-v4-flash"
    assert settings.openrouter_scoring_model == "deepseek/deepseek-v4-flash"
    assert settings.database_url == "sqlite+aiosqlite:////data/bot.db"
    assert "Mozilla/5.0" in settings.hh_web_user_agent
    assert isinstance(settings.telegram_bot_token, SecretStr)
    assert settings.hh_storage_state_path == Path("/data/hh_storage_state.json")
    assert settings.hh_apply_dry_run is True
    assert settings.hh_apply_timeout_seconds == 90


def test_threshold_outside_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(**valid_values(), notification_threshold=101)
