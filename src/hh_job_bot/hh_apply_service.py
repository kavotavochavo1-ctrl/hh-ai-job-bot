from typing import Protocol

from hh_job_bot.cover_letter_validation import (
    build_allowed_tech_terms,
    cover_letter_issues,
)
from hh_job_bot.repository import Repository


class HHApplyError(RuntimeError):
    pass


class ApplyBrowser(Protocol):
    async def apply(
        self,
        vacancy_url: str,
        letter: str,
        *,
        dry_run: bool,
    ) -> str: ...


class HHApplyService:
    def __init__(
        self,
        repository: Repository,
        browser: ApplyBrowser,
        *,
        dry_run: bool,
        candidate_profile: str,
    ) -> None:
        self.repository = repository
        self.browser = browser
        self.dry_run = dry_run
        self.candidate_profile = candidate_profile

    async def apply(self, vacancy_id: str) -> str:
        vacancy = await self.repository.get_vacancy(vacancy_id)
        letter = await self.repository.latest_cover_letter(vacancy_id)
        if vacancy is None or letter is None:
            raise HHApplyError("Сначала создайте корректное сопроводительное письмо.")
        allowed_latin_terms = build_allowed_tech_terms(
            self.candidate_profile,
            vacancy.description,
        )
        if cover_letter_issues(
            letter.text,
            allowed_latin_terms=allowed_latin_terms,
        ):
            raise HHApplyError("Сохранённое письмо не прошло проверку.")
        try:
            await self.repository.begin_application(vacancy_id, letter.id)
        except (KeyError, ValueError) as error:
            raise HHApplyError(str(error)) from error
        try:
            result = await self.browser.apply(
                vacancy.url,
                letter.text,
                dry_run=self.dry_run,
            )
            if result not in {"dry_run_ready", "submitted"}:
                raise HHApplyError("HH вернул неизвестный результат отклика.")
            await self.repository.finish_application(vacancy_id, status=result)
            return result
        except Exception as error:
            await self.repository.finish_application(
                vacancy_id,
                status="failed",
                error=str(error),
            )
            if isinstance(error, HHApplyError):
                raise
            raise HHApplyError(
                "HH не принял отклик; завершите его вручную."
            ) from error
