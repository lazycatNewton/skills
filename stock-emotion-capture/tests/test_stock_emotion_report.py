import json

from scripts.stock_emotion_data import organize_limit_pool, organized_limit_pool_to_dict
from scripts.stock_emotion_report import load_organized_limit_pool, render_ladder_section
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
    organized = organize_limit_pool(payload)
    organized_path = tmp_path / "organized.json"
    organized_path.write_text(
        json.dumps(organized_limit_pool_to_dict(organized), ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_organized_limit_pool(organized_path)
    section = render_ladder_section(loaded)

    assert section.startswith("## 3. 连板梯队\n\n| n板 | 半导体 | 化学制品 |")
    assert "| 3板 | `000001 A股一` | - |" in section
    assert "| 2板 | - | `000005 A股三` |" in section
