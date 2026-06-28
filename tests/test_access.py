import pytest

from hh_job_bot.access import PrivateUserMiddleware
from tests.fakes import make_message


@pytest.mark.asyncio
async def test_access_middleware_rejects_other_user() -> None:
    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = make_message(user_id=999)
    await PrivateUserMiddleware(allowed_user_id=123)(handler, event, {})
    assert called is False


@pytest.mark.asyncio
async def test_access_middleware_allows_configured_user() -> None:
    called = False

    async def handler(event, data):
        nonlocal called
        called = True

    event = make_message(user_id=123)
    await PrivateUserMiddleware(allowed_user_id=123)(handler, event, {})
    assert called is True
