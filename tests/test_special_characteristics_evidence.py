from minos_core.special_characteristics_evidence import (
    build_special_characteristic_evidence_packet,
)


def test_build_packet_collects_visual_locator_candidates_ocr_text_and_page_evidence():
    drawing = {
        "drawing_identity": {
            "part_name": "RR DH ASSY",
            "drawing_number": "JLV03000500-001-AC-RR",
            "revision": "A",
        },
        "special_characteristic_candidates": [
            {
                "candidate_id": "MSC-001",
                "candidate_type": "unknown",
                "source": "gpt55_visual_locator",
                "symbol_text_or_shape": "diamond",
                "linked_feature": "mounting hole position",
                "symbol_bbox": [0.31, 0.44, 0.02, 0.02],
                "evidence_refs": ["drawing_page_001"],
                "confidence": 0.93,
            }
        ],
        "technical_requirements": [
            {
                "id": "TR-001",
                "text": "Drawing legend: diamond means CC",
                "evidence_refs": ["drawing_page_001"],
            }
        ],
        "evidence": [
            {"evidence_id": "drawing_page_001", "source": "drawing_page"}
        ],
    }

    packet = build_special_characteristic_evidence_packet(drawing)

    assert packet["packet_id"] == "SC-EVIDENCE-001"
    assert packet["drawing_identity"]["drawing_number"] == "JLV03000500-001-AC-RR"
    assert packet["symbol_occurrences"][0]["candidate_id"] == "MSC-001"
    assert packet["text_evidence"][0]["text"] == "Drawing legend: diamond means CC"
    assert packet["page_evidence_refs"] == ["drawing_page_001"]


def test_build_packet_keeps_vision_candidates_as_evidence_not_confirmation():
    packet = build_special_characteristic_evidence_packet(
        {
            "special_characteristic_candidates": [
                {
                    "candidate_id": "MSC-001",
                    "candidate_type": "CC",
                    "source": "gpt55_visual_locator",
                    "linked_feature": "mounting hole position",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [
                {"evidence_id": "drawing_page_001", "source": "drawing_page"}
            ],
        }
    )

    occurrence = packet["symbol_occurrences"][0]
    assert occurrence["candidate_id"] == "MSC-001"
    assert "confirmation_status" not in occurrence
    assert packet["special_characteristics"] == []


def test_packet_includes_declared_counts_locations_and_missing_counts():
    packet = build_special_characteristic_evidence_packet(
        {
            "declared_special_characteristics": [
                {
                    "declaration_id": "SCD-CC-001",
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["ocr_page_001"],
                }
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "special_characteristic_locations": [
                {
                    "location_id": "SCL-001",
                    "classification": "CC",
                    "linked_feature": "技术要求 1",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "special_characteristic_discovery": {
                "missing_counts": {"CC": 1, "SC": 1},
                "search_coverage": {"CC": 0.5, "SC": 0.0},
            },
            "evidence": [{"evidence_id": "drawing_page_001"}],
        }
    )

    assert packet["declared_counts"][0]["declaration_id"] == "SCD-CC-001"
    assert packet["declared_totals"] == {"CC": 2, "SC": 1}
    assert packet["located_occurrences"][0]["location_id"] == "SCL-001"
    assert packet["missing_counts"] == {"CC": 1, "SC": 1}
    assert packet["search_coverage"] == {"CC": 0.5, "SC": 0.0}


def test_packet_preserves_gpt55_locator_candidate_counts_and_visual_crop_metadata():
    packet = build_special_characteristic_evidence_packet(
        {
            "declared_totals": {"CC": 2, "SC": 1},
            "special_characteristic_candidates": [
                {
                    "candidate_id": "SC-REQ4-TORQUE",
                    "candidate_type": "SC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "水平圆角长框",
                    "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                    "symbol_bbox": [2050, 906, 2255, 929],
                    "evidence_refs": ["drawing_page_001", "crop_sc_req4"],
                    "evidence_regions": [
                        {
                            "region_id": "crop_sc_req4",
                            "evidence_ref": "crop_sc_req4",
                            "bbox": [2050, 906, 2255, 929],
                            "text": "转动力矩(0.5~2.5)Nm",
                            "confidence": 0.96,
                        }
                    ],
                    "confidence": 0.96,
                }
            ],
            "special_characteristic_discovery": {
                "missing_counts": {"CC": 2, "SC": 0},
                "search_coverage": {"CC": 0.0, "SC": 1.0},
            },
            "visual_evidence": [
                {
                    "evidence_id": "crop_sc_req4",
                    "source": "visual_crop",
                    "region_id": "drawing_page_001_technical_requirement_004",
                    "page_evidence_id": "drawing_page_001",
                    "image_path": "visual_evidence/crop_sc_req4.png",
                    "metadata": {
                        "locator_pass": "focused_missing_sc",
                        "source": "gpt55_visual_locator",
                    },
                }
            ],
            "metadata": {
                "visual_locator": {
                    "source": "gpt55_visual_locator",
                    "declared_totals": {"CC": 2, "SC": 1},
                    "passes": ["initial", "focused_missing_sc"],
                }
            },
        }
    )

    occurrence = packet["symbol_occurrences"][0]
    assert occurrence["candidate_id"] == "SC-REQ4-TORQUE"
    assert occurrence["source"] == "gpt55_visual_locator"
    assert occurrence["evidence_regions"][0]["region_id"] == "crop_sc_req4"
    assert packet["declared_totals"] == {"CC": 2, "SC": 1}
    assert packet["missing_counts"] == {"CC": 2, "SC": 0}
    assert packet["search_coverage"] == {"CC": 0.0, "SC": 1.0}
    assert packet["visual_evidence"][0]["evidence_id"] == "crop_sc_req4"
    assert packet["visual_evidence_refs"] == ["crop_sc_req4"]
    assert packet["visual_locator_metadata"]["source"] == "gpt55_visual_locator"
