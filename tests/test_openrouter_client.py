import httpx
import pytest

from hh_job_bot.openrouter_client import OpenRouterClient


@pytest.mark.asyncio
async def test_complete_json_calls_openrouter_with_structured_format(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"score": 70, "matches": [], "gaps": [], "reason": "ok"}'
                        }
                    }
                ]
            },
        )
    )
    client = OpenRouterClient("secret")

    result = await client.complete_json(
        "deepseek/deepseek-v4-flash",
        [{"role": "user", "content": "score"}],
    )

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer secret"
    assert result["score"] == 70
    assert b'"type":"json_object"' in request.content
    assert b'"reasoning":{"enabled":false}' in request.content
    await client.close()


@pytest.mark.asyncio
async def test_complete_text_disables_reasoning_to_preserve_output_budget(respx_mock) -> None:
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Готовое письмо"}}]},
        )
    )
    client = OpenRouterClient("secret")

    result = await client.complete_text(
        "deepseek/deepseek-v4-flash",
        [{"role": "user", "content": "letter"}],
    )

    assert result == "Готовое письмо"
    assert b'"reasoning":{"enabled":false}' in route.calls[0].request.content
    await client.close()
