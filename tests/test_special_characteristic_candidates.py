from minos_core.special_characteristic_candidates import (
    confirmed_special_characteristics_from_candidates,
    normalize_special_characteristic_candidates,
    risks_from_special_characteristic_candidates,
)


def test_visual_symbol_candidate_is_normalized_with_evidence_regions():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_type": "sc",
                "source": "visual_symbol",
                "symbol_text_or_shape": "triangle",
                "linked_feature": "孔径 10.0 +0.05/0 mm",
                "symbol_bbox": [0.1, 0.2, 0.05, 0.04],
                "linked_feature_bbox": [0.2, 0.2, 0.2, 0.05],
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.91,
                "needs_confirmation": False,
            }
        ]
    )

    assert candidates[0]["candidate_id"] == "MSC-001"
    assert candidates[0]["candidate_type"] == "SC"
    assert candidates[0]["confirmation_status"] == "needs_human_review"
    assert candidates[0]["needs_confirmation"] is True
    assert candidates[0]["evidence_regions"][0]["evidence_ref"] == "drawing_page_001"
    assert confirmed_special_characteristics_from_candidates(candidates) == []


def test_legend_candidate_does_not_rule_confirm_without_judge():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_type": "CC",
                "source": "legend",
                "symbol_text_or_shape": "diamond",
                "linked_feature": "安装孔位置度 0.2 A B",
                "symbol_bbox": [0.1, 0.2, 0.05, 0.04],
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.96,
            }
        ]
    )

    assert candidates[0]["confirmation_status"] == "needs_human_review"
    assert confirmed_special_characteristics_from_candidates(candidates) == []


def test_ocr_text_candidate_can_still_rule_confirm_explicit_sc_text():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_type": "SC",
                "source": "ocr_text",
                "symbol_text_or_shape": "SC",
                "linked_feature": "孔径 10.0 +0.05/0 mm",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.91,
            }
        ]
    )

    assert candidates[0]["confirmation_status"] == "rule_confirmed"
    assert candidates[0]["needs_confirmation"] is False
    assert confirmed_special_characteristics_from_candidates(candidates)[0]["classification"] == "SC"


def test_judge_confirmed_candidate_becomes_special_characteristic_boundary():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_id": "CC-001",
                "candidate_type": "CC",
                "source": "judge_verdict",
                "symbol_text_or_shape": "CC",
                "linked_feature": "安装孔位置度 0.2 A B",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.77,
                "confirmation_status": "judge_confirmed",
                "needs_confirmation": False,
            }
        ]
    )

    confirmed = confirmed_special_characteristics_from_candidates(candidates)

    assert candidates[0]["confirmation_status"] == "judge_confirmed"
    assert candidates[0]["needs_confirmation"] is False
    assert confirmed[0]["id"] == "CC-001"
    assert confirmed[0]["classification"] == "CC"


def test_numeric_only_candidate_is_not_confirmed():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_type": "SC",
                "source": "knowledge",
                "linked_feature": "红锈出现时间不低于120h",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.96,
            }
        ]
    )

    assert candidates[0]["confirmation_status"] == "needs_human_review"
    assert candidates[0]["needs_confirmation"] is True
    assert confirmed_special_characteristics_from_candidates(candidates) == []


def test_unconfirmed_candidate_projects_review_risk():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_type": "unknown",
                "source": "visual_symbol",
                "symbol_text_or_shape": "customer_star",
                "linked_feature": "位置度 0.2 A B",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.72,
            }
        ]
    )

    risks = risks_from_special_characteristic_candidates(candidates)

    assert risks[0]["risk_id"] == "SC-CANDIDATE-MSC-001"
    assert risks[0]["severity"] == "review"
    assert risks[0]["target"] == "special_characteristic_candidates.MSC-001"


def test_unknown_candidate_type_can_be_inferred_from_visual_locator_reasoning():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_id": "symbol_candidate_1",
                "candidate_type": "unknown",
                "source": "gpt55_visual_locator",
                "symbol_text_or_shape": "三角形符号",
                "linked_feature": "螺栓（零件1）",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.70,
                "reasoning": "图纸关键件表格中显示三角形符号，可能表示安全特性（SC）或类似。",
            },
            {
                "candidate_id": "symbol_candidate_2",
                "candidate_type": "unknown",
                "source": "gpt55_visual_locator",
                "symbol_text_or_shape": "菱形符号",
                "linked_feature": "销子（零件2）",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.70,
                "reasoning": "图纸关键件表格中显示菱形符号，可能表示关键特性（CC）或类似。",
            },
        ]
    )

    assert [item["candidate_type"] for item in candidates] == ["SC", "CC"]
    assert all(item["confirmation_status"] == "needs_human_review" for item in candidates)


def test_gpt55_visual_locator_jlv_candidates_keep_req4_sc_and_req5_req6_cc_pending_judge():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_id": "SC-REQ4-TORQUE",
                "candidate_type": "SC",
                "source": "gpt55_visual_locator",
                "symbol_text_or_shape": "水平圆角长框",
                "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                "symbol_bbox": [0.62, 0.52, 0.08, 0.03],
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
                "symbol_bbox": [0.58, 0.56, 0.08, 0.03],
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
                "symbol_bbox": [0.58, 0.59, 0.08, 0.03],
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.82,
                "reasoning": "第6条前标记与 CC 图例一致。",
            },
        ]
    )

    assert {item["candidate_id"]: item["candidate_type"] for item in candidates} == {
        "SC-REQ4-TORQUE": "SC",
        "CC-REQ5-GB15086": "CC",
        "CC-REQ6-M0102": "CC",
    }
    assert all(item["source"] == "gpt55_visual_locator" for item in candidates)
    assert all(item["confirmation_status"] == "needs_human_review" for item in candidates)
    assert confirmed_special_characteristics_from_candidates(candidates) == []


def test_ptc_candidate_type_is_downgraded_to_unknown():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_id": "symbol_candidate_3",
                "candidate_type": "PTC",
                "source": "visual_symbol",
                "symbol_text_or_shape": "菱形符号",
                "linked_feature": "图例定义项",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.77,
                "reasoning": "模型误判为 PTC 或产品关键特性。",
            }
        ]
    )

    assert candidates[0]["candidate_type"] == "unknown"
    assert candidates[0]["confirmation_status"] == "needs_human_review"


def test_unsupported_candidate_type_cannot_be_confirmed():
    candidates = normalize_special_characteristic_candidates(
        [
            {
                "candidate_id": "symbol_candidate_4",
                "candidate_type": "PTC",
                "source": "visual_symbol",
                "symbol_text_or_shape": "菱形符号",
                "linked_feature": "图例定义项",
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.92,
                "confirmation_status": "human_confirmed",
            }
        ]
    )

    assert confirmed_special_characteristics_from_candidates(candidates) == []
