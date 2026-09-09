from minos_core.special_characteristic_discovery import (
    build_special_characteristic_discovery_report,
    normalize_special_characteristic_locations,
)


def test_normalizes_locations_and_reports_missing_count():
    drawing = {
        "declared_totals": {"CC": 2, "SC": 1},
        "special_characteristic_locations": [
            {
                "classification": "cc",
                "linked_feature": "technical requirement 1",
                "symbol_text_or_shape": "CC",
                "bbox": [0.70, 0.62, 0.03, 0.03],
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.88,
                "reasoning": "Located near the feature callout.",
            }
        ],
    }

    locations = normalize_special_characteristic_locations(
        drawing["special_characteristic_locations"]
    )
    report = build_special_characteristic_discovery_report(
        declared_totals=drawing["declared_totals"],
        locations=locations,
    )

    assert locations[0] == {
        "location_id": "SCL-001",
        "classification": "CC",
        "linked_feature": "technical requirement 1",
        "symbol_text_or_shape": "CC",
        "bbox": [0.7, 0.62, 0.03, 0.03],
        "evidence_refs": ["drawing_page_001"],
        "confidence": 0.88,
        "reasoning": "Located near the feature callout.",
    }
    assert report["found_counts"] == {"CC": 1, "SC": 0}
    assert report["missing_counts"] == {"CC": 1, "SC": 1}
    assert report["extra_counts"] == {"CC": 0, "SC": 0}
    assert report["search_coverage"] == {"CC": 0.5, "SC": 0.0}
    assert [risk["risk_id"] for risk in report["risks"]] == [
        "SC-DISCOVERY-MISSING-CC",
        "SC-DISCOVERY-MISSING-SC",
    ]


def test_no_declared_counts_does_not_raise_missing_risk():
    report = build_special_characteristic_discovery_report(
        declared_totals={"CC": 0, "SC": 0},
        locations=[],
    )

    assert report["missing_counts"] == {"CC": 0, "SC": 0}
    assert report["risks"] == []


def test_normalizer_keeps_only_cc_sc_unknown_classifications():
    locations = normalize_special_characteristic_locations(
        [
            {
                "location_id": "RAW-7",
                "classification": "unknown",
                "linked_feature": "unreadable note",
                "symbol_text_or_shape": "?",
                "symbol_bbox": [1, "bad", -1, 2],
                "evidence_refs": "drawing_page_001",
                "confidence": 2,
                "reasoning_summary": "Symbol cannot be classified as CC or SC.",
            },
            {
                "location_id": "RAW-8",
                "classification": "PTC",
                "linked_feature": "ignored non-target class",
                "bbox": [0.1, 0.2, 0.3, 0.4],
            },
        ]
    )

    assert locations == [
        {
            "location_id": "RAW-7",
            "classification": "unknown",
            "linked_feature": "unreadable note",
            "symbol_text_or_shape": "?",
            "bbox": [],
            "evidence_refs": ["drawing_page_001"],
            "confidence": 1.0,
            "reasoning": "Symbol cannot be classified as CC or SC.",
        },
        {
            "location_id": "RAW-8",
            "classification": "unknown",
            "linked_feature": "ignored non-target class",
            "symbol_text_or_shape": "",
            "bbox": [0.1, 0.2, 0.3, 0.4],
            "evidence_refs": [],
            "confidence": 0.0,
            "reasoning": "",
        },
    ]


def test_extra_locations_are_reported_separately_from_missing():
    locations = normalize_special_characteristic_locations(
        [
            {
                "classification": "CC",
                "bbox": [0.1, 0.2, 0.03, 0.03],
                "evidence_refs": ["drawing_page_001"],
            },
            {
                "classification": "CC",
                "bbox": [0.2, 0.2, 0.03, 0.03],
                "evidence_refs": ["drawing_page_001"],
            },
            {
                "classification": "SC",
                "bbox": [0.3, 0.2, 0.03, 0.03],
                "evidence_refs": ["drawing_page_001"],
            },
        ]
    )

    report = build_special_characteristic_discovery_report(
        declared_totals={"CC": 1, "SC": 0},
        locations=locations,
    )

    assert report["found_counts"] == {"CC": 2, "SC": 1}
    assert report["missing_counts"] == {"CC": 0, "SC": 0}
    assert report["extra_counts"] == {"CC": 1, "SC": 1}
    assert [risk["risk_id"] for risk in report["risks"]] == [
        "SC-DISCOVERY-EXTRA-CC",
        "SC-DISCOVERY-EXTRA-SC",
    ]


def test_placeholder_locations_without_real_bbox_do_not_satisfy_declared_counts():
    locations = normalize_special_characteristic_locations(
        [
            {
                "classification": "CC",
                "linked_feature": "未在图纸视图中明确找到第一个盾牌符号",
                "symbol_text_or_shape": "未在当前视图中发现独立盾牌符号",
                "bbox": [],
                "evidence_refs": ["drawing_page_001"],
            },
            {
                "classification": "SC",
                "linked_feature": "整体装配或功能相关",
                "symbol_text_or_shape": "未在当前视图中发现独立胶囊符号",
                "bbox": [0, 0, 0, 0],
                "evidence_refs": ["drawing_page_001"],
            },
        ]
    )

    report = build_special_characteristic_discovery_report(
        declared_totals={"CC": 2, "SC": 1},
        locations=locations,
    )

    assert report["found_counts"] == {"CC": 0, "SC": 0}
    assert report["missing_counts"] == {"CC": 2, "SC": 1}
    assert [risk["risk_id"] for risk in report["risks"]] == [
        "SC-DISCOVERY-MISSING-CC",
        "SC-DISCOVERY-MISSING-SC",
    ]
