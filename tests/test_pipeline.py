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
    # only the first run builds from scratch; later runs restore a complete snapshot
    rebuilt = [any("rebuilt warehouse" in n for n in o.entry["notes"]) for o in outcomes]
    assert rebuilt == [True, False, False, False, False, False], rebuilt
    # day 5 (index 4): Lever board fails -> 2 of 3 boards OK (< 90 %) -> held
    assert statuses == ["published"] * 4 + ["held", "published"], errors
    assert any("boards fetched OK 2/3" in r for r in outcomes[4].entry["hold_reasons"])

    runs = publish.read_runs(tmp_path / "public" / "runs.jsonl")
    assert [r["run_date"] for r in runs] == [d.isoformat() for d in fixtures.RUN_DATES]
    assert len(publish.last_per_date(runs)) == 6
    st = publish.status(runs, today=fixtures.RUN_DATES[-1])
    assert st["runs_held"] == 1
    assert st["days_running"] == 10  # 2026-10-26 .. 2026-11-04
    assert st["missed_runs"] == 10 - 5  # calendar days without a published run
    assert (tmp_path / "public" / "summary" / "salary_bands.csv").exists()
    page = (tmp_path / "run5" / "site" / "index.html").read_text()
    # The dashboard's status line names this run, not the one before it.
    assert f"Latest run {fixtures.RUN_DATES[-1].isoformat()}: published" in page
    assert (tmp_path / "run5" / "site" / "assets" / "site.css").exists()

    # state: warehouse snapshot and bronze for every run date (held day included)
    assert gh.find("state", "warehouse.duckdb.gz") is not None
    assert len(state.bronze_dates(gh, ["2026-10", "2026-11"])) == 6

    # re-running the last day is idempotent for the data; the ledger keeps both attempts
    again = pipeline.daily(fixtures.RUN_DATES[-1], _paths(tmp_path, seeds, 9), gh)
    assert again.status == "published", again.entry
    runs = publish.read_runs(tmp_path / "public" / "runs.jsonl")
    assert len(runs) == 7
    assert len(publish.last_per_date(runs)) == 6
    st = publish.status(runs, today=fixtures.RUN_DATES[-1])
    assert st["attempts"] == 7 and st["runs_published"] == 5


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


# Closings (docs/incidents.md, 2026-11-21): a closing is confirmed by the second successful board
# fetch that misses the posting, and every "closed in this run" count must use that date.
# RUN_DATES: 10-26, 10-27, 10-28, 11-02, 11-03 (Lever fetch fails -> held), 11-04.
#   a2   missed 10-27 and 10-28 -> closed in the 10-28 run; back on 11-02 -> reopened, and
#        never counted as closed again.
#   1002 missed 11-02 and 11-03 -> closed in the 11-03 run (held). A held run is not loaded into
#        the published warehouse, so in the published history 11-04 is its second missed run.
#   a3   missed 11-02, then the Lever fetch fails on 11-03 (does not count) -> closed on 11-04.
EXPECTED_CLOSED = [0, 0, 1, 0, 1, 2]
EXPECTED_REOPENED = [0, 0, 0, 1, 0, 0]
EXPECTED_STATUS = ["published"] * 4 + ["held", "published"]


