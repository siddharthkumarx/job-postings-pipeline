"""Greenhouse Job Board API (https://docs.greenhouse.io/job-board.html)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jobpipe.providers.base import ReconJob, parse_ts
from jobpipe.providers.base import s as clean


class Greenhouse:
    name = "greenhouse"
    host = "boards-api.greenhouse.io"

    def board_url(self, token: str) -> str:
        return f"https://{self.host}/v1/boards/{quote(token, safe='')}/jobs"

    def params(self) -> dict[str, str]:
        # Recon does not need descriptions; the daily ingest asks for content=true.
        return {}

    def ingest_params(self) -> dict[str, str]:
        return {"content": "true"}

    def jobs(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        jobs = payload.get("jobs") or []
        return [j for j in jobs if isinstance(j, dict)]

    def company_name(self, payload: Any) -> str | None:
        for job in self.jobs(payload):
            name = job.get("company_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    def recon_job(self, job: dict[str, Any]) -> ReconJob:
        loc = (job.get("location") or {}).get("name") or ""
        locations = [loc] if loc else []
        for office in job.get("offices") or []:
            if isinstance(office, dict):
                for key in ("location", "name"):
                    if office.get(key):
                        locations.append(str(office[key]))
                        break
        dept = None
        depts = job.get("departments") or []
        if depts and isinstance(depts[0], dict):
            dept = depts[0].get("name")
        return ReconJob(title=str(job.get("title") or ""), locations=locations, department=dept)

    def posting_fields(self, job: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        rj = self.recon_job(job)
        depts = [d.get("name") for d in job.get("departments") or [] if isinstance(d, dict)]
        fields: dict[str, Any] = {
            "posting_id": str(job.get("id") or ""),
            "requisition_id": clean(job.get("requisition_id")),
            "title": clean(job.get("title")) or "",
            "department": clean(depts[0]) if depts else None,
            "location_raw": rj.locations[0] if rj.locations else None,
            "locations_all": rj.locations,
            "published_at": parse_ts(job.get("first_published")),
            "updated_at": parse_ts(job.get("updated_at")),
            "job_url": job.get("absolute_url"),
        }
        # `metadata` (employer-defined custom fields) is deliberately not read.
        return fields, job.get("content")
