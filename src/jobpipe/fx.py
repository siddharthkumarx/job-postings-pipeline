"""ECB euro foreign exchange reference rates → bronze fx table.

Source: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip (daily,
all history, rates quoted as units of currency per 1 EUR). Stored long:
``rate_date, currency, per_eur, usd_per_unit``, where
``usd_per_unit = USD_per_EUR / currency_per_EUR``. EUR itself is included (per_eur = 1).
See docs/decisions.md D-008.
"""

from __future__ import annotations

import asyncio
import csv
import io
import os
import zipfile
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from jobpipe.http import HostPolicy, PoliteClient

ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
EARLIEST = date(2024, 1, 1)

FX_SCHEMA = pa.schema(
    [
        ("rate_date", pa.date32()),
        ("currency", pa.string()),
        ("per_eur", pa.float64()),
        ("usd_per_unit", pa.float64()),
        ("source", pa.string()),
    ]
)


def parse_hist_csv(text: str, earliest: date = EARLIEST) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rec in csv.DictReader(io.StringIO(text)):
        d = date.fromisoformat(rec["Date"].strip())
        if d < earliest:
            continue
        rates: dict[str, float] = {"EUR": 1.0}
        for cur, val in rec.items():
            if not cur or cur == "Date" or not val:
                continue
            val = val.strip()
            if val in ("", "N/A"):
                continue
            rates[cur.strip()] = float(val)
        usd = rates.get("USD")
        if not usd:
            continue
        for cur, per_eur in sorted(rates.items()):
            rows.append(
                {
                    "rate_date": d,
                    "currency": cur,
                    "per_eur": per_eur,
                    "usd_per_unit": usd / per_eur,
                    "source": "ECB euro reference rates",
                }
            )
    return rows


def parse_hist_zip(blob: bytes, earliest: date = EARLIEST) -> list[dict[str, object]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        return parse_hist_csv(z.read(name).decode("utf-8"), earliest)


def fx_path(data_dir: Path) -> Path:
    return data_dir / "bronze" / "fx" / "ecb_eurofxref.parquet"


def write(rows: list[dict[str, object]], data_dir: Path) -> Path:
    path = fx_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=FX_SCHEMA), tmp, compression="zstd")
    os.replace(tmp, path)
    return path


def fetch(data_dir: Path = Path("data")) -> dict[str, object]:
    async def go() -> bytes:
        policy = {"www.ecb.europa.eu": HostPolicy(concurrency=1, min_interval_s=1.0)}
        async with PoliteClient(host_policies=policy, timeout_s=60.0) as client:
            res = await client.get_bytes(ECB_HIST_URL)
        if not res.ok or not isinstance(res.data, bytes):
            raise RuntimeError(f"ECB download failed: {res.outcome} {res.status} {res.error}")
        return res.data

    rows = parse_hist_zip(asyncio.run(go()))
    write(rows, data_dir)
    dates = [r["rate_date"] for r in rows if isinstance(r["rate_date"], date)]
    return {
        "rows": len(rows),
        "latest_rate_date": max(dates).isoformat() if dates else None,
        "currencies": len({r["currency"] for r in rows}),
    }
