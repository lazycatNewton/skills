#!/usr/bin/env python3
"""Core Chan-theory structures used by chart rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


FractalKind = Literal["top", "bottom"]
StrokeDirection = Literal["up", "down"]
SignalKind = Literal[
    "first_buy",
    "first_sell",
    "second_buy",
    "second_sell",
    "third_buy",
    "third_sell",
]
DivergenceKind = Literal["top_divergence", "bottom_divergence", "top_exhaustion", "bottom_exhaustion"]


@dataclass(frozen=True)
class KBar:
    index: int
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AnalysisKBar:
    index: int
    start_index: int
    end_index: int
    high_index: int
    low_index: int
    high_date: str
    low_date: str
    date: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Fractal:
    kind: FractalKind
    analysis_index: int
    index: int
    date: str
    price: float
    high: float
    low: float

    @property
    def merged_index(self) -> int:
        """Backward-compatible alias for callers created before raw K-line mapping was renamed."""
        return self.analysis_index


@dataclass(frozen=True)
class Stroke:
    start: Fractal
    end: Fractal
    direction: StrokeDirection
    start_index: int
    end_index: int
    high: float
    low: float


@dataclass(frozen=True)
class Zhongshu:
    start_stroke_index: int
    end_stroke_index: int
    start_index: int
    end_index: int
    zd: float
    zg: float
    gg: float
    dd: float
    zd_source_index: int
    zg_source_index: int


@dataclass(frozen=True)
class MacdPoint:
    index: int
    date: str
    dif: float
    dea: float
    hist: float


@dataclass(frozen=True)
class ChanSignal:
    kind: SignalKind
    index: int
    date: str
    price: float
    label: str
    note: str


@dataclass(frozen=True)
class Divergence:
    kind: DivergenceKind
    index: int
    date: str
    price: float
    label: str
    note: str


@dataclass(frozen=True)
class ChanAnalysis:
    bars: list[KBar]
    analysis_bars: list[AnalysisKBar]
    fractals: list[Fractal]
    strokes: list[Stroke]
    zhongshu: list[Zhongshu]
    macd: list[MacdPoint]
    signals: list[ChanSignal]
    divergences: list[Divergence]

    @property
    def merged_bars(self) -> list[AnalysisKBar]:
        """Backward-compatible alias for callers created before raw K-line mapping was renamed."""
        return self.analysis_bars


def build_kbars(raw_bars: list[dict[str, Any]]) -> list[KBar]:
    return [
        KBar(
            index=index,
            date=str(bar["date"]),
            open=float(bar["open"]),
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
            volume=float(bar["volume"]),
        )
        for index, bar in enumerate(raw_bars)
    ]


def analysis_bar_from_kbar(bar: KBar, index: int) -> AnalysisKBar:
    return AnalysisKBar(
        index=index,
        start_index=bar.index,
        end_index=bar.index,
        high_index=bar.index,
        low_index=bar.index,
        high_date=bar.date,
        low_date=bar.date,
        date=bar.date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
    )


def kbar_direction(left: AnalysisKBar, right: AnalysisKBar) -> StrokeDirection | None:
    if right.high > left.high and right.low > left.low:
        return "up"
    if right.high < left.high and right.low < left.low:
        return "down"
    return None


def has_inclusion(left: AnalysisKBar, right: AnalysisKBar) -> bool:
    left_contains_right = left.high >= right.high and left.low <= right.low
    right_contains_left = right.high >= left.high and right.low <= left.low
    return left_contains_right or right_contains_left


def initial_merge_direction(left: AnalysisKBar, right: AnalysisKBar) -> StrokeDirection:
    if right.close != left.close:
        return "up" if right.close > left.close else "down"
    left_mid = (left.high + left.low) / 2
    right_mid = (right.high + right.low) / 2
    return "up" if right_mid >= left_mid else "down"


def merge_direction(
    analysis_bars: list[AnalysisKBar],
    incoming: AnalysisKBar,
    last_direction: StrokeDirection | None,
) -> StrokeDirection:
    if len(analysis_bars) >= 2:
        direction = kbar_direction(analysis_bars[-2], analysis_bars[-1])
        if direction is not None:
            return direction
    if last_direction is not None:
        return last_direction
    return initial_merge_direction(analysis_bars[-1], incoming)


def high_source(left: AnalysisKBar, right: AnalysisKBar, high: float) -> tuple[int, str]:
    if left.high == high:
        return left.high_index, left.high_date
    return right.high_index, right.high_date


def low_source(left: AnalysisKBar, right: AnalysisKBar, low: float) -> tuple[int, str]:
    if left.low == low:
        return left.low_index, left.low_date
    return right.low_index, right.low_date


def merge_inclusion_kbars(left: AnalysisKBar, right: AnalysisKBar, direction: StrokeDirection) -> AnalysisKBar:
    if direction == "up":
        high = max(left.high, right.high)
        low = max(left.low, right.low)
    else:
        high = min(left.high, right.high)
        low = min(left.low, right.low)

    high_index, high_date = high_source(left, right, high)
    low_index, low_date = low_source(left, right, low)
    return AnalysisKBar(
        index=left.index,
        start_index=left.start_index,
        end_index=right.end_index,
        high_index=high_index,
        low_index=low_index,
        high_date=high_date,
        low_date=low_date,
        date=right.date,
        open=left.open,
        high=high,
        low=low,
        close=right.close,
    )


def reindex_analysis_bars(analysis_bars: list[AnalysisKBar]) -> list[AnalysisKBar]:
    return [
        AnalysisKBar(
            index=index,
            start_index=bar.start_index,
            end_index=bar.end_index,
            high_index=bar.high_index,
            low_index=bar.low_index,
            high_date=bar.high_date,
            low_date=bar.low_date,
            date=bar.date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )
        for index, bar in enumerate(analysis_bars)
    ]


def map_kbars(bars: list[KBar]) -> list[AnalysisKBar]:
    """Build analysis K-lines after Chan inclusion processing."""
    analysis_bars: list[AnalysisKBar] = []
    last_direction: StrokeDirection | None = None

    for bar in bars:
        current = analysis_bar_from_kbar(bar, len(analysis_bars))
        if not analysis_bars:
            analysis_bars.append(current)
            continue

        previous = analysis_bars[-1]
        if has_inclusion(previous, current):
            direction = merge_direction(analysis_bars, current, last_direction)
            analysis_bars[-1] = merge_inclusion_kbars(previous, current, direction)
            last_direction = direction
            continue

        direction = kbar_direction(previous, current)
        if direction is not None:
            last_direction = direction
        analysis_bars.append(current)

    return reindex_analysis_bars(analysis_bars)


def detect_fractals(analysis_bars: list[AnalysisKBar]) -> list[Fractal]:
    candidates: list[Fractal] = []
    for index in range(1, len(analysis_bars) - 1):
        left = analysis_bars[index - 1]
        middle = analysis_bars[index]
        right = analysis_bars[index + 1]

        is_top = middle.high >= max(left.high, right.high) and middle.low >= max(left.low, right.low)
        is_bottom = middle.low <= min(left.low, right.low) and middle.high <= min(left.high, right.high)

        if is_top:
            candidates.append(
                Fractal(
                    kind="top",
                    analysis_index=index,
                    index=middle.high_index,
                    date=middle.high_date,
                    price=middle.high,
                    high=middle.high,
                    low=middle.low,
                )
            )
        elif is_bottom:
            candidates.append(
                Fractal(
                    kind="bottom",
                    analysis_index=index,
                    index=middle.low_index,
                    date=middle.low_date,
                    price=middle.low,
                    high=middle.high,
                    low=middle.low,
                )
            )

    filtered: list[Fractal] = []
    for fractal in candidates:
        if not filtered or filtered[-1].kind != fractal.kind:
            filtered.append(fractal)
            continue

        last = filtered[-1]
        if fractal.kind == "top" and fractal.price > last.price:
            filtered[-1] = fractal
        elif fractal.kind == "bottom" and fractal.price < last.price:
            filtered[-1] = fractal

    return filtered


def detect_strokes(fractals: list[Fractal], min_basic_bars: int = 3) -> list[Stroke]:
    strokes: list[Stroke] = []
    if not fractals:
        return strokes

    def stronger_same_kind(candidate: Fractal, reference: Fractal) -> bool:
        if candidate.kind == "top":
            return candidate.price > reference.price
        return candidate.price < reference.price

    def build_stroke(start: Fractal, end: Fractal) -> Stroke:
        direction: StrokeDirection = "up" if start.kind == "bottom" and end.kind == "top" else "down"
        return Stroke(
            start=start,
            end=end,
            direction=direction,
            start_index=start.index,
            end_index=end.index,
            high=max(start.price, end.price),
            low=min(start.price, end.price),
        )

    start = fractals[0]
    for end in fractals[1:]:
        if end.kind == start.kind:
            if stronger_same_kind(end, start):
                if strokes:
                    strokes[-1] = build_stroke(strokes[-1].start, end)
                start = end
            continue

        if end.analysis_index - start.analysis_index + 1 < min_basic_bars:
            continue

        strokes.append(build_stroke(start, end))
        start = end

    return strokes


def stroke_high_fractal(stroke: Stroke) -> Fractal:
    return stroke.start if stroke.start.price >= stroke.end.price else stroke.end


def stroke_low_fractal(stroke: Stroke) -> Fractal:
    return stroke.start if stroke.start.price <= stroke.end.price else stroke.end


def detect_zhongshu(strokes: list[Stroke]) -> list[Zhongshu]:
    centers: list[Zhongshu] = []
    index = 0
    while index + 2 < len(strokes):
        group = strokes[index : index + 3]
        zg = min(stroke.high for stroke in group)
        zd = max(stroke.low for stroke in group)
        if zg <= zd:
            index += 1
            continue

        end_stroke_index = index + 2
        gg = max(stroke.high for stroke in group)
        dd = min(stroke.low for stroke in group)
        current_zg = zg
        current_zd = zd

        probe = end_stroke_index + 1
        while probe < len(strokes):
            next_zg = min(current_zg, strokes[probe].high)
            next_zd = max(current_zd, strokes[probe].low)
            if next_zg <= next_zd:
                break
            current_zg = next_zg
            current_zd = next_zd
            gg = max(gg, strokes[probe].high)
            dd = min(dd, strokes[probe].low)
            end_stroke_index = probe
            probe += 1

        included_strokes = strokes[index : end_stroke_index + 1]
        zg_source = min((stroke_high_fractal(stroke) for stroke in included_strokes), key=lambda fractal: fractal.price)
        zd_source = max((stroke_low_fractal(stroke) for stroke in included_strokes), key=lambda fractal: fractal.price)

        centers.append(
            Zhongshu(
                start_stroke_index=index,
                end_stroke_index=end_stroke_index,
                start_index=strokes[index].start_index,
                end_index=strokes[end_stroke_index].end_index,
                zd=current_zd,
                zg=current_zg,
                gg=gg,
                dd=dd,
                zd_source_index=zd_source.index,
                zg_source_index=zg_source.index,
            )
        )
        index = end_stroke_index + 1

    return centers


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def calculate_macd(bars: list[KBar], fast: int = 12, slow: int = 26, signal: int = 9) -> list[MacdPoint]:
    closes = [bar.close for bar in bars]
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif_values = [fast_value - slow_value for fast_value, slow_value in zip(ema_fast, ema_slow)]
    dea_values = ema(dif_values, signal)
    return [
        MacdPoint(
            index=bar.index,
            date=bar.date,
            dif=dif,
            dea=dea,
            hist=2 * (dif - dea),
        )
        for bar, dif, dea in zip(bars, dif_values, dea_values)
    ]


def macd_area(macd: list[MacdPoint], start_index: int, end_index: int, direction: StrokeDirection) -> float:
    segment = macd[min(start_index, end_index) : max(start_index, end_index) + 1]
    if direction == "up":
        return sum(max(point.hist, 0.0) for point in segment)
    return abs(sum(min(point.hist, 0.0) for point in segment))


def detect_divergences(
    fractals: list[Fractal],
    strokes: list[Stroke],
    centers: list[Zhongshu],
    macd: list[MacdPoint],
) -> list[Divergence]:
    divergences: list[Divergence] = []
    last_top: Fractal | None = None
    last_bottom: Fractal | None = None
    center_count = len(centers)

    for fractal in fractals:
        point = macd[fractal.index]
        if fractal.kind == "top":
            if last_top is not None:
                previous = macd[last_top.index]
                if fractal.price > last_top.price and point.dif < previous.dif:
                    kind: DivergenceKind = "top_exhaustion" if center_count >= 2 else "top_divergence"
                    label = "BC-S" if kind == "top_exhaustion" else "DIV-S"
                    note = "top price made a new high while DIF weakened"
                    divergences.append(Divergence(kind, fractal.index, fractal.date, fractal.price, label, note))
            last_top = fractal
        else:
            if last_bottom is not None:
                previous = macd[last_bottom.index]
                if fractal.price < last_bottom.price and point.dif > previous.dif:
                    kind = "bottom_exhaustion" if center_count >= 2 else "bottom_divergence"
                    label = "BC-B" if kind == "bottom_exhaustion" else "DIV-B"
                    note = "bottom price made a new low while DIF strengthened"
                    divergences.append(Divergence(kind, fractal.index, fractal.date, fractal.price, label, note))
            last_bottom = fractal

    # A stricter exhaustion comparison: same-direction stroke area weakens after two centers exist.
    if center_count >= 2:
        same_direction: dict[StrokeDirection, Stroke] = {}
        for stroke in strokes:
            previous = same_direction.get(stroke.direction)
            if previous is not None:
                previous_area = macd_area(macd, previous.start_index, previous.end_index, previous.direction)
                current_area = macd_area(macd, stroke.start_index, stroke.end_index, stroke.direction)
                if current_area < previous_area:
                    if stroke.direction == "up" and stroke.end.price > previous.end.price:
                        divergences.append(
                            Divergence(
                                "top_exhaustion",
                                stroke.end_index,
                                stroke.end.date,
                                stroke.end.price,
                                "BC-S",
                                "up stroke made a new high with smaller MACD histogram area",
                            )
                        )
                    elif stroke.direction == "down" and stroke.end.price < previous.end.price:
                        divergences.append(
                            Divergence(
                                "bottom_exhaustion",
                                stroke.end_index,
                                stroke.end.date,
                                stroke.end.price,
                                "BC-B",
                                "down stroke made a new low with smaller MACD histogram area",
                            )
                        )
            same_direction[stroke.direction] = stroke

    deduped: dict[tuple[str, int], Divergence] = {}
    for divergence in divergences:
        deduped[(divergence.kind, divergence.index)] = divergence
    return sorted(deduped.values(), key=lambda divergence: (divergence.index, divergence.kind))


def detect_signals(
    strokes: list[Stroke],
    centers: list[Zhongshu],
    divergences: list[Divergence],
) -> list[ChanSignal]:
    """Detect simplified stroke-level buy/sell points.

    Ordinary DIV-B/DIV-S divergences are observation signals only. First buy/sell
    points are emitted only from exhaustion markers at stroke endpoints.
    """
    signals: list[ChanSignal] = []
    divergence_by_index = {divergence.index: divergence for divergence in divergences}

    for stroke in strokes:
        divergence = divergence_by_index.get(stroke.end_index)
        if divergence is None:
            continue
        if divergence.kind == "bottom_exhaustion":
            signals.append(
                ChanSignal("first_buy", stroke.end_index, stroke.end.date, stroke.end.price, "1B", "bottom exhaustion")
            )
        elif divergence.kind == "top_exhaustion":
            signals.append(
                ChanSignal("first_sell", stroke.end_index, stroke.end.date, stroke.end.price, "1S", "top exhaustion")
            )

    for first in list(signals):
        if first.kind == "first_buy":
            for stroke in strokes:
                if stroke.start_index <= first.index or stroke.direction != "down":
                    continue
                if stroke.low > first.price:
                    signals.append(
                        ChanSignal("second_buy", stroke.end_index, stroke.end.date, stroke.end.price, "2B", "pullback did not break first-buy low")
                    )
                    break
        elif first.kind == "first_sell":
            for stroke in strokes:
                if stroke.start_index <= first.index or stroke.direction != "up":
                    continue
                if stroke.high < first.price:
                    signals.append(
                        ChanSignal("second_sell", stroke.end_index, stroke.end.date, stroke.end.price, "2S", "rebound did not break first-sell high")
                    )
                    break

    for center in centers:
        after = strokes[center.end_stroke_index + 1 :]
        for offset in range(len(after) - 1):
            leave = after[offset]
            pullback = after[offset + 1]
            if leave.direction == "up" and leave.high > center.zg and pullback.direction == "down" and pullback.low > center.zg:
                signals.append(
                    ChanSignal("third_buy", pullback.end_index, pullback.end.date, pullback.end.price, "3B", "pullback stayed above ZG")
                )
                break
            if leave.direction == "down" and leave.low < center.zd and pullback.direction == "up" and pullback.high < center.zd:
                signals.append(
                    ChanSignal("third_sell", pullback.end_index, pullback.end.date, pullback.end.price, "3S", "rebound stayed below ZD")
                )
                break

    deduped: dict[tuple[str, int], ChanSignal] = {}
    for signal in signals:
        deduped[(signal.kind, signal.index)] = signal
    return sorted(deduped.values(), key=lambda signal: (signal.index, signal.kind))


def analyze_chan(raw_bars: list[dict[str, Any]]) -> ChanAnalysis:
    bars = build_kbars(raw_bars)
    analysis_bars = map_kbars(bars)
    fractals = detect_fractals(analysis_bars)
    strokes = detect_strokes(fractals)
    centers = detect_zhongshu(strokes)
    macd = calculate_macd(bars)
    divergences = detect_divergences(fractals, strokes, centers, macd)
    signals = detect_signals(strokes, centers, divergences)
    return ChanAnalysis(
        bars=bars,
        analysis_bars=analysis_bars,
        fractals=fractals,
        strokes=strokes,
        zhongshu=centers,
        macd=macd,
        signals=signals,
        divergences=divergences,
    )
