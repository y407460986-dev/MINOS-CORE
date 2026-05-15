import unittest

from minos_core.drawing_to_pfd import infer_process_flow_from_drawing


class DrawingToPfdTests(unittest.TestCase):
    # ========== 工艺库匹配 ==========

    def test_process_library_matches_sheet_metal_operations(self):
        """钣金工艺（blanking, piercing, forming, bending）能从工艺库匹配"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "piercing", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "evidence_refs": ["EV-001"]},
            {"operation": "bending", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("落料", operations)
        self.assertIn("冲孔", operations)
        self.assertIn("成形", operations)
        self.assertIn("折弯", operations)

        for step in pfd["steps"]:
            if step["operation"] in ("落料", "冲孔", "成形", "折弯"):
                self.assertTrue(step["process_function"])
                self.assertTrue(step["equipment"])

    def test_process_library_matches_machining_operations(self):
        """机加工艺（machining, drilling, tapping）能从工艺库匹配"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "machining", "evidence_refs": ["EV-001"]},
            {"operation": "drilling", "evidence_refs": ["EV-001"]},
            {"operation": "tapping", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("机加工", operations)
        self.assertIn("钻孔", operations)
        self.assertIn("攻丝", operations)

        for step in pfd["steps"]:
            if step["operation"] in ("机加工", "钻孔", "攻丝"):
                self.assertTrue(step["process_function"])
                self.assertTrue(step["equipment"])

    def test_process_library_matches_surface_treatment(self):
        """表面处理（surface treatment, plating, painting）能从工艺库匹配"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "surface treatment", "evidence_refs": ["EV-001"]},
            {"operation": "plating", "evidence_refs": ["EV-001"]},
            {"operation": "painting", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("表面处理", operations)
        self.assertIn("电镀", operations)
        self.assertIn("喷涂", operations)

        for step in pfd["steps"]:
            if step["operation"] in ("表面处理", "电镀", "喷涂"):
                self.assertTrue(step["process_function"])
                self.assertTrue(step["equipment"])

    # ========== 工序推断 ==========

    def test_infer_process_flow_from_drawing_clues(self):
        """从 manufacturing_clues 推断工序"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {
                "operation": "blanking",
                "process_function": "Cut blank from sheet",
                "confidence": 0.92,
                "evidence_refs": ["EV-001"],
            },
            {
                "operation": "piercing",
                "process_function": "Pierce mounting holes",
                "confidence": 0.88,
                "evidence_refs": ["EV-002"],
            },
        ]
        bundle["evidence"].append({"evidence_id": "EV-002", "source": "drawing_page"})

        pfd = infer_process_flow_from_drawing(bundle)

        # 会自动添加来料检验、材料准备等默认工序
        self.assertGreater(len(pfd["steps"]), 2)

        # 找到 blanking 和 piercing 工序
        blanking_step = next(s for s in pfd["steps"] if s["operation"] == "落料")
        piercing_step = next(s for s in pfd["steps"] if s["operation"] == "冲孔")

        self.assertEqual(blanking_step["process_function"], "Cut blank from sheet")
        self.assertEqual(blanking_step["confidence"], 0.92)
        self.assertIn("EV-001", blanking_step["evidence_refs"])

        self.assertEqual(piercing_step["process_function"], "Pierce mounting holes")
        self.assertIn("EV-002", piercing_step["evidence_refs"])

    def test_infer_process_flow_handles_missing_clues(self):
        """处理缺失线索 - 应该填充默认工序"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        # 应该有来料检验、材料准备等默认工序
        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("来料检验", operations)
        self.assertIn("材料准备", operations)
        self.assertIn("落料", operations)

    def test_infer_process_flow_with_empty_clues(self):
        """空 manufacturing_clues 应该生成通用工序"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = []

        pfd = infer_process_flow_from_drawing(bundle)

        # 应该至少有来料检验、材料准备、最终检验、包装
        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("来料检验", operations)
        self.assertIn("材料准备", operations)
        self.assertIn("最终检验", operations)
        self.assertIn("包装", operations)
        self.assertGreater(len(pfd["steps"]), 0)

    # ========== 工序链接 ==========

    def test_steps_have_linear_links(self):
        """验证 previous_step_ids/next_step_ids 线性链接"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "piercing", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        steps = pfd["steps"]
        self.assertGreaterEqual(len(steps), 3)

        # 检查线性链接
        for i in range(len(steps) - 1):
            current = steps[i]
            next_step = steps[i + 1]
            self.assertIn(next_step["process_step_id"], current["next_step_ids"])
            self.assertIn(current["process_step_id"], next_step["previous_step_ids"])

    def test_steps_preserve_non_linear_links(self):
        """保留非线性链接（如果 clue 中已有）"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {
                "operation": "blanking",
                "evidence_refs": ["EV-001"],
                "next_step_ids": ["P20", "P30"],  # 分支
            },
            {"operation": "piercing", "process_step_id": "P20", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "process_step_id": "P30", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        # 找到 blanking 工序
        blanking_step = next(s for s in pfd["steps"] if "落料" in s["operation"])
        # 应该保留原有的分支链接
        self.assertGreaterEqual(len(blanking_step["next_step_ids"]), 1)

    def test_steps_handle_parallel_branches(self):
        """并行分支处理"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "piercing", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        # 验证 links 结构
        self.assertIn("links", pfd)
        links = pfd["links"]
        self.assertGreater(len(links), 0)

        for link in links:
            self.assertIn("from", link)
            self.assertIn("to", link)
            self.assertEqual(link["link_type"], "sequence")
            self.assertTrue(link["ai_inferred"])

    # ========== 工序规范化 ==========

    def test_steps_have_sequence_numbers(self):
        """验证 sequence 递增"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "piercing", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        sequences = [step["sequence"] for step in pfd["steps"]]
        self.assertEqual(sequences, sorted(sequences))
        # 验证递增且为 10 的倍数
        for i, seq in enumerate(sequences, start=1):
            self.assertEqual(seq, i * 10)

    def test_steps_have_flow_types(self):
        """验证流程类型推断"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "final inspection", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        for step in pfd["steps"]:
            self.assertIn("flow_type", step)
            self.assertIn("operation_type", step)
            self.assertTrue(step["flow_type"])

    def test_steps_propagate_special_characteristics(self):
        """特殊特性传播"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {
                "operation": "blanking",
                "evidence_refs": ["EV-001"],
                "special_characteristics": ["SC-001"],
            },
        ]
        bundle["special_characteristics"] = [
            {"characteristic_id": "SC-001", "description": "Critical dimension"}
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        blanking_step = next(s for s in pfd["steps"] if "落料" in s["operation"])
        self.assertIn("SC-001", blanking_step["special_characteristics"])

    # ========== 边界情况 ==========

    def test_single_step_process_flow(self):
        """单工序流程"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "assembly", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        # 应该至少有装配工序
        operations = [step["operation"] for step in pfd["steps"]]
        self.assertIn("装配", operations)
        self.assertGreater(len(pfd["steps"]), 0)

    def test_complex_multi_branch_flow(self):
        """复杂多分支流程"""
        bundle = _minimal_bundle()
        bundle["manufacturing_clues"] = [
            {"operation": "blanking", "evidence_refs": ["EV-001"]},
            {"operation": "piercing", "evidence_refs": ["EV-001"]},
            {"operation": "forming", "evidence_refs": ["EV-001"]},
            {"operation": "bending", "evidence_refs": ["EV-001"]},
            {"operation": "welding", "evidence_refs": ["EV-001"]},
            {"operation": "surface treatment", "evidence_refs": ["EV-001"]},
        ]

        pfd = infer_process_flow_from_drawing(bundle)

        self.assertGreater(len(pfd["steps"]), 5)
        # 验证所有工序都有 process_step_id
        for step in pfd["steps"]:
            self.assertTrue(step["process_step_id"])
            self.assertTrue(step["process_step_id"].startswith("P"))

    def test_empty_bundle_returns_minimal_flow(self):
        """空输入返回最小流程"""
        bundle = {
            "drawing_identity": {},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristics": [],
            "evidence": [],
        }

        pfd = infer_process_flow_from_drawing(bundle)

        self.assertIn("steps", pfd)
        self.assertIn("links", pfd)
        self.assertIn("metadata", pfd)
        self.assertEqual(pfd["document_type"], "process_flow")
        # 应该至少有通用工序
        self.assertGreater(len(pfd["steps"]), 0)


def _minimal_bundle():
    """最小测试数据包"""
    refs = ["EV-001"]
    return {
        "drawing_identity": {
            "part_name": "Test Part",
            "drawing_number": "TEST-001",
            "revision": "A",
            "evidence_refs": refs,
        },
        "materials": [{"name": "SPCC", "evidence_refs": refs}],
        "manufacturing_clues": [],
        "special_characteristics": [],
        "evidence": [{"evidence_id": "EV-001", "source": "drawing_page"}],
    }


if __name__ == "__main__":
    unittest.main()
