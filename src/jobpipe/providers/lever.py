"""Lever Postings API (https://github.com/lever/postings-api)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jobpipe.providers.base import ReconJob, parse_ts
from jobpipe.providers.base import s as clean

LEVER_PERIODS = {
    "per-year-salary": "year",
    "per-month-salary": "month",
    "per-week-salary": "week",
    "per-day-wage": "day",
    "per-hour-wage": "hour",
}


class Lever:
    name = "lever"
    host = "api.lever.co"

    def board_url(self, token: str) -> str:
        return f"https://{self.host}/v0/postings/{quote(token, safe='')}"

    def params(self) -> dict[str, str]:
        return {"mode": "json"}

    def ingest_params(self) -> dict[str, str]:
        return {"mode": "json"}

    def jobs(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            return []
        return [j for j in payload if isinstance(j, dict)]

    def company_name(self, payload: Any) -> str | None:
        return None  # The Postings API does not expose the company name.

    def recon_job(self, job: dict[str, Any]) -> ReconJob:
        cats = job.get("categories") or {}
        locations: list[str] = []
        if cats.get("location"):
            locations.append(str(cats["location"]))
        for loc in cats.get("allLocations") or []:
            if loc and loc not in locations:
                locations.append(str(loc))
        hints = [str(job["country"])] if job.get("country") else []
        return ReconJob(
            title=str(job.get("text") or ""),
            locations=locations,
            country_hints=hints,
            workplace=job.get("workplaceType"),
            department=cats.get("department") or cats.get("team"),
        )

    def posting_fields(self, job: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        rj = self.recon_job(job)
        cats = job.get("categories") or {}
        sal = job.get("salaryRange") or {}
        period = LEVER_PERIODS.get(str(sal.get("interval") or ""))
        has_sal = period is not None and sal.get("min") is not None
        fields: dict[str, Any] = {
            "posting_id": str(job.get("id") or ""),
            "title": clean(job.get("text")) or "",
            "department": clean(cats.get("department")),
            "team": clean(cats.get("team")),
            "location_raw": rj.locations[0] if rj.locations else None,
            "locations_all": rj.locations,
            "workplace_type_raw": clean(job.get("workplaceType")),
            "employment_type": clean(cats.get("commitment")),
            "country_hint": clean(job.get("country")),
            "published_at": parse_ts(job.get("createdAt")),
            "job_url": job.get("hostedUrl"),
            "api_salary_min": sal.get("min") if has_sal else None,
            "api_salary_max": sal.get("max") if has_sal else None,
            "api_salary_currency": clean(sal.get("currency")) if has_sal else None,
            "api_salary_period": period if has_sal else None,
        }
        parts = [str(job.get("descriptionPlain") or job.get("description") or "")]
        for item in job.get("lists") or []:
            if isinstance(item, dict):
                parts.append(f"{item.get('text') or ''} {item.get('content') or ''}")
        parts.append(str(job.get("additionalPlain") or job.get("additional") or ""))
        return fields, " ".join(p for p in parts if p)
