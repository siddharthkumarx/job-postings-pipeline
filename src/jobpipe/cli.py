"""Command-line entry point: ``jobpipe <command>``."""

from __future__ import annotations

import argparse
import sys
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

    args = parser.parse_args(argv)
    if args.cmd == "recon-select":
        import json

        from jobpipe.recon import select

        harvest = json.loads(args.harvest.read_text())
        th = select.Thresholds(
            min_us_share=args.min_us_share,
            min_known_share=args.min_known_share,
            min_tech_share=args.min_tech_share,
            target=args.target,
        )
        result = select.run(
            args.verify,
            harvest.get("result", {}),
            [args.harvest.parent.name, args.verify.parent.name],
            args.out_csv,
            args.out_md,
            th,
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
