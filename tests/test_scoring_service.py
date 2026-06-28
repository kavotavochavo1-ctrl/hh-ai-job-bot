import pytest

from hh_job_bot.scoring_service import ScoringService
from tests.fakes import FakeOpenRouterClient


@pytest.mark.asyncio
async def test_scoring_saves_valid_assessment(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    await repo.upsert_vacancy(vacancy_factory(hh_id="42"), profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.result = {
        "score": 76,
        "matches": ["Playwright", "Telegram Bot API"],
        "gaps": ["SQL"],
        "reason": "Практический опыт близок к основным задачам.",
    }

    await ScoringService(
        repo,
        fake_openrouter,
        "profile",
        model="deepseek/deepseek-v4-flash",
        concurrency=2,
        threshold=70,
    ).process()

    saved = await repo.get_vacancy("42")
    assert saved is not None
    assert saved.score == 76
    assert saved.score_gaps == ["SQL"]
    assert saved.notification_eligible is True


@pytest.mark.asyncio
async def test_invalid_assessment_is_deferred(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    await repo.upsert_vacancy(vacancy_factory(hh_id="42"), profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.result = {"score": 120, "matches": [], "gaps": [], "reason": ""}

    await ScoringService(
        repo,
        fake_openrouter,
        "profile",
        model="deepseek/deepseek-v4-flash",
        concurrency=2,
        threshold=70,
    ).process()

    saved = await repo.get_vacancy("42")
    assert saved is not None
    assert saved.score is None
    assert saved.scoring_attempts == 1
    assert saved.scoring_next_attempt_at is not None


@pytest.mark.asyncio
async def test_scoring_auto_hides_below_separate_threshold(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    await repo.upsert_vacancy(vacancy_factory(hh_id="42"), profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.result = {
        "score": 19,
        "matches": [],
        "gaps": ["стек"],
        "reason": "Низкая релевантность.",
    }

    await ScoringService(
        repo,
        fake_openrouter,
        "profile",
        model="deepseek/deepseek-v4-flash",
        concurrency=2,
        threshold=70,
        auto_hide_threshold=20,
    ).process()

    assert [item.hh_id for item in await repo.catalog(hidden=True)] == ["42"]
