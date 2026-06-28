from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

NonEmptyText = Annotated[str, Field(min_length=1)]


@dataclass(frozen=True, slots=True)
class SearchProfileData:
    id: int
    name: str
    query: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class VacancyData:
    hh_id: str
    title: str
    company: str
    url: str
    published_at: datetime
    description: str
    description_hash: str
    details_refreshed_at: datetime | None = None
    discovered_at: datetime | None = None
    salary_text: str | None = None
    area_name: str | None = None
    experience_name: str | None = None
    work_format_text: str | None = None
    profile_names: list[str] = field(default_factory=list)
    score: int | None = None
    score_reason: str | None = None
    score_matches: list[str] | None = None
    score_gaps: list[str] | None = None
    viewed_at: datetime | None = None
    hidden: bool = False
    notification_sent_at: datetime | None = None
    baseline: bool = False
    notification_eligible: bool | None = None
    scored_description_hash: str | None = None
    scoring_attempts: int = 0
    scoring_next_attempt_at: datetime | None = None


class RelevanceAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    matches: list[NonEmptyText]
    gaps: list[NonEmptyText]
    reason: NonEmptyText
