import pytest


@pytest.mark.asyncio
async def test_application_attempt_is_idempotent(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    letter = await repo.save_cover_letter(vacancy.hh_id, "А" * 550)

    attempt = await repo.begin_application(vacancy.hh_id, letter.id)
    assert attempt.status == "pending"

    await repo.finish_application(vacancy.hh_id, status="submitted")
    with pytest.raises(ValueError, match="уже отправлен"):
        await repo.begin_application(vacancy.hh_id, letter.id)


@pytest.mark.asyncio
async def test_failed_attempt_can_be_retried(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    letter = await repo.save_cover_letter(vacancy.hh_id, "А" * 550)

    await repo.begin_application(vacancy.hh_id, letter.id)
    await repo.finish_application(vacancy.hh_id, status="failed", error="captcha")
    retried = await repo.begin_application(vacancy.hh_id, letter.id)

    assert retried.status == "pending"
    assert retried.error_text is None


@pytest.mark.asyncio
async def test_latest_cover_letter_is_returned(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    await repo.save_cover_letter(vacancy.hh_id, "А" * 550)
    latest = await repo.save_cover_letter(vacancy.hh_id, "Б" * 550)

    saved = await repo.latest_cover_letter(vacancy.hh_id)

    assert saved is not None
    assert saved.id == latest.id
