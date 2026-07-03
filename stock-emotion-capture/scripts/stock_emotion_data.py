#!/usr/bin/env python3
"""Data organization layer for A-share emotion review limit pools."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


DATE_RE = re.compile(r"^\d{8}$")


@dataclass(frozen=True)
class StockRecord:
    rank: int | None
    symbol: str
    name: str
    industry: str
    change_pct: float | None
    latest_price: float | None
    turnover: float | None
    free_float_market_cap: float | None
    total_market_cap: float | None
    turnover_rate: float | None
    seal_fund: float | None
    first_limit_time: str | None
    last_limit_time: str | None
    break_limit_count: int
    consecutive_limit_up_days: int
    consecutive_limit_down_days: int
    is_st: bool
    is_new_stock: bool
    listing_date: str | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def is_special(self) -> bool:
        return self.is_st or self.is_new_stock

    @property
    def seal_strength(self) -> float | None:
        if not self.seal_fund or not self.free_float_market_cap:
            return None
        if self.free_float_market_cap <= 0:
            return None
        return self.seal_fund / self.free_float_market_cap


@dataclass(frozen=True)
class IndustrySummary:
    industry: str
    limit_up_count: int
    lianban_count: int
    max_board_height: int
    limit_down_count: int
    limit_up_symbols: tuple[str, ...]
    limit_down_symbols: tuple[str, ...]


@dataclass(frozen=True)
class LadderLevel:
    board_height: int
    count: int
    industries: tuple[str, ...]
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class OrganizedLimitPool:
    date: str
    source: str | None
    include_special: bool
    raw_counts: dict[str, int]
    filtered_counts: dict[str, int]
    excluded_counts: dict[str, int]
    flags: dict[str, Any]
    limit_up: tuple[StockRecord, ...]
    limit_down: tuple[StockRecord, ...]
    industry_view: tuple[IndustrySummary, ...]
    ladder_view: tuple[LadderLevel, ...]
    data_issues: tuple[str, ...]


LimitPoolFetcher = Callable[[str, str], Any]


def should_include_special(user_text: str) -> bool:
    """Return True only when the user explicitly asks to include ST and new stocks."""
    return "包括ST和新股" in user_text


def fetch_and_organize_limit_pool(
    date: str,
    fetcher: LimitPoolFetcher,
    *,
    include_special: bool = False,
) -> OrganizedLimitPool:
    """Fetch `pool="both"` through a supplied MCP adapter and organize the payload."""
    validate_trade_date(date)
    payload = fetcher(date, "both")
    return organize_limit_pool(payload, include_special=include_special)


def organize_limit_pool(payload: Any, *, include_special: bool = False) -> OrganizedLimitPool:
    """Normalize and organize a get_limit_pool payload into review-ready views."""
    data = parse_limit_pool_payload(payload)
    issues = collect_data_issues(data)

    raw_limit_up = [_normalize_record(item, "up") for item in data.get("limit_up", []) or []]
    raw_limit_down = [_normalize_record(item, "down") for item in data.get("limit_down", []) or []]

    if include_special:
        limit_up = raw_limit_up
        limit_down = raw_limit_down
    else:
        limit_up = [item for item in raw_limit_up if not item.is_special]
        limit_down = [item for item in raw_limit_down if not item.is_special]

    excluded_up = len(raw_limit_up) - len(limit_up)
    excluded_down = len(raw_limit_down) - len(limit_down)

    return OrganizedLimitPool(
        date=str(data.get("date") or ""),
        source=_optional_str(data.get("source")),
        include_special=include_special,
        raw_counts=_counts_from_payload(data, raw_limit_up, raw_limit_down),
        filtered_counts={
            "limit_up": len(limit_up),
            "limit_down": len(limit_down),
        },
        excluded_counts={
            "limit_up": excluded_up,
            "limit_down": excluded_down,
            "st_or_new_stock": excluded_up + excluded_down,
        },
        flags=dict(data.get("flags") or {}),
        limit_up=tuple(limit_up),
        limit_down=tuple(limit_down),
        industry_view=tuple(_build_industry_view(limit_up, limit_down)),
        ladder_view=tuple(_build_ladder_view(limit_up)),
        data_issues=tuple(issues),
    )


def parse_limit_pool_payload(payload: Any) -> dict[str, Any]:
    """Accept raw dict, JSON text, or MCP text-content list and return a dict."""
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, str):
        parsed = json.loads(payload)
        if not isinstance(parsed, Mapping):
            raise ValueError("limit pool JSON must decode to an object")
        return dict(parsed)
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        text_parts: list[str] = []
        for item in payload:
            if isinstance(item, Mapping) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        if text_parts:
            return parse_limit_pool_payload("\n".join(text_parts))
    raise TypeError("unsupported limit pool payload type")


def validate_trade_date(date: str) -> None:
    if not DATE_RE.match(date):
        raise ValueError("date must use YYYYMMDD format")


def collect_data_issues(data: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    date = data.get("date")
    if not isinstance(date, str) or not DATE_RE.match(date):
        issues.append("date_missing_or_invalid")
    limit_up = data.get("limit_up")
    limit_down = data.get("limit_down")
    if not isinstance(limit_up, list):
        issues.append("limit_up_missing_or_invalid")
    if not isinstance(limit_down, list):
        issues.append("limit_down_missing_or_invalid")
    if isinstance(limit_up, list) and isinstance(limit_down, list) and not limit_up and not limit_down:
        issues.append("empty_limit_pool")
    return issues


def organized_limit_pool_to_dict(organized: OrganizedLimitPool) -> dict[str, Any]:
    """Convert organized dataclasses to a JSON-serializable dict."""
    return asdict(organized)


def format_ladder_matrix_markdown(
    organized: OrganizedLimitPool,
    *,
    min_board_height: int = 2,
) -> str:
    """Render the report ladder section as an n-board by industry Markdown matrix."""
    if min_board_height < 1:
        raise ValueError("min_board_height must be at least 1")

    rows_by_height: dict[int, dict[str, list[StockRecord]]] = {}
    industry_order: list[str] = []
    heights = sorted(
        {
            max(item.consecutive_limit_up_days, 1)
            for item in organized.limit_up
            if max(item.consecutive_limit_up_days, 1) >= min_board_height
        },
        reverse=True,
    )

    for height in heights:
        level_items = sorted(
            (
                item
                for item in organized.limit_up
                if max(item.consecutive_limit_up_days, 1) == height
            ),
            key=lambda item: item.rank or 999999,
        )
        row: dict[str, list[StockRecord]] = {}
        for item in level_items:
            row.setdefault(item.industry, []).append(item)
            if item.industry not in industry_order:
                industry_order.append(item.industry)
        rows_by_height[height] = row

    if not heights:
        return f"当日无 {min_board_height} 板及以上连板股。"

    header = ["n板", *industry_order]
    lines = [
        _markdown_row(header),
        _markdown_row(["---", *(["---"] * len(industry_order))]),
    ]
    for height in heights:
        row_cells = [f"{height}板"]
        for industry in industry_order:
            items = rows_by_height[height].get(industry, [])
            if not items:
                row_cells.append("-")
                continue
            row_cells.append("、".join(f"`{item.symbol} {item.name}`" for item in items))
        lines.append(_markdown_row(row_cells))
    return "\n".join(lines)


def _build_industry_view(
    limit_up: Sequence[StockRecord],
    limit_down: Sequence[StockRecord],
) -> list[IndustrySummary]:
    industries = sorted({item.industry for item in (*limit_up, *limit_down)})
    summaries: list[IndustrySummary] = []
    for industry in industries:
        up_items = [item for item in limit_up if item.industry == industry]
        down_items = [item for item in limit_down if item.industry == industry]
        summaries.append(
            IndustrySummary(
                industry=industry,
                limit_up_count=len(up_items),
                lianban_count=sum(1 for item in up_items if item.consecutive_limit_up_days >= 2),
                max_board_height=max((item.consecutive_limit_up_days for item in up_items), default=0),
                limit_down_count=len(down_items),
                limit_up_symbols=tuple(item.symbol for item in up_items),
                limit_down_symbols=tuple(item.symbol for item in down_items),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (item.limit_up_count, item.lianban_count, item.max_board_height),
        reverse=True,
    )


def _build_ladder_view(limit_up: Sequence[StockRecord]) -> list[LadderLevel]:
    heights = sorted({max(item.consecutive_limit_up_days, 1) for item in limit_up}, reverse=True)
    levels: list[LadderLevel] = []
    for height in heights:
        items = [item for item in limit_up if max(item.consecutive_limit_up_days, 1) == height]
        levels.append(
            LadderLevel(
                board_height=height,
                count=len(items),
                industries=tuple(sorted({item.industry for item in items})),
                symbols=tuple(item.symbol for item in sorted(items, key=lambda item: item.rank or 999999)),
            )
        )
    return levels


def _normalize_record(raw: Mapping[str, Any], side: str) -> StockRecord:
    return StockRecord(
        rank=_optional_int(raw.get("rank")),
        symbol=str(raw.get("symbol") or ""),
        name=str(raw.get("name") or ""),
        industry=str(raw.get("industry") or "未分类"),
        change_pct=_optional_float(raw.get("change_pct")),
        latest_price=_optional_float(raw.get("latest_price")),
        turnover=_optional_float(raw.get("turnover")),
        free_float_market_cap=_optional_float(raw.get("free_float_market_cap")),
        total_market_cap=_optional_float(raw.get("total_market_cap")),
        turnover_rate=_optional_float(raw.get("turnover_rate")),
        seal_fund=_optional_float(raw.get("seal_fund")),
        first_limit_time=_optional_str(raw.get("first_limit_time")),
        last_limit_time=_optional_str(raw.get("last_limit_time")),
        break_limit_count=_optional_int(raw.get("break_limit_count")) or 0,
        consecutive_limit_up_days=_up_days(raw, side),
        consecutive_limit_down_days=_down_days(raw, side),
        is_st=bool(raw.get("is_st")),
        is_new_stock=bool(raw.get("is_new_stock")),
        listing_date=_optional_str(raw.get("listing_date")),
        raw=dict(raw),
    )


def _up_days(raw: Mapping[str, Any], side: str) -> int:
    if side != "up":
        return 0
    return max(_optional_int(raw.get("consecutive_limit_up_days")) or 1, 1)


def _down_days(raw: Mapping[str, Any], side: str) -> int:
    if side != "down":
        return 0
    return max(_optional_int(raw.get("consecutive_limit_down_days")) or 1, 1)


def _counts_from_payload(
    data: Mapping[str, Any],
    raw_limit_up: Sequence[StockRecord],
    raw_limit_down: Sequence[StockRecord],
) -> dict[str, int]:
    counts = data.get("counts")
    if isinstance(counts, Mapping):
        return {
            "limit_up": _optional_int(counts.get("limit_up")) or len(raw_limit_up),
            "limit_down": _optional_int(counts.get("limit_down")) or len(raw_limit_down),
        }
    return {"limit_up": len(raw_limit_up), "limit_down": len(raw_limit_down)}


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


def _markdown_row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
