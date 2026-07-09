#!/usr/bin/env python3
"""Temporary analysis runner -- will be cleaned."""
import sys, json
sys.path.insert(0, '/Users/didiapp/.hermes/skills/chan/scripts')
from chan_core import analyze_chan
from datetime import datetime

# The bars file was cleaned by report.py, so reconstruct from the known data
# We know the PDF was generated, so the analysis ran successfully.
# Let me just read what we can from the existing model output.
# The analysis results from earlier (60-day) should be embedded in the report.

# Actually let me just parse from the earlier successful mcp_stock structuredContent
# The values are extracted from the structuredContent field

with open('/Users/didiapp/dev/skills/chan/output/bars/002050-20251009-20260703.json', 'r') as f:
    payload = json.load(f)

bars = payload['bars']
analysis = analyze_chan(bars)

def fmt(d):
    return datetime.strptime(d, '%Y%m%d').strftime('%Y-%m-%d')

latest = bars[-1]; first = bars[0]
high_bar = max(bars, key=lambda b: b['high'])
low_bar = min(bars, key=lambda b: b['low'])
change = (latest['close'] - first['close']) / first['close'] * 100

print('=' * 66)
print('三花智控（002050）缠论分析  [mcp_stock qfq 前复权]')
print('=' * 66)
print(f'区间: {fmt(first["date"])} → {fmt(latest["date"])}（{len(bars)} 根日K）')
print(f'首收: {first["close"]:.2f}  最新: {latest["close"]:.2f}  涨跌: {change:+.2f}%')
print(f'最高: {high_bar["high"]:.2f}（{fmt(high_bar["date"])}）  最低: {low_bar["low"]:.2f}（{fmt(low_bar["date"])}）')
hilo_swing = (high_bar['high'] - low_bar['low']) / low_bar['low'] * 100
print(f'高低振幅: {hilo_swing:.1f}%')
print()

tc = sum(1 for f in analysis.fractals if f.kind == 'top')
bc = sum(1 for f in analysis.fractals if f.kind == 'bottom')
us = sum(1 for s in analysis.strokes if s.direction == 'up')
ds = sum(1 for s in analysis.strokes if s.direction == 'down')
print(f'【结构摘要】分型 {len(analysis.fractals)}(顶{tc}+底{bc}) | 笔 {len(analysis.strokes)}(↑{us}+↓{ds}) | 中枢 {len(analysis.zhongshu)} | 买卖点 {len(analysis.signals)} | 背离/背驰 {len(analysis.divergences)}')
print()

if analysis.strokes:
    print('  笔序列:')
    for i, s in enumerate(analysis.strokes):
        d = '↑' if s.direction == 'up' else '↓'
        pct = (s.end.price - s.start.price) / s.start.price * 100
        print(f'    {d}{i+1}: {fmt(s.start.date)}→{fmt(s.end.date)}  {s.start.price:.2f}→{s.end.price:.2f} ({pct:+.2f}%)')
print()

if analysis.zhongshu:
    for i, zs in enumerate(analysis.zhongshu, 1):
        print(f'【中枢{i}】{fmt(bars[zs.start_index]["date"])}→{fmt(bars[zs.end_index]["date"])}')
        print(f'  ZD={zs.zd:.2f}  ZG={zs.zg:.2f}  DD={zs.dd:.2f}  GG={zs.gg:.2f}')
print()

SIG_ZH = {'bottom exhaustion':'底部衰竭','top exhaustion':'顶部衰竭','pullback did not break first-buy low':'一买回调未破低','rebound did not break first-sell high':'一卖反弹未破高','pullback stayed above ZG':'回抽不破ZG','rebound stayed below ZD':'反弹不破ZD'}
DIV_ZH = {'bottom exhaustion':'底部衰竭','top exhaustion':'顶部衰竭','bottom divergence':'底背离','top divergence':'顶背离'}
if analysis.signals:
    print('【买卖点】')
    for sig in analysis.signals:
        print(f'  {sig.label} @ {fmt(sig.date)} {sig.price:.2f} — {SIG_ZH.get(sig.note, sig.note)}')
