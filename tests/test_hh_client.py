from datetime import UTC, datetime, timedelta

import httpx
import pytest

from hh_job_bot.hh_web_client import HHWebClient

SEARCH_HTML = """
<html><body>
  <div data-qa="vacancy-serp__vacancy">
    <a data-qa="serp-item__title"
       href="https://hh.ru/vacancy/42?query=n8n">AI developer</a>
  </div>
</body></html>
"""


@pytest.mark.asyncio
async def test_search_uses_public_html_and_no_region_filter(respx_mock) -> None:
    route = respx_mock.get("https://hh.ru/search/vacancy").mock(
        return_value=httpx.Response(200, text=SEARCH_HTML)
    )
    client = HHWebClient()

    since = datetime.now(UTC) - timedelta(days=7)
    results = await client.search("n8n developer", since)

    query = route.calls[0].request.url.params
    assert "area" not in query
    assert query.get_list("experience") == ["noExperience", "between1And3"]
    assert query.get_list("search_field") == ["name", "company_name", "description"]
    assert query["work_format"] == "REMOTE"
    assert query["period"] == "7"
    assert results == [{"id": "42"}]
    assert "Authorization" not in route.calls[0].request.headers
    await client.close()


@pytest.mark.asyncio
async def test_search_paginates_while_next_button_exists(respx_mock) -> None:
    def page_response(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "0"))
        next_link = '<a data-qa="pager-next" href="?page=1">next</a>' if page == 0 else ""
        item_id = "new" if page == 0 else "old"
        return httpx.Response(
            200,
            text=SEARCH_HTML.replace("/42?", f"/{item_id}?").replace(
                "</body>",
                f"{next_link}</body>",
            ),
        )

    respx_mock.get("https://hh.ru/search/vacancy").mock(side_effect=page_response)
    client = HHWebClient()

    results = await client.search("AI developer", datetime(2026, 6, 20, tzinfo=UTC))

    assert [item["id"] for item in results] == ["new", "old"]
    await client.close()


@pytest.mark.asyncio
async def test_search_limits_default_page_count_to_protect_against_captcha(
    respx_mock,
) -> None:
    def page_response(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "0"))
        return httpx.Response(
            200,
            text=SEARCH_HTML.replace("/42?", f"/{page}?").replace(
                "</body>",
                '<a data-qa="pager-next" href="?page=next">next</a></body>',
            ),
        )

    route = respx_mock.get("https://hh.ru/search/vacancy").mock(side_effect=page_response)
    client = HHWebClient()

    results = await client.search("AI automation", datetime(2026, 6, 20, tzinfo=UTC))

    assert [item["id"] for item in results] == ["0", "1", "2"]
    assert len(route.calls) == 3
    await client.close()


@pytest.mark.asyncio
async def test_vacancy_details_come_from_json_ld(respx_mock) -> None:
    respx_mock.get("https://hh.ru/vacancy/42").mock(
        return_value=httpx.Response(
            200,
            text="""
            <html><head>
              <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "identifier": {"value": "42"},
                "title": "AI developer",
                "description": "<p>Build <strong>n8n</strong> workflows</p>",
                "datePosted": "2026-06-27T14:35:00+03:00",
                "hiringOrganization": {"name": "Example"},
                "jobLocation": {"address": {"addressLocality": "Москва"}}
              }
              </script>
            </head><body>
              <span data-qa="vacancy-salary">100 000–150 000 ₽ на руки</span>
              <span data-qa="vacancy-experience">Опыт 1–3 года</span>
            </body></html>
            """,
        )
    )
    client = HHWebClient()

    vacancy = await client.get_vacancy("42")

    assert vacancy.description == "Build n8n workflows"
    assert vacancy.salary_text == "100 000–150 000 ₽ на руки"
    assert vacancy.experience_name == "Опыт 1–3 года"
    assert vacancy.work_format_text == "Удалённо"
    assert len(vacancy.description_hash) == 64
    await client.close()
