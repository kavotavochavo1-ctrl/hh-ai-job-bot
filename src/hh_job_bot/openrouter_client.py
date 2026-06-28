import json
from typing import Any

import httpx
from pydantic import SecretStr
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


class OpenRouterError(RuntimeError):
    pass


class OpenRouterTransientError(OpenRouterError):
    pass


def _secret_value(value: str | SecretStr) -> str:
    return value.get_secret_value() if isinstance(value, SecretStr) else value


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | SecretStr,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 45.0,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {_secret_value(api_key)}",
                "Content-Type": "application/json",
                "X-OpenRouter-Title": "Personal HH Job Bot",
            },
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def complete_json(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        content = await self._complete(
            {
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_completion_tokens": 500,
                "reasoning": {"enabled": False},
                "response_format": {"type": "json_object"},
            }
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise OpenRouterError("OpenRouter returned invalid JSON") from error

    async def complete_text(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return await self._complete(
            {
                "model": model,
                "messages": messages,
                "temperature": 0.5,
                "max_completion_tokens": 700,
                "reasoning": {"enabled": False},
            }
        )

    async def _complete(self, payload: dict[str, Any]) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=4),
            retry=retry_if_exception_type((OpenRouterTransientError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                response = await self._http.post("/chat/completions", json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    raise OpenRouterTransientError(
                        f"OpenRouter temporary error: {response.status_code}"
                    )
                if response.status_code >= 400:
                    raise OpenRouterError(f"OpenRouter API error: {response.status_code}")
                data = response.json()
                try:
                    return str(data["choices"][0]["message"]["content"]).strip()
                except (KeyError, IndexError, TypeError) as error:
                    raise OpenRouterError("OpenRouter response has no content") from error
        raise OpenRouterError("OpenRouter request exhausted without response")
