import json

from scripts.bridge_limit_pool_payload import bridge_payload
from tests.test_stock_emotion_data import sample_payload


def test_bridge_payload_saves_raw_and_organized_json(tmp_path):
    raw_path = tmp_path / "raw.json"
    organized_path = tmp_path / "organized.json"

    summary = bridge_payload(
        json.dumps(sample_payload(), ensure_ascii=False),
        date="20260702",
        raw_output=raw_path,
        organized_output=organized_path,
    )

    assert summary["date"] == "20260702"
    assert summary["raw_counts"] == {"limit_up": 4, "limit_down": 2}
    assert summary["filtered_counts"] == {"limit_up": 2, "limit_down": 1}
    assert summary["excluded_counts"]["st_or_new_stock"] == 3
    assert summary["ladder_levels"] == [3, 1]
    assert raw_path.exists()
    assert organized_path.exists()

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    organized = json.loads(organized_path.read_text(encoding="utf-8"))
    assert raw["date"] == "20260702"
    assert organized["date"] == "20260702"
    assert organized["industry_view"][0]["limit_up_count"] >= 1


def test_bridge_payload_can_include_special_from_user_text(tmp_path):
    summary = bridge_payload(
        json.dumps(sample_payload(), ensure_ascii=False),
        user_text="复盘20260702，包括ST和新股",
        raw_output=tmp_path / "raw.json",
        organized_output=tmp_path / "organized.json",
    )

    assert summary["include_special"] is True
    assert summary["filtered_counts"] == {"limit_up": 4, "limit_down": 2}
