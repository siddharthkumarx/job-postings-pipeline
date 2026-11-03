"""Distinct (location_raw, country_hint) → country / US state / city / remote words.

Uses the same parser as recon (jobpipe.geo.parse_location), so the rules are unit-tested
in Python and a parser change re-labels history on the next build.
"""

import pyarrow as pa


def model(dbt, session):
    dbt.config(materialized="table")
    from jobpipe.geo import parse_location

    rel = dbt.ref("stg_postings")
    rows = rel.query(
        "p",
        "select distinct location_raw, country_hint from p",
    ).fetchall()
    out = {
        "location_key": [],
        "location_raw": [],
        "country_hint": [],
        "country_code": [],
        "state_code": [],
        "city": [],
        "remote_text": [],
    }
    for location_raw, country_hint in rows:
        parsed = parse_location(location_raw, country_hint)
        out["location_key"].append(f"{location_raw or ''}|{country_hint or ''}")
        out["location_raw"].append(location_raw)
        out["country_hint"].append(country_hint)
        out["country_code"].append(parsed.country_code)
        out["state_code"].append(parsed.state_code)
        out["city"].append(parsed.city)
        out["remote_text"].append(parsed.remote_text)
    schema = pa.schema([(name, pa.string()) for name in out])
    return pa.table(out, schema=schema)
