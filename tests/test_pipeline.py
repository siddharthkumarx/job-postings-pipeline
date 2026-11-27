"""End-to-end daily runs on synthetic data with a fake GitHub Releases API."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from jobpipe import fixtures, fx, guards, ingest, pipeline, publish, state, warehouse
from jobpipe.models import BoardRun, Posting
from tests.test_state import FakeGitHub

EVALUATE = guards.evaluate  # the real gate, before any test wraps it


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
#   1002 missed 11-02 and 11-03 -> closed in the 11-03 run (held). The 11-04 run loads the held
#        day first (docs/incidents.md, 2026-11-27), so 1002 is not confirmed a second time.
#   a3   missed 11-02, then the Lever fetch fails on 11-03 (does not count) -> closed on 11-04.
EXPECTED_CLOSED = [0, 0, 1, 0, 1, 1]
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
    assert sum(EXPECTED_CLOSED) == 3  # a2, 1002 (held run), a3: once each
    published = [i for i, s in enumerate(EXPECTED_STATUS) if s == "published"]
    # README "What changed today" and the dashboard's newest bar agree with runs.jsonl
    assert [readme_closed[i] for i in published] == [EXPECTED_CLOSED[i] for i in published]
    assert [dashboard_closed[i] for i in published] == [EXPECTED_CLOSED[i] for i in published]
    assert readme_most_closed[-1] == [("Beta Robotics", 1)]
    # a failed board fetch never confirms a closing: on 11-03 only 1002 (Greenhouse) closes
    assert entries[4]["closed_postings"] == 1
    # a posting that comes back is reopened and not counted as closed again
    assert [e.get("reopened_postings") for e in entries] == EXPECTED_REOPENED

    # flow check: open(today) = open(previous run) + new + first fetch + reopened - closed.
    # The previous run is the previous run date in the warehouse that built today's numbers:
    # the 11-04 run loads the held 11-03 run, so 11-04 follows 11-03.
    prev_in_warehouse = [None, 0, 1, 2, 3, 4]
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


# Held days (docs/incidents.md, 2026-11-27): the next run loads every day stored since the last
# published snapshot, so published -> held -> published ends with the same tables as clean days.


def _tables(db: Path) -> dict[str, list[tuple[object, ...]]]:
    import duckdb

    con = duckdb.connect(str(db), read_only=True)
    try:
        names = con.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_schema in ('silver', 'history', 'gold') order by 1, 2"
        ).fetchall()
        return {
            f"{s}.{t}": sorted(con.execute(f'select * from "{s}"."{t}"').fetchall(), key=repr)
            for s, t in names
        }
    finally:
        con.close()


def _sequence(
    root: Path,
    seeds: Path,
    hold: set[date] | None,
    monkeypatch: pytest.MonkeyPatch,
    days: list[date] | None = None,
) -> tuple[list[pipeline.Outcome], pipeline.Paths, state.GitHubReleases]:
    """Run the fixture days (all, or ``days``) in order on a fresh fake GitHub.

    ``hold=None`` publishes every day (clean days); otherwise the dates in ``hold`` are held
    on top of the normal guards (the Lever failure on 11-03 holds that day by itself).
    """

    def gate(stats: guards.RunStats, previous: dict[str, object] | None) -> list[str]:
        if hold is None:
            return []
        extra = ["held by the test"] if date.fromisoformat(stats.run_date) in hold else []
        return EVALUATE(stats, previous) + extra

    monkeypatch.setattr(guards, "evaluate", gate)
    gh = state.GitHubReleases(
        "o/r", "t", transport=httpx.MockTransport(FakeGitHub().handler), retries=0
    )
    outcomes, paths = [], None
    for n, d in enumerate(days or fixtures.RUN_DATES):
        paths = pipeline.Paths(
            data_dir=root / f"run{n}" / "data", public_dir=root / "public",
            site_dir=root / f"run{n}" / "site", seeds_dir=seeds,
            duckdb=root / f"run{n}" / "data" / "warehouse.duckdb",
        )  # fmt: skip
        outcomes.append(pipeline.daily(d, paths, gh))
    assert paths is not None
    return outcomes, paths, gh


def _lifecycle(db: Path) -> dict[str, tuple[object, ...]]:
    import duckdb

    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "select posting_id, closed_on, close_confirmed_on, is_open from gold.fct_job_postings"
        ).fetchall()
    finally:
        con.close()
    return {r[0]: r[1:] for r in rows}


def test_published_held_published_gives_the_tables_of_clean_days(
    tmp_path: Path, env: tuple[FakeGitHub, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, seeds = env
    d = fixtures.RUN_DATES
    clean, clean_paths, _ = _sequence(tmp_path / "clean", seeds, None, monkeypatch)
    assert [o.status for o in clean] == ["published"] * 6, [o.entry.get("error") for o in clean]
    held, held_paths, gh = _sequence(tmp_path / "held", seeds, set(), monkeypatch)
    assert [o.status for o in held] == EXPECTED_STATUS, [o.entry.get("error") for o in held]

    # 1002 is missed on 11-02 and 11-03: its closing is confirmed once, by the 11-03 run, and
    # the published 11-04 run does not confirm it again
    assert [o.entry["closed_postings"] for o in clean] == [0, 0, 1, 0, 1, 1]
    assert [o.entry["closed_postings"] for o in held] == [0, 0, 1, 0, 1, 1]
    assert _lifecycle(held_paths.duckdb)["1002"] == (d[3], d[4], False)
    for key in ("open_postings", "new_postings", "reopened_postings", "open_previous"):
        assert held[5].entry[key] == clean[5].entry[key], key
    assert not [n for n in held[5].entry["notes"] if n.startswith("flow check")]

    # every table matches clean days, and a full rebuild from every bronze snapshot
    assert _tables(held_paths.duckdb) == _tables(clean_paths.duckdb)
    full = pipeline.Paths(
        data_dir=tmp_path / "full" / "data", seeds_dir=tmp_path / "full" / "seeds",
        duckdb=tmp_path / "full" / "data" / "warehouse.duckdb",
    )  # fmt: skip
    assert pipeline.offline_build(full).success
    assert _tables(full.duckdb) == _tables(clean_paths.duckdb)
    # the run after the hold loaded the held day, once, before its own day
    assert "loaded unpublished days 2026-11-03" in held[5].entry["notes"]

    # the published snapshot now lists the held day, so it is never loaded twice
    st = state.pull_warehouse(gh, tmp_path / "check" / "warehouse.duckdb")
    assert st is not None and st["bronze_dates"] == [x.isoformat() for x in d]


def test_every_unpublished_day_is_loaded_once_in_date_order(
    tmp_path: Path, env: tuple[FakeGitHub, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, seeds = env
    d = fixtures.RUN_DATES
    pulled: list[date] = []
    pull = state.pull_bronze

    def spy(gh: state.GitHubReleases, data_dir: Path, day: date, *, fx: bool = True) -> bool:
        assert not fx  # the catch-up keeps the FX file today's run fetched
        # ... and runs only after today's (later) bronze is on disk
        later = [p for p in (data_dir / "bronze" / "postings").glob("run_date=*")
                 if p.name > f"run_date={day.isoformat()}"]  # fmt: skip
        assert later, "catch-up ran before today's ingest"
        pulled.append(day)
        return pull(gh, data_dir, day, fx=fx)

    monkeypatch.setattr(state, "pull_bronze", spy)
    _, clean_paths, _ = _sequence(tmp_path / "clean", seeds, None, monkeypatch)
    pulled.clear()
    # published, published, published, held, held, published
    held, held_paths, _ = _sequence(tmp_path / "held", seeds, {d[3]}, monkeypatch)
    assert [o.status for o in held] == ["published"] * 3 + ["held", "held", "published"]
    assert [o.entry["closed_postings"] for o in held] == [0, 0, 1, 0, 1, 1]
    assert _lifecycle(held_paths.duckdb)["1002"] == (d[3], d[4], False)
    assert _tables(held_paths.duckdb) == _tables(clean_paths.duckdb)
    # day 1 rebuilds from nothing; the second held run already sees the first held day; the
    # published run loads both held days, once each, oldest first
    assert pulled == [d[3], d[3], d[4]]
    assert "loaded unpublished days 2026-11-02, 2026-11-03" in held[5].entry["notes"]


def test_release_hold_loads_the_held_days_before_its_range(
    tmp_path: Path, env: tuple[FakeGitHub, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, seeds = env
    d = fixtures.RUN_DATES
    # published, published, held, held; then a human releases the second hold
    held, held_paths, gh = _sequence(tmp_path / "held", seeds, {d[2], d[3]}, monkeypatch, d[:4])
    assert [o.status for o in held] == ["published"] * 2 + ["held"] * 2
    paths = pipeline.Paths(
        data_dir=tmp_path / "release" / "data", public_dir=held_paths.public_dir,
        site_dir=tmp_path / "release" / "site", seeds_dir=seeds,
        duckdb=tmp_path / "release" / "data" / "warehouse.duckdb",
    )  # fmt: skip
    out = pipeline.backfill(d[3], d[3], paths, gh, force=True)
    assert out.status == "published", out.entry
    assert "loaded unpublished days 2026-10-28" in out.entry["notes"]
    # the same tables as one clean build of those four days
    clean = tmp_path / "clean"
    fixtures.write(clean / "data", clean / "seeds", dates=d[:4])
    res = warehouse.run_dbt(
        ["build"], data_dir=clean / "data", duckdb_path=clean / "w.duckdb",
        seeds_dir=clean / "seeds",
    )  # fmt: skip
    assert res.success, res.failures
    assert _tables(paths.duckdb) == _tables(clean / "w.duckdb")
    st = state.pull_warehouse(gh, tmp_path / "check" / "warehouse.duckdb")
    assert st is not None and st["bronze_dates"] == [x.isoformat() for x in d[:4]]


def test_held_day_without_postings_does_not_block_later_snapshots(
    tmp_path: Path, env: tuple[FakeGitHub, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, seeds = env
    d = fixtures.RUN_DATES
    postings_for, board_runs_for = fixtures.postings_for, fixtures.board_runs_for

    def no_postings(day: date) -> list[Posting]:
        return [] if day == d[1] else postings_for(day)

    def all_failed(day: date) -> list[BoardRun]:
        runs = board_runs_for(day)
        if day != d[1]:
            return runs
        return [r.model_copy(update={"status": "error", "http_status": 503}) for r in runs]

    # every board fails on 10-27, so its bronze has no postings at all and the run is held
    monkeypatch.setattr(fixtures, "postings_for", no_postings)
    monkeypatch.setattr(fixtures, "board_runs_for", all_failed)
    out, _, gh = _sequence(tmp_path / "run", seeds, set(), monkeypatch, d[:4])
    assert [o.status for o in out] == ["published", "held", "published", "published"], [
        o.entry.get("error") for o in out
    ]
    assert "loaded unpublished days 2026-10-27" in out[2].entry["notes"]
    # the empty day leaves no rows to validate, so the snapshot does not list it; the next run
    # restores that snapshot instead of failing or rebuilding, and does not load the day again
    st = state.pull_warehouse(gh, tmp_path / "check" / "warehouse.duckdb")
    assert st is not None and st["bronze_dates"] == [d[0].isoformat(), *map(str, d[2:4])]
    assert not [n for n in out[3].entry["notes"] if "rebuilt" in n or "unpublished" in n]


def test_unpublished_days_skip_loaded_and_incomplete_days(tmp_path: Path) -> None:
    gh = state.GitHubReleases(
        "o/r", "t", transport=httpx.MockTransport(FakeGitHub().handler), retries=0
    )
    src = tmp_path / "src"
    days = [date(2026, 10, 30), date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)]
    for d in days:
        for table in state.BRONZE_ASSETS:
            p = state.bronze_local(src, table, d)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(table.encode())
        state.push_bronze(gh, src, d)
    # 11-02 lost its board log: half a day is never built on
    lost = gh.find("bronze-2026-11", "board_runs_2026-11-02.parquet")
    assert lost is not None
    gh._req("DELETE", f"{state.API}/repos/o/r/releases/assets/{lost.id}")

    st = {"last_good_run": "2026-10-30", "bronze_dates": ["2026-10-30"]}
    assert pipeline.unpublished_dates(gh, st, date(2026, 11, 4)) == days[1:]
    assert pipeline.unpublished_dates(gh, st, date(2026, 11, 2)) == [days[1]]
    paths = pipeline.Paths(data_dir=tmp_path / "data")
    notes: list[str] = []
    loaded = pipeline.load_unpublished(gh, paths, st, date(2026, 11, 4), notes)
    assert loaded == [days[1], days[3]]
    assert notes == [
        "bronze for 2026-11-02 incomplete; not loaded",
        "loaded unpublished days 2026-11-01, 2026-11-03",
    ]
    assert not state.bronze_local(paths.data_dir, "postings", days[2]).exists()
    assert st["bronze_dates"] == ["2026-10-30", "2026-11-01", "2026-11-03"]
    # once listed in the snapshot state, a day is not loaded again
    assert pipeline.unpublished_dates(gh, st, date(2026, 11, 4)) == [days[2]]


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
