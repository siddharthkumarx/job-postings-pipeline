from jobpipe.recon.select import (
    Thresholds,
    company_kind,
    norm_company,
    pretty_token,
    select,
)


def _row(**kw: str) -> dict[str, str]:
    base = {
        "provider": "greenhouse", "token": "acme", "sources": "cc:X", "cc_hits": "3",
        "yc_name": "", "outcome": "ok", "status": "200", "company_name": "Acme Inc.",
        "jobs": "10", "us_jobs": "8", "non_us_jobs": "2", "unknown_jobs": "0",
        "tech_jobs": "5", "us_tech_jobs": "4", "remote_jobs": "0", "top_countries": "",
        "bytes": "1", "attempts": "1", "elapsed_s": "0.2",
    }  # fmt: skip
    base.update(kw)
    return base


def test_norm_company_and_pretty_token() -> None:
    assert norm_company("Acme, Inc.") == norm_company("ACME") == "acme"
    assert pretty_token("open-co_labs") == "Open Co Labs"


def test_company_kind_rules() -> None:
    assert company_kind(_row(company_name="Bright Staffing Group"), {}) == (
        "staffing or recruiting agency"
    )
    assert company_kind(_row(token="leverdemo", company_name=""), {}) == "test or demo board"
    assert company_kind(_row(token="remotejobs", company_name="Remote Jobs Hub"), {}) == (
        "job aggregator"
    )
    assert company_kind(_row(), {}) is None
    assert company_kind(_row(), {("greenhouse", "acme"): "reviewed: agency"}) == "reviewed: agency"
    # not fooled by words that merely contain the patterns
    assert company_kind(_row(token="contest", company_name="Contestly"), {}) is None


def test_select_filters_dedupes_and_explains_every_drop() -> None:
    rows = [
        _row(),
        _row(provider="lever", token="acme", company_name="", yc_name="Acme",
             sources="cc:X|yc", jobs="3", us_jobs="3", non_us_jobs="0"),  # dup, smaller
        _row(token="eu", company_name="EU Co", us_jobs="1", non_us_jobs="9"),
        _row(token="nontech", company_name="Bakery", tech_jobs="0", us_tech_jobs="0"),
        _row(token="dead", outcome="not_found", jobs="0"),
        _row(token="empty", company_name="Empty", jobs="0", us_jobs="0", non_us_jobs="0"),
        _row(token="nous", company_name="No US", us_jobs="0", non_us_jobs="10"),
        _row(token="brightstaff", company_name="Bright Staffing"),
    ]  # fmt: skip
    boards, dropped, funnel = select(rows, Thresholds(), {})
    assert [b["board"] for b in boards] == ["acme"]
    assert "also on lever" in boards[0]["notes"]
    reasons = {d["board"]: d["reason"] for d in dropped}
    assert len(boards) + len(dropped) == len(rows)
    assert reasons["eu"].startswith("mostly non-US")
    assert reasons["nontech"].startswith("not a tech company")
    assert reasons["dead"].startswith("board not found")
    assert reasons["empty"] == "no open jobs"
    assert reasons["nous"] == "0 US roles"
    assert reasons["brightstaff"] == "staffing or recruiting agency"
    assert reasons["acme"].startswith("duplicate: same company also on greenhouse")
    assert sum(funnel["kept"].values()) == 1


def test_target_cut_is_recorded() -> None:
    rows = [_row(token=f"co{i}", company_name=f"Co {i}", us_tech_jobs=str(i)) for i in range(5)]
    boards, dropped, _ = select(rows, Thresholds(target=3), {})
    assert [b["board"] for b in sorted(boards, key=lambda b: b["board"])] == ["co2", "co3", "co4"]
    assert all(d["reason"].startswith("below the 3-company cut") for d in dropped)


def test_sanitise_job_removes_free_text() -> None:
    from jobpipe.checks import SYNTHETIC_DESCRIPTION, sanitise_job

    gh = sanitise_job(
        "greenhouse",
        {"id": 1, "title": "X", "content": "real text", "metadata": [{"value": "Jane"}]},
    )
    assert gh == {"id": 1, "title": "X", "content": SYNTHETIC_DESCRIPTION, "metadata": None}
    lv = sanitise_job("lever", {"id": "a", "descriptionPlain": "secret body", "additional": "x"})
    assert "secret body" not in repr(lv) and "additional" not in lv
