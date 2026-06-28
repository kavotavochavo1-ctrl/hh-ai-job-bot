FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /data \
    && chown -R bot:bot /data

COPY pyproject.toml candidate_profile.md ./

RUN python -m pip install --no-cache-dir "playwright>=1.53,<2" \
    && python -m playwright install --with-deps chromium --only-shell \
    && chmod -R a+rX /ms-playwright

COPY src ./src

RUN python -m pip install --no-cache-dir .

USER bot

CMD ["python", "-m", "hh_job_bot.app"]
