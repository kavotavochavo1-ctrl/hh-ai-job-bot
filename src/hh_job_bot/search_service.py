from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from hh_job_bot.domain import VacancyData
from hh_job_bot.repository import Repository


class HHSearchClient(Protocol):
    async def search(self, query: str, since: datetime) -> list[dict]: ...

    async def get_vacancy(self, hh_id: str) -> VacancyData: ...


@dataclass(frozen=True, slots=True)
class SyncReport:
    discovered_ids: list[str]
    updated_ids: list[str]
    profile_errors: dict[str, str]


class SearchService:
    def __init__(self, repository: Repository, hh_client: HHSearchClient) -> None:
        self.repository = repository
        self.hh_client = hh_client

    async def initial_sync(
        self,
        *,
        days: int = 7,
        now: datetime | None = None,
    ) -> SyncReport:
        current = now or datetime.now(UTC)
        return await self.sync(since=current - timedelta(days=days), baseline=True)

    async def sync(self, *, since: datetime, baseline: bool = False) -> SyncReport:
        discovered_ids: list[str] = []
        updated_ids: list[str] = []
        errors: dict[str, str] = {}
        profiles = await self.repository.list_profiles(enabled_only=True)

        for profile in profiles:
            try:
                results = await self.hh_client.search(profile.query, since)
                for item in results:
                    hh_id = str(item["id"])
                    existing = await self.repository.get_vacancy(hh_id)
                    if existing is None:
                        vacancy = await self.hh_client.get_vacancy(hh_id)
                        if hh_id not in discovered_ids:
                            discovered_ids.append(hh_id)
                    else:
                        vacancy = existing
                    await self.repository.upsert_vacancy(
                        vacancy,
                        profile_id=profile.id,
                        baseline=baseline or vacancy.published_at <= since,
                    )
            except Exception as error:
                errors[profile.name] = str(error)

        if not baseline:
            all_profiles = await self.repository.list_profiles()
            profile_ids = {profile.name: profile.id for profile in all_profiles}
            for stale in await self.repository.vacancies_due_for_detail_refresh():
                try:
                    refreshed = await self.hh_client.get_vacancy(stale.hh_id)
                    for profile_name in stale.profile_names:
                        profile_id = profile_ids.get(profile_name)
                        if profile_id is not None:
                            await self.repository.upsert_vacancy(
                                refreshed,
                                profile_id=profile_id,
                            )
                    updated_ids.append(stale.hh_id)
                except Exception as error:
                    errors[f"refresh:{stale.hh_id}"] = str(error)

        return SyncReport(
            discovered_ids=discovered_ids,
            updated_ids=updated_ids,
            profile_errors=errors,
        )

    async def sync_profile(self, profile_id: int, *, since: datetime) -> SyncReport:
        profile = await self.repository.get_profile(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        if not profile.enabled:
            return SyncReport([], [], {profile.name: "Профиль выключен"})
        discovered_ids: list[str] = []
        try:
            for item in await self.hh_client.search(profile.query, since):
                hh_id = str(item["id"])
                existing = await self.repository.get_vacancy(hh_id)
                vacancy = existing or await self.hh_client.get_vacancy(hh_id)
                if existing is None:
                    discovered_ids.append(hh_id)
                await self.repository.upsert_vacancy(vacancy, profile_id=profile.id)
        except Exception as error:
            return SyncReport([], [], {profile.name: str(error)})
        return SyncReport(discovered_ids, [], {})
