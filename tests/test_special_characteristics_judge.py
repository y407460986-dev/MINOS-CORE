from minos_core.special_characteristics_judge import (
    FakeSpecialCharacteristicJudge,
    SpecialCharacteristicJudge,
    normalize_special_characteristic_judgments,
    verify_special_characteristic_judgments,
)


def _packet():
    return {
        "symbol_occurrences": [
            {"candidate_id": "MSC-001", "evidence_refs": ["drawing_page_001"]}
        ],
        "legend_evidence": [
            {"legend_id": "LEG-001", "evidence_refs": ["drawing_page_001"]}
        ],
        "text_evidence": [
            {"text_id": "TXT-001", "evidence_refs": ["drawing_page_001"]}
        ],
        "customer_rules": [
            {"rule_id": "RULE-001", "evidence_refs": ["drawing_page_001"]}
        ],
        "page_evidence_refs": ["drawing_page_001"],
    }


def test_confirmed_judge_verdict_passes_verifier():
    judge = FakeSpecialCharacteristicJudge(
        {
            "special_characteristic_judgments": [
                {
                    "judgment_id": "SCJ-001",
                    "candidate_id": "MSC-001",
                    "classification": "CC",
                    "verdict": "confirmed",
                    "linked_feature": "mounting hole position",
                    "confidence": 0.91,
                    "standard_evidence_refs": ["LEG-001", "TXT-001"],
                    "symbol_evidence_refs": ["MSC-001"],
                    "page_evidence_refs": ["drawing_page_001"],
                    "reasoning_summary": "Legend maps the diamond to CC.",
                }
            ]
        }
    )

    judgments = normalize_special_characteristic_judgments(judge.judge(_packet()))
    report = verify_special_characteristic_judgments(judgments, _packet())

    assert report["confirmed"][0]["classification"] == "CC"
    assert report["confirmed"][0]["confirmation_status"] == "judge_confirmed"
    assert report["confirmed"][0]["needs_confirmation"] is False
    assert report["risks"] == []


def test_hallucinated_evidence_is_forced_to_human_review():
    judgments = normalize_special_characteristic_judgments(
        {
            "special_characteristic_judgments": [
                {
                    "judgment_id": "SCJ-001",
                    "candidate_id": "MSC-999",
                    "classification": "SC",
                    "verdict": "confirmed",
                    "linked_feature": "missing dimension",
                    "confidence": 0.95,
                    "standard_evidence_refs": ["LEG-MISSING"],
                    "symbol_evidence_refs": ["MSC-999"],
                    "page_evidence_refs": ["drawing_page_missing"],
                    "reasoning_summary": "References evidence outside the packet.",
                }
            ]
        }
    )

    report = verify_special_characteristic_judgments(judgments, _packet())

    assert report["confirmed"] == []
    assert report["risks"][0]["category"] == "special_characteristic_judge"
    assert "MSC-999" in report["risks"][0]["missing_evidence_refs"]
    assert "LEG-MISSING" in report["risks"][0]["missing_evidence_refs"]
    assert "drawing_page_missing" in report["risks"][0]["missing_evidence_refs"]


def test_missing_symbol_evidence_ref_is_forced_to_human_review():
    judgments = normalize_special_characteristic_judgments(
        {
            "special_characteristic_judgments": [
                {
                    "judgment_id": "SCJ-001",
                    "candidate_id": "MSC-001",
                    "classification": "SC",
                    "verdict": "confirmed",
                    "linked_feature": "安装孔位置度",
                    "confidence": 0.92,
                    "standard_evidence_refs": ["TXT-001"],
                    "symbol_evidence_refs": ["MSC-MISSING"],
                    "page_evidence_refs": ["drawing_page_001"],
                    "reasoning_summary": "引用了不存在的符号证据。",
                }
            ]
        }
    )

    report = verify_special_characteristic_judgments(judgments, _packet())

    assert report["confirmed"] == []
    assert "MSC-MISSING" in report["risks"][0]["missing_evidence_refs"]


def test_gpt_judge_uses_evidence_packet_and_requires_citations():
    class FakeGenerator:
        def __init__(self):
            self.calls = []

        def generate_structured(
            self,
            system_prompt,
            user_prompt,
            response_format=None,
            **kwargs,
        ):
            self.calls.append((system_prompt, user_prompt, response_format, kwargs))
            return {"special_characteristic_judgments": []}

    generator = FakeGenerator()
    judge = SpecialCharacteristicJudge(generator=generator)
    judge.judge({"symbol_occurrences": [], "page_evidence_refs": []})

    system_prompt, user_prompt, response_format, kwargs = generator.calls[0]
    assert "证据约束裁判" in system_prompt
    assert "不能引用 evidence packet 之外的证据" in system_prompt
    assert "symbol_evidence_refs 只能引用 symbol_occurrences.candidate_id" in system_prompt
    assert "standard_evidence_refs 只能引用" in system_prompt
    assert "page_evidence_refs 只能引用 evidence packet.page_evidence_refs" in system_prompt
    assert "symbol_occurrences" in user_prompt
    assert response_format["type"] == "json_schema"
    assert kwargs["model"] == "gpt-5.5"


def test_judge_verifier_reports_count_mismatch_when_confirmed_less_than_declared():
    packet = {
        "declared_totals": {"CC": 2, "SC": 1},
        "symbol_occurrences": [
            {"candidate_id": "MSC-001", "evidence_refs": ["drawing_page_001"]}
        ],
        "legend_evidence": [],
        "text_evidence": [
            {"text_id": "TXT-001", "evidence_refs": ["ocr_page_001"]}
        ],
        "customer_rules": [],
        "page_evidence_refs": ["drawing_page_001", "ocr_page_001"],
    }
    judgments = [
        {
            "judgment_id": "SCJ-001",
            "candidate_id": "MSC-001",
            "classification": "CC",
            "verdict": "confirmed",
            "linked_feature": "技术要求 1",
            "confidence": 0.9,
            "standard_evidence_refs": ["TXT-001"],
            "symbol_evidence_refs": ["MSC-001"],
            "page_evidence_refs": ["drawing_page_001"],
            "reasoning_summary": "证据完整。",
        }
    ]

    report = verify_special_characteristic_judgments(judgments, packet)

    assert report["confirmed"][0]["classification"] == "CC"
    risk_ids = {risk["risk_id"] for risk in report["risks"]}
    assert "SC-JUDGE-COUNT-MISMATCH-CC" in risk_ids
    assert "SC-JUDGE-COUNT-MISMATCH-SC" in risk_ids
