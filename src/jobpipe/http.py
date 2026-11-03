"""Polite asynchronous HTTP client.

Rules (see docs/decisions.md):

* per-host concurrency cap and a minimum delay between request starts per host;
* retries only for HTTP 429, HTTP 5xx and network/timeout errors, with
  exponential backoff + jitter;
* ``Retry-After`` (seconds or HTTP date) is honoured; a value above
  ``max_retry_after`` is treated as a block;
* a block (HTTP 403, or 429 still returned after the last retry, or too many
  consecutive network failures) stops that host for the rest of the run: every
  later request to it returns immediately with ``outcome == "host_blocked"``.
"""

from __future__ import annotations

import asyncio
import email.utils
import json
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from jobpipe import USER_AGENT

Outcome = Literal["ok", "not_found", "http_error", "network_error", "host_blocked", "bad_json"]

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 520, 521, 522, 523, 524})


@dataclass(slots=True)
class FetchResult:
    url: str
    outcome: Outcome
    status: int | None = None
    data: Any = None
    attempts: int = 0
    elapsed_s: float = 0.0
    bytes: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"


@dataclass(slots=True)
class HostPolicy:
    concurrency: int = 4
    min_interval_s: float = 0.25


@dataclass
class HostStats:
    requests: int = 0
    retries: int = 0
    by_outcome: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    blocked: bool = False
    block_reason: str | None = None
    consecutive_network_errors: int = 0


def parse_retry_after(value: str | None, now: float | None = None) -> float | None:
    """Return the number of seconds to wait, or None if absent/unparseable."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    current = time.time() if now is None else now
    return max(0.0, dt.timestamp() - current)


class PoliteClient:
    """Async JSON GET client enforcing per-host politeness rules."""

    def __init__(
        self,
        *,
        default_policy: HostPolicy | None = None,
        host_policies: dict[str, HostPolicy] | None = None,
        max_retries: int = 4,
        backoff_base_s: float = 2.0,
        max_backoff_s: float = 60.0,
        max_retry_after_s: float = 120.0,
        block_after_network_errors: int = 20,
        timeout_s: float = 30.0,
        user_agent: str = USER_AGENT,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._default = default_policy or HostPolicy()
        self._policies = host_policies or {}
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.max_backoff_s = max_backoff_s
        self.max_retry_after_s = max_retry_after_s
        self.block_after_network_errors = block_after_network_errors
        self._sleep: Any = sleep
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
            transport=transport,
        )
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._next_start: dict[str, float] = defaultdict(float)
        self.stats: dict[str, HostStats] = defaultdict(HostStats)

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _policy(self, host: str) -> HostPolicy:
        return self._policies.get(host, self._default)

    def is_blocked(self, host: str) -> bool:
        return self.stats[host].blocked

    def _block(self, host: str, reason: str) -> None:
        st = self.stats[host]
        if not st.blocked:
            st.blocked = True
            st.block_reason = reason

    async def _wait_turn(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        interval = self._policy(host).min_interval_s
        async with lock:
            now = time.monotonic()
            wait = self._next_start[host] - now
            if wait > 0:
                await self._sleep(wait)
            self._next_start[host] = max(now, self._next_start[host]) + interval

    def _backoff(self, attempt: int) -> float:
        base = min(self.max_backoff_s, self.backoff_base_s * (2 ** (attempt - 1)))
        return float(base * (0.5 + random.random() / 2))  # noqa: S311 - jitter, not crypto

    async def get_json(self, url: str, params: dict[str, str] | None = None) -> FetchResult:
        return await self.get(url, params, as_json=True)

    async def get_text(self, url: str, params: dict[str, str] | None = None) -> FetchResult:
        return await self.get(url, params, as_json=False)

    async def get_bytes(self, url: str, params: dict[str, str] | None = None) -> FetchResult:
        return await self.get(url, params, as_json=False, raw=True)

    async def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        *,
        as_json: bool = True,
        raw: bool = False,
    ) -> FetchResult:
        host = urlsplit(url).hostname or ""
        st = self.stats[host]
        sem = self._sems.setdefault(host, asyncio.Semaphore(self._policy(host).concurrency))
        result = FetchResult(url=url, outcome="network_error")
        started = time.monotonic()
        async with sem:
            for attempt in range(1, self.max_retries + 2):
                if st.blocked:
                    result.outcome = "host_blocked"
                    result.error = st.block_reason
                    break
                await self._wait_turn(host)
                result.attempts = attempt
                st.requests += 1
                retry_wait: float | None = None
                try:
                    resp = await self._client.get(url, params=params)
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    st.consecutive_network_errors += 1
                    result.outcome = "network_error"
                    result.error = f"{type(exc).__name__}: {exc}"[:300]
                    if st.consecutive_network_errors >= self.block_after_network_errors:
                        self._block(host, "too many consecutive network errors")
                        result.outcome = "host_blocked"
                        break
                else:
                    st.consecutive_network_errors = 0
                    result.status = resp.status_code
                    result.bytes = len(resp.content)
                    if resp.status_code == 200 and not as_json:
                        result.data = resp.content if raw else resp.text
                        result.outcome = "ok"
                        break
                    if resp.status_code == 200:
                        try:
                            result.data = resp.json()
                            result.outcome = "ok"
                        except (json.JSONDecodeError, ValueError) as exc:
                            result.outcome = "bad_json"
                            result.error = str(exc)[:300]
                        break
                    if resp.status_code in (404, 410):
                        result.outcome = "not_found"
                        break
                    if resp.status_code == 403:
                        self._block(host, f"HTTP 403 on {url}")
                        result.outcome = "host_blocked"
                        result.error = "HTTP 403"
                        break
                    if resp.status_code not in RETRY_STATUSES:
                        result.outcome = "http_error"
                        result.error = f"HTTP {resp.status_code}"
                        break
                    result.outcome = "http_error"
                    result.error = f"HTTP {resp.status_code}"
                    retry_wait = parse_retry_after(resp.headers.get("Retry-After"))
                    if retry_wait is not None and retry_wait > self.max_retry_after_s:
                        self._block(host, f"Retry-After {retry_wait:.0f}s exceeds cap")
                        result.outcome = "host_blocked"
                        break
                    if resp.status_code == 429 and attempt > self.max_retries:
                        self._block(host, "HTTP 429 after all retries")
                        result.outcome = "host_blocked"
                        break
                if attempt > self.max_retries:
                    break
                st.retries += 1
                await self._sleep(retry_wait if retry_wait is not None else self._backoff(attempt))
        result.elapsed_s = round(time.monotonic() - started, 3)
        st.by_outcome[result.outcome] += 1
        return result

    def stats_summary(self) -> dict[str, dict[str, Any]]:
        return {
            host: {
                "requests": s.requests,
                "retries": s.retries,
                "by_outcome": dict(s.by_outcome),
                "blocked": s.blocked,
                "block_reason": s.block_reason,
            }
            for host, s in sorted(self.stats.items())
        }
