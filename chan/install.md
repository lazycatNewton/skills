# Chan Skill Installation

本文说明如何在主流 Agent 环境中载入 `chan` skill。安装时必须保留整个 `chan/` 目录，不能只复制 `SKILL.md`，因为运行依赖 `scripts/` 和 `references/`。

## 目录内容

```text
chan/
├── SKILL.md
├── scripts/
│   ├── bars_io.py
│   ├── chan_core.py
│   ├── plot_bars.py
│   ├── report.py
│   └── save_bars.py
└── references/
    └── notion.md
```

## 运行依赖

目标环境需要 Python 3，并建议安装：

```bash
pip install pandas numpy matplotlib mplfinance reportlab svglib pytest
```

生成 PDF 报告时，最终产物默认保存到：

```text
output/reports/chan/{symbol}-{name}-{start}-{end}.pdf
```

行情数据默认由 `mcp_stock` 提供，要求能获取 A 股前复权日 K 数据。

## Codex

Codex 原生支持 skills。将整个 `chan/` 目录复制到 Codex skills 目录：

```bash
mkdir -p ~/.codex/skills
cp -R chan ~/.codex/skills/chan
```

也可以从 Git 仓库安装：

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo <owner>/<repo> \
  --path chan
```

安装后重启 Codex 或开启新会话。触发示例：

```text
用 chan skill 获取 603379 近 180 个交易日数据并生成缠论分析报告。
```

## Claude

Claude 不一定原生识别 Codex 的 `SKILL.md` 格式。推荐把 `chan/` 作为项目资源放入仓库，并在项目级说明文件中要求 Claude 读取：

```text
当用户要求进行 A 股缠论分析时，先读取 chan/SKILL.md；
需要严谨定义时读取 chan/references/notion.md；
调用 chan/scripts/report.py 生成最终 PDF。
```

如果 Claude 环境支持 MCP，请同时配置 `mcp_stock`，否则需要先由外部流程保存行情 JSON，再让 Claude 调用：

```bash
python chan/scripts/report.py --input /path/to/payload.json --symbol 603379 --name 三美股份
```

## Hermes

Hermes 或其他自定义 Agent 通常采用“工具目录 + 指令文件”的方式接入。建议将 `chan/` 挂载为 Agent 可读写的资源目录，并在 Hermes 的 system prompt、tool registry 或 agent profile 中加入：

```text
For Chinese A-share Chan analysis, load chan/SKILL.md first.
Use chan/scripts/report.py as the final report generator.
The only final artifact is output/reports/chan/{symbol}-{name}-{start}-{end}.pdf.
```

若 Hermes 支持自定义工具，注册 `python chan/scripts/report.py` 为报告生成工具，并传入 `--input`、`--symbol`、`--name` 参数。

## 其他 Agent

对不支持 skill 机制的 Agent，按以下通用流程接入：

1. 将整个 `chan/` 目录复制到 Agent 工作区。
2. 在 Agent 的长期指令中写明“缠论分析任务必须先读取 `chan/SKILL.md`”。
3. 配置行情来源，优先接入 `mcp_stock`。
4. 让 Agent 保存行情 payload 为 JSON。
5. 调用 `chan/scripts/report.py` 生成 PDF。

## 验证

安装后建议执行：

```bash
python -X pycache_prefix=/tmp/chan-pycache -m py_compile \
  chan/scripts/bars_io.py \
  chan/scripts/save_bars.py \
  chan/scripts/chan_core.py \
  chan/scripts/plot_bars.py \
  chan/scripts/report.py

python -m pytest tests
```

如果没有测试目录，至少使用一份真实行情 JSON 验证：

```bash
python chan/scripts/report.py \
  --input /path/to/payload.json \
  --symbol 603379 \
  --name 三美股份 \
  --no-cleanup-artifacts
```

确认输出 PDF 位于 `output/reports/chan/`，并且报告包含 K 线、成交量、MACD、分型、笔、中枢、DIV/BC 和买卖点标记。
