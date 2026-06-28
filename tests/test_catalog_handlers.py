from datetime import UTC, datetime, timedelta

import pytest

from hh_job_bot.handlers.catalog import navigate_catalog, show_catalog
from tests.fakes import FakeMessage

NOW = datetime(2026, 6, 27, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_catalog_starts_with_newest_and_edits_same_message(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    for index in range(3):
        await repo.upsert_vacancy(
            vacancy_factory(
                hh_id=str(index),
                published_at=NOW - timedelta(hours=index),
            ),
            profile_id=profile.id,
        )
    message = FakeMessage()

    await show_catalog(message, repo, index=0, hidden=False, now=NOW)

    assert message.latest_counter == "1 / 3"
    assert message.latest_vacancy_id == "0"
    await navigate_catalog(message, repo, index=1, hidden=False, now=NOW)
    assert message.edit_count == 1
    assert message.latest_counter == "2 / 3"
    assert message.latest_vacancy_id == "1"


@pytest.mark.asyncio
async def test_empty_catalog_has_no_navigation(repo) -> None:
    message = FakeMessage()
    await show_catalog(message, repo, index=0, hidden=False, now=NOW)
    assert message.text == "Подходящих вакансий пока нет."
