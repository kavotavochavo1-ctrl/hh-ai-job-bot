import pytest

from hh_job_bot.hh_apply_service import HHApplyError, HHApplyService


class FakeApplyBrowser:
    def __init__(
        self,
        result: str = "submitted",
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, bool]] = []

    async def apply(
        self,
        vacancy_url: str,
        letter: str,
        *,
        dry_run: bool,
    ) -> str:
        self.calls.append((vacancy_url, letter, dry_run))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_apply_service_uses_latest_valid_letter_in_dry_run(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    await repo.save_cover_letter(vacancy.hh_id, "А" * 550)
    browser = FakeApplyBrowser(result="dry_run_ready")
    service = HHApplyService(
        repo,
        browser,
        dry_run=True,
        candidate_profile="Python",
    )

    result = await service.apply(vacancy.hh_id)

    assert result == "dry_run_ready"
    assert browser.calls == [(vacancy.url, "А" * 550, True)]
    attempt = await repo.get_application_attempt(vacancy.hh_id)
    assert attempt is not None
    assert attempt.status == "dry_run_ready"


@pytest.mark.asyncio
async def test_apply_service_records_browser_failure(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    await repo.save_cover_letter(vacancy.hh_id, "А" * 550)
    browser = FakeApplyBrowser(error=RuntimeError("captcha"))
    service = HHApplyService(
        repo,
        browser,
        dry_run=True,
        candidate_profile="Python",
    )

    with pytest.raises(HHApplyError, match="вручную"):
        await service.apply(vacancy.hh_id)

    attempt = await repo.get_application_attempt(vacancy.hh_id)
    assert attempt is not None
    assert attempt.status == "failed"
    assert attempt.error_text == "captcha"


@pytest.mark.asyncio
async def test_apply_service_rejects_invalid_saved_letter(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    await repo.save_cover_letter(vacancy.hh_id, "А" * 520 + " [Имя]")
    browser = FakeApplyBrowser()
    service = HHApplyService(
        repo,
        browser,
        dry_run=True,
        candidate_profile="Python",
    )

    with pytest.raises(HHApplyError, match="не прошло проверку"):
        await service.apply(vacancy.hh_id)

    assert browser.calls == []
