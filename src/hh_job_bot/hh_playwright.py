import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hh_job_bot.hh_apply_service import HHApplyError

RESPONSE_BUTTON = '[data-qa="vacancy-response-link-top"]'
RESUME_DROPDOWN = '[data-qa="resume-title"]'
RESUME_OPTIONS = '[data-qa^="magritte-select-option-"]'
ADD_LETTER = '[data-qa="add-cover-letter"]'
LETTER_INPUT = '[data-qa="vacancy-response-popup-form-letter-input"]'
SUBMIT_BUTTON = '[data-qa="vacancy-response-submit-popup"]'
LEGACY_ADD_LETTER = '[data-qa="vacancy-response-letter-toggle-text"]'
LEGACY_LETTER_INPUT = "#cover-letter textarea"
LEGACY_SUBMIT_BUTTON = '[data-qa="vacancy-response-letter-submit"]'
ALREADY_APPLIED = '[data-qa="vacancy-response-link-view-topic"]'
CHAT_ADD_COVER_LETTER = '[data-qa="chatik-chat-message-applicant-action-text"]'
CHAT_MESSAGE_INPUT = 'textarea[data-qa="chatik-new-message-text"]'
CHAT_SEND_BUTTON = 'button[data-qa="chatik-do-send-message"]'
EMPLOYER_QUESTIONS = (
    '[data-qa*="vacancy-response-question"], '
    '[data-qa*="vacancy-response-test"]'
)


def vacancy_id_from_url(vacancy_url: str) -> str:
    path_parts = urlparse(vacancy_url).path.rstrip("/").split("/")
    if len(path_parts) < 2 or path_parts[-2] != "vacancy":
        raise HHApplyError("Некорректная ссылка вакансии HH.")
    vacancy_id = path_parts[-1]
    if not vacancy_id.isdigit():
        raise HHApplyError("Некорректная ссылка вакансии HH.")
    return vacancy_id


def response_button_selector(vacancy_id: str) -> str:
    if not vacancy_id.isdigit():
        raise HHApplyError("Некорректный идентификатор вакансии HH.")
    return (
        f'{RESPONSE_BUTTON}[href*="vacancyId={vacancy_id}&"], '
        f'{RESPONSE_BUTTON}[href$="vacancyId={vacancy_id}"]'
    )


def chat_vacancy_selector(vacancy_id: str) -> str:
    if not vacancy_id.isdigit():
        raise HHApplyError("Некорректный идентификатор вакансии HH.")
    return (
        f'a[href*="/vacancy/{vacancy_id}?"], '
        f'a[href$="/vacancy/{vacancy_id}"]'
    )


async def find_chat_frame(page: Any) -> Any:
    for _ in range(20):
        for frame in page.frames:
            parsed = urlparse(frame.url)
            if parsed.hostname == "chatik.hh.ru" and parsed.path.startswith("/chat/"):
                return frame
        await page.wait_for_timeout(250)
    raise HHApplyError("HH не загрузил чат отклика.")


async def send_cover_letter_in_chat(
    page: Any,
    letter: str,
    *,
    vacancy_id: str,
    dry_run: bool,
) -> str:
    chat = page.locator(ALREADY_APPLIED)
    if not await chat.count():
        raise HHApplyError("HH не показал чат отклика.")
    await chat.first.click()
    chat_frame = await find_chat_frame(page)
    if not await chat_frame.locator(chat_vacancy_selector(vacancy_id)).count():
        raise HHApplyError("Открытый чат относится к другой вакансии.")

    add_letter = chat_frame.locator(CHAT_ADD_COVER_LETTER)
    if not await add_letter.count():
        raise HHApplyError("HH не предложил добавить сопроводительное.")
    await add_letter.first.click()
    await chat_frame.wait_for_timeout(250)

    message = chat_frame.locator(CHAT_MESSAGE_INPUT)
    if not await message.count():
        raise HHApplyError("HH не показал поле сообщения.")
    await message.fill(letter)

    send = chat_frame.locator(CHAT_SEND_BUTTON)
    if not await send.count():
        raise HHApplyError("HH не показал кнопку отправки сообщения.")
    if dry_run:
        return "dry_run_ready"
    await send.first.click()
    await chat_frame.wait_for_timeout(1000)
    if await message.input_value():
        raise HHApplyError("HH не подтвердил отправку сопроводительного.")
    return "submitted"


