"""Small server-side chart builders: HTML/CSS bars and inline SVG lines, no JavaScript.

Every mark carries a hover tooltip (SVG <title> or a title attribute) and every chart has a
table view, so nothing depends on colour or on scripts.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape


def fmt_int(v: float | int | None) -> str:
    return "–" if v is None else f"{round(v):,}"


def fmt_usd(v: float | None) -> str:
    if v is None:
        return "–"
    return f"${v / 1000:,.0f}k"


def fmt_pct(v: float | None, digits: int = 0) -> str:
    return "–" if v is None else f"{v * 100:.{digits}f}%"


def hbars(
    rows: Sequence[tuple[str, float, str]],
    *,
    caption: str,
    tone: str = "teal",
    highlight: set[str] | None = None,
) -> str:
    """Horizontal bars: (label, value, value_text). Highlighted labels use amber."""
    if not rows:
        return '<p class="empty">No data yet.</p>'
    top = max(v for _, v, _ in rows) or 1
    items = []
    for label, value, text in rows:
        cls = "amber" if highlight and label in highlight else tone
        width = max(0.5, 100 * value / top)
        items.append(
            f'<li><span class="bar-label">{escape(label)}</span>'
            f'<span class="bar-track"><span class="bar {cls}" style="width:{width:.1f}%" '
            f'title="{escape(label)}: {escape(text)}"></span></span>'
            f'<span class="bar-value">{escape(text)}</span></li>'
        )
    return (
        f'<figure class="chart"><figcaption>{escape(caption)}</figcaption>'
        f'<ul class="hbars" role="list">{"".join(items)}</ul></figure>'
    )


def ranges(
    rows: Sequence[tuple[str, float, float, float, int]], *, caption: str, lo: float, hi: float
) -> str:
    """Salary range rows: (label, p25, median, p75, n) on a shared scale lo..hi."""
    if not rows:
        return '<p class="empty">Not enough salaries published yet.</p>'
    span = (hi - lo) or 1

    def pos(v: float) -> float:
        return 100 * (v - lo) / span

    items = []
    for label, p25, med, p75, n in rows:
        tip = f"{label}: p25 {fmt_usd(p25)}, median {fmt_usd(med)}, p75 {fmt_usd(p75)} (n={n:,})"
        items.append(
            f'<li><span class="bar-label">{escape(label)}</span>'
            f'<span class="range-track" title="{escape(tip)}">'
            f'<span class="range teal" style="left:{pos(p25):.1f}%;'
            f'width:{pos(p75) - pos(p25):.1f}%"></span>'
            f'<span class="median" style="left:{pos(med):.1f}%"></span></span>'
            f'<span class="bar-value">{fmt_usd(med)} <span class="quiet">n={n:,}</span></span></li>'
        )
    ticks = "".join(
        f'<span style="left:{pos(t):.1f}%">{fmt_usd(t)}</span>' for t in _nice_ticks(lo, hi, 4)
    )
    return (
        f'<figure class="chart"><figcaption>{escape(caption)}</figcaption>'
        f'<ul class="hbars ranges" role="list">{"".join(items)}</ul>'
        f'<div class="range-axis" aria-hidden="true"><span class="bar-label"></span>'
        f'<span class="range-ticks">{ticks}</span><span class="bar-value"></span></div></figure>'
    )


def _nice_ticks(lo: float, hi: float, n: int) -> list[float]:
    step = (hi - lo) / n
    mag = 10 ** len(str(int(step))) / 10 if step >= 1 else 1
    step = max(mag, round(step / mag) * mag)
    start = (lo // step + 1) * step
    out = []
    t = start
    while t < hi:
        out.append(t)
        t += step
    return out


def columns(rows: Sequence[tuple[str, float, str]], *, caption: str, tone: str = "teal") -> str:
    """Vertical columns (histogram bands): (label, value, value_text)."""
    if not rows or not any(v for _, v, _ in rows):
        return '<p class="empty">No data yet.</p>'
    top = max(v for _, v, _ in rows) or 1
    cols = "".join(
        f'<li><span class="col-value">{escape(text)}</span>'
        f'<span class="col-track"><span class="col {tone}" '
        f'style="height:{max(1, 100 * v / top):.1f}%" title="{escape(label)}: {escape(text)}">'
        f"</span></span>"
        f'<span class="col-label">{escape(label)}</span></li>'
        for label, v, text in rows
    )
    return (
        f'<figure class="chart"><figcaption>{escape(caption)}</figcaption>'
        f'<ol class="columns" role="list">{cols}</ol></figure>'
    )


def line(
    series: Sequence[tuple[str, Sequence[tuple[str, float]], str]],
    *,
    caption: str,
    height: int = 200,
    width: int = 640,
) -> str:
    """Line chart in SVG. series: (name, [(x_label, y)], tone). ≥ 2 series get a legend."""
    pts_all = [y for _, pts, _ in series for _, y in pts]
    if not pts_all:
        return '<p class="empty">No data yet.</p>'
    xs = list(dict.fromkeys(x for _, pts, _ in series for x, _ in pts))
    if len(xs) < 2:
        latest = "; ".join(
            f"{escape(name)} {fmt_int(pts[-1][1])}" for name, pts, _ in series if pts
        )
        return (
            f'<figure class="chart"><figcaption>{escape(caption)}</figcaption>'
            f'<p class="empty">The line starts after the second daily run. '
            f"{escape(xs[0])}: {latest}.</p></figure>"
        )
    ymax = max(pts_all) or 1
    ymin = 0.0
    pad_l, pad_r, pad_t, pad_b = 8, 8, 10, 10
    w, h = width - pad_l - pad_r, height - pad_t - pad_b

    def px(i: int) -> float:
        return pad_l + (w * i / (len(xs) - 1) if len(xs) > 1 else w / 2)

    def py(v: float) -> float:
        return pad_t + h - h * (v - ymin) / (ymax - ymin)

    grid = "".join(
        f'<line class="grid" x1="{pad_l}" x2="{width - pad_r}" y1="{py(ymax * f):.1f}" '
        f'y2="{py(ymax * f):.1f}"/>'
        for f in (0, 0.5, 1)
    )
    paths, dots = [], []
    for name, pts, tone in series:
        lookup = dict(pts)
        coords = [(px(i), py(lookup[x]), x, lookup[x]) for i, x in enumerate(xs) if x in lookup]
        if len(coords) > 1:
            d = " ".join(
                f"{'M' if k == 0 else 'L'}{cx:.1f},{cy:.1f}"
                for k, (cx, cy, _, _) in enumerate(coords)
            )
            paths.append(f'<path class="line {tone}" d="{d}"/>')
        for cx, cy, x, y in coords:
            dots.append(
                f'<circle class="dot {tone}" cx="{cx:.1f}" cy="{cy:.1f}" r="4">'
                f"<title>{escape(name)} · {escape(x)}: {fmt_int(y)}</title></circle>"
            )
    first, last = xs[0], xs[-1]
    # Axis labels are HTML so they stay readable when the SVG scales down on phones.
    axis = (
        f'<div class="axis-row" aria-hidden="true"><span>{escape(first)}</span>'
        f"<span>max {fmt_int(ymax)}</span><span>{escape(last)}</span></div>"
    )
    legend = ""
    if len(series) > 1:
        legend = (
            '<ul class="legend" role="list">'
            + "".join(
                f'<li><span class="swatch {tone}"></span>{escape(name)}</li>'
                for name, _, tone in series
            )
            + "</ul>"
        )
    label = escape(caption)
    return (
        f'<figure class="chart"><figcaption>{label}</figcaption>{legend}'
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{label}" '
        f'preserveAspectRatio="xMidYMid meet">{grid}{"".join(paths)}{"".join(dots)}</svg>'
        f"{axis}</figure>"
    )


def table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], *, caption: str, numeric: set[int]
) -> str:
    head = "".join(
        f'<th scope="col"{" class=num" if i in numeric else ""}>{escape(h)}</th>'
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td{' class=num' if i in numeric else ''}>{escape(c)}</td>" for i, c in enumerate(r)
        )
        + "</tr>"
        for r in rows
    )
    return (
        f'<details class="table-view"><summary>{escape(caption)}</summary>'
        f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div></details>"
    )
