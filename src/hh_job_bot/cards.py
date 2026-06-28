from html import escape
from zoneinfo import ZoneInfo

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hh_job_bot.domain import VacancyData


class VacancyAction(CallbackData, prefix="vac"):
    action: str
    hh_id: str


class CatalogPage(CallbackData, prefix="page"):
    index: int
    hidden: bool


def render_vacancy(vacancy: VacancyData, *, timezone: str = "Europe/Moscow") -> str:
    published = vacancy.published_at.astimezone(ZoneInfo(timezone)).strftime("%d.%m.%Y, %H:%M")
    score = (
        f"{vacancy.score}/100"
        if vacancy.score is not None
        else "ожидает оценки"
    )
    matches = ", ".join(vacancy.score_matches or []) or "не выделены"
    gaps = ", ".join(vacancy.score_gaps or []) or "существенных нет"
    profiles = ", ".join(vacancy.profile_names) or "не указан"
    snippet = vacancy.description[:900]
    if len(vacancy.description) > 900:
        snippet += "…"
    lines = [
        f"<b>{escape(vacancy.title)}</b>",
        f"🏢 {escape(vacancy.company)}",
        f"💰 {escape(vacancy.salary_text or 'не указана')}",
        f"📍 {escape(vacancy.area_name or 'любой регион')}",
        f"🏠 {escape(vacancy.work_format_text or 'формат не указан')}",
        f"🧭 Опыт: {escape(vacancy.experience_name or 'не указан')}",
        f"🕒 Опубликовано: {published} МСК",
        f"🎯 Релевантность: {score}",
        f"✅ Подходит: {escape(matches)}",
        f"⚠️ Пробелы: {escape(gaps)}",
        f"🔎 Найдено по: {escape(profiles)}",
        "",
        escape(snippet),
    ]
    return "\n".join(lines)[:4096]


def vacancy_keyboard(
    vacancy: VacancyData,
    *,
    index: int | None = None,
    total: int | None = None,
    hidden_catalog: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if index is not None and total is not None:
        previous_index = max(index - 1, 0)
        next_index = min(index + 1, max(total - 1, 0))
        builder.row(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=CatalogPage(index=previous_index, hidden=hidden_catalog).pack(),
            ),
            InlineKeyboardButton(text=f"{index + 1} / {total}", callback_data="noop"),
            InlineKeyboardButton(
                text="➡️",
                callback_data=CatalogPage(index=next_index, hidden=hidden_catalog).pack(),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="✨ Создать отклик",
            callback_data=VacancyAction(action="cover", hh_id=vacancy.hh_id).pack(),
        ),
        InlineKeyboardButton(
            text="♻️ Переоценить",
            callback_data=VacancyAction(action="rescore", hh_id=vacancy.hh_id).pack(),
        ),
    )
    builder.row(InlineKeyboardButton(text="🔗 Открыть на HH", url=vacancy.url))
    action = "restore" if hidden_catalog or vacancy.hidden else "hide"
    label = "↩️ Вернуть" if action == "restore" else "🙈 Скрыть"
    builder.row(
        InlineKeyboardButton(
            text=label,
            callback_data=VacancyAction(action=action, hh_id=vacancy.hh_id).pack(),
        )
    )
    return builder.as_markup()
