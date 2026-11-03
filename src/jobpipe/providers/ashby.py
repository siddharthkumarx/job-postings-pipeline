"""Ashby Job Postings API (https://developers.ashbyhq.com/docs/public-job-posting-api)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jobpipe.providers.base import ReconJob


class Ashby:
    name = "ashby"
    host = "api.ashbyhq.com"

    def board_url(self, token: str) -> str:
        return f"https://{self.host}/posting-api/job-board/{quote(token, safe='')}"

    def params(self) -> dict[str, str]:
        return {"includeCompensation": "false"}

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
