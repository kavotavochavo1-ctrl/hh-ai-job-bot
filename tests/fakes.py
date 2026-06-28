from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


class FakeHHClient:
    def __init__(self) -> None:
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.default_results: list[dict[str, Any]] = []
        self.details: dict[str, Any] = {}
        self.queries: list[str] = []

    async def search(self, query: str, since) -> list[dict[str, Any]]:
        self.queries.append(query)
        return self.results.get(query, self.default_results)

    async def get_vacancy(self, hh_id: str):
        return self.details[hh_id]

    async def close(self) -> None:
        return None


class FakeOpenRouterClient:
    def __init__(self) -> None:
        self.result: dict[str, Any] = {}
        self.text = ""
        self.texts: list[str] = []
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def complete_json(self, model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        self.calls.append((model, messages))
        return self.result

    async def complete_text(self, model: str, messages: list[dict[str, str]]) -> str:
        self.calls.append((model, messages))
        return self.texts.pop(0) if self.texts else self.text


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> SimpleNamespace:
        self.messages.append({"chat_id": chat_id, "text": text, **kwargs})
        return SimpleNamespace(message_id=len(self.messages))


@dataclass
class FakeMessage:
    text: str = ""
    edit_count: int = 0
    latest_vacancy_id: str | None = None
    latest_counter: str | None = None
    sent_messages: list[str] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.text = text
        self.sent_messages.append(text)

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.text = text
        self.edit_count += 1


@dataclass
class ServicesSpy:
    calls: list[str] = field(default_factory=list)
    repo: Any = None


def make_message(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id))
