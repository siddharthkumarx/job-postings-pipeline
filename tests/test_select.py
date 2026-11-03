from jobpipe.recon.select import Thresholds, funnel_and_select, norm_company, pretty_token


def _row(**kw: str) -> dict[str, str]:
    base = {
        "provider": "greenhouse", "token": "acme", "sources": "cc:X", "cc_hits": "3",
        "yc_name": "", "outcome": "ok", "status": "200", "company_name": "Acme Inc.",
        "jobs": "10", "us_jobs": "8", "non_us_jobs": "2", "unknown_jobs": "0",
        "tech_jobs": "5", "us_tech_jobs": "4", "remote_jobs": "0", "top_countries": "",
        "bytes": "1", "attempts": "1",
    }  # fmt: skip
    base.update(kw)
    return base


def test_norm_company_and_pretty_token() -> None:
    assert norm_company("Acme, Inc.") == norm_company("ACME") == "acme"
    assert pretty_token("open-co_labs") == "Open Co Labs"


def test_funnel_filters_and_dedupes() -> None:
    rows = [
        _row(),
        _row(provider="lever", token="acme", company_name="", yc_name="Acme",
             sources="cc:X|yc", jobs="3", us_jobs="3", non_us_jobs="0"),  # dup, smaller
        _row(token="eu", company_name="EU Co", us_jobs="1", non_us_jobs="9"),  # not US
        _row(token="nontech", company_name="Bakery", tech_jobs="0", us_tech_jobs="0"),
        _row(token="dead", outcome="not_found", jobs="0"),
        _row(token="empty", company_name="Empty", jobs="0", us_jobs="0", non_us_jobs="0"),
    ]  # fmt: skip
    boards, funnel = funnel_and_select(rows, Thresholds())
    assert [b["board"] for b in boards] == ["acme"]
    assert boards[0]["provider"] == "greenhouse"
    assert boards[0]["company"] == "Acme Inc."
    assert sum(funnel["http_200"].values()) == 5
    assert sum(funnel["tech"].values()) == 2
    assert sum(funnel["kept"].values()) == 1
