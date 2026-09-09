from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from minos_core.quality_gates import evaluate_export_gate

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "jlv_quality_gate"
    / "defective_chain.json"
)


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _corrected_chain() -> dict:
    chain = deepcopy(_load_fixture())
    chain["product"]["part_name"] = "BACK DOOR HINGE 尾门铰链"
    chain["metadata"]["drawing_analysis_risks"] = []
    chain["metadata"]["ocr_identity_risks"] = []
    chain["pending_fields"] = []
    chain["ai_inferred_items"] = []
    chain["metadata"]["review_issues"] = []
    for failure_mode in chain["failure_modes"]:
        failure_mode["responsibility"] = "质量工程师"
        failure_mode["target_date"] = "2026-12-31"
        failure_mode["action_status"] = "计划中"
        if failure_mode["pfmea_id"] == "PFMEA-P02-02":
            failure_mode["recommended_action"] = "强化表面处理膜层和封闭参数验证，确保红锈 240h 要求稳定达成"

    chain["controls"] = [
        {
            "control_plan_id": "CP-P01-01",
            "process_step_id": "P01",
            "pfmea_id": "PFMEA-P01-01",
            "product_process_characteristic": "图纸身份与来料零件一致性",
            "specification": (
                "零件号 JLV03000500-001-AC-RR，零件名称 BACK DOOR HINGE 尾门铰链，"
                "图纸版本 AC，来料标识与图纸一致"
            ),
            "measurement_method": "核对图纸、标签、随货文件和首件实物标识",
            "sample_size": "每批首件 1 件",
            "sample_frequency": "每批来料",
            "control_method": "质量工程师按 JLV 图纸身份清单逐项复核并记录",
            "reaction_plan": "身份不一致时隔离整批来料，冻结后续表面处理并通知质量工程师处置",
            "evidence_refs": [
                "EV-JLV-DRAWING-001"
            ],
        },
        {
            "control_plan_id": "CP-P02-01",
            "process_step_id": "P02",
            "pfmea_id": "PFMEA-P02-01",
            "product_process_characteristic": "白锈耐蚀性能",
            "specification": "中性盐雾试验白锈 72h 无白锈，120h 白锈面积满足 JLV 图纸要求",
            "measurement_method": "按盐雾试验作业指导书进行 72h 与 120h 外观判定",
            "sample_size": "每炉次 3 件",
            "sample_frequency": "每炉次表面处理后",
            "control_method": "监控表面处理膜层参数并执行白锈盐雾验证",
            "reaction_plan": "白锈 72h/120h 不合格时停线隔离，复核膜层厚度并重新表面处理",
            "evidence_refs": [
                "EV-JLV-DRAWING-001"
            ],
        },
        {
            "control_plan_id": "CP-P02-02",
            "process_step_id": "P02",
            "pfmea_id": "PFMEA-P02-02",
            "product_process_characteristic": "红锈耐蚀性能",
            "specification": "中性盐雾试验红锈 240h 无红锈，且白锈 72h/120h 同步满足 JLV 图纸要求",
            "measurement_method": "按盐雾试验作业指导书进行 240h 红锈判定并记录白锈节点结果",
            "sample_size": "每炉次 3 件",
            "sample_frequency": "每炉次表面处理后",
            "control_method": "监控表面处理膜层和封闭参数并执行红锈 240h 盐雾验证",
            "reaction_plan": "红锈 240h 不合格时冻结发运，隔离炉次产品并启动纠正措施",
            "evidence_refs": [
                "EV-JLV-DRAWING-001"
            ],
        },
    ]
    return chain


def test_jlv_defective_chain_blocks_formal_export() -> None:
    gate = evaluate_export_gate(_load_fixture())
    gate_text = json.dumps(gate.model_dump(), ensure_ascii=False, default=str)

    assert gate.allow_formal_release is False
    assert "duplicate_control_plan_id" in gate_text
    assert "uncovered_pfmea" in gate_text
    assert "generic_control_text" in gate_text
    assert "DRAWING-IDENTITY-SUSPECT-OCR" in gate_text
    assert "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in gate_text


def test_jlv_corrected_chain_allows_formal_export() -> None:
    chain = _corrected_chain()

    gate = evaluate_export_gate(chain)
    gate_text = json.dumps(gate.model_dump(), ensure_ascii=False, default=str)

    assert gate.allow_formal_release is True, gate_text


def test_jlv_final_export_blocks_unresolved_special_characteristic_judge_risk() -> None:
    chain = _corrected_chain()
    chain["metadata"]["drawing_analysis_risks"] = [
        {
            "risk_id": "SCJ-RISK-001",
            "category": "special_characteristic_judge",
            "severity": "review",
            "target": "special_characteristic_judgments.SCJ-001",
            "message": "AI 裁判判定缺少完整证据引用，正式输出前必须复核。",
        }
    ]

    gate = evaluate_export_gate(chain)
    gate_text = json.dumps(gate.model_dump(), ensure_ascii=False, default=str)

    assert gate.allow_formal_release is False
    assert "special_characteristic_judge" in gate_text
    assert "SCJ-RISK-001" in gate_text

    chain["metadata"]["review_confirmations"] = [
        {
            "target": "special_characteristic_judgments.SCJ-001",
            "confirmed_by": "quality.engineer",
            "confirmed_at": "2026-06-04T10:00:00Z",
            "reason": "AI 裁判风险已人工复核。",
        }
    ]

    gate_after_confirmation = evaluate_export_gate(chain)
    gate_after_text = json.dumps(
        gate_after_confirmation.model_dump(),
        ensure_ascii=False,
        default=str,
    )

    assert gate_after_confirmation.allow_formal_release is True, gate_after_text


def test_final_export_gate_blocks_declared_special_count_missing_risk() -> None:
    chain = _corrected_chain()
    chain["metadata"]["drawing_analysis_risks"] = [
        {
            "risk_id": "SC-DISCOVERY-MISSING-CC",
            "item_id": "SC-DISCOVERY-MISSING-CC",
            "category": "special_characteristic_discovery",
            "severity": "review",
            "target": "declared_totals.CC",
            "message": "图纸声明 CC 有 2 个，当前只定位到 0 个。",
        }
    ]

    gate = evaluate_export_gate(chain)

    assert gate.allow_formal_release is False
    assert any(
        item.item_id == "SC-DISCOVERY-MISSING-CC"
        for item in gate.manual_review_items
    )
