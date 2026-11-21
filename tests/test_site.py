import re
from datetime import date

import pytest

from jobpipe.site import build

# Light system v1 (D-018): every text colour on every surface it is used on.
PAGE, ALT, CARD, SOFT = "#FFFFFF", "#F3F8F7", "#FFFFFF", "#E3F3F0"
TEXTS = {"ink": "#0B1416", "body": "#3D4B49", "muted": "#5F716E", "accent": "#0B7468",
         "accent_hover": "#095E55"}  # fmt: skip


def _lum(hex_: str) -> float:
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("surface", [PAGE, ALT, CARD])
@pytest.mark.parametrize("name", list(TEXTS))
def test_text_contrast_at_least_4_5(name: str, surface: str) -> None:
    assert contrast(TEXTS[name], surface) >= 4.5


def test_soft_surfaces_and_button_contrast() -> None:
    assert contrast("#0B1416", SOFT) >= 4.5  # status pill and CTA text
    assert contrast("#FFFFFF", "#0B7468") >= 4.5  # button
    assert contrast("#FFFFFF", "#095E55") >= 4.5  # button hover
    assert contrast("#0B1416", "#FBF1E1") >= 4.5  # "data role" tag


def test_css_uses_the_light_palette() -> None:
    css = (build.ASSETS / "site.css").read_text()
    for token in ("#FFFFFF", "#F3F8F7", "#E2EAE8", "#0B1416", "#3D4B49", "#5F716E", "#0B7468",
                  "#095E55", "#E3F3F0", "#0E8A7D", "#D98E14", "Plus Jakarta Sans"):  # fmt: skip
        assert token in css
    assert "Instrument Sans" not in css and "#0F1C1E" not in css


def _data() -> dict[str, object]:
    d = date(2026, 11, 4)
    return {
        "latest": d,
        "kpi": (1493, 60000, 0.82, 4000, 0.55, 0.2),
        "tracked": 1500,
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
    assert set(external) == {
        "https://github.com/siddharthkumarx/job-postings-pipeline",
        "https://github.com/siddharthkumarx/job-postings-pipeline/releases",
        "https://github.com/siddharthkumarx/job-postings-pipeline/tree/main/public",
        "https://github.com/siddharthkumarx/job-postings-pipeline/blob/main/public/runs.jsonl",
        "https://steadydata.co",
        "https://steadydata.co/contact/",
        "https://siddharthkumar.com/job-postings-pipeline/",  # canonical
    }
    assert "Built by SteadyData" in html and "Get a free sample" in html
    assert "Built and maintained by Siddharth Kumar, Founder of SteadyData" in html
    assert "hello@steadydata.co" in html and "hello@" + "siddharthkumar.com" not in html
    assert "<!--" not in html
    assert 'lang="en"' in html and 'name="viewport"' in html and 'name="description"' in html
    assert "Acme &lt;script&gt;" in html


def test_head_has_icon_set_and_link_preview() -> None:
    html = build.render(_data(), {"days_running": 3})
    assert '<link rel="icon" href="assets/favicon.ico" sizes="32x32">' in html
    assert '<link rel="manifest" href="assets/site.webmanifest">' in html
    assert 'stop-color="#5FE8D6"' in html  # the SteadyData mark in the top bar
    assert "data:image/svg+xml" not in html
    url = "https://siddharthkumar.com/job-postings-pipeline/"
    assert f'<meta property="og:image" content="{url}assets/og.png">' in html
    for name in ("favicon.ico", "icon.svg", "apple-touch-icon.png", "site.webmanifest", "og.png"):
        assert (build.ASSETS / name).exists()


def test_headlines_use_tracked_count_not_boards_read() -> None:
    html = build.render(_data(), {"companies_tracked": 1500, "days_running": 3})
    assert "Every open job at 1,500 US tech companies" in html
    assert "1,493 boards read in the latest run" in html
    assert "at 1,493" not in html
    # without status.json the warehouse's tracked count is used
    assert "Every open job at 1,500 US tech" in build.render(_data(), {})
