from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from hh_job_bot.db import (
    ApplicationAttemptRow,
    AppSettingRow,
    AutoHiddenVacancyRow,
    CoverLetterRow,
    Database,
    SearchProfileRow,
    VacancyRow,
)
from hh_job_bot.domain import RelevanceAssessment, SearchProfileData, VacancyData

DEFAULT_PROFILES = (
    ("ИИ-разработчик", "ИИ-разработчик"),
    ("Вайб-кодер", "вайб-кодер OR vibe coder"),
    ("Low-code", "low-code разработчик"),
    ("n8n", "n8n разработчик"),
    ("AI automation", "AI automation OR автоматизация с ИИ"),
)


class DuplicateProfileName(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def seed_default_profiles(self) -> None:
        for name, query in DEFAULT_PROFILES:
            try:
                await self.create_profile(name, query)
            except DuplicateProfileName:
                continue

    async def list_profiles(self, *, enabled_only: bool = False) -> list[SearchProfileData]:
        statement = select(SearchProfileRow).order_by(SearchProfileRow.id)
        if enabled_only:
            statement = statement.where(SearchProfileRow.enabled.is_(True))
        async with self.database.session() as session:
            rows = (await session.scalars(statement)).all()
        return [self._profile_data(row) for row in rows]

    async def get_profile(self, profile_id: int) -> SearchProfileData | None:
        async with self.database.session() as session:
            row = await session.get(SearchProfileRow, profile_id)
        return self._profile_data(row) if row else None

    async def create_profile(self, name: str, query: str) -> SearchProfileData:
        clean_name = name.strip()
        clean_query = query.strip()
        row = SearchProfileRow(
            name=clean_name,
            name_key=clean_name.casefold(),
            query=clean_query,
            enabled=True,
        )
        async with self.database.session() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise DuplicateProfileName(clean_name) from error
            await session.refresh(row)
        return self._profile_data(row)

    async def update_profile(
        self,
        profile_id: int,
        *,
        name: str,
        query: str,
    ) -> SearchProfileData:
        async with self.database.session() as session:
            row = await session.get(SearchProfileRow, profile_id)
            if row is None:
                raise KeyError(profile_id)
            row.name = name.strip()
            row.name_key = row.name.casefold()
            row.query = query.strip()
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise DuplicateProfileName(name) from error
            await session.refresh(row)
        return self._profile_data(row)

    async def set_profile_enabled(self, profile_id: int, enabled: bool) -> None:
        async with self.database.session() as session:
            row = await session.get(SearchProfileRow, profile_id)
            if row is None:
                raise KeyError(profile_id)
            row.enabled = enabled
            await session.commit()

    async def delete_profile(self, profile_id: int) -> None:
        async with self.database.session() as session:
            await session.execute(delete(SearchProfileRow).where(SearchProfileRow.id == profile_id))
            await session.commit()

    async def upsert_vacancy(
        self,
        vacancy: VacancyData,
        *,
        profile_id: int,
        baseline: bool = False,
    ) -> VacancyData:
        now = _utc_now()
        statement = (
            select(VacancyRow)
            .where(VacancyRow.hh_id == vacancy.hh_id)
            .options(selectinload(VacancyRow.profiles))
        )
        async with self.database.session() as session:
            profile = await session.get(SearchProfileRow, profile_id)
            if profile is None:
                raise KeyError(profile_id)
            row = await session.scalar(statement)
            if row is None:
                row = VacancyRow(
                    hh_id=vacancy.hh_id,
                    title=vacancy.title,
                    company=vacancy.company,
                    url=vacancy.url,
                    salary_text=vacancy.salary_text,
                    area_name=vacancy.area_name,
                    experience_name=vacancy.experience_name,
                    work_format_text=vacancy.work_format_text,
                    published_at=vacancy.published_at,
                    description=vacancy.description,
                    description_hash=vacancy.description_hash,
                    details_refreshed_at=vacancy.details_refreshed_at or now,
                    discovered_at=vacancy.discovered_at or now,
                    baseline=baseline,
                    notification_eligible=False if baseline else None,
                    profiles=[profile],
                )
                session.add(row)
            else:
                description_changed = row.description_hash != vacancy.description_hash
                row.title = vacancy.title
                row.company = vacancy.company
                row.url = vacancy.url
                row.salary_text = vacancy.salary_text
                row.area_name = vacancy.area_name
                row.experience_name = vacancy.experience_name
                row.work_format_text = vacancy.work_format_text
                row.published_at = vacancy.published_at
                row.description = vacancy.description
                row.description_hash = vacancy.description_hash
                row.details_refreshed_at = vacancy.details_refreshed_at or now
                if description_changed:
                    row.score = None
                    row.score_reason = None
                    row.score_matches = None
                    row.score_gaps = None
                    row.scoring_attempts = 0
                    row.scoring_next_attempt_at = None
                    if row.notification_sent_at is None and not row.baseline:
                        row.notification_eligible = None
                if all(item.id != profile_id for item in row.profiles):
                    row.profiles.append(profile)
            await session.commit()
        saved = await self.get_vacancy(vacancy.hh_id)
        if saved is None:
            raise RuntimeError("Vacancy disappeared after upsert")
        return saved

    async def get_vacancy(self, hh_id: str) -> VacancyData | None:
        statement = (
            select(VacancyRow)
            .where(VacancyRow.hh_id == hh_id)
            .options(selectinload(VacancyRow.profiles))
        )
        async with self.database.session() as session:
            row = await session.scalar(statement)
        return self._vacancy_data(row) if row else None

    async def catalog(
        self,
        *,
        hidden: bool,
        since: datetime | None = None,
    ) -> list[VacancyData]:
        auto_hidden = exists(
            select(AutoHiddenVacancyRow.hh_id).where(
                AutoHiddenVacancyRow.hh_id == VacancyRow.hh_id
            )
        )
        visibility = (
            or_(VacancyRow.hidden.is_(True), auto_hidden)
            if hidden
            else (VacancyRow.hidden.is_(False) & ~auto_hidden)
        )
        statement = (
            select(VacancyRow)
            .where(visibility)
            .options(selectinload(VacancyRow.profiles))
            .order_by(VacancyRow.published_at.desc(), VacancyRow.hh_id.desc())
        )
        if since is not None:
            statement = statement.where(VacancyRow.published_at >= since)
        async with self.database.session() as session:
            rows = (await session.scalars(statement)).all()
        return [self._vacancy_data(row) for row in rows]

    async def set_hidden(self, hh_id: str, hidden: bool) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.hidden = hidden
            if not hidden:
                await session.execute(
                    delete(AutoHiddenVacancyRow).where(
                        AutoHiddenVacancyRow.hh_id == hh_id
                    )
                )
            await session.commit()

    async def mark_viewed(self, hh_id: str, at: datetime | None = None) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.viewed_at = at or _utc_now()
            await session.commit()

    async def pending_scoring(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[VacancyData]:
        current = now or _utc_now()
        statement = (
            select(VacancyRow)
            .where(
                or_(
                    VacancyRow.scored_description_hash.is_(None),
                    VacancyRow.scored_description_hash != VacancyRow.description_hash,
                ),
                or_(
                    VacancyRow.scoring_next_attempt_at.is_(None),
                    VacancyRow.scoring_next_attempt_at <= current,
                ),
            )
            .options(selectinload(VacancyRow.profiles))
            .order_by(VacancyRow.published_at.desc())
            .limit(limit)
        )
        async with self.database.session() as session:
            rows = (await session.scalars(statement)).all()
        return [self._vacancy_data(row) for row in rows]

    async def save_assessment(
        self,
        hh_id: str,
        assessment: RelevanceAssessment,
        *,
        threshold: int,
        auto_hide_threshold: int = 0,
    ) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.score = assessment.score
            row.score_reason = assessment.reason
            row.score_matches = assessment.matches
            row.score_gaps = assessment.gaps
            row.scored_description_hash = row.description_hash
            row.scoring_attempts = 0
            row.scoring_next_attempt_at = None
            if row.notification_sent_at is None:
                row.notification_eligible = not row.baseline and assessment.score >= threshold
            auto_hidden = await session.get(AutoHiddenVacancyRow, hh_id)
            should_auto_hide = (
                auto_hide_threshold > 0
                and assessment.score < auto_hide_threshold
            )
            if should_auto_hide and auto_hidden is None:
                session.add(AutoHiddenVacancyRow(hh_id=hh_id))
            elif not should_auto_hide and auto_hidden is not None:
                await session.delete(auto_hidden)
            await session.commit()

    async def defer_scoring(
        self,
        hh_id: str,
        *,
        delay: timedelta,
        now: datetime | None = None,
    ) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.scoring_attempts += 1
            row.scoring_next_attempt_at = (now or _utc_now()) + delay
            await session.commit()

    async def request_rescore(self, hh_id: str) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.scored_description_hash = None
            row.scoring_attempts = 0
            row.scoring_next_attempt_at = None
            await session.commit()

    async def eligible_notifications(self, *, limit: int = 100) -> list[VacancyData]:
        statement = (
            select(VacancyRow)
            .where(
                VacancyRow.notification_eligible.is_(True),
                VacancyRow.notification_sent_at.is_(None),
                VacancyRow.baseline.is_(False),
            )
            .options(selectinload(VacancyRow.profiles))
            .order_by(VacancyRow.published_at.desc())
            .limit(limit)
        )
        async with self.database.session() as session:
            rows = (await session.scalars(statement)).all()
        return [self._vacancy_data(row) for row in rows]

    async def mark_notified(self, hh_id: str, at: datetime | None = None) -> None:
        async with self.database.session() as session:
            row = await session.get(VacancyRow, hh_id)
            if row is None:
                raise KeyError(hh_id)
            row.notification_sent_at = at or _utc_now()
            await session.commit()

    async def save_cover_letter(self, hh_id: str, text: str) -> CoverLetterRow:
        async with self.database.session() as session:
            row = CoverLetterRow(vacancy_id=hh_id, text=text)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_cover_letters(self, hh_id: str) -> list[CoverLetterRow]:
        statement = (
            select(CoverLetterRow)
            .where(CoverLetterRow.vacancy_id == hh_id)
            .order_by(CoverLetterRow.created_at, CoverLetterRow.id)
        )
        async with self.database.session() as session:
            return list((await session.scalars(statement)).all())

    async def latest_cover_letter(self, hh_id: str) -> CoverLetterRow | None:
        statement = (
            select(CoverLetterRow)
            .where(CoverLetterRow.vacancy_id == hh_id)
            .order_by(CoverLetterRow.created_at.desc(), CoverLetterRow.id.desc())
            .limit(1)
        )
        async with self.database.session() as session:
            return await session.scalar(statement)

    async def get_application_attempt(
        self,
        hh_id: str,
    ) -> ApplicationAttemptRow | None:
        async with self.database.session() as session:
            return await session.scalar(
                select(ApplicationAttemptRow).where(
                    ApplicationAttemptRow.vacancy_id == hh_id
                )
            )

    async def begin_application(
        self,
        hh_id: str,
        cover_letter_id: int,
    ) -> ApplicationAttemptRow:
        async with self.database.session() as session:
            letter = await session.get(CoverLetterRow, cover_letter_id)
            if letter is None or letter.vacancy_id != hh_id:
                raise KeyError(cover_letter_id)
            row = await session.scalar(
                select(ApplicationAttemptRow).where(
                    ApplicationAttemptRow.vacancy_id == hh_id
                )
            )
            if row is None:
                row = ApplicationAttemptRow(
                    vacancy_id=hh_id,
                    cover_letter_id=cover_letter_id,
                    status="pending",
                )
                session.add(row)
            elif row.status == "submitted":
                raise ValueError("Отклик на эту вакансию уже отправлен.")
            elif row.status == "pending":
                raise ValueError("Отклик уже выполняется.")
            else:
                row.cover_letter_id = cover_letter_id
                row.status = "pending"
                row.error_text = None
            await session.commit()
            await session.refresh(row)
            return row

    async def finish_application(
        self,
        hh_id: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in {"dry_run_ready", "submitted", "failed"}:
            raise ValueError(status)
        async with self.database.session() as session:
            row = await session.scalar(
                select(ApplicationAttemptRow).where(
                    ApplicationAttemptRow.vacancy_id == hh_id
                )
            )
            if row is None:
                raise KeyError(hh_id)
            row.status = status
            row.error_text = error[:500] if error else None
            await session.commit()

    async def get_setting(self, key: str) -> str | None:
        async with self.database.session() as session:
            row = await session.get(AppSettingRow, key)
            return row.value if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with self.database.session() as session:
            row = await session.get(AppSettingRow, key)
            if row is None:
                session.add(AppSettingRow(key=key, value=value))
            else:
                row.value = value
            await session.commit()

    async def get_threshold(self, *, default: int = 70) -> int:
        raw = await self.get_setting("notification_threshold")
        return int(raw) if raw is not None else default

    async def get_auto_hide_threshold(self, *, default: int = 20) -> int:
        raw = await self.get_setting("auto_hide_threshold")
        return int(raw) if raw is not None else default

    async def reconcile_auto_hidden(self, threshold: int) -> None:
        async with self.database.session() as session:
            await session.execute(delete(AutoHiddenVacancyRow))
            if threshold > 0:
                hh_ids = (
                    await session.scalars(
                        select(VacancyRow.hh_id).where(
                            VacancyRow.score.is_not(None),
                            VacancyRow.score < threshold,
                        )
                    )
                ).all()
                session.add_all(
                    [AutoHiddenVacancyRow(hh_id=hh_id) for hh_id in hh_ids]
                )
            await session.commit()

    async def last_successful_sync(self) -> datetime | None:
        raw = await self.get_setting("last_successful_sync")
        return datetime.fromisoformat(raw) if raw else None

    async def vacancies_due_for_detail_refresh(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
    ) -> list[VacancyData]:
        cutoff = (now or _utc_now()) - timedelta(hours=6)
        statement = (
            select(VacancyRow)
            .where(VacancyRow.details_refreshed_at <= cutoff)
            .options(selectinload(VacancyRow.profiles))
            .order_by(VacancyRow.details_refreshed_at)
            .limit(limit)
        )
        async with self.database.session() as session:
            rows = (await session.scalars(statement)).all()
        return [self._vacancy_data(row) for row in rows]

    @staticmethod
    def _profile_data(row: SearchProfileRow) -> SearchProfileData:
        return SearchProfileData(id=row.id, name=row.name, query=row.query, enabled=row.enabled)

    @staticmethod
    def _vacancy_data(row: VacancyRow) -> VacancyData:
        return VacancyData(
            hh_id=row.hh_id,
            title=row.title,
            company=row.company,
            url=row.url,
            salary_text=row.salary_text,
            area_name=row.area_name,
            experience_name=row.experience_name,
            work_format_text=row.work_format_text,
            published_at=_ensure_utc(row.published_at),
            description=row.description,
            description_hash=row.description_hash,
            details_refreshed_at=_ensure_utc(row.details_refreshed_at),
            discovered_at=_ensure_utc(row.discovered_at),
            profile_names=sorted(profile.name for profile in row.profiles),
            score=row.score,
            score_reason=row.score_reason,
            score_matches=row.score_matches,
            score_gaps=row.score_gaps,
            viewed_at=_ensure_utc(row.viewed_at),
            hidden=row.hidden,
            notification_sent_at=_ensure_utc(row.notification_sent_at),
            baseline=row.baseline,
            notification_eligible=row.notification_eligible,
            scored_description_hash=row.scored_description_hash,
            scoring_attempts=row.scoring_attempts,
            scoring_next_attempt_at=_ensure_utc(row.scoring_next_attempt_at),
        )
