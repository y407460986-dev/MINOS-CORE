"""Tests for minos_core.live_linkage -- live edit events, preview, and sync patch."""

import unittest

from minos_core.live_linkage import (
    build_live_edit_events,
    preview_live_linkage_impacts,
    build_live_sync_patch,
)
from minos_core.edit_patch import EDIT_PATCH_VERSION


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_payload(steps=None, pfmea=None, control_plan=None):
    payload = {}
    if steps is not None:
        payload["process_flow"] = {"steps": steps}
    if pfmea is not None:
        payload["pfmea"] = {"rows": pfmea}
    if control_plan is not None:
        payload["control_plan"] = {"rows": control_plan}
    return payload


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

P10 = {
    "process_step_id": "P10",
    "operation": "冲孔",
    "process_function": "按图纸冲孔",
    "product_characteristics": ["孔径"],
    "process_characteristics": ["冲压力"],
    "special_characteristics": ["SC-HOLE"],
    "characteristic_refs": ["SC-HOLE"],
}

P20 = {
    "process_step_id": "P20",
    "operation": "铆接",
    "process_function": "装配铆钉",
    "product_characteristics": [],
    "process_characteristics": [],
    "special_characteristics": [],
    "characteristic_refs": [],
}

PFMEA_10 = {
    "pfmea_id": "PFMEA-P10-001",
    "process_step_id": "P10",
    "operation": "冲孔",
    "process_function": "按图纸冲孔",
    "failure_mode": "孔径超差",
    "failure_effect": "装配不良",
    "failure_cause": "冲头磨损",
    "severity": 8,
    "occurrence": 4,
    "detection": 5,
    "action_priority": "M",
    "prevention_control": "首件检查",
    "detection_control": "通止规",
    "characteristic_refs": ["SC-HOLE"],
}

PFMEA_20 = {
    "pfmea_id": "PFMEA-P20-001",
    "process_step_id": "P20",
    "operation": "铆接",
    "process_function": "装配铆钉",
    "failure_mode": "铆接松动",
    "failure_effect": "异响",
    "failure_cause": "压力不足",
    "severity": 9,
    "occurrence": 3,
    "detection": 4,
    "action_priority": "H",
    "prevention_control": "压力监控",
    "detection_control": "拉力测试",
    "characteristic_refs": [],
}

CP_10 = {
    "control_plan_id": "CP-P10-001",
    "pfmea_id": "PFMEA-P10-001",
    "process_step_id": "P10",
    "product_process_characteristic": "孔径",
    "specification": "10+/-0.1",
    "measurement_method": "通止规",
    "sample_frequency": "首件",
    "reaction_plan": "隔离调整",
}

CP_20 = {
    "control_plan_id": "CP-P20-001",
    "pfmea_id": "PFMEA-P20-001",
    "process_step_id": "P20",
    "product_process_characteristic": "铆接力",
    "specification": ">=500N",
    "measurement_method": "拉力机",
    "sample_frequency": "每批",
    "reaction_plan": "调整压力",
}


# ===================================================================
# LiveEditEventsTests (3 tests)
# ===================================================================

class LiveEditEventsTests(unittest.TestCase):

    def test_pfd_update_generates_event(self):
        """修改 PFD operation 生成 update event"""
        before = _make_payload(steps=[P10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"operation": "冲孔（改）"}}],
        }
        events = build_live_edit_events(before, patch)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "update")
        self.assertEqual(events[0]["source_table"], "process_flow")
        self.assertIn("operation", events[0]["changed_fields"])

    def test_confirm_action_no_sync_event(self):
        """confirm 不产生同步事件"""
        before = _make_payload(steps=[P10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "confirm", "table": "process_flow", "target_id": "P10"}],
        }
        events = build_live_edit_events(before, patch)
        self.assertEqual(len(events), 0)

    def test_empty_patch_no_events(self):
        """空 patch（只有 metadata action）不产生事件"""
        before = _make_payload(steps=[P10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "accept_recommendation", "table": "metadata", "target_id": "KR-1"}],
        }
        events = build_live_edit_events(before, patch)
        self.assertEqual(len(events), 0)


# ===================================================================
# LiveLinkagePreviewTests (6 tests)
# ===================================================================

