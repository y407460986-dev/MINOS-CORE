import copy
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.quality_gates import evaluate_stage_gate
from minos_core.review_patch import (
    REVIEW_PATCH_VERSION,
    ReviewPatchError,
    apply_review_patch,
    build_review_patch_template,
)


ROOT_FIXTURE = str(Path(__file__).parent / "fixtures" / "apqp_chain")


def _fixture():
    return load_fixture_payload(ROOT_FIXTURE)


class ReviewPatchTests(unittest.TestCase):
    def test_review_patch_confirms_evidence_and_rows_for_formal_export(self):
        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        payload["process_flow"]["steps"][0]["needs_confirmation"] = True
        payload["pfmea"]["rows"][0]["needs_confirmation"] = True
        payload["control_plan"]["rows"][0]["needs_confirmation"] = True
        payload["ai_inferred_items"] = ["PFMEA-P10-001", "CP-P10-001"]
        payload["pfmea"]["ai_inferred_items"] = ["PFMEA-P10-001"]
        payload["control_plan"]["ai_inferred_items"] = ["CP-P10-001"]

        before = evaluate_stage_gate(payload, stage="export")
        self.assertFalse(before.allow_user_export)
        self.assertIn("process_step:P10", before.needs_confirmation_items)
        self.assertIn("failure_mode:PFMEA-P10-001", before.needs_confirmation_items)
        self.assertIn("control_item:CP-P10-001", before.needs_confirmation_items)
        self.assertTrue(any("EV-PFD-ROUTE-001" in item for item in before.needs_confirmation_items))

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "confirmed_by": "qa.engineer",
                "confirmed_at": "2026-04-25T10:00:00Z",
                "reason": "人工复核已确认这些 draft 项可以正式放行",
                "evidence_refs": ["EV-PFD-ROUTE-001"],
                "items": [
                    {"action": "confirm", "target": "evidence:EV-PFD-ROUTE-001"},
                    {"action": "confirm", "target": "process_step:P10"},
                    {"action": "confirm", "target": "failure_mode:PFMEA-P10-001"},
                    {"action": "confirm", "target": "control_item:CP-P10-001"},
                ],
            },
        )

        self.assertTrue(payload["evidence"][0]["needs_confirmation"])
        self.assertFalse(updated["evidence"][0]["needs_confirmation"])
        self.assertFalse(updated["process_flow"]["steps"][0]["needs_confirmation"])
        self.assertFalse(updated["pfmea"]["rows"][0]["needs_confirmation"])
        self.assertFalse(updated["control_plan"]["rows"][0]["needs_confirmation"])
        self.assertNotIn("PFMEA-P10-001", updated["ai_inferred_items"])
        self.assertNotIn("CP-P10-001", updated["ai_inferred_items"])
        self.assertEqual(updated["pfmea"]["ai_inferred_items"], [])
        self.assertEqual(updated["control_plan"]["ai_inferred_items"], [])
        self.assertEqual(
            len(updated["metadata"]["review_confirmations"]),
            4,
        )
        self.assertEqual(
            updated["metadata"]["review_confirmations"][0]["confirmed_by"],
            "qa.engineer",
        )

        after = evaluate_stage_gate(updated, stage="export")
        self.assertTrue(after.can_continue)
        self.assertTrue(after.allow_user_export)
        self.assertEqual(after.needs_confirmation_items, [])

    def test_review_patch_corrects_pending_field_and_records_basis(self):
        payload = _fixture()
        payload["control_plan"]["rows"][0]["specification"] = ""
        payload["pending_fields"] = [
            {"source_ref": "CP-P10-001", "field": "specification"},
            "control_item:CP-P10-001.specification",
        ]

        before = evaluate_stage_gate(payload, stage="export")
        self.assertFalse(before.allow_user_export)
        self.assertIn("CP-P10-001.specification", before.pending_fields)

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "correct",
                        "target": "pending_field:CP-P10-001.specification",
                        "value": "2.00 +/- 0.10 mm",
                        "confirmed_by": "quality.lead",
                        "confirmed_at": "2026-04-25T11:00:00Z",
                        "reason": "按已存在工程要求证据补齐规格",
                        "evidence_refs": ["EV-ENG-REQ-001"],
                    }
                ],
            },
        )

        self.assertEqual(
            updated["control_plan"]["rows"][0]["specification"],
            "2.00 +/- 0.10 mm",
        )
        self.assertEqual(updated["pending_fields"], [])
        record = updated["metadata"]["review_confirmations"][0]
        self.assertEqual(record["target"], "pending_field:CP-P10-001.specification")
        self.assertEqual(record["field_path"], "CP-P10-001.specification")
        self.assertEqual(record["evidence_refs"], ["EV-ENG-REQ-001"])

        after = evaluate_stage_gate(updated, stage="export")
        self.assertTrue(after.allow_user_export)
        self.assertNotIn("CP-P10-001.specification", after.pending_fields)

    def test_review_patch_rejects_missing_evidence_reference(self):
        payload = _fixture()

        with self.assertRaises(ReviewPatchError):
            apply_review_patch(
                payload,
                {
                    "review_patch_version": REVIEW_PATCH_VERSION,
                    "confirmed_by": "qa.engineer",
                    "confirmed_at": "2026-04-25T12:00:00Z",
                    "reason": "invalid evidence should fail fast",
                    "items": [
                        {
                            "action": "confirm",
                            "target": "process_step:P10",
                            "evidence_refs": ["EV-DOES-NOT-EXIST"],
                        }
                    ],
                },
            )

    def test_review_patch_allows_explicit_manual_confirmation_event(self):
        payload = _fixture()
        payload["pfmea"]["rows"][0]["needs_confirmation"] = True

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "confirm",
                        "target": "failure_mode:PFMEA-P10-001",
                        "confirmed_by": "manufacturing.engineer",
                        "confirmed_at": "2026-04-25T13:00:00Z",
                        "reason": "现场评审会议确认该 PFMEA 行",
                        "manual_confirmation_event": "MRB-2026-04-25-001",
                    }
                ],
            },
        )

        self.assertFalse(updated["pfmea"]["rows"][0]["needs_confirmation"])
        record = updated["metadata"]["review_confirmations"][0]
        self.assertEqual(record["manual_confirmation_event"], "MRB-2026-04-25-001")

    def test_review_template_lists_review_items_without_auto_confirmation(self):
        payload = _fixture()
        payload["control_plan"]["rows"][0]["specification"] = ""
        payload["pending_fields"] = ["control_item:CP-P10-001.specification"]
        payload["evidence"][0]["needs_confirmation"] = True
        payload["evidence"].append(
            {
                "evidence_id": "EV-AI-001",
                "source": "llm",
                "content": "AI inferred risk for manual review only.",
                "confidence": 0.5,
                "ai_inferred": True,
                "needs_confirmation": True,
            }
        )
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }

        template = build_review_patch_template(draft_result)

        self.assertEqual(template["review_patch_version"], REVIEW_PATCH_VERSION)
        self.assertEqual(
            template["template_status"],
            "requires_human_review_before_apply_review",
        )
        self.assertEqual(template["confirmed_by"], "")
        self.assertEqual(template["confirmed_at"], "")
        self.assertEqual(template["reason"], "")
        targets = {item["target"] for item in template["items"]}
        categories = {item["review_category"] for item in template["items"]}
        self.assertIn("pending_field:CP-P10-001.specification", targets)
        self.assertIn("evidence:EV-PFD-ROUTE-001", targets)
        self.assertIn("evidence:EV-AI-001", targets)
        self.assertIn("pending_field", categories)
        self.assertIn("needs_confirmation", categories)
        self.assertIn("ai_inferred_manual_review", categories)
        for item in template["items"]:
            self.assertEqual(item["confirmed_by"], "")
            self.assertEqual(item["confirmed_at"], "")
            self.assertEqual(item["reason"], "")
            self.assertEqual(item["evidence_refs"], [])

    def test_review_patch_populates_change_impacts_after_correction(self):
        """Applying a PFMEA correction should run impact analysis and populate metadata.change_impacts."""
        payload = _fixture()
        # Pre-set conditions that trigger PFMEA 控制/特性修改 impact:
        #   - review_status == "人工修改"
        #   - prevention_control in changed_fields
        payload["pfmea"]["rows"][0]["review_status"] = "人工修改"
        payload["pfmea"]["rows"][0]["changed_fields"] = ["prevention_control"]

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "correct",
                        "target": "failure_mode:PFMEA-P10-001",
                        "field": "prevention_control",
                        "value": "修订后的预防控制措施",
                        "confirmed_by": "qa.engineer",
                        "confirmed_at": "2026-04-25T10:00:00Z",
                        "reason": "现场审核后修订预防控制",
                        "evidence_refs": ["EV-ENG-REQ-001"],
                    }
                ],
            },
        )

        self.assertIn("metadata", updated)
        self.assertIn("change_impacts", updated["metadata"])
        impacts = updated["metadata"]["change_impacts"]
        self.assertIsInstance(impacts, list)
        self.assertTrue(
            any(
                "pfmea" in impact.get("target", "")
                and "CP" in impact.get("message", "")
                for impact in impacts
            ),
            f"Expected change impact about PFMEA->CP sync, got: {impacts}",
        )

    def test_review_patch_deduplicates_change_impacts_by_item_id(self):
        """Pre-existing change_impacts should be preserved and new ones merged without duplicates."""
        payload = _fixture()
        existing_impact = {
            "item_id": "pfmea:PFMEA-P10-001.PFMEA 控制/特性修改.CP 控制方法需同步确认",
            "category": "变更影响",
            "target": "pfmea:PFMEA-P10-001",
            "message": "CP 控制方法需同步确认",
            "status": "已处理",
            "ignore_reason": "",
            "severity": "blocker",
        }
        payload.setdefault("metadata", {})["change_impacts"] = [existing_impact]
        payload["pfmea"]["rows"][0]["review_status"] = "人工修改"
        payload["pfmea"]["rows"][0]["changed_fields"] = ["prevention_control"]

        updated = apply_review_patch(
            payload,
            {
                "review_patch_version": REVIEW_PATCH_VERSION,
                "items": [
                    {
                        "action": "correct",
                        "target": "failure_mode:PFMEA-P10-001",
                        "field": "prevention_control",
                        "value": "修订后的预防控制措施",
                        "confirmed_by": "qa.engineer",
                        "confirmed_at": "2026-04-25T10:00:00Z",
                        "reason": "现场审核后修订预防控制",
                        "evidence_refs": ["EV-ENG-REQ-001"],
                    }
                ],
            },
        )

        impacts = updated["metadata"]["change_impacts"]
        # Original entry with status "已处理" must be preserved, not overwritten
        self.assertIn(existing_impact, impacts)
        self.assertEqual(
            1,
            sum(
                1
                for ci in impacts
                if ci.get("item_id") == existing_impact["item_id"]
            ),
            f"Impacts should be deduplicated by item_id: {impacts}",
        )

    def test_review_template_cannot_be_applied_without_human_completion(self):
        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }
        template = build_review_patch_template(draft_result)

        with self.assertRaisesRegex(ReviewPatchError, "templates must be completed"):
            apply_review_patch(payload, template)

    def test_review_template_cli_writes_template_file(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        payload = _fixture()
        payload["evidence"][0]["needs_confirmation"] = True
        draft_result = {
            "document_type": "apqp_chain_draft_result",
            "status": "draft_ready",
            "draft": payload,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            draft_path = tmp_path / "draft_result.json"
            output_path = tmp_path / "review_patch_template.json"
            draft_path.write_text(
                json.dumps(draft_result, ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "minos_core.cli",
                    "review-template",
                    "--draft-result",
                    str(draft_path),
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            template = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(template["review_patch_version"], REVIEW_PATCH_VERSION)
            self.assertIn(
                "requires_human_review_before_apply_review",
                output_path.read_text(encoding="utf-8"),
            )


class AiInferredAggregateTargetTests(unittest.TestCase):
    def test_confirm_ai_inferred_aggregate_target_clears_items(self):
        """确认 ai_inferred_item:control_plan 能清除所有容器中的 control_plan。"""
        payload = {
            "document_type": "apqp_chain",
            "ai_inferred_items": ["control_plan", "process_flow"],
            "process_steps": [],
            "failure_modes": [],
            "controls": [],
            "evidence": [{"evidence_id": "EV-1", "content": "测试"}],
            "links": [],
            "metadata": {},
            "control_plan": {"ai_inferred_items": ["control_plan"]},
        }
        patch = {
            "review_patch_version": REVIEW_PATCH_VERSION,
            "confirmed_by": "test",
            "confirmed_at": "2026-04-28T10:00:00Z",
            "items": [{
                "action": "confirm",
                "target": "ai_inferred_item:control_plan",
                "reason": "人工确认控制计划AI推断项",
                "evidence_refs": ["EV-1"],
            }],
        }
        result = apply_review_patch(payload, patch)

        # 顶层 control_plan 已被移除
        self.assertNotIn("control_plan", result.get("ai_inferred_items", []))
        # process_flow 未被影响
        self.assertIn("process_flow", result.get("ai_inferred_items", []))
        # control_plan 容器中的也被移除
        self.assertNotIn(
            "control_plan",
            result.get("control_plan", {}).get("ai_inferred_items", []),
        )
        # review_confirmations 记录了确认
        confirmations = result["metadata"]["review_confirmations"]
        self.assertEqual(len(confirmations), 1)
        self.assertEqual(confirmations[0]["target"], "ai_inferred_item:control_plan")

    def test_correct_ai_inferred_item_rejected(self):
        """ai_inferred_item 只支持 confirm，correct 应被拒绝。"""
        payload = {
            "document_type": "apqp_chain",
            "ai_inferred_items": ["control_plan"],
            "process_steps": [],
            "failure_modes": [],
            "controls": [],
            "evidence": [{"evidence_id": "EV-1", "content": "测试"}],
            "links": [],
            "metadata": {},
        }
        patch = {
            "review_patch_version": REVIEW_PATCH_VERSION,
            "confirmed_by": "test",
            "confirmed_at": "2026-04-28T10:00:00Z",
            "items": [{
                "action": "correct",
                "target": "ai_inferred_item:control_plan",
                "reason": "尝试修正",
                "evidence_refs": ["EV-1"],
                "value": "fixed",
            }],
        }
        with self.assertRaises(ReviewPatchError):
            apply_review_patch(payload, patch)

    def test_export_gate_filters_confirmed_ai_inferred_items(self):
        """确认 ai_inferred_item 后，export gate 不将其计入阻断。"""
        from minos_core.quality_gates import evaluate_export_gate

        payload = {
            "document_type": "apqp_chain",
            "ai_inferred_items": ["control_plan"],
            "process_steps": [{
                "process_step_id": "P10",
                "operation": "冲孔",
            }],
            "failure_modes": [{
                "pfmea_id": "PFMEA-P10-001",
                "process_step_id": "P10",
                "failure_mode": "孔径超差",
                "process_step": "",
                "process_item": "",
            }],
            "controls": [{
                "control_plan_id": "CP-P10-001",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-P10-001",
                "product_process_characteristic": "孔径",
                "specification": "10+/-0.1",
                "measurement_method": "CMM",
                "sample_size": "5",
                "sample_frequency": "每批",
                "control_method": "SPC",
                "reaction_plan": "隔离",
            }],
            "evidence": [{
                "evidence_id": "EV-1",
                "content": "图纸",
                "confidence": 0.9,
            }],
            "links": [{
                "trace_link_id": "TL-1",
                "from_id": "P10",
                "to_id": "PFMEA-P10-001",
                "link_type": "pfd_to_pfmea",
            }],
            "metadata": {
                "review_confirmations": [{
                    "target": "ai_inferred_item:control_plan",
                    "action": "confirm",
                    "confirmed_by": "test",
                    "confirmed_at": "2026-04-28T10:00:00Z",
                    "reason": "已确认",
                    "evidence_refs": ["EV-1"],
                }],
            },
        }
        gate = evaluate_export_gate(payload)
        # ai_inferred_items 应被过滤掉
        self.assertEqual(gate.ai_inferred_items, [])


if __name__ == "__main__":
    unittest.main()
