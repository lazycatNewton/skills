---
name: chan
description: 缠论（缠中说禅）A股技术解析 skill。Use when Codex needs to analyze an A-share stock with Chan theory, fetch or normalize mcp_stock qfq daily bars, keep every raw K-line visible, identify fractals, strokes, Zhongshu, divergences/exhaustion, and buy/sell signals, or generate annotated K-line charts. Do not use for non-A-share markets, pure fundamentals, or high-frequency minute-level analysis.
---

# 缠论个股技术解析

## Overview

这是一个面向 Agent 调用的缠论个股技术解析 skill，用于基于 A 股前复权行情数据生成结构化缠论分析结果。

本 skill 的数据主要来自 `mcp_stock` MCP 工具，默认使用 `qfq` 前复权日线数据。缠论相关逻辑完全自研实现。

**核心目标：**

- 通过 Agent 协议获取并整理 `mcp_stock` 行情数据
- 对每根前复权 K 线执行自研缠论结构识别，不做包含合并
- 输出可解释的分型、笔、中枢、买卖点和趋势结论
- 生成适合用户查看的 K 线标注图和简洁文字结论

## Agent 调用协议

### Step 1：获取前复权日 K 线

使用 mcp_stock MCP 工具获取 qfq 前复权日线数据：

```
mcp_mcp_stock_get_historical_data(
    symbol="603629",
    start_date="20250101",
    end_date="20250618",
    period="daily",
    adjust="qfq"
)
```

日期参数必须使用 `YYYYMMDD` 格式，例如 `20060102`。

### Step 2：保存原始行情 JSON

将 mcp_stock 返回的 bars 数据保存到当前工作目录的相对路径：

```text
output/bars/{symbol}-{start_date}-{end_date}.json
```

例如：

```text
output/bars/603629-20250101-20250618.json
```

可使用当前 skill 提供的保存入口：

```bash
python3 chan/scripts/save_bars.py \
  --symbol 603629 \
  --start-date 20250101 \
  --end-date 20250618 \
  --input /path/to/mcp_stock_payload.json
```

保存后的文件格式如下：

```json
{
  "symbol": "603629",
  "start_date": "20250101",
  "end_date": "20250618",
  "period": "daily",
  "adjust": "qfq",
  "source": "mcp_stock",
  "bars": [
    {"date": "20250102", "open": 19.63, "high": 20.18, "low": 19.00, "close": 19.71, "volume": 14397312},
    ...
  ]
}
```

### Step 3：分析与绘图

使用图表入口读取保存后的 JSON，并输出到 `output/charts/`：

```bash
python3 chan/scripts/plot_bars.py output/bars/603629-20250101-20250618.json
```

如环境缺少 `mplfinance`，或用户需要纯文本 SVG，可指定：

```bash
python3 chan/scripts/plot_bars.py output/bars/603629-20250101-20250618.json --backend svg
```

## 算法说明

所有算法实现在 `scripts/chan_core.py` 中，5 个核心步骤：

### 1. 原始 K 线映射 (`map_kbars`)

当前实现不做包含关系合并。`map_kbars` 会将每根原始日 K 一对一映射为分析用 K 线结构，保证图表、SVG 和后续分型/笔分析都直接基于获取到的完整 K 线序列。

### 2. 分型识别 (`detect_fractals`)

参考缠中说禅第62课。三根 K 线判定：
- 顶分型：中间 K 线高点最高、低点最高
- 底分型：中间 K 线低点最低、高点最低
- 连续同类型取最极端（顶取最高，底取最低）

### 3. 笔检测 (`detect_strokes`)

参考缠中说禅第62课。相邻顶底分型构成一笔，需要至少 4 根独立 K 线间隔（含两端≥5 根）。

### 4. 中枢构建 (`detect_zhongshu`)

参考缠中说禅第63-64课。至少 3 笔的价格重叠区间：
- ZG = min(各笔高点的最大值)
- ZD = max(各笔低点的最小值)
- ZG > ZD 才有效
- 保存 ZG/ZD 来源分型索引，绘图层直接使用来源索引标注中枢上下沿价格

### 5. 买卖点判定 (`detect_signals`)

- 一买/一卖：背驰（同向两笔中后笔价格创新高/低但力度减弱）
- 二买/二卖：一买/一卖后回调不破
- 三买/三卖：突破中枢后回调/反弹不回到中枢内

## 文件结构

```
skills/chan/
├── SKILL.md                        # 本文件
├── scripts/
│   ├── bars_io.py                  # mcp_stock payload 校验、标准化、落盘
│   ├── save_bars.py                # 保存行情 JSON 的 CLI
│   ├── chan_core.py                # 缠论核心算法（无第三方缠论库依赖）
│   └── plot_bars.py                # K 线图渲染与缠论结构叠加
└── references/
    └── notion.md                   # 分型、笔、中枢、背驰、买卖点定义
```

读取 `references/notion.md` 的时机：当用户要求解释缠论概念、核对算法定义，或需要严谨说明分型、笔、中枢、背驰、三类买卖点时再加载。

## 依赖

```bash
pip install pandas numpy matplotlib mplfinance
```

| 包 | 用途 |
| --- | --- |
| pandas | `mplfinance` 后端的数据整理 |
| matplotlib | 图表渲染 |
| mplfinance | K线图表 |

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

1. **K 线数量保持不变**：当前不做包含合并，分析用 K 线数量应等于原始 bars 数量。
2. **笔数量偏少**：当股价窄幅震荡时，分型难以形成，笔数自然偏少。扩大时间范围可改善。
3. **中枢不存在**：笔数 < 3 或笔间无重叠区间时，无有效中枢。
4. **背驰信号少**：需要至少两个同向笔才能判定，半年数据可能只有少数信号。
5. **图表后端不可用**：缺少 `pandas`、`matplotlib` 或 `mplfinance` 时使用 `--backend svg`。
6. **输出文件是产物**：`output/bars/` 与 `output/charts/` 可用于验证，但不应作为核心源码维护。

## Verification Checklist

- [ ] mcp_stock 数据获取成功，K 线数 ≥ 60
- [ ] JSON 文件格式正确，date 字段为 YYYYMMDD 格式
- [ ] 原始 K 线映射正常（analysis_bars 数量等于 bars 数量）
- [ ] 分型识别有产出（≥ 5 个）
- [ ] 笔检测有产出（≥ 3 笔）
- [ ] `plot_bars.py` 已生成 PNG 或 SVG 图表
- [ ] 输出结论区分算法事实、信号解释和投资风险
