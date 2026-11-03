"""Common provider interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ReconJob:
    """Minimal per-job view used by recon (no free text, no personal data)."""

    title: str
    locations: list[str] = field(default_factory=list)
    country_hints: list[str] = field(default_factory=list)
    workplace: str | None = None
    department: str | None = None


class Provider(Protocol):
    name: str
    host: str

    def board_url(self, token: str) -> str: ...

    def params(self) -> dict[str, str]: ...

    def jobs(self, payload: Any) -> list[dict[str, Any]]: ...

    def company_name(self, payload: Any) -> str | None: ...

    def recon_job(self, job: dict[str, Any]) -> ReconJob: ...
