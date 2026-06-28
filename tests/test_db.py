from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from hh_job_bot.db import Database, SearchProfileRow, VacancyRow
from hh_job_bot.domain import RelevanceAssessment


@pytest.mark.asyncio
async def test_schema_persists_profiles_and_vacancies(tmp_path) -> None:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_schema()
    now = datetime(2026, 6, 27, tzinfo=UTC)

    async with db.session() as session:
        session.add(
            SearchProfileRow(
                name="n8n",
                name_key="n8n",
                query="n8n developer",
                enabled=True,
            )
        )
        session.add(
            VacancyRow(
                hh_id="123",
                title="AI Automation Developer",
                company="Example",
                url="https://hh.ru/vacancy/123",
                published_at=now,
                description="Build workflows",
                description_hash="hash",
                details_refreshed_at=now,
                discovered_at=now,
            )
        )
        await session.commit()

    async with db.session() as session:
        assert (await session.scalar(select(SearchProfileRow))).name == "n8n"
        assert (await session.scalar(select(VacancyRow))).hh_id == "123"

    await db.dispose()


def test_relevance_assessment_validates_score_and_content() -> None:
    assessment = RelevanceAssessment(
        score=76,
        matches=["Playwright"],
        gaps=["SQL"],
        reason="Опыт соответствует основным задачам.",
    )
    assert assessment.score == 76

    with pytest.raises(ValidationError):
        RelevanceAssessment(score=101, matches=[], gaps=[], reason="")
