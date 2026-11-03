"""Generate dbt/models/marts/_marts.yml (contracts + tests) from docs/data-contracts.md.

Run: uv run python scripts/gen_marts_yml.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from contracts_spec import parse

PROVIDERS = ["greenhouse", "lever", "ashby"]
ROLE_FAMILIES = [
    "software_engineer", "data_engineer", "analytics_engineer", "data_analyst", "data_scientist",
    "ml_engineer", "devops_sre", "security", "product_manager", "design", "qa_test", "it_support",
    "hardware_engineer", "solutions_engineer", "engineering_manager", "sales", "marketing",
    "customer_success", "operations", "finance", "people_hr", "legal", "other",
]  # fmt: skip
SENIORITY = [
    "intern", "junior", "mid", "senior", "staff_principal", "manager", "director", "vp_exec",
]  # fmt: skip
DATA_ROLES = ["data_engineer", "analytics_engineer", "data_analyst", "ml_engineer"]


def av(values: list[str]) -> dict[str, Any]:
    return {"accepted_values": {"arguments": {"values": values}}}


def between(lo: float, hi: float) -> dict[str, Any]:
    return {"column_between": {"arguments": {"min_value": lo, "max_value": hi}}}


def rel(model: str, field: str) -> dict[str, Any]:
    return {"relationships": {"arguments": {"to": f"ref('{model}')", "field": field}}}


def combo(cols: list[str]) -> dict[str, Any]:
    return {"unique_combination": {"arguments": {"columns": cols}}}


def expr(e: str) -> dict[str, Any]:
    return {"expression_is_true": {"arguments": {"expression": e}}}


DESCRIPTIONS = {
    "fct_job_postings": "One row per posting ever seen: current attributes, lifecycle, SCD2 "
    "version count and salary in annual USD. Public; contract enforced.",
    "dim_company": "One row per tracked company with the latest fetch status and posting counts. "
    "Public; contract enforced.",
    "mart_weekly_open_roles": "Weekly open / new / closed roles by company, role family, country "
    "and US state. Public; contract enforced.",
    "mart_days_open_bands": "Distribution of days open for closed postings by role family. "
    "Public; contract enforced.",
    "mart_salary_bands": "Annual USD salary percentiles for US postings by role family and "
    "seniority. Public; contract enforced.",
    "mart_hiring_velocity": "Weekly new vs closed postings per company. Public; contract enforced.",
    "mart_data_roles": "Posting-level subset of fct_job_postings for data engineer, analytics "
    "engineer, data analyst and ML engineer roles. Public; contract enforced.",
}

FCT_TESTS: dict[str, list[Any]] = {
    "posting_key": ["unique", "not_null"],
    "provider": ["not_null", av(PROVIDERS)],
    "company_id": ["not_null", rel("dim_company", "company_id")],
    "company_name": ["not_null"],
    "title": ["not_null"],
    "job_url": ["not_null"],
    "role_family": ["not_null", av(ROLE_FAMILIES)],
    "seniority": ["not_null", av(SENIORITY)],
    "seniority_source": [av(["title", "description", "default"])],
    "remote_type": ["not_null", av(["remote", "hybrid", "onsite", "unknown"])],
    "employment_type": [
        av(["full_time", "part_time", "contract", "intern", "temporary", "unknown"])
    ],
    "salary_period": [av(["year", "month", "week", "day", "hour"])],
    "salary_source": [av(["api", "description"])],
    "salary_min_usd_annual": [between(10000, 2000000)],
    "first_seen": ["not_null"],
    "last_seen": ["not_null"],
    "is_open": ["not_null"],
    "days_open": ["not_null", between(1, 5000)],
    "version_count": [between(1, 100000)],
}
COLUMN_TESTS: dict[str, dict[str, list[Any]]] = {
    "fct_job_postings": FCT_TESTS,
    "mart_data_roles": {
        "posting_key": ["unique", "not_null"],
        "role_family": [av(DATA_ROLES)],
    },
    "dim_company": {
        "company_id": ["unique", "not_null"],
        "company_name": ["not_null"],
        "provider": ["not_null", av(PROVIDERS)],
        "last_fetch_status": [av(["ok", "not_found", "error", "blocked"])],
    },
    "mart_weekly_open_roles": {
        "week_start": ["not_null"],
        "company_id": ["not_null", rel("dim_company", "company_id")],
        "open_roles": [between(0, 1000000)],
    },
    "mart_days_open_bands": {
        "band": [av(["0-7", "8-14", "15-30", "31-60", "61-90", "91+"])],
        "share": [between(0, 1)],
    },
    "mart_salary_bands": {"role_family": ["not_null"], "seniority": ["not_null"]},
    "mart_hiring_velocity": {
        "week_start": ["not_null"],
        "company_id": ["not_null", rel("dim_company", "company_id")],
    },
}
MODEL_TESTS: dict[str, list[Any]] = {
    "fct_job_postings": [
        expr("salary_min is null or salary_min <= salary_max"),
        expr("last_seen >= first_seen"),
        expr("closed_on is null or closed_on > last_seen"),
    ],
    "mart_weekly_open_roles": [
        combo(["week_start", "company_id", "role_family", "country_code", "state_code"])
    ],
    "mart_days_open_bands": [combo(["role_family", "band"])],
    "mart_salary_bands": [combo(["role_family", "seniority"])],
    "mart_hiring_velocity": [combo(["week_start", "company_id"])],
}


def build() -> dict[str, Any]:
    spec = parse()
    spec["mart_data_roles"] = spec["fct_job_postings"]
    models = []
    for table, cols in spec.items():
        model: dict[str, Any] = {
            "name": table,
            "description": DESCRIPTIONS[table],
            "config": {"contract": {"enforced": True}},
        }
        if table in MODEL_TESTS:
            model["data_tests"] = MODEL_TESTS[table]
        model["columns"] = []
        for name, dtype, desc in cols:
            col: dict[str, Any] = {"name": name, "data_type": dtype, "description": desc}
            if name in COLUMN_TESTS.get(table, {}):
                col["data_tests"] = COLUMN_TESTS[table][name]
            model["columns"].append(col)
        models.append(model)
    return {"version": 2, "models": models}


HEADER = (
    "# GENERATED from docs/data-contracts.md by scripts/gen_marts_yml.py:"
    " edit the doc, then regenerate.\n"
)


def render() -> str:
    return HEADER + yaml.safe_dump(build(), sort_keys=False, width=120, allow_unicode=True)


if __name__ == "__main__":
    Path("dbt/models/marts/_marts.yml").write_text(render(), encoding="utf-8")
