#!/usr/bin/env python3
"""Bridge MCP get_limit_pool payloads into local raw and organized JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.stock_emotion_data import (
        organized_limit_pool_to_dict,
        organize_limit_pool,
        parse_limit_pool_payload,
        should_include_special,
        validate_trade_date,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from stock_emotion_data import (
        organized_limit_pool_to_dict,
        organize_limit_pool,
        parse_limit_pool_payload,
        should_include_special,
        validate_trade_date,
    )


DEFAULT_RAW_DIR = Path("output/raw/stock-emotion-capture")
DEFAULT_ORGANIZED_DIR = Path("output/data/stock-emotion-capture")


def bridge_payload(
    payload_text: str,
    *,
    date: str | None = None,
    include_special: bool = False,
    user_text: str = "",
    raw_output: Path | None = None,
    organized_output: Path | None = None,
) -> dict[str, Any]:
    """Save raw MCP payload and organized data without printing the full payload."""
    payload = json.loads(payload_text)
    raw_payload = parse_limit_pool_payload(payload)
    payload_date = str(raw_payload.get("date") or "")
    if date is not None:
        validate_trade_date(date)
        if payload_date and payload_date != date:
            raise ValueError(f"payload date {payload_date!r} does not match requested date {date!r}")
        output_date = date
    else:
        validate_trade_date(payload_date)
        output_date = payload_date

    effective_include_special = include_special or should_include_special(user_text)
    organized = organize_limit_pool(raw_payload, include_special=effective_include_special)
    organized_dict = organized_limit_pool_to_dict(organized)

    raw_path = raw_output or DEFAULT_RAW_DIR / f"{output_date}-limit-pool.json"
    organized_path = organized_output or DEFAULT_ORGANIZED_DIR / f"{output_date}-organized.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    organized_path.parent.mkdir(parents=True, exist_ok=True)

    raw_path.write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    organized_path.write_text(
        json.dumps(organized_dict, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "date": output_date,
        "include_special": effective_include_special,
        "raw_path": str(raw_path),
        "organized_path": str(organized_path),
        "raw_counts": organized.raw_counts,
        "filtered_counts": organized.filtered_counts,
        "excluded_counts": organized.excluded_counts,
        "industry_count": len(organized.industry_view),
        "ladder_levels": [level.board_height for level in organized.ladder_view],
        "data_issues": list(organized.data_issues),
    }


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Save a get_limit_pool MCP payload to raw JSON and produce organized "
            "industry/ladder JSON. Pass '-' as input to read from stdin."
        )
    )
    parser.add_argument("--input", default="-", help="Input JSON file, or '-' for stdin.")
    parser.add_argument("--date", help="Expected trading date in YYYYMMDD format.")
    parser.add_argument("--include-special", action="store_true", help="Include ST and new stocks.")
    parser.add_argument("--user-text", default="", help="Original user request text for include-special detection.")
    parser.add_argument("--raw-output", type=Path, help="Raw payload output path.")
    parser.add_argument("--organized-output", type=Path, help="Organized JSON output path.")
    args = parser.parse_args(argv)

    summary = bridge_payload(
        _read_input(args.input),
        date=args.date,
        include_special=args.include_special,
        user_text=args.user_text,
        raw_output=args.raw_output,
        organized_output=args.organized_output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
