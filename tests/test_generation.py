import pytest

from hh_job_bot.handlers.generation import (
    cover_letter_keyboard,
    create_cover_letter,
)
from hh_job_bot.prompts import build_cover_messages
from tests.fakes import FakeOpenRouterClient


def test_cover_prompt_requires_500_to_800_characters() -> None:
    messages = build_cover_messages("profile", "vacancy")
    combined = "\n".join(item["content"] for item in messages)
    assert "500–800" in combined
    assert "не придумывай" in combined
    assert "недоверенные данные" in combined


def test_generated_letter_keyboard_has_explicit_hh_apply(vacancy_factory) -> None:
    markup = cover_letter_keyboard(vacancy_factory())
    callback_data = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any(":apply:" in value for value in callback_data)


@pytest.mark.asyncio
async def test_cover_generation_sends_and_saves_valid_text(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.text = "А" * 550

    text = await create_cover_letter(
        repo,
        fake_openrouter,
        candidate_profile="profile",
        vacancy_id=vacancy.hh_id,
        model="deepseek/deepseek-v4-flash",
    )

    saved = await repo.list_cover_letters(vacancy.hh_id)
    assert text == "А" * 550
    assert saved[-1].text == text


@pytest.mark.asyncio
async def test_invalid_length_is_rejected_after_correction(repo, vacancy_factory) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.text = "коротко"

    with pytest.raises(ValueError, match="500"):
        await create_cover_letter(
            repo,
            fake_openrouter,
            candidate_profile="profile",
            vacancy_id=vacancy.hh_id,
            model="deepseek/deepseek-v4-flash",
        )
    assert await repo.list_cover_letters(vacancy.hh_id) == []
    assert len(fake_openrouter.calls) == 3


@pytest.mark.asyncio
async def test_invalid_language_and_placeholder_trigger_regeneration(
    repo,
    vacancy_factory,
) -> None:
    profile = await repo.create_profile("AI", "AI developer")
    vacancy = vacancy_factory()
    await repo.upsert_vacancy(vacancy, profile_id=profile.id)
    fake_openrouter = FakeOpenRouterClient()
    fake_openrouter.texts = [
        "А" * 520 + " [Имя]",
        "Б" * 520 + " 日 🚀",
        "В" * 550,
    ]

    text = await create_cover_letter(
        repo,
        fake_openrouter,
        candidate_profile="Использую FastAPI",
        vacancy_id=vacancy.hh_id,
        model="deepseek/deepseek-v4-flash",
    )

    assert text == "В" * 550
    assert len(fake_openrouter.calls) == 3
    second_prompt = "\n".join(
        message["content"] for message in fake_openrouter.calls[1][1]
    )
    assert "заглушка" in second_prompt