class LiveLinkagePreviewTests(unittest.TestCase):

    def test_pfd_update_previews_pfmea_impact(self):
        """修改 PFD operation 预览 PFMEA/CP 受影响"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10], control_plan=[CP_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"operation": "冲孔（改）"}}],
        }
        result = preview_live_linkage_impacts(before, patch)
        self.assertGreaterEqual(len(result["impacts"]), 1)
        pfmea_impacts = [i for i in result["impacts"] if i["target_table"] == "pfmea"]
        self.assertGreaterEqual(len(pfmea_impacts), 1)
        self.assertEqual(pfmea_impacts[0]["recommended_action"], "sync_inherited_fields")

    def test_pfd_soft_delete_previews_blocker(self):
        """删除有下游 PFMEA 的 PFD 预览 blocker"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "soft_delete", "table": "process_flow", "target_id": "P10"}],
        }
        result = preview_live_linkage_impacts(before, patch)
        blockers = [i for i in result["impacts"] if i["severity"] == "blocker"]
        self.assertGreaterEqual(len(blockers), 1)

    def test_pfd_add_previews_pfmea_stub(self):
        """新增 PFD 预览建议新增 PFMEA"""
        before = _make_payload(steps=[P10])
        new_step = {"process_step_id": "P30", "operation": "检验", "process_function": "终检", "special_characteristics": []}
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "add", "table": "process_flow", "target_id": "P30", "row": new_step}],
        }
        result = preview_live_linkage_impacts(before, patch)
        stub_impacts = [i for i in result["impacts"] if i["recommended_action"] == "create_pfmea_stub"]
        self.assertGreaterEqual(len(stub_impacts), 1)

    def test_pfmea_high_ap_add_previews_cp_stub(self):
        """新增 AP=H PFMEA 预览建议新增 CP"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        new_pfmea = {"pfmea_id": "PFMEA-P10-002", "process_step_id": "P10", "failure_mode": "毛刺",
                     "severity": 9, "action_priority": "H"}
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "add", "table": "pfmea", "target_id": "PFMEA-P10-002", "row": new_pfmea}],
        }
        result = preview_live_linkage_impacts(before, patch)
        stub_impacts = [i for i in result["impacts"] if i["recommended_action"] == "create_cp_stub"]
        self.assertGreaterEqual(len(stub_impacts), 1)

    def test_pfmea_soft_delete_previews_blocker(self):
        """删除有 CP 的 PFMEA 预览 blocker"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10], control_plan=[CP_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "soft_delete", "table": "pfmea", "target_id": "PFMEA-P10-001"}],
        }
        result = preview_live_linkage_impacts(before, patch)
        blockers = [i for i in result["impacts"] if i["severity"] == "blocker"]
        self.assertGreaterEqual(len(blockers), 1)

    def test_cp_update_no_upstream_impact(self):
        """修改 CP 不产生上游 PFMEA/PFD 影响"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10], control_plan=[CP_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "control_plan", "target_id": "CP-P10-001",
                        "changes": {"measurement_method": "CMM"}}],
        }
        result = preview_live_linkage_impacts(before, patch)
        # CP update shouldn't impact pfmea or process_flow
        upstream = [i for i in result["impacts"] if i["target_table"] in ("pfmea", "process_flow")]
        self.assertEqual(len(upstream), 0)


# ===================================================================
# LiveSyncPatchTests (6 tests)
# ===================================================================

class LiveSyncPatchTests(unittest.TestCase):

    def test_build_sync_patch_for_inherited_fields(self):
        """sync_inherited_fields 生成 update items"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"operation": "冲孔（改）"}}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "sync_inherited_fields"]
        self.assertGreater(len(impact_ids), 0)

        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        self.assertGreater(len(sync_patch["items"]), 0)
        self.assertEqual(sync_patch["edit_patch_version"], EDIT_PATCH_VERSION)

    def test_build_sync_patch_for_pfmea_stub(self):
        """create_pfmea_stub 生成 add item"""
        before = _make_payload(steps=[P10])
        new_step = {"process_step_id": "P30", "operation": "检验", "process_function": "终检", "special_characteristics": []}
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "add", "table": "process_flow", "target_id": "P30", "row": new_step}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "create_pfmea_stub"]
        self.assertGreater(len(impact_ids), 0)

        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        add_items = [it for it in sync_patch["items"] if it["action"] == "add" and it["table"] == "pfmea"]
        self.assertGreaterEqual(len(add_items), 1)
        self.assertEqual(add_items[0]["row"]["review_status"], "联动新增")
        self.assertEqual(add_items[0]["row"]["needs_confirmation"], True)

    def test_build_sync_patch_for_cp_stub(self):
        """create_cp_stub 生成 add item"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        new_pfmea = {"pfmea_id": "PFMEA-P10-002", "process_step_id": "P10", "failure_mode": "毛刺",
                     "severity": 9, "action_priority": "H"}
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "add", "table": "pfmea", "target_id": "PFMEA-P10-002", "row": new_pfmea}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "create_cp_stub"]
        self.assertGreater(len(impact_ids), 0)

        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        add_items = [it for it in sync_patch["items"] if it["action"] == "add" and it["table"] == "control_plan"]
        self.assertGreaterEqual(len(add_items), 1)

    def test_sync_patch_items_have_linkage_metadata(self):
        """同步 item 带 linkage metadata"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"operation": "冲孔（改）"}}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "sync_inherited_fields"]
        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        for item in sync_patch["items"]:
            self.assertEqual(item.get("source"), "live_linkage")
            self.assertIn("linkage_impact_id", item)

    def test_sync_patch_sets_needs_confirmation_on_downstream(self):
        """同步后下游行 needs_confirmation=True"""
        before = _make_payload(steps=[P10], pfmea=[PFMEA_10])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"operation": "冲孔（改）"}}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "sync_inherited_fields"]
        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        for item in sync_patch["items"]:
            if item["action"] == "update":
                self.assertTrue(item.get("needs_confirmation", False) or
                              item.get("review_status") == "联动同步")

    def test_sync_patch_does_not_overwrite_filled_fields(self):
        """人工已填字段不被覆盖"""
        # Create before with PFMEA that has a manually filled failure_mode
        custom_pfmea = dict(PFMEA_10)
        custom_pfmea["failure_mode"] = "人工填写的失效模式"
        before = _make_payload(steps=[P10], pfmea=[custom_pfmea])
        patch = {
            "edit_patch_version": EDIT_PATCH_VERSION,
            "items": [{"action": "update", "table": "process_flow", "target_id": "P10",
                        "changes": {"process_function": "新过程功能"}}],
        }
        preview = preview_live_linkage_impacts(before, patch)
        impact_ids = [i["impact_id"] for i in preview["impacts"] if i["recommended_action"] == "sync_inherited_fields"]
        sync_patch = build_live_sync_patch(before, patch, impact_ids)
        for item in sync_patch["items"]:
            if item["action"] == "update" and item["table"] == "pfmea":
                changes = item.get("changes", {})
                # Should NOT overwrite the existing failure_mode
                self.assertNotIn("failure_mode", changes)


if __name__ == "__main__":
    unittest.main()
