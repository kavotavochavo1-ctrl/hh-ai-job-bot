from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest_asyncio

from hh_job_bot.db import Database
from hh_job_bot.domain import VacancyData
from hh_job_bot.repository import Repository


@pytest_asyncio.fixture
async def repo(tmp_path) -> AsyncIterator[Repository]:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await database.create_schema()
    yield Repository(database)
    await database.dispose()


@pytest_asyncio.fixture
def vacancy_factory() -> Callable[..., VacancyData]:
    def factory(**overrides) -> VacancyData:
        published_at = overrides.pop("published_at", datetime(2026, 6, 27, 10, tzinfo=UTC))
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at)
        values = {
            "hh_id": "42",
            "title": "AI Automation Developer",
            "company": "Example",
            "url": "https://hh.ru/vacancy/42",
            "published_at": published_at,
            "description": "Build reliable automations",
            "description_hash": "hash-42",
        }
        values.update(overrides)
        return VacancyData(**values)

    return factory
