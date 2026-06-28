from dataclasses import dataclass
from typing import Any, Protocol

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from hh_job_bot.cards import render_vacancy, vacancy_keyboard
from hh_job_bot.repository import Repository


class TelegramSender(Protocol):
    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class DispatchReport:
    cards_sent: int
    remaining: int


class NotificationService:
    def __init__(
        self,
        repository: Repository,
        bot: TelegramSender,
        *,
        user_id: int,
    ) -> None:
        self.repository = repository
        self.bot = bot
        self.user_id = user_id

    async def dispatch(self, *, threshold: int) -> DispatchReport:
        eligible = await self.repository.eligible_notifications(limit=1000)
        batch = eligible[:10]
        for vacancy in batch:
            await self.bot.send_message(
                self.user_id,
                render_vacancy(vacancy),
                parse_mode="HTML",
                reply_markup=vacancy_keyboard(vacancy),
            )
            await self.repository.mark_notified(vacancy.hh_id)

        remaining = max(len(eligible) - len(batch), 0)
        if remaining:
            await self.bot.send_message(
                self.user_id,
                (
                    f"Ещё {remaining} новых вакансий с релевантностью "
                    f"не ниже {threshold}/100."
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📚 Открыть каталог",
                                callback_data="catalog:open",
                            )
                        ]
                    ]
                ),
            )
        return DispatchReport(cards_sent=len(batch), remaining=remaining)
