import pytest

from jobpipe.extract import analyse, find_salary, remote_hint, seniority_hint, to_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The base salary range is $120,000 - $150,000 per year.", (120000, 150000, "USD", "year")),
        ("Pay: $120K–$160K", (120000, 160000, "USD", "year")),
        ("Range $120-150K USD", (120000, 150000, "USD", "year")),
        ("$45 - $60 per hour", (45, 60, "USD", "hour")),
        ("$45.50/hr to $60/hr", (45.5, 60, "USD", "hour")),
        ("CA$90,000 to CA$110,000", (90000, 110000, "CAD", "year")),
        ("£50,000 - £65,000", (50000, 65000, "GBP", "year")),
        ("€60.000 – €80.000 per annum", (60000, 80000, "EUR", "year")),
        ("salary of $150,000 USD per year", (150000, 150000, "USD", "year")),
        ("We raised $50M - $100M", None),
        ("401(k) with 4% match", None),
        ("no numbers here", None),
    ],
)
def test_find_salary(text: str, expected: tuple[float, float, str, str] | None) -> None:
    s = find_salary(text)
    if expected is None:
        assert s is None
    else:
        assert s is not None
        assert (s.min, s.max, s.currency, s.period) == expected


def test_remote_hint_priority() -> None:
    assert remote_hint("Hybrid: 3 days a week in the office") == "hybrid"
    assert remote_hint("We are a remote-first company") == "remote"
    assert remote_hint("This role is on-site in Austin") == "onsite"
    assert remote_hint("Great benefits") is None


def test_seniority_hint() -> None:
    assert seniority_hint("5+ years of experience in Python") == "senior"
    assert seniority_hint("1 year of professional experience") == "junior"
    assert seniority_hint("3-5 years of relevant experience") == "mid"
    assert seniority_hint("10+ years experience") == "staff_principal"
    assert seniority_hint("founded 12 years ago") is None


def test_to_text_unescapes_greenhouse_html() -> None:
    assert to_text("&amp;lt;p&amp;gt;Hello&amp;lt;/p&amp;gt; world") == "Hello world"


def test_analyse_returns_no_text() -> None:
    facts = analyse("<p>Remote-first. $100,000 - $120,000. Email jane@example.com</p>")
    assert facts.salary is not None
    assert facts.remote_hint == "remote"
    assert facts.sha256 is not None and len(facts.sha256) == 64
    assert "jane" not in repr(facts)
    assert analyse(None).sha256 is None
