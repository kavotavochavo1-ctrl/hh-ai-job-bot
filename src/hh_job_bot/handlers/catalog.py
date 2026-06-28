from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from hh_job_bot.cards import CatalogPage, VacancyAction, render_vacancy, vacancy_keyboard
from hh_job_bot.repository import Repository

router = Router(name="catalog")


async def show_catalog(
    message: Message | Any,
    repository: Repository,
    *,
    index: int,
    hidden: bool,
    now: datetime | None = None,
    edit: bool = False,
) -> None:
    current = now or datetime.now(UTC)
    vacancies = await repository.catalog(
        hidden=hidden,
        since=current - timedelta(days=7),
    )
    if not vacancies:
        text = "Скрытых вакансий нет." if hidden else "Подходящих вакансий пока нет."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    safe_index = min(max(index, 0), len(vacancies) - 1)
    vacancy = vacancies[safe_index]
    await repository.mark_viewed(vacancy.hh_id)
    text = render_vacancy(vacancy)
    markup = vacancy_keyboard(
        vacancy,
        index=safe_index,
        total=len(vacancies),
        hidden_catalog=hidden,
    )
    if hasattr(message, "latest_vacancy_id"):
        message.latest_vacancy_id = vacancy.hh_id
        message.latest_counter = f"{safe_index + 1} / {len(vacancies)}"
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


async def navigate_catalog(
    message: Message | Any,
    repository: Repository,
    *,
    index: int,
    hidden: bool,
    now: datetime | None = None,
) -> None:
    await show_catalog(
        message,
        repository,
        index=index,
        hidden=hidden,
        now=now,
        edit=True,
    )


@router.message(Command("vacancies"))
async def vacancies_command(message: Message, repository: Repository) -> None:
    await show_catalog(message, repository, index=0, hidden=False)


@router.message(Command("hidden"))
async def hidden_command(message: Message, repository: Repository) -> None:
    await show_catalog(message, repository, index=0, hidden=True)


@router.callback_query(F.data == "catalog:open")
async def open_catalog(callback: CallbackQuery, repository: Repository) -> None:
    if callback.message is not None:
        await show_catalog(callback.message, repository, index=0, hidden=False)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(CatalogPage.filter())
async def page_callback(
    callback: CallbackQuery,
    callback_data: CatalogPage,
    repository: Repository,
) -> None:
    if callback.message is not None:
        await navigate_catalog(
            callback.message,
            repository,
            index=callback_data.index,
            hidden=callback_data.hidden,
        )
    await callback.answer()


@router.callback_query(VacancyAction.filter(F.action.in_({"hide", "restore"})))
async def visibility_callback(
    callback: CallbackQuery,
    callback_data: VacancyAction,
    repository: Repository,
) -> None:
    hidden = callback_data.action == "hide"
    await repository.set_hidden(callback_data.hh_id, hidden)
    if callback.message is not None:
        await navigate_catalog(
            callback.message,
            repository,
            index=0,
            hidden=not hidden,
        )
    await callback.answer("Вакансия скрыта" if hidden else "Вакансия возвращена")


@router.callback_query(VacancyAction.filter(F.action == "rescore"))
async def rescore_callback(
    callback: CallbackQuery,
    callback_data: VacancyAction,
    repository: Repository,
) -> None:
    await repository.request_rescore(callback_data.hh_id)
    await callback.answer("Вакансия поставлена на переоценку")
