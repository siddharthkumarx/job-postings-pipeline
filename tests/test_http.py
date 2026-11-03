import asyncio

import httpx
import pytest

from jobpipe.http import HostPolicy, PoliteClient, parse_retry_after


async def _noop_sleep(_: float) -> None:
    return None


def _client(handler: object, **kw: object) -> PoliteClient:
    return PoliteClient(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        default_policy=HostPolicy(concurrency=2, min_interval_s=0.0),
        sleep=_noop_sleep,
        **kw,  # type: ignore[arg-type]
    )


def test_parse_retry_after() -> None:
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("garbage") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412480.0 - 10) == 10.0


def test_retries_5xx_then_ok() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"jobs": []})

    async def go() -> None:
        async with _client(handler) as c:
            r = await c.get_json("https://h.example/x")
            assert r.ok and r.attempts == 3 and r.data == {"jobs": []}

    asyncio.run(go())


def test_404_not_retried() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    async def go() -> None:
        async with _client(handler) as c:
            r = await c.get_json("https://h.example/x")
            assert r.outcome == "not_found" and calls["n"] == 1

    asyncio.run(go())


def test_400_not_retried() -> None:
    async def go() -> None:
        async with _client(lambda req: httpx.Response(400)) as c:
            r = await c.get_json("https://h.example/x")
            assert r.outcome == "http_error" and r.attempts == 1

    asyncio.run(go())


def test_403_blocks_host_for_run() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(403)

    async def go() -> None:
        async with _client(handler) as c:
            r1 = await c.get_json("https://h.example/a")
            r2 = await c.get_json("https://h.example/b")
            other = await c.get_json("https://other.example/a")
            assert r1.outcome == "host_blocked"
            assert r2.outcome == "host_blocked" and r2.attempts == 0
            assert other.outcome == "host_blocked"  # other host also returned 403
            assert calls["n"] == 2

    asyncio.run(go())


def test_429_exhausted_blocks_and_honours_retry_after() -> None:
    waits: list[float] = []

    async def rec_sleep(s: float) -> None:
        waits.append(s)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7"})

    async def go() -> None:
        c = PoliteClient(
            transport=httpx.MockTransport(handler),
            default_policy=HostPolicy(concurrency=1, min_interval_s=0.0),
            sleep=rec_sleep,
            max_retries=2,
        )
        async with c:
            r = await c.get_json("https://h.example/a")
            assert r.outcome == "host_blocked"
            assert r.attempts == 3
            assert waits.count(7.0) == 2
            assert c.is_blocked("h.example")

    asyncio.run(go())


def test_retry_after_above_cap_blocks() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"Retry-After": "3600"})

    async def go() -> None:
        async with _client(handler, max_retry_after_s=60.0) as c:
            r = await c.get_json("https://h.example/a")
            assert r.outcome == "host_blocked" and r.attempts == 1

    asyncio.run(go())


def test_network_errors_retried() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=[])

    async def go() -> None:
        async with _client(handler) as c:
            r = await c.get_json("https://h.example/a")
            assert r.ok and r.attempts == 2

    asyncio.run(go())


@pytest.mark.parametrize("text", [True, False])
def test_text_mode(text: bool) -> None:
    async def go() -> None:
        async with _client(lambda req: httpx.Response(200, text='{"a": 1}')) as c:
            r = await (c.get_text if text else c.get_json)("https://h.example/a")
            assert r.data == ('{"a": 1}' if text else {"a": 1})

    asyncio.run(go())