async def prepare_application_page(
    page: Any,
    letter: str,
    *,
    dry_run: bool,
    vacancy_id: str | None = None,
) -> str:
    lowered_url = page.url.casefold()
    if "/account/login" in lowered_url or "captcha" in lowered_url:
        raise HHApplyError("Сессия HH истекла или запрошена CAPTCHA.")
    current_vacancy_id = vacancy_id or vacancy_id_from_url(page.url)
    if await page.locator(ALREADY_APPLIED).count():
        return await send_cover_letter_in_chat(
            page,
            letter,
            vacancy_id=current_vacancy_id,
            dry_run=dry_run,
        )

    selector = (
        response_button_selector(current_vacancy_id)
        if vacancy_id is not None
        else RESPONSE_BUTTON
    )
    response = page.locator(selector)
    if not await response.count():
        raise HHApplyError("HH не показал кнопку отклика.")
    if dry_run:
        raise HHApplyError(
            "Тестовый режим не нажимает новый отклик: HH может отправить его сразу."
        )
    await response.first.click()
    await page.wait_for_timeout(500)
    if await page.locator(EMPLOYER_QUESTIONS).count():
        raise HHApplyError("Вакансия требует ответов или теста.")

    resume_dropdown = page.locator(RESUME_DROPDOWN)
    if await resume_dropdown.count():
        await resume_dropdown.first.click()
        await page.wait_for_timeout(250)
        options = page.locator(RESUME_OPTIONS)
        if await options.count() != 1:
            raise HHApplyError("Ожидалось ровно одно резюме.")
        await options.first.click()

    add_letter = page.locator(ADD_LETTER)
    if await add_letter.count():
        await add_letter.first.click()
    letter_input = page.locator(LETTER_INPUT)
    if not await letter_input.count():
        legacy_toggle = page.locator(LEGACY_ADD_LETTER)
        if await legacy_toggle.count():
            await legacy_toggle.first.click()
        letter_input = page.locator(LEGACY_LETTER_INPUT)
    if not await letter_input.count():
        return await send_cover_letter_in_chat(
            page,
            letter,
            vacancy_id=current_vacancy_id,
            dry_run=False,
        )
    await letter_input.fill(letter)

    submit = page.locator(SUBMIT_BUTTON)
    if not await submit.count():
        submit = page.locator(LEGACY_SUBMIT_BUTTON)
    if not await submit.count():
        raise HHApplyError("HH не показал кнопку отправки.")
    if dry_run:
        return "dry_run_ready"
    await submit.first.click()
    await page.wait_for_timeout(1000)
    return "submitted"


class PlaywrightHHBrowser:
    def __init__(
        self,
        storage_state_path: Path,
        *,
        timeout_seconds: int = 90,
    ) -> None:
        self.storage_state_path = storage_state_path
        self.timeout_seconds = timeout_seconds
        self._lock = asyncio.Lock()

    async def apply(
        self,
        vacancy_url: str,
        letter: str,
        *,
        dry_run: bool,
    ) -> str:
        if not self.storage_state_path.is_file():
            raise HHApplyError("Сессия HH не настроена.")
        vacancy_id = vacancy_id_from_url(vacancy_url)
        async with self._lock, asyncio.timeout(self.timeout_seconds):
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--disable-dev-shm-usage", "--no-sandbox"],
                )
                context = await browser.new_context(
                    storage_state=str(self.storage_state_path),
                    locale="ru-RU",
                )
                try:
                    page = await context.new_page()
                    await page.goto(vacancy_url, wait_until="domcontentloaded")
                    return await prepare_application_page(
                        page,
                        letter,
                        dry_run=dry_run,
                        vacancy_id=vacancy_id,
                    )
                finally:
                    await context.close()
                    await browser.close()