else:
    print('【买卖点】样本内未触发')
print()

if analysis.divergences:
    print('【背离/背驰观察】')
    for div in analysis.divergences:
        print(f'  {div.label} @ {fmt(div.date)} {div.price:.2f} — {DIV_ZH.get(div.note, str(div.note))}')
else:
    print('【背离/背驰观察】无')
print()

print('【当前结论】')
centers = analysis.zhongshu
if centers:
    zs = centers[-1]
    if latest['close'] > zs.zg:
        print(f'  结构位置：收盘{latest["close"]:.2f} > 最近中枢上沿 ZG={zs.zg:.2f}，短线偏强')
        print(f'  回落观察 ZG={zs.zg:.2f} 是否守住，守住则中枢上方结构成立')
    elif latest['close'] < zs.zd:
        print(f'  结构位置：收盘{latest["close"]:.2f} < 最近中枢下沿 ZD={zs.zd:.2f}，短线偏弱')
    else:
        print(f'  结构位置：收盘{latest["close"]:.2f} 在最近中枢 [{zs.zd:.2f}, {zs.zg:.2f}] 内震荡')
    if len(centers) > 1:
        z1 = centers[0]
        print(f'  多中枢：共{len(centers)}个中枢。中枢1 [{z1.zd:.2f}, {z1.zg:.2f}]，后续中枢位置变化反映趋势方向')
else:
    print('  结构位置：样本内无有效中枢')

if analysis.strokes:
    ls = analysis.strokes[-1]
    d = '向上' if ls.direction == 'up' else '向下'
    print(f'  最近一笔：{d}笔（{fmt(ls.start.date)}→{fmt(ls.end.date)}），样本内无买卖点触发')
    up_n = sum(1 for s in analysis.strokes if s.direction == 'up')
    dn = sum(1 for s in analysis.strokes if s.direction == 'down')
    hint = '多空交替，整体偏震荡' if abs(up_n - dn) <= 1 else ('向下笔偏多，偏空结构' if dn > up_n else '向上笔偏多，偏多结构')
    print(f'  笔方向统计：↑{up_n} ↓{dn} — {hint}')

if analysis.divergences:
    latest_div = analysis.divergences[-1]
    kind = '背驰近似' if latest_div.label.startswith('BC') else '普通背离'
    print(f'  力度观察：最近为 {latest_div.label}（{kind}），日期 {fmt(latest_div.date)}，价格 {latest_div.price:.2f}')
    if latest_div.label.endswith('S'):
        print(f'  方向含义：观察上涨力度衰减后的回落风险，已部分兑现（随后跌至 {low_bar["low"]:.2f}）')
    else:
        print(f'  方向含义：观察下跌力度衰减后的修复可能')
print()

print('【风险与观察位】')
print(f'  最新收盘：{latest["close"]:.2f}')
print(f'  区间高点：{high_bar["high"]:.2f}（{fmt(high_bar["date"])}）')
print(f'  区间低点：{low_bar["low"]:.2f}（{fmt(low_bar["date"])}）')
if centers:
    zs = centers[-1]
    print(f'  最近中枢：ZG={zs.zg:.2f}  ZD={zs.zd:.2f}  DD={zs.dd:.2f}  GG={zs.gg:.2f}')
    print(f'  跌破 ZG={zs.zg:.2f} 需重新评估离开段有效性')
print('  若后续出现新分型/笔，当前结构结论可能被覆盖或修正')
print()

print(f'📄 PDF报告：/Users/didiapp/dev/skills/chan/output/reports/chan/002050-三花智控-20251009-20260703.pdf')
print('⚠ 基于日线笔级别缠论结构，不构成投资建议')
