from minos_core.special_characteristics_visual_locator import (
    FakeGPT55VisualLocator,
    normalize_visual_locator_result,
)


def test_visual_locator_confirms_jlv_two_cc_and_one_sc():
    locator = FakeGPT55VisualLocator(
        {
            "located_occurrences": [
                {
                    "candidate_id": "SC-REQ4-TORQUE",
                    "candidate_type": "SC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "水平圆角长框",
                    "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                    "symbol_bbox": [2050, 906, 2255, 929],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.96,
                    "reasoning": "形状与右下 SC 图例一致。",
                },
                {
                    "candidate_id": "CC-REQ5-GB15086",
                    "candidate_type": "CC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "圆内倒三角",
                    "linked_feature": "技术要求第5条：GB 15086",
                    "symbol_bbox": [1700, 932, 2370, 962],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.90,
                    "reasoning": "第5条前标记与 CC 图例一致。",
                },
                {
                    "candidate_id": "CC-REQ6-M0102",
                    "candidate_type": "CC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "圆内倒三角",
                    "linked_feature": "技术要求第6条：Q/BJORV M 0102",
                    "symbol_bbox": [1700, 962, 2370, 994],
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.82,
                    "reasoning": "第6条前标记与 CC 图例一致。",
                },
            ],
            "missing_counts": {"CC": 0, "SC": 0},
            "focused_review_requests": [],
        }
    )

    result = normalize_visual_locator_result(locator.locate({}))

    assert [item["candidate_id"] for item in result["located_occurrences"]] == [
        "SC-REQ4-TORQUE",
        "CC-REQ5-GB15086",
        "CC-REQ6-M0102",
    ]
    assert [item["candidate_type"] for item in result["located_occurrences"]] == ["SC", "CC", "CC"]
    assert result["located_occurrences"][0]["linked_feature"] == "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm"
    assert result["missing_counts"] == {"CC": 0, "SC": 0}
    assert result["focused_review_requests"] == []
