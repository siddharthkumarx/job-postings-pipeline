from datetime import date
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest

from jobpipe import ingest
from jobpipe.http import HostPolicy, PoliteClient

GH = {
    "jobs": [
        {
            "id": 1,
            "title": "Senior Data Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "New York, NY"},
            "updated_at": "2026-11-01T10:00:00-04:00",
            "first_published": "2026-10-01T10:00:00-04:00",
            "requisition_id": "R1",
            "company_name": "Acme",
            "metadata": [{"id": 9, "name": "Recruiter", "value": "Jane Doe"}],
            "departments": [{"id": 1, "name": "Data"}],
            "offices": [],
            "content": "&lt;p&gt;Hybrid. Pay $150,000 - $190,000. Contact jane@acme.com&lt;/p&gt;",
        },
        {"id": 2, "title": "", "absolute_url": "https://x.example/2"},  # invalid: empty title
    ]
}
LEVER = [
    {
        "id": "abc",
        "text": "Analytics Engineer",
        "hostedUrl": "https://jobs.lever.co/beta/abc",
        "categories": {"location": "Remote - US", "commitment": "Full-time", "team": "Data"},
        "country": "US",
        "workplaceType": "remote",
        "createdAt": 1761955200000,
        "salaryRange": {"currency": "USD", "interval": "per-year-salary", "min": 1, "max": 2},
        "descriptionPlain": "5+ years of experience",
    }
]


def handler(req: httpx.Request) -> httpx.Response:
    if req.url.host == "boards-api.greenhouse.io":
        assert req.url.params["content"] == "true"
        return httpx.Response(200, json=GH)
    if req.url.host == "api.lever.co":
        return httpx.Response(200, json=LEVER)
    return httpx.Response(404)


def test_ingest_writes_bronze_without_free_text(tmp_path: Path) -> None:
    boards = tmp_path / "boards.csv"
    boards.write_text(
        "provider,board,company\ngreenhouse,acme,Acme\nlever,beta,Beta\nashby,gone,Gone\n"
    )

    async def nosleep(_: float) -> None:
        return None

    client = PoliteClient(
        transport=httpx.MockTransport(handler),
        default_policy=HostPolicy(concurrency=2, min_interval_s=0),
        sleep=nosleep,
    )
    d = date(2026, 11, 4)
    m = ingest.run(d, boards_csv=boards, data_dir=tmp_path, client=client)
    assert m["postings"] == 2
    assert m["invalid_postings"] == 1
    assert m["board_status"] == {"ashby:not_found": 1, "greenhouse:ok": 1, "lever:ok": 1}

    t = pq.read_table(ingest.partition_path(tmp_path, "postings", d)).to_pylist()
    gh = next(r for r in t if r["provider"] == "greenhouse")
    assert gh["desc_salary_min"] == 150000 and gh["desc_remote_hint"] == "hybrid"
    assert gh["department"] == "Data" and gh["location_raw"] == "New York, NY"
    lv = next(r for r in t if r["provider"] == "lever")
    assert lv["api_salary_period"] == "year" and lv["desc_seniority_hint"] == "senior"
    blob = repr(t)  # every decoded value (Parquet bytes are compressed)
    for forbidden in ("Jane", "jane@acme.com", "Contact", "5+ years", "Recruiter"):
        assert forbidden not in blob

    runs = pq.read_table(ingest.partition_path(tmp_path, "board_runs", d)).to_pylist()
    assert {r["status"] for r in runs} == {"ok", "not_found"}


def test_parse_failure_fails_the_board_not_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boards = tmp_path / "boards.csv"
    boards.write_text("provider,board,company\ngreenhouse,acme,Acme\nlever,beta,Beta\n")
    real = ingest.to_postings

    def flaky(provider, payload, ctx):  # type: ignore[no-untyped-def]
        if provider.name == "greenhouse":
            raise ValueError("could not convert string to float: '140.000.00'")
        return real(provider, payload, ctx)

    monkeypatch.setattr(ingest, "to_postings", flaky)

    async def nosleep(_: float) -> None:
        return None

    client = PoliteClient(
        transport=httpx.MockTransport(handler),
        default_policy=HostPolicy(concurrency=2, min_interval_s=0),
        sleep=nosleep,
    )
    m = ingest.run(date(2026, 11, 4), boards_csv=boards, data_dir=tmp_path, client=client)
    assert m["board_status"] == {"greenhouse:error": 1, "lever:ok": 1}
    assert m["postings"] == 1
