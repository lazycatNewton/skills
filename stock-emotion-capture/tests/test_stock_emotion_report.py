import json

from scripts.stock_emotion_data import organize_limit_pool, organized_limit_pool_to_dict
from scripts.stock_emotion_report import (
    load_organized_limit_pool,
    render_industry_section,
    render_ladder_section,
    render_limit_up_structure_section,
)
from tests.test_stock_emotion_data import sample_payload


def test_render_ladder_section_from_organized_json(tmp_path):
    payload = sample_payload()
    payload["limit_up"].append(
        {
            "rank": 5,
            "symbol": "000005",
            "name": "A股三",
            "industry": "化学制品",
            "consecutive_limit_up_days": 2,
            "is_st": False,
            "is_new_stock": False,
        }
    )
    payload["limit_down"].append(
        {
            "rank": 3,
            "symbol": "600003",
            "name": "跌停二",
            "industry": "房地产",
            "consecutive_limit_down_days": 2,
            "is_st": False,
            "is_new_stock": False,
        }
    )
    organized = organize_limit_pool(payload)
    organized_path = tmp_path / "organized.json"
    organized_path.write_text(
        json.dumps(organized_limit_pool_to_dict(organized), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_organized_limit_pool(organized_path)
    section = render_ladder_section(loaded)

    assert section.startswith("## 3. 连板梯队\n\n### 涨停连板梯队")
    assert "### 跌停连板梯队" in section
    assert "| n板 | 半导体 | 化学制品 | 光学光电 |" in section
    assert "| 3板 | `000001 A股一` | - | - |" in section
    assert "| 2板 | - | `000005 A股三` | - |" in section
    assert "| 1板 | - | - | `000004 A股二` |" in section
    assert "| n连跌 | 房地产 | 半导体 |" in section
    assert "| 2连跌 | `600003 跌停二` | - |" in section
    assert "| 1连跌 | - | `600001 跌停一` |" in section


def test_render_industry_section_keeps_all_industries_and_stocks(tmp_path):
    organized = organize_limit_pool(sample_payload())
    organized_path = tmp_path / "organized.json"
    organized_path.write_text(
        json.dumps(organized_limit_pool_to_dict(organized), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_organized_limit_pool(organized_path)
    section = render_industry_section(loaded)

    assert section.startswith("## 2. 主线板块复盘")
    assert "`000001 A股一`" in section
    assert "`000004 A股二`" in section
    assert "`600001 跌停一`" in section
    assert "本表覆盖过滤后的全部涨停和跌停数据" in section


def test_render_limit_up_structure_section_uses_table_for_all_limit_up(tmp_path):
    organized = organize_limit_pool(sample_payload())
    organized_path = tmp_path / "organized.json"
    organized_path.write_text(
        json.dumps(organized_limit_pool_to_dict(organized), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_organized_limit_pool(organized_path)
    section = render_limit_up_structure_section(loaded)

    assert section.startswith("## 4. 涨停结构分析")
    assert "| 排名 | 代码 | 名称 | 行业口径 | n板 | 首封 | 末封 | 炸板 | 封单强度 | 结构判断 |" in section
    assert "| 1 | 000001 | A股一 | 半导体 | 3 | - | - | 0 | 10.00% | 换手回封 |" in section
    assert "| 4 | 000004 | A股二 | 光学光电 | 1 | - | - | 0 | - | 换手回封 |" in section
