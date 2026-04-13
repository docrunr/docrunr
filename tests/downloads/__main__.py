from __future__ import annotations

import argparse
import sys

from tests.downloads.models import DEFAULT_TIMEOUT
from tests.downloads.runner import run_downloads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download random sample documents from open data sources."
    )
    parser.add_argument(
        "mimetype",
        help="Mimetype or extension alias. Supports comma-separated values, e.g. 'pdf,docx'.",
    )
    parser.add_argument("count", type=int, help="Number of documents to download per mimetype.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout (seconds).")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible ordering.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    args = parse_args()
    return run_downloads(args.mimetype, args.count, args.timeout, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