def _changes(public: Path) -> list[dict[str, str]]:
    import csv

    with (public / "summary" / "changes_today.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_closings_counted_once_in_the_run_that_confirms_them(
    tmp_path: Path, env: tuple[FakeGitHub, Path]
) -> None:
    from jobpipe.site import build as site_build

    fake, seeds = env
    gh = state.GitHubReleases("o/r", "t", transport=httpx.MockTransport(fake.handler), retries=0)
    public = tmp_path / "public"
    entries, readme_closed, readme_most_closed, dashboard_closed = [], [], [], []
    for n, d in enumerate(fixtures.RUN_DATES):
        paths = _paths(tmp_path, seeds, n)
        out = pipeline.daily(d, paths, gh)
        entries.append(out.entry)
        if out.status != "published":
            for acc in (readme_closed, readme_most_closed, dashboard_closed):
                acc.append(None)
            continue
        ch = _changes(public)
        readme_closed.append(sum(int(r["count"]) for r in ch if r["kind"] == "closed_total"))
        readme_most_closed.append(
            [(r["company"], int(r["count"])) for r in ch if r["kind"] == "most_closed"]
        )
        flows = {str(r[0]): r for r in site_build.gather(paths.duckdb)["flows"]}
        dashboard_closed.append(int(flows[d.isoformat()][2]))  # the newest bar

    assert [e["status"] for e in entries] == EXPECTED_STATUS
    # runs.jsonl: each closing is counted once, in the run that confirms it
    assert [e["closed_postings"] for e in entries] == EXPECTED_CLOSED
    ledger = publish.read_runs(public / "runs.jsonl")
    assert [r["closed_postings"] for r in ledger] == EXPECTED_CLOSED
    published = [i for i, s in enumerate(EXPECTED_STATUS) if s == "published"]
    assert sum(EXPECTED_CLOSED[i] for i in published) == 3  # a2, 1002, a3: once each
    # README "What changed today" and the dashboard's newest bar agree with runs.jsonl
    assert [readme_closed[i] for i in published] == [EXPECTED_CLOSED[i] for i in published]
    assert [dashboard_closed[i] for i in published] == [EXPECTED_CLOSED[i] for i in published]
    assert readme_most_closed[-1] == [("Acme Analytics", 1), ("Beta Robotics", 1)]
    # a failed board fetch never confirms a closing: on 11-03 only 1002 (Greenhouse) closes
    assert entries[4]["closed_postings"] == 1
    # a posting that comes back is reopened and not counted as closed again
    assert [e.get("reopened_postings") for e in entries] == EXPECTED_REOPENED

    # flow check: open(today) = open(previous run) + new + first fetch + reopened - closed.
    # The previous run is the previous run date in the warehouse that built today's numbers:
    # the held 11-03 run is not in the published warehouse, so 11-04 follows 11-02.
    prev_in_warehouse = [None, 0, 1, 2, 3, 3]
    assert [e.get("first_fetch_postings") for e in entries] == [8, 0, 0, 0, 0, 0]
    for e, p in zip(entries, prev_in_warehouse, strict=True):
        before = entries[p]["open_postings"] if p is not None else 0
        flow = (
            before
            + e["new_postings"]
            + e["first_fetch_postings"]
            + e["reopened_postings"]
            - e["closed_postings"]
        )
        assert e["open_postings"] == flow, e
        assert e["open_previous"] == before, e
        assert not [x for x in e["notes"] if x.startswith("flow check")], e["notes"]
    assert [e["open_postings"] for e in entries] == [8, 8, 7, 9, 8, 7]


def test_lifecycle_confirms_closing_on_second_successful_miss(tmp_path: Path) -> None:
    import duckdb

    from jobpipe import guards

    paths = pipeline.Paths(
        data_dir=tmp_path / "data", seeds_dir=tmp_path / "seeds",
        duckdb=tmp_path / "data" / "warehouse.duckdb",
    )  # fmt: skip
    res = pipeline.offline_build(paths)  # all six run dates, the failed fetch included
    assert res.success, res.failures

    # per-run counts on the latest date: only a3 is confirmed on 11-04 (1002 was on 11-03)
    stats = guards.collect(paths.duckdb, fixtures.RUN_DATES[-1])
    assert stats.closed_postings == 1
    assert stats.flow_gap == 0

    d = fixtures.RUN_DATES
    con = duckdb.connect(str(paths.duckdb))
    try:
        rows = con.execute(
            """select f.posting_id, f.closed_on, f.close_confirmed_on, l.reopened_count, f.is_open
               from gold.fct_job_postings f
               join history.int_posting_lifecycle l using (posting_key)"""
        ).fetchall()
        lc = {r[0]: r[1:] for r in rows}
        assert lc["1002"] == (d[3], d[4], 0, False)  # missed 11-02 and 11-03
        assert lc["a3"] == (d[3], d[5], 0, False)  # 11-03 fetch failed: confirmed 11-04
        assert lc["a2"] == (None, None, 1, True)  # came back: open, not closed
        assert lc["u-1"] == (None, None, 0, True)  # missed once only
        assert lc["a1"] == (None, None, 0, True)  # absent only on the failed fetch
        # the flow identity holds on every run date, as each run saw it
        for day in d:
            f = guards.flow_asof(con, day)
            assert f["open_now"] == (
                f["open_previous"] + f["new"] + f["first_fetch"] + f["reopened"] - f["closed"]
            ), (day, f)
        # a2 was confirmed closed by the 10-28 run as it saw it, and reopened on 11-02
        assert guards.flow_asof(con, d[2])["closed"] == 1
        assert guards.flow_asof(con, d[3])["reopened"] == 1
        assert guards.flow_asof(con, d[4])["closed"] == 1  # 1002 only, not a3
    finally:
        con.close()
