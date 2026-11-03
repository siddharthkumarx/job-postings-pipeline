"""Command-line entry point: ``jobpipe <command>``."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobpipe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_checks = sub.add_parser("checks", help="run a live check described in a request file")
    p_checks.add_argument("request", type=Path, nargs="?", default=Path("checks/request.yml"))

    p_sel = sub.add_parser("recon-select", help="pick tracked boards from recon verify results")
    p_sel.add_argument("--verify", type=Path, required=True, help="checks/results/<id>/verify.csv")
    p_sel.add_argument("--harvest", type=Path, required=True, help="harvest summary.json")
    p_sel.add_argument("--out-csv", type=Path, default=Path("seeds/boards.csv"))
    p_sel.add_argument("--out-md", type=Path, default=Path("docs/sources.md"))
    p_sel.add_argument("--min-us-share", type=float, default=0.5)
    p_sel.add_argument("--min-known-share", type=float, default=0.5)
    p_sel.add_argument("--min-tech-share", type=float, default=0.2)
    p_sel.add_argument("--target", type=int, default=1500)

    p_run = sub.add_parser("run", help="daily run for one date (needs network + GITHUB_TOKEN)")
    p_run.add_argument("--date", type=date.fromisoformat, default=None, help="UTC run date")

    p_bf = sub.add_parser("backfill", help="re-process stored bronze snapshots for a date range")
    p_bf.add_argument("--from", dest="d_from", type=date.fromisoformat, required=True)
    p_bf.add_argument("--to", dest="d_to", type=date.fromisoformat, required=True)

    p_rh = sub.add_parser("release-hold", help="accept a held run (publish it despite guards)")
    p_rh.add_argument("--date", type=date.fromisoformat, required=True)

    sub.add_parser("rebuild", help="rebuild the warehouse from every bronze snapshot")

    p_fx = sub.add_parser("fixtures-build", help="dbt build on synthetic fixtures (offline)")
    p_fx.add_argument("--dir", type=Path, default=Path("data/fixtures"))

    p_site = sub.add_parser("site", help="build the dashboard into site/")
    p_site.add_argument("--duckdb", type=Path, default=Path("data/warehouse.duckdb"))
    p_site.add_argument("--public", type=Path, default=Path("public"))
    p_site.add_argument("--out", type=Path, default=Path("site"))

    args = parser.parse_args(argv)
    if args.cmd in ("run", "backfill", "release-hold", "rebuild"):
        from jobpipe import pipeline

        if args.cmd == "run":
            outcome = pipeline.daily(args.date or datetime.now(UTC).date())
        elif args.cmd == "backfill":
            outcome = pipeline.backfill(args.d_from, args.d_to)
        elif args.cmd == "release-hold":
            outcome = pipeline.backfill(args.date, args.date, force=True)
        else:
            outcome = pipeline.rebuild()
        print(pipeline.dump(outcome))
        return outcome.exit_code
    if args.cmd == "fixtures-build":
        from jobpipe import pipeline

        paths = pipeline.Paths(
            data_dir=args.dir / "data",
            seeds_dir=args.dir / "seeds",
            duckdb=args.dir / "warehouse.duckdb",
            public_dir=args.dir / "public",
            site_dir=args.dir / "site",
        )
        res = pipeline.offline_build(paths)
        print(f"dbt build on fixtures: success={res.success} {res.counts}")
        for f in res.failures:
            print("  ", f)
        return 0 if res.success else 1
    if args.cmd == "site":
        from jobpipe.site import build as site_build

        site_build.build(args.duckdb, args.public, args.out)
        return 0
    if args.cmd == "recon-select":
        import json

        from jobpipe.recon import select

        harvest = json.loads(args.harvest.read_text())
        verify_summary = json.loads((args.verify.parent / "summary.json").read_text())
        th = select.Thresholds(
            min_us_share=args.min_us_share,
            min_known_share=args.min_known_share,
            min_tech_share=args.min_tech_share,
            target=args.target,
        )
        result = select.run(
            args.verify,
            harvest.get("result", {}),
            verify_summary.get("result", {}),
            [args.harvest.parent.name, args.verify.parent.name],
            args.out_csv,
            args.out_md,
            th,
            dropped_csv=args.verify.parent / "dropped.csv",
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "checks":
        from jobpipe.checks import run_request

        return run_request(args.request)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
