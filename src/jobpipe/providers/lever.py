"""Lever Postings API (https://github.com/lever/postings-api)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jobpipe.providers.base import ReconJob


class Lever:
    name = "lever"
    host = "api.lever.co"

    def board_url(self, token: str) -> str:
        return f"https://{self.host}/v0/postings/{quote(token, safe='')}"

    def params(self) -> dict[str, str]:
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
