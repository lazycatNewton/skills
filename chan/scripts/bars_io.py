#!/usr/bin/env python3
"""
Utilities for persisting qfq daily bars fetched by an Agent through mcp_stock.

This module deliberately does not call MCP tools directly. In a Codex skill,
the Agent performs the MCP call, then passes the returned payload here for
validation, normalization, and deterministic local persistence.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


DATE_PATTERN = re.compile(r"^\d{8}$")
REQUIRED_BAR_FIELDS = ("date", "open", "high", "low", "close", "volume")


def validate_yyyymmdd(value: str, field_name: str) -> str:
    """Validate dates in 20060102 / YYYYMMDD format."""
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        raise ValueError(f"{field_name} must use YYYYMMDD format, got {value!r}")

    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid calendar date: {value!r}") from exc

    return value


def validate_symbol(symbol: str) -> str:
    """Validate and normalize an A-share symbol used in output filenames."""
    if not isinstance(symbol, str):
        raise ValueError(f"symbol must be a string, got {type(symbol).__name__}")

    normalized = symbol.strip()
    if not re.fullmatch(r"\d{6}", normalized):
        raise ValueError(f"symbol must be a 6-digit stock code, got {symbol!r}")

    return normalized


def build_bars_path(
    symbol: str,
    start_date: str,
    end_date: str,
    base_dir: str | Path | None = None,
) -> Path:
    """
    Build the required relative output path:
    output/bars/{symbol}-{start_date}-{end_date}.json
    """
    normalized_symbol = validate_symbol(symbol)
    normalized_start = validate_yyyymmdd(start_date, "start_date")
    normalized_end = validate_yyyymmdd(end_date, "end_date")

    if normalized_start > normalized_end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    root = Path.cwd() if base_dir is None else Path(base_dir)
    filename = f"{normalized_symbol}-{normalized_start}-{normalized_end}.json"
    return root / "output" / "bars" / filename


def extract_bars(payload: Any) -> list[dict[str, Any]]:
    """
    Extract bars from common mcp_stock payload shapes.

    Supported shapes:
    - [bar, bar, ...]
    - {"result": [bar, ...]}
    - {"bars": [bar, ...]}
    - {"data": [bar, ...]}
    - {"data": {"bars": [bar, ...]}}
    """
    if isinstance(payload, list):
        bars = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("result"), list):
            bars = payload["result"]
        elif isinstance(payload.get("bars"), list):
            bars = payload["bars"]
        elif isinstance(payload.get("data"), list):
            bars = payload["data"]
        elif isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("bars"), list):
            bars = payload["data"]["bars"]
        else:
            raise ValueError("payload must contain a bars list")
    else:
        raise ValueError("payload must be a list or object containing bars")

    if not all(isinstance(bar, dict) for bar in bars):
        raise ValueError("every bar must be a JSON object")

    return list(bars)


def normalize_bar(raw_bar: dict[str, Any]) -> dict[str, Any]:
    """Normalize one daily bar into the skill's canonical JSON shape."""
    date_value = raw_bar.get("date", raw_bar.get("trade_date"))
    date_text = str(date_value)
    validate_yyyymmdd(date_text, "bar.date")

    normalized = {
        "date": date_text,
        "open": float(raw_bar["open"]),
        "high": float(raw_bar["high"]),
        "low": float(raw_bar["low"]),
        "close": float(raw_bar["close"]),
        "volume": float(raw_bar["volume"]),
    }

    return normalized


def normalize_bars(payload: Any) -> list[dict[str, Any]]:
    """Extract, normalize, sort, and validate qfq daily bars."""
    bars = [normalize_bar(bar) for bar in extract_bars(payload)]
    bars.sort(key=lambda bar: bar["date"])

    if not bars:
        raise ValueError("bars cannot be empty")

    seen_dates: set[str] = set()
    for bar in bars:
        if bar["date"] in seen_dates:
            raise ValueError(f"duplicate bar date: {bar['date']}")
        seen_dates.add(bar["date"])

        if bar["high"] < max(bar["open"], bar["close"], bar["low"]):
            raise ValueError(f"invalid high on {bar['date']}")
        if bar["low"] > min(bar["open"], bar["close"], bar["high"]):
            raise ValueError(f"invalid low on {bar['date']}")

    return bars


def build_bars_document(
    symbol: str,
    start_date: str,
    end_date: str,
    payload: Any,
) -> dict[str, Any]:
    """Build the canonical persisted document for this skill."""
    normalized_symbol = validate_symbol(symbol)
    normalized_start = validate_yyyymmdd(start_date, "start_date")
    normalized_end = validate_yyyymmdd(end_date, "end_date")
    if normalized_start > normalized_end:
        raise ValueError("start_date must be earlier than or equal to end_date")

    bars = normalize_bars(payload)
    for bar in bars:
        if bar["date"] < normalized_start or bar["date"] > normalized_end:
            raise ValueError(f"bar date {bar['date']} is outside requested range")

    return {
        "symbol": normalized_symbol,
        "start_date": normalized_start,
        "end_date": normalized_end,
        "period": "daily",
        "adjust": "qfq",
        "source": "mcp_stock",
        "bars": bars,
    }


def save_bars_document(
    symbol: str,
    start_date: str,
    end_date: str,
    payload: Any,
    base_dir: str | Path | None = None,
) -> Path:
    """Persist normalized mcp_stock bars under output/bars."""
    output_path = build_bars_path(symbol, start_date, end_date, base_dir=base_dir)
    document = build_bars_document(symbol, start_date, end_date, payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return output_path
