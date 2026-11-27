"""One number, one name (D-020): every figure called "open roles" is the same number.

The fixture warehouse is built from the synthetic run dates up to the failed Lever read
(2026-11-03), with one Acme posting dropped that day, so all three parts of the open-roles
count are non-zero: listed today, missing once, and on a board not read today.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any

import pytest
import yaml

from jobpipe import fixtures, guards, publish, readme, warehouse
from jobpipe.models import Posting
from jobpipe.readme_data import load
from jobpipe.site import build as site_build
from jobpipe.visuals import build as visuals

LINE = re.compile(
    r"([\d,]+) open = ([\d,]+) listed today \+ ([\d,]+) missing once \(closed after a 2nd miss\)"
    r" \+ ([\d,]+) on ([\d,]+) boards? not read today"
)
# A number labelled "open roles" either way round; shares ("open roles: 13%") are not counts.
FIGURES = (
    re.compile(r"(?i)\bopen roles?\b[ :]*(\d[\d,]*)(?![\d,.]*%)"),
    re.compile(r"(?i)(?<![\d,])(\d[\d,]*) open roles?\b"),
)


def _n(s: str) -> int:
    return int(s.replace(",", ""))


def figures(text: str) -> list[int]:
    return [_n(m.group(1)) for rx in FIGURES for m in rx.finditer(text)]


def where(text: str) -> list[str]:
    """Each match with its surroundings, for the failure message."""
    return [
        text[max(0, m.start() - 60) : m.end() + 10] for rx in FIGURES for m in rx.finditer(text)
    ]


def line_parts(text: str) -> list[tuple[int, ...]]:
    return [tuple(_n(g) for g in m.groups()) for m in LINE.finditer(text)]


def plain(html: str) -> str:
    """Visible text; block elements end with " | " so a number never runs into the next one."""
    blocks = r"</?(?:li|p|td|th|tr|figcaption|figure|ul|ol|div|h\d|summary|title|desc|text)\b[^>]*>"
    text = re.sub(r"<[^>]+>", " ", re.sub(blocks, " | ", html))
    return " ".join(unescape(text).split())


def chart_values(html: str, caption: str) -> list[int]:
    head = f"<figcaption>{re.escape(caption)}</figcaption>"
    fig = re.search(head + r'<ul class="hbars" role="list">(.*?)</ul>', html)
    assert fig, caption
    values = re.findall(r'<span class="bar-value">([^<]+)</span>', fig[1])
    return [_n(v.split(" ")[0]) for v in values]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("open-roles")
    data, public, site = root / "data", root / "public", root / "site"
    duckdb = data / "warehouse.duckdb"
    days = fixtures.RUN_DATES[:5]
    original = fixtures.postings_for

    def postings_for(d: date) -> list[Posting]:
        out = original(d)
        if d == days[-1]:  # Analytics Engineer 1004 (first seen the run before) is missed once
            out = [p for p in out if p.posting_id != "1004"]
        return out

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fixtures, "postings_for", postings_for)
        fixtures.write(data, root / "seeds", dates=days)
    res = warehouse.run_dbt(["build"], data_dir=data, duckdb_path=duckdb, seeds_dir=root / "seeds")
    assert res.success, res.failures

    publish.summary_csvs(duckdb, public / "summary")
    publish.readme_extracts(duckdb, public)
    stats = guards.collect(duckdb, days[-1])
    publish.append_run(
        public / "runs.jsonl",
        {"run_date": days[-1].isoformat(), "status": "published", "boards": stats.boards_total,
         "boards_ok": stats.boards_ok, "companies": stats.boards_total,
         "postings_listed": stats.postings_listed, "open_postings": stats.open_postings},
    )  # fmt: skip
    publish.write_status(public, today=days[-1])
    html = site_build.build(duckdb, public, site).read_text(encoding="utf-8")

    import duckdb as ddb

    con = ddb.connect(str(duckdb))
    try:
        truth = {
            "open": con.execute(
                "select count(*) from gold.fct_job_postings where is_open"
            ).fetchone()[0],  # type: ignore[index]
            "listed": con.execute(
                """select count(*) from history.int_postings_daily
                   where run_date = (select max(run_date) from history.int_run_calendar)"""
            ).fetchone()[0],  # type: ignore[index]
        }
    finally:
        con.close()

    d = load(root)
    cfg = yaml.safe_load((readme.ROOT_TEMPLATES / "readme.yml").read_text())
    env = readme.environment()
    ctx = readme.context(d, cfg)
    return {
        "root": root, "public": public, "html": html, "truth": truth, "stats": stats,
        "readme": env.get_template("README.md.j2").render(**ctx),
        "card": env.get_template("dataset-card.md.j2").render(**ctx),
        "hero": visuals.hero(d) + visuals.hero(d, square=True),
    }  # fmt: skip


def test_fixture_exercises_every_part(built: dict[str, Any]) -> None:
    b = json.loads((built["public"] / "summary" / "open_roles.json").read_text())
    assert b["open_roles"] == built["truth"]["open"] == 8
    assert (b["listed_today"], b["missing_once"], b["on_unread_boards"]) == (4, 1, 3)
    assert (b["boards"], b["boards_read"], b["boards_unread"]) == (3, 2, 1)


def test_dashboard_open_roles_are_one_number(built: dict[str, Any]) -> None:
    html, truth = built["html"], built["truth"]
    kpi = re.search(
        r'<span class="label">Open roles</span><span class="value">([\d,]+)</span>', html
    )
    assert kpi and _n(kpi[1]) == truth["open"]
    text = plain(html)
    assert figures(text) and set(figures(text)) == {truth["open"]}, where(text)
    # the reconciliation line sits right under the headline figures and adds up
    overview = plain(html.split('id="overview"')[1].split("</section>")[0])
    (parts,) = line_parts(overview)
    o, listed, missed, unread, boards = parts
    assert o == listed + missed + unread == truth["open"]
    assert listed == truth["listed"] == built["stats"].postings_listed
    assert boards == built["stats"].boards_total - built["stats"].boards_ok
    assert f"{built['stats'].boards_ok:,} boards read in the latest run" in text
    # charts that split open roles add up to it
    assert sum(chart_values(html, "Open roles by job-board provider")) == truth["open"]
    assert sum(chart_values(html, "Open roles by role family")) == truth["open"]
    # the per-run trend counts postings listed, and says so
    assert "open roles per run" not in text.lower()
    assert "Postings listed per run" in text
    assert re.search(rf"Listed · {fixtures.RUN_DATES[4]}: {listed}<", html)


def test_badges_and_status_name_each_number(built: dict[str, Any]) -> None:
    truth, badges = built["truth"], built["public"] / "badges"
    st = json.loads((built["public"] / "status.json").read_text())
    assert st["jobs_tracked"] == truth["open"] and st["rows_today"] == truth["listed"]
    open_b = json.loads((badges / "jobs-tracked.json").read_text())
    listed_b = json.loads((badges / "rows-today.json").read_text())
    assert (open_b["label"], _n(open_b["message"])) == ("open roles", truth["open"])
    assert (listed_b["label"], _n(listed_b["message"])) == ("listed today", truth["listed"])


@pytest.mark.parametrize("doc", ["readme", "card", "hero"])
def test_readme_card_and_hero_use_the_same_number(built: dict[str, Any], doc: str) -> None:
    text, truth = built[doc], built["truth"]
    if doc == "hero":
        text = plain(text)
    assert figures(text) and set(figures(text)) == {truth["open"]}, where(text)
    if doc != "hero":
        (parts,) = line_parts(text)
        assert parts[0] == parts[1] + parts[2] + parts[3] == truth["open"]
        assert parts[1] == truth["listed"]
    if doc == "readme":
        today = text.split("### What changed today")[1].split("\n## ")[0]
        assert line_parts(today), "reconciliation line belongs in the today section"
        assert "badge('rows-today')" not in text and "rows-today.json" not in text
        assert "[![Open roles](" in text and "jobs-tracked.json" in text


def test_published_readme_matches_status() -> None:
    """The committed README, re-rendered from the committed public/ files: one number."""
    d = load(Path("."))
    if not d.open_jobs:
        pytest.skip("no published run in public/")
    cfg = yaml.safe_load((readme.ROOT_TEMPLATES / "readme.yml").read_text())
    ctx = readme.context(d, cfg)
    for name in ("README.md.j2", "dataset-card.md.j2"):
        text = readme.environment().get_template(name).render(**ctx)
        assert set(figures(text)) == {d.open_jobs}, (name, where(text))
        for parts in line_parts(text):
            assert parts[0] == parts[1] + parts[2] + parts[3] == d.open_jobs


def test_line_is_left_out_when_it_belongs_to_another_run(built: dict[str, Any]) -> None:
    d = load(built["root"])
    assert d.open_line
    d.status = {**d.status, "jobs_tracked": d.open_jobs + 1}
    assert d.open_line == ""
