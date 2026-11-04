"""Shared pieces for the README visuals: colours, embedded font subsets, text helpers.

A README SVG is loaded as an image, so it cannot fetch fonts or run scripts. Each SVG
therefore embeds WOFF2 subsets (only the glyphs it uses, base64) of Instrument Sans and
IBM Plex Mono (both SIL OFL 1.1), and animates with CSS only.
"""

from __future__ import annotations

import base64
import io
from collections import defaultdict
from html import escape
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "site" / "assets" / "fonts"
FONTS = {
    "sans": ("Instrument Sans", "instrument-sans-latin-400-normal.woff2", 400),
    "sansb": ("Instrument Sans", "instrument-sans-latin-600-normal.woff2", 600),
    "mono": ("IBM Plex Mono", "ibm-plex-mono-latin-400-normal.woff2", 400),
    "monob": ("IBM Plex Mono", "ibm-plex-mono-latin-500-normal.woff2", 500),
}

BG = "#0B1416"
PANEL = "#0F1C1E"
BORDER = "#1D3331"
TEXT = "#EAF2F0"
BODY = "#C9D8D5"
QUIET = "#7E9996"
TEAL = "#2FBFAE"
AMBER = "#E9A93C"

ICON_DIR = Path(__file__).parent / "icons"


def subset_woff2(path: Path, text: str) -> str:
    """Base64 WOFF2 containing only the glyphs needed for ``text``."""
    from fontTools import subset

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    font = subset.load_font(str(path), opts)
    sub = subset.Subsetter(opts)
    sub.populate(text=text + " 0123456789")
    sub.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, opts)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class Canvas:
    """Collects SVG elements and the characters each font must carry."""

    def __init__(self, width: int, height: int, title: str, desc: str) -> None:
        self.w, self.h = width, height
        self.title, self.desc = title, desc
        self.parts: list[str] = []
        self.chars: dict[str, set[str]] = defaultdict(set)
        self.css: list[str] = []

    def add(self, svg: str) -> None:
        self.parts.append(svg)

    def text(
        self,
        x: float,
        y: float,
        s: str,
        *,
        size: float,
        font: str = "sans",
        fill: str = TEXT,
        anchor: str = "start",
        cls: str = "",
        extra: str = "",
    ) -> str:
        self.chars[font].update(s)
        family, _, weight = FONTS[font]
        c = f' class="{cls}"' if cls else ""
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-weight="{weight}" '
            f'font-size="{size}" fill="{fill}" text-anchor="{anchor}"{c}{extra}>{escape(s)}</text>'
        )

    def render(self) -> str:
        faces = []
        for key, chars in self.chars.items():
            family, file, weight = FONTS[key]
            b64 = subset_woff2(FONT_DIR / file, "".join(sorted(chars)))
            faces.append(
                f"@font-face{{font-family:'{family}';font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
            )
        style = "".join(faces) + "".join(self.css)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'width="{self.w}" height="{self.h}" role="img" aria-labelledby="t d">'
            f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
            f"<style>{style}</style>"
            f'<rect width="{self.w}" height="{self.h}" rx="16" fill="{BG}"/>'
            + "".join(self.parts)
            + "</svg>"
        )


def icon(name: str, x: float, y: float, size: float, fill: str = BODY, cls: str = "") -> str:
    """A Simple Icons glyph (CC0) scaled into a size x size box at (x, y)."""
    svg = (ICON_DIR / f"{name}.svg").read_text()
    start = svg.index(' d="') + 4
    d = svg[start : svg.index('"', start)]
    c = f' class="{cls}"' if cls else ""
    return (
        f'<g transform="translate({x:.1f},{y:.1f}) scale({size / 24:.4f})"{c}>'
        f'<path d="{d}" fill="{fill}"/></g>'
    )


def beats_css(n: int, loop_s: float, hold_s: float = 2.6, fade: float = 0.35) -> str:
    """CSS for n sequential beats (classes .b1..bn) in one loop; the last beat holds.

    The final frame is also the still: see ``start_on_final_frame`` and ``final_state_css``.
    """
    span = (loop_s - hold_s) / (n - 1) if n > 1 else loop_s
    css = [f".beat{{animation:{loop_s}s linear infinite}}"]
    for i in range(1, n + 1):
        start = (i - 1) * span
        end = start + span if i < n else loop_s
        a, b = start / loop_s * 100, (start + fade) / loop_s * 100
        c, d = (end - fade) / loop_s * 100, end / loop_s * 100
        if i < n:
            frames = (
                f"0%{{opacity:0}}{a:.2f}%{{opacity:0}}{b:.2f}%{{opacity:1}}"
                f"{c:.2f}%{{opacity:1}}{d:.2f}%{{opacity:0}}100%{{opacity:0}}"
            )
            css.append(f".b{i}{{opacity:0;animation-name:k{i}}}@keyframes k{i}{{{frames}}}")
        else:
            frames = f"0%{{opacity:0}}{a:.2f}%{{opacity:0}}{b:.2f}%{{opacity:1}}100%{{opacity:1}}"
            css.append(f".b{i}{{opacity:1;animation-name:k{i}}}@keyframes k{i}{{{frames}}}")
    return "".join(css)


def final_beat_time(n: int, loop_s: float, hold_s: float = 2.6, fade: float = 0.35) -> float:
    """Seconds into the loop at which the last beat is fully shown."""
    span = (loop_s - hold_s) / (n - 1) if n > 1 else loop_s
    return (n - 1) * span + fade + 0.05


def start_on_final_frame(seconds: float) -> str:
    """Shift every animation so that t = 0 shows the final frame.

    Renderers that never advance time (thumbnails, image previews, some README viewers)
    then show the result instead of the first beat; the loop continues from there.
    """
    return f"*{{animation-delay:-{seconds:.2f}s!important}}"


def final_state_css(n_beats: int = 0, extra: str = "") -> str:
    """Under reduced motion: no animation, and every animated element takes its final state."""
    beats = "".join(f".b{i}{{opacity:0!important}}" for i in range(1, n_beats))
    last = f".b{n_beats}{{opacity:1!important}}" if n_beats else ""
    return (
        "@media (prefers-reduced-motion: reduce){*{animation:none!important}"
        + beats
        + last
        + ".row{opacity:1!important}.bar{transform:none!important}"
        + f".st{{stroke:{TEAL}!important}}"
        + extra
        + "}"
    )


def fmt_usd_k(v: float | None) -> str:
    return "–" if v is None else f"${v / 1000:,.0f}k"
