import asyncio
from datetime import UTC, datetime, timedelta

from hh_job_bot.config import Settings
from hh_job_bot.db import Database
from hh_job_bot.repository import Repository


async def check_health(
    repository: Repository,
    *,
    now: datetime | None = None,
) -> bool:
    if not await repository.database.ping():
        return False
    heartbeat = await repository.get_setting("heartbeat_at")
    if heartbeat is None:
        return False
    recorded = datetime.fromisoformat(heartbeat)
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - recorded <= timedelta(minutes=30)


async def _main() -> int:
    settings = Settings()
    database = Database(settings.database_url)
    try:
        healthy = await check_health(Repository(database))
        return 0 if healthy else 1
    finally:
        await database.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
