import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from hh_job_bot.domain import VacancyData

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


class HHWebError(RuntimeError):
    pass


class HHWebTransientError(HHWebError):
    pass


class HHWebBlockedError(HHWebError):
    pass


class HHWebClient:
    def __init__(
        self,
        *,
        base_url: str = "https://hh.ru",
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_pages: int = 3,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        self.max_pages = max_pages

    async def close(self) -> None:
        await self._http.aclose()

    async def search(self, query: str, since: datetime) -> list[dict[str, str]]:
        age = datetime.now(UTC) - since.astimezone(UTC)
        period = max(1, min(age.days, 30))
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for page in range(self.max_pages):
            params: list[tuple[str, str | int]] = [
                ("text", query),
                ("search_field", "name"),
                ("search_field", "company_name"),
                ("search_field", "description"),
                ("experience", "noExperience"),
                ("experience", "between1And3"),
                ("work_format", "REMOTE"),
                ("order_by", "publication_time"),
                ("period", period),
                ("page", page),
            ]
            response = await self._request("/search/vacancy", params=params)
            soup = BeautifulSoup(response.text, "html.parser")
            self._raise_if_blocked(soup, response)
            for card in soup.select('[data-qa="vacancy-serp__vacancy"]'):
                link = card.select_one('[data-qa="serp-item__title"]')
                if link is None:
                    continue
                match = re.search(r"/vacancy/([^?/#]+)", str(link.get("href") or ""))
                if match and match.group(1) not in seen:
                    seen.add(match.group(1))
                    results.append({"id": match.group(1)})
            if soup.select_one('[data-qa="pager-next"]') is None:
                break
        return results

    async def get_vacancy(self, hh_id: str) -> VacancyData:
        response = await self._request(f"/vacancy/{hh_id}")
        soup = BeautifulSoup(response.text, "html.parser")
        self._raise_if_blocked(soup, response)
        posting = self._job_posting(soup)
        raw_description = str(posting.get("description") or "")
        description = BeautifulSoup(raw_description, "html.parser").get_text(" ", strip=True)
        published_at = datetime.fromisoformat(str(posting["datePosted"])).astimezone(UTC)
        salary = soup.select_one('[data-qa="vacancy-salary"]')
        experience = soup.select_one('[data-qa="vacancy-experience"]')
        company = posting.get("hiringOrganization") or {}
        return VacancyData(
            hh_id=hh_id,
            title=str(posting.get("title") or "Без названия"),
            company=str(company.get("name") or "Компания не указана"),
            url=f"https://hh.ru/vacancy/{hh_id}",
            salary_text=salary.get_text(" ", strip=True) if salary else None,
            area_name=self._area_name(posting.get("jobLocation")),
            experience_name=experience.get_text(" ", strip=True) if experience else None,
            work_format_text="Удалённо",
            published_at=published_at,
            description=description,
            description_hash=hashlib.sha256(description.encode("utf-8")).hexdigest(),
            details_refreshed_at=datetime.now(UTC),
        )

    async def _request(self, url: str, **kwargs: Any) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, max=4),
            retry=retry_if_exception_type((HHWebTransientError, httpx.TransportError)),
            reraise=True,
        ):
            with attempt:
                response = await self._http.get(url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    raise HHWebTransientError(f"HH temporary error: {response.status_code}")
                if response.status_code in {401, 403}:
                    raise HHWebBlockedError(f"HH blocked the request: {response.status_code}")
                if response.status_code >= 400:
                    raise HHWebError(f"HH page error: {response.status_code}")
                return response
        raise HHWebError("HH request exhausted without response")

    @staticmethod
    def _raise_if_blocked(soup: BeautifulSoup, response: httpx.Response) -> None:
        text = soup.get_text(" ", strip=True).casefold()
        if "captcha" in str(response.url).casefold() or "подтвердите, что вы не робот" in text:
            raise HHWebBlockedError("HH запросил CAPTCHA")

    @staticmethod
    def _job_posting(soup: BeautifulSoup) -> dict[str, Any]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.get_text())
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate.get("@type") == "JobPosting":
                    return candidate
        raise HHWebError("HH vacancy page has no JobPosting data")

    @staticmethod
    def _area_name(location: Any) -> str | None:
        if isinstance(location, list):
            location = location[0] if location else None
        if not isinstance(location, dict):
            return None
        address = location.get("address")
        if isinstance(address, dict):
            return address.get("addressLocality") or address.get("addressRegion")
        return None
