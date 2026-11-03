import re
from datetime import date

import pytest

from jobpipe.site import build

BG, PANEL = "#0B1416", "#0F1C1E"
TEXTS = {"main": "#EAF2F0", "body": "#C9D8D5", "quiet": "#7E9996", "teal": "#2FBFAE",
         "amber": "#E9A93C"}  # fmt: skip


def _lum(hex_: str) -> float:
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("surface", [BG, PANEL])
@pytest.mark.parametrize("name", list(TEXTS))
def test_text_contrast_at_least_4_5(name: str, surface: str) -> None:
    assert contrast(TEXTS[name], surface) >= 4.5


def _data() -> dict[str, object]:
    d = date(2026, 11, 4)
    return {
        "latest": d,
        "kpi": (1500, 60000, 0.82, 4000, 0.55, 0.2),
        "daily": [(d, 60000)],
        "flows": [(d, 0, 0)],
        "families": [("software_engineer", 20000), ("data_engineer", 1500)],
        "providers": [("greenhouse", 900, 40000), ("lever", 300, 10000), ("ashby", 300, 10000)],
        "data_by_family": [("data_engineer", 1500, 180000.0, 0.3)],
        "data_daily": [(d, "data_engineer", 1500)],
        "data_seniority": [("senior", 800)],
        "data_states": [("CA", 400)],
        "salary": [("data_engineer", 150000.0, 180000.0, 210000.0, 700)],
        "salary_seniority": [("senior", 160000.0, 190000.0, 220000.0, 3000)],
        "days_bands": [("0-7", 0, 0.0, None)],
        "age_bands": [("0-7", 100), ("8-14", 50)],
        "age_median": 21,
        "companies": [("Acme <script>", "greenhouse", 10, 9)],
    }


def test_render_has_no_external_scripts_and_escapes() -> None:
    html = build.render(_data(), {"days_running": 3, "missed_runs": 0, "first_run": "2026-11-02"})
    assert "<script" not in html.replace("&lt;script", "")
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external == ["https://siddharthkumar.com"]
    assert 'lang="en"' in html and 'name="viewport"' in html and 'name="description"' in html
    assert "Acme &lt;script&gt;" in html
