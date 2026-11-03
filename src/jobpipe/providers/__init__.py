"""Provider adapters for the official public job-board APIs."""

from __future__ import annotations

from jobpipe.providers.base import Provider, ReconJob
from jobpipe.providers.registry import PROVIDERS, get_provider

__all__ = ["PROVIDERS", "Provider", "ReconJob", "get_provider"]
