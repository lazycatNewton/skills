#!/usr/bin/env python3
"""Markdown report rendering helpers for stock emotion capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.stock_emotion_data import (
        OrganizedLimitPool,
        StockRecord,
        format_ladder_matrix_markdown,
        validate_trade_date,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from stock_emotion_data import (
        OrganizedLimitPool,
        StockRecord,
        format_ladder_matrix_markdown,
        validate_trade_date,
    )


def load_organized_limit_pool(path: Path) -> OrganizedLimitPool:
    """Load the organized JSON produced by bridge_limit_pool_payload.py."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("organized JSON must decode to an object")
    return _organized_from_mapping(data)


def render_ladder_section(organized: OrganizedLimitPool) -> str:
    """Render section 3 using n-board rows and industry columns."""
    return "## 3. 连板梯队\n\n" + format_ladder_matrix_markdown(organized)


def _organized_from_mapping(data: Mapping[str, Any]) -> OrganizedLimitPool:
    date = str(data.get("date") or "")
    validate_trade_date(date)
    return OrganizedLimitPool(
        date=date,
        source=_optional_str(data.get("source")),
        include_special=bool(data.get("include_special")),
        raw_counts=dict(data.get("raw_counts") or {}),
        filtered_counts=dict(data.get("filtered_counts") or {}),
        excluded_counts=dict(data.get("excluded_counts") or {}),
        flags=dict(data.get("flags") or {}),
        limit_up=tuple(_stock_record_from_mapping(item) for item in data.get("limit_up", []) or []),
        limit_down=tuple(_stock_record_from_mapping(item) for item in data.get("limit_down", []) or []),
        industry_view=(),
        ladder_view=(),
        data_issues=tuple(data.get("data_issues") or ()),
    )


def _stock_record_from_mapping(data: Mapping[str, Any]) -> StockRecord:
    return StockRecord(
        rank=_optional_int(data.get("rank")),
        symbol=str(data.get("symbol") or ""),
        name=str(data.get("name") or ""),
        industry=str(data.get("industry") or "未分类"),
        change_pct=_optional_float(data.get("change_pct")),
        latest_price=_optional_float(data.get("latest_price")),
        turnover=_optional_float(data.get("turnover")),
        free_float_market_cap=_optional_float(data.get("free_float_market_cap")),
        total_market_cap=_optional_float(data.get("total_market_cap")),
        turnover_rate=_optional_float(data.get("turnover_rate")),
        seal_fund=_optional_float(data.get("seal_fund")),
        first_limit_time=_optional_str(data.get("first_limit_time")),
        last_limit_time=_optional_str(data.get("last_limit_time")),
        break_limit_count=_optional_int(data.get("break_limit_count")) or 0,
        consecutive_limit_up_days=_optional_int(data.get("consecutive_limit_up_days")) or 0,
        consecutive_limit_down_days=_optional_int(data.get("consecutive_limit_down_days")) or 0,
        is_st=bool(data.get("is_st")),
        is_new_stock=bool(data.get("is_new_stock")),
        listing_date=_optional_str(data.get("listing_date")),
        raw=dict(data.get("raw") or {}),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render stock emotion report Markdown sections.")
    parser.add_argument("--organized", required=True, type=Path, help="Organized JSON path.")
    parser.add_argument(
        "--section",
        choices=("ladder",),
        default="ladder",
        help="Report section to render.",
    )
    args = parser.parse_args(argv)

    organized = load_organized_limit_pool(args.organized)
    if args.section == "ladder":
        print(render_ladder_section(organized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
