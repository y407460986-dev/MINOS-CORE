import unittest
from unittest.mock import patch

from minos_core.generate_control_plan import (
    generate_control_plan_from_pfmea,
    normalize_control_plan_rows,
)
from minos_core.pipeline_chain import (
    generate_cp_from_confirmed_pfmea,
    generate_pfd_from_drawing,
    generate_pfmea_from_confirmed_pfd,
)


class ControlPlanGenerationTests(unittest.TestCase):
    """Tests for ControlPlanGeneration workflow stage."""

    def test_chain_cp_generates_per_pfmea_row_to_avoid_gateway_timeout(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P10",
                    "operation": "来料检验",
                    "special_characteristics": ["SC-来料尺寸"],
                },
                {"process_step_id": "P20", "operation": "冲压成形"},
            ]
        }
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "equipment": "检具",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "H",
                    "special_characteristics": "SC",
                    "characteristic_refs": ["SC-来料尺寸"],
                    "evidence_refs": ["EV-PFMEA-P10"],
                },
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "冲压参数漂移",
                    "prevention_control": "参数点检",
                    "detection_control": "尺寸巡检",
                    "action_priority": "M",
                    "special_characteristics": "无",
                    "evidence_refs": ["EV-PFMEA-P20"],
                },
            ]
        }
        payloads = [
            {
                "rows": [
                    {
                        "control_plan_id": "CP-P10-01",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-01",
                        "process_name": "来料检验",
                        "equipment": "检具",
                        "characteristic_number": "PFMEA-P10-01",
                        "product_characteristic": "来料尺寸",
                        "process_characteristic": "供应商批次",
                        "special_characteristic_class": "SC",
                        "specification_tolerance": "按图纸要求",
                        "measurement_method": "来料检验",
                        "sample_size": "5 件",
                        "sample_frequency": "每批",
                        "control_method": "供应商审核；来料检验",
                        "process_parameter": "供应商批次追溯",
                        "parameter_specification": "批次状态受控且证书齐全",
                        "process_control_method": "供应商放行清单与批次扫描",
                        "setup_verification": "换批前确认供应商批次和材质证明",
                        "poka_yoke_device": "批次扫码防错",
                        "poka_yoke_verification": "每批首件扫码验证",
                        "process_record": "来料批次追溯记录",
                        "reaction_plan": "隔离批次并通知质量工程师",
                        "needs_confirmation": True,
                    }
                ]
            },
            {
                "rows": [
                    {
                        "control_plan_id": "CP-P20-01",
                        "process_step_id": "P20",
                        "pfmea_id": "PFMEA-P20-01",
                        "process_name": "冲压成形",
                        "equipment": "压力机",
                        "characteristic_number": "PFMEA-P20-01",
                        "product_characteristic": "成形尺寸",
                        "process_characteristic": "冲压参数",
                        "special_characteristic_class": "无",
                        "specification_tolerance": "按图纸要求",
                        "measurement_method": "尺寸巡检",
                        "sample_size": "5 件",
                        "sample_frequency": "每班",
                        "control_method": "参数点检；尺寸巡检",
                        "process_parameter": "冲压力",
                        "parameter_specification": "按作业指导书设定范围",
                        "process_control_method": "参数锁定并每班点检",
                        "setup_verification": "首件确认冲压参数和模具状态",
                        "poka_yoke_device": "压力机参数权限锁",
                        "poka_yoke_verification": "换型后验证参数锁定有效",
                        "process_record": "冲压参数点检表",
                        "reaction_plan": "隔离产品并调整参数",
                        "needs_confirmation": True,
                    }
                ]
            },
        ]

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            llm = generator.return_value
            llm.generate_structured.side_effect = payloads

            cp = generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

        self.assertEqual(llm.generate_structured.call_count, 2)
        prompts = [call.kwargs["user_prompt"] for call in llm.generate_structured.call_args_list]
        self.assertIn("PFMEA-P10-01", prompts[0])
        self.assertNotIn("PFMEA-P20-01", prompts[0])
        self.assertIn("PFMEA-P20-01", prompts[1])
        self.assertNotIn("PFMEA-P10-01", prompts[1])
        self.assertEqual([row["pfmea_id"] for row in cp["rows"]], ["PFMEA-P10-01", "PFMEA-P20-01"])
        for row in cp["rows"]:
            for field in (
                "process_parameter",
                "parameter_specification",
                "process_control_method",
                "setup_verification",
                "poka_yoke_device",
                "poka_yoke_verification",
                "process_record",
            ):
                self.assertIn(field, row)
                self.assertTrue(row[field])
            self.assertEqual(row["specification"], row["specification_tolerance"])
            self.assertEqual(row["evidence_refs"], [f"EV-{row['pfmea_id'].removesuffix('-01')}"])
        self.assertEqual(cp["rows"][0]["source_special_characteristics"], ["SC-来料尺寸"])
        self.assertEqual(cp["rows"][0]["product_process_characteristic"], "来料尺寸")
        self.assertEqual(cp["metadata"]["cp_generation_strategy"], "per_pfmea_row")

    def test_chain_cp_covers_low_ap_pfmea_rows_for_formal_export_gate(self):
        confirmed_pfd = {"steps": [{"process_step_id": "P10", "operation": "来料检验"}]}
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-HIGH",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "H",
                    "evidence_refs": ["EV-HIGH"],
                },
                {
                    "pfmea_id": "PFMEA-P10-LOW",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "标签轻微污损",
                    "failure_cause": "搬运摩擦",
                    "prevention_control": "周转防护",
                    "detection_control": "目视检查",
                    "action_priority": "L",
                    "evidence_refs": ["EV-LOW"],
                },
            ]
        }

        def payload_for_prompt(*args, **kwargs):
            prompt_text = " ".join(str(value) for value in args)
            prompt_text += " " + " ".join(str(value) for value in kwargs.values())
            if "PFMEA-P10-HIGH" in prompt_text:
                return {
                    "rows": [
                        {
                            "control_plan_id": "CP-P10-HIGH",
                            "process_step_id": "P10",
                            "pfmea_id": "PFMEA-P10-HIGH",
                            "process_name": "来料检验",
                            "equipment": "检具",
                            "characteristic_number": "PFMEA-P10-HIGH",
                            "product_characteristic": "来料尺寸",
                            "process_characteristic": "供应商批次",
                            "special_characteristic_class": "无",
                            "specification_tolerance": "按图纸要求",
                            "measurement_method": "尺寸检验",
                            "sample_size": "5 件",
                            "sample_frequency": "每批",
                            "control_method": "供应商审核；来料检验",
                            "process_parameter": "供应商批次状态",
                            "parameter_specification": "批次状态受控",
                            "process_control_method": "供应商放行清单",
                            "setup_verification": "换批前确认批次状态",
                            "poka_yoke_device": "批次扫码",
                            "poka_yoke_verification": "每批首件扫码验证",
                            "process_record": "来料检验记录",
                            "reaction_plan": "隔离并通知质量工程师",
                            "needs_confirmation": True,
                        }
                    ]
                }
            if "PFMEA-P10-LOW" in prompt_text:
                return {
                    "rows": [
                        {
                            "control_plan_id": "CP-P10-LOW",
                            "process_step_id": "P10",
                            "pfmea_id": "PFMEA-P10-LOW",
                            "process_name": "来料检验",
                            "equipment": "检具",
                            "characteristic_number": "PFMEA-P10-LOW",
                            "product_characteristic": "标签外观",
                            "process_characteristic": "搬运防护",
                            "special_characteristic_class": "无",
                            "specification_tolerance": "标签清晰可识别",
                            "measurement_method": "目视检查",
                            "sample_size": "3 件",
                            "sample_frequency": "每批",
                            "control_method": "周转防护；目视检查",
                            "process_parameter": "周转防护状态",
                            "parameter_specification": "料框隔离完好",
                            "process_control_method": "周转料框点检",
                            "setup_verification": "上线前确认防护状态",
                            "poka_yoke_device": "料框隔离标识",
                            "poka_yoke_verification": "每批确认隔离标识",
                            "process_record": "来料外观检查记录",
                            "reaction_plan": "隔离并更换标签",
                            "needs_confirmation": True,
                        }
                    ]
                }
            raise AssertionError(f"Prompt did not include expected PFMEA id: {prompt_text}")

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = payload_for_prompt

            cp = generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

        self.assertEqual(generator.return_value.generate_structured.call_count, 2)
        self.assertEqual(
            [row["pfmea_id"] for row in cp["rows"]],
            ["PFMEA-P10-HIGH", "PFMEA-P10-LOW"],
        )

    def test_chain_cp_normalizes_duplicate_llm_control_plan_ids_per_step(self):
        confirmed_pfd = {"steps": [{"process_step_id": "P10", "operation": "来料检验"}]}
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "来料尺寸不符",
                    "action_priority": "H",
                },
                {
                    "pfmea_id": "PFMEA-P10-02",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "标签错误",
                    "action_priority": "M",
                },
            ]
        }
        payload_by_pfmea_id = {
            "PFMEA-P10-01": {
                "rows": [
                    {
                        "control_plan_id": "CP-DUPLICATE",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-01",
                        "process_name": "来料检验",
                        "characteristic_number": "PFMEA-P10-01",
                        "product_characteristic": "来料尺寸",
                        "process_characteristic": "来料检验",
                        "specification_tolerance": "按图纸要求",
                        "measurement_method": "尺寸检验",
                        "control_method": "来料检验",
                        "reaction_plan": "隔离并通知质量工程师",
                    }
                ]
            },
            "PFMEA-P10-02": {
                "rows": [
                    {
                        "control_plan_id": "CP-DUPLICATE",
                        "process_step_id": "P10",
                        "pfmea_id": "PFMEA-P10-02",
                        "process_name": "来料检验",
                        "characteristic_number": "PFMEA-P10-02",
                        "product_characteristic": "标签",
                        "process_characteristic": "来料检验",
                        "specification_tolerance": "按包装规范",
                        "measurement_method": "目视检查",
                        "control_method": "标签核对",
                        "reaction_plan": "隔离并更换标签",
                    }
                ]
            },
        }

        def duplicate_id_payload_for_prompt(*args, **kwargs):
            prompt_text = " ".join(str(value) for value in args)
            prompt_text += " " + " ".join(str(value) for value in kwargs.values())
            for pfmea_id, payload in payload_by_pfmea_id.items():
                if pfmea_id in prompt_text:
                    return payload
            raise AssertionError(f"Prompt did not include expected PFMEA id: {prompt_text}")

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.side_effect = duplicate_id_payload_for_prompt

            cp = generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)

        self.assertEqual(
            [(row["control_plan_id"], row["pfmea_id"]) for row in cp["rows"]],
            [("CP-P10-01", "PFMEA-P10-01"), ("CP-P10-02", "PFMEA-P10-02")],
        )

    def test_chain_pfd_uses_drawing_page_evidence_when_llm_omits_refs(self):
        drawing_analysis = {
            "drawing_identity": {"part_name": "尾门铰链"},
            "evidence": [
                {
                    "evidence_id": "ocr_page_001",
                    "source": "ocr_page",
                    "content": "图纸整页 OCR",
                },
                {
                    "evidence_id": "ocr_page_001_block_0001",
                    "source": "ocr_block",
                    "content": "局部文字",
                },
            ],
        }
        payload = {
            "steps": [
                {
                    "process_step_id": "P01",
                    "operation": "来料检验",
                    "flow_type": "inspection",
                    "equipment": "检具",
                }
            ]
        }

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = payload

            pfd = generate_pfd_from_drawing(drawing_analysis)

        self.assertEqual(pfd["steps"][0]["evidence_refs"], ["ocr_page_001"])

    def test_chain_pfmea_inherits_pfd_evidence_when_llm_omits_refs(self):
        confirmed_pfd = {
            "steps": [
                {
                    "process_step_id": "P01",
                    "operation": "来料检验",
                    "evidence_refs": ["ocr_page_001"],
                    "special_characteristics": ["SC-盐雾"],
                    "product_characteristic_class": "SC",
                }
            ]
        }
        payload = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P01-01",
                    "process_step_id": "P01",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "M",
                }
            ]
        }

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = payload

            pfmea = generate_pfmea_from_confirmed_pfd({}, confirmed_pfd)

        self.assertEqual(pfmea["rows"][0]["evidence_refs"], ["ocr_page_001"])
        self.assertEqual(pfmea["rows"][0]["characteristic_refs"], ["SC-盐雾"])

    def test_control_plan_generation_outputs_process_controls_not_only_result_checks(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "process_characteristic": "冲压力",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "冲压参数漂移",
                    "prevention_control": "换型后参数点检并锁定",
                    "detection_control": "尺寸巡检",
                    "action_priority": "H",
                    "severity": 8,
                    "occurrence": 6,
                    "detection": 5,
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["process_parameter"], "冲压力")
        self.assertIn("冲压参数漂移", row["parameter_specification"])
        self.assertIn("换型后参数点检并锁定", row["process_control_method"])
        self.assertIn("首件", row["setup_verification"])
        self.assertTrue(row["poka_yoke_device"])
        self.assertTrue(row["poka_yoke_verification"])
        self.assertTrue(row["process_record"])


    def test_control_plan_generation_inherits_pfmea_cause_process_parameter(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P20-01",
                    "process_step_id": "P20",
                    "process_step_name": "冲压成形",
                    "equipment": "压力机",
                    "cause_process_parameter": "冲压力",
                    "failure_mode": "成形尺寸偏差",
                    "failure_cause": "压力不足导致成形不到位",
                    "prevention_control": "锁定压力机参数",
                    "detection_control": "尺寸巡检",
                    "action_priority": "H",
                    "severity": 8,
                    "occurrence": 6,
                    "detection": 5,
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["process_parameter"], "冲压力")
        self.assertIn("压力不足导致成形不到位", row["parameter_specification"])


    def test_control_plan_generation_ignores_source_control_plan_id(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "control_plan_id": "CP-DUPLICATE",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "H",
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        self.assertEqual(cp["rows"][0]["control_plan_id"], "CP-PFMEA-P10-01")


    def test_control_plan_generation_keeps_linked_control_plan_id(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "linked_control_plan_id": "CP-EXISTING-001",
                    "control_plan_id": "CP-DUPLICATE",
                    "failure_mode": "来料尺寸不符",
                    "failure_cause": "供应商过程波动",
                    "prevention_control": "供应商审核",
                    "detection_control": "来料检验",
                    "action_priority": "H",
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        self.assertEqual(cp["rows"][0]["control_plan_id"], "CP-EXISTING-001")


    def test_chain_cp_rejects_row_request_returning_another_pfmea(self):
        confirmed_pfd = {"steps": [{"process_step_id": "P10", "operation": "来料检验"}]}
        confirmed_pfmea = {
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "来料尺寸不符",
                    "action_priority": "H",
                },
                {
                    "pfmea_id": "PFMEA-P10-02",
                    "process_step_id": "P10",
                    "process_step_name": "来料检验",
                    "failure_mode": "标签错误",
                    "action_priority": "M",
                },
            ]
        }
        llm_payload = {
            "rows": [
                {
                    "control_plan_id": "CP-P10-02",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-02",
                    "process_name": "来料检验",
                    "equipment": "检具",
                    "characteristic_number": "PFMEA-P10-02",
                    "product_characteristic": "标签",
                    "process_characteristic": "来料批次",
                    "special_characteristic_class": "无",
                    "specification_tolerance": "按包装规范",
                    "measurement_method": "目视检查",
                    "sample_size": "5 件",
                    "sample_frequency": "每批",
                    "control_method": "标签核对",
                    "reaction_plan": "隔离并更换标签",
                    "needs_confirmation": True,
                }
            ]
        }

        with patch("minos_core.adapters.llm_text.OpenAITextGenerator") as generator:
            generator.return_value.generate_structured.return_value = llm_payload

            with self.assertRaisesRegex(ValueError, "expected PFMEA-P10-01"):
                generate_cp_from_confirmed_pfmea({}, confirmed_pfd, confirmed_pfmea)


    def test_normalize_control_plan_rows_outputs_cp_2024_fields(self):
        rows = [
            {
                "control_plan_id": "CP-P10-01",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-01",
                "process_name": "冲压成形",
                "product_process_characteristic": "安装面高度",
                "specification": "10.0 +/- 0.2 mm",
                "measurement_method": "高度规",
                "sample_size": "5 件",
                "sample_frequency": "每批",
                "control_method": "首件检验",
                "reaction_plan": "隔离并调整参数",
            }
        ]

        normalize_control_plan_rows(rows)

        row = rows[0]
        for field in (
            "control_plan_id",
            "process_step_id",
            "pfmea_id",
            "process_name",
            "equipment",
            "characteristic_number",
            "product_characteristic",
            "process_characteristic",
            "special_characteristic_class",
            "specification_tolerance",
            "measurement_method",
            "sample_size",
            "sample_frequency",
            "control_method",
                "reaction_plan",
                "process_parameter",
                "parameter_specification",
                "process_control_method",
                "setup_verification",
                "poka_yoke_device",
                "poka_yoke_verification",
                "process_record",
                "needs_confirmation",
            ):
                self.assertIn(field, row)
        self.assertEqual(row["product_characteristic"], "安装面高度")
        self.assertEqual(row["specification_tolerance"], "10.0 +/- 0.2 mm")
        self.assertIsInstance(row["needs_confirmation"], bool)


    def test_control_plan_generation_prefers_standard_pfmea_fields(self):
        pfmea_bundle = {
            "document_type": "pfmea",
            "rows": [
                {
                    "pfmea_id": "PFMEA-P10-01",
                    "process_step_id": "P10",
                    "process_step": "旧工序名",
                    "failure_mode": "孔位偏移",
                    "severity": 8,
                    "occurrence": 4,
                    "detection": 5,
                    "action_priority": "M",
                    "product_process_characteristic": "旧合并特性",
                    "product_characteristic": "标准产品特性",
                    "process_characteristic": "标准过程特性",
                    "specification": "旧规格",
                    "specification_tolerance": "标准规格公差",
                    "classification": "旧分类",
                    "special_characteristic_class": "标准特殊分类",
                }
            ],
        }

        cp = generate_control_plan_from_pfmea(pfmea_bundle)

        row = cp["rows"][0]
        self.assertEqual(row["product_characteristic"], "标准产品特性")
        self.assertEqual(row["process_characteristic"], "标准过程特性")
        self.assertEqual(row["product_process_characteristic"], "标准产品特性")
        self.assertEqual(row["specification_tolerance"], "标准规格公差")
        self.assertEqual(row["specification"], "标准规格公差")
        self.assertEqual(row["special_characteristic_class"], "标准特殊分类")
        self.assertEqual(row["classification"], "标准特殊分类")




if __name__ == "__main__":
    unittest.main()
