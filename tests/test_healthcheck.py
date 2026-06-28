from datetime import UTC, datetime

import pytest

from hh_job_bot.healthcheck import check_health


@pytest.mark.asyncio
async def test_healthcheck_fails_for_stale_heartbeat(repo) -> None:
    await repo.set_setting("heartbeat_at", "2026-06-27T10:00:00+00:00")
    healthy = await check_health(
        repo,
        now=datetime(2026, 6, 27, 11, tzinfo=UTC),
    )
    assert healthy is False


@pytest.mark.asyncio
async def test_healthcheck_accepts_recent_heartbeat(repo) -> None:
    await repo.set_setting("heartbeat_at", "2026-06-27T10:50:00+00:00")
    healthy = await check_health(
        repo,
        now=datetime(2026, 6, 27, 11, tzinfo=UTC),
    )
    assert healthy is True
