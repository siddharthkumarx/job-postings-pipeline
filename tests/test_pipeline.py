"""End-to-end daily runs on synthetic data with a fake GitHub Releases API."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from jobpipe import fixtures, fx, ingest, pipeline, publish, state
from tests.test_state import FakeGitHub


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[pipeline.Paths, FakeGitHub]:
    fake = FakeGitHub()
    seeds = tmp_path / "seeds"
    fixtures.write(tmp_path / "unused", seeds, dates=[fixtures.RUN_DATES[0]])

    def fake_ingest(run_date: date, *, boards_csv: Path, data_dir: Path) -> dict[str, object]:
        ingest._atomic_write_table(
            ingest.postings_table(fixtures.postings_for(run_date)),
            ingest.partition_path(data_dir, "postings", run_date),
        )
        ingest._atomic_write_table(
            ingest.board_runs_table(fixtures.board_runs_for(run_date)),
            ingest.partition_path(data_dir, "board_runs", run_date),
        )
        return {"boards": 3, "boards_ok": 3, "postings": 1, "invalid_postings": 0,
                "duration_s": 0.1, "http": {}}  # fmt: skip

    def fake_fx(data_dir: Path) -> dict[str, object]:
        src = tmp_path / "unused" / "bronze" / "fx" / "ecb_eurofxref.parquet"
        dst = fx.fx_path(data_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return {"latest_rate_date": "2026-11-08"}

    monkeypatch.setattr(ingest, "run", fake_ingest)
    monkeypatch.setattr(fx, "fetch", fake_fx)
    monkeypatch.setattr(pipeline, "PIPELINE_START", date(2026, 10, 1))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    return fake, seeds  # type: ignore[return-value]


def _paths(tmp_path: Path, seeds: Path, n: int) -> pipeline.Paths:
    work = tmp_path / f"run{n}"  # fresh container per run: state must come from releases
    return pipeline.Paths(
        data_dir=work / "data", public_dir=tmp_path / "public", site_dir=work / "site",
        seeds_dir=seeds, duckdb=work / "data" / "warehouse.duckdb",
    )  # fmt: skip


def test_daily_runs_restore_state_and_publish(tmp_path: Path, env: tuple[FakeGitHub, Path]) -> None:
    fake, seeds = env
    gh = state.GitHubReleases("o/r", "t", transport=httpx.MockTransport(fake.handler), retries=0)
    outcomes = []
    for n, d in enumerate(fixtures.RUN_DATES):
        outcomes.append(pipeline.daily(d, _paths(tmp_path, seeds, n), gh))
    statuses = [o.status for o in outcomes]
    errors = [o.entry.get("error") or o.entry.get("hold_reasons") for o in outcomes]
    # day 5 (index 4): Lever board fails -> 2 of 3 boards OK (< 90 %) -> held
    assert statuses == ["published"] * 4 + ["held", "published"], errors
    assert any("boards fetched OK 2/3" in r for r in outcomes[4].entry["hold_reasons"])

    runs = publish.read_runs(tmp_path / "public" / "runs.jsonl")
    assert [r["run_date"] for r in runs] == [d.isoformat() for d in fixtures.RUN_DATES]
    st = publish.status(runs, today=fixtures.RUN_DATES[-1])
    assert st["runs_held"] == 1
    assert st["days_running"] == 10  # 2026-10-26 .. 2026-11-04
    assert st["missed_runs"] == 10 - 5  # calendar days without a published run
    assert (tmp_path / "public" / "summary" / "salary_bands.csv").exists()
    assert (tmp_path / "run5" / "site" / "index.html").exists()

    # state: warehouse snapshot and bronze for every run date (held day included)
    assert gh.find("state", "warehouse.duckdb.gz") is not None
    assert len(state.bronze_dates(gh, ["2026-10", "2026-11"])) == 6

    # idempotent re-run of the last day replaces, not duplicates, the ledger entry
    again = pipeline.daily(fixtures.RUN_DATES[-1], _paths(tmp_path, seeds, 9), gh)
    assert again.status == "published", again.entry
    assert len(publish.read_runs(tmp_path / "public" / "runs.jsonl")) == 6


def test_rebuild_from_bronze_when_snapshot_missing(
    tmp_path: Path, env: tuple[FakeGitHub, Path]
) -> None:
    fake, seeds = env
    gh = state.GitHubReleases("o/r", "t", transport=httpx.MockTransport(fake.handler), retries=0)
    for n, d in enumerate(fixtures.RUN_DATES[:3]):
        assert pipeline.daily(d, _paths(tmp_path, seeds, n), gh).status == "published"
    # lose the warehouse snapshot: the next run must rebuild from bronze assets
    snap = gh.find("state", "warehouse.duckdb.gz")
    assert snap is not None
    fake.assets.pop(snap.id)
    out = pipeline.daily(fixtures.RUN_DATES[3], _paths(tmp_path, seeds, 7), gh)
    assert out.status == "published", out.entry
    assert out.entry["open_postings"] >= 6
