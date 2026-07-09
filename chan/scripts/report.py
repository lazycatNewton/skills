#!/usr/bin/env python3
"""Generate PDF Chan-analysis reports as the only final artifacts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import shutil
import textwrap
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from bars_io import normalize_bars, validate_symbol, validate_yyyymmdd
from chan_core import ChanAnalysis, ChanSignal, Divergence, Zhongshu, analyze_chan
from plot_bars import has_mplfinance, render_candlestick_mplfinance, render_candlestick_svg


SKILL_ROOT = Path(__file__).resolve().parents[1]


def resolve_output_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path.cwd() / path


def resolve_input_path(path: Path) -> Path:
    if path.is_absolute() or path.exists():
        return path
    skill_path = SKILL_ROOT / path
    if skill_path.exists():
        return skill_path
    return path


def format_cwd_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


@dataclass(frozen=True)
class ChartAssets:
    svg_path: Path
    png_path: Path | None


@dataclass(frozen=True)
class ReportModel:
    symbol: str
    name: str
    start_date: str
    end_date: str
    generated_at: str
    bars: list[dict[str, Any]]
    analysis: ChanAnalysis
    chart_svg_path: Path | None
    chart_png_path: Path | None

    @property
    def display_name(self) -> str:
        return f"{self.name}（{self.symbol}）" if self.name else self.symbol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Chan-analysis PDF report.")
    parser.add_argument("--input", required=True, help="Saved bars JSON or raw mcp_stock payload.")
    parser.add_argument("--symbol", help="6-digit A-share stock code. Defaults to payload metadata or filename.")
    parser.add_argument("--name", default="", help="Stock display name used in report titles.")
    parser.add_argument("--output-dir", default="output/reports/chan", help="Directory for final PDF reports.")
    parser.add_argument("--width", type=int, default=1400, help="Temporary chart width in pixels.")
    parser.add_argument("--height", type=int, default=920, help="Temporary chart height in pixels.")
    parser.add_argument("--dpi", type=int, default=140, help="Temporary chart DPI.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep this run's temporary files for debugging.")
    parser.add_argument(
        "--no-cleanup-artifacts",
        action="store_true",
        help="Do not remove matching files from output/bars and output/charts after report generation.",
    )
    return parser.parse_args()


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def infer_symbol(payload: Any, input_path: Path, explicit_symbol: str | None) -> str:
    if explicit_symbol:
        return validate_symbol(explicit_symbol)
    if isinstance(payload, dict) and isinstance(payload.get("symbol"), str):
        return validate_symbol(payload["symbol"])
    first_part = input_path.stem.split("-")[0]
    if len(first_part) == 6 and first_part.isdigit():
        return validate_symbol(first_part)
    raise ValueError("symbol is required when it cannot be inferred from payload or filename")


def infer_metadata(payload: Any, bars: list[dict[str, Any]], input_path: Path, explicit_symbol: str | None) -> dict[str, str]:
    symbol = infer_symbol(payload, input_path, explicit_symbol)
    start_date = bars[0]["date"]
    end_date = bars[-1]["date"]
    if isinstance(payload, dict):
        if isinstance(payload.get("start_date"), str):
            start_date = validate_yyyymmdd(payload["start_date"], "start_date")
        if isinstance(payload.get("end_date"), str):
            end_date = validate_yyyymmdd(payload["end_date"], "end_date")
    return {"symbol": symbol, "start_date": start_date, "end_date": end_date}


def format_yyyymmdd(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")


def money(value: float) -> str:
    return f"{value:.2f}"


def pct(value: float) -> str:
    return f"{value:.2f}%"


SIGNAL_NOTE_ZH: dict[str, str] = {
    "bottom exhaustion": "底部力度衰竭",
    "top exhaustion": "顶部力度衰竭",
    "pullback did not break first-buy low": "一买后回调未跌破一买低点",
    "rebound did not break first-sell high": "一卖后反弹未突破一卖高点",
    "pullback stayed above ZG": "离开中枢后回抽低点仍在 ZG 上方",
    "rebound stayed below ZD": "跌破中枢后反弹高点仍在 ZD 下方",
}


DIVERGENCE_NOTE_ZH: dict[str, str] = {
    "bottom exhaustion": "底部力度衰竭",
    "top exhaustion": "顶部力度衰竭",
    "bottom divergence": "底部背离观察",
    "top divergence": "顶部背离观察",
    "down stroke made a new low with smaller MACD histogram area": "向下笔价格创新低，但 MACD 柱面积缩小",
    "up stroke made a new high with smaller MACD histogram area": "向上笔价格创新高，但 MACD 柱面积缩小",
    "bottom price made a new low while DIF strengthened": "底分型价格创新低，但 DIF 走强",
    "top price made a new high while DIF weakened": "顶分型价格创新高，但 DIF 走弱",
}


def signal_note_zh(signal: ChanSignal) -> str:
    return SIGNAL_NOTE_ZH.get(signal.note, signal.note)


def divergence_note_zh(divergence: Divergence) -> str:
    return DIVERGENCE_NOTE_ZH.get(divergence.note, divergence.note)


SIGNAL_KIND_EXPLANATION_ZH: dict[str, str] = {
    "first_buy": "一买表示下跌笔末端出现背驰或力度衰竭后的初始买点，后续需要观察反弹能否延续为新的向上结构。",
    "second_buy": "二买表示一买后的回调没有跌破一买低点，属于对一买有效性的回踩确认。",
    "third_buy": "三买表示离开中枢后的回抽没有回到中枢内部，重点观察 ZG 上沿是否继续有效。",
    "first_sell": "一卖表示上涨笔末端出现背驰或力度衰竭后的初始卖点，后续需要观察回落是否扩大。",
    "second_sell": "二卖表示一卖后的反弹没有突破一卖高点，属于对一卖有效性的反抽确认。",
    "third_sell": "三卖表示跌破中枢后的反弹没有回到中枢内部，重点观察 ZD 下沿是否形成反压。",
}


def signal_bias(signal: ChanSignal) -> str:
    return "买点观察" if signal.label.endswith("B") else "卖点观察"


def signal_type_counts(signals: list[ChanSignal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        counts[signal.label] = counts.get(signal.label, 0) + 1
    return counts


def divergence_type_counts(divergences: list[Divergence]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for divergence in divergences:
        counts[divergence.label] = counts.get(divergence.label, 0) + 1
    return counts


def latest_zhongshu_relation(latest_close: float, centers: list[Zhongshu]) -> str:
    if not centers:
        return "当前样本内未形成有效中枢。"
    center = centers[-1]
    if latest_close > center.zg:
        return f"最新收盘价位于最近中枢上沿 ZG {money(center.zg)} 之上，短线处于中枢上方。"
    if latest_close < center.zd:
        return f"最新收盘价位于最近中枢下沿 ZD {money(center.zd)} 之下，短线处于中枢下方。"
    return f"最新收盘价位于最近中枢区间 [{money(center.zd)}, {money(center.zg)}] 内，结构仍在中枢约束范围。"


def trend_summary(model: ReportModel) -> list[str]:
    bars = model.bars
    analysis = model.analysis
    latest = bars[-1]
    first = bars[0]
    high_bar = max(bars, key=lambda bar: bar["high"])
    low_bar = min(bars, key=lambda bar: bar["low"])
    change = (latest["close"] - first["close"]) / first["close"] * 100 if first["close"] else 0.0
    strokes = analysis.strokes
    last_stroke = strokes[-1] if strokes else None
    last_stroke_text = "暂无有效笔"
    if last_stroke is not None:
        direction = "向上" if last_stroke.direction == "up" else "向下"
        last_stroke_text = (
            f"最近一笔为{direction}笔，区间 {format_yyyymmdd(last_stroke.start.date)} "
            f"至 {format_yyyymmdd(last_stroke.end.date)}，端点价 {money(last_stroke.end.price)}。"
        )
    return [
        f"样本区间首收 {money(first['close'])}，最新收盘 {money(latest['close'])}，区间涨跌幅 {pct(change)}。",
        f"区间最高价 {money(high_bar['high'])}（{format_yyyymmdd(high_bar['date'])}），最低价 {money(low_bar['low'])}（{format_yyyymmdd(low_bar['date'])}）。",
        last_stroke_text,
        latest_zhongshu_relation(latest["close"], analysis.zhongshu),
    ]


def structure_summary(model: ReportModel) -> list[str]:
    analysis = model.analysis
    top_count = sum(1 for fractal in analysis.fractals if fractal.kind == "top")
    bottom_count = sum(1 for fractal in analysis.fractals if fractal.kind == "bottom")
    up_strokes = sum(1 for stroke in analysis.strokes if stroke.direction == "up")
    down_strokes = sum(1 for stroke in analysis.strokes if stroke.direction == "down")
    divergence_counts = divergence_type_counts(analysis.divergences)
    signal_counts = signal_type_counts(analysis.signals)
    return [
        f"K 线数量 {len(model.bars)}，包含处理后分析用 K 线数量 {len(analysis.analysis_bars)}。",
        f"分型 {len(analysis.fractals)} 个，其中顶分型 {top_count} 个、底分型 {bottom_count} 个。",
        f"笔 {len(analysis.strokes)} 笔，其中向上笔 {up_strokes} 笔、向下笔 {down_strokes} 笔。",
        f"中枢 {len(analysis.zhongshu)} 个，背离/背驰观察 {len(analysis.divergences)} 个，买卖点 {len(analysis.signals)} 个。",
        "背离/背驰标签统计：" + (", ".join(f"{key}={value}" for key, value in sorted(divergence_counts.items())) or "无"),
        "买卖点标签统计：" + (", ".join(f"{key}={value}" for key, value in sorted(signal_counts.items())) or "无"),
    ]


def conclusion_summary(model: ReportModel) -> list[str]:
    analysis = model.analysis
    bars = model.bars
    latest_close = bars[-1]["close"]
    centers = analysis.zhongshu
    latest_signal = analysis.signals[-1] if analysis.signals else None
    latest_divergence = analysis.divergences[-1] if analysis.divergences else None
    points: list[str] = []
    if centers:
        center = centers[-1]
        if latest_close > center.zg:
            points.append(f"结构位置：最新收盘位于最近中枢上方，回落时优先观察 ZG {money(center.zg)} 是否守住。")
        elif latest_close < center.zd:
            points.append(f"结构位置：最新收盘位于最近中枢下方，反弹时优先观察能否重新收回 ZD {money(center.zd)}。")
        else:
            points.append(f"结构位置：最新收盘仍在最近中枢 [{money(center.zd)}, {money(center.zg)}] 内，短线更偏震荡结构。")
    else:
        points.append("结构位置：样本内没有有效中枢，当前报告不输出中枢突破类结论。")

    if latest_signal is not None:
        points.append(
            f"信号状态：最近买卖点为 {latest_signal.label}（{signal_bias(latest_signal)}），日期 {format_yyyymmdd(latest_signal.date)}，价格 {money(latest_signal.price)}。"
        )
    else:
        points.append("信号状态：样本内未触发 1B/1S/2B/2S/3B/3S 买卖点。")

    if latest_divergence is not None:
        points.append(
            f"力度观察：最近背离/背驰观察为 {latest_divergence.label}，日期 {format_yyyymmdd(latest_divergence.date)}，价格 {money(latest_divergence.price)}，触发说明为{divergence_note_zh(latest_divergence)}。"
        )
    else:
        points.append("力度观察：样本内未出现 DIV 或 BC 类观察标记。")

    points.append("边界说明：本结论仅基于当前日线笔级别结构，不构成投资建议。")
    return points


def signal_interpretation_summary(model: ReportModel) -> list[str]:
    signals = model.analysis.signals
    divergences = model.analysis.divergences
    if not signals:
        return ["样本内没有买卖点，当前只保留分型、笔、中枢和背离/背驰观察。"]

    latest_signal = signals[-1]
    same_index_divergences = [divergence for divergence in divergences if divergence.index == latest_signal.index]
    points = [
        f"最近信号：{latest_signal.label}（{signal_bias(latest_signal)}），{format_yyyymmdd(latest_signal.date)}，价格 {money(latest_signal.price)}，触发说明为{signal_note_zh(latest_signal)}。",
        SIGNAL_KIND_EXPLANATION_ZH[latest_signal.kind],
    ]
    if same_index_divergences:
        labels = "/".join(divergence.label for divergence in same_index_divergences)
        notes = "；".join(divergence_note_zh(divergence) for divergence in same_index_divergences)
        points.append(f"该买卖点与 {labels} 重合，说明同一位置同时出现力度观察：{notes}。")
    else:
        points.append("该买卖点未与同一 K 线上的 DIV/BC 标记重合，后续更依赖价格是否继续确认。")

    recent_signals = signals[-3:]
    if len(recent_signals) > 1:
        sequence = " -> ".join(
            f"{signal.label}@{format_yyyymmdd(signal.date)}({money(signal.price)})" for signal in recent_signals
        )
        points.append(f"最近信号序列：{sequence}。")
    return points


def divergence_interpretation_summary(model: ReportModel) -> list[str]:
    divergences = model.analysis.divergences
    if not divergences:
        return ["样本内没有 DIV 或 BC 标记，当前无法从 MACD 力度角度给出背离/背驰观察。"]

    latest = divergences[-1]
    kind_text = "背驰近似或力度衰竭" if latest.label.startswith("BC") else "普通背离观察"
    points = [
        f"最近观察：{latest.label}，{format_yyyymmdd(latest.date)}，价格 {money(latest.price)}，属于{kind_text}。",
        f"触发说明：{divergence_note_zh(latest)}。",
    ]
    if latest.label.endswith("B"):
        points.append("方向含义：偏向观察下跌力度衰减后的修复可能，但仍需后续向上笔或买点确认。")
    else:
        points.append("方向含义：偏向观察上涨力度衰减后的回落风险，但仍需后续向下笔或卖点确认。")
    return points


def risk_summary(model: ReportModel) -> list[str]:
    high_bar = max(model.bars, key=lambda bar: bar["high"])
    low_bar = min(model.bars, key=lambda bar: bar["low"])
    latest_close = model.bars[-1]["close"]
    points = [
        f"最新收盘：{money(latest_close)}。",
        f"区间高点：{money(high_bar['high'])}（{format_yyyymmdd(high_bar['date'])}）。",
        f"区间低点：{money(low_bar['low'])}（{format_yyyymmdd(low_bar['date'])}）。",
    ]
    if model.analysis.zhongshu:
        center = model.analysis.zhongshu[-1]
        points.extend(
            [
                f"最近中枢上沿 ZG：{money(center.zg)}；若价格从中枢上方跌回 ZG 下方，需要重新评估离开段有效性。",
                f"最近中枢下沿 ZD：{money(center.zd)}；若价格跌破 ZD，下方结构风险会进一步放大。",
                f"最近中枢极值 DD/GG：{money(center.dd)} / {money(center.gg)}，可作为观察区间扩张或失效的参考。",
            ]
        )
    if model.analysis.signals:
        latest_signal = model.analysis.signals[-1]
        points.append(f"最近买卖点价格：{latest_signal.label} @ {money(latest_signal.price)}，后续若被反向突破，应重新评估该信号。")
    points.append("若后续出现新的分型和笔，当前买卖点标签可能被新的结构覆盖或修正。")
    return points


def report_detail_sections(model: ReportModel) -> list[tuple[str, list[str]]]:
    return [
        ("信号解读", signal_interpretation_summary(model)),
        ("背离与背驰解读", divergence_interpretation_summary(model)),
        ("当前结论", conclusion_summary(model)),
        ("风险与观察位", risk_summary(model)),
    ]


def write_pdf(model: ReportModel, output_path: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        write_pdf_with_matplotlib(model, output_path)
        return

    font_name = "Helvetica"
    for font_path in (
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/NISC18030.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ):
        if not font_path.exists():
            continue
        try:
            font_name = "ChanReportFont"
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            break
        except Exception:
            font_name = "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ChanTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=19,
        leading=25,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ChanHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13.5,
        leading=18,
        spaceBefore=10,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "ChanBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=12.8,
        spaceAfter=3,
    )
    small_style = ParagraphStyle(
        "ChanSmall",
        parent=body_style,
        fontSize=7.8,
        leading=10.5,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=15 * mm,
        title=f"{model.display_name} 缠论即时分析报告",
    )

    story: list[Any] = [Paragraph(f"{model.display_name} 缠论即时分析报告", title_style)]
    story.append(Paragraph(f"分析区间：{format_yyyymmdd(model.start_date)} 至 {format_yyyymmdd(model.end_date)}；生成时间：{model.generated_at}", body_style))

    def add_heading(text: str) -> None:
        story.append(Paragraph(text, heading_style))

    def add_bullets(items: list[str]) -> None:
        for item in items:
            story.append(Paragraph(f"- {item}", body_style))

    add_heading("基本信息")
    add_bullets(
        [
            f"股票代码：{model.symbol}",
            f"股票名称：{model.name or '未提供'}",
            f"数据周期：日 K，前复权口径由输入数据决定",
            f"K 线数量：{len(model.bars)}",
        ]
    )

    add_heading("走势概览")
    add_bullets(trend_summary(model))

    add_heading("缠论结构摘要")
    add_bullets(structure_summary(model))

    def add_table(headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
        if not rows:
            story.append(Paragraph("暂无。", body_style))
            return
        table_data = [[Paragraph(cell, small_style) for cell in headers]]
        table_data.extend([[Paragraph(cell, small_style) for cell in row] for row in rows])
        table = Table(table_data, colWidths=[width * mm for width in widths], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#24292f")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d0d7de")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    add_heading("中枢分析")
    zhongshu_rows = [
        [
            str(index),
            f"{format_yyyymmdd(model.analysis.bars[center.start_index].date)} 至 {format_yyyymmdd(model.analysis.bars[center.end_index].date)}",
            money(center.zd),
            money(center.zg),
            money(center.dd),
            money(center.gg),
        ]
        for index, center in enumerate(model.analysis.zhongshu, start=1)
    ]
    add_table(["序号", "区间", "ZD", "ZG", "DD", "GG"], zhongshu_rows, [12, 52, 23, 23, 23, 23])

    add_heading("买卖点分析")
    signal_rows = [[signal.label, format_yyyymmdd(signal.date), money(signal.price), signal_note_zh(signal)] for signal in model.analysis.signals]
    add_table(["标签", "日期", "价格", "触发说明"], signal_rows, [20, 32, 25, 96])

    add_heading("背离与背驰观察")
    story.append(Paragraph("DIV-B / DIV-S 为普通背离观察；BC-B / BC-S 为第一阶段实现中的背驰近似或力度衰竭标记。", body_style))
    divergence_rows = [
        [divergence.label, format_yyyymmdd(divergence.date), money(divergence.price), divergence_note_zh(divergence)]
        for divergence in model.analysis.divergences
    ]
    add_table(["标签", "日期", "价格", "触发说明"], divergence_rows, [20, 32, 25, 96])

    for heading, items in report_detail_sections(model):
        add_heading(heading)
        add_bullets(items)

    if (model.chart_svg_path and model.chart_svg_path.exists()) or (model.chart_png_path and model.chart_png_path.exists()):
        story.append(PageBreak())
        add_heading("K线与缠论结构图")
        chart_added = False
        if model.chart_svg_path and model.chart_svg_path.exists():
            try:
                from svglib.svglib import svg2rlg

                drawing = svg2rlg(str(model.chart_svg_path))
                if drawing is not None:
                    max_width = 180 * mm
                    max_height = 232 * mm
                    ratio = min(max_width / drawing.width, max_height / drawing.height)
                    drawing.width *= ratio
                    drawing.height *= ratio
                    drawing.scale(ratio, ratio)
                    story.append(drawing)
                    chart_added = True
            except Exception:
                chart_added = False
        if not chart_added and model.chart_png_path and model.chart_png_path.exists():
            image = Image(str(model.chart_png_path))
            max_width = 180 * mm
            max_height = 232 * mm
            ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
            image.drawWidth = image.imageWidth * ratio
            image.drawHeight = image.imageHeight * ratio
            story.append(image)
        story.append(Spacer(1, 4))

    doc.build(story)


def write_pdf_with_matplotlib(model: ReportModel, output_path: Path) -> None:
    """Fallback PDF writer used when reportlab is unavailable."""
    import matplotlib.image as mpimg
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.font_manager import FontProperties, findSystemFonts
    import matplotlib.pyplot as plt

    def pick_font() -> FontProperties:
        preferred = ("PingFang", "Hiragino", "Songti", "STHeiti", "NotoSansCJK", "SourceHanSans", "SimHei")
        for font_path in findSystemFonts():
            lower = font_path.lower()
            if any(name.lower() in lower for name in preferred):
                return FontProperties(fname=font_path)
        return FontProperties()

    font = pick_font()
    title_font = font.copy()
    title_font.set_size(17)
    heading_font = font.copy()
    heading_font.set_size(13)
    body_font = font.copy()
    body_font.set_size(9)

    def wrapped_lines(text: str, width: int = 58) -> list[str]:
        lines: list[str] = []
        for part in text.splitlines():
            if not part:
                lines.append("")
                continue
            lines.extend(textwrap.wrap(part, width=width, replace_whitespace=False) or [""])
        return lines

    def add_text_page(pdf: PdfPages, title: str, sections: list[tuple[str, list[str]]]) -> None:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        ax = fig.add_axes((0, 0, 1, 1))
        ax.axis("off")
        y = 0.965
        ax.text(0.06, y, title, fontproperties=title_font, color="#24292f", va="top")
        y -= 0.04
        ax.text(
            0.06,
            y,
            f"分析区间：{format_yyyymmdd(model.start_date)} 至 {format_yyyymmdd(model.end_date)}；生成时间：{model.generated_at}",
            fontproperties=body_font,
            color="#57606a",
            va="top",
        )
        y -= 0.04
        for heading, items in sections:
            if y < 0.08:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                fig.patch.set_facecolor("white")
                ax = fig.add_axes((0, 0, 1, 1))
                ax.axis("off")
                y = 0.955
            ax.text(0.06, y, heading, fontproperties=heading_font, color="#24292f", va="top")
            y -= 0.026
            for item in items:
                for line in wrapped_lines(f"- {item}"):
                    ax.text(0.075, y, line, fontproperties=body_font, color="#24292f", va="top")
                    y -= 0.018
                    if y < 0.06:
                        pdf.savefig(fig, bbox_inches="tight")
                        plt.close(fig)
                        fig = plt.figure(figsize=(8.27, 11.69))
                        fig.patch.set_facecolor("white")
                        ax = fig.add_axes((0, 0, 1, 1))
                        ax.axis("off")
                        y = 0.955
            y -= 0.012
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    def table_lines(headers: list[str], rows: list[list[str]], limit: int = 18) -> list[str]:
        if not rows:
            return ["暂无。"]
        values = [" | ".join(headers)]
        values.extend(" | ".join(row) for row in rows[:limit])
        if len(rows) > limit:
            values.append(f"仅展示前 {limit} 条，共 {len(rows)} 条。")
        return values

    zhongshu_rows = [
        [
            str(index),
            f"{format_yyyymmdd(model.analysis.bars[center.start_index].date)} 至 {format_yyyymmdd(model.analysis.bars[center.end_index].date)}",
            f"ZD {money(center.zd)}",
            f"ZG {money(center.zg)}",
        ]
        for index, center in enumerate(model.analysis.zhongshu, start=1)
    ]
    signal_rows = [[signal.label, format_yyyymmdd(signal.date), money(signal.price), signal_note_zh(signal)] for signal in model.analysis.signals]
    divergence_rows = [
        [divergence.label, format_yyyymmdd(divergence.date), money(divergence.price), divergence_note_zh(divergence)]
        for divergence in model.analysis.divergences
    ]

    with PdfPages(output_path) as pdf:
        add_text_page(
            pdf,
            f"{model.display_name} 缠论即时分析报告",
            [
                (
                    "基本信息",
                    [
                        f"股票代码：{model.symbol}",
                        f"股票名称：{model.name or '未提供'}",
                        f"数据周期：日 K，K 线数量：{len(model.bars)}",
                    ],
                ),
                ("走势概览", trend_summary(model)),
                ("缠论结构摘要", structure_summary(model)),
            ],
        )
        add_text_page(
            pdf,
            "结构明细与结论",
            [
                ("中枢分析", table_lines(["序号", "区间", "ZD", "ZG"], zhongshu_rows)),
                ("买卖点分析", table_lines(["标签", "日期", "价格", "触发说明"], signal_rows)),
                ("背离与背驰观察", table_lines(["标签", "日期", "价格", "触发说明"], divergence_rows)),
                *report_detail_sections(model),
            ],
        )
        if model.chart_png_path and model.chart_png_path.exists():
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.patch.set_facecolor("white")
            ax = fig.add_axes((0.04, 0.06, 0.92, 0.88))
            ax.axis("off")
            ax.set_title("K线与缠论结构图", fontproperties=heading_font, color="#24292f", pad=10)
            ax.imshow(mpimg.imread(model.chart_png_path))
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def create_chart_assets(
    bars: list[dict[str, Any]],
    metadata: dict[str, str],
    temp_dir: Path,
    width: int,
    height: int,
    dpi: int,
) -> ChartAssets:
    temp_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{metadata['symbol']}-{metadata['start_date']}-{metadata['end_date']}"
    svg_path = temp_dir / f"{stem}.svg"
    svg_path.write_text(render_candlestick_svg(bars, metadata, width=width, height=height), encoding="utf-8")

    png_path: Path | None = None
    if has_mplfinance():
        png_path = temp_dir / f"{stem}.png"
        render_candlestick_mplfinance(bars, metadata, png_path, width=width, height=height, dpi=dpi)

    return ChartAssets(svg_path=svg_path, png_path=png_path)


def build_pdf_output_path(output_dir: Path, metadata: dict[str, str], name: str) -> Path:
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")) or "report"
    stem = f"{metadata['symbol']}-{safe_name}-{metadata['start_date']}-{metadata['end_date']}"
    return output_dir / f"{stem}.pdf"


def cleanup_matching_artifacts(metadata: dict[str, str], input_path: Path) -> None:
    symbol = metadata["symbol"]
    start_date = metadata["start_date"]
    end_date = metadata["end_date"]
    resolved_input_path = resolve_input_path(input_path)
    bars_path = Path.cwd() / "output" / "bars" / f"{symbol}-{start_date}-{end_date}.json"
    candidates = [
        bars_path,
        resolved_input_path if resolved_input_path.parent == bars_path.parent else None,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            candidate.unlink()

    charts_dir = Path.cwd() / "output" / "charts"
    if charts_dir.exists():
        for chart_path in charts_dir.glob(f"{symbol}-{start_date}-{end_date}*"):
            if chart_path.suffix.lower() in {".png", ".svg"}:
                chart_path.unlink()


def generate_report(
    input_path: Path,
    *,
    symbol: str | None,
    name: str,
    output_dir: Path,
    width: int,
    height: int,
    dpi: int,
    keep_temp: bool = False,
    cleanup_artifacts: bool = True,
) -> Path:
    payload = load_json(input_path)
    bars = normalize_bars(payload)
    metadata = infer_metadata(payload, bars, input_path, symbol)
    analysis = analyze_chan(bars)
    temp_dir = Path.cwd() / "output" / "tmp" / f"report-{metadata['symbol']}-{uuid4().hex[:8]}"
    output_dir = resolve_output_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        chart_assets = create_chart_assets(bars, metadata, temp_dir, width, height, dpi)
        model = ReportModel(
            symbol=metadata["symbol"],
            name=name,
            start_date=metadata["start_date"],
            end_date=metadata["end_date"],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bars=bars,
            analysis=analysis,
            chart_svg_path=chart_assets.svg_path,
            chart_png_path=chart_assets.png_path,
        )
        pdf_path = build_pdf_output_path(output_dir, metadata, name or metadata["symbol"])
        write_pdf(model, pdf_path)
        if cleanup_artifacts:
            cleanup_matching_artifacts(metadata, input_path)
        return pdf_path
    finally:
        if not keep_temp and temp_dir.exists():
            shutil.rmtree(temp_dir)


def main() -> int:
    args = parse_args()
    pdf_path = generate_report(
        resolve_input_path(Path(args.input)),
        symbol=args.symbol,
        name=args.name,
        output_dir=Path(args.output_dir),
        width=args.width,
        height=args.height,
        dpi=args.dpi,
        keep_temp=args.keep_temp,
        cleanup_artifacts=not args.no_cleanup_artifacts,
    )
    print(format_cwd_relative_path(pdf_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
