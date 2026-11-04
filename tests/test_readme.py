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
    assert text.rstrip().endswith("[siddharthkumar.com](https://siddharthkumar.com)")
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
    assert sizes and min(sizes) >= 22
    assert "prefers-reduced-motion: reduce" in svg
    assert "<title" in svg and "<desc" in svg
    assert "http://" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "<script" not in svg
