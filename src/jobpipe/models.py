"""Bronze record: the only shape of a posting that is ever written to disk.

No free text (descriptions) and no personal fields. Derived fields extracted in
memory from the description are prefixed ``desc_``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

SCHEMA_VERSION = 1

ProviderName = Literal["greenhouse", "lever", "ashby"]
SalaryPeriod = Literal["year", "month", "week", "day", "hour"]


class Posting(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider: ProviderName
    board: str = Field(min_length=1, max_length=120)
    posting_id: str = Field(min_length=1, max_length=120)
    requisition_id: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    department: str | None = Field(default=None, max_length=200)
    team: str | None = Field(default=None, max_length=200)
    location_raw: str | None = Field(default=None, max_length=500)
    locations_all: list[str] = Field(default_factory=list)
    workplace_type_raw: str | None = Field(default=None, max_length=50)
    employment_type: str | None = Field(default=None, max_length=50)
    country_hint: str | None = Field(default=None, max_length=60)
    is_listed: bool = True
    published_at: datetime | None = None
    updated_at: datetime | None = None
    job_url: HttpUrl
    api_salary_min: float | None = Field(default=None, ge=0)
    api_salary_max: float | None = Field(default=None, ge=0)
    api_salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    api_salary_period: SalaryPeriod | None = None
    desc_salary_min: float | None = Field(default=None, ge=0)
    desc_salary_max: float | None = Field(default=None, ge=0)
    desc_salary_currency: str | None = Field(default=None, min_length=3, max_length=3)
    desc_salary_period: SalaryPeriod | None = None
    desc_remote_hint: Literal["remote", "hybrid", "onsite"] | None = None
    desc_seniority_hint: str | None = Field(default=None, max_length=30)
    description_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    description_chars: int | None = Field(default=None, ge=0)
    run_date: date
    fetched_at: datetime
    schema_version: int = SCHEMA_VERSION

    @field_validator("locations_all")
    @classmethod
    def _cap_locations(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for loc in v:
            loc = loc.strip()[:200]
            if loc and loc not in out:
                out.append(loc)
        return out[:25]

    @field_validator("api_salary_currency", "desc_salary_currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


# Arrow/Parquet column order and types for bronze postings.
PARQUET_FIELDS: list[tuple[str, str]] = [
    ("provider", "string"), ("board", "string"), ("posting_id", "string"),
    ("requisition_id", "string"), ("title", "string"), ("department", "string"),
    ("team", "string"), ("location_raw", "string"), ("locations_all", "list<string>"),
    ("workplace_type_raw", "string"), ("employment_type", "string"), ("country_hint", "string"),
    ("is_listed", "bool"), ("published_at", "timestamp"), ("updated_at", "timestamp"),
    ("job_url", "string"), ("api_salary_min", "double"), ("api_salary_max", "double"),
    ("api_salary_currency", "string"), ("api_salary_period", "string"),
    ("desc_salary_min", "double"), ("desc_salary_max", "double"),
    ("desc_salary_currency", "string"), ("desc_salary_period", "string"),
    ("desc_remote_hint", "string"), ("desc_seniority_hint", "string"),
    ("description_sha256", "string"), ("description_chars", "int32"), ("run_date", "date"),
    ("fetched_at", "timestamp"), ("schema_version", "int16"),
]  # fmt: skip


class BoardRun(BaseModel):
    """One row per board per run: did the fetch work, how many postings, how long."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ProviderName
    board: str
    run_date: date
    status: Literal["ok", "not_found", "error", "blocked", "skipped"]
    http_status: int | None = None
    postings: int = 0
    invalid_postings: int = 0
    attempts: int = 0
    elapsed_s: float = 0.0
    bytes: int = 0
    error: str | None = None
    fetched_at: datetime
