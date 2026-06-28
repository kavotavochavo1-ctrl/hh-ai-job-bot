from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from hh_job_bot.domain import SearchProfileData
from hh_job_bot.repository import DuplicateProfileName, Repository
from hh_job_bot.search_service import SearchService

router = Router(name="profiles")


class ProfileInputError(ValueError):
    pass


class ProfileAction(CallbackData, prefix="profile"):
    action: str
    profile_id: int = 0


class ThresholdValue(CallbackData, prefix="threshold"):
    value: int


class AutoHideThresholdValue(CallbackData, prefix="hide-threshold"):
    value: int


class ProfileForm(StatesGroup):
    name = State()
    query = State()
    confirm = State()
    threshold = State()
    auto_hide_threshold = State()


def validate_profile_name(value: str) -> str:
    clean = value.strip()
    if not 1 <= len(clean) <= 100:
        raise ProfileInputError("Название должно содержать от 1 до 100 символов.")
    return clean


def validate_profile_query(value: str) -> str:
    clean = value.strip()
    if not 1 <= len(clean) <= 500:
        raise ProfileInputError("Поисковая фраза должна содержать от 1 до 500 символов.")
    return clean


async def save_profile(
    repository: Repository,
    *,
    profile_id: int | None,
    name: str,
    query: str,
) -> SearchProfileData:
    clean_name = validate_profile_name(name)
    clean_query = validate_profile_query(query)
    if profile_id is None:
        return await repository.create_profile(clean_name, clean_query)
    return await repository.update_profile(profile_id, name=clean_name, query=clean_query)


def _parse_threshold(value: str | int) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError) as error:
        raise ProfileInputError("Порог должен быть целым числом от 0 до 100.") from error
    if not 0 <= threshold <= 100:
        raise ProfileInputError("Порог должен быть целым числом от 0 до 100.")
    return threshold


async def apply_threshold(repository: Repository, value: str | int) -> int:
    threshold = _parse_threshold(value)
    await repository.set_setting("notification_threshold", str(threshold))
    return threshold


async def apply_auto_hide_threshold(
    repository: Repository,
    value: str | int,
) -> int:
    threshold = _parse_threshold(value)
    await repository.set_setting("auto_hide_threshold", str(threshold))
    await repository.reconcile_auto_hidden(threshold)
    return threshold


def profiles_keyboard(profiles: list[SearchProfileData]):
    builder = InlineKeyboardBuilder()
    for profile in profiles:
        status = "✅" if profile.enabled else "⏸"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {profile.name}",
                callback_data=ProfileAction(action="select", profile_id=profile.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="➕ Добавить",
            callback_data=ProfileAction(action="add").pack(),
        )
    )
    return builder.as_markup()


async def show_profiles(message: Message, repository: Repository, *, edit: bool = False) -> None:
    profiles = await repository.list_profiles()
    lines = ["<b>Поисковые профили</b>"]
    for profile in profiles:
        status = "включён" if profile.enabled else "выключен"
        lines.append(f"• {profile.name} — {status}\n  <code>{profile.query}</code>")
    text = "\n".join(lines)
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=profiles_keyboard(profiles))
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=profiles_keyboard(profiles))


@router.message(Command("profiles"))
async def profiles_command(message: Message, repository: Repository) -> None:
    await show_profiles(message, repository)


@router.callback_query(ProfileAction.filter(F.action == "select"))
async def select_profile(
    callback: CallbackQuery,
    callback_data: ProfileAction,
    repository: Repository,
) -> None:
    profile = await repository.get_profile(callback_data.profile_id)
    if profile is None or callback.message is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    toggle_label = "⏸ Выключить" if profile.enabled else "▶️ Включить"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Изменить",
            callback_data=ProfileAction(action="edit", profile_id=profile.id).pack(),
        ),
        InlineKeyboardButton(
            text=toggle_label,
            callback_data=ProfileAction(action="toggle", profile_id=profile.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔎 Проверить сейчас",
            callback_data=ProfileAction(action="check", profile_id=profile.id).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=ProfileAction(action="delete", profile_id=profile.id).pack(),
        ),
    )
    await callback.message.edit_text(
        f"<b>{profile.name}</b>\n<code>{profile.query}</code>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(ProfileAction.filter(F.action.in_({"add", "edit"})))
async def start_profile_form(
    callback: CallbackQuery,
    callback_data: ProfileAction,
    state: FSMContext,
) -> None:
    await state.set_state(ProfileForm.name)
    await state.set_data(
        {
            "profile_id": callback_data.profile_id or None,
            "mode": callback_data.action,
        }
    )
    if callback.message is not None:
        await callback.message.answer("Введите название поискового профиля:")
    await callback.answer()


@router.message(ProfileForm.name)
async def profile_name_input(message: Message, state: FSMContext) -> None:
    try:
        name = validate_profile_name(message.text or "")
    except ProfileInputError as error:
        await message.answer(str(error))
        return
    await state.update_data(name=name)
    await state.set_state(ProfileForm.query)
    await message.answer("Введите поисковую фразу HH:")


@router.message(ProfileForm.query)
async def profile_query_input(message: Message, state: FSMContext) -> None:
    try:
        query = validate_profile_query(message.text or "")
    except ProfileInputError as error:
        await message.answer(str(error))
        return
    await state.update_data(query=query)
    data = await state.get_data()
    await state.set_state(ProfileForm.confirm)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Сохранить",
            callback_data=ProfileAction(action="confirm").pack(),
        ),
        InlineKeyboardButton(
            text="Отмена",
            callback_data=ProfileAction(action="cancel").pack(),
        ),
    )
    await message.answer(
        f"Название: {data['name']}\nЗапрос: {query}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(ProfileForm.confirm, ProfileAction.filter(F.action == "confirm"))
async def confirm_profile(
    callback: CallbackQuery,
    state: FSMContext,
    repository: Repository,
) -> None:
    data = await state.get_data()
    try:
        await save_profile(
            repository,
            profile_id=data.get("profile_id"),
            name=data["name"],
            query=data["query"],
        )
    except DuplicateProfileName:
        await callback.answer("Такое название уже существует", show_alert=True)
        return
    await state.clear()
    if callback.message is not None:
        await show_profiles(callback.message, repository, edit=True)
    await callback.answer("Сохранено")


@router.callback_query(ProfileAction.filter(F.action == "cancel"))
async def cancel_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")


@router.callback_query(ProfileAction.filter(F.action == "toggle"))
async def toggle_profile(
    callback: CallbackQuery,
    callback_data: ProfileAction,
    repository: Repository,
) -> None:
    profile = await repository.get_profile(callback_data.profile_id)
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await repository.set_profile_enabled(profile.id, not profile.enabled)
    if callback.message is not None:
        await show_profiles(callback.message, repository, edit=True)
    await callback.answer("Настройка изменена")


@router.callback_query(ProfileAction.filter(F.action == "delete"))
async def ask_delete(callback: CallbackQuery, callback_data: ProfileAction) -> None:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🗑 Да, удалить",
            callback_data=ProfileAction(
                action="confirm_delete",
                profile_id=callback_data.profile_id,
            ).pack(),
        ),
        InlineKeyboardButton(
            text="Отмена",
            callback_data=ProfileAction(action="cancel").pack(),
        ),
    )
    if callback.message is not None:
        await callback.message.edit_text(
            "Удалить этот поисковый профиль?",
            reply_markup=builder.as_markup(),
        )
    await callback.answer()


