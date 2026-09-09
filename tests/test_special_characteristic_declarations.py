from minos_core.special_characteristic_declarations import (
    attach_declared_special_characteristics,
    extract_declared_special_characteristics,
)


def test_extracts_declared_cc_sc_counts_from_title_block_text():
    bundle = {
        "evidence": [
            {
                "evidence_id": "ocr_page_001_block_0001",
                "source": "ocr_block",
                "content": "关键特性 CC (Critical Characteristic) 2",
                "confidence": 0.91,
            },
            {
                "evidence_id": "ocr_page_001_block_0002",
                "source": "ocr_block",
                "content": "重要特性 SC (Special Characteristic) 1",
                "confidence": 0.89,
            },
        ],
        "technical_requirements": [],
        "inspection_requirements": [],
    }

    result = extract_declared_special_characteristics(bundle)

    assert result["declared_totals"] == {"CC": 2, "SC": 1}
    assert result["declared_counts"][0]["classification"] == "CC"
    assert result["declared_counts"][0]["expected_count"] == 2
    assert result["declared_counts"][0]["evidence_refs"] == [
        "ocr_page_001_block_0001"
    ]
    assert result["declared_counts"][1]["classification"] == "SC"
    assert result["declared_counts"][1]["expected_count"] == 1


def test_attach_declared_counts_is_idempotent_and_keeps_zero_absent():
    bundle = {
        "evidence": [
            {
                "evidence_id": "ocr_page_001",
                "content": "材料 SPCC; 技术要求: 去毛刺",
                "confidence": 0.9,
            }
        ]
    }

    attach_declared_special_characteristics(bundle)
    attach_declared_special_characteristics(bundle)

    assert bundle["declared_special_characteristics"] == []
    assert bundle["declared_totals"] == {"CC": 0, "SC": 0}


def test_extracts_declared_counts_from_structured_text_sources():
    bundle = {
        "evidence": [],
        "text_evidence": [
            {
                "text": "标题栏: 关键特性 CC 数量 2",
                "evidence_refs": ["text_ref_001"],
                "confidence": 0.88,
            }
        ],
        "technical_requirements": [
            {
                "description": "技术要求: 重要特性 SC 共 1 项",
                "evidence_refs": ["tech_ref_001"],
                "confidence": 0.86,
            }
        ],
        "inspection_requirements": [
            {
                "name": "检验区: 关键特性 CC 1",
                "evidence_refs": ["inspection_ref_001"],
                "confidence": 0.84,
            }
        ],
    }

    result = extract_declared_special_characteristics(bundle)

    assert result["declared_totals"] == {"CC": 2, "SC": 1}
    sources = {item["source"] for item in result["declared_counts"]}
    assert sources == {
        "text_evidence",
        "technical_requirements",
        "inspection_requirements",
    }
    refs_by_source = {
        item["source"]: item["evidence_refs"]
        for item in result["declared_counts"]
    }
    assert refs_by_source["text_evidence"] == ["text_ref_001"]
    assert refs_by_source["technical_requirements"] == ["tech_ref_001"]
    assert refs_by_source["inspection_requirements"] == ["inspection_ref_001"]


def test_ignores_ptc_as_formal_declared_classification():
    bundle = {
        "evidence": [
            {
                "evidence_id": "ocr_page_001_block_0001",
                "source": "ocr_block",
                "content": "产品关键特性 PTC 3",
                "confidence": 0.9,
            }
        ]
    }

    result = extract_declared_special_characteristics(bundle)

    assert result["declared_counts"] == []
    assert result["declared_totals"] == {"CC": 0, "SC": 0}


def test_material_spcc_and_isolated_sc_letters_are_not_declarations():
    bundle = {
        "evidence": [
            {
                "evidence_id": "ocr_page_001_block_0001",
                "source": "ocr_block",
                "content": "材料: SPCC t=1.2; 表面处理: SC-900 涂层",
                "confidence": 0.92,
            },
            {
                "evidence_id": "ocr_page_001_block_0002",
                "source": "ocr_block",
                "content": "控制计划栏位: SC 1; CC 2; 但无声明标题",
                "confidence": 0.9,
            },
        ],
        "technical_requirements": [
            {
                "text": "需检查 SC 标记区域，未声明重要特性数量",
                "evidence_refs": ["tech_ref_002"],
            }
        ],
    }

    result = extract_declared_special_characteristics(bundle)

    assert result["declared_counts"] == []
    assert result["declared_totals"] == {"CC": 0, "SC": 0}
