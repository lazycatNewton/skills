import json

from scripts.stock_emotion_data import (
    fetch_and_organize_limit_pool,
    format_ladder_matrix_markdown,
    organize_limit_pool,
    should_include_special,
)


def sample_payload():
    return {
        "date": "20260702",
        "source": "eastmoney",
        "counts": {"limit_up": 4, "limit_down": 2},
        "flags": {"st_source": "stock_name_prefix"},
        "limit_up": [
            {
                "rank": 1,
                "symbol": "000001",
                "name": "A股一",
                "industry": "半导体",
                "seal_fund": 100,
                "free_float_market_cap": 1000,
                "consecutive_limit_up_days": 3,
                "is_st": False,
                "is_new_stock": False,
            },
            {
                "rank": 2,
                "symbol": "000002",
                "name": "ST样本",
                "industry": "半导体",
                "consecutive_limit_up_days": 2,
                "is_st": True,
                "is_new_stock": False,
            },
            {
                "rank": 3,
                "symbol": "000003",
                "name": "新股样本",
                "industry": "光学光电",
                "consecutive_limit_up_days": 1,
                "is_st": False,
                "is_new_stock": True,
            },
            {
                "rank": 4,
                "symbol": "000004",
                "name": "A股二",
                "industry": "光学光电",
                "consecutive_limit_up_days": 1,
                "is_st": False,
                "is_new_stock": False,
            },
        ],
        "limit_down": [
            {
                "rank": 1,
                "symbol": "600001",
                "name": "跌停一",
                "industry": "半导体",
                "consecutive_limit_down_days": 1,
                "is_st": False,
                "is_new_stock": False,
            },
            {
                "rank": 2,
                "symbol": "600002",
                "name": "跌停新股",
                "industry": "房地产",
                "consecutive_limit_down_days": 2,
                "is_st": False,
                "is_new_stock": True,
            },
        ],
    }


def test_default_excludes_st_and_new_stocks_from_views():
    organized = organize_limit_pool(sample_payload())

    assert organized.include_special is False
    assert organized.raw_counts == {"limit_up": 4, "limit_down": 2}
    assert organized.filtered_counts == {"limit_up": 2, "limit_down": 1}
    assert organized.excluded_counts["st_or_new_stock"] == 3
    assert [item.symbol for item in organized.limit_up] == ["000001", "000004"]
    assert [level.board_height for level in organized.ladder_view] == [3, 1]

    semiconductor = next(item for item in organized.industry_view if item.industry == "半导体")
    assert semiconductor.limit_up_count == 1
    assert semiconductor.limit_down_count == 1
    assert semiconductor.max_board_height == 3


def test_include_special_keeps_st_and_new_stocks():
    organized = organize_limit_pool(sample_payload(), include_special=True)

    assert organized.filtered_counts == {"limit_up": 4, "limit_down": 2}
    assert organized.excluded_counts["st_or_new_stock"] == 0
    assert [level.board_height for level in organized.ladder_view] == [3, 2, 1]


def test_accepts_mcp_text_content_payload():
    payload = [{"type": "text", "text": json.dumps(sample_payload(), ensure_ascii=False)}]

    organized = organize_limit_pool(payload)

    assert organized.date == "20260702"
    assert organized.source == "eastmoney"


def test_fetch_and_organize_calls_fetcher_with_both_pool():
    calls = []

    def fetcher(date, pool):
        calls.append((date, pool))
        return sample_payload()

    organized = fetch_and_organize_limit_pool("20260702", fetcher)

    assert calls == [("20260702", "both")]
    assert organized.date == "20260702"


def test_should_include_special_requires_explicit_phrase():
    assert should_include_special("请包括ST和新股一起整理")
    assert not should_include_special("分析今天涨跌停")


def test_format_ladder_matrix_markdown_uses_board_rows_and_industry_columns():
    payload = sample_payload()
    payload["limit_up"].extend(
        [
            {
                "rank": 5,
                "symbol": "000005",
                "name": "A股三",
                "industry": "化学制品",
                "consecutive_limit_up_days": 2,
                "is_st": False,
                "is_new_stock": False,
            },
            {
                "rank": 6,
                "symbol": "000006",
                "name": "A股四",
                "industry": "半导体",
                "consecutive_limit_up_days": 2,
                "is_st": False,
                "is_new_stock": False,
            },
        ]
    )
    organized = organize_limit_pool(payload)

    table = format_ladder_matrix_markdown(organized)

    assert table.splitlines()[0] == "| n板 | 半导体 | 化学制品 |"
    assert "| 3板 | `000001 A股一` | - |" in table
    assert "| 2板 | `000006 A股四` | `000005 A股三` |" in table
    assert "1板" not in table
