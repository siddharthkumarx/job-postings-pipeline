"""Animated README visuals, regenerated from real run outputs on every run.

hero.svg            problem → the run with real rows → the result (one big number)
pipeline.svg        source → collect → check → store → deliver, with tool logos
maintenance-loop.svg  daily runs → a real incident → fixed → data keeps arriving
data-roles.svg      open data roles today (real counts and median salaries)
dbt-lineage.svg     the dbt model graph, read from dbt's manifest.json
hero-square.svg     1080x1080 hero for the LinkedIn video (text ≥ 40 px)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

from jobpipe.readme_data import ROLE_LABELS, Incident, ReadmeData, load, short_title
from jobpipe.visuals.base import (
    AMBER,
    BODY,
    BORDER,
    PANEL,
    QUIET,
    TEAL,
    TEXT,
    Canvas,
    beats_css,
    fmt_usd_k,
    icon,
)

LOOP_S = 10.0


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


# ---- hero ------------------------------------------------------------------------------


def hero(d: ReadmeData, square: bool = False) -> str:
    w, h = (1080, 1080) if square else (1000, 460)
    c = Canvas(
        w,
        h,
        f"{d.companies:,} companies, {d.open_jobs:,} open jobs, checked every day",
        f"Animated: open tech jobs are spread across {d.companies:,} company job boards; one "
        f"daily run collects them into a single table; result: {d.open_jobs:,} open jobs at "
        f"{d.companies:,} US tech companies (latest run {d.run_date}).",
    )
    c.css.append(beats_css(3, LOOP_S))
    cx = w / 2
    rows = d.sample[:3]
    if not square:
        b1 = [
            c.text(cx, 185, "Open tech jobs are spread across", size=40, font="sansb", anchor="middle"),
            c.text(cx, 240, f"{d.companies:,} separate company job boards.", size=40, font="sansb",
                   anchor="middle", fill=AMBER),
            c.text(cx, 300, "Checking them by hand takes days.", size=26, fill=BODY, anchor="middle"),
        ]  # fmt: skip
        b2 = [c.text(40, 70, "One run every morning", size=26, fill=BODY)]
        for i, name in enumerate(("Greenhouse", "Lever", "Ashby")):
            y = 110 + i * 80
            b2.append(f'<rect x="40" y="{y}" width="190" height="56" rx="10" fill="{PANEL}" '
                      f'stroke="{BORDER}" stroke-width="2"/>')  # fmt: skip
            b2.append(c.text(135, y + 36, name, size=24, fill=BODY, anchor="middle"))
            b2.append(f'<path class="flow" d="M232 {y + 28} C 270 {y + 28}, 262 218, 300 218" '
                      f'stroke="{TEAL}" stroke-width="3" fill="none" stroke-dasharray="6 10"/>')  # fmt: skip
        b2 += [
            f'<rect x="300" y="160" width="200" height="116" rx="14" fill="{PANEL}" stroke="{TEAL}" stroke-width="2"/>',
            c.text(400, 210, "check + clean", size=24, font="sansb", anchor="middle"),
            c.text(400, 246, "every row", size=22, font="mono", fill=QUIET, anchor="middle"),
            f'<path class="flow" d="M502 218 L 556 218" stroke="{TEAL}" stroke-width="3" fill="none" stroke-dasharray="6 10"/>',
        ]  # fmt: skip
        for i, r in enumerate(rows):
            y = 120 + i * 70
            b2.append(f'<g class="row r{i + 1}"><rect x="560" y="{y}" width="400" height="56" rx="10" '
                      f'fill="{PANEL}" stroke="{BORDER}" stroke-width="2"/>'
                      + c.text(578, y + 36, r["company_name"][:18], size=24, font="sansb")
                      + c.text(942, y + 36, _salary(r), size=22, font="mono", fill=TEAL, anchor="end")
                      + "</g>")  # fmt: skip
        b2.append(
            c.text(560, 350, f"real rows, run of {d.run_date}", size=22, font="mono", fill=QUIET)
        )
        b3 = [
            c.text(cx, 215, f"{d.open_jobs:,}", size=120, font="sansb", fill=TEAL, anchor="middle"),
            c.text(cx, 292, f"open jobs at {d.companies:,} US tech companies", size=42, anchor="middle"),
            c.text(cx, 352, f"checked every day · latest run {d.run_date}", size=28, font="mono",
                   fill=QUIET, anchor="middle"),
        ]  # fmt: skip
    else:
        b1 = [
            c.text(cx, 420, "Open tech jobs are", size=64, font="sansb", anchor="middle"),
            c.text(cx, 500, "spread across", size=64, font="sansb", anchor="middle"),
            c.text(cx, 600, f"{d.companies:,} job boards.", size=72, font="sansb", fill=AMBER,
                   anchor="middle"),
        ]  # fmt: skip
        b2 = [c.text(cx, 180, "One run every morning", size=48, fill=BODY, anchor="middle")]
        for i, r in enumerate(rows):
            y = 300 + i * 190
            b2.append(f'<g class="row r{i + 1}"><rect x="90" y="{y}" width="900" height="150" rx="18" '
                      f'fill="{PANEL}" stroke="{BORDER}" stroke-width="3"/>'
                      + c.text(130, y + 66, r["company_name"][:22], size=48, font="sansb")
                      + c.text(130, y + 120, short_title(r, 24), size=40, fill=BODY)
                      + c.text(950, y + 66, _salary(r), size=40, font="mono", fill=TEAL, anchor="end")
                      + "</g>")  # fmt: skip
        b2.append(c.text(cx, 930, f"real rows · {d.run_date}", size=40, font="mono", fill=QUIET,
                         anchor="middle"))  # fmt: skip
        b3 = [
            c.text(cx, 520, f"{d.open_jobs:,}", size=200, font="sansb", fill=TEAL, anchor="middle"),
            c.text(cx, 620, "open jobs at", size=56, anchor="middle"),
            c.text(cx, 690, f"{d.companies:,} US tech companies", size=56, anchor="middle"),
            c.text(cx, 790, f"checked every day · {d.run_date}", size=44, font="mono", fill=QUIET,
                   anchor="middle"),
        ]  # fmt: skip
    c.css.append(
        ".flow{animation:dash 1.2s linear infinite}@keyframes dash{to{stroke-dashoffset:-32}}"
        + "".join(
            f".r{i}{{animation:rw{i} {LOOP_S}s linear infinite}}"
            f"@keyframes rw{i}{{0%,{40 + i * 5}%{{opacity:0}}{43 + i * 5}%,100%{{opacity:1}}}}"
            for i in (1, 2, 3)
        )
    )
    c.add(f'<g class="beat b1">{"".join(b1)}</g>')
    c.add(f'<g class="beat b2">{"".join(b2)}</g>')
    c.add(f'<g class="beat b3">{"".join(b3)}</g>')
    return c.render()


# ---- pipeline --------------------------------------------------------------------------

STAGES: list[tuple[str, str, list[str]]] = [
    ("Source", "3 job boards", []),
    ("Collect", "Python", ["python", "uv", "pydantic"]),
    ("Check", "dbt + pytest", ["pytest"]),
    ("Store", "DuckDB", ["duckdb", "apacheparquet"]),
    ("Deliver", "GitHub, HF", ["github", "githubactions", "huggingface"]),
]


def pipeline(d: ReadmeData) -> str:
    c = Canvas(
        1000,
        400,
        "How it works: source, collect, check, store, deliver",
        "Animated pipeline: public job boards (Greenhouse, Lever, Ashby) are collected with "
        "Python, checked with dbt tests and pytest, stored in DuckDB and Parquet, and delivered "
        f"through GitHub and Hugging Face. {d.companies:,} job boards, about "
        f"{d.minutes:.0f} minutes, every morning.",
    )
    xs = [100, 300, 500, 700, 900]
    loop = 8.0
    for i in range(len(xs)):
        a = i * 1.0 / loop * 100
        b = (i * 1.0 + 0.3) / loop * 100
        c.css.append(
            f".s{i}{{animation:sk{i} {loop}s linear infinite}}"
            f"@keyframes sk{i}{{0%,{a:.1f}%{{stroke:{BORDER}}}{b:.1f}%,100%{{stroke:{TEAL}}}}}"
        )
    c.css.append(
        ".dot{animation:mv 1.6s linear infinite}@keyframes mv{from{transform:translateX(0)}"
        "to{transform:translateX(50px)}}"
        "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    )
    for i, (label, caption, icons) in enumerate(STAGES):
        x = xs[i]
        c.add(f'<rect class="s{i}" x="{x - 75}" y="50" width="150" height="130" rx="18" '
              f'fill="{PANEL}" stroke="{TEAL}" stroke-width="3"/>')  # fmt: skip
        if not icons:  # the three sources: a simple list glyph
            for j in range(3):
                c.add(
                    f'<rect x="{x - 40}" y="{82 + j * 24}" width="80" height="12" rx="6" fill="{BODY}"/>'
                )
        elif label == "Check":
            c.add(icon("pytest", x - 50, 95, 40))
            c.add(c.text(x + 30, 126, "dbt", size=26, font="monob", fill=BODY, anchor="middle"))
        else:
            n = len(icons)
            size = 40 if n <= 2 else 34
            total = n * size + (n - 1) * 12
            for j, name in enumerate(icons):
                c.add(icon(name, x - total / 2 + j * (size + 12), 115 - size / 2, size))
        c.add(c.text(x, 225, label, size=26, font="sansb", anchor="middle"))
        c.add(c.text(x, 260, caption, size=22, font="mono", fill=QUIET, anchor="middle"))
        if i < len(xs) - 1:
            c.add(
                f'<line x1="{x + 77}" y1="115" x2="{x + 123}" y2="115" stroke="{BORDER}" stroke-width="3"/>'
            )
            c.add(f'<circle class="dot" cx="{x + 75}" cy="115" r="6" fill="{TEAL}"/>')
    c.add(c.text(500, 340, f"{d.companies:,} job boards · about {d.minutes:.0f} minutes · "
                           "every morning at 07:41 UTC", size=24, fill=BODY, anchor="middle"))  # fmt: skip
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
    rows_today = int(d.last_run.get("postings_listed") or d.open_jobs)
    c = Canvas(
        1000,
        420,
        "Maintenance loop: daily runs, a real incident, fixed, data keeps arriving",
        f"Animated: one square per pipeline run ({len(d.runs)} so far). "
        + (f"Incident {inc.date}: {inc.plain} Fix: {inc.fix_plain} " if inc else "")
        + f"Latest run ({d.run_date}) read every tracked job board and collected "
        f"{rows_today:,} jobs.",
    )
    c.css.append(beats_css(4, LOOP_S))
    size, gap = 44, 14
    total = len(attempts) * size + (len(attempts) - 1) * gap
    x0 = 500 - total / 2
    for i, r in enumerate(attempts):
        status = r.get("status")
        color = TEAL if status == "published" else AMBER
        hl = run_id is not None and r.get("actions_run_id") == run_id
        cls = " hl" if hl else ""
        c.add(f'<rect class="sq{cls}" x="{x0 + i * (size + gap):.1f}" y="60" width="{size}" '
              f'height="{size}" rx="8" fill="{color}"/>')  # fmt: skip
    c.css.append(f".hl{{stroke:{TEXT};stroke-width:3}}")
    b1 = [
        c.text(500, 220, "A fresh run every morning.", size=36, font="sansb", anchor="middle"),
        c.text(500, 268, f"{len(d.runs)} runs so far · amber = held or failed", size=24,
               font="mono", fill=QUIET, anchor="middle"),
    ]  # fmt: skip
    b2, b3 = [], []
    if inc:
        b2.append(c.text(500, 200, f"{inc.date}: {inc.title}", size=28, font="sansb", fill=AMBER,
                         anchor="middle"))  # fmt: skip
        for j, line in enumerate(_wrap(inc.plain, 66)):
            b2.append(c.text(500, 250 + j * 36, line, size=24, fill=BODY, anchor="middle"))
        b3.append(c.text(500, 200, "Fixed the same day.", size=30, font="sansb", fill=TEAL,
                         anchor="middle"))  # fmt: skip
        for j, line in enumerate(_wrap(inc.fix_plain, 66)):
            b3.append(c.text(500, 250 + j * 36, line, size=24, fill=BODY, anchor="middle"))
    ing = d.last_run.get("ingest") or {}
    ok, total = int(ing.get("boards_ok") or 0), int(ing.get("boards") or d.companies)
    b4 = [
        c.text(500, 250, f"{ok:,} of {total:,}", size=88, font="sansb", fill=TEAL, anchor="middle"),
        c.text(500, 305, f"job boards read in the latest run · {d.run_date}", size=26,
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
        420,
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
    c.add(c.text(40, 62, "Open data roles today", size=30, font="sansb"))
    c.add(c.text(960, 62, f"run of {d.run_date}", size=22, font="mono", fill=QUIET, anchor="end"))
    for i, r in enumerate(rows):
        y = 110 + i * 72
        width = max(6.0, 400 * int(r["open_roles"]) / top)
        c.add(c.text(40, y + 30, ROLE_LABELS[r["role_family"]], size=24, fill=BODY))
        c.add(f'<rect class="bar g{i}" x="290" y="{y + 8}" width="{width:.1f}" height="30" rx="4" '
              f'fill="{TEAL}"/>')  # fmt: skip
        c.add(c.text(290 + width + 14, y + 32, f"{int(r['open_roles']):,}", size=24, font="monob"))
        c.add(c.text(960, y + 32, f"median {fmt_usd_k(r['median_salary_usd'])}", size=22,
                     font="mono", fill=QUIET, anchor="end"))  # fmt: skip
    c.add(c.text(40, 400, "Median: middle of the published US salary range, per year.", size=22,
                 fill=QUIET))  # fmt: skip
    c.css.append(
        ".bar{transform-box:fill-box;transform-origin:left center}"
        + "".join(
            f".g{i}{{animation:gr{i} {LOOP_S}s ease-out infinite}}"
            f"@keyframes gr{i}{{0%,{i * 4}%{{transform:scaleX(0)}}{20 + i * 4}%,100%"
            "{transform:scaleX(1)}}"
            for i in range(4)
        )
        + "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    )
    return c.render()


# ---- dbt lineage -----------------------------------------------------------------------

LAYERS = [("Raw inputs", ("source", "seed")), ("Cleaned", ("staging",)),
          ("History", ("intermediate",)), ("Published", ("marts",))]  # fmt: skip


def lineage(manifest: dict[str, Any]) -> str:
    nodes: dict[str, dict[str, Any]] = {}
    for uid, n in {**manifest.get("nodes", {}), **manifest.get("sources", {})}.items():
        rt = n.get("resource_type")
        if rt not in ("model", "seed", "source"):
            continue
        if rt == "model":
            layer = n.get("fqn", ["", ""])[1] if len(n.get("fqn", [])) > 2 else "marts"
        else:
            layer = rt
        name = n.get("name", uid)
        for p in ("stg_", "int_", "mart_"):
            name = name.removeprefix(p)
        if rt == "source":
            name = f"{name} (raw)"
        nodes[uid] = {
            "name": name,
            "layer": layer,
            "deps": n.get("depends_on", {}).get("nodes", []),
        }
    cols: list[list[str]] = [[] for _ in LAYERS]
    for uid, n in sorted(nodes.items(), key=lambda kv: kv[1]["name"]):
        for i, (_, kinds) in enumerate(LAYERS):
            if n["layer"] in kinds:
                cols[i].append(uid)
    box_w, box_h, gap_y, col_gap = 360, 58, 22, 110
    w = 60 * 2 + len(cols) * box_w + (len(cols) - 1) * col_gap
    max_rows = max(len(col) for col in cols)
    h = 150 + max_rows * (box_h + gap_y) + 40
    c = Canvas(
        w,
        h,
        "dbt model lineage",
        "Graph of the dbt project: raw inputs (bronze files and seed tables) feed cleaned "
        "staging models, then history models, then the published marts.",
    )
    pos: dict[str, tuple[float, float]] = {}
    for i, col in enumerate(cols):
        x = 60 + i * (box_w + col_gap)
        c.add(c.text(x, 80, LAYERS[i][0], size=34, font="sansb"))
        top = 130 + (max_rows - len(col)) * (box_h + gap_y) / 2
        for j, uid in enumerate(col):
            y = top + j * (box_h + gap_y)
            pos[uid] = (x, y)
    edges = []
    for uid, n in nodes.items():
        if uid not in pos:
            continue
        x2, y2 = pos[uid]
        for dep in n["deps"]:
            if dep in pos:
                x1, y1 = pos[dep]
                sx, sy, ex, ey = x1 + box_w, y1 + box_h / 2, x2, y2 + box_h / 2
                mx = (sx + ex) / 2
                edges.append(f'<path class="edge" d="M{sx:.0f} {sy:.0f} C {mx:.0f} {sy:.0f}, '
                             f'{mx:.0f} {ey:.0f}, {ex:.0f} {ey:.0f}" stroke="{BORDER}" '
                             'stroke-width="3" fill="none"/>')  # fmt: skip
    c.add("".join(edges))
    for uid, (bx, by) in pos.items():
        n = nodes[uid]
        stroke = TEAL if n["layer"] == "marts" else BORDER
        c.add(f'<rect x="{bx}" y="{by}" width="{box_w}" height="{box_h}" rx="10" fill="{PANEL}" '
              f'stroke="{stroke}" stroke-width="2"/>')  # fmt: skip
        c.add(c.text(bx + 18, by + 38, n["name"], size=26, font="mono", fill=TEXT))
    c.css.append(
        ".edge{stroke-dasharray:8 10;animation:fl 2s linear infinite}"
        "@keyframes fl{to{stroke-dashoffset:-36}}"
        "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    )
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
