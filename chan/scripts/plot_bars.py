#!/usr/bin/env python3
"""
Render normalized daily bars JSON as a candlestick (K-line) chart.

Usage:
  python3 chan/scripts/plot_bars.py output/bars/603629-20250101-20250103.json
  python3 chan/scripts/plot_bars.py output/bars/603629-20250101-20250103.json --output /tmp/603629.png
  python3 chan/scripts/plot_bars.py output/bars/603629-20250101-20250103.json --backend svg
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal

from bars_io import normalize_bars, validate_symbol, validate_yyyymmdd
from chan_core import ChanAnalysis, DivergenceKind, FractalKind, SignalKind, StrokeDirection, analyze_chan


UP_COLOR = "#d62728"
DOWN_COLOR = "#2ca02c"
GRID_COLOR = "#e6e8eb"
TEXT_COLOR = "#24292f"
MUTED_TEXT_COLOR = "#6e7781"
BACKGROUND_COLOR = "#ffffff"
FRACTAL_TOP_COLOR = "#d62728"
FRACTAL_BOTTOM_COLOR = "#2563eb"
STROKE_COLOR = "#d62728"
ZHONGSHU_COLOR = "#2563eb"
MACD_DIF_COLOR = "#f59e0b"
MACD_DEA_COLOR = "#2563eb"
BUY_SIGNAL_COLOR = "#2563eb"
SELL_SIGNAL_COLOR = "#d62728"


Backend = Literal["auto", "mplfinance", "svg"]


@dataclass(frozen=True)
class OverlayFractal:
    kind: FractalKind
    index: int
    price: float


@dataclass(frozen=True)
class OverlayStroke:
    direction: StrokeDirection
    start_index: int
    start_price: float
    end_index: int
    end_price: float


@dataclass(frozen=True)
class OverlayZhongshu:
    start_index: int
    end_index: int
    zd: float
    zg: float
    zd_source_index: int
    zg_source_index: int


@dataclass(frozen=True)
class OverlaySignal:
    kind: SignalKind
    index: int
    price: float
    label: str


@dataclass(frozen=True)
class OverlayDivergence:
    kind: DivergenceKind
    index: int
    price: float
    label: str


@dataclass(frozen=True)
class OverlayTradeArrow:
    direction: Literal["buy", "sell"]
    index: int
    label: str


@dataclass(frozen=True)
class ChartOverlay:
    fractals: list[OverlayFractal]
    strokes: list[OverlayStroke]
    zhongshu: list[OverlayZhongshu]
    signals: list[OverlaySignal]
    divergences: list[OverlayDivergence]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a bars JSON file as a K-line chart.")
    parser.add_argument("input", help="JSON file containing saved bars or a raw mcp_stock payload.")
    parser.add_argument(
        "--backend",
        choices=("auto", "mplfinance", "svg"),
        default="auto",
        help="Chart renderer. auto prefers mplfinance when installed and falls back to svg.",
    )
    parser.add_argument("--output", help="Output path. Defaults to output/charts/{symbol}-{start}-{end}.png.")
    parser.add_argument("--width", type=int, default=1200, help="Chart width in pixels.")
    parser.add_argument("--height", type=int, default=760, help="Chart height in pixels.")
    parser.add_argument("--dpi", type=int, default=120, help="DPI used by the mplfinance backend.")
    parser.add_argument("--no-volume", action="store_true", help="Hide the volume panel.")
    return parser.parse_args()


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def infer_metadata(payload: Any, bars: list[dict[str, Any]], input_path: Path) -> dict[str, str]:
    symbol = ""
    start_date = bars[0]["date"]
    end_date = bars[-1]["date"]

    if isinstance(payload, dict):
        raw_symbol = payload.get("symbol")
        raw_start = payload.get("start_date")
        raw_end = payload.get("end_date")
        if isinstance(raw_symbol, str):
            symbol = validate_symbol(raw_symbol)
        if isinstance(raw_start, str):
            start_date = validate_yyyymmdd(raw_start, "start_date")
        if isinstance(raw_end, str):
            end_date = validate_yyyymmdd(raw_end, "end_date")

    if not symbol:
        stem_parts = input_path.stem.split("-")
        if stem_parts and len(stem_parts[0]) == 6 and stem_parts[0].isdigit():
            symbol = stem_parts[0]
        else:
            symbol = "bars"

    return {"symbol": symbol, "start_date": start_date, "end_date": end_date}


def build_default_output_path(
    metadata: dict[str, str],
    *,
    extension: str,
    base_dir: str | Path | None = None,
) -> Path:
    root = Path.cwd() if base_dir is None else Path(base_dir)
    filename = f"{metadata['symbol']}-{metadata['start_date']}-{metadata['end_date']}.{extension}"
    return root / "output" / "charts" / filename


def format_cwd_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def has_mplfinance() -> bool:
    configure_plot_cache()
    try:
        import mplfinance  # noqa: F401
        import pandas  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_backend(requested: Backend, output_path: Path | None = None) -> Literal["mplfinance", "svg"]:
    if requested == "svg":
        return "svg"
    if requested == "mplfinance":
        if not has_mplfinance():
            raise RuntimeError("mplfinance backend requires pandas, matplotlib, and mplfinance")
        return "mplfinance"
    if output_path is not None and output_path.suffix.lower() == ".svg":
        return "svg"
    return "mplfinance" if has_mplfinance() else "svg"


def configure_plot_cache() -> None:
    cache_root = Path(tempfile.gettempdir()) / "chan-plot-cache"
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    xdg_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))


def price_to_y(price: float, min_price: float, max_price: float, top: float, height: float) -> float:
    return top + (max_price - price) / (max_price - min_price) * height


def format_date(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").strftime("%m-%d")


def svg_line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str,
    width: float = 1.0,
    *,
    dasharray: str | None = None,
) -> str:
    dash = f' stroke-dasharray="{dasharray}"' if dasharray else ""
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{color}" stroke-width="{width:.2f}"{dash} />'
    )


def svg_circle(x: float, y: float, radius: float, color: str) -> str:
    return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" />'


def svg_triangle(x: float, y: float, size: float, color: str, *, direction: Literal["up", "down"]) -> str:
    if direction == "up":
        points = [(x, y - size), (x - size, y + size), (x + size, y + size)]
    else:
        points = [(x, y + size), (x - size, y - size), (x + size, y - size)]
    value = " ".join(f"{point_x:.2f},{point_y:.2f}" for point_x, point_y in points)
    return f'<polygon points="{value}" fill="{color}" />'


def svg_text(
    text: str,
    x: float,
    y: float,
    *,
    size: int = 12,
    color: str = TEXT_COLOR,
    anchor: str = "start",
    weight: str = "400",
) -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" fill="{color}" font-size="{size}" '
        f'font-family="Arial, sans-serif" font-weight="{weight}" text-anchor="{anchor}">'
        f"{escape(text)}</text>"
    )


def svg_rect_outline(
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
    *,
    stroke_width: float = 1.0,
    dasharray: str | None = None,
) -> str:
    dash = f' stroke-dasharray="{dasharray}"' if dasharray else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width:.2f}"{dash} />'
    )


def svg_polyline(points: list[tuple[float, float]], color: str, width: float = 1.0) -> str:
    if not points:
        return ""
    value = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return f'<polyline points="{value}" fill="none" stroke="{color}" stroke-width="{width:.2f}" />'


def svg_vertical_arrow(x: float, y_start: float, y_end: float, color: str, *, width: float = 1.1) -> list[str]:
    if y_end < y_start:
        head_points = [(x, y_end), (x - 4, y_end + 7), (x + 4, y_end + 7)]
    else:
        head_points = [(x, y_end), (x - 4, y_end - 7), (x + 4, y_end - 7)]
    head = " ".join(f"{px:.2f},{py:.2f}" for px, py in head_points)
    return [
        svg_line(x, y_start, x, y_end, color, width, dasharray="4 3"),
        f'<polygon points="{head}" fill="{color}" />',
    ]


def divergence_display_label(kind: DivergenceKind) -> str:
    if kind == "bottom_exhaustion":
        return "BC-B"
    if kind == "top_exhaustion":
        return "BC-S"
    return "DIV-B" if kind == "bottom_divergence" else "DIV-S"


def is_buy_signal(kind: SignalKind) -> bool:
    return kind.endswith("buy")


def build_trade_arrows(overlay: ChartOverlay) -> list[OverlayTradeArrow]:
    grouped: dict[tuple[str, int], list[str]] = {}
    for divergence in overlay.divergences:
        direction: Literal["buy", "sell"] = "buy" if "bottom" in divergence.kind else "sell"
        grouped.setdefault((direction, divergence.index), []).append(divergence.label)
    for signal in overlay.signals:
        direction = "buy" if is_buy_signal(signal.kind) else "sell"
        grouped.setdefault((direction, signal.index), []).append(signal.label)

    arrows: list[OverlayTradeArrow] = []
    for (direction, index), labels in sorted(grouped.items(), key=lambda item: item[0][1]):
        deduped_labels = list(dict.fromkeys(labels))
        arrows.append(OverlayTradeArrow(direction, index, "/".join(deduped_labels)))
    return arrows


def trade_arrow_label_lanes(arrows: list[OverlayTradeArrow], min_gap: int = 6, lane_count: int = 3) -> dict[tuple[str, int, str], int]:
    last_index_by_lane: dict[tuple[str, int], int] = {}
    lanes: dict[tuple[str, int, str], int] = {}
    for arrow in arrows:
        lane = 0
        while lane < lane_count:
            previous_index = last_index_by_lane.get((arrow.direction, lane))
            if previous_index is None or arrow.index - previous_index >= min_gap:
                break
            lane += 1
        if lane == lane_count:
            lane = lane_count - 1
        last_index_by_lane[(arrow.direction, lane)] = arrow.index
        lanes[(arrow.direction, arrow.index, arrow.label)] = lane
    return lanes


def build_chart_overlay(analysis: ChanAnalysis) -> ChartOverlay:
    return ChartOverlay(
        fractals=[
            OverlayFractal(fractal.kind, fractal.index, fractal.price)
            for fractal in analysis.fractals
        ],
        strokes=[
            OverlayStroke(
                stroke.direction,
                stroke.start_index,
                stroke.start.price,
                stroke.end_index,
                stroke.end.price,
            )
            for stroke in analysis.strokes
        ],
        zhongshu=[
            OverlayZhongshu(
                center.start_index,
                center.end_index,
                center.zd,
                center.zg,
                center.zd_source_index,
                center.zg_source_index,
            )
            for center in analysis.zhongshu
        ],
        signals=[
            OverlaySignal(signal.kind, signal.index, signal.price, signal.label)
            for signal in analysis.signals
        ],
        divergences=[
            OverlayDivergence(
                divergence.kind,
                divergence.index,
                divergence.price,
                divergence_display_label(divergence.kind),
            )
            for divergence in analysis.divergences
        ],
    )


def render_candlestick_svg(
    bars: list[dict[str, Any]],
    metadata: dict[str, str],
    *,
    width: int = 1200,
    height: int = 760,
    show_volume: bool = True,
) -> str:
    if width < 640:
        raise ValueError("width must be at least 640")
    if height < 420:
        raise ValueError("height must be at least 420")

    left = 76
    right = 36
    top = 58
    bottom = 58
    panel_gap = 34
    volume_height = 132 if show_volume else 0
    macd_height = 132
    date_label_height = 24
    gap_count = 2 if show_volume else 1
    price_height = height - top - bottom - date_label_height - panel_gap * gap_count - volume_height - macd_height
    chart_width = width - left - right

    lows = [bar["low"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    min_price = min(lows)
    max_price = max(highs)
    price_padding = max((max_price - min_price) * 0.05, max_price * 0.005, 0.01)
    min_price -= price_padding
    max_price += price_padding

    step = chart_width / max(len(bars), 1)
    candle_width = max(4.0, min(18.0, step * 0.56))
    half_width = candle_width / 2
    analysis = analyze_chan(bars)
    overlay = build_chart_overlay(analysis)

    def x_for_index(index: int) -> float:
        return left + step * index + step / 2

    def y_for_price(price: float) -> float:
        return price_to_y(price, min_price, max_price, top, price_height)

    macd_top = top + price_height + panel_gap + volume_height + (panel_gap if show_volume else 0)
    macd_bottom = macd_top + macd_height
    date_label_y = macd_bottom + 22

    elements: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{BACKGROUND_COLOR}" />',
        svg_text(
            f"{metadata['symbol']} K-line {metadata['start_date']} - {metadata['end_date']}",
            left,
            30,
            size=18,
            weight="700",
        ),
    ]

    price_ticks = 5
    for index in range(price_ticks + 1):
        ratio = index / price_ticks
        y = top + price_height * ratio
        price = max_price - (max_price - min_price) * ratio
        elements.append(svg_line(left, y, width - right, y, GRID_COLOR))
        elements.append(svg_text(f"{price:.2f}", left - 10, y + 4, size=12, color=MUTED_TEXT_COLOR, anchor="end"))

    elements.append(svg_line(left, top, left, top + price_height, "#8c959f"))
    elements.append(svg_line(left, top + price_height, width - right, top + price_height, "#8c959f"))

    label_stride = max(1, len(bars) // 8)
    for index, bar in enumerate(bars):
        x = x_for_index(index)
        high_y = y_for_price(bar["high"])
        low_y = y_for_price(bar["low"])
        open_y = y_for_price(bar["open"])
        close_y = y_for_price(bar["close"])
        color = UP_COLOR if bar["close"] >= bar["open"] else DOWN_COLOR
        body_y = min(open_y, close_y)
        body_height = max(abs(close_y - open_y), 1.0)

        elements.append(svg_line(x, high_y, x, low_y, color, 1.35))
        elements.append(
            f'<rect x="{x - half_width:.2f}" y="{body_y:.2f}" width="{candle_width:.2f}" '
            f'height="{body_height:.2f}" fill="{color}" stroke="{color}" stroke-width="1" />'
        )

    for center in overlay.zhongshu:
        y_top = y_for_price(center.zg)
        y_bottom = y_for_price(center.zd)
        box_start_index = max(center.start_index - 2, 0)
        box_end_index = min(center.end_index + 2, len(bars) - 1)
        box_left = x_for_index(box_start_index) - step / 2
        box_right = x_for_index(box_end_index) + step / 2
        elements.append(
            svg_rect_outline(
                box_left,
                y_top,
                max(box_right - box_left, 1.0),
                max(y_bottom - y_top, 1.0),
                ZHONGSHU_COLOR,
                stroke_width=1.35,
                dasharray="6 4",
            )
        )

        elements.append(
            svg_text(
                f"ZG {center.zg:.2f}",
                x_for_index(center.zg_source_index),
                y_for_price(center.zg) - 8,
                size=10,
                color=FRACTAL_TOP_COLOR,
                anchor="middle",
                weight="700",
            )
        )
        elements.append(
            svg_text(
                f"ZD {center.zd:.2f}",
                x_for_index(center.zd_source_index),
                y_for_price(center.zd) + 16,
                size=10,
                color=FRACTAL_BOTTOM_COLOR,
                anchor="middle",
                weight="700",
            )
        )

    for stroke in overlay.strokes:
        elements.append(
            svg_line(
                x_for_index(stroke.start_index),
                y_for_price(stroke.start_price),
                x_for_index(stroke.end_index),
                y_for_price(stroke.end_price),
                STROKE_COLOR,
                1.45,
                dasharray="6 4",
            )
        )

    for fractal in overlay.fractals:
        color = FRACTAL_TOP_COLOR if fractal.kind == "top" else FRACTAL_BOTTOM_COLOR
        elements.append(svg_circle(x_for_index(fractal.index), y_for_price(fractal.price), 3.4, color))

    trade_arrows = build_trade_arrows(overlay)
    label_lanes = trade_arrow_label_lanes(trade_arrows)
    for trade_arrow in trade_arrows:
        is_buy = trade_arrow.direction == "buy"
        color = BUY_SIGNAL_COLOR if is_buy else SELL_SIGNAL_COLOR
        x = x_for_index(trade_arrow.index)
        lane = label_lanes[(trade_arrow.direction, trade_arrow.index, trade_arrow.label)]
        if is_buy:
            y_start = top + 4
            y_end = y_for_price(bars[trade_arrow.index]["high"])
            label_y = min(y_start + 12 + lane * 12, top + price_height - 4)
        else:
            y_start = top + price_height - 4
            y_end = y_for_price(bars[trade_arrow.index]["low"])
            label_y = max(y_start - 6 - lane * 12, top + 10)
        elements.extend(svg_vertical_arrow(x, y_start, y_end, color))
        elements.append(
            svg_text(
                trade_arrow.label,
                x,
                label_y,
                size=9,
                color=color,
                anchor="middle",
                weight="700",
            )
        )

    if show_volume:
        volume_top = top + price_height + panel_gap
        volume_bottom = volume_top + volume_height
        max_volume = max(bar["volume"] for bar in bars) or 1.0
        elements.append(svg_line(left, volume_bottom, width - right, volume_bottom, "#8c959f"))
        elements.append(svg_line(left, volume_top, left, volume_bottom, "#8c959f"))
        elements.append(svg_text("Volume", left, volume_top - 8, size=12, color=MUTED_TEXT_COLOR))
        elements.append(svg_text(f"{max_volume:.0f}", left - 10, volume_top + 4, size=11, color=MUTED_TEXT_COLOR, anchor="end"))

        for index, bar in enumerate(bars):
            x = x_for_index(index)
            color = UP_COLOR if bar["close"] >= bar["open"] else DOWN_COLOR
            bar_height = max(volume_height * (bar["volume"] / max_volume), 1.0)
            elements.append(
                f'<rect x="{x - half_width:.2f}" y="{volume_bottom - bar_height:.2f}" '
                f'width="{candle_width:.2f}" height="{bar_height:.2f}" fill="{color}" opacity="0.38" />'
            )


    macd_values = [point.dif for point in analysis.macd] + [point.dea for point in analysis.macd] + [
        point.hist for point in analysis.macd
    ]
    macd_abs_max = max((abs(value) for value in macd_values), default=1.0) or 1.0

    def y_for_macd(value: float) -> float:
        return macd_top + (macd_abs_max - value) / (macd_abs_max * 2) * macd_height

    zero_y = y_for_macd(0.0)
    elements.append(svg_line(left, zero_y, width - right, zero_y, "#8c959f", 0.9))
    elements.append(svg_line(left, macd_top, left, macd_bottom, "#8c959f"))
    elements.append(svg_line(left, macd_bottom, width - right, macd_bottom, "#8c959f"))
    elements.append(svg_text("MACD", left, macd_top - 8, size=12, color=MUTED_TEXT_COLOR))
    elements.append(svg_text(f"{macd_abs_max:.2f}", left - 10, macd_top + 4, size=11, color=MUTED_TEXT_COLOR, anchor="end"))
    elements.append(svg_text(f"{-macd_abs_max:.2f}", left - 10, macd_bottom + 4, size=11, color=MUTED_TEXT_COLOR, anchor="end"))

    macd_bar_width = max(2.0, min(12.0, candle_width * 0.72))
    for point in analysis.macd:
        x = x_for_index(point.index)
        hist_y = y_for_macd(point.hist)
        bar_y = min(hist_y, zero_y)
        bar_height = max(abs(hist_y - zero_y), 1.0)
        color = UP_COLOR if point.hist >= 0 else DOWN_COLOR
        elements.append(
            f'<rect x="{x - macd_bar_width / 2:.2f}" y="{bar_y:.2f}" width="{macd_bar_width:.2f}" '
            f'height="{bar_height:.2f}" fill="{color}" opacity="0.42" />'
        )

    dif_points = [(x_for_index(point.index), y_for_macd(point.dif)) for point in analysis.macd]
    dea_points = [(x_for_index(point.index), y_for_macd(point.dea)) for point in analysis.macd]
    elements.append(svg_polyline(dif_points, MACD_DIF_COLOR, 1.15))
    elements.append(svg_polyline(dea_points, MACD_DEA_COLOR, 1.15))
    elements.append(svg_text("DIF", width - right - 72, macd_top - 8, size=11, color=MACD_DIF_COLOR, weight="700"))
    elements.append(svg_text("DEA", width - right - 38, macd_top - 8, size=11, color=MACD_DEA_COLOR, weight="700"))

    for index, bar in enumerate(bars):
        if index % label_stride == 0 or index == len(bars) - 1:
            elements.append(
                svg_text(
                    format_date(bar["date"]),
                    x_for_index(index),
                    date_label_y,
                    size=11,
                    color=MUTED_TEXT_COLOR,
                    anchor="middle",
                )
            )

    elements.append("</svg>")
    return "\n".join(elements) + "\n"


def draw_chan_overlays(price_ax: Any, macd_ax: Any, analysis: ChanAnalysis) -> None:
    from matplotlib.patches import Rectangle

    overlay = build_chart_overlay(analysis)
    tops = [fractal for fractal in overlay.fractals if fractal.kind == "top"]
    bottoms = [fractal for fractal in overlay.fractals if fractal.kind == "bottom"]

    if tops:
        price_ax.scatter(
            [fractal.index for fractal in tops],
            [fractal.price for fractal in tops],
            marker="o",
            s=22,
            color=FRACTAL_TOP_COLOR,
            edgecolors=FRACTAL_TOP_COLOR,
            zorder=5,
        )
    if bottoms:
        price_ax.scatter(
            [fractal.index for fractal in bottoms],
            [fractal.price for fractal in bottoms],
            marker="o",
            s=22,
            color=FRACTAL_BOTTOM_COLOR,
            edgecolors=FRACTAL_BOTTOM_COLOR,
            zorder=5,
        )

    for stroke in overlay.strokes:
        price_ax.plot(
            [stroke.start_index, stroke.end_index],
            [stroke.start_price, stroke.end_price],
            color=STROKE_COLOR,
            linestyle="--",
            linewidth=1.25,
            alpha=0.9,
            zorder=4,
        )

    for center in overlay.zhongshu:
        box_start_index = max(center.start_index - 2, 0)
        box_end_index = min(center.end_index + 2, len(analysis.bars) - 1)
        box_left = box_start_index - 0.5
        box_width = max(box_end_index - box_start_index + 1, 1)
        rectangle = Rectangle(
            (box_left, center.zd),
            box_width,
            center.zg - center.zd,
            facecolor="none",
            edgecolor=ZHONGSHU_COLOR,
            linewidth=1.15,
            linestyle="--",
            alpha=0.9,
            zorder=1,
        )
        price_ax.add_patch(rectangle)
        price_ax.annotate(
            f"ZG {center.zg:.2f}",
            xy=(center.zg_source_index, center.zg),
            xytext=(0, 8),
            textcoords="offset points",
            color=FRACTAL_TOP_COLOR,
            fontsize=8,
            fontweight="bold",
            va="bottom",
            ha="center",
            zorder=6,
        )
        price_ax.annotate(
            f"ZD {center.zd:.2f}",
            xy=(center.zd_source_index, center.zd),
            xytext=(0, -10),
            textcoords="offset points",
            color=FRACTAL_BOTTOM_COLOR,
            fontsize=8,
            fontweight="bold",
            va="top",
            ha="center",
            zorder=6,
        )

    trade_arrows = build_trade_arrows(overlay)
    label_lanes = trade_arrow_label_lanes(trade_arrows)
    for trade_arrow in trade_arrows:
        is_buy = trade_arrow.direction == "buy"
        color = BUY_SIGNAL_COLOR if is_buy else SELL_SIGNAL_COLOR
        lane = label_lanes[(trade_arrow.direction, trade_arrow.index, trade_arrow.label)]
        y_min, y_max = price_ax.get_ylim()
        y_span = y_max - y_min
        pad = y_span * 0.01
        bar = analysis.bars[trade_arrow.index]
        if is_buy:
            y_start = y_max - pad
            y_end = bar.high
        else:
            y_start = y_min + pad
            y_end = bar.low
        price_ax.annotate(
            "",
            xy=(trade_arrow.index, y_end),
            xytext=(trade_arrow.index, y_start),
            textcoords="data",
            arrowprops={
                "arrowstyle": "-|>",
                "color": color,
                "linestyle": (0, (3, 2)),
                "linewidth": 1.0,
                "mutation_scale": 7,
                "shrinkA": 0,
                "shrinkB": 0,
            },
            zorder=9,
        )
        label_offset = (-10 + lane * 9) if is_buy else (8 - lane * 9)
        label_va = "top" if is_buy else "bottom"
        price_ax.annotate(
            trade_arrow.label,
            xy=(trade_arrow.index, y_start),
            xytext=(0, label_offset),
            textcoords="offset points",
            ha="center",
            va=label_va,
            fontsize=7,
            color=color,
            fontweight="bold",
            zorder=10,
        )


def render_candlestick_mplfinance(
    bars: list[dict[str, Any]],
    metadata: dict[str, str],
    output_path: Path,
    *,
    width: int = 1200,
    height: int = 760,
    dpi: int = 120,
    show_volume: bool = True,
) -> None:
    configure_plot_cache()

    import mplfinance as mpf
    import pandas as pd

    analysis = analyze_chan(bars)
    records = [
        {
            "Date": pd.to_datetime(bar["date"], format="%Y%m%d"),
            "Open": bar["open"],
            "High": bar["high"],
            "Low": bar["low"],
            "Close": bar["close"],
            "Volume": bar["volume"],
        }
        for bar in bars
    ]
    frame = pd.DataFrame.from_records(records).set_index("Date")
    macd_frame = pd.DataFrame(
        {
            "DIF": [point.dif for point in analysis.macd],
            "DEA": [point.dea for point in analysis.macd],
            "Hist": [point.hist for point in analysis.macd],
        },
        index=frame.index,
    )
    macd_panel = 2 if show_volume else 1
    macd_colors = [UP_COLOR if value >= 0 else DOWN_COLOR for value in macd_frame["Hist"]]
    add_plots = [
        mpf.make_addplot(macd_frame["Hist"], type="bar", panel=macd_panel, color=macd_colors, alpha=0.42, ylabel="MACD"),
        mpf.make_addplot(macd_frame["DIF"], panel=macd_panel, color=MACD_DIF_COLOR, width=0.9),
        mpf.make_addplot(macd_frame["DEA"], panel=macd_panel, color=MACD_DEA_COLOR, width=0.9),
    ]

    market_colors = mpf.make_marketcolors(
        up=UP_COLOR,
        down=DOWN_COLOR,
        edge="inherit",
        wick="inherit",
        volume="inherit",
    )
    style = mpf.make_mpf_style(
        base_mpf_style="yahoo",
        marketcolors=market_colors,
        facecolor=BACKGROUND_COLOR,
        figcolor=BACKGROUND_COLOR,
        gridcolor=GRID_COLOR,
        gridstyle="-",
        rc={
            "axes.labelcolor": TEXT_COLOR,
            "axes.edgecolor": "#8c959f",
            "axes.titlesize": 14,
            "font.size": 10,
            "savefig.bbox": "tight",
        },
    )

    plot_kwargs: dict[str, Any] = {
        "type": "candle",
        "style": style,
        "volume": show_volume,
        "figsize": (width / dpi, height / dpi),
        "datetime_format": "%m-%d",
        "xrotation": 0,
        "tight_layout": False,
        "ylabel": "Price",
        "addplot": add_plots,
        "returnfig": True,
    }
    if show_volume:
        plot_kwargs["ylabel_lower"] = "Volume"
        plot_kwargs["panel_ratios"] = (5, 1.35, 1.45)
    else:
        plot_kwargs["panel_ratios"] = (5, 1.45)

    fig, axes = mpf.plot(frame, **plot_kwargs)
    fig.suptitle(
        f"{metadata['symbol']} K-line {metadata['start_date']} - {metadata['end_date']}",
        fontsize=14,
        fontweight="bold",
        color=TEXT_COLOR,
        y=0.985,
    )
    fig.subplots_adjust(top=0.91)
    price_ax = axes[0]
    macd_ax = axes[4] if show_volume else axes[2]
    if show_volume:
        axes[0].tick_params(axis="x", labelbottom=False)
        axes[2].tick_params(axis="x", labelbottom=False)
        fig.subplots_adjust(top=0.91, hspace=0.12)
    draw_chan_overlays(price_ax, macd_ax, analysis)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", pad_inches=0.16)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    payload = load_json(input_path)
    bars = normalize_bars(payload)
    metadata = infer_metadata(payload, bars, input_path)
    requested_backend: Backend = args.backend
    requested_output = Path(args.output) if args.output else None
    backend = resolve_backend(requested_backend, requested_output)
    default_extension = "png" if backend == "mplfinance" else "svg"
    output_path = requested_output or build_default_output_path(metadata, extension=default_extension)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if backend == "mplfinance":
        render_candlestick_mplfinance(
            bars,
            metadata,
            output_path,
            width=args.width,
            height=args.height,
            dpi=args.dpi,
            show_volume=not args.no_volume,
        )
    else:
        svg = render_candlestick_svg(
            bars,
            metadata,
            width=args.width,
            height=args.height,
            show_volume=not args.no_volume,
        )
        output_path.write_text(svg, encoding="utf-8")

    print(format_cwd_relative_path(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
