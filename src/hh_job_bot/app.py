import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from hh_job_bot.access import PrivateUserMiddleware
from hh_job_bot.config import Settings
from hh_job_bot.db import Database
from hh_job_bot.handlers import catalog, common, generation, profiles
from hh_job_bot.hh_apply_service import HHApplyService
from hh_job_bot.hh_playwright import PlaywrightHHBrowser
from hh_job_bot.hh_web_client import HHWebClient
from hh_job_bot.notification_service import NotificationService
from hh_job_bot.openrouter_client import OpenRouterClient
from hh_job_bot.repository import Repository
from hh_job_bot.scoring_service import ScoringService
from hh_job_bot.search_service import SearchService

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AppServices:
    repository: Repository
    search: SearchService
    scoring: ScoringService
    notifications: NotificationService


async def heartbeat(repository: Repository) -> None:
    await repository.set_setting("heartbeat_at", datetime.now(UTC).isoformat())


async def run_cycle(services: AppServices | Any) -> None:
    threshold = await services.repository.get_threshold(default=70)
    services.scoring.threshold = threshold
    services.scoring.auto_hide_threshold = (
        await services.repository.get_auto_hide_threshold(default=20)
    )
    last_sync = await services.repository.last_successful_sync()
    since = last_sync or datetime.now(UTC) - timedelta(minutes=15)
    report = await services.search.sync(since=since)
    await services.scoring.process()
    await services.notifications.dispatch(threshold=threshold)
    if not report.profile_errors:
        await services.repository.set_setting(
            "last_successful_sync",
            datetime.now(UTC).isoformat(),
        )
    await heartbeat(services.repository)


async def startup_sync(services: AppServices | Any, *, initial_days: int) -> None:
    threshold = await services.repository.get_threshold(default=70)
    services.scoring.threshold = threshold
    services.scoring.auto_hide_threshold = (
        await services.repository.get_auto_hide_threshold(default=20)
    )
    report = await services.search.initial_sync(days=initial_days)
    await services.scoring.process()
    if report.profile_errors:
        LOGGER.warning("Initial HH sync completed partially: %s", report.profile_errors)
    await services.repository.set_setting(
        "last_successful_sync",
        datetime.now(UTC).isoformat(),
    )
    await heartbeat(services.repository)


async def run() -> None:
    settings = Settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database = Database(settings.database_url)
    await database.create_schema()
    repository = Repository(database)
    await repository.seed_default_profiles()

    candidate_profile = Path(settings.candidate_profile_path).read_text(encoding="utf-8")
    hh_client = HHWebClient(user_agent=settings.hh_web_user_agent)
    openrouter_client = OpenRouterClient(settings.openrouter_api_key)
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.message.outer_middleware(
        PrivateUserMiddleware(allowed_user_id=settings.telegram_user_id)
    )
    dispatcher.callback_query.outer_middleware(
        PrivateUserMiddleware(allowed_user_id=settings.telegram_user_id)
    )
    dispatcher.include_routers(
        common.router,
        catalog.router,
        profiles.router,
        generation.router,
    )

    search = SearchService(repository, hh_client)
    scoring = ScoringService(
        repository,
        openrouter_client,
        candidate_profile,
        model=settings.openrouter_scoring_model,
        concurrency=settings.scoring_concurrency,
        threshold=await repository.get_threshold(default=settings.notification_threshold),
        auto_hide_threshold=await repository.get_auto_hide_threshold(default=20),
    )
    notifications = NotificationService(
        repository,
        bot,
        user_id=settings.telegram_user_id,
    )
    services = AppServices(repository, search, scoring, notifications)
    hh_apply_service = HHApplyService(
        repository,
        PlaywrightHHBrowser(
            settings.hh_storage_state_path,
            timeout_seconds=settings.hh_apply_timeout_seconds,
        ),
        dry_run=settings.hh_apply_dry_run,
        candidate_profile=candidate_profile,
    )

    dispatcher["repository"] = repository
    dispatcher["search_service"] = search
    dispatcher["openrouter_client"] = openrouter_client
    dispatcher["candidate_profile"] = candidate_profile
    dispatcher["cover_model"] = settings.openrouter_model
    dispatcher["hh_apply_service"] = hh_apply_service

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        run_cycle,
        "interval",
        minutes=settings.poll_interval_minutes,
        args=[services],
        max_instances=1,
        coalesce=True,
        id="vacancy-sync",
    )
    scheduler.add_job(
        heartbeat,
        "interval",
        minutes=1,
        args=[repository],
        max_instances=1,
        coalesce=True,
        id="heartbeat",
    )

    try:
        if await repository.last_successful_sync() is None:
            await startup_sync(services, initial_days=settings.initial_sync_days)
        else:
            await run_cycle(services)
        scheduler.start()
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await hh_client.close()
        await openrouter_client.close()
        await bot.session.close()
        await database.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
