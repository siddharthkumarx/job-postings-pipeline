"""State in GitHub Release assets (docs/decisions.md D-007).

Releases used:

* ``bronze-YYYY-MM`` - bronze snapshots for that month (the source of truth):
  ``postings_D.parquet``, ``board_runs_D.parquet``, ``manifest_D.json``, ``fx_D.parquet``
* ``state``          - ``warehouse.duckdb.gz`` (last good build) and ``state.json``
* ``dataset-YYYY-MM`` - the public monthly dataset

Uploads go to a temporary asset name first; the old asset is deleted and the new
one renamed only after the upload succeeded, so a failed upload never destroys
the previous version.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from jobpipe import USER_AGENT

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
STATE_TAG = "state"


def bronze_tag(d: date) -> str:
    return f"bronze-{d:%Y-%m}"


def dataset_tag(d: date) -> str:
    return f"dataset-{d:%Y-%m}"


BRONZE_ASSETS = {
    "postings": ("postings", "parquet"),
    "board_runs": ("board_runs", "parquet"),
}


@dataclass(frozen=True, slots=True)
class Asset:
    id: int
    name: str
    size: int


class GitHubReleases:
    def __init__(
        self,
        repo: str | None = None,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
        retries: int = 4,
    ) -> None:
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        token = token or os.environ.get("GITHUB_TOKEN", "")
        if not self.repo or not token:
            raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required for state sync")
        self.retries = retries
        self._c = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            },
            timeout=httpx.Timeout(120.0),
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._c.close()

    def _req(self, method: str, url: str, **kw: Any) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = self._c.request(method, url, **kw)
            except httpx.TransportError as exc:
                last = exc
            else:
                if resp.status_code < 500 and resp.status_code != 429:
                    return resp
                last = RuntimeError(f"{method} {url} -> HTTP {resp.status_code}")
            time.sleep(min(30, 2 ** (attempt + 1)))
        raise RuntimeError(f"GitHub API failed after retries: {last}")

    def release(self, tag: str, *, create: bool = False, body: str = "") -> dict[str, Any] | None:
        resp = self._req("GET", f"{API}/repos/{self.repo}/releases/tags/{tag}")
        if resp.status_code == 200:
            data: dict[str, Any] = resp.json()
            return data
        if resp.status_code != 404:
            raise RuntimeError(f"release lookup {tag}: HTTP {resp.status_code} {resp.text[:200]}")
        if not create:
            return None
        resp = self._req(
            "POST",
            f"{API}/repos/{self.repo}/releases",
            json={
                "tag_name": tag,
                "name": tag,
                "body": body or f"Pipeline data: {tag}",
                "prerelease": tag != STATE_TAG and not tag.startswith("dataset-"),
                "make_latest": "false",
            },
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"create release {tag}: HTTP {resp.status_code} {resp.text[:200]}")
        created: dict[str, Any] = resp.json()
        return created

    def assets(self, release: dict[str, Any]) -> list[Asset]:
        out: list[Asset] = []
        page = 1
        while True:
            resp = self._req(
                "GET",
                f"{API}/repos/{self.repo}/releases/{release['id']}/assets",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            out += [Asset(a["id"], a["name"], a["size"]) for a in batch]
            if len(batch) < 100:
                return out
            page += 1

    def upload(self, tag: str, path: Path, name: str | None = None) -> Asset:
        name = name or path.name
        rel = self.release(tag, create=True)
        assert rel is not None
        tmp_name = f"{name}.uploading"
        existing = {a.name: a for a in self.assets(rel)}
        if tmp_name in existing:
            self._req("DELETE", f"{API}/repos/{self.repo}/releases/assets/{existing[tmp_name].id}")
        with path.open("rb") as fh:
            resp = self._req(
                "POST",
                f"{UPLOADS}/repos/{self.repo}/releases/{rel['id']}/assets",
                params={"name": tmp_name},
                content=fh.read(),
                headers={"Content-Type": "application/octet-stream"},
            )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"upload {name}: HTTP {resp.status_code} {resp.text[:200]}")
        new = resp.json()
        if name in existing:
            self._req("DELETE", f"{API}/repos/{self.repo}/releases/assets/{existing[name].id}")
        resp = self._req(
            "PATCH",
            f"{API}/repos/{self.repo}/releases/assets/{new['id']}",
            json={"name": name},
        )
        resp.raise_for_status()
        return Asset(new["id"], name, new["size"])

    def download(self, asset: Asset, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        resp = self._req(
            "GET",
            f"{API}/repos/{self.repo}/releases/assets/{asset.id}",
            headers={"Accept": "application/octet-stream"},
        )
        resp.raise_for_status()
        tmp.write_bytes(resp.content)
        os.replace(tmp, dest)
        return dest

    def find(self, tag: str, name: str) -> Asset | None:
        rel = self.release(tag)
        if rel is None:
            return None
        return next((a for a in self.assets(rel) if a.name == name), None)


# ---- bronze ---------------------------------------------------------------------------


def bronze_local(data_dir: Path, table: str, d: date) -> Path:
    return data_dir / "bronze" / table / f"run_date={d.isoformat()}" / "part-0.parquet"


def push_bronze(gh: GitHubReleases, data_dir: Path, d: date) -> list[str]:
    names: list[str] = []
    for table in BRONZE_ASSETS:
        local = bronze_local(data_dir, table, d)
        name = f"{table}_{d.isoformat()}.parquet"
        gh.upload(bronze_tag(d), local, name)
        names.append(name)
    manifest = data_dir / "bronze" / "manifests" / f"run_date={d.isoformat()}.json"
    if manifest.exists():
        gh.upload(bronze_tag(d), manifest, f"manifest_{d.isoformat()}.json")
        names.append(manifest.name)
    fx = data_dir / "bronze" / "fx" / "ecb_eurofxref.parquet"
    if fx.exists():
        gh.upload(bronze_tag(d), fx, f"fx_{d.isoformat()}.parquet")
    return names


def pull_bronze(gh: GitHubReleases, data_dir: Path, d: date) -> bool:
    """Download one run date's bronze; True if all tables were present."""
    rel = gh.release(bronze_tag(d))
    if rel is None:
        return False
    assets = {a.name: a for a in gh.assets(rel)}
    ok = True
    for table in BRONZE_ASSETS:
        a = assets.get(f"{table}_{d.isoformat()}.parquet")
        if a is None:
            ok = False
            continue
        gh.download(a, bronze_local(data_dir, table, d))
    fx = assets.get(f"fx_{d.isoformat()}.parquet")
    if fx is not None:
        gh.download(fx, data_dir / "bronze" / "fx" / "ecb_eurofxref.parquet")
    return ok


