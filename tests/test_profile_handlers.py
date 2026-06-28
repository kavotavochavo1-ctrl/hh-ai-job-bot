import pytest

from hh_job_bot.domain import RelevanceAssessment
from hh_job_bot.handlers.profiles import (
    ProfileInputError,
    apply_auto_hide_threshold,
    apply_threshold,
    save_profile,
    validate_profile_name,
    validate_profile_query,
)


def test_profile_input_validation() -> None:
    assert validate_profile_name("  AI вакансии  ") == "AI вакансии"
    assert validate_profile_query("  AI developer  ") == "AI developer"
    with pytest.raises(ProfileInputError):
        validate_profile_name("")
    with pytest.raises(ProfileInputError):
        validate_profile_query("x" * 501)


@pytest.mark.asyncio
async def test_add_and_edit_profile(repo) -> None:
    created = await save_profile(
        repo,
        profile_id=None,
        name="Robotic Process Automation",
        query="RPA developer",
    )
    assert created.query == "RPA developer"

    updated = await save_profile(
        repo,
        profile_id=created.id,
        name="RPA",
        query="RPA OR robotic process automation",
    )
    assert updated.name == "RPA"


@pytest.mark.asyncio
async def test_threshold_accepts_only_zero_to_one_hundred(repo) -> None:
    with pytest.raises(ProfileInputError):
        await apply_threshold(repo, "101")
    with pytest.raises(ProfileInputError):
        await apply_threshold(repo, "not-a-number")

    assert await apply_threshold(repo, "65") == 65
    assert await repo.get_threshold(default=70) == 65


@pytest.mark.asyncio
async def test_auto_hide_threshold_reconciles_existing_scores(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI")
    await repo.upsert_vacancy(vacancy_factory(), profile_id=profile.id)
    await repo.save_assessment(
        "42",
        RelevanceAssessment(score=15, matches=[], gaps=[], reason="low"),
        threshold=70,
    )

    assert await apply_auto_hide_threshold(repo, "20") == 20
    assert [item.hh_id for item in await repo.catalog(hidden=True)] == ["42"]
    assert await apply_auto_hide_threshold(repo, "0") == 0
    assert [item.hh_id for item in await repo.catalog(hidden=False)] == ["42"]
