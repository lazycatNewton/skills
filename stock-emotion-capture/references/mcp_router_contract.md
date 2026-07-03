# MCP Router 数据契约

读取 `mcp_router` 响应并进行 A 股情绪复盘时，使用本参考文档。

## 主工具

默认运行环境是已安装所需 MCP 服务的 Agent。数据获取由 Agent 调用 `mcp_router.get_limit_pool` 完成；Python 数据整理脚本不直接连接 MCP 服务，只接收 MCP 返回的原始 payload。

为避免大 payload 在对话显示层被截断，Agent 获取 MCP 返回后应优先通过桥接脚本保存，不要先完整打印到对话中：

```bash
python3 scripts/bridge_limit_pool_payload.py --date 20260702 --input -
```

桥接脚本从 stdin 或 `--input` 文件读取 MCP 原始 JSON，默认写入：

- raw payload: `output/raw/stock-emotion-capture/{YYYYMMDD}-limit-pool.json`
- organized data: `output/data/stock-emotion-capture/{YYYYMMDD}-organized.json`

调用参数：

```json
{
  "date": "YYYYMMDD",
  "pool": "both"
}
```

预期顶层结构：

```json
{
  "date": "20260630",
  "source": "eastmoney",
  "counts": {
    "limit_up": 140,
    "limit_down": 5
  },
  "flags": {},
  "limit_up": [],
  "limit_down": []
}
```

## 顶层字段

- `date`: 数据源返回的交易日期。
- `source`: 数据源标识，当前观察到的值为 `eastmoney`。
- `counts.limit_up`: 当日涨停总数。
- `counts.limit_down`: 当日跌停总数。
- `flags.st_source`: ST 识别来源。
- `flags.new_stock_source`: 次新股识别来源。
- `flags.new_stock_count`: 数据源侧次新股池数量。
- `limit_up`: 涨停股票列表。
- `limit_down`: 跌停股票列表。

## `limit_up` 单条字段

- `rank`: 数据源侧排序。
- `symbol`, `name`: 股票代码和名称。
- `change_pct`: 涨跌幅百分比。
- `latest_price`: 最新价，或数据源给出的类收盘价格。
- `turnover`: 成交额。
- `free_float_market_cap`: 流通市值。
- `total_market_cap`: 总市值。
- `turnover_rate`: 换手率。
- `seal_fund`: 封单资金。
- `first_limit_time`: 首次涨停时间，格式为 `HHMMSS`。
- `last_limit_time`: 最后封板时间，格式为 `HHMMSS`。
- `break_limit_count`: 炸板次数。
- `limit_up_stat`: 数据源侧涨停统计字符串。除非已验证具体口径，否则只作为辅助字段。
- `consecutive_limit_up_days`: 连续涨停天数，用于判断连板高度。
- `industry`: 数据源侧行业字段，用作第一层板块字段。
- `is_st`: 是否 ST。
- `is_new_stock`: 是否次新股。
- `listing_date`: 上市日期，存在时返回。

## `limit_down` 单条字段

- `rank`, `symbol`, `name`, `change_pct`, `latest_price`, `turnover`, `free_float_market_cap`, `total_market_cap`, `turnover_rate`, `seal_fund`, `industry`, `is_st`, `is_new_stock`, `listing_date`: 与涨停字段含义基本一致。
- `pe_dynamic`: 动态市盈率。
- `last_limit_time`: 最后跌停时间。
- `limit_board_turnover`: 跌停板成交额。
- `consecutive_limit_down_days`: 连续跌停天数。
- `open_limit_count`: 跌停板打开次数。

## 派生指标

使用派生指标时，必须明确标注为派生计算：

- `seal_strength = seal_fund / free_float_market_cap`
- `board_break_risk = break_limit_count`
- `sector_limit_up_count = count(limit_up grouped by industry)`
- `sector_lianban_count = count(limit_up where consecutive_limit_up_days >= 2 grouped by industry)`
- `max_board_height = max(consecutive_limit_up_days)`
- `lianban_count = count(limit_up where consecutive_limit_up_days >= 2)`

## 注意事项

- `industry` 不一定等同于完整市场题材或概念，不要把它直接说成确定的题材主线。
- `first_limit_time = "092500"` 只表示数据源记录的最早时间。除非有开盘/竞价数据确认，不要直接称为一字板。
- 收盘前的市场数据可能延迟或不完整。必要时说明数据日期和时间口径。
