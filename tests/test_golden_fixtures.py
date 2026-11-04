"""Golden fixtures: sanitised real API responses per provider (tests/fixtures/<provider>/).

Captured by the `capture-fixtures` live check; descriptions were replaced with
synthetic text and Greenhouse metadata removed before the files were committed.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from jobpipe.checks import SYNTHETIC_DESCRIPTION
from jobpipe.providers import get_provider
from jobpipe.providers.base import RunContext, to_postings

FIXTURES = sorted(Path("tests/fixtures").glob("*/*.json"))
PROVIDERS = {"greenhouse", "lever", "ashby"}


def test_every_provider_has_a_golden_fixture() -> None:
    assert {p.parent.name for p in FIXTURES} >= PROVIDERS


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_parses_into_valid_postings(path: Path) -> None:
    provider = get_provider(path.parent.name)
    payload = json.loads(path.read_text())
    jobs = provider.jobs(payload)
    assert jobs, "fixture has no jobs"
    ctx = RunContext(path.stem, date(2026, 11, 4), datetime(2026, 11, 4, 7, 41, tzinfo=UTC))
    postings, errors = to_postings(provider, payload, ctx)
    assert not errors
    assert len(postings) == len(jobs)
    for p in postings:
        assert p.title and str(p.job_url).startswith("https://")
        # the synthetic description drives the in-memory extraction
        assert p.desc_salary_min == 120000 and p.desc_salary_max == 150000
        assert p.desc_remote_hint == "hybrid"
        assert p.desc_seniority_hint == "senior"
        assert p.description_sha256 is not None
    dumped = repr([p.model_dump() for p in postings])
    assert SYNTHETIC_DESCRIPTION not in dumped


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_is_sanitised(path: Path) -> None:
    text = path.read_text()
    for key in ('"descriptionHtml"', '"description"', '"additional"', '"opening"'):
        assert key not in text
    payload = json.loads(text)
    jobs = get_provider(path.parent.name).jobs(payload)
    for job in jobs:
        for field in ("content", "descriptionPlain"):
            if field in job:
                assert job[field] == SYNTHETIC_DESCRIPTION
        assert not job.get("metadata")
