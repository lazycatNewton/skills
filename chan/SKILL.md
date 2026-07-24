---
name: chan
description: 缠论（缠中说禅）A股技术解析 skill。Use when Codex needs to analyze an A-share stock with Chan theory, obtain or normalize Tushare-backed mcp_router qfq daily bars, keep every raw K-line visible, identify fractals, strokes, Zhongshu, divergences/exhaustion, and buy/sell signals, or generate final PDF analysis reports. Do not use for non-A-share markets, pure fundamentals, or high-frequency minute-level analysis.
---

# 缠论个股技术解析

## Overview

这是一个面向 Agent 调用的缠论个股技术解析 skill，用于基于 A 股前复权行情数据生成结构化缠论分析结果和即时 PDF 报告。

本 skill 的行情数据唯一来源是以 Tushare 为上游的 `mcp_router` MCP 工具，默认使用 `qfq` 前复权日线数据。缠论相关逻辑完全自研实现。

**核心目标：**

- 通过 Agent 协议获取并整理 `mcp_router` 行情数据
- 对前复权 K 线执行包含处理后，再识别分型、笔、中枢和买卖点
- 输出可解释的分型、笔、中枢、买卖点和趋势结论
- 生成最终 PDF 分析报告；报告完成后清理本次 bars/charts 中间产物

## Agent 调用协议

### Step 1：获取前复权日 K 线

仅使用 Tushare 驱动的 `mcp_router` MCP 工具获取 qfq 前复权日线数据：

```
mcp_mcp_router_get_historical_data(
    symbol="603629",
    start_date="20250101",
    end_date="20250618",
    period="daily",
    adjust="qfq"
)
```

日期参数必须使用 `YYYYMMDD` 格式，例如 `20060102`。

不得使用其他行情源作为替代或回退。若 `mcp_router` 无法从 Tushare 返回完整、可靠的 qfq 日线数据，应停止分析并说明数据前置条件未满足，不得基于估算、非 qfq 或不完整数据生成结论或 PDF。

### Step 2：生成最终分析报告

将 `mcp_router` 返回的 Tushare payload 临时保存为任意本地 JSON 文件，然后调用报告入口：

```bash
python3 scripts/report.py \
  --input /path/to/mcp_router_tushare_payload.json \
  --symbol 603629 \
  --name 利通电子
```

正式产物只保留在：

```text
output/reports/chan/{symbol}-{name}-{start_date}-{end_date}.pdf
```

所有未显式指定为绝对路径的输出和临时文件，都以调用脚本时的当前工作目录为基准生成。

`report.py` 会完成数据归一化、缠论分析、临时图表生成、PDF 组装，并在报告生成后清理本次匹配的 `output/bars/` 与 `output/charts/` 产物。报告主图优先使用 SVG；PNG 仅作为当前 PDF 后端需要时的临时兼容图。不要把 `output/bars/` 或 `output/charts/` 作为最终交付。

### Step 3：调试入口（非最终输出）

如需单独检查数据归一化，可使用：

```bash
python3 scripts/save_bars.py \
  --symbol 603629 \
  --start-date 20250101 \
  --end-date 20250618 \
  --input /path/to/mcp_router_tushare_payload.json
```

保存后的调试文件格式如下：

```json
{
  "symbol": "603629",
  "start_date": "20250101",
  "end_date": "20250618",
  "period": "daily",
  "adjust": "qfq",
  "source": "mcp_router_tushare",
  "bars": [
    {"date": "20250102", "open": 19.63, "high": 20.18, "low": 19.00, "close": 19.71, "volume": 14397312},
    ...
  ]
}
```

如需单独检查图表，可使用：

```bash
python3 scripts/plot_bars.py output/bars/603629-20250101-20250618.json
```

这些调试产物不应作为最终输出；正式分析应以 `report.py` 生成的 PDF 为准。

## 报告章节

`report.py` 输出的 PDF 应尽量详细，并从同一份结构化分析结果生成。报告至少包含：

- 基本信息：股票代码、名称、数据周期、分析区间、K 线数量、生成时间。
- 走势概览：最新收盘、区间涨跌幅、区间高低点、最近一笔方向、价格相对最近中枢的位置。
- 缠论结构摘要：分型、笔、中枢、背离/背驰观察、买卖点数量与标签统计。
- 中枢分析：列出每个中枢的日期区间、ZD、ZG、DD、GG。
- 买卖点分析：列出 `1B/1S/2B/2S/3B/3S` 的日期、价格、中文触发说明。
- 背离与背驰观察：区分普通 `DIV-B/DIV-S` 与近似 `BC-B/BC-S`，并输出中文触发说明。
- 信号解读：解释最近买卖点的方向含义、触发依据、是否与 DIV/BC 标记重合，以及最近信号序列。
- 背离与背驰解读：解释最近 DIV/BC 标记的力度含义和后续确认条件。
- 当前结论：按结构位置、信号状态、力度观察、边界说明分层给出即时判断。
- 风险与观察位：列出最新收盘、区间高低点、最近中枢 ZG/ZD/DD/GG、最近买卖点价格和结构重绘风险。
- K 线与缠论结构图：作为 PDF 最后一个章节单独占用一页，优先内嵌 SVG，展示 K 线、成交量、MACD、分型、笔、中枢、DIV/BC、买卖点标记。

## 算法说明

所有算法实现在 `scripts/chan_core.py` 中，5 个核心步骤：

### 1. 包含处理 (`map_kbars`)

`map_kbars` 会把原始日 K 转换为经过包含关系处理的分析用 K 线。原始 K 线仍完整保留，用于图表底图、成交量和 MACD；分型、笔、中枢和买卖点基于包含处理后的 `analysis_bars` 计算。

