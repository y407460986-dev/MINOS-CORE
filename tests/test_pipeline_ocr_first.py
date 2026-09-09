from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from minos_core.adapters.ocr import OCRPageText, OCRResult
from minos_core.drawing_analysis import analyze_drawing_pages
from minos_core.pipeline import (
    HYBRID_OCR_FALLBACK_WARNING,
    HYBRID_VISION_MAX_RETRIES,
    HYBRID_VISION_TIMEOUT_SECONDS,
    _analyze_drawing_pages_for_mode,
    _effective_ocr_engine,
    generate_three_tables_from_drawing,
)


class PipelineOCRFirstTests(unittest.TestCase):
    def test_hybrid_applies_fake_special_characteristic_judge_payload(self) -> None:
        calls: dict[str, object] = {}
        evidence_module = types.ModuleType("minos_core.special_characteristics_evidence")
        judge_module = types.ModuleType("minos_core.special_characteristics_judge")

        def build_special_characteristic_evidence_packet(drawing_analysis):
            calls["drawing_analysis"] = drawing_analysis
            return {
                "packet_id": "SC-EVIDENCE-001",
                "symbol_occurrences": [
                    {"candidate_id": "MSC-001", "evidence_refs": ["drawing_page_001"]}
                ],
                "text_evidence": [
                    {"text_id": "TXT-001", "evidence_refs": ["drawing_page_001"]}
                ],
                "page_evidence_refs": ["drawing_page_001"],
            }

        def normalize_special_characteristic_judgments(payload):
            calls["judge_payload"] = payload
            return list(payload["special_characteristic_judgments"])

        def verify_special_characteristic_judgments(judgments, packet):
            calls["judgments"] = judgments
            calls["packet"] = packet
            return {
                "confirmed": [
                    {
                        **judgments[0],
                        "confirmation_status": "judge_confirmed",
                        "needs_confirmation": False,
                    }
                ],
                "risks": [
                    {
                        "risk_id": "SC-JUDGE-SCJ-REVIEW",
                        "item_id": "SC-JUDGE-SCJ-REVIEW",
                        "category": "special_characteristic_judge",
                        "severity": "review",
                        "target": "special_characteristic_judgments.SCJ-REVIEW",
                        "message": "AI 裁判结果需要人工复核。",
                    }
                ],
            }

        evidence_module.build_special_characteristic_evidence_packet = (
            build_special_characteristic_evidence_packet
        )
        judge_module.normalize_special_characteristic_judgments = (
            normalize_special_characteristic_judgments
        )
        judge_module.verify_special_characteristic_judgments = (
            verify_special_characteristic_judgments
        )
        vision = {
            "drawing_identity": {"part_name": "BRACKET"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristic_candidates": [
                {
                    "candidate_id": "MSC-001",
                    "candidate_type": "unknown",
                    "source": "visual_symbol",
                    "symbol_text_or_shape": "菱形",
                    "linked_feature": "安装孔位置度",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.94,
                }
            ],
            "technical_requirements": [
                {
                    "id": "TXT-001",
                    "text": "图例: 菱形 = CC",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
            "special_characteristic_judgments": [
                {
                    "judgment_id": "SCJ-001",
                    "candidate_id": "MSC-001",
                    "classification": "CC",
                    "verdict": "confirmed",
                    "linked_feature": "安装孔位置度",
                    "confidence": 0.91,
                    "standard_evidence_refs": ["TXT-001"],
                    "symbol_evidence_refs": ["MSC-001"],
                    "page_evidence_refs": ["drawing_page_001"],
                    "reasoning_summary": "图例说明菱形为 CC。",
                }
            ],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-REVIEW",
                        "severity": "review",
                        "message": "身份需要复核。",
                    }
                ]
            },
        }

        with patch.dict(
            sys.modules,
            {
                "minos_core.special_characteristics_evidence": evidence_module,
                "minos_core.special_characteristics_judge": judge_module,
            },
        ):
            from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

            _merge_special_characteristic_candidates(vision, {})

        self.assertEqual(
            calls["judge_payload"],
            {
                "special_characteristic_judgments": vision[
                    "special_characteristic_judgments"
                ]
            },
        )
        self.assertEqual(vision["special_characteristics"][0]["classification"], "CC")
        self.assertEqual(
            vision["special_characteristics"][0]["confirmation_status"],
            "judge_confirmed",
        )
        self.assertEqual(
            vision["special_characteristics"][0]["source_judgment_id"],
            "SCJ-001",
        )
        self.assertEqual(
            vision["special_characteristic_candidates"][0]["candidate_id"],
            "MSC-001",
        )
        risk_ids = {
            item["risk_id"]
            for item in vision["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("DRAWING-IDENTITY-REVIEW", risk_ids)
        self.assertIn("SC-JUDGE-SCJ-REVIEW", risk_ids)

    def test_hybrid_calls_injected_special_characteristic_judge_when_payload_missing(
        self,
    ) -> None:
        class FakeJudge:
            def __init__(self) -> None:
                self.packets: list[dict[str, object]] = []

            def judge(self, evidence_packet):
                self.packets.append(evidence_packet)
                return {
                    "special_characteristic_judgments": [
                        {
                            "judgment_id": "SCJ-001",
                            "candidate_id": "MSC-001",
                            "classification": "CC",
                            "verdict": "confirmed",
                            "linked_feature": "安装孔位置度",
                            "confidence": 0.91,
                            "standard_evidence_refs": ["TXT-001"],
                            "symbol_evidence_refs": ["MSC-001"],
                            "page_evidence_refs": ["drawing_page_001"],
                            "reasoning_summary": "图例说明菱形为 CC。",
                        }
                    ]
                }

        vision = {
            "drawing_identity": {"part_name": "BRACKET"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristic_candidates": [
                {
                    "candidate_id": "MSC-001",
                    "candidate_type": "unknown",
                    "source": "visual_symbol",
                    "symbol_text_or_shape": "菱形",
                    "linked_feature": "安装孔位置度",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.94,
                }
            ],
            "technical_requirements": [
                {
                    "id": "TXT-001",
                    "text": "图例: 菱形 = CC",
                    "evidence_refs": ["drawing_page_001"],
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        }
        judge = FakeJudge()

        from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

        _merge_special_characteristic_candidates(
            vision,
            {},
            special_characteristic_judge=judge,
        )

        self.assertEqual(judge.packets[0]["symbol_occurrences"][0]["candidate_id"], "MSC-001")
        self.assertEqual(vision["special_characteristic_judgments"][0]["classification"], "CC")
        self.assertEqual(vision["special_characteristics"][0]["confirmation_status"], "judge_confirmed")

    def test_hybrid_merges_gpt55_visual_locator_occurrences_into_evidence_packet(
        self,
    ) -> None:
        class FakeJudge:
            def __init__(self) -> None:
                self.packets: list[dict[str, object]] = []

            def judge(self, evidence_packet):
                self.packets.append(evidence_packet)
                return {"special_characteristic_judgments": []}

        vision = {
            "drawing_identity": {"part_name": "JLV DEMO"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristic_candidates": [],
            "special_characteristic_locations": [],
            "located_occurrences": [
                {
                    "candidate_id": "SC-REQ4-TORQUE",
                    "candidate_type": "SC",
                    "source": "gpt55_visual_locator",
                    "symbol_text_or_shape": "水平圆角长框",
                    "linked_feature": "技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm",
                    "symbol_bbox": [2050, 906, 2255, 929],
                    "evidence_refs": ["drawing_page_001", "crop_sc_req4"],
                    "confidence": 0.96,
                }
            ],
            "visual_evidence": [
                {
                    "evidence_id": "crop_sc_req4",
                    "source": "visual_crop",
                    "page_evidence_id": "drawing_page_001",
                    "metadata": {"source": "gpt55_visual_locator"},
                }
            ],
            "metadata": {
                "visual_locator": {
                    "source": "gpt55_visual_locator",
                    "declared_totals": {"CC": 2, "SC": 1},
                }
            },
        }
        ocr = {
            "declared_totals": {"CC": 2, "SC": 1},
            "special_characteristics": [],
        }
        judge = FakeJudge()

        from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

        _merge_special_characteristic_candidates(
            vision,
            ocr,
            special_characteristic_judge=judge,
        )

        self.assertEqual(
            vision["special_characteristic_candidates"][0]["candidate_id"],
            "SC-REQ4-TORQUE",
        )
        self.assertEqual(
            vision["special_characteristic_candidates"][0]["source"],
            "gpt55_visual_locator",
        )
        packet = judge.packets[0]
        self.assertEqual(packet["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            packet["symbol_occurrences"][0]["source"],
            "gpt55_visual_locator",
        )
        self.assertEqual(
            packet["symbol_occurrences"][0]["candidate_id"],
            "SC-REQ4-TORQUE",
        )
        self.assertEqual(
            vision["special_characteristic_discovery"]["missing_counts"],
            {"CC": 2, "SC": 0},
        )

    def test_hybrid_preserves_explicit_ocr_sc_as_candidate_when_vision_misses_it(self) -> None:
        vision = {
            "drawing_identity": {"part_name": "BRACKET"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristic_candidates": [
                {
                    "candidate_type": "unknown",
                    "source": "visual_symbol",
                    "linked_feature": "客户符号",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.6,
                }
            ],
            "metadata": {
                "drawing_analysis_risks": [
                    {
                        "risk_id": "DRAWING-IDENTITY-REVIEW",
                        "severity": "review",
                        "message": "身份需要复核。",
                    }
                ]
            },
        }
        ocr = {
            "special_characteristics": [
                {
                    "classification": "SC",
                    "name": "孔径 10.0 +/- 0.1 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.93,
                }
            ]
        }

        from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

        _merge_special_characteristic_candidates(vision, ocr)

        self.assertTrue(
            any(
                item["candidate_type"] == "SC" and item["source"] == "ocr_text"
                for item in vision["special_characteristic_candidates"]
            )
        )
        self.assertEqual(vision["special_characteristics"][0]["classification"], "SC")
        risk_ids = {
            item["risk_id"]
            for item in vision["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("DRAWING-IDENTITY-REVIEW", risk_ids)
        self.assertIn("SC-CANDIDATE-MSC-001", risk_ids)

    def test_ocr_summary_for_context_includes_declared_special_counts(self) -> None:
        from minos_core.pipeline.hybrid_fusion import _ocr_summary_for_context

        drawing_analysis = {
            "drawing_identity": {"part_name": "OCR 支架"},
            "materials": [],
            "dimensions": [],
            "special_characteristics": [],
            "technical_requirements": [],
            "manufacturing_clues": [],
            "declared_special_characteristics": [
                {
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["ocr_page_001"],
                },
                {
                    "classification": "SC",
                    "expected_count": 1,
                    "evidence_refs": ["ocr_page_002"],
                },
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "metadata": {"ocr_summary": {"raw_text_preview": "声明 CC=2 SC=1"}},
        }

        summary = _ocr_summary_for_context(drawing_analysis)

        self.assertEqual(summary["raw_text_preview"], "声明 CC=2 SC=1")
        self.assertEqual(summary["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            summary["declared_special_characteristics"][0]["classification"],
            "CC",
        )

    def test_hybrid_context_includes_special_characteristic_discovery_request_after_ocr(
        self,
    ) -> None:
        from minos_core.pipeline import drawing_analysis as drawing_pipeline

        captured: dict[str, object] = {}
        ocr_analysis = {
            "drawing_identity": {"part_name": "JLV DEMO", "drawing_number": "JLV03000500"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristics": [],
            "declared_special_characteristics": [
                {
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["ocr_page_001"],
                },
                {
                    "classification": "SC",
                    "expected_count": 1,
                    "evidence_refs": ["ocr_page_001"],
                },
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "evidence": [{"evidence_id": "ocr_page_001", "source": "ocr_page"}],
            "metadata": {},
        }

        def fake_vision_analysis(pages, analyzer, context):
            captured["vision_context"] = dict(context)
            return {
                "drawing_identity": {"part_name": "JLV DEMO"},
                "materials": [],
                "manufacturing_clues": [],
                "special_characteristic_candidates": [],
                "special_characteristic_locations": [],
                "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
                "metadata": {},
            }

        with patch(
            "minos_core.pipeline.drawing_analysis._run_ocr_drawing_analysis",
            return_value=ocr_analysis,
        ):
            analysis, warnings, source, errors = drawing_pipeline._analyze_drawing_pages_for_mode(
                source={"path": "drawing.png"},
                pages=[_page_evidence()],
                target_dir=Path("out"),
                context_payload={},
                analysis_mode="hybrid",
                ocr_engine="rapidocr",
                ocr_adapter=None,
                analyzer=object(),
                default_analyzer_factory=object,
                analyze_drawing_pages=fake_vision_analysis,
            )

        request = captured["vision_context"]["special_characteristic_discovery_request"]
        self.assertEqual(source, "hybrid_vision")
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])
        self.assertEqual(request["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            request["declared_special_characteristics"][1]["classification"],
            "SC",
        )
        self.assertEqual(analysis["declared_totals"], {"CC": 2, "SC": 1})

    def test_hybrid_fallback_keeps_declared_counts_and_missing_risk_when_vision_fails(
        self,
    ) -> None:
        ocr_analysis = {
            "drawing_identity": {"part_name": "JLV DEMO", "drawing_number": "JLV03000500"},
            "materials": [{"name": "SPCC", "evidence_refs": ["ocr_page_001"]}],
            "manufacturing_clues": [{"operation": "装配", "evidence_refs": ["ocr_page_001"]}],
            "special_characteristics": [],
            "declared_special_characteristics": [
                {
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["ocr_page_001"],
                },
                {
                    "classification": "SC",
                    "expected_count": 1,
                    "evidence_refs": ["ocr_page_001"],
                },
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "special_characteristic_candidates": [],
            "evidence": [{"evidence_id": "ocr_page_001", "source": "ocr_page"}],
            "metadata": {},
        }

        from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

        _merge_special_characteristic_candidates(
            ocr_analysis,
            ocr_analysis,
            context={},
        )

        self.assertEqual(ocr_analysis["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            ocr_analysis["special_characteristic_discovery"]["missing_counts"],
            {"CC": 2, "SC": 1},
        )
        risk_ids = {
            item["risk_id"]
            for item in ocr_analysis["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("SC-DISCOVERY-MISSING-CC", risk_ids)
        self.assertIn("SC-DISCOVERY-MISSING-SC", risk_ids)

    def test_hybrid_merge_keeps_positive_visual_declared_counts_when_ocr_has_zero_counts(
        self,
    ) -> None:
        from minos_core.pipeline.hybrid_fusion import _merge_special_characteristic_candidates

        vision_analysis = {
            "drawing_identity": {"part_name": "JLV DEMO"},
            "materials": [],
            "manufacturing_clues": [],
            "special_characteristic_candidates": [],
            "special_characteristic_locations": [],
            "declared_special_characteristics": [
                {
                    "classification": "CC",
                    "expected_count": 2,
                    "source": "gpt55_visual_locator",
                    "evidence_refs": ["drawing_page_001"],
                },
                {
                    "classification": "SC",
                    "expected_count": 1,
                    "source": "gpt55_visual_locator",
                    "evidence_refs": ["drawing_page_001"],
                },
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "metadata": {},
        }
        ocr_analysis = {
            "declared_special_characteristics": [],
            "declared_totals": {"CC": 0, "SC": 0},
            "special_characteristics": [],
        }

        _merge_special_characteristic_candidates(
            vision_analysis,
            ocr_analysis,
            context={},
        )

        self.assertEqual(vision_analysis["declared_totals"], {"CC": 2, "SC": 1})
        self.assertEqual(
            vision_analysis["special_characteristic_discovery"]["missing_counts"],
            {"CC": 2, "SC": 1},
        )
        risk_ids = {
            item["risk_id"]
            for item in vision_analysis["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("SC-DISCOVERY-MISSING-CC", risk_ids)
        self.assertIn("SC-DISCOVERY-MISSING-SC", risk_ids)

    def test_hybrid_vision_failure_fallback_adds_declared_missing_risks(
        self,
    ) -> None:
        from minos_core.pipeline import drawing_analysis as drawing_pipeline

        captured: dict[str, object] = {}
        ocr_analysis = {
            "drawing_identity": {"part_name": "JLV DEMO", "drawing_number": "JLV03000500"},
            "materials": [{"name": "SPCC", "evidence_refs": ["ocr_page_001"]}],
            "manufacturing_clues": [{"operation": "装配", "evidence_refs": ["ocr_page_001"]}],
            "special_characteristics": [],
            "declared_special_characteristics": [
                {
                    "classification": "CC",
                    "expected_count": 2,
                    "evidence_refs": ["ocr_page_001"],
                },
                {
                    "classification": "SC",
                    "expected_count": 1,
                    "evidence_refs": ["ocr_page_001"],
                },
            ],
            "declared_totals": {"CC": 2, "SC": 1},
            "special_characteristic_candidates": [],
            "evidence": [{"evidence_id": "ocr_page_001", "source": "ocr_page"}],
            "metadata": {},
        }

        with patch(
            "minos_core.pipeline.drawing_analysis._run_ocr_drawing_analysis",
            return_value=ocr_analysis,
        ):
            analysis, warnings, source, errors = drawing_pipeline._analyze_drawing_pages_for_mode(
                source={"path": "drawing.png"},
                pages=[_page_evidence()],
                target_dir=Path("out"),
                context_payload={},
                analysis_mode="hybrid",
                ocr_engine="rapidocr",
                ocr_adapter=None,
                analyzer=_FailingAnalyzer(captured),
                default_analyzer_factory=lambda: _FailingAnalyzer(captured),
                analyze_drawing_pages=analyze_drawing_pages,
            )

        self.assertEqual(source, "hybrid_ocr_fallback")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, warnings)
        self.assertEqual(errors[-1]["stage"], "vision")
        self.assertEqual(analysis["declared_totals"], {"CC": 2, "SC": 1})
        risk_ids = {
            item["risk_id"]
            for item in analysis["metadata"]["drawing_analysis_risks"]
        }
        self.assertIn("SC-DISCOVERY-MISSING-CC", risk_ids)
        self.assertIn("SC-DISCOVERY-MISSING-SC", risk_ids)

    def test_hybrid_uses_ocr_manufacturing_clues_when_vision_has_none(self) -> None:
        vision = {
            "drawing_identity": {"part_name": "BRACKET"},
            "manufacturing_clues": [],
            "metadata": {},
        }
        ocr = {
            "manufacturing_clues": [
                {
                    "operation": "deburr",
                    "process_function": "OCR text mentions no burrs",
                    "evidence_refs": ["ocr_page_001_block_0026"],
                    "confidence": 0.89,
                }
            ]
        }

        from minos_core.pipeline.hybrid_fusion import _merge_ocr_manufacturing_clues_if_needed

        _merge_ocr_manufacturing_clues_if_needed(vision, ocr)

        self.assertEqual(vision["manufacturing_clues"][0]["operation"], "deburr")
        self.assertTrue(vision["manufacturing_clues"][0]["needs_confirmation"])
        self.assertTrue(vision["metadata"]["ocr_manufacturing_clues_used"])

    def test_hybrid_returns_ocr_draft_when_vision_fails(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline(
                tmpdir,
                analysis_mode="hybrid",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        error_text = " ".join(
            item["message"]
            for item in result["drawing_analysis"]["metadata"]["analysis_errors"]
        )
        self.assertIn("AI 视觉识别中断，已保留 OCR 识别结果。", error_text)
        self.assertIn("stream_read_error", error_text)
        self.assertIn("ocr_analysis_summary", captured["vision_context"])
        self.assertEqual(captured["ocr_engine"], "rapidocr")
        self.assertIsInstance(captured["ocr_adapter"], _FakeOCRAdapter)
        self.assertEqual(result["process_flow"]["steps"][0]["operation"], "来料检验")

    def test_ocr_only_enters_three_table_chain_without_vision(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline(
                tmpdir,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertNotEqual(result["blocked_stage"], "drawing_recognition")
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "ocr",
        )
        self.assertNotIn("vision_context", captured)
        self.assertEqual(result["drawing_analysis"]["drawing_identity"]["part_name"], "OCR 支架")

    def test_ocr_only_uses_real_ocr_entrypoint_and_blocks_final_export(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
                export_mode="final",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked_stage"], "final_three_table")
        self.assertEqual(result["exports"], {})
        self.assertIn("最终三表质量门未通过，已阻止正式导出。", result["warnings"])
        self.assertEqual(result["drawing_analysis"]["metadata"]["analysis_source"], "ocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "rapidocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr"]["engine"], "unit_ocr")
        self.assertGreater(result["manual_review"]["raw_count"], 0)

    def test_hybrid_stream_error_keeps_ocr_draft_exports_and_review_warning(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="hybrid",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertIn("unified_workbook", result["exports"])
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        self.assertIn("AI 视觉识别错误", "\n".join(result["warnings"]))
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "rapidocr")
        error_text = str(result["drawing_analysis"]["metadata"]["analysis_errors"])
        self.assertIn("AI 视觉识别中断，已保留 OCR 识别结果。", error_text)
        self.assertIn("stream_read_error", error_text)

    def test_effective_ocr_engine_accepts_mineru_and_error_lists_it(self) -> None:
        self.assertEqual(_effective_ocr_engine("mineru", {}), "mineru")
        self.assertEqual(_effective_ocr_engine("auto", {"ocr_engine": "mineru"}), "mineru")
        with patch(
            "minos_core.ocr_detection.get_default_ocr_engine",
            return_value="rapidocr",
        ):
            self.assertEqual(_effective_ocr_engine("auto", {"ocr_engine": "auto"}), "rapidocr")
            self.assertEqual(_effective_ocr_engine("auto", {}), "rapidocr")

        with self.assertRaisesRegex(ValueError, "mineru"):
            _effective_ocr_engine("bad_engine", {})

    def test_generate_three_tables_records_detected_auto_ocr_engine(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "minos_core.ocr_detection.get_default_ocr_engine",
                return_value="rapidocr",
            ):
                result = _run_pipeline(
                    tmpdir,
                    analysis_mode="ocr_only",
                    ocr_engine="auto",
                    analyzer=_FailingAnalyzer(captured),
                    captured=captured,
                )

        self.assertEqual(captured["ocr_engine"], "rapidocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "rapidocr")
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine_requested"], "auto")

    def test_hybrid_with_mineru_falls_back_to_ocr_and_preserves_metadata(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_pipeline(
                tmpdir,
                analysis_mode="hybrid",
                ocr_engine="mineru",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(captured["ocr_engine"], "mineru")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        self.assertEqual(result["drawing_analysis"]["metadata"]["ocr_engine"], "mineru")

    def test_hybrid_default_analyzer_gets_bounded_runtime_before_vision(self) -> None:
        captured: dict[str, object] = {}

        class _ConfigurableAnalyzer(_FailingAnalyzer):
            timeout = 120
            max_retries = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer = _ConfigurableAnalyzer(captured)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                bundle, warnings, analysis_source, errors = _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                    default_analyzer_factory=lambda: analyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(analysis_source, "hybrid_ocr_fallback")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "JLV03000500")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, warnings)
        self.assertEqual(analyzer.timeout, HYBRID_VISION_TIMEOUT_SECONDS)
        self.assertEqual(analyzer.max_retries, HYBRID_VISION_MAX_RETRIES)
        self.assertEqual(errors[-1]["stage"], "vision")

    def test_hybrid_context_can_override_vision_runtime_budget(self) -> None:
        captured: dict[str, object] = {}

        class _ConfigurableAnalyzer(_FailingAnalyzer):
            timeout = 120
            max_retries = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            analyzer = _ConfigurableAnalyzer(captured)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {
                        "hybrid_vision_timeout_seconds": 12,
                        "hybrid_vision_max_retries": 1,
                    },
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                    default_analyzer_factory=lambda: analyzer,
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(analyzer.timeout, 12)
        self.assertEqual(analyzer.max_retries, 1)

    def test_hybrid_vision_cannot_override_high_confidence_ocr_identity(self) -> None:
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_hinge_ocr_module(captured)},
            ):
                bundle, warnings, analysis_source, errors = _analyze_drawing_pages_for_mode(
                    {"path": str(root / "JLV03000500.pdf")},
                    [_page_evidence()],
                    root / "out",
                    {},
                    analysis_mode="hybrid",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=_VisionBushingAnalyzer(captured),
                    default_analyzer_factory=lambda: _VisionBushingAnalyzer(captured),
                    analyze_drawing_pages=analyze_drawing_pages,
                )

        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])
        self.assertEqual(analysis_source, "hybrid_vision")
        self.assertEqual(bundle["drawing_identity"]["part_name"], "尾门较链")
        self.assertEqual(bundle["drawing_identity"]["drawing_number"], "JLV03000500")
        self.assertTrue(bundle["drawing_identity"]["ocr_identity_locked"])

        metadata = bundle["metadata"]
        lock = metadata["ocr_identity_lock"]
        self.assertEqual(lock["source"], "ocr_title_block")
        self.assertIn("drawing_identity.part_name", lock["locked_fields"])
        self.assertEqual(lock["original_vision_identity"]["part_name"], "衬套")
        self.assertEqual(
            lock["part_family_classification"]["family_key"],
            "door_hinge",
        )
        self.assertEqual(
            metadata["locked_part_family_classification"]["family_key"],
            "door_hinge",
        )
        evidence_ids = {item["evidence_id"] for item in bundle["evidence"]}
        self.assertIn("drawing_page_001", evidence_ids)
        self.assertIn("ocr_page_001", evidence_ids)
        self.assertEqual(
            captured["vision_context"]["ocr_analysis_summary"]["drawing_identity"]["part_name"],
            "尾门较链",
        )

    def test_generate_draft_complete_workflow(self) -> None:
        """完整草案生成工作流：从证据到草案，验证所有阶段执行。"""
        from minos_core.pipeline import generate_draft

        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            evidence_path = root / "evidence.json"
            evidence_path.write_text('{"type": "test_evidence"}', encoding="utf-8")
            output_path = root / "draft.json"

            with patch("minos_core.stage.run_stage", side_effect=_mock_stage_runner(captured)):
                result = generate_draft(str(evidence_path), output_path=str(output_path))

            self.assertIn("status", result)
            self.assertIn(result["status"], {"draft_ready", "blocked"})
            self.assertTrue(output_path.exists())

        self.assertIn("ingest", captured)
        self.assertIn("analyze", captured)
        self.assertIn("generate_pfd", captured)

    def test_generate_three_tables_complete_workflow(self) -> None:
        """完整三表生成工作流：从图纸到三表导出，验证所有阶段执行。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
                export_mode="draft",
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertIn("drawing_analysis", result)
        self.assertIn("process_flow", result)
        self.assertIn("pfmea", result)
        self.assertIn("control_plan", result)
        self.assertIn("unified_workbook", result["exports"])
        self.assertEqual(result["drawing_analysis"]["metadata"]["analysis_source"], "ocr")

    def test_hybrid_mode_switches_to_ocr_on_vision_failure(self) -> None:
        """混合模式在视觉识别失败时切换到 OCR 结果。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="hybrid",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(
            result["drawing_analysis"]["metadata"]["analysis_source"],
            "hybrid_ocr_fallback",
        )
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])
        error_text = str(result["drawing_analysis"]["metadata"]["analysis_errors"])
        self.assertIn("AI 视觉识别中断，已保留 OCR 识别结果。", error_text)
        self.assertIn("stream_read_error", error_text)

    def test_hybrid_fallback_promotes_ocr_sc_cc_to_review_candidates(self) -> None:
        from minos_core.pipeline import drawing_analysis as drawing_pipeline

        ocr_analysis = {
            "drawing_identity": {"part_name": "OCR 支架", "drawing_number": "OCR-001"},
            "special_characteristics": [
                {
                    "classification": "SC",
                    "name": "孔径 10.0 +/- 0.1 mm",
                    "evidence_refs": ["drawing_page_001"],
                    "confidence": 0.91,
                }
            ],
            "evidence": [{"evidence_id": "drawing_page_001", "source": "ocr_text"}],
            "metadata": {"source_stage": "drawing_ocr_analysis"},
        }

        with patch(
            "minos_core.pipeline.drawing_analysis._run_ocr_drawing_analysis",
            return_value=ocr_analysis,
        ):
            analysis, warnings, source, errors = drawing_pipeline._analyze_drawing_pages_for_mode(
                source={"path": "drawing.png"},
                pages=[_page_evidence()],
                target_dir=Path("out"),
                context_payload={},
                analysis_mode="hybrid",
                ocr_engine="rapidocr",
                ocr_adapter=None,
                analyzer=_FailingAnalyzer({}),
                default_analyzer_factory=lambda: _FailingAnalyzer({}),
                analyze_drawing_pages=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("vision failed")
                ),
            )

        self.assertEqual(source, "hybrid_ocr_fallback")
        self.assertIn(HYBRID_OCR_FALLBACK_WARNING, warnings)
        self.assertEqual(errors[0]["stage"], "vision")
        self.assertTrue(
            any(
                item["candidate_type"] == "SC" and item["source"] == "ocr_text"
                for item in analysis["special_characteristic_candidates"]
            )
        )

    def test_ocr_only_mode_skips_vision_analysis(self) -> None:
        """OCR-only 模式跳过视觉识别，直接使用 OCR 结果。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
            )

        self.assertEqual(result["drawing_analysis"]["metadata"]["analysis_source"], "ocr")
        self.assertNotIn("vision_context", captured)
        self.assertNotIn(HYBRID_OCR_FALLBACK_WARNING, result["warnings"])

    def test_vision_only_mode_skips_ocr_analysis(self) -> None:
        """Vision-only 模式跳过 OCR 识别，仅使用视觉分析。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            patches = _pipeline_patches(captured)
            with ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.load_drawing_source",
                        return_value={"path": str(drawing_path)},
                    )
                )
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.render_drawing_pages",
                        return_value=[_page_evidence()],
                    )
                )
                stack.enter_context(
                    patch(
                        "minos_core.drawing_analysis.analyze_drawing_pages",
                        return_value=_vision_only_analysis(),
                    )
                )
                for item in patches:
                    stack.enter_context(item)
                result = generate_three_tables_from_drawing(
                    drawing_path,
                    root / "out",
                    context={"analysis_mode": "vision_only"},
                    analysis_mode="vision_only",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                )

        self.assertEqual(result["drawing_analysis"]["metadata"]["analysis_source"], "vision")
        self.assertNotIn("ocr", result["drawing_analysis"]["metadata"])

    def test_export_gate_blocks_unreviewed_draft(self) -> None:
        """导出质量门阻止未复核的草案正式导出。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            result = _run_pipeline_without_fake_ocr_module(
                root,
                drawing_path,
                analysis_mode="ocr_only",
                analyzer=_FailingAnalyzer(captured),
                captured=captured,
                export_mode="final",
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked_stage"], "final_three_table")
        self.assertEqual(result["exports"], {})
        self.assertIn("最终三表质量门未通过，已阻止正式导出。", result["warnings"])

    def test_export_gate_allows_reviewed_draft(self) -> None:
        """导出质量门允许已复核的草案正式导出。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            patches = _pipeline_patches(
                captured,
                final_gate=_Gate(can_continue=True, allow_user_export=True, needs_human_review=False),
            )
            with ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.load_drawing_source",
                        return_value={"path": str(drawing_path)},
                    )
                )
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.render_drawing_pages",
                        return_value=[_page_evidence()],
                    )
                )
                stack.enter_context(
                    patch(
                        "minos_core.drawing_analysis.analyze_drawing_pages",
                        return_value=_vision_only_analysis(),
                    )
                )
                for item in patches:
                    stack.enter_context(item)
                result = generate_three_tables_from_drawing(
                    drawing_path,
                    root / "out",
                    context={"analysis_mode": "vision_only"},
                    analysis_mode="vision_only",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=None,
                    export_mode="final",
                )

        self.assertEqual(result["status"], "draft_ready")
        self.assertIsNone(result["blocked_stage"])
        self.assertIn("unified_workbook", result["exports"])

    def test_quality_gate_evaluation_with_blockers(self) -> None:
        """质量门评估检测阻断项并阻止继续。"""
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            drawing_path = root / "drawing.png"
            drawing_path.write_bytes(b"fake drawing")
            patches = _pipeline_patches(captured)
            # Replace the default drawing recognition gate with a blocking one.
            patches[0] = patch(
                "minos_core.drawing_analysis.evaluate_drawing_recognition_gate",
                return_value=_Gate(
                    can_continue=False,
                    manual_review_items=[{"item_id": "blocker", "severity": "blocker"}],
                ),
            )
            with ExitStack() as stack:
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.load_drawing_source",
                        return_value={"path": str(drawing_path)},
                    )
                )
                stack.enter_context(
                    patch(
                        "minos_core.drawing_input.render_drawing_pages",
                        return_value=[_page_evidence()],
                    )
                )
                for item in patches:
                    stack.enter_context(item)
                result = generate_three_tables_from_drawing(
                    drawing_path,
                    root / "out",
                    context={"analysis_mode": "ocr_only"},
                    analysis_mode="ocr_only",
                    ocr_engine="rapidocr",
                    ocr_adapter=_FakeOCRAdapter(),
                    analyzer=_FailingAnalyzer(captured),
                )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocked_stage"], "drawing_recognition")
        self.assertEqual(result["exports"], {})
        self.assertIn("图纸识别质量门未通过，已阻止继续推导过程流程图。", result["warnings"])


class _FailingAnalyzer:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def analyze_drawing_pages(self, pages, context=None):
        self.captured["vision_context"] = dict(context or {})
        raise RuntimeError("stream_read_error: simulated vision failure")


class _VisionBushingAnalyzer:
    def __init__(self, captured: dict[str, object]) -> None:
        self.captured = captured

    def analyze_drawing_pages(self, pages, context=None):
        self.captured["vision_context"] = dict(context or {})
        return types.SimpleNamespace(
            content=json.dumps(
                {
                    "drawing_identity": {
                        "part_name": "衬套",
                        "drawing_number": "JLV03000500",
                        "revision": "A",
                        "confidence": 0.92,
                    },
                    "materials": [
                        {"name": "SPCC", "confidence": 0.9, "evidence_refs": ["drawing_page_001"]}
                    ],
                    "surface_treatments": [],
                    "dimensions": [],
                    "tolerances": [],
                    "special_characteristics": [],
                    "technical_requirements": [
                        {
                            "content": "衬套压入后不得松动。",
                            "confidence": 0.9,
                            "evidence_refs": ["drawing_page_001"],
                        }
                    ],
                    "inspection_requirements": [],
                    "manufacturing_clues": [
                        {
                            "operation": "衬套压入",
                            "confidence": 0.9,
                            "evidence_refs": ["drawing_page_001"],
                        }
                    ],
                    "uncertainties": [],
                },
                ensure_ascii=False,
            ),
            model="unit-vision",
            metadata={"source": "unit"},
        )


class _FakeOCRAdapter:
    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        return _ocr_result(source_ref)


class _Gate:
    def __init__(
        self,
        *,
        can_continue: bool = True,
        allow_user_export: bool = False,
        needs_human_review: bool = True,
        manual_review_items: list[dict[str, object]] | None = None,
    ) -> None:
        self.can_continue = can_continue
        self.allow_user_export = allow_user_export
        self.needs_human_review = needs_human_review
        self.manual_review_items: list[dict[str, object]] = manual_review_items or []

    def model_dump(self) -> dict[str, object]:
        return {
            "can_continue": self.can_continue,
            "allow_user_export": self.allow_user_export,
            "needs_human_review": self.needs_human_review,
            "manual_review_items": list(self.manual_review_items),
            "needs_confirmation_items": [],
        }


def _run_pipeline(
    tmpdir: str,
    *,
    analysis_mode: str,
    ocr_engine: str = "rapidocr",
    analyzer: object,
    captured: dict[str, object],
) -> dict[str, object]:
    root = Path(tmpdir)
    drawing_path = root / "drawing.png"
    drawing_path.write_bytes(b"fake drawing")

    patches = [
        patch("minos_core.drawing_input.load_drawing_source", return_value={"path": str(drawing_path)}),
        patch("minos_core.drawing_input.render_drawing_pages", return_value=["page-1"]),
        patch("minos_core.drawing_analysis.evaluate_drawing_recognition_gate", return_value=_Gate()),
        patch("minos_core.part_family_classifier.classify_part_family", return_value={"family_key": "unknown"}),
        patch("minos_core.drawing_to_pfd.infer_process_flow_from_drawing", return_value=_process_flow()),
        patch("minos_core.characteristic_registry.build_characteristic_registry", return_value={}),
        patch("minos_core.quality_gates.evaluate_pfd_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_pfmea_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_control_plan_bundle_gate", return_value=_Gate()),
        patch("minos_core.pfd_to_pfmea_ai.infer_pfmea_from_process_flow", return_value=_pfmea()),
        patch("minos_core.generate_control_plan.generate_control_plan_from_pfmea", return_value=_control_plan()),
        patch("minos_core.pipeline.orchestration.evaluate_export_gate", return_value=_Gate()),
        patch("minos_core.pipeline.orchestration.export_three_table_workbook", side_effect=_write_export),
        patch("minos_core.pipeline.orchestration.export_split_three_table_workbooks", side_effect=_write_split_exports),
        patch("minos_core.action_tracking.build_action_items", return_value=[]),
        patch("minos_core.action_tracking.action_items_summary", return_value={"total": 0}),
        patch("minos_core.three_table_linkage.build_three_table_linkage_map", return_value={"gaps": []}),
        patch("minos_core.three_table_linkage.evaluate_three_table_linkage", return_value={}),
        patch("minos_core.risk_structure.build_risk_structure", return_value={}),
        patch("minos_core.edit_patch.evaluate_edit_export_gate", return_value={}),
        patch("minos_core.edit_patch._build_review_dashboard", return_value={}),
        patch("minos_core.knowledge_recommendation.load_knowledge_rules", return_value=[]),
    ]
    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                sys.modules,
                {"minos_core.drawing_ocr_analysis": _fake_ocr_module(captured)},
            )
        )
        for item in patches:
            stack.enter_context(item)
        return generate_three_tables_from_drawing(
            drawing_path,
            root / "out",
            context={"analysis_mode": analysis_mode},
            analysis_mode=analysis_mode,
            ocr_engine=ocr_engine,
            ocr_adapter=_FakeOCRAdapter(),
            analyzer=analyzer,
        )


def _run_pipeline_without_fake_ocr_module(
    root: Path,
    drawing_path: Path,
    *,
    analysis_mode: str,
    ocr_engine: str = "rapidocr",
    analyzer: object,
    captured: dict[str, object],
    export_mode: str = "draft",
) -> dict[str, object]:
    patches = _pipeline_patches(captured, final_gate=_Gate(can_continue=True, allow_user_export=False))
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "minos_core.drawing_input.load_drawing_source",
                return_value={"path": str(drawing_path)},
            )
        )
        stack.enter_context(patch("minos_core.drawing_input.render_drawing_pages", return_value=[_page_evidence()]))
        for item in patches:
            stack.enter_context(item)
        return generate_three_tables_from_drawing(
            drawing_path,
            root / "out",
            context={"analysis_mode": analysis_mode},
            analysis_mode=analysis_mode,
            ocr_engine=ocr_engine,
            ocr_adapter=_FakeOCRAdapter(),
            analyzer=analyzer,
            export_mode=export_mode,
        )


def _pipeline_patches(
    _captured: dict[str, object],
    *,
    final_gate: _Gate | None = None,
) -> list[object]:
    return [
        patch(
            "minos_core.drawing_analysis.evaluate_drawing_recognition_gate",
            return_value=_Gate(
                manual_review_items=[
                    {
                        "item_id": "drawing:ocr",
                        "category": "drawing_recognition_ocr",
                        "message": "OCR 待人工复核",
                    }
                ]
            ),
        ),
        patch("minos_core.part_family_classifier.classify_part_family", return_value={"family_key": "unknown"}),
        patch("minos_core.drawing_to_pfd.infer_process_flow_from_drawing", return_value=_process_flow()),
        patch("minos_core.characteristic_registry.build_characteristic_registry", return_value={}),
        patch("minos_core.quality_gates.evaluate_pfd_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_pfmea_bundle_gate", return_value=_Gate()),
        patch("minos_core.quality_gates.evaluate_control_plan_bundle_gate", return_value=_Gate()),
        patch("minos_core.pfd_to_pfmea_ai.infer_pfmea_from_process_flow", return_value=_pfmea()),
        patch("minos_core.generate_control_plan.generate_control_plan_from_pfmea", return_value=_control_plan()),
        patch("minos_core.pipeline.orchestration.evaluate_export_gate", return_value=final_gate or _Gate()),
        patch("minos_core.pipeline.orchestration.export_three_table_workbook", side_effect=_write_export),
        patch("minos_core.pipeline.orchestration.export_split_three_table_workbooks", side_effect=_write_split_exports),
        patch("minos_core.action_tracking.build_action_items", return_value=[]),
        patch("minos_core.action_tracking.action_items_summary", return_value={"total": 0}),
        patch("minos_core.three_table_linkage.build_three_table_linkage_map", return_value={"gaps": []}),
        patch("minos_core.three_table_linkage.evaluate_three_table_linkage", return_value={}),
        patch("minos_core.risk_structure.build_risk_structure", return_value={}),
        patch("minos_core.edit_patch.evaluate_edit_export_gate", return_value={}),
        patch("minos_core.edit_patch._build_review_dashboard", return_value={}),
        patch("minos_core.knowledge_recommendation.load_knowledge_rules", return_value=[]),
    ]


def _fake_ocr_module(captured: dict[str, object]) -> types.ModuleType:
    module = types.ModuleType("minos_core.drawing_ocr_analysis")

    def analyze_drawing_with_ocr(**kwargs):
        captured["ocr_engine"] = kwargs["ocr_engine"]
        captured["ocr_adapter"] = kwargs["ocr_adapter"]
        captured["ocr_context"] = dict(kwargs["context"])
        return _drawing_analysis()

    module.analyze_drawing_with_ocr = analyze_drawing_with_ocr
    return module


def _fake_hinge_ocr_module(captured: dict[str, object]) -> types.ModuleType:
    module = types.ModuleType("minos_core.drawing_ocr_analysis")

    def analyze_drawing_with_ocr(**kwargs):
        captured["ocr_engine"] = kwargs["ocr_engine"]
        captured["ocr_adapter"] = kwargs["ocr_adapter"]
        captured["ocr_context"] = dict(kwargs["context"])
        return _hinge_ocr_drawing_analysis()

    module.analyze_drawing_with_ocr = analyze_drawing_with_ocr
    return module


def _drawing_analysis() -> dict[str, object]:
    return {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {"part_name": "OCR 支架", "drawing_number": "OCR-001"},
        "materials": [{"name": "SPCC", "confidence": 0.9, "evidence_refs": ["EV-1"]}],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [
            {"operation": "来料检验", "confidence": 0.9, "evidence_refs": ["EV-1"]}
        ],
        "uncertainties": [],
        "evidence": [{"evidence_id": "EV-1", "source": "ocr_text"}],
        "metadata": {
            "source_stage": "drawing_ocr_analysis",
            "ocr_summary": {"raw_text_preview": "OCR 支架 SPCC 来料检验"},
        },
    }


def _hinge_ocr_drawing_analysis() -> dict[str, object]:
    return {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {
            "part_name": "尾门较链",
            "drawing_number": "JLV03000500",
            "revision": "A",
            "evidence_refs": ["ocr_page_001"],
            "field_evidence_refs": {
                "part_name": ["ocr_page_001"],
                "drawing_number": ["ocr_page_001"],
                "revision": ["ocr_page_001"],
            },
            "confidence": 0.82,
            "ai_inferred": False,
            "ocr_inferred": True,
            "needs_confirmation": True,
        },
        "materials": [{"name": "SPCC", "confidence": 0.9, "evidence_refs": ["ocr_page_001"]}],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [
            {"operation": "铰链装配", "confidence": 0.82, "evidence_refs": ["ocr_page_001"]}
        ],
        "uncertainties": [],
        "evidence": [
            {
                "evidence_id": "ocr_page_001",
                "source": "ocr_page",
                "content": "JLV03000500 BACKX D00R HIMGE 尾门较链",
                "confidence": 0.82,
            }
        ],
        "metadata": {
            "source_stage": "drawing_ocr_analysis",
            "ocr_summary": {
                "drawing_identity": {
                    "part_name": "尾门较链",
                    "drawing_number": "JLV03000500",
                }
            },
        },
    }


def _ocr_result(source_ref: str) -> OCRResult:
    return OCRResult(
        source_ref=source_ref,
        pages=[
            OCRPageText(
                page_number=1,
                text="Drawing No: OCR-001\nPart Name: OCR 支架\nMaterial: SPCC\nProcess: incoming inspection",
                confidence=0.88,
                engine="unit_ocr",
                source_ref=source_ref,
            )
        ],
    )


def _page_evidence():
    class Page:
        evidence_id = "drawing_page_001"
        image_path = "drawing.png"
        source_ref = "drawing.png"

        def model_dump(self):
            return {
                "evidence_id": "drawing_page_001",
                "source": "drawing_page",
                "page_number": 1,
                "image_path": "drawing.png",
                "content": "drawing page",
            }

    return Page()


def _process_flow() -> dict[str, object]:
    return {
        "document_type": "process_flow",
        "product": {"part_name": "OCR 支架"},
        "drawings": [],
        "characteristics": [],
        "steps": [
            {
                "process_step_id": "P10",
                "operation": "来料检验",
                "process_function": "确认材料",
                "evidence_refs": ["EV-1"],
            }
        ],
        "links": [],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _pfmea() -> dict[str, object]:
    return {
        "document_type": "pfmea",
        "rows": [{"pfmea_id": "PFMEA-P10-001", "process_step_id": "P10"}],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _control_plan() -> dict[str, object]:
    return {
        "document_type": "control_plan",
        "rows": [{"control_plan_id": "CP-P10-001", "process_step_id": "P10"}],
        "pending_fields": [],
        "ai_inferred_items": [],
    }


def _write_export(chain, path, **kwargs):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"test workbook")
    return destination


def _write_split_exports(chain, output_dir, **kwargs):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in ("process_flow", "pfmea", "control_plan"):
        path = directory / f"{name}.xlsx"
        path.write_bytes(b"test workbook")
        result[name] = path
    return result


def _mock_stage_runner(captured: dict[str, object]):
    """Mock stage runner for generate_draft workflow."""
    from minos_core.stage import StageResult

    def run_stage(stage_input, stage: str):
        captured[stage] = stage_input
        return StageResult(
            stage=stage,
            status="ok",
            output={"stage": stage, "result": "success"},
        )

    return run_stage


def _vision_only_analysis() -> dict[str, object]:
    """Vision-only 分析结果（无 OCR）。"""
    return {
        "document_type": "drawing_analysis_bundle",
        "schema_version": "minos-core.drawing_analysis.v1",
        "drawing_identity": {"part_name": "视觉支架", "drawing_number": "VIS-001"},
        "materials": [{"name": "SPCC", "confidence": 0.9, "evidence_refs": ["drawing_page_001"]}],
        "surface_treatments": [],
        "dimensions": [],
        "tolerances": [],
        "special_characteristics": [],
        "technical_requirements": [],
        "inspection_requirements": [],
        "manufacturing_clues": [
            {"operation": "来料检验", "confidence": 0.9, "evidence_refs": ["drawing_page_001"]}
        ],
        "uncertainties": [],
        "evidence": [{"evidence_id": "drawing_page_001", "source": "drawing_page"}],
        "metadata": {
            "source_stage": "drawing_vision_analysis",
            "analysis_source": "vision",
        },
    }


if __name__ == "__main__":
    unittest.main()
