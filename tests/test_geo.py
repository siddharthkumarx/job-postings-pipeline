import pytest

from jobpipe.geo import job_countries


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
