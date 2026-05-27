from __future__ import annotations

from minos_core.process_boundary import (
    apply_process_boundary_to_pfd,
    build_process_boundary_prompt,
    default_process_boundary_config,
)


def _step(step_id: str, operation: str, **overrides):
    row = {
        "process_step_id": step_id,
        "flow_type": "operation",
        "flow_symbol": "operation",
        "flow_type_display": "加工",
        "operation_type": "加工",
        "operation": operation,
        "input_material": "",
        "output_result": operation,
        "previous_step_ids": [],
        "next_step_ids": [],
        "process_function": operation,
        "equipment": "",
        "product_characteristics": "",
        "product_characteristic_class": "无",
        "process_characteristics": "",
        "process_characteristic_class": "无",
        "special_characteristics": [],
        "evidence_refs": [],
        "confidence": 0.8,
        "ai_inferred": True,
        "needs_confirmation": False,
    }
    row.update(overrides)
    return row


def test_default_process_boundary_declares_forging_as_purchased_input() -> None:
    config = default_process_boundary_config()

    assert config["enabled"] is True
    assert "锻件" in config["purchased_inputs"]


def test_default_process_boundary_disallows_supplier_forging_operations() -> None:
    config = default_process_boundary_config()

    assert "锻造成形" in config["disallowed_internal_operations"]
    assert "热处理锻件" in config["disallowed_internal_operations"]


def test_process_boundary_prompt_states_company_scope_and_supplier_exclusion() -> None:
    prompt = build_process_boundary_prompt(default_process_boundary_config())

    assert "PFD 是本公司总成制造过程" in prompt
    assert "不展开供应商制程" in prompt
    assert "锻件" in prompt


def test_process_boundary_removes_supplier_steps_and_keeps_internal_processes() -> None:
    process_flow = {
        "steps": [
            _step(
                "P01",
                "来料检验",
                flow_type="inspection",
                flow_symbol="inspection",
                flow_type_display="检验",
                operation_type="检验",
                input_material="毛坯",
                process_function="确认来料合格",
            ),
            _step("P02", "加热坯料", equipment="加热炉"),
            _step("P03", "锻造成形", equipment="摩擦压力机"),
            _step("P04", "冲制轴孔", equipment="冲床"),
        ],
        "metadata": {"source": "test"},
    }

    corrected = apply_process_boundary_to_pfd(
        process_flow,
        default_process_boundary_config(),
    )

    operations = [step["operation"] for step in corrected["steps"]]
    assert "加热坯料" not in operations
    assert "锻造成形" not in operations
    assert "冲制轴孔" in operations
    assert [step["process_step_id"] for step in corrected["steps"]] == ["P01", "P02"]
    assert corrected["steps"][0]["previous_step_ids"] == []
    assert corrected["steps"][0]["next_step_ids"] == ["P02"]
    assert corrected["steps"][1]["previous_step_ids"] == ["P01"]
    assert corrected["steps"][1]["next_step_ids"] == []
    incoming_text = " ".join(
        str(corrected["steps"][0].get(field, ""))
        for field in ("input_material", "process_function")
    )
    assert "锻件" in incoming_text
    assert corrected["metadata"]["process_boundary_applied"] is True
    assert corrected["metadata"]["process_boundary_adjustments"]


def test_process_boundary_respects_supplier_exclusion_toggle() -> None:
    config = {
        **default_process_boundary_config(),
        "supplier_processes_excluded": False,
    }
    process_flow = {
        "steps": [
            _step("P01", "来料检验"),
            _step("P02", "锻造成形", equipment="摩擦压力机"),
        ]
    }

    corrected = apply_process_boundary_to_pfd(process_flow, config)
    prompt = build_process_boundary_prompt(config)

    assert [step["operation"] for step in corrected["steps"]] == ["来料检验", "锻造成形"]
    assert corrected["metadata"]["process_boundary_applied"] is False
    assert prompt == ""
