from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class PrivateUserMiddleware(BaseMiddleware):
    def __init__(self, *, allowed_user_id: int) -> None:
        self.allowed_user_id = allowed_user_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor = getattr(event, "from_user", None)
        if actor is None:
            message = getattr(event, "message", None)
            actor = getattr(message, "from_user", None)
        if actor is None or actor.id != self.allowed_user_id:
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён", show_alert=True)
            return None
        return await handler(event, data)