def bronze_dates(gh: GitHubReleases, months: list[str]) -> list[date]:
    """Run dates with a postings asset in the given ``YYYY-MM`` months."""
    out: list[date] = []
    for m in months:
        rel = gh.release(f"bronze-{m}")
        if rel is None:
            continue
        for a in gh.assets(rel):
            if a.name.startswith("postings_") and a.name.endswith(".parquet"):
                out.append(date.fromisoformat(a.name[len("postings_") : -len(".parquet")]))
    return sorted(set(out))


# ---- warehouse snapshot ----------------------------------------------------------------


REQUIRED_TABLES = [
    ("silver", "stg_postings"),
    ("silver", "stg_board_runs"),
    ("history", "int_postings_daily"),
    ("history", "int_title_labels"),
    *[("gold", t) for t in (
        "fct_job_postings", "dim_company", "mart_weekly_open_roles", "mart_days_open_bands",
        "mart_salary_bands", "mart_hiring_velocity", "mart_data_roles",
    )],
]  # fmt: skip


def checkpoint(duckdb_path: Path) -> None:
    """Flush the write-ahead log into the database file so a file copy is complete.

    dbt keeps its DuckDB connection open in this process; a connection to the same file
    shares that database instance, so FORCE CHECKPOINT writes everything dbt committed.
    """
    import duckdb

    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute("FORCE CHECKPOINT")
    finally:
        con.close()


def validate_warehouse(duckdb_path: Path, bronze_dates: list[str]) -> list[str]:
    """Problems with a restored snapshot (empty list = usable for an incremental run)."""
    import duckdb

    problems: list[str] = []
    con = duckdb.connect(str(duckdb_path))
    try:
        have = {
            (r[0], r[1])
            for r in con.execute(
                "select table_schema, table_name from information_schema.tables"
            ).fetchall()
        }
        problems += [f"missing table {s}.{t}" for s, t in REQUIRED_TABLES if (s, t) not in have]
        if ("silver", "stg_postings") in have and bronze_dates:
            loaded = {
                str(r[0])
                for r in con.execute("select distinct run_date from silver.stg_postings").fetchall()
            }
            missing = sorted(set(bronze_dates) - loaded)
            if missing:
                problems.append(f"silver.stg_postings lacks run dates {missing[:5]}")
    finally:
        con.close()
    return problems


def push_warehouse(gh: GitHubReleases, duckdb_path: Path, state: dict[str, Any]) -> None:
    checkpoint(duckdb_path)
    problems = validate_warehouse(duckdb_path, list(state.get("bronze_dates", [])))
    if problems:
        raise RuntimeError(f"refusing to upload an incomplete warehouse: {problems}")
    gz = duckdb_path.with_suffix(".duckdb.gz")
    with duckdb_path.open("rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    gh.upload(STATE_TAG, gz, "warehouse.duckdb.gz")
    sj = duckdb_path.parent / "state.json"
    sj.write_text(json.dumps(state, indent=2, default=str) + "\n")
    gh.upload(STATE_TAG, sj, "state.json")


def pull_warehouse(gh: GitHubReleases, duckdb_path: Path) -> dict[str, Any] | None:
    """Restore the last good warehouse; None when there is none (→ rebuild)."""
    rel = gh.release(STATE_TAG)
    if rel is None:
        return None
    assets = {a.name: a for a in gh.assets(rel)}
    if "warehouse.duckdb.gz" not in assets or "state.json" not in assets:
        return None
    gz = gh.download(assets["warehouse.duckdb.gz"], duckdb_path.with_suffix(".duckdb.gz"))
    sj = gh.download(assets["state.json"], duckdb_path.parent / "state.json")
    with gzip.open(gz, "rb") as src, duckdb_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    data: dict[str, Any] = json.loads(sj.read_text())
    return data
