from pathlib import Path


def test_ci_runs_tests_and_lint() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in workflow
    assert "python -m pytest -q" in workflow
    assert "python -m ruff check src tests scripts" in workflow


def test_public_security_files_exist() -> None:
    license_text = Path("LICENSE").read_text(encoding="utf-8")
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "2026 kavotavochavo1-ctrl" in license_text
    for secret_file in (".env", "hh_storage_state.json", "bot.db"):
        assert secret_file in security


def test_readme_has_project_sections() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for text in (
        "AI-powered HH.ru job monitoring",
        "## Возможности",
        "## Архитектура",
        "```mermaid",
        "## Быстрый старт",
        "## Безопасность",
        "## Ограничения",
        "## Лицензия",
    ):
        assert text in readme
