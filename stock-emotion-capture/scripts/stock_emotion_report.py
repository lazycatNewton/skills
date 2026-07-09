#!/usr/bin/env python3
"""Markdown report rendering helpers for stock emotion capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts.stock_emotion_data import (
        IndustrySummary,
        OrganizedLimitPool,
        StockRecord,
        format_ladder_matrix_markdown,
        format_limit_down_ladder_matrix_markdown,
        validate_trade_date,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from stock_emotion_data import (
        IndustrySummary,
        OrganizedLimitPool,
        StockRecord,
        format_ladder_matrix_markdown,
        format_limit_down_ladder_matrix_markdown,
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
    return "\n\n".join(
        [
            "## 3. 连板梯队",
            "### 涨停连板梯队",
            format_ladder_matrix_markdown(organized),
            "### 跌停连板梯队",
            format_limit_down_ladder_matrix_markdown(organized),
        ]
    )


def render_industry_section(organized: OrganizedLimitPool) -> str:
    """Render section 2 with every filtered limit-up and limit-down stock."""
    lines = [
        "## 2. 主线板块复盘",
        "",
        "以下为 `industry` 行业口径，不等同于完整概念题材。本表覆盖过滤后的全部涨停和跌停数据，不截断行业或股票列表。",
        "",
        _markdown_row(["行业口径", "涨停", "连板", "最高板", "跌停", "涨停股票", "跌停股票"]),
        _markdown_row(["---", "---:", "---:", "---:", "---:", "---", "---"]),
    ]
    for item in organized.industry_view:
        lines.append(
            _markdown_row(
                [
                    item.industry,
                    str(item.limit_up_count),
                    str(item.lianban_count),
                    str(item.max_board_height),
                    str(item.limit_down_count),
                    _stock_list_by_symbols(organized.limit_up, item.limit_up_symbols),
                    _stock_list_by_symbols(organized.limit_down, item.limit_down_symbols),
                ]
            )
        )
    return "\n".join(lines)


def render_limit_up_structure_section(organized: OrganizedLimitPool) -> str:
    """Render section 4 as a full limit-up structure table."""
    early_count = sum(1 for item in organized.limit_up if (item.first_limit_time or "") <= "093000")
    zero_break_count = sum(1 for item in organized.limit_up if item.break_limit_count == 0)
    high_break_count = sum(1 for item in organized.limit_up if item.break_limit_count >= 5)
    lines = [
        "## 4. 涨停结构分析",
        "",
        (
            f"09:30 前首次封板 {early_count} 只，炸板 0 次 {zero_break_count} 只，"
            f"炸板大于等于 5 次 {high_break_count} 只。下表覆盖过滤后的全部涨停股票。"
        ),
        "",
        _markdown_row(["排名", "代码", "名称", "行业口径", "n板", "首封", "末封", "炸板", "封单强度", "结构判断"]),
        _markdown_row(["---:", "---", "---", "---", "---:", "---", "---", "---:", "---:", "---"]),
    ]
    for item in sorted(organized.limit_up, key=lambda stock: stock.rank or 999999):
        lines.append(
            _markdown_row(
                [
                    str(item.rank or ""),
                    item.symbol,
                    item.name,
                    item.industry,
                    str(max(item.consecutive_limit_up_days, 1)),
                    _format_time(item.first_limit_time),
                    _format_time(item.last_limit_time),
                    str(item.break_limit_count),
                    _format_percent(item.seal_strength),
                    _limit_up_structure_label(item),
                ]
            )
        )
    return "\n".join(lines)


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
        industry_view=tuple(_industry_summary_from_mapping(item) for item in data.get("industry_view", []) or []),
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


def _industry_summary_from_mapping(data: Mapping[str, Any]) -> IndustrySummary:
    return IndustrySummary(
        industry=str(data.get("industry") or "未分类"),
        limit_up_count=_optional_int(data.get("limit_up_count")) or 0,
        lianban_count=_optional_int(data.get("lianban_count")) or 0,
        max_board_height=_optional_int(data.get("max_board_height")) or 0,
        limit_down_count=_optional_int(data.get("limit_down_count")) or 0,
        limit_up_symbols=tuple(str(item) for item in data.get("limit_up_symbols", []) or []),
        limit_down_symbols=tuple(str(item) for item in data.get("limit_down_symbols", []) or []),
    )


def _stock_list_by_symbols(records: tuple[StockRecord, ...], symbols: tuple[str, ...]) -> str:
    by_symbol = {item.symbol: item for item in records}
    values = []
    for symbol in symbols:
        item = by_symbol.get(symbol)
        if item is None:
            values.append(symbol)
        else:
            values.append(f"`{item.symbol} {item.name}`")
    return "、".join(values) if values else "-"


def _format_time(value: str | None) -> str:
    if not value:
        return "-"
    if len(value) == 6 and value.isdigit():
        return f"{value[:2]}:{value[2:4]}:{value[4:]}"
    return value


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _limit_up_structure_label(item: StockRecord) -> str:
    height = max(item.consecutive_limit_up_days, 1)
    if item.break_limit_count >= 5:
        return "高分歧"
    if item.break_limit_count == 0 and item.first_limit_time and item.last_limit_time == item.first_limit_time:
        if height >= 2:
            return "连板强封"
        return "首板强封"
    if item.last_limit_time and item.last_limit_time >= "145000":
        return "尾盘回封"
    return "换手回封"


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


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
        choices=("industry", "ladder", "limit-up-structure"),
        default="ladder",
        help="Report section to render.",
    )
    args = parser.parse_args(argv)

    organized = load_organized_limit_pool(args.organized)
    renderers = {
        "industry": render_industry_section,
        "ladder": render_ladder_section,
        "limit-up-structure": render_limit_up_structure_section,
    }
    print(renderers[args.section](organized))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
