from hh_job_bot.cover_letter_validation import (
    build_allowed_tech_terms,
    cover_letter_issues,
)


def test_valid_russian_letter_allows_technology_names() -> None:
    text = (
        "Работаю с ChatGPT, Cursor, Python, Playwright, n8n и REST API. "
        + "А" * 500
    )
    assert cover_letter_issues(text, allowed_latin_terms=set()) == []


def test_context_allows_only_technical_latin_terms() -> None:
    terms = build_allowed_tech_terms(
        "Работаю с FastAPI, AI-assisted разработкой и web3",
        "Интеграции через CI/CD; engineer position",
    )
    assert {"fastapi", "ai-assisted", "web3", "ci/cd"} <= terms
    assert "engineer" not in terms
    assert "position" not in terms


def test_validator_rejects_placeholders_foreign_scripts_and_emoji() -> None:
    base = "А" * 520

    def issues(text: str) -> str:
        return " ".join(cover_letter_issues(text, allowed_latin_terms=set()))

    assert "заглушка" in issues(base + " [Имя]")
    assert "заглушка" in issues(base + " {Компания}")
    assert "заглушка" in issues(base + " <контакт>")
    assert "посторонний алфавит" in issues(base + " 日常")
    assert "посторонний алфавит" in issues(base + " مرحبا")
    assert "посторонний алфавит" in issues(base + " γειά")
    assert "эмодзи" in issues(base + " 🚀")
    assert "представление по имени" in issues("Меня зовут Иван. " + base)


def test_validator_rejects_english_prose_but_allows_context_tech() -> None:
    base = "А" * 500
    allowed = {"fastapi", "ci/cd"}
    assert cover_letter_issues(
        base + " FastAPI CI/CD",
        allowed_latin_terms=allowed,
    ) == []
    issues = cover_letter_issues(
        base + " in daily work",
        allowed_latin_terms=allowed,
    )
    assert any("латинские слова" in issue for issue in issues)


def test_validator_reports_actual_invalid_length() -> None:
    assert cover_letter_issues("коротко", allowed_latin_terms=set()) == [
        "длина 7 знаков вне диапазона 500–800"
    ]