@router.callback_query(ProfileAction.filter(F.action == "confirm_delete"))
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: ProfileAction,
    repository: Repository,
) -> None:
    await repository.delete_profile(callback_data.profile_id)
    if callback.message is not None:
        await show_profiles(callback.message, repository, edit=True)
    await callback.answer("Профиль удалён")


@router.callback_query(ProfileAction.filter(F.action == "check"))
async def check_profile_now(
    callback: CallbackQuery,
    callback_data: ProfileAction,
    search_service: SearchService,
) -> None:
    report = await search_service.sync_profile(
        callback_data.profile_id,
        since=datetime.now(UTC) - timedelta(days=7),
    )
    if report.profile_errors:
        await callback.answer(next(iter(report.profile_errors.values())), show_alert=True)
    else:
        await callback.answer(f"Найдено новых: {len(report.discovered_ids)}", show_alert=True)


@router.message(Command("threshold"))
async def threshold_command(
    message: Message,
    repository: Repository,
    state: FSMContext,
) -> None:
    current = await repository.get_threshold(default=70)
    await state.set_state(ProfileForm.threshold)
    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=str(value),
                callback_data=ThresholdValue(value=value).pack(),
            )
            for value in (60, 70, 80)
        ]
    )
    await message.answer(
        f"Текущий порог: {current}/100. Выберите или введите число 0–100:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(ThresholdValue.filter())
async def threshold_callback(
    callback: CallbackQuery,
    callback_data: ThresholdValue,
    repository: Repository,
    state: FSMContext,
) -> None:
    value = await apply_threshold(repository, callback_data.value)
    await state.clear()
    await callback.answer(f"Порог установлен: {value}/100", show_alert=True)


@router.message(ProfileForm.threshold)
async def threshold_input(
    message: Message,
    repository: Repository,
    state: FSMContext,
) -> None:
    try:
        value = await apply_threshold(repository, message.text or "")
    except ProfileInputError as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(f"Порог установлен: {value}/100")


@router.message(Command("hide_threshold"))
async def auto_hide_threshold_command(
    message: Message,
    repository: Repository,
    state: FSMContext,
) -> None:
    current = await repository.get_auto_hide_threshold(default=20)
    await state.set_state(ProfileForm.auto_hide_threshold)
    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=str(value),
                callback_data=AutoHideThresholdValue(value=value).pack(),
            )
            for value in (0, 10, 20, 30)
        ]
    )
    await message.answer(
        f"Текущий порог автоскрытия: {current}/100. "
        "Значение 0 отключает автоскрытие. Выберите или введите число 0–100:",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AutoHideThresholdValue.filter())
async def auto_hide_threshold_callback(
    callback: CallbackQuery,
    callback_data: AutoHideThresholdValue,
    repository: Repository,
    state: FSMContext,
) -> None:
    value = await apply_auto_hide_threshold(repository, callback_data.value)
    await state.clear()
    label = "выключено" if value == 0 else f"{value}/100"
    await callback.answer(f"Автоскрытие: {label}", show_alert=True)


@router.message(ProfileForm.auto_hide_threshold)
async def auto_hide_threshold_input(
    message: Message,
    repository: Repository,
    state: FSMContext,
) -> None:
    try:
        value = await apply_auto_hide_threshold(repository, message.text or "")
    except ProfileInputError as error:
        await message.answer(str(error))
        return
    await state.clear()
    label = "выключено" if value == 0 else f"{value}/100"
    await message.answer(f"Автоскрытие: {label}")
