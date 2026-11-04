import pytest

from jobpipe.geo import job_countries, parse_location


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("San Francisco, CA", {"US"}),
        ("Remote - US", {"US"}),
        ("US-Remote", {"US"}),
        ("Remote, USA", {"US"}),
        ("Indianapolis, IN", {"US"}),
        ("Washington, DC", {"US"}),
        ("Atlanta, Georgia", {"US"}),
        ("Hybrid - Seattle", {"US"}),
        ("Berlin, DE", {"DE"}),
        ("Toronto, CA", {"CA"}),
        ("Bangalore, IN", {"IN"}),
        ("Vancouver, BC", {"CA"}),
        ("Paris, France", {"FR"}),
        ("Remote (EMEA)", {"XX"}),
        ("Remote", set()),
        ("", set()),
        ("London, United Kingdom; New York, NY", {"GB", "US"}),
    ],
)
def test_job_countries_text(text: str, expected: set[str]) -> None:
    assert job_countries([text]) == expected


def test_structured_hints_win() -> None:
    assert job_countries(["Remote"], ["US"]) == {"US"}
    assert job_countries([], ["United States"]) == {"US"}
    assert job_countries([], ["Canada"]) == {"CA"}


@pytest.mark.parametrize(
    ("loc", "hint", "expected"),
    [
        ("San Francisco, CA", None, ("US", "CA", "San Francisco", None)),
        ("New York, New York, United States", None, ("US", "NY", "New York", None)),
        ("Remote - US", None, ("US", None, None, "remote")),
        ("Hybrid - Austin, TX", None, ("US", "TX", "Austin", "hybrid")),
        ("NYC", None, ("US", "NY", "New York", None)),
        ("Seattle", None, ("US", "WA", "Seattle", None)),
        ("London, United Kingdom", None, ("GB", None, "London", None)),
        ("Remote", "US", ("US", None, None, "remote")),
        ("", None, (None, None, None, None)),
        ("Texas", None, ("US", "TX", None, None)),
    ],
)
def test_parse_location(loc: str, hint: str | None, expected: tuple[object, ...]) -> None:
    p = parse_location(loc, hint)
    assert (p.country_code, p.state_code, p.city, p.remote_text) == expected


@pytest.mark.parametrize("loc", ["-", " / ", ";", "|", "—", "  "])
def test_parse_location_separator_only(loc: str) -> None:
    p = parse_location(loc)
    assert (p.country_code, p.state_code, p.city) == (None, None, None)
