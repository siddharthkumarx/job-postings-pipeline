"""Ashby Job Postings API (https://developers.ashbyhq.com/docs/public-job-posting-api)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jobpipe.providers.base import ReconJob, parse_ts
from jobpipe.providers.base import s as clean

ASHBY_PERIODS = {
    "1 YEAR": "year",
    "1 MONTH": "month",
    "1 WEEK": "week",
    "1 DAY": "day",
    "1 HOUR": "hour",
}


class Ashby:
    name = "ashby"
    host = "api.ashbyhq.com"

    def board_url(self, token: str) -> str:
        return f"https://{self.host}/posting-api/job-board/{quote(token, safe='')}"

    def params(self) -> dict[str, str]:
        return {"includeCompensation": "false"}

    def ingest_params(self) -> dict[str, str]:
        return {"includeCompensation": "true"}

    def jobs(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        jobs = payload.get("jobs") or []
        # Unlisted postings are reachable only by direct link; they are not on the board.
        return [j for j in jobs if isinstance(j, dict) and j.get("isListed", True)]

    def company_name(self, payload: Any) -> str | None:
        return None  # The Posting API does not expose the organisation name.

    def recon_job(self, job: dict[str, Any]) -> ReconJob:
        locations: list[str] = []
        hints: list[str] = []
        if job.get("location"):
            locations.append(str(job["location"]))
        addr = ((job.get("address") or {}).get("postalAddress")) or {}
        if addr.get("addressCountry"):
            hints.append(str(addr["addressCountry"]))
        for sec in job.get("secondaryLocations") or []:
            if not isinstance(sec, dict):
                continue
            if sec.get("location"):
                locations.append(str(sec["location"]))
            country = (sec.get("address") or {}).get("addressCountry")
            if country:
                hints.append(str(country))
        return ReconJob(
            title=str(job.get("title") or ""),
            locations=locations,
            country_hints=hints,
            workplace=job.get("workplaceType"),
            department=job.get("department"),
        )

    def posting_fields(self, job: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        rj = self.recon_job(job)
        salary: dict[str, Any] = {}
        comp = job.get("compensation") or {}
        for comp_part in comp.get("summaryComponents") or []:
            if not isinstance(comp_part, dict) or comp_part.get("compensationType") != "Salary":
                continue
            period = ASHBY_PERIODS.get(str(comp_part.get("interval") or "").upper())
            if period and comp_part.get("minValue") is not None and comp_part.get("currencyCode"):
                salary = {
                    "api_salary_min": comp_part.get("minValue"),
                    "api_salary_max": comp_part.get("maxValue") or comp_part.get("minValue"),
                    "api_salary_currency": comp_part.get("currencyCode"),
                    "api_salary_period": period,
                }
                break
        fields: dict[str, Any] = {
            "posting_id": str(job.get("id") or ""),
            "title": clean(job.get("title")) or "",
            "department": clean(job.get("department")),
            "team": clean(job.get("team")),
            "location_raw": rj.locations[0] if rj.locations else None,
            "locations_all": rj.locations,
            "workplace_type_raw": clean(job.get("workplaceType")),
            "employment_type": clean(job.get("employmentType")),
            "country_hint": rj.country_hints[0] if rj.country_hints else None,
            "is_listed": bool(job.get("isListed", True)),
            "published_at": parse_ts(job.get("publishedAt")),
            "job_url": job.get("jobUrl"),
            **salary,
        }
        return fields, job.get("descriptionPlain") or job.get("descriptionHtml")
