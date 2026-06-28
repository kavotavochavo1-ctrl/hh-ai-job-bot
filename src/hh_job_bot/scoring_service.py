import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from hh_job_bot.domain import RelevanceAssessment, VacancyData
from hh_job_bot.prompts import build_scoring_messages
from hh_job_bot.repository import Repository


class JSONCompletionClient(Protocol):
    async def complete_json(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> dict: ...


@dataclass(frozen=True, slots=True)
class ScoringReport:
    scored: int
    deferred: int


class ScoringService:
    RETRY_MINUTES = (1, 5, 15, 60, 360)

    def __init__(
        self,
        repository: Repository,
        client: JSONCompletionClient,
        candidate_profile: str,
        *,
        model: str,
        concurrency: int,
        threshold: int,
        auto_hide_threshold: int = 20,
    ) -> None:
        self.repository = repository
        self.client = client
        self.candidate_profile = candidate_profile
        self.model = model
        self.threshold = threshold
        self.auto_hide_threshold = auto_hide_threshold
        self._semaphore = asyncio.Semaphore(concurrency)

    async def process(self) -> ScoringReport:
        vacancies = await self.repository.pending_scoring()
        results = await asyncio.gather(*(self._score_one(vacancy) for vacancy in vacancies))
        return ScoringReport(
            scored=sum(result for result in results),
            deferred=len(results) - sum(result for result in results),
        )

    async def _score_one(self, vacancy: VacancyData) -> int:
        async with self._semaphore:
            try:
                raw = await self.client.complete_json(
                    self.model,
                    build_scoring_messages(
                        self.candidate_profile,
                        self._vacancy_text(vacancy),
                    ),
                )
                assessment = RelevanceAssessment.model_validate(raw)
                await self.repository.save_assessment(
                    vacancy.hh_id,
                    assessment,
                    threshold=self.threshold,
                    auto_hide_threshold=self.auto_hide_threshold,
                )
                return 1
            except Exception:
                index = min(vacancy.scoring_attempts, len(self.RETRY_MINUTES) - 1)
                await self.repository.defer_scoring(
                    vacancy.hh_id,
                    delay=timedelta(minutes=self.RETRY_MINUTES[index]),
                )
                return 0

    @staticmethod
    def _vacancy_text(vacancy: VacancyData) -> str:
        return "\n".join(
            (
                f"Название: {vacancy.title}",
                f"Компания: {vacancy.company}",
                f"Опыт: {vacancy.experience_name or 'не указан'}",
                f"Формат: {vacancy.work_format_text or 'не указан'}",
                f"Описание: {vacancy.description}",
            )
        )
