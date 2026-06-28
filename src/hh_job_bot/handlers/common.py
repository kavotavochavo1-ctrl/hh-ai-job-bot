from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from hh_job_bot.repository import Repository

router = Router(name="common")

HELP_TEXT = (
    "Бот ищет вакансии HH, оценивает их и помогает отправлять "
    "сопроводительные.\n\n"
    "/vacancies — свежий каталог вакансий\n"
    "/hidden — скрытые и автоматически отфильтрованные вакансии\n"
    "/profiles — управление поисковыми профилями\n"
    "/threshold — порог релевантности для уведомлений\n"
    "/hide_threshold — порог автоматического скрытия\n"
    "/status — состояние мониторинга и очереди\n"
    "/help — список команд и их описание"
)


@router.message(CommandStart())
async def start_command(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("status"))
async def status_command(message: Message, repository: Repository) -> None:
    last_sync = await repository.last_successful_sync()
    if last_sync is None:
        sync_text = "ещё не выполнялась"
    else:
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=UTC)
        sync_text = last_sync.astimezone(ZoneInfo("Europe/Moscow")).strftime(
            "%d.%m.%Y, %H:%M МСК"
        )
    profiles = await repository.list_profiles(enabled_only=True)
    catalog = await repository.catalog(
        hidden=False,
        since=datetime.now(UTC) - timedelta(days=7),
    )
    pending = await repository.pending_scoring()
    threshold = await repository.get_threshold(default=70)
    auto_hide_threshold = await repository.get_auto_hide_threshold(default=20)
    auto_hide_text = (
        "выключен"
        if auto_hide_threshold == 0
        else f"{auto_hide_threshold}/100"
    )
    await message.answer(
        f"Последняя проверка: {sync_text}\n"
        f"Активных профилей: {len(profiles)}\n"
        f"Вакансий в каталоге: {len(catalog)}\n"
        f"Ожидают оценки: {len(pending)}\n"
        f"Порог уведомлений: {threshold}/100\n"
        f"Порог автоскрытия: {auto_hide_text}"
    )
