"""Everything the README and the visuals show, loaded from real run outputs.

Sources: ``public/status.json``, ``public/runs.jsonl``, ``public/summary/*`` (written by
the daily run), ``docs/incidents.md`` and ``seeds/boards.csv``. Nothing here is typed in
by hand; if a file is missing the README simply leaves that line out.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEDULE_UTC = (7, 41)  # .github/workflows/daily.yml: cron "41 7 * * *"

ROLE_LABELS = {
    "data_engineer": "Data engineer", "analytics_engineer": "Analytics engineer",
    "data_analyst": "Data analyst", "ml_engineer": "ML engineer",
    "software_engineer": "Software engineer", "data_scientist": "Data scientist",
}  # fmt: skip


@dataclass
class Incident:
    date: str
    title: str
    run: str
    plain: str
    fix_plain: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ReadmeData:
    status: dict[str, Any]
    last_run: dict[str, Any]
    runs: list[dict[str, Any]]
    sample: list[dict[str, str]]
    changes: list[dict[str, str]]
    quality: dict[str, Any]
    example: dict[str, Any]
    data_roles: list[dict[str, Any]]
    providers: list[dict[str, str]]
    incidents: list[Incident]
    boards_by_provider: dict[str, int]

    @property
    def companies(self) -> int:
        return int(self.status.get("companies_tracked") or sum(self.boards_by_provider.values()))

    @property
    def open_jobs(self) -> int:
        return int(self.status.get("jobs_tracked") or 0)

    @property
    def run_date(self) -> str:
        return str(self.status.get("last_published") or self.status.get("last_run") or "")

    @property
    def minutes(self) -> float:
        return round(float(self.last_run.get("duration_s") or 0) / 60, 1)

    @property
    def runs_delivered(self) -> tuple[int, int]:
        """(days with published data, days since the first run), from status.json."""
        return int(self.status.get("runs_published") or 0), int(
            self.status.get("days_running") or 0
        )

    @property
    def hf_uploaded(self) -> bool:
        """True only when the latest published run really uploaded to Hugging Face."""
        notes = self.last_run.get("notes") or []
        return any(n.startswith("hf ") and "skipped" not in n for n in notes)

    def start_delays(self, last: int = 14) -> list[float]:
        return start_delays(self.runs, last)

    def schedule_note(self, last: int = 14) -> dict[str, Any]:
        return schedule_note(self.runs, last)


def start_delays(runs: list[dict[str, Any]], last: int = 14) -> list[float]:
    """Hours between the scheduled 07:41 UTC and the start of each day's final run.

    Read from ``started_at`` in the run log, for the last ``last`` run dates whose final
    run started on its own run date.
    """
    final: dict[str, dict[str, Any]] = {}
    for r in runs:
        if r.get("run_date") and r.get("started_at"):
            final[r["run_date"]] = r
    hours: list[float] = []
    for run_date in sorted(final)[-last:]:
        started = datetime.fromisoformat(final[run_date]["started_at"]).astimezone(UTC)
        due = datetime.fromisoformat(run_date).replace(
            hour=SCHEDULE_UTC[0], minute=SCHEDULE_UTC[1], tzinfo=UTC
        )
        if started.date().isoformat() == run_date:
            hours.append(max(0.0, (started - due).total_seconds() / 3600))
    return hours


def schedule_note(runs: list[dict[str, Any]], last: int = 14) -> dict[str, Any]:
    """Start delay of the scheduled run over the last ``last`` days, in hours."""
    h = start_delays(runs, last)
    if not h:
        return {}
    return {
        "runs": len(h),
        "late": sum(x > 0.25 for x in h),
        "min_h": round(min(h), 1),
        "median_h": round(statistics.median(h), 1),
        "max_h": round(max(h), 1),
    }


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


def parse_incidents(path: Path) -> list[Incident]:
    if not path.exists():
        return []
    out: list[Incident] = []
    for block in re.split(r"^### ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        date, _, title = head.partition(" · ")
        fields = {
            m.group(1): m.group(2).strip()
            for m in re.finditer(r"^- \*\*(.+?):\*\* (.+)$", body, flags=re.M)
        }
        out.append(
            Incident(
                date=date.strip(),
                title=title.strip(),
                run=fields.get("Run / check", ""),
                plain=fields.get("In plain words", ""),
                fix_plain=fields.get("Fix in plain words", ""),
                fields=fields,
            )
        )
    return out


def load(root: Path = Path(".")) -> ReadmeData:
    public = root / "public"
    runs = [
        json.loads(line)
        for line in (public / "runs.jsonl").read_text().splitlines()
        if line.strip()
    ] if (public / "runs.jsonl").exists() else []  # fmt: skip
    published = [r for r in runs if r.get("status") == "published"]
    boards = _csv(root / "seeds" / "boards.csv")
    by_provider: dict[str, int] = {}
    for b in boards:
        by_provider[b["provider"]] = by_provider.get(b["provider"], 0) + 1
    return ReadmeData(
        status=_json(public / "status.json", {}),
        last_run=published[-1] if published else {},
        runs=runs,
        sample=_csv(public / "summary" / "sample_postings.csv"),
        changes=_csv(public / "summary" / "changes_today.csv"),
        quality=_json(public / "summary" / "quality.json", {}),
        example=_json(public / "summary" / "example_posting.json", {}),
        data_roles=_json(public / "summary" / "data_roles.json", []),
        providers=_csv(public / "summary" / "providers.csv"),
        incidents=parse_incidents(root / "docs" / "incidents.md"),
        boards_by_provider=by_provider,
    )


def short_title(row: dict[str, str], limit: int = 26) -> str:
    """A short role label for visuals: the role family when known, else a trimmed title."""
    if row.get("role_family") in ROLE_LABELS:
        return ROLE_LABELS[row["role_family"]]
    t = re.split(r"[,(–—-]| - ", row.get("title", ""))[0].strip()
    t = re.sub(r"^(Sr\.?|Senior)\s+", "Senior ", t)
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"
