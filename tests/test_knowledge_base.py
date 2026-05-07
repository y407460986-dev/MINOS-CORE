"""Tests for minos_core.knowledge_base (local knowledge base v2)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from minos_core.knowledge_base import (
    active_knowledge_items,
    load_knowledge_base,
    normalize_knowledge_item,
)
from minos_core.knowledge_recommendation import DEFAULT_KNOWLEDGE_RULES

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _write_temp_json(content: Any, suffix: str = ".json") -> str:
    """写入一个临时 JSON 文件并返回路径。"""
    fd, path = tempfile.mkstemp(suffix=suffix, text=True)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(content, fh, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class LoadKnowledgeBaseTest(unittest.TestCase):
    """Tests for load_knowledge_base."""

    def test_load_default_returns_normalized_items(self):
        """1. 默认加载返回标准化知识对象，包含 knowledge_id、category 等。"""
        items = load_knowledge_base()
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0, "默认知识库不应为空")

        required_keys = {
            "knowledge_id",
            "category",
            "process_terms",
            "characteristic_terms",
            "failure_terms",
            "special_characteristic_required",
            "requires_high_ap",
            "suggested_fields",
            "recommended_controls",
            "rating_hint",
            "risk",
            "message",
            "source",
            "version",
            "status",
            "confidence",
            "enabled",
        }
        for item in items:
            self.assertIsInstance(item, dict)
            for key in required_keys:
                self.assertIn(key, item, f"标准化条目缺少字段: {key}")

    def test_old_format_mapped_to_new_fields(self):
        """2. 旧格式 rule_id/operation_terms 映射到新字段。"""
        old_item: dict[str, Any] = {
            "rule_id": "KR-TEST-001",
            "operation_terms": ["冲孔", "piercing"],
            "requires_special_characteristic": True,
            "enabled": True,
        }
        normalized = normalize_knowledge_item(old_item)
        self.assertEqual(normalized["knowledge_id"], "KR-TEST-001")
        self.assertEqual(normalized["process_terms"], ["冲孔", "piercing"])
        self.assertTrue(normalized["special_characteristic_required"])
        self.assertEqual(normalized["status"], "active")

    def test_active_knowledge_items_filters_inactive(self):
        """3. status=inactive 或 enabled=False 被过滤。"""
        items: list[dict[str, Any]] = [
            {
                "knowledge_id": "KB-ACTIVE",
                "status": "active",
                "enabled": True,
            },
            {
                "knowledge_id": "KB-INACTIVE-STATUS",
                "status": "inactive",
                "enabled": True,
            },
            {
                "knowledge_id": "KB-DISABLED",
                "status": "active",
                "enabled": False,
            },
            {
                "knowledge_id": "KB-BOTH-BAD",
                "status": "deprecated",
                "enabled": False,
            },
        ]
        active = active_knowledge_items(items)
        active_ids = {item["knowledge_id"] for item in active}
        self.assertEqual(active_ids, {"KB-ACTIVE"})

    def test_explicit_path_missing_raises_file_not_found(self):
        """4. 显式路径不存在抛 FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            load_knowledge_base("/nonexistent/path/kb.json")

    def test_invalid_json_raises_value_error(self):
        """5. 非法 JSON 抛 ValueError。"""
        path = _write_temp_json("not valid json {{{")
        try:
            with self.assertRaises(ValueError):
                load_knowledge_base(path)
        finally:
            os.unlink(path)

    def test_empty_list_raises_value_error(self):
        """6. 空 JSON 列表抛 ValueError。"""
        path = _write_temp_json([])
        try:
            with self.assertRaises(ValueError):
                load_knowledge_base(path)
        finally:
            os.unlink(path)

    def test_category_auto_inferred(self):
        """7. category 自动推断正确。"""
        # failure_mode_pattern: 只有 failure_mode / failure_effect
        item_fm: dict[str, Any] = {
            "rule_id": "TEST-FM",
            "suggested_fields": {"failure_mode": "xxx", "failure_effect": "yyy"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_fm)["category"],
            "failure_mode_pattern",
        )

        # failure_cause_pattern: 只有 failure_cause
        item_fc: dict[str, Any] = {
            "rule_id": "TEST-FC",
            "suggested_fields": {"failure_cause": "zzz"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_fc)["category"],
            "failure_cause_pattern",
        )

        # prevention_control_pattern
        item_pc: dict[str, Any] = {
            "rule_id": "TEST-PC",
            "suggested_fields": {"prevention_control": "aaa"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_pc)["category"],
            "prevention_control_pattern",
        )

        # detection_control_pattern
        item_dc: dict[str, Any] = {
            "rule_id": "TEST-DC",
            "suggested_fields": {"detection_control": "bbb"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_dc)["category"],
            "detection_control_pattern",
        )

        # control_plan_pattern: measurement_method 等
        item_cp: dict[str, Any] = {
            "rule_id": "TEST-CP",
            "suggested_fields": {"measurement_method": "CMM"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_cp)["category"],
            "control_plan_pattern",
        )

        # rating_hint: severity / occurrence / detection
        item_rh: dict[str, Any] = {
            "rule_id": "TEST-RH",
            "suggested_fields": {"severity": 8},
        }
        self.assertEqual(
            normalize_knowledge_item(item_rh)["category"],
            "rating_hint",
        )

        # comprehensive: 多个 category 同时命中
        item_multi: dict[str, Any] = {
            "rule_id": "TEST-MULTI",
            "suggested_fields": {
                "failure_mode": "xxx",
                "prevention_control": "aaa",
            },
        }
        self.assertEqual(
            normalize_knowledge_item(item_multi)["category"],
            "comprehensive",
        )

        # comprehensive: 包含 risk 键（即使 suggested_fields 很少）
        item_risk: dict[str, Any] = {
            "rule_id": "TEST-RISK",
            "suggested_fields": {"failure_mode": "xxx"},
            "risk": {"failure_mode": "xxx"},
        }
        self.assertEqual(
            normalize_knowledge_item(item_risk)["category"],
            "comprehensive",
        )

        # 默认: 无任何匹配 → control_plan_pattern
        item_default: dict[str, Any] = {
            "rule_id": "TEST-DEFAULT",
        }
        self.assertEqual(
            normalize_knowledge_item(item_default)["category"],
            "control_plan_pattern",
        )

    def test_confidence_non_numeric_normalized_to_zero(self):
        """8. 非数字 confidence 归一为 0.0。"""
        # 字符串
        item_str: dict[str, Any] = {
            "rule_id": "TEST-STR",
            "confidence": "high",
        }
        self.assertEqual(normalize_knowledge_item(item_str)["confidence"], 0.0)

        # None
        item_none: dict[str, Any] = {
            "rule_id": "TEST-NONE",
            "confidence": None,
        }
        self.assertEqual(normalize_knowledge_item(item_none)["confidence"], 0.0)

        # 布尔值应归零（bool 是 int 子类，需要特殊处理）
        item_bool: dict[str, Any] = {
            "rule_id": "TEST-BOOL",
            "confidence": True,
        }
        self.assertEqual(normalize_knowledge_item(item_bool)["confidence"], 0.0)

        # 正常数值
        item_num: dict[str, Any] = {
            "rule_id": "TEST-NUM",
            "confidence": 0.85,
        }
        self.assertEqual(normalize_knowledge_item(item_num)["confidence"], 0.85)

        # 缺失
        item_missing: dict[str, Any] = {"rule_id": "TEST-MISSING"}
        self.assertEqual(normalize_knowledge_item(item_missing)["confidence"], 0.0)

    def test_dedup_same_knowledge_id_and_version(self):
        """9. 同 knowledge_id+version 去重，保留 confidence 较高的。"""
        path = _write_temp_json([
            {
                "rule_id": "KB-DUP",
                "version": "1.0",
                "confidence": 0.7,
                "message": "low",
            },
            {
                "rule_id": "KB-DUP",
                "version": "1.0",
                "confidence": 0.9,
                "message": "high",
            },
            {
                "rule_id": "KB-OTHER",
                "version": "1.0",
                "confidence": 0.5,
                "message": "other",
            },
        ])
        try:
            items = load_knowledge_base(path)
            ids = [it["knowledge_id"] for it in items]
            # KB-DUP 应只保留一条（confidence 0.9 的）
            self.assertEqual(ids.count("KB-DUP"), 1)
            dup_item = next(it for it in items if it["knowledge_id"] == "KB-DUP")
            self.assertEqual(dup_item["confidence"], 0.9)
            self.assertEqual(dup_item["message"], "high")
            # KB-OTHER 保留
            self.assertIn("KB-OTHER", ids)
            self.assertEqual(len(items), 2)
        finally:
            os.unlink(path)

    def test_default_missing_fallback_with_warning(self):
        """10. 默认知识库缺失时 fallback 内置规则并 warning。"""
        import minos_core.knowledge_base as kb

        original = kb._DEFAULT_KB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                kb._DEFAULT_KB_PATH = Path(tmpdir) / "nonexistent.json"
                with self.assertWarns(UserWarning) as warn_ctx:
                    items = load_knowledge_base()
                # 应发出 warning
                self.assertTrue(
                    any("不存在" in str(w.message) for w in warn_ctx.warnings),
                    f"warning 内容应包含'不存在'，实际: {[str(w.message) for w in warn_ctx.warnings]}",
                )
                # 应回退到内置种子规则
                expected_ids = {r["rule_id"] for r in DEFAULT_KNOWLEDGE_RULES}
                actual_ids = {it["knowledge_id"] for it in items}
                self.assertEqual(actual_ids, expected_ids)
                self.assertEqual(len(items), len(DEFAULT_KNOWLEDGE_RULES))
        finally:
            kb._DEFAULT_KB_PATH = original


