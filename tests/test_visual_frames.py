"""Render each README visual in Chromium and check the frame a still capture shows.

1. With prefers-reduced-motion: reduce, every animated element must sit in its final
   state: the last beat visible, earlier beats hidden, bars full width, stage outlines
   lit, and the result number among the visible text.
2. Without reduced motion, at t ≈ 0 (what thumbnails and image previews capture), the
   same final frame must already be on screen.

Needs Playwright's Chromium (CI installs it; locally set CHROMIUM_PATH or run
`uv run playwright install chromium`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from jobpipe.readme_data import load
from jobpipe.visuals import build as visuals

playwright = pytest.importorskip("playwright.sync_api")

TEAL_RGB = "rgb(47, 191, 174)"

STATE_JS = """
() => {
  const vis = (el) => {
    for (let e = el; e && e.tagName !== 'svg'; e = e.parentElement) {
      if (parseFloat(getComputedStyle(e).opacity) < 0.99) return false;
    }
    return true;
  };
  const op = (e) => parseFloat(getComputedStyle(e).opacity);
  const beats = [...document.querySelectorAll('.beat')].map(op);
  const svg = document.querySelector('svg');
  const scale = svg.getBoundingClientRect().width / svg.viewBox.baseVal.width;
  const bars = [...document.querySelectorAll('.bar')].map(
    (b) => b.getBoundingClientRect().width / (parseFloat(b.getAttribute('width')) * scale));
  const strokes = [...document.querySelectorAll('.st')].map(s => getComputedStyle(s).stroke);
  const text = [...document.querySelectorAll('text')].filter(vis).map(t => t.textContent);
  return { beats, bars, strokes, text };
}
"""


def _browser(p: Any) -> Any:
    path = os.environ.get("CHROMIUM_PATH")
    try:
        return p.chromium.launch(executable_path=path or None)
    except Exception as exc:  # no browser installed locally
        pytest.skip(f"Chromium not available: {exc}")


@pytest.fixture(scope="module")
def svgs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = load()
    out = tmp_path_factory.mktemp("svg")
    files = {
        "hero": visuals.hero(d),
        "maintenance-loop": visuals.maintenance_loop(d),
        "data-roles": visuals.data_roles(d),
        "pipeline": visuals.pipeline(d),
    }
    paths = {}
    for name, svg in files.items():
        paths[name] = out / f"{name}.svg"
        paths[name].write_text(svg, encoding="utf-8")
    return paths


def _expected_number(name: str) -> str:
    d = load()
    if name == "hero":
        return f"{d.open_jobs:,}"
    if name == "maintenance-loop":
        ing = d.last_run.get("ingest") or {}
        return f"{int(ing.get('boards_ok') or 0):,} of"
    if name == "data-roles":
        top = max(d.data_roles, key=lambda r: int(r["open_roles"]))
        return f"{int(top['open_roles']):,}"
    return f"{d.companies:,} boards"


def _assert_final(name: str, state: dict[str, Any]) -> None:
    beats = state["beats"]
    if beats:
        assert beats[-1] == pytest.approx(1.0), f"{name}: last beat not visible {beats}"
        assert all(b == pytest.approx(0.0) for b in beats[:-1]), (
            f"{name}: early beat visible {beats}"
        )
    for ratio in state["bars"]:
        assert ratio == pytest.approx(1.0, abs=0.02), f"{name}: bar not full width {state['bars']}"
    for stroke in state["strokes"]:
        assert stroke == TEAL_RGB, f"{name}: stage outline not lit {state['strokes']}"
    joined = " ".join(state["text"])
    assert _expected_number(name) in joined, f"{name}: result number missing from {joined!r}"


@pytest.mark.parametrize("name", ["hero", "maintenance-loop", "data-roles", "pipeline"])
def test_reduced_motion_shows_final_frame(svgs: dict[str, Path], name: str) -> None:
    with playwright.sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(reduced_motion="reduce")
        page.goto(svgs[name].resolve().as_uri())
        page.wait_for_timeout(300)
        _assert_final(name, page.evaluate(STATE_JS))
        browser.close()


@pytest.mark.parametrize("name", ["hero", "maintenance-loop", "data-roles", "pipeline"])
def test_first_moment_is_the_final_frame(svgs: dict[str, Path], name: str) -> None:
    with playwright.sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(reduced_motion="no-preference")
        page.goto(svgs[name].resolve().as_uri())
        page.evaluate(
            "() => document.getAnimations().forEach(a => { a.pause(); a.currentTime = 0; })"
        )
        page.wait_for_timeout(100)
        _assert_final(name, page.evaluate(STATE_JS))
        browser.close()
