import pytest

from hh_job_bot.domain import RelevanceAssessment
from hh_job_bot.repository import DuplicateProfileName


@pytest.mark.asyncio
async def test_seed_is_idempotent(repo) -> None:
    await repo.seed_default_profiles()
    await repo.seed_default_profiles()
    profiles = await repo.list_profiles()
    assert [profile.name for profile in profiles] == [
        "ИИ-разработчик",
        "Вайб-кодер",
        "Low-code",
        "n8n",
        "AI automation",
    ]


@pytest.mark.asyncio
async def test_profile_name_is_unique_case_insensitively(repo) -> None:
    await repo.create_profile("Custom", "n8n developer")
    with pytest.raises(DuplicateProfileName):
        await repo.create_profile("CUSTOM", "automation")


@pytest.mark.asyncio
async def test_catalog_is_newest_first_and_excludes_hidden(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("Catalog", "AI developer")
    older = vacancy_factory(hh_id="1", published_at="2026-06-26T10:00:00+00:00")
    newer = vacancy_factory(hh_id="2", published_at="2026-06-27T10:00:00+00:00")
    await repo.upsert_vacancy(older, profile_id=profile.id)
    await repo.upsert_vacancy(newer, profile_id=profile.id)
    await repo.set_hidden("2", True)

    assert [vacancy.hh_id for vacancy in await repo.catalog(hidden=False)] == ["1"]
    assert [vacancy.hh_id for vacancy in await repo.catalog(hidden=True)] == ["2"]


@pytest.mark.asyncio
async def test_upsert_preserves_hidden_state_and_adds_profile_labels(
    repo,
    vacancy_factory,
) -> None:
    first = await repo.create_profile("AI", "AI developer")
    second = await repo.create_profile("Automation", "AI automation")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=first.id)
    await repo.set_hidden(vacancy.hh_id, True)
    await repo.upsert_vacancy(
        vacancy_factory(title="Updated title"),
        profile_id=second.id,
    )

    saved = await repo.get_vacancy(vacancy.hh_id)
    assert saved is not None
    assert saved.hidden is True
    assert saved.title == "Updated title"
    assert saved.profile_names == ["AI", "Automation"]


@pytest.mark.asyncio
async def test_auto_hidden_and_manual_hidden_are_independent(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    low = vacancy_factory(hh_id="low")
    manual = vacancy_factory(hh_id="manual")
    await repo.upsert_vacancy(low, profile_id=profile.id)
    await repo.upsert_vacancy(manual, profile_id=profile.id)
    await repo.set_hidden("manual", True)

    await repo.save_assessment(
        "low",
        RelevanceAssessment(score=19, matches=[], gaps=[], reason="low"),
        threshold=70,
        auto_hide_threshold=20,
    )

    assert await repo.catalog(hidden=False) == []
    assert {item.hh_id for item in await repo.catalog(hidden=True)} == {
        "low",
        "manual",
    }


@pytest.mark.asyncio
async def test_score_equal_to_auto_hide_threshold_stays_visible(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI")
    await repo.upsert_vacancy(vacancy_factory(hh_id="equal"), profile_id=profile.id)

    await repo.save_assessment(
        "equal",
        RelevanceAssessment(score=20, matches=[], gaps=[], reason="equal"),
        threshold=70,
        auto_hide_threshold=20,
    )

    assert [item.hh_id for item in await repo.catalog(hidden=False)] == ["equal"]


@pytest.mark.asyncio
async def test_manual_restore_overrides_automatic_hide(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    await repo.upsert_vacancy(vacancy_factory(hh_id="low"), profile_id=profile.id)
    await repo.save_assessment(
        "low",
        RelevanceAssessment(score=5, matches=[], gaps=[], reason="low"),
        threshold=70,
        auto_hide_threshold=20,
    )

    await repo.set_hidden("low", False)

    assert [item.hh_id for item in await repo.catalog(hidden=False)] == ["low"]


@pytest.mark.asyncio
async def test_reconcile_returns_auto_hidden_but_not_manual_hidden(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI")
    for hh_id in ("low", "manual"):
        await repo.upsert_vacancy(vacancy_factory(hh_id=hh_id), profile_id=profile.id)
        await repo.save_assessment(
            hh_id,
            RelevanceAssessment(score=10, matches=[], gaps=[], reason="low"),
            threshold=70,
            auto_hide_threshold=20,
        )
    await repo.set_hidden("manual", True)

    await repo.reconcile_auto_hidden(0)

    assert [item.hh_id for item in await repo.catalog(hidden=False)] == ["low"]
    assert [item.hh_id for item in await repo.catalog(hidden=True)] == ["manual"]
