from datetime import date

import pytest

from jobpipe.fx import parse_hist_csv

CSV = """Date,USD,JPY,CYP,GBP,CAD,
2026-11-03,1.1179,176.95,N/A,0.83358,1.5623,
2026-11-02,1.1200,177.00,N/A,0.83000,1.5600,
2023-12-29,1.1050,156.33,N/A,0.86905,1.4642,
"""


def test_parse_hist_csv() -> None:
    rows = parse_hist_csv(CSV, earliest=date(2024, 1, 1))
    by = {(r["rate_date"], r["currency"]): r for r in rows}
    assert (date(2023, 12, 29), "USD") not in by
    assert (date(2026, 11, 3), "CYP") not in by  # N/A skipped
    assert by[(date(2026, 11, 3), "USD")]["usd_per_unit"] == pytest.approx(1.0)
    assert by[(date(2026, 11, 3), "EUR")]["usd_per_unit"] == pytest.approx(1.1179)
    assert by[(date(2026, 11, 3), "GBP")]["usd_per_unit"] == pytest.approx(1.1179 / 0.83358)
    assert len(rows) == 2 * 5  # EUR, USD, JPY, GBP, CAD per day
