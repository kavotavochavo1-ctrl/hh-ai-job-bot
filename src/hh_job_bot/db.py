from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


vacancy_profiles = Table(
    "vacancy_profiles",
    Base.metadata,
    Column("vacancy_id", ForeignKey("vacancies.hh_id", ondelete="CASCADE"), primary_key=True),
    Column(
        "profile_id",
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class SearchProfileRow(Base):
    __tablename__ = "search_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    query: Mapped[str] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    vacancies: Mapped[list["VacancyRow"]] = relationship(
        secondary=vacancy_profiles,
        back_populates="profiles",
    )


class VacancyRow(Base):
    __tablename__ = "vacancies"

    hh_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    salary_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    experience_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_format_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    description: Mapped[str] = mapped_column(Text)
    description_hash: Mapped[str] = mapped_column(String(64))
    details_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_matches: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    score_gaps: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scored_description_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scoring_attempts: Mapped[int] = mapped_column(Integer, default=0)
    scoring_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    profiles: Mapped[list[SearchProfileRow]] = relationship(
        secondary=vacancy_profiles,
        back_populates="vacancies",
    )
    cover_letters: Mapped[list["CoverLetterRow"]] = relationship(
        back_populates="vacancy",
        cascade="all, delete-orphan",
    )


class AutoHiddenVacancyRow(Base):
    __tablename__ = "auto_hidden_vacancies"

    hh_id: Mapped[str] = mapped_column(
        ForeignKey("vacancies.hh_id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


class CoverLetterRow(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[str] = mapped_column(
        ForeignKey("vacancies.hh_id", ondelete="CASCADE"),
        index=True,
    )
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    vacancy: Mapped[VacancyRow] = relationship(back_populates="cover_letters")


class ApplicationAttemptRow(Base):
    __tablename__ = "application_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vacancy_id: Mapped[str] = mapped_column(
        ForeignKey("vacancies.hh_id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    cover_letter_id: Mapped[int] = mapped_column(
        ForeignKey("cover_letters.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(String(32))
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class AppSettingRow(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("key"),)

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class Database:
    def __init__(self, url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(url)
        self._session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def ping(self) -> bool:
        async with self.engine.connect() as connection:
            return (await connection.scalar(text("SELECT 1"))) == 1
