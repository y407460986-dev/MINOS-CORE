import unittest
from unittest.mock import patch

from minos_core.pfd_to_pfmea_ai import (
    infer_pfmea_from_process_flow,
    normalize_pfmea_rows,
)
from minos_core.pipeline_chain import (
    generate_pfmea_from_confirmed_pfd,
)

from .conftest import PFMEA_CONTROL_LOGIC_FIELDS, assert_pfmea_ai_risk_row, rows_by_step


class PFMEAGenerationTests(unittest.TestCase):
    """Tests for PFMEAGeneration workflow stage."""

    def test_chain_pfmea_inherits_confirmed_pfd_process_fields(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "",
                    "process_step_id": "P10",
                    "process_item": "制造过程",
                    "process_step_name": "",
                    "work_element_4m": "机",
                    "function_process_step": "",
                    "function_work_element": "压力机稳定输出",
                    "failure_effect": "下一工序无法装配",
                    "severity": 8,
                    "failure_mode": "安装孔偏移",
                    "failure_cause": "定位销磨损",
                    "prevention_control": "点检定位销",
                    "occurrence": 4,
                    "detection_control": "首件检验孔位",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "SC",
                    "preventive_action": "点检定位销并确认孔位能力",
                    "detection_action": "增加孔位巡检频次",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "needs_confirmation": True,
                }
            ]
        }
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "冲压安装孔",
                    "process_function": "形成安装孔位置",
                    "equipment": "压力机",
                    "product_characteristics": "安装孔位置度",
                    "process_characteristics": "冲压力",
                }
            ]
        }

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.return_value = llm_payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        row = pfmea["rows"][0]
        call_kwargs = llm.generate_structured.call_args.kwargs
        schema_items = (
            call_kwargs["response_format"]["json_schema"]["schema"]["properties"]["rows"]["items"]
        )
        for field in PFMEA_CONTROL_LOGIC_FIELDS:
            self.assertIn(field, schema_items["properties"])
            self.assertIn(field, schema_items["required"])
        self.assertIn("原因过程参数", call_kwargs["system_prompt"])
        self.assertIn("预防控制对象", call_kwargs["system_prompt"])
        self.assertIn("探测对象", call_kwargs["system_prompt"])
        self.assertIn("预防控制必须控制失效原因", call_kwargs["user_prompt"])
        self.assertEqual(row["process_step_id"], "P10")
        self.assertEqual(row["operation"], "冲压安装孔")
        self.assertEqual(row["process_step"], "冲压安装孔")
        self.assertEqual(row["process_step_name"], "冲压安装孔")
        self.assertEqual(row["structure_process_step"], "冲压安装孔")
        self.assertEqual(row["structure_process_item"], "制造过程")
        self.assertEqual(row["structure_work_element"], "压力机")
        self.assertEqual(row["function_process_item"], "制造过程")
        self.assertEqual(row["function_process_step"], "形成安装孔位置")
        self.assertEqual(row["function_work_element"], "压力机稳定输出")
        self.assertEqual(row["function_requirement"], "形成安装孔位置")
        self.assertEqual(row["preventive_action"], "点检定位销并确认孔位能力")
        self.assertEqual(row["detection_action"], "增加孔位巡检频次")
        self.assertEqual(row["optimization_action"], "点检定位销并确认孔位能力；增加孔位巡检频次")
        self.assertEqual(row["AP"], "M")
        self.assertNotIn("rpn", row)
        self.assertNotIn("after_rpn", row)
        self.assertEqual(row["pfmea_id"], "PFMEA-P10-01")
        self.assertEqual(row["cause_process_parameter"], "冲压力")
        self.assertIn("定位销磨损", row["prevention_control_target"])
        self.assertTrue(row["prevention_control_timing"])
        self.assertIn("安装孔", row["detection_control_target"])
        self.assertTrue(row["detection_control_timing"])
        self.assertIn("预防", row["control_logic_review"])
        self.assertIn("探测", row["control_logic_review"])


    def test_chain_pfmea_generates_one_llm_request_per_confirmed_pfd_step(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "来料检验",
                    "process_function": "确认来料符合图纸要求",
                    "equipment": "检验台",
                },
                {
                    "process_step_id": "P20",
                    "operation": "冲压成形",
                    "process_function": "形成铰链主体形状",
                    "equipment": "压力机",
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P10",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "检验台",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "检验台执行来料确认",
                        "failure_effect": "不合格物料流入后续工序",
                        "severity": 7,
                        "failure_mode": "来料状态误判",
                        "failure_cause": "检验标准使用错误",
                        "prevention_control": "检验标准版本确认",
                        "occurrence": 3,
                        "detection_control": "复核检验记录",
                        "detection": 4,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "锁定检验标准版本",
                        "detection_action": "抽查记录",
                        "optimization_action": "锁定检验标准版本；抽查记录",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "pfmea_id": "",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "",
                        "structure_process_item": "制造过程",
                        "structure_process_step": "",
                        "structure_work_element": "压力机",
                        "work_element_4m": "机",
                        "function_process_item": "制造过程",
                        "function_process_step": "",
                        "function_work_element": "压力机形成主体形状",
                        "failure_effect": "铰链安装间隙异常",
                        "severity": 8,
                        "failure_mode": "成形尺寸偏差",
                        "failure_cause": "冲压参数漂移",
                        "prevention_control": "首件参数确认",
                        "occurrence": 4,
                        "detection_control": "尺寸巡检",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "SC",
                        "preventive_action": "锁定压力机参数",
                        "detection_action": "增加尺寸巡检",
                        "optimization_action": "锁定压力机参数；增加尺寸巡检",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            },
        ]

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.side_effect = payloads

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        self.assertEqual(llm.generate_structured.call_count, 2)
        prompts = [
            call.kwargs["user_prompt"]
            for call in llm.generate_structured.call_args_list
        ]
        self.assertIn("P10", prompts[0])
        self.assertNotIn("P20", prompts[0])
        self.assertIn("P20", prompts[1])
        self.assertNotIn("P10", prompts[1])
        self.assertEqual(
            [row["process_step_id"] for row in pfmea["rows"]],
            ["P10", "P20"],
        )
        self.assertEqual(
            pfmea["metadata"]["pfmea_generation_strategy"],
            "per_pfd_step",
        )


    def test_chain_pfmea_rejects_rows_not_from_confirmed_pfd(self):
        llm_payload = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P99-01",
                    "process_step_id": "P99",
                    "process_item": "制造过程",
                    "process_step_name": "不存在工序",
                    "work_element_4m": "机",
                    "function_process_step": "不存在",
                    "function_work_element": "不存在",
                    "failure_effect": "影响装配",
                    "severity": 8,
                    "failure_mode": "尺寸偏差",
                    "failure_cause": "参数错误",
                    "prevention_control": "参数确认",
                    "occurrence": 4,
                    "detection_control": "检验",
                    "detection": 5,
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "preventive_action": "",
                    "detection_action": "",
                    "responsible_person": "",
                    "target_date": "",
                    "status": "未开始",
                    "needs_confirmation": True,
                }
            ]
        }

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            with self.assertRaisesRegex(ValueError, "P99"):
                generate_pfmea_from_confirmed_pfd(
                    {},
                    {"steps": [{"process_step_id": "P10", "operation": "冲压安装孔"}]},
                )


    def test_chain_pfmea_rejects_step_request_returning_another_confirmed_step(self):
        confirmed_pfd = {
            "steps": [
                {"process_step_id": "P10", "operation": "来料检验"},
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "pfmea_id": "PFMEA-P20-01",
                        "process_step_id": "P20",
                        "process_item": "制造过程",
                        "process_step_name": "冲压成形",
                        "work_element_4m": "机",
                        "function_process_step": "形成铰链主体",
                        "function_work_element": "压力机输出",
                        "failure_effect": "影响装配",
                        "severity": 8,
                        "failure_mode": "尺寸偏差",
                        "failure_cause": "参数漂移",
                        "prevention_control": "参数确认",
                        "occurrence": 4,
                        "detection_control": "尺寸检验",
                        "detection": 5,
                        "action_priority": "M",
                        "special_characteristics": "无",
                        "preventive_action": "",
                        "detection_action": "",
                        "responsible_person": "",
                        "target_date": "",
                        "status": "未开始",
                        "needs_confirmation": True,
                    }
                ]
            }
        ]

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            # Parallel execution: both steps call LLM; return the same wrong payload for both
            generator.return_value.generate_structured.return_value = payloads[0]

            with self.assertRaisesRegex(ValueError, "expected P10"):
                generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)


    def test_normalize_pfmea_rows_outputs_aiag_vda_form_c_fields(self):
        rows = [
            {
                "pfmea_id": "PFMEA-P10-01",
                "process_step_id": "P10",
                "operation": "冲压成形",
                "process_function": "形成安装面",
                "equipment": "压力机",
                "process_characteristics": "冲压力",
                "failure_mode": "安装面变形",
                "failure_effect": "装配间隙不满足要求",
                "failure_cause": "压力机参数不稳定",
                "severity": 8,
                "occurrence": 5,
                "detection": 6,
                "prevention_control": "锁定压力机参数",
                "detection_control": "首件和巡检测量安装面",
                "special_characteristics": ["SC-1"],
            }
        ]

        normalize_pfmea_rows(
            rows,
            process_steps=[
                {
                    "process_step_id": "P10",
                    "operation": "冲压成形",
                    "process_function": "形成安装面",
                    "equipment": "压力机",
                    "process_characteristics": "冲压力",
                }
            ],
        )

        row = rows[0]
        for field in (
            "process_item",
            "process_step",
            "process_work_element",
            "structure_process_item",
            "structure_process_step",
            "structure_work_element",
            "function_process_item",
            "function_process_step",
            "function_work_element",
            "failure_effect",
            "failure_mode",
            "failure_cause",
            "prevention_control",
            "detection_control",
            "cause_process_parameter",
            "prevention_control_target",
            "prevention_control_timing",
            "detection_control_target",
            "detection_control_timing",
            "control_logic_review",
            "severity",
            "occurrence",
            "detection",
            "action_priority",
            "optimization_action",
            "responsible_person",
            "target_date",
            "status",
            "needs_confirmation",
            "S",
            "O",
            "D",
            "AP",
        ):
            self.assertIn(field, row)
        self.assertEqual(row["process_item"], "制造过程")
        self.assertEqual(row["process_step"], "冲压成形")
        self.assertEqual(row["process_work_element"], "压力机")
        self.assertEqual(row["structure_process_item"], "制造过程")
        self.assertEqual(row["structure_process_step"], "冲压成形")
        self.assertEqual(row["structure_work_element"], "压力机")
        self.assertEqual(row["function_process_item"], "制造过程")
        self.assertEqual(row["function_process_step"], "形成安装面")
        self.assertEqual(row["function_work_element"], "冲压力")
        self.assertEqual(row["cause_process_parameter"], "冲压力")
        self.assertIn("压力机参数不稳定", row["prevention_control_target"])
        self.assertTrue(row["prevention_control_timing"])
        self.assertIn("安装面", row["detection_control_target"])
        self.assertIn("首件", row["detection_control_timing"])
        self.assertIn("预防", row["control_logic_review"])
        self.assertEqual(row["AP"], row["action_priority"])
        self.assertIn(row["action_priority"], {"H", "M", "L"})
        self.assertNotIn("rpn", row)
        self.assertNotIn("after_rpn", row)
        self.assertIsInstance(row["needs_confirmation"], bool)


    def test_pfmea_ai_risk_inference_uses_step_context_and_confirmation_rules(self):
        pfd = {
            "document_type": "process_flow",
            "schema_version": "minos-core.generated.v1",
            "product": {"part_name": "Demo Part"},
            "evidence": [{"evidence_id": "EV-1"}],
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Blanking",
                    "process_function": "Create blank profile",
                    "confidence": 0.88,
                    "evidence_refs": ["EV-1"],
                },
                {
                    "process_step_id": "P20",
                    "operation": "Piercing",
                    "process_function": "Create mounting holes",
                    "special_characteristics": ["SC-HOLE-POS"],
                    "confidence": 0.83,
                    "evidence_refs": ["EV-1"],
                },
                {
                    "process_step_id": "P30",
                    "operation": "Final inspection",
                    "process_function": "Verify finished part",
                    "confidence": 0.62,
                    "evidence_refs": ["EV-1"],
                },
            ],
            "links": [],
        }

        pfmea = infer_pfmea_from_process_flow(pfd)
        rows_by_step_dict = rows_by_step(pfmea["rows"])

        for step_id in ("P10", "P20", "P30"):
            self.assertGreaterEqual(len(rows_by_step_dict[step_id]), 2)
            failure_modes = [row["failure_mode"] for row in rows_by_step_dict[step_id]]
            self.assertEqual(len(failure_modes), len(set(failure_modes)))
        for row in pfmea["rows"]:
            assert_pfmea_ai_risk_row(self, row)
            self.assertEqual(row["S"], row["severity"])
            self.assertEqual(row["O"], row["occurrence"])
            self.assertEqual(row["D"], row["detection"])
            self.assertEqual(row["AP"], row["action_priority"])
        self.assertTrue(any("毛坯" in row["failure_mode"] for row in rows_by_step_dict["P10"]))
        self.assertTrue(any("孔" in row["failure_mode"] for row in rows_by_step_dict["P20"]))
        self.assertTrue(any(row["AP"] == "H" for row in rows_by_step_dict["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step_dict["P20"]))
        self.assertTrue(all(row["needs_confirmation"] for row in rows_by_step_dict["P30"]))
        self.assertTrue(any(not row["needs_confirmation"] for row in rows_by_step_dict["P10"]))




if __name__ == "__main__":
    unittest.main()
