#!/usr/bin/env python3
"""
Persist qfq daily bars returned by mcp_stock into output/bars.

Usage:
  python3 chan/scripts/save_bars.py --symbol 603629 --start-date 20250101 --end-date 20250618 --input /tmp/mcp_stock.json

If --input is omitted, the script reads JSON from stdin.
"""

from __future__ import annotations

import argparse
import json
import sys

from bars_io import format_cwd_relative_path, save_bars_document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save mcp_stock qfq daily bars.")
    parser.add_argument("--symbol", required=True, help="6-digit A-share stock code.")
    parser.add_argument("--start-date", required=True, help="Start date in YYYYMMDD format.")
    parser.add_argument("--end-date", required=True, help="End date in YYYYMMDD format.")
    parser.add_argument(
        "--input",
        help="JSON file containing the mcp_stock payload. Reads stdin when omitted.",
    )
    return parser.parse_args()


def load_payload(input_path: str | None):
    if input_path:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return json.load(sys.stdin)


def main() -> int:
    args = parse_args()
    payload = load_payload(args.input)
    output_path = save_bars_document(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        payload=payload,
    )
    print(format_cwd_relative_path(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
