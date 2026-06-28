"""Capture an authenticated HH browser session without storing a password."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def capture_session(output: Path) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(locale="ru-RU")
        page = await context.new_page()
        await page.goto("https://hh.ru/account/login", wait_until="domcontentloaded")

        await asyncio.to_thread(
            input,
            "Войдите в HH в открывшемся окне и нажмите Enter здесь: ",
        )

        if "/account/login" in page.url:
            await browser.close()
            raise RuntimeError("Вход в HH не завершён.")
        if await page.locator("text=/captcha|капч/i").count():
            await browser.close()
            raise RuntimeError("HH показывает CAPTCHA; сессия не сохранена.")

        output.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(output))
        await browser.close()

    print(f"Сессия HH сохранена: {output.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("hh_storage_state.json"),
        help="Путь к закрытому файлу состояния браузера.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(capture_session(parse_args().output))
