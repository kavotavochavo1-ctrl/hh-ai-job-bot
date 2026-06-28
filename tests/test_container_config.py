from pathlib import Path


def test_compose_has_persistence_healthcheck_and_log_rotation() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "bot-data:/data" in compose
    assert "healthcheck:" in compose
    assert "restart: unless-stopped" in compose
    assert 'max-size: "10m"' in compose
    assert 'max-file: "3"' in compose


def test_dockerfile_runs_as_non_root_user() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "USER bot" in dockerfile
    assert 'CMD ["python", "-m", "hh_job_bot.app"]' in dockerfile
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in dockerfile
    assert "playwright install --with-deps chromium" in dockerfile
    assert "--only-shell" in dockerfile
