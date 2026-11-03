import pytest

from jobpipe.recon.seeds import SeedSet, token_from_url, yc_guesses


@pytest.mark.parametrize(
    ("url", "provider", "token"),
    [
        ("https://boards.greenhouse.io/Stripe/jobs/123", "greenhouse", "stripe"),
        ("https://boards.greenhouse.io/embed/job_board?for=acme&b=x", "greenhouse", "acme"),
        ("https://job-boards.greenhouse.io/figma", "greenhouse", "figma"),
        ("https://boards.greenhouse.io/robots.txt", "greenhouse", None),
        ("https://jobs.lever.co/palantir/abc-123", "lever", "palantir"),
        ("https://jobs.lever.co/_next/static/x.js", "lever", None),
        ("https://jobs.ashbyhq.com/Ramp/xyz", "ashby", "Ramp"),
        ("https://jobs.ashbyhq.com/api/non-user-graphql", "ashby", None),
        ("jobs.ashbyhq.com/Open%20Co", "ashby", "Open Co"),
    ],
)
def test_token_from_url(url: str, provider: str, token: str | None) -> None:
    assert token_from_url(url, provider) == token


def test_seedset_merges_case_insensitively() -> None:
    s = SeedSet()
    s.add("ashby", "ramp", "cc:a", hits=1)
    s.add("ashby", "Ramp", "cc:b", hits=5)
    s.add("ashby", "ramp", "yc", yc_name="Ramp", yc_slug="ramp")
    rows = s.rows()
    assert len(rows) == 1
    assert rows[0]["token"] == "Ramp"
    assert rows[0]["sources"] == "cc:a|cc:b|yc"
    assert rows[0]["cc_hits"] == 6
    assert rows[0]["yc_name"] == "Ramp"


def test_yc_guesses() -> None:
    assert yc_guesses({"name": "Open Co.", "website": "https://www.openco.ai"}) == [
        "openco",
        "open-co",
    ]
