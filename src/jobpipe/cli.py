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

    args = parser.parse_args(argv)
    if args.cmd == "checks":
        from jobpipe.checks import run_request

        return run_request(args.request)
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
