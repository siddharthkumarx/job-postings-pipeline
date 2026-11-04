import json
import re
from datetime import date
from pathlib import Path

import httpx
import pytest

from jobpipe import state


class FakeGitHub:
    """In-memory subset of the Releases API."""

    def __init__(self) -> None:
        self.releases: dict[str, dict[str, object]] = {}
        self.assets: dict[int, dict[str, object]] = {}
        self.next_id = 1

    def handler(self, req: httpx.Request) -> httpx.Response:
        path, m = req.url.path, None
        if (m := re.fullmatch(r"/repos/o/r/releases/tags/(.+)", path)) and req.method == "GET":
            rel = self.releases.get(m.group(1))
            return httpx.Response(200, json=rel) if rel else httpx.Response(404)
        if path == "/repos/o/r/releases" and req.method == "POST":
            body = json.loads(req.content)
            rel = {"id": self.next_id, "tag_name": body["tag_name"]}
            self.next_id += 1
            self.releases[body["tag_name"]] = rel
            return httpx.Response(201, json=rel)
        if (m := re.fullmatch(r"/repos/o/r/releases/(\d+)/assets", path)) and req.method == "GET":
            rid = int(m.group(1))
            items = [
                {"id": a["id"], "name": a["name"], "size": len(a["data"])}  # type: ignore[arg-type]
                for a in self.assets.values()
                if a["rid"] == rid
            ]
            page = int(req.url.params.get("page", "1"))
            return httpx.Response(200, json=items if page == 1 else [])
        if (m := re.fullmatch(r"/repos/o/r/releases/(\d+)/assets", path)) and req.method == "POST":
            aid = self.next_id
            self.next_id += 1
            self.assets[aid] = {
                "id": aid, "rid": int(m.group(1)), "name": req.url.params["name"],
                "data": req.content,
            }  # fmt: skip
            return httpx.Response(201, json={"id": aid, "size": len(req.content)})
        if (m := re.fullmatch(r"/repos/o/r/releases/(\d+)", path)) and req.method == "PATCH":
            return httpx.Response(200, json={"id": int(m.group(1))})
        if m := re.fullmatch(r"/repos/o/r/releases/assets/(\d+)", path):
            aid = int(m.group(1))
            if req.method == "DELETE":
                self.assets.pop(aid)
                return httpx.Response(204)
            if req.method == "PATCH":
                self.assets[aid]["name"] = json.loads(req.content)["name"]
                return httpx.Response(200, json={})
            if req.method == "GET":
                return httpx.Response(200, content=self.assets[aid]["data"])  # type: ignore[arg-type]
        return httpx.Response(500, text=f"unhandled {req.method} {path}")


def _gh(fake: FakeGitHub) -> state.GitHubReleases:
    return state.GitHubReleases("o/r", "t", transport=httpx.MockTransport(fake.handler), retries=0)


def test_upload_replaces_and_downloads(tmp_path: Path) -> None:
    fake = FakeGitHub()
    gh = _gh(fake)
    f = tmp_path / "a.bin"
    f.write_bytes(b"one")
    gh.upload("bronze-2026-11", f, "x.bin")
    f.write_bytes(b"two")
    gh.upload("bronze-2026-11", f, "x.bin")
    names = [a["name"] for a in fake.assets.values()]
    assert names == ["x.bin"]
    asset = gh.find("bronze-2026-11", "x.bin")
    assert asset is not None
    assert gh.download(asset, tmp_path / "out.bin").read_bytes() == b"two"


def test_bronze_roundtrip_and_dates(tmp_path: Path) -> None:
    fake = FakeGitHub()
    gh = _gh(fake)
    d = date(2026, 11, 4)
    src = tmp_path / "src"
    for table in state.BRONZE_ASSETS:
        p = state.bronze_local(src, table, d)
        p.parent.mkdir(parents=True)
        p.write_bytes(table.encode())
    state.push_bronze(gh, src, d)
    assert state.bronze_dates(gh, ["2026-11", "2026-10"]) == [d]
    dst = tmp_path / "dst"
    assert state.pull_bronze(gh, dst, d)
    assert state.bronze_local(dst, "postings", d).read_bytes() == b"postings"
    assert not state.pull_bronze(gh, dst, date(2026, 12, 1))


def test_warehouse_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(state, "checkpoint", lambda p: None)
    monkeypatch.setattr(state, "validate_warehouse", lambda p, d: [])
    fake = FakeGitHub()
    gh = _gh(fake)
    assert state.pull_warehouse(gh, tmp_path / "w.duckdb") is None
    db = tmp_path / "src" / "warehouse.duckdb"
    db.parent.mkdir()
    db.write_bytes(b"duck" * 100)
    state.push_warehouse(gh, db, {"last_good_run": "2026-11-04"})
    out = tmp_path / "restore" / "warehouse.duckdb"
    out.parent.mkdir()
    st = state.pull_warehouse(gh, out)
    assert st == {"last_good_run": "2026-11-04"}
    assert out.read_bytes() == b"duck" * 100


def test_push_refuses_incomplete_warehouse(tmp_path: Path) -> None:
    import duckdb

    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create schema silver; create table silver.stg_postings (run_date date)")
    con.close()
    problems = state.validate_warehouse(db, ["2026-11-04"])
    assert any("missing table gold.dim_company" in p for p in problems)
    assert any("lacks run dates" in p for p in problems)
    with pytest.raises(RuntimeError, match="incomplete warehouse"):
        state.push_warehouse(_gh(FakeGitHub()), db, {"bronze_dates": ["2026-11-04"]})
