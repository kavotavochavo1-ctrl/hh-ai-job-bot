from collections.abc import Callable

import pytest

from hh_job_bot.hh_apply_service import HHApplyError
from hh_job_bot.hh_playwright import (
    ADD_LETTER,
    ALREADY_APPLIED,
    CHAT_ADD_COVER_LETTER,
    CHAT_MESSAGE_INPUT,
    CHAT_SEND_BUTTON,
    EMPLOYER_QUESTIONS,
    LEGACY_ADD_LETTER,
    LEGACY_LETTER_INPUT,
    LEGACY_SUBMIT_BUTTON,
    LETTER_INPUT,
    RESPONSE_BUTTON,
    RESUME_DROPDOWN,
    RESUME_OPTIONS,
    SUBMIT_BUTTON,
    chat_vacancy_selector,
    prepare_application_page,
    response_button_selector,
)


class FakeLocator:
    def __init__(
        self,
        count: int = 0,
        *,
        enabled: bool = True,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        self.count_value = count
        self.enabled = enabled
        self.on_click = on_click
        self.clicks = 0
        self.filled: str | None = None
        self.first_selected = False

    @property
    def first(self):
        self.first_selected = True
        return self

    async def count(self) -> int:
        return self.count_value

    async def click(self) -> None:
        if self.count_value > 1 and not self.first_selected:
            raise RuntimeError("strict mode violation")
        if not self.enabled:
            raise RuntimeError("button disabled")
        self.clicks += 1
        if self.on_click is not None:
            self.on_click()

    async def fill(self, text: str) -> None:
        self.filled = text

    async def input_value(self) -> str:
        return self.filled or ""


class FakePage:
    def __init__(self, *, url: str = "https://hh.ru/vacancy/42") -> None:
        self.url = url
        self.locators: dict[str, FakeLocator] = {}
        self.roles: dict[tuple[str, str, bool], FakeLocator] = {}
        self.frames = [self]
        self.chat_frame: FakePage | None = None

    @classmethod
    def popup_form(cls, *, url: str = "https://hh.ru/vacancy/42"):
        page = cls(url=url)
        page.locators = {
            ALREADY_APPLIED: FakeLocator(),
            RESPONSE_BUTTON: FakeLocator(1),
            EMPLOYER_QUESTIONS: FakeLocator(),
            RESUME_DROPDOWN: FakeLocator(1),
            RESUME_OPTIONS: FakeLocator(1),
            ADD_LETTER: FakeLocator(1),
            LETTER_INPUT: FakeLocator(1),
            SUBMIT_BUTTON: FakeLocator(1),
            LEGACY_ADD_LETTER: FakeLocator(),
            LEGACY_LETTER_INPUT: FakeLocator(),
            LEGACY_SUBMIT_BUTTON: FakeLocator(),
        }
        return page

    @classmethod
    def chat_form(cls, *, vacancy_id: str = "42"):
        page = cls.popup_form(url=f"https://hh.ru/vacancy/{vacancy_id}")
        page.locators[ALREADY_APPLIED] = FakeLocator(1)
        page.locators[response_button_selector(vacancy_id)] = FakeLocator(1)
        chat_frame = cls(url="https://chatik.hh.ru/chat/123")
        chat_frame.locators[chat_vacancy_selector(vacancy_id)] = FakeLocator(1)
        chat_frame.locators[CHAT_ADD_COVER_LETTER] = FakeLocator(1)
        message = FakeLocator(1)
        chat_frame.locators[CHAT_MESSAGE_INPUT] = message
        chat_frame.locators[CHAT_SEND_BUTTON] = FakeLocator(
            1,
            on_click=lambda: setattr(message, "filled", ""),
        )
        page.frames = [page, chat_frame]
        page.chat_frame = chat_frame
        return page

    def locator(self, selector: str) -> FakeLocator:
        return self.locators.setdefault(selector, FakeLocator())

    def get_by_role(self, role: str, *, name: str, exact: bool) -> FakeLocator:
        return self.roles.setdefault((role, name, exact), FakeLocator())

    async def wait_for_timeout(self, milliseconds: int) -> None:
        return None


@pytest.mark.asyncio
async def test_dry_run_stops_before_new_one_click_response() -> None:
    page = FakePage.popup_form()

    with pytest.raises(HHApplyError, match="Тестовый режим"):
        await prepare_application_page(page, "А" * 550, dry_run=True)

    assert page.locators[RESPONSE_BUTTON].clicks == 0
    assert page.locators[SUBMIT_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_multiple_response_buttons_use_first_match() -> None:
    page = FakePage.popup_form()
    page.locators[RESPONSE_BUTTON] = FakeLocator(3)

    result = await prepare_application_page(page, "А" * 550, dry_run=False)

    assert result == "submitted"
    assert page.locators[RESPONSE_BUTTON].first_selected is True
    assert page.locators[RESPONSE_BUTTON].clicks == 1


@pytest.mark.asyncio
async def test_response_button_must_match_current_vacancy_id() -> None:
    page = FakePage.popup_form()
    page.locators[RESPONSE_BUTTON] = FakeLocator(4)
    matching_selector = response_button_selector("42")
    page.locators[matching_selector] = FakeLocator(2)

    result = await prepare_application_page(
        page,
        "А" * 550,
        dry_run=False,
        vacancy_id="42",
    )

    assert result == "submitted"
    assert page.locators[RESPONSE_BUTTON].clicks == 0
    assert page.locators[matching_selector].clicks == 1


@pytest.mark.asyncio
async def test_live_mode_clicks_submit_once() -> None:
    page = FakePage.popup_form()

    result = await prepare_application_page(page, "А" * 550, dry_run=False)

    assert result == "submitted"
    assert page.locators[SUBMIT_BUTTON].clicks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "selector"),
    [
        ("https://hh.ru/account/login", None),
        ("https://hh.ru/account/captcha", None),
        ("https://hh.ru/vacancy/42", EMPLOYER_QUESTIONS),
    ],
)
async def test_unsafe_pages_stop_without_submit(
    url: str,
    selector: str | None,
) -> None:
    page = FakePage.popup_form(url=url)
    if selector:
        page.locators[selector] = FakeLocator(1)

    with pytest.raises(HHApplyError):
        await prepare_application_page(page, "А" * 550, dry_run=False)

    assert page.locators[SUBMIT_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_multiple_resumes_stop_without_submit() -> None:
    page = FakePage.popup_form()
    page.locators[RESUME_OPTIONS] = FakeLocator(2)

    with pytest.raises(HHApplyError, match="одно резюме"):
        await prepare_application_page(page, "А" * 550, dry_run=False)

    assert page.locators[SUBMIT_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_missing_letter_field_and_chat_stops_without_submit() -> None:
    page = FakePage.popup_form()
    page.locators[LETTER_INPUT] = FakeLocator()
    page.locators[LEGACY_LETTER_INPUT] = FakeLocator()

    with pytest.raises(HHApplyError, match="чат"):
        await prepare_application_page(page, "А" * 550, dry_run=False)

    assert page.locators[SUBMIT_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_existing_response_sends_letter_through_verified_chat() -> None:
    page = FakePage.chat_form()
    chat_frame = page.chat_frame
    assert chat_frame is not None

    result = await prepare_application_page(
        page,
        "А" * 550,
        dry_run=False,
        vacancy_id="42",
    )

    assert result == "submitted"
    assert page.locators[RESPONSE_BUTTON].clicks == 0
    assert page.locators[SUBMIT_BUTTON].clicks == 0
    assert chat_frame.locators[CHAT_MESSAGE_INPUT].filled == ""
    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 1


@pytest.mark.asyncio
async def test_one_click_response_falls_back_to_verified_chat() -> None:
    page = FakePage.chat_form()
    page.locators[ALREADY_APPLIED] = FakeLocator()
    page.locators[response_button_selector("42")].on_click = lambda: setattr(
        page.locators[ALREADY_APPLIED],
        "count_value",
        1,
    )
    page.locators[LETTER_INPUT] = FakeLocator()
    page.locators[LEGACY_LETTER_INPUT] = FakeLocator()
    chat_frame = page.chat_frame
    assert chat_frame is not None

    result = await prepare_application_page(
        page,
        "А" * 550,
        dry_run=False,
        vacancy_id="42",
    )

    assert result == "submitted"
    assert page.locators[response_button_selector("42")].clicks == 1
    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 1


@pytest.mark.asyncio
async def test_chat_for_another_vacancy_stops_without_send() -> None:
    page = FakePage.chat_form()
    chat_frame = page.chat_frame
    assert chat_frame is not None
    chat_frame.locators[chat_vacancy_selector("42")] = FakeLocator()

    with pytest.raises(HHApplyError, match="другой вакансии"):
        await prepare_application_page(
            page,
            "А" * 550,
            dry_run=False,
            vacancy_id="42",
        )

    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_missing_chat_add_cover_letter_stops_without_send() -> None:
    page = FakePage.chat_form()
    chat_frame = page.chat_frame
    assert chat_frame is not None
    chat_frame.locators[CHAT_ADD_COVER_LETTER] = FakeLocator()

    with pytest.raises(HHApplyError, match="добавить сопроводительное"):
        await prepare_application_page(
            page,
            "А" * 550,
            dry_run=False,
            vacancy_id="42",
        )

    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_existing_response_dry_run_fills_chat_without_send() -> None:
    page = FakePage.chat_form()
    chat_frame = page.chat_frame
    assert chat_frame is not None

    result = await prepare_application_page(
        page,
        "А" * 550,
        dry_run=True,
        vacancy_id="42",
    )

    assert result == "dry_run_ready"
    assert chat_frame.locators[CHAT_MESSAGE_INPUT].filled == "А" * 550
    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 0


@pytest.mark.asyncio
async def test_chat_send_not_confirmed_is_not_retried() -> None:
    page = FakePage.chat_form()
    chat_frame = page.chat_frame
    assert chat_frame is not None
    chat_frame.locators[CHAT_SEND_BUTTON] = FakeLocator(1)

    with pytest.raises(HHApplyError, match="не подтвердил"):
        await prepare_application_page(
            page,
            "А" * 550,
            dry_run=False,
            vacancy_id="42",
        )

    assert chat_frame.locators[CHAT_SEND_BUTTON].clicks == 1
