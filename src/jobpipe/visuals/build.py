"""Animated README visuals, regenerated from real run outputs on every run.

hero.svg            problem → the run with real rows → the result (one big number)
pipeline.svg        source → collect → check → store → deliver, with tool logos
maintenance-loop.svg  daily runs → a real incident → fixed → data keeps arriving
data-roles.svg      open data roles today (real counts and median salaries)
dbt-lineage.svg     the dbt model graph, read from dbt's manifest.json
hero-square.svg     1080x1080 hero for the LinkedIn video (text ≥ 40 px)

Light system v1 (D-018): an alt-section background, white cards, ink/body/muted/accent
text, the good colour for data marks and the look-here colour only with a direct label.

Sizes (in a 1000-px-wide viewBox): headings ≥ 36 px, row and body text ≥ 30 px, so the
text stays readable when GitHub shrinks the image to a phone's width.

Every animation starts on its final frame (negative delay) and reduced motion pins every
animated element to its final state, so any still capture shows the result.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from jobpipe.readme_data import ROLE_LABELS, Incident, ReadmeData, load, short_title
from jobpipe.visuals.base import (
    ACCENT,
    BODY,
    GOOD,
    INK,
    LINE,
    LOOK,
    MUTED,
    SOFT,
    Canvas,
    beats_css,
    card,
    final_beat_time,
    final_state_css,
    fmt_usd_k,
    icon,
    start_on_final_frame,
)

LOOP_S = 10.0
H1 = 40  # headings
H2 = 36  # smaller headings
ROW = 30  # row and body text


def _salary(row: dict[str, str]) -> str:
    lo, hi = row.get("salary_min_usd_annual"), row.get("salary_max_usd_annual")
    if not lo:
        return ""
    lo_k, hi_k = float(lo) / 1000, float(hi or lo) / 1000
    return f"${lo_k:,.0f}k–{hi_k:,.0f}k" if hi_k != lo_k else f"${lo_k:,.0f}k"


def _wrap(s: str, width: int, lines: int = 2) -> list[str]:
    out = textwrap.wrap(s, width)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,; ") + "…"
    return out


def _first_sentence(s: str) -> str:
    """First sentence (a dot followed by a space and a capital), so it fits in two lines."""
    import re

    m = re.search(r"(?<=[.!?])\s+(?=[A-Z])", s)
    return s[: m.start()] if m else s


def _timing(c: Canvas, n_beats: int) -> None:
    c.css.append(beats_css(n_beats, LOOP_S))
    c.css.append(start_on_final_frame(final_beat_time(n_beats, LOOP_S)))
    c.css.append(final_state_css(n_beats))


def _rows_css() -> str:
    return "".join(
        f".r{i}{{animation:rw{i} {LOOP_S}s linear infinite}}"
        f"@keyframes rw{i}{{0%,{40 + i * 5}%{{opacity:0}}{43 + i * 5}%,100%{{opacity:1}}}}"
        for i in (1, 2, 3)
    )


# ---- hero ------------------------------------------------------------------------------


def hero(d: ReadmeData, square: bool = False) -> str:
    w, h = (1080, 1080) if square else (1000, 460)
    c = Canvas(
        w,
        h,
        f"{d.open_jobs:,} open jobs at {d.companies:,} US tech companies, checked every day",
        f"Animated: open tech jobs are spread across {d.companies:,} company job boards; one "
        f"daily run collects them into a single table; result: {d.open_jobs:,} open jobs at "
        f"{d.companies:,} US tech companies (latest run {d.run_date}).",
    )
    cx = w / 2
    rows = d.sample[:3]
    if not square:
        mark_w = len(f"{d.companies:,} separate company job boards.") * 22.6
        b1 = [
            c.text(cx, 170, "Open tech jobs are spread across", size=44, font="sansb", anchor="middle"),
            c.text(cx, 236, f"{d.companies:,} separate company job boards.", size=44, font="sansb",
                   anchor="middle"),
            f'<rect x="{cx - mark_w / 2}" y="252" width="{mark_w}" height="8" rx="4" fill="{LOOK}"/>',
            c.text(cx, 322, "Checking them by hand takes days.", size=ROW + 2, fill=BODY, anchor="middle"),
        ]  # fmt: skip
        b2 = [
            c.text(60, 84, "One run a day, one clean table", size=H2, font="sansb"),
            c.text(940, 84, d.run_date, size=ROW, fill=MUTED, anchor="end"),
        ]
        for i, r in enumerate(rows):
            y = 120 + i * 100
            b2.append(f'<g class="row r{i + 1}">' + card(60, y, 880, 80)
                      + c.text(92, y + 51, r["company_name"][:24], size=ROW + 2, font="sansb")
                      + c.text(908, y + 51, _salary(r), size=ROW, font="sansm", fill=ACCENT, anchor="end")
                      + "</g>")  # fmt: skip
        b3 = [
            card(60, 60, 880, 340),
            c.text(cx, 230, f"{d.open_jobs:,}", size=132, font="sansb", fill=ACCENT, anchor="middle"),
            c.text(cx, 300, f"open jobs at {d.companies:,} US tech companies", size=42, anchor="middle"),
            c.text(cx, 356, f"checked every day · latest run {d.run_date}", size=ROW, fill=MUTED,
                   anchor="middle"),
        ]  # fmt: skip
    else:
        sq_w = len(f"{d.companies:,} job boards.") * 37
        b1 = [
            c.text(cx, 420, "Open tech jobs are", size=64, font="sansb", anchor="middle"),
            c.text(cx, 500, "spread across", size=64, font="sansb", anchor="middle"),
            c.text(cx, 600, f"{d.companies:,} job boards.", size=72, font="sansb", anchor="middle"),
            f'<rect x="{cx - sq_w / 2}" y="626" width="{sq_w}" height="10" rx="5" fill="{LOOK}"/>',
        ]  # fmt: skip
        b2 = [
            c.text(
                cx, 190, "One run a day, one clean table", size=48, font="sansb", anchor="middle"
            )
        ]
        for i, r in enumerate(rows):
            y = 280 + i * 190
            b2.append(f'<g class="row r{i + 1}">' + card(90, y, 900, 150)
                      + c.text(130, y + 66, r["company_name"][:22], size=48, font="sansb")
                      + c.text(130, y + 120, short_title(r, 24), size=40, fill=BODY)
                      + c.text(950, y + 66, _salary(r), size=40, font="sansm", fill=ACCENT, anchor="end")
                      + "</g>")  # fmt: skip
        b2.append(
            c.text(cx, 900, f"real rows · {d.run_date}", size=40, fill=MUTED, anchor="middle")
        )
        b3 = [
            card(90, 300, 900, 520),
            c.text(cx, 540, f"{d.open_jobs:,}", size=190, font="sansb", fill=ACCENT, anchor="middle"),
            c.text(cx, 630, "open jobs at", size=56, anchor="middle"),
            c.text(cx, 700, f"{d.companies:,} US tech companies", size=56, anchor="middle"),
            c.text(cx, 780, f"checked every day · {d.run_date}", size=40, fill=MUTED, anchor="middle"),
        ]  # fmt: skip
    c.css.append(_rows_css())
    _timing(c, 3)
    c.add(f'<g class="beat b1">{"".join(b1)}</g>')
    c.add(f'<g class="beat b2">{"".join(b2)}</g>')
    c.add(f'<g class="beat b3">{"".join(b3)}</g>')
    return c.render()


# ---- pipeline --------------------------------------------------------------------------

PIPE_LOOP = 8.0


def stages(d: ReadmeData) -> list[tuple[str, str, list[str]]]:
    """The five steps with the logos of tools this repo really uses in each step.

    Hugging Face appears only once a run has really uploaded the dataset there.
    """
    deliver = ["github", "githubactions"] + (["huggingface"] if d.hf_uploaded else [])
    return [
        ("Source", "3 job boards", []),
        ("Collect", "Python", ["python", "uv", "pydantic"]),
        ("Check", "dbt, pytest", ["pytest"]),
        ("Store", "DuckDB", ["duckdb", "apacheparquet"]),
        ("Deliver", "GitHub, HF" if d.hf_uploaded else "GitHub", deliver),
    ]


def pipeline(d: ReadmeData) -> str:
    steps = stages(d)
    deliver_to = "GitHub and Hugging Face" if d.hf_uploaded else "GitHub"
    c = Canvas(
        1000,
        400,
        "How it works: source, collect, check, store, deliver",
        "Animated pipeline: public job boards (Greenhouse, Lever, Ashby) are collected with "
        "Python, checked with dbt tests and pytest, stored in DuckDB and Parquet, and delivered "
        f"through {deliver_to}. {d.companies:,} job boards, about {d.minutes:.0f} minutes, "
        "once a day.",
    )
    xs = [100, 300, 500, 700, 900]
    for i in range(len(xs)):
        a = i * 1.0 / PIPE_LOOP * 100
        b = (i * 1.0 + 0.3) / PIPE_LOOP * 100
        c.css.append(
            f".s{i}{{animation:sk{i} {PIPE_LOOP}s linear infinite}}"
            f"@keyframes sk{i}{{0%,{a:.1f}%{{stroke:{LINE}}}{b:.1f}%,100%{{stroke:{ACCENT}}}}}"
        )
    c.css.append(
        ".dot{animation:mv 1.6s linear infinite}@keyframes mv{from{transform:translateX(0)}"
        "to{transform:translateX(30px)}}"
    )
    c.css.append(start_on_final_frame(len(xs) * 1.0 + 0.3))
    c.css.append(final_state_css(0, ".dot{transform:none!important}"))
    for i, (label, caption, icons) in enumerate(steps):
        x = xs[i]
        c.add(card(x - 78, 40, 156, 136, stroke=ACCENT, sw=3, cls=f"st s{i}"))
        if not icons:  # the three sources: a simple list glyph
            for j in range(3):
                c.add(
                    f'<rect x="{x - 42}" y="{74 + j * 26}" width="84" height="13" rx="6" fill="{MUTED}"/>'
                )
        elif label == "Check":
            c.add(icon("pytest", x - 56, 88, 42))
            c.add(c.text(x + 30, 120, "dbt", size=ROW, font="sansb", anchor="middle"))
        else:
            n = len(icons)
            size = 42 if n <= 2 else 36
            total = n * size + (n - 1) * 10
            for j, name in enumerate(icons):
                c.add(icon(name, x - total / 2 + j * (size + 10), 108 - size / 2, size))
        c.add(c.text(x, 226, label, size=H2, font="sansb", anchor="middle"))
        c.add(c.text(x, 268, caption, size=ROW, fill=MUTED, anchor="middle"))
        if i < len(xs) - 1:
            c.add(
                f'<line x1="{x + 80}" y1="108" x2="{x + 120}" y2="108" stroke="{LINE}" stroke-width="3"/>'
            )
            c.add(f'<circle class="dot" cx="{x + 85}" cy="108" r="6" fill="{GOOD}"/>')
    c.add(c.text(500, 350, f"{d.companies:,} boards · about {d.minutes:.0f} min · once a day",
                 size=ROW + 2, fill=BODY, anchor="middle"))  # fmt: skip
    return c.render()


# ---- maintenance loop ------------------------------------------------------------------


def _pick_incident(d: ReadmeData) -> tuple[Incident | None, str | None]:
    failed = {r.get("actions_run_id") for r in d.runs if r.get("status") in ("failed", "held")}
    for inc in d.incidents:
        run_id = next((t for t in inc.run.replace("(", " ").split() if t.isdigit()), None)
        if run_id and run_id in failed and "first" in inc.run:
            return inc, run_id
    for inc in d.incidents:
        run_id = next((t for t in inc.run.split() if t.isdigit()), None)
        if run_id and run_id in failed:
            return inc, run_id
    return (d.incidents[0], None) if d.incidents else (None, None)


def maintenance_loop(d: ReadmeData) -> str:
    inc, run_id = _pick_incident(d)
    attempts = d.runs[-14:]
    ing = d.last_run.get("ingest") or {}
    ok, total = int(ing.get("boards_ok") or 0), int(ing.get("boards") or d.companies)
    bad_total = sum(r.get("status") != "published" for r in d.runs)
    c = Canvas(
        1000,
        400,
        "Maintenance loop: daily runs, a real incident, fixed, data keeps arriving",
        f"Animated: one square per pipeline run, the latest {len(attempts)} of {len(d.runs)}; "
        f"{bad_total} held or failed so far. "
        + (f"Incident {inc.date}: {inc.plain} Fix: {inc.fix_plain} " if inc else "")
        + f"Latest run ({d.run_date}): {ok:,} of {total:,} job boards read.",
    )
    _timing(c, 4)
    size, gap = 44, 14
    width = len(attempts) * size + (len(attempts) - 1) * gap
    x0 = 500 - width / 2
    prev_bad = False
    for i, r in enumerate(attempts):
        bad = r.get("status") != "published"
        x = x0 + i * (size + gap)
        hl = run_id is not None and r.get("actions_run_id") == run_id
        stroke = f' stroke="{INK}" stroke-width="3"' if hl else ""
        c.add(f'<rect x="{x:.1f}" y="40" width="{size}" height="{size}" rx="8" '
              f'fill="{LOOK if bad else GOOD}"{stroke}/>')  # fmt: skip
        if bad and not prev_bad:  # direct label under the first square of each amber stretch
            c.add(c.text(x, 120, "held or failed", size=ROW, fill=BODY))
        prev_bad = bad
    b1 = [
        c.text(500, 206, "A fresh run every day.", size=H1, font="sansb", anchor="middle"),
        c.text(500, 262, f"{len(d.runs)} runs so far, {bad_total} held or failed", size=ROW,
               fill=MUTED, anchor="middle"),
    ]  # fmt: skip
    b2: list[str] = []
    b3: list[str] = []
    if inc:
        title = _wrap(inc.title, 44, 1)[0]
        b2.append(f'<circle cx="{500 - len(title) * 8.4 - 26:.0f}" cy="194" r="10" fill="{LOOK}"/>')
        b2.append(c.text(500, 206, title, size=H2, font="sansb", anchor="middle"))
        for j, line in enumerate(_wrap(_first_sentence(inc.plain), 54)):
            b2.append(c.text(500, 260 + j * 44, line, size=ROW, fill=BODY, anchor="middle"))
        b3.append(c.text(500, 206, "Fixed the same day.", size=H2, font="sansb", fill=ACCENT,
                         anchor="middle"))  # fmt: skip
        for j, line in enumerate(_wrap(_first_sentence(inc.fix_plain), 54)):
            b3.append(c.text(500, 260 + j * 44, line, size=ROW, fill=BODY, anchor="middle"))
    b4 = [
        c.text(500, 250, f"{ok:,} of {total:,}", size=92, font="sansb", fill=ACCENT, anchor="middle"),
        c.text(500, 316, f"job boards read in the latest run · {d.run_date}", size=ROW + 2,
               anchor="middle"),
    ]  # fmt: skip
    c.add(f'<g class="beat b1">{"".join(b1)}</g>')
    c.add(f'<g class="beat b2">{"".join(b2)}</g>')
    c.add(f'<g class="beat b3">{"".join(b3)}</g>')
    c.add(f'<g class="beat b4">{"".join(b4)}</g>')
    return c.render()


# ---- data roles ------------------------------------------------------------------------


def data_roles(d: ReadmeData) -> str:
    order = ["data_engineer", "analytics_engineer", "data_analyst", "ml_engineer"]
    by = {r["role_family"]: r for r in d.data_roles}
    rows = [
        by.get(k, {"role_family": k, "open_roles": 0, "median_salary_usd": None}) for k in order
    ]
    top = max((int(r["open_roles"]) for r in rows), default=1) or 1
    c = Canvas(
        1000,
        480,
        "Open data roles today",
        "Bar chart, open roles on "
        + d.run_date
        + ": "
        + "; ".join(
            f"{ROLE_LABELS[r['role_family']]} {int(r['open_roles']):,} "
            f"(median US salary {fmt_usd_k(r['median_salary_usd'])})"
            for r in rows
        ),
    )
    c.add(c.text(40, 70, "Open data roles today", size=H1, font="sansb"))
    c.add(c.text(960, 70, "median pay", size=ROW, fill=MUTED, anchor="end"))
    for i, r in enumerate(rows):
        y = 108 + i * 78
        width = max(6.0, 300 * int(r["open_roles"]) / top)
        c.add(c.text(40, y + 40, ROLE_LABELS[r["role_family"]], size=ROW, fill=BODY))
        c.add(f'<rect class="bar g{i}" x="340" y="{y + 14}" width="{width:.1f}" height="34" rx="6" '
              f'fill="{GOOD}"/>')  # fmt: skip
        c.add(c.text(340 + width + 14, y + 42, f"{int(r['open_roles']):,}", size=ROW, font="sansb"))
        c.add(c.text(960, y + 42, fmt_usd_k(r["median_salary_usd"]), size=ROW, font="sansm",
                     fill=INK, anchor="end"))  # fmt: skip
    c.add(c.text(40, 450, f"US roles, middle of the published yearly range · {d.run_date}",
                 size=ROW, fill=MUTED))  # fmt: skip
    c.css.append(
        ".bar{transform-box:fill-box;transform-origin:left center}"
        + "".join(
            f".g{i}{{animation:gr{i} {LOOP_S}s ease-out infinite}}"
            f"@keyframes gr{i}{{0%,{i * 4}%{{transform:scaleX(0)}}{20 + i * 4}%,100%"
            "{transform:scaleX(1)}}"
            for i in range(4)
        )
    )
    c.css.append(start_on_final_frame(0.2 * LOOP_S + 3 * 0.04 * LOOP_S + 0.1))
    c.css.append(final_state_css(0))
    return c.render()


# ---- dbt lineage -----------------------------------------------------------------------

LAYERS = [("Raw inputs", ("source", "seed"), "inputs"), ("Cleaned", ("staging",), "models"),
          ("History", ("intermediate",), "models"), ("Published", ("marts",), "models")]  # fmt: skip


def lineage(manifest: dict[str, Any]) -> str:
    """The dbt project as four layers, each with its real number of inputs or models."""
    counts = [0] * len(LAYERS)
    for n in {**manifest.get("nodes", {}), **manifest.get("sources", {})}.values():
        rt = n.get("resource_type")
        if rt not in ("model", "seed", "source"):
            continue
        if rt == "model":
            layer = n.get("fqn", ["", ""])[1] if len(n.get("fqn", [])) > 2 else "marts"
        else:
            layer = rt
        for i, (_, kinds, _) in enumerate(LAYERS):
            if layer in kinds:
                counts[i] += 1
    tests = sum(1 for n in manifest.get("nodes", {}).values() if n.get("resource_type") == "test")
    c = Canvas(
        1000,
        480,
        "dbt model lineage",
        "The dbt project in four layers: "
        + ", then ".join(f"{counts[i]} {unit} in {name.lower()}" for i, (name, _, unit) in
                         enumerate(LAYERS))
        + f". {tests} data tests run on every build.",
    )  # fmt: skip
    c.add(c.text(40, 70, "Raw data to published tables, in 4 layers", size=H1, font="sansb"))
    box_w, gap = 200, 40
    for i, (name, _, unit) in enumerate(LAYERS):
        x = 40 + i * (box_w + gap)
        last = i == len(LAYERS) - 1
        c.add(card(x, 110, box_w, 280, stroke=ACCENT if last else LINE, sw=3 if last else 2))
        c.add(c.text(x + 20, 160, name, size=ROW, font="sansb"))
        c.add(c.text(x + 24, 236, str(counts[i]), size=64, font="sansb", fill=ACCENT))
        c.add(c.text(x + 24, 280, unit, size=ROW, fill=BODY))
        for j in range(min(counts[i], 8)):
            c.add(f'<rect x="{x + 24 + j * 20}" y="318" width="14" height="40" rx="4" '
                  f'fill="{GOOD if last else SOFT}"/>')  # fmt: skip
        if not last:
            ax = x + box_w + 8
            c.add(f'<path d="M{ax} 250 l14 0 m-7 -8 l8 8 l-8 8" fill="none" stroke="{MUTED}" '
                  'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')  # fmt: skip
    c.add(c.text(40, 446, f"{tests} data tests run on every build", size=ROW, fill=MUTED))
    return c.render()


# ---- entry point -----------------------------------------------------------------------


def manifest_json(dbt_dir: Path) -> dict[str, Any]:
    path = dbt_dir / "target" / "manifest.json"
    if not path.exists():
        from jobpipe.warehouse import run_dbt

        run_dbt(["parse"], data_dir=Path("data"), duckdb_path=Path("data/warehouse.duckdb"))
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def build_all(out_dir: Path = Path("assets"), root: Path = Path(".")) -> dict[str, int]:
    from jobpipe.warehouse import DBT_DIR

    d = load(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "hero.svg": hero(d),
        "hero-square.svg": hero(d, square=True),
        "pipeline.svg": pipeline(d),
        "maintenance-loop.svg": maintenance_loop(d),
        "data-roles.svg": data_roles(d),
        "dbt-lineage.svg": lineage(manifest_json(DBT_DIR)),
    }
    sizes: dict[str, int] = {}
    for name, svg in files.items():
        (out_dir / name).write_text(svg, encoding="utf-8")
        sizes[name] = len(svg.encode())
    return sizes
