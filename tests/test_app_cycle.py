from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from hh_job_bot.app import run_cycle, startup_sync
from hh_job_bot.handlers.common import (
    HELP_TEXT,
    help_command,
    start_command,
    status_command,
)
from tests.fakes import FakeMessage


class CallRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []


class SearchSpy:
    def __init__(
        self,
        recorder: CallRecorder,
        *,
        initial_errors: dict[str, str] | None = None,
    ) -> None:
        self.recorder = recorder
        self.initial_errors = initial_errors or {}

    async def sync(self, **kwargs):
        self.recorder.calls.append("sync")
        return SimpleNamespace(profile_errors={})

    async def initial_sync(self, *, days: int):
        self.recorder.calls.append(f"initial:{days}")
        return SimpleNamespace(profile_errors=self.initial_errors)


class ScoreSpy:
    def __init__(self, recorder: CallRecorder) -> None:
        self.recorder = recorder
        self.threshold = 70
        self.auto_hide_threshold = -1

    async def process(self):
        self.recorder.calls.append("score")


class NotifySpy:
    def __init__(self, recorder: CallRecorder) -> None:
        self.recorder = recorder

    async def dispatch(self, **kwargs):
        self.recorder.calls.append("notify")


class RepoSpy:
    def __init__(self) -> None:
        self.settings: dict[str, str] = {}

    async def last_successful_sync(self):
        return None

    async def get_threshold(self, *, default: int) -> int:
        return default

    async def get_auto_hide_threshold(self, *, default: int) -> int:
        return 20

    async def set_setting(self, key: str, value: str) -> None:
        self.settings[key] = value


def services(
    recorder: CallRecorder,
    *,
    initial_errors: dict[str, str] | None = None,
):
    return SimpleNamespace(
        search=SearchSpy(recorder, initial_errors=initial_errors),
        scoring=ScoreSpy(recorder),
        notifications=NotifySpy(recorder),
        repository=RepoSpy(),
    )


@pytest.mark.asyncio
async def test_cycle_orders_sync_score_then_notifications() -> None:
    recorder = CallRecorder()
    app_services = services(recorder)
    await run_cycle(app_services)
    assert recorder.calls == ["sync", "score", "notify"]
    assert app_services.scoring.auto_hide_threshold == 20


@pytest.mark.asyncio
async def test_first_start_runs_baseline_without_old_notifications() -> None:
    recorder = CallRecorder()
    app_services = services(recorder)
    await startup_sync(app_services, initial_days=7)
    assert recorder.calls == ["initial:7", "score"]
    assert "notify" not in recorder.calls
    assert "last_successful_sync" in app_services.repository.settings
    assert app_services.scoring.auto_hide_threshold == 20


@pytest.mark.asyncio
async def test_first_start_checkpoints_partial_sync_to_avoid_restart_loop() -> None:
    recorder = CallRecorder()
    app_services = services(
        recorder,
        initial_errors={"AI automation": "HH запросил CAPTCHA"},
    )

    await startup_sync(app_services, initial_days=7)

    assert "last_successful_sync" in app_services.repository.settings


@pytest.mark.asyncio
async def test_status_counts_vacancies_from_last_seven_days(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    vacancy = vacancy_factory(published_at=datetime.now(UTC) - timedelta(minutes=1))
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    message = FakeMessage()

    await status_command(message, repo)

    assert "Вакансий в каталоге: 1" in message.text


@pytest.mark.asyncio
async def test_start_lists_auto_hide_threshold_command() -> None:
    message = FakeMessage()

    await start_command(message)

    assert "/hide_threshold" in message.text


@pytest.mark.asyncio
async def test_help_lists_every_command() -> None:
    message = FakeMessage()

    await help_command(message)

    for command in (
        "/help",
        "/vacancies",
        "/hidden",
        "/profiles",
        "/threshold",
        "/hide_threshold",
        "/status",
    ):
        assert command in message.text


@pytest.mark.asyncio
async def test_start_and_help_share_same_reference() -> None:
    start_message = FakeMessage()
    help_message = FakeMessage()

    await start_command(start_message)
    await help_command(help_message)

    assert start_message.text == HELP_TEXT
    assert help_message.text == HELP_TEXT


@pytest.mark.asyncio
async def test_status_shows_disabled_auto_hide_threshold(repo) -> None:
    await repo.set_setting("auto_hide_threshold", "0")
    message = FakeMessage()

    await status_command(message, repo)

    assert "Порог автоскрытия: выключен" in message.text
