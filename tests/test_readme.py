"""README and visuals are rendered from real run outputs; check they render cleanly."""

import re
from pathlib import Path

import pytest

from jobpipe import readme
from jobpipe.readme_data import load, parse_incidents
from jobpipe.visuals import build as visuals


def test_readme_renders_without_placeholders(tmp_path: Path) -> None:
    out = tmp_path / "README.md"
    text = readme.render(out=out)
    assert readme.check_rendered(text) == []
    order = [
        "# US tech hiring data, checked every day", "## What you get", "### What changed today",
        "## Why you can trust this data", "## How it works", "## What broke and how I fixed it",
        "## Who uses data like this", "## Want this for your own sites?", "## FAQ",
        "## Data dictionary", "<summary><b>For engineers</b></summary>",
        "## Data use and compliance", "## License",
    ]  # fmt: skip
    positions = [text.index(h) for h in order]
    assert positions == sorted(positions)
    assert text.rstrip().endswith(
        "Built and maintained by Siddharth Kumar, Founder of SteadyData · "
        "[steadydata.co](https://steadydata.co)"
    )
    old_email = "hello@" + "siddharthkumar.com"
    for banned in (old_email, "20 " + "to 50", "our team", "AI-powered"):
        assert banned not in text
    assert "No sales calls needed. Everything by email." in text
    assert "Up to 1,000 real rows" in text
    assert "https://steadydata.co/contact/" in text and "https://steadydata.co/pricing/" in text
    assert "Daily runs delivered:" in text
    # every image has meaningful alt text
    for alt in re.findall(r"!\[([^\]]*)\]\(assets/", text):
        assert len(alt) > 20


def test_check_rendered_catches_leftovers() -> None:
    assert readme.check_rendered("hello {{ x }}")
    assert readme.check_rendered("<!-- note -->")
    assert readme.check_rendered("[a]()")
    assert readme.check_rendered("all good") == []


def test_incidents_have_plain_words() -> None:
    incidents = parse_incidents(Path("docs/incidents.md"))
    assert incidents
    for inc in incidents:
        assert inc.date and inc.title and inc.plain and inc.fix_plain


@pytest.mark.parametrize("name", ["hero", "pipeline", "maintenance_loop", "data_roles"])
def test_visuals_size_text_and_motion(name: str) -> None:
    svg = getattr(visuals, name)(load())
    assert len(svg.encode()) < 1_000_000
    sizes = [float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)]
    assert sizes and min(sizes) >= 30  # row text >= 30 px in the 1000-px viewBox
    assert "Plus Jakarta Sans" in svg and "Instrument Sans" not in svg
    assert "prefers-reduced-motion: reduce" in svg
    assert "<title" in svg and "<desc" in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "<script" not in svg


def test_second_source_shows_real_result_and_flat_badges(tmp_path: Path) -> None:
    text = readme.render(out=tmp_path / "README.md")
    assert "shown here after each run" not in text
    assert re.search(r"Latest run \(\d{4}-\d{2}-\d{2}\): \d+ of \d+ matched", text)
    assert "flat-square" not in text
    assert "img.shields.io/endpoint?url=" in text


def test_lineage_uses_phone_sizes_and_real_counts() -> None:
    manifest = {
        "nodes": {
            "model.a": {
                "resource_type": "model",
                "fqn": ["p", "staging", "stg_a"],
                "name": "stg_a",
            },
            "model.b": {"resource_type": "model", "fqn": ["p", "marts", "b"], "name": "b"},
            "test.x": {"resource_type": "test"},
        },
        "sources": {"source.r": {"resource_type": "source", "name": "r"}},
    }
    svg = visuals.lineage(manifest)
    assert 'viewBox="0 0 1000 ' in svg
    sizes = [float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)]
    assert min(sizes) >= 30
    assert "1 data tests run on every build" in svg


def test_svg_text_colours_meet_contrast() -> None:
    from jobpipe.visuals import base

    for name in ("hero", "pipeline", "maintenance_loop", "data_roles"):
        svg = getattr(visuals, name)(load())
        for fill in set(re.findall(r'<text [^>]*fill="(#[0-9A-Fa-f]{6})"', svg)):
            assert fill not in (base.GOOD, base.LOOK), f"{name}: data colour {fill} used as text"
