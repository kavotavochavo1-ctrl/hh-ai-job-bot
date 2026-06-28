from typing import Protocol

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from hh_job_bot.cards import VacancyAction
from hh_job_bot.cover_letter_validation import (
    build_allowed_tech_terms,
    cover_letter_issues,
)
from hh_job_bot.domain import VacancyData
from hh_job_bot.hh_apply_service import HHApplyError, HHApplyService
from hh_job_bot.prompts import build_cover_messages
from hh_job_bot.repository import Repository

router = Router(name="generation")


class TextCompletionClient(Protocol):
    async def complete_text(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> str: ...


def cover_letter_keyboard(vacancy: VacancyData) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Другой вариант",
                    callback_data=VacancyAction(
                        action="regenerate",
                        hh_id=vacancy.hh_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📨 Отправить на HH",
                    callback_data=VacancyAction(
                        action="apply",
                        hh_id=vacancy.hh_id,
                    ).pack(),
                ),
            ],
            [InlineKeyboardButton(text="🔗 Открыть на HH", url=vacancy.url)],
        ]
    )


async def create_cover_letter(
    repository: Repository,
    client: TextCompletionClient,
    *,
    candidate_profile: str,
    vacancy_id: str,
    model: str,
) -> str:
    vacancy = await repository.get_vacancy(vacancy_id)
    if vacancy is None:
        raise KeyError(vacancy_id)
    vacancy_text = _vacancy_text(vacancy)
    allowed_latin_terms = build_allowed_tech_terms(
        candidate_profile,
        vacancy_text,
    )
    correction: str | None = None
    for _ in range(3):
        text = (
            await client.complete_text(
                model,
                build_cover_messages(
                    candidate_profile,
                    vacancy_text,
                    correction=correction,
                ),
            )
        ).strip()
        issues = cover_letter_issues(
            text,
            allowed_latin_terms=allowed_latin_terms,
        )
        if not issues:
            await repository.save_cover_letter(vacancy_id, text)
            return text
        correction = (
            "Предыдущий текст не прошёл проверку: "
            + "; ".join(issues)
            + ". Напиши полностью новый вариант, устранив все перечисленные проблемы."
        )
    raise ValueError(
        "Модель трижды не смогла создать корректный русский текст длиной "
        "500–800 знаков без заглушек, посторонних языков и необычных символов."
    )


def _vacancy_text(vacancy: VacancyData) -> str:
    return "\n".join(
        (
            f"Название: {vacancy.title}",
            f"Компания: {vacancy.company}",
            f"Опыт: {vacancy.experience_name or 'не указан'}",
            f"Описание: {vacancy.description}",
        )
    )


@router.callback_query(VacancyAction.filter(F.action.in_({"cover", "regenerate"})))
async def cover_callback(
    callback: CallbackQuery,
    callback_data: VacancyAction,
    repository: Repository,
    openrouter_client: TextCompletionClient,
    candidate_profile: str,
    cover_model: str,
) -> None:
    await callback.answer("Готовлю сопроводительное…")
    if callback.message is None:
        return
    try:
        text = await create_cover_letter(
            repository,
            openrouter_client,
            candidate_profile=candidate_profile,
            vacancy_id=callback_data.hh_id,
            model=cover_model,
        )
        vacancy = await repository.get_vacancy(callback_data.hh_id)
        if vacancy is None:
            raise KeyError(callback_data.hh_id)
    except (KeyError, ValueError, RuntimeError) as error:
        await callback.message.answer(f"Не удалось создать текст: {error}")
        return
    await callback.message.answer(text, reply_markup=cover_letter_keyboard(vacancy))


@router.callback_query(VacancyAction.filter(F.action == "apply"))
async def apply_callback(
    callback: CallbackQuery,
    callback_data: VacancyAction,
    repository: Repository,
    hh_apply_service: HHApplyService,
) -> None:
    await callback.answer("Открываю форму отклика на HH…")
    if callback.message is None:
        return
    vacancy = await repository.get_vacancy(callback_data.hh_id)
    if vacancy is None:
        await callback.message.answer("Вакансия не найдена.")
        return
    try:
        result = await hh_apply_service.apply(callback_data.hh_id)
    except HHApplyError as error:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Завершить вручную", url=vacancy.url)]
            ]
        )
        await callback.message.answer(
            f"Не удалось отправить отклик: {error}",
            reply_markup=keyboard,
        )
        return
    if result == "dry_run_ready":
        await callback.message.answer(
            "Форма HH заполнена и проверена. Финальная отправка отключена "
            "тестовым режимом."
        )
    else:
        await callback.message.answer("Отклик отправлен на HH.")
