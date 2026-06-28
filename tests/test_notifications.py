from datetime import UTC, datetime, timedelta

import pytest

from hh_job_bot.domain import RelevanceAssessment
from hh_job_bot.notification_service import NotificationService
from tests.fakes import FakeBot


@pytest.mark.asyncio
async def test_dispatch_sends_only_thresholded_vacancies_and_caps_ten(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    scores = [90] * 12 + [69]
    for index, score in enumerate(scores):
        vacancy = vacancy_factory(
            hh_id=str(index),
            published_at=datetime(2026, 6, 27, tzinfo=UTC) + timedelta(minutes=index),
        )
        await repo.upsert_vacancy(vacancy, profile_id=profile.id)
        await repo.save_assessment(
            vacancy.hh_id,
            RelevanceAssessment(
                score=score,
                matches=["Python"],
                gaps=[],
                reason="Тестовая оценка.",
            ),
            threshold=70,
        )
    fake_bot = FakeBot()

    result = await NotificationService(repo, fake_bot, user_id=1).dispatch(threshold=70)

    assert result.cards_sent == 10
    assert result.remaining == 2
    assert len(fake_bot.messages) == 11
    low_score = await repo.get_vacancy("12")
    assert low_score is not None
    assert low_score.notification_sent_at is None