class NormalizeEdgeCasesTest(unittest.TestCase):
    """Normalize edge cases."""

    def test_operation_terms_tuple_converted_to_list(self):
        """DEFAULT_KNOWLEDGE_RULES 使用 tuple，应转为 list。"""
        old_rule = dict(DEFAULT_KNOWLEDGE_RULES[0])  # KR-INSPECTION-GAUGE
        normalized = normalize_knowledge_item(old_rule)
        self.assertIsInstance(normalized["process_terms"], list)
        self.assertEqual(
            normalized["process_terms"],
            ["检验", "inspection", "check", "verify"],
        )

    def test_enabled_false_maps_to_inactive(self):
        """enabled=False 时 status="inactive"。"""
        item: dict[str, Any] = {"rule_id": "TEST-DISABLED", "enabled": False}
        normalized = normalize_knowledge_item(item)
        self.assertEqual(normalized["status"], "inactive")

    def test_auto_knowledge_id_when_rule_id_missing(self):
        """缺失 rule_id 时自动生成 KB-AUTO-XXXX。"""
        item: dict[str, Any] = {"message": "no rule_id"}
        normalized = normalize_knowledge_item(item, index=7)
        self.assertEqual(normalized["knowledge_id"], "KB-AUTO-0007")

    def test_source_defaults_to_local_seed(self):
        """source 缺失时默认为 local_seed。"""
        item: dict[str, Any] = {"rule_id": "TEST-SRC"}
        normalized = normalize_knowledge_item(item)
        self.assertEqual(normalized["source"], "local_seed")

    def test_version_defaults_to_1_0(self):
        """version 缺失时默认为 1.0。"""
        item: dict[str, Any] = {"rule_id": "TEST-VER"}
        normalized = normalize_knowledge_item(item)
        self.assertEqual(normalized["version"], "1.0")

    def test_normalized_items_from_json_have_source(self):
        """从 JSON 加载的条目保留原始 source。"""
        rules = load_knowledge_base()
        for item in rules:
            self.assertTrue(
                item["source"], f"source 不应为空: {item['knowledge_id']}"
            )

    def test_active_knowledge_items_excludes_deprecated(self):
        """status 不是 active 时被过滤。"""
        items: list[dict[str, Any]] = [
            {"knowledge_id": "K1", "status": "active", "enabled": True},
            {"knowledge_id": "K2", "status": "deprecated", "enabled": True},
        ]
        active = active_knowledge_items(items)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["knowledge_id"], "K1")

    def test_load_default_v2_rules_all_active(self):
        """默认加载的 V2 扩展规则全部为 active。"""
        items = load_knowledge_base()
        self.assertGreaterEqual(len(items), 58)
        self.assertEqual(len({item["knowledge_id"] for item in items}), len(items))
        active = active_knowledge_items(items)
        self.assertEqual(len(active), len(items))
        ids = {item["knowledge_id"] for item in items}
        self.assertIn("KR-STAMPING-HOLE-DIMENSION-001", ids)
        self.assertIn("KR-HIGH-AP-REACTION-015", ids)

    def test_category_enum_valid(self):
        """所有标准化条目的 category 都在枚举值内。"""
        from minos_core.knowledge_base import _CATEGORY_VALUES

        items = load_knowledge_base()
        for item in items:
            self.assertIn(
                item["category"],
                _CATEGORY_VALUES,
                f"{item['knowledge_id']} 的 category 无效: {item['category']}",
            )

    def test_normalize_empty_item_produces_valid_structure(self):
        """完全空的输入也产生合法的标准化结构。"""
        normalized = normalize_knowledge_item({})
        self.assertTrue(normalized["knowledge_id"].startswith("KB-AUTO-"))
        self.assertEqual(normalized["category"], "control_plan_pattern")
        self.assertEqual(normalized["status"], "active")
        self.assertEqual(normalized["confidence"], 0.0)
        self.assertEqual(normalized["process_terms"], [])


if __name__ == "__main__":
    unittest.main()