方向确定规则：
- 优先使用最近两根非包含分析 K 线的高低点关系判断上升或下降。
- 没有明确非包含方向时，沿用上一轮已确认方向。
- 序列开头方向仍不明确时，以收盘价变化和高低点中值作为兜底。

合并规则：
- 上升方向：高点取两根最高，低点取两根较高低点。
- 下降方向：高点取两根较低高点，低点取两根最低。
- 合并后记录真实高点和真实低点所在的原始 K 线索引，图表分型、笔和中枢边界使用这些原始索引标注。

### 2. 分型识别 (`detect_fractals`)

参考缠中说禅第62课。三根 K 线判定：
- 顶分型：中间 K 线高点最高、低点最高
- 底分型：中间 K 线低点最低、高点最低
- 连续同类型取最极端（顶取最高，底取最低）

### 3. 笔检测 (`detect_strokes`)

参考缠中说禅第62课。一个顶分型与一个底分型之间可构成一笔，至少 3 个基本 K 线单位。

### 4. 中枢构建 (`detect_zhongshu`)

参考缠中说禅第63-64课。至少 3 笔的价格重叠区间：
- ZG = min(各笔高点的最大值)
- ZD = max(各笔低点的最小值)
- ZG > ZD 才有效
- 保存 ZG/ZD 来源分型索引，绘图层直接使用来源索引标注中枢上下沿价格

### 5. 买卖点判定 (`detect_signals`)

当前实现为日线笔级别的简化判定，输出 `1B/1S/2B/2S/3B/3S`：

- 一买/一卖：趋势背驰点。只有 `bottom_exhaustion` / `top_exhaustion` 且位于一笔结束点时，才标记为 `1B` / `1S`；普通 `DIV-B` / `DIV-S` 只作为背离提示。
- 二买/二卖：一买/一卖后，首次回调/反弹不破一买低点或一卖高点。
- 三买/三卖：离开中枢后回抽/反弹不回到中枢内，三买要求低点 > ZG，三卖要求高点 < ZD。

注意：完整缠论中的一买/一卖依赖趋势背驰结构，严格定义参见 `references/notion.md`；当前代码未实现多级别递归确认。

## 文件结构

```
skills/chan/
├── SKILL.md                        # 本文件
├── scripts/
│   ├── bars_io.py                  # mcp_router/Tushare payload 校验、标准化、落盘
│   ├── save_bars.py                # 保存行情 JSON 的 CLI
│   ├── chan_core.py                # 缠论核心算法（无第三方缠论库依赖）
│   ├── plot_bars.py                # K 线图渲染与缠论结构叠加
│   └── report.py                   # PDF 最终报告生成入口
└── references/
    └── notion.md                   # 分型、笔、中枢、背驰、买卖点定义
```

读取 `references/notion.md` 的时机：当用户要求解释缠论概念、核对算法定义，或需要严谨说明分型、笔、中枢、背驰、三类买卖点时再加载。

## 依赖

```bash
pip install pandas numpy matplotlib mplfinance reportlab
```

| 包 | 用途 |
| --- | --- |
| pandas | `mplfinance` 后端的数据整理 |
| matplotlib | 图表渲染 |
| mplfinance | K线图表 |
| reportlab | PDF 报告生成 |

无需 czsc 或任何第三方缠论库。

## 实测 Benchmarks

利通电子（603629）2025-01-01 ~ 2025-06-18 日线（109 根 K 线）：

| 指标 | 结果 |
|------|------|
| 原始 K 线映射后 | 109 根分析用 K 线 |
| 分型 | 23 个（顶11 + 底12） |
| 笔 | 7 笔（↑3 + ↓4） |
| 中枢 | 2 个（上移） |
| 信号 | 三卖 @ 23.34（20250609） |
| 图表大小 | 160KB / 2954×1838px |

## Common Pitfalls

1. **K 线数量会变化**：包含处理后，分析用 K 线数量应小于或等于原始 bars 数量；图表底图仍显示完整原始 K 线。
2. **笔数量偏少**：当股价窄幅震荡时，分型难以形成，笔数自然偏少。扩大时间范围可改善。
3. **中枢不存在**：笔数 < 3 或笔间无重叠区间时，无有效中枢。
4. **背离/背驰信号少**：背离需要同类分型价格与 MACD DIF 不确认；背驰还需要更严格的趋势结构，半年数据可能只有少数信号。
5. **图表后端不可用**：SVG 主图由内置渲染器生成；缺少 `pandas`、`matplotlib` 或 `mplfinance` 时，PDF 可能缺少 PNG fallback 图。
6. **PDF 依赖缺失**：缺少 `reportlab` 时使用 matplotlib PDF fallback；如需更精细排版，安装 `reportlab` 与 `svglib`。
7. **最终输出唯一性**：`output/reports/chan/` 下的 PDF 是正式产物，`output/bars/` 与 `output/charts/` 仅用于调试或临时验证。

## Verification Checklist

- [ ] mcp_router 已通过 Tushare 成功获取 qfq 日线数据，K 线数 ≥ 60
- [ ] 未使用其他行情数据源
- [ ] JSON 文件格式正确，date 字段为 YYYYMMDD 格式
- [ ] 包含处理正常（analysis_bars 数量小于或等于 bars 数量，分型落点对应原始 K 线真实高低点）
- [ ] 分型识别有产出（≥ 5 个）
- [ ] 笔检测有产出（≥ 3 笔）
- [ ] `python3 -m pytest tests` 通过（当前环境需先安装 pytest）
- [ ] `report.py` 已生成 PDF 报告
- [ ] 报告生成后，本次匹配的 `output/bars/` 与 `output/charts/` 中间产物已清理
- [ ] 输出结论区分算法事实、信号解释和投资风险
