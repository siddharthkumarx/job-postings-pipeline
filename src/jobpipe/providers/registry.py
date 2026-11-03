"""Provider registry."""

from __future__ import annotations

from jobpipe.providers.ashby import Ashby
from jobpipe.providers.base import Provider
from jobpipe.providers.greenhouse import Greenhouse
from jobpipe.providers.lever import Lever

PROVIDERS: dict[str, Provider] = {p.name: p for p in (Greenhouse(), Lever(), Ashby())}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"unknown provider {name!r}; expected one of {sorted(PROVIDERS)}"
        ) from None
