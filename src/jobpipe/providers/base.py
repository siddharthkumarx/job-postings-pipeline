"""Common provider interface and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from pydantic import ValidationError

from jobpipe.extract import analyse
from jobpipe.models import Posting


@dataclass(slots=True)
class ReconJob:
    """Minimal per-job view used by recon (no free text, no personal data)."""

    title: str
    locations: list[str] = field(default_factory=list)
    country_hints: list[str] = field(default_factory=list)
    workplace: str | None = None
    department: str | None = None


@dataclass(slots=True)
class RunContext:
    board: str
    run_date: date
    fetched_at: datetime


class Provider(Protocol):
    name: str
    host: str

    def board_url(self, token: str) -> str: ...

    def params(self) -> dict[str, str]: ...

    def ingest_params(self) -> dict[str, str]: ...

    def jobs(self, payload: Any) -> list[dict[str, Any]]: ...

    def company_name(self, payload: Any) -> str | None: ...

    def recon_job(self, job: dict[str, Any]) -> ReconJob: ...

    def posting_fields(self, job: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Allowlisted API fields for a Posting, and the description text (in memory only)."""
        ...


def s(value: Any) -> str | None:
    """Clean optional string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):  # epoch milliseconds (Lever)
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def to_postings(
    provider: Provider, payload: Any, ctx: RunContext
) -> tuple[list[Posting], list[str]]:
    """Build validated Postings; returns (postings, error messages for invalid jobs)."""
    postings: list[Posting] = []
    errors: list[str] = []
    seen: set[str] = set()
    for job in provider.jobs(payload):
        try:
            fields, description = provider.posting_fields(job)
            facts = analyse(description)
        except Exception as exc:  # one malformed job must not drop the board
            errors.append(f"{job.get('id')}: {type(exc).__name__}: {exc}"[:200])
            continue
        description = None  # never kept beyond this point
        sal = facts.salary
        fields.update(
            board=ctx.board,
            run_date=ctx.run_date,
            fetched_at=ctx.fetched_at,
            desc_salary_min=sal.min if sal else None,
            desc_salary_max=sal.max if sal else None,
            desc_salary_currency=sal.currency if sal else None,
            desc_salary_period=sal.period if sal else None,
            desc_remote_hint=facts.remote_hint,
            desc_seniority_hint=facts.seniority_hint,
            description_sha256=facts.sha256,
            description_chars=facts.chars,
        )
        try:
            posting = Posting(provider=provider.name, **fields)  # type: ignore[arg-type]
        except ValidationError as exc:
            first = exc.errors()[0]
            errors.append(f"{fields.get('posting_id')}: {first['loc']} {first['msg']}"[:200])
            continue
        if posting.posting_id in seen:
            continue
        seen.add(posting.posting_id)
        postings.append(posting)
    return postings, errors
