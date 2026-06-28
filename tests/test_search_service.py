from datetime import UTC, datetime

import pytest

from hh_job_bot.search_service import SearchService
from tests.fakes import FakeHHClient

NOW = datetime(2026, 6, 27, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_sync_runs_only_enabled_profiles_and_deduplicates(repo, vacancy_factory) -> None:
    await repo.create_profile("AI", "AI developer")
    disabled = await repo.create_profile("n8n", "n8n developer")
    await repo.set_profile_enabled(disabled.id, False)
    fake_hh = FakeHHClient()
    fake_hh.results["AI developer"] = [{"id": "42"}]
    fake_hh.details["42"] = vacancy_factory(hh_id="42")

    report = await SearchService(repo, fake_hh).sync(since=NOW)

    assert fake_hh.queries == ["AI developer"]
    assert report.discovered_ids == ["42"]
    assert report.profile_errors == {}


@pytest.mark.asyncio
async def test_same_vacancy_keeps_all_matching_profile_labels(repo, vacancy_factory) -> None:
    await repo.create_profile("AI", "AI developer")
    await repo.create_profile("Automation", "AI automation")
    fake_hh = FakeHHClient()
    fake_hh.default_results = [{"id": "42"}]
    fake_hh.details["42"] = vacancy_factory(hh_id="42")

    await SearchService(repo, fake_hh).sync(since=NOW)

    saved = await repo.get_vacancy("42")
    assert saved is not None
    assert saved.profile_names == ["AI", "Automation"]


@pytest.mark.asyncio
async def test_initial_sync_marks_old_vacancies_as_baseline(repo, vacancy_factory) -> None:
    await repo.create_profile("AI", "AI developer")
    fake_hh = FakeHHClient()
    fake_hh.default_results = [{"id": "42"}]
    fake_hh.details["42"] = vacancy_factory(hh_id="42")

    await SearchService(repo, fake_hh).initial_sync(days=7, now=NOW)

    saved = await repo.get_vacancy("42")
    assert saved is not None
    assert saved.baseline is True
    assert saved.notification_eligible is False


@pytest.mark.asyncio
async def test_sync_treats_late_discovered_older_vacancy_as_baseline(
    repo,
    vacancy_factory,
) -> None:
    await repo.create_profile("AI", "AI developer")
    fake_hh = FakeHHClient()
    fake_hh.default_results = [{"id": "42"}]
    fake_hh.details["42"] = vacancy_factory(
        hh_id="42",
        published_at=datetime(2026, 6, 27, 11, 59, tzinfo=UTC),
    )

    await SearchService(repo, fake_hh).sync(since=NOW)

    saved = await repo.get_vacancy("42")
    assert saved is not None
    assert saved.baseline is True
    assert saved.notification_eligible is False
