"""Command line interface for MINOS Core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .adapters.fixture_json import load_fixture_payload
from .config import list_samples
from .domain import APQPChain
from .validation import validate_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minos-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List configured sample metadata")
    list_parser.add_argument(
        "--samples-dir", default=None, help="Optional sample metadata directory"
    )
    subparsers.add_parser("list-samples", help="List configured sample metadata")
    subparsers.add_parser("ai-config", help="Show AI provider config status without printing secrets")

    analyze_drawing_parser = subparsers.add_parser(
        "analyze-drawing",
        help="Analyze a PDF/PNG/JPG drawing with the configured multimodal AI",
    )
    analyze_drawing_parser.add_argument("--input", required=True, help="Drawing PDF/PNG/JPG path")
    analyze_drawing_parser.add_argument("--output", help="Optional drawing_analysis_bundle JSON path")
    analyze_drawing_parser.add_argument(
        "--pages-output-dir",
        help="Optional directory for rendered PDF page images",
    )
    analyze_drawing_parser.add_argument(
        "--context-json",
        default="{}",
        help="Optional JSON object with part family or project context",
    )
    analyze_drawing_parser.add_argument(
        "--mode",
        choices=("ocr_only", "vision_only", "hybrid"),
        default="hybrid",
        help="Drawing analysis mode; hybrid tries OCR before multimodal AI",
    )
    analyze_drawing_parser.add_argument(
        "--ocr-engine",
        choices=("auto", "pdf_text", "rapidocr"),
        default="auto",
        help="OCR engine for ocr_only/hybrid modes",
    )

    generate_three_parser = subparsers.add_parser(
        "generate-three-tables",
        help="Generate draft PFD/PFMEA/CP workbooks from a drawing",
    )
    generate_three_parser.add_argument("--input", required=True, help="Drawing PDF/PNG/JPG path")
    generate_three_parser.add_argument("--output-dir", required=True, help="Output directory")
    generate_three_parser.add_argument(
        "--result-output",
        help="Optional result envelope JSON path; defaults to output-dir\\three_table_generation_result.json",
    )
    generate_three_parser.add_argument(
        "--context-json",
        default="{}",
        help="Optional JSON object with part family or project context",
    )
    generate_three_parser.add_argument(
        "--export-mode",
        choices=("draft", "final"),
        default="draft",
        help="Export draft by default; final is blocked unless the quality gate allows it",
    )
    generate_three_parser.add_argument(
        "--mode",
        choices=("ocr_only", "vision_only", "hybrid"),
        default="hybrid",
        help="Drawing analysis mode; hybrid tries OCR before multimodal AI",
    )
    generate_three_parser.add_argument(
        "--ocr-engine",
        choices=("auto", "pdf_text", "rapidocr"),
        default="auto",
        help="OCR engine for ocr_only/hybrid modes",
    )

    demo_drawing_parser = subparsers.add_parser(
        "write-demo-drawing",
        help="Write a synthetic safe demo drawing PNG for local smoke tests",
    )
    demo_drawing_parser.add_argument("--output", required=True, help="Output PNG path")

    accept_three_parser = subparsers.add_parser(
        "accept-three-tables",
        help="Check a three_table_generation_result JSON and exported workbooks",
    )
    accept_three_parser.add_argument(
        "--result",
        required=True,
        help="three_table_generation_result.json path",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate an APQP fixture")
    validate_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    validate_parser.add_argument(
        "--input", help="Fixture JSON file or fixture directory"
    )

    export_parser = subparsers.add_parser("export", help="Export a formally released APQP fixture")
    export_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    export_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    export_parser.add_argument("--output", required=True, help="Output workbook path")
    export_parser.add_argument("--label", default="", help="Optional export label")
    export_parser.add_argument(
        "--manifest-output",
        help="Optional path to save the run manifest JSON",
    )

    export_draft_parser = subparsers.add_parser(
        "export-draft",
        help="Export a draft-only APQP workbook for engineering review",
    )
    export_draft_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    export_draft_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    export_draft_parser.add_argument("--output", required=True, help="Output workbook path")
    export_draft_parser.add_argument("--label", default="", help="Optional export label")
    export_draft_parser.add_argument(
        "--manifest-output",
        help="Optional path to save the run manifest JSON",
    )

    audit_parser = subparsers.add_parser(
        "audit", help="Audit APQP fixture quality without blocking export"
    )
    audit_parser.add_argument(
        "--fixture", help="Fixture JSON file or fixture directory"
    )
    audit_parser.add_argument("--input", help="Fixture JSON file or fixture directory")
    audit_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )

    draft_parser = subparsers.add_parser(
        "generate-draft",
        aliases=["run-pipeline"],
        help="Run generated stages from evidence and emit a draft APQPChain JSON",
    )
    draft_parser.add_argument(
        "--input", required=True, help="Evidence bundle JSON file or evidence directory"
    )
    draft_parser.add_argument(
        "--output", help="Optional path to save the draft result JSON"
    )
    draft_parser.add_argument(
        "--manifest-output",
        help="Optional path to save the run manifest JSON",
    )

    apply_review_parser = subparsers.add_parser(
        "apply-review",
        help="Apply a review patch to an APQPChain draft/result and re-run the export gate",
    )
    apply_review_parser.add_argument(
        "--input",
        help="Draft result JSON, APQPChain JSON, or fixture directory",
    )
    apply_review_parser.add_argument(
        "--draft-result",
        dest="draft_result",
        help="Alias for --input when passing a draft result JSON",
    )
    apply_review_parser.add_argument(
        "--apqp-chain",
        dest="apqp_chain",
        help="Alias for --input when passing an APQPChain JSON or fixture directory",
    )
    apply_review_parser.add_argument(
        "--review-patch",
        required=True,
        help="Review patch JSON file",
    )
    apply_review_parser.add_argument(
        "--output",
        help="Optional path to save the reviewed result JSON envelope",
    )
    apply_review_parser.add_argument(
        "--manifest-output",
        help="Optional path to save the run manifest JSON",
    )

    review_template_parser = subparsers.add_parser(
        "review-template",
        help="Create a human-fillable review patch template from a draft result",
    )
    review_template_parser.add_argument(
        "--draft-result",
        dest="draft_result",
        required=True,
        help="Draft result JSON generated by generate-draft",
    )
    review_template_parser.add_argument(
        "--output",
        required=True,
        help="Output review patch template JSON path",
    )

    convert_parser = subparsers.add_parser(
        "convert-legacy", help="Convert a legacy Excel seed workbook"
    )
    convert_parser.add_argument(
        "--sample-id",
        required=True,
        help="Sample identifier for the generated fixtures",
    )
    convert_parser.add_argument(
        "--display-name", required=True, help="Display name for the generated fixtures"
    )
    convert_parser.add_argument(
        "--input", required=True, help="Legacy .xlsx seed workbook path"
    )
    convert_parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for process_flow/pfmea/control_plan JSON",
    )
    convert_parser.add_argument(
        "--profile",
        default=None,
        help="Optional profile: door_hinge, stamping, or limiter",
    )

    args = parser.parse_args(argv)
    if args.command in {"list", "list-samples"}:
        return _list_samples(getattr(args, "samples_dir", None))
    if args.command == "ai-config":
        return _ai_config()
    if args.command == "analyze-drawing":
        return _analyze_drawing(
            args.input,
            args.output,
            args.pages_output_dir,
            args.context_json,
            args.mode,
            args.ocr_engine,
        )
    if args.command == "generate-three-tables":
        return _generate_three_tables(
            args.input,
            args.output_dir,
            args.result_output,
            args.context_json,
            args.export_mode,
            args.mode,
            args.ocr_engine,
        )
    if args.command == "write-demo-drawing":
        return _write_demo_drawing(args.output)
    if args.command == "accept-three-tables":
        return _accept_three_tables(args.result)
    if args.command == "validate":
        return _validate(args.fixture or args.input)
    if args.command == "export":
        return _export(args.fixture or args.input, args.output, args.label, args.manifest_output)
    if args.command == "export-draft":
        return _export_draft(
            args.fixture or args.input, args.output, args.label, args.manifest_output
        )
    if args.command == "audit":
        return _audit(args.fixture or args.input, args.json)
    if args.command in {"generate-draft", "run-pipeline"}:
        return _generate_draft(args.input, args.output, args.manifest_output)
    if args.command == "apply-review":
        review_input = args.input or args.draft_result or args.apqp_chain
        return _apply_review(
            review_input, args.review_patch, args.output, args.manifest_output
        )
    if args.command == "review-template":
        return _review_template(args.draft_result, args.output)
    if args.command == "convert-legacy":
        return _convert_legacy(
            args.input, args.output_dir, args.sample_id, args.display_name, args.profile
        )
    parser.error(f"unknown command: {args.command}")
    return 2


def _list_samples(samples_dir: str | None = None) -> int:
    for sample in list_samples(samples_dir):
        print(
            "\t".join(
                [
                    sample.sample_id,
                    sample.display_name,
                    sample.product_family,
                    sample.apqp_phase,
                    sample.language,
                    sample.workbook_name,
                ]
            )
        )
    return 0


def _ai_config() -> int:
    from .ai_config import load_openai_responses_config

    config = load_openai_responses_config().model_dump()
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0 if config["api_key_configured"] else 2


def _analyze_drawing(
    drawing_input: str,
    output: str | None,
    pages_output_dir: str | None,
    context_json: str,
    analysis_mode: str,
    ocr_engine: str,
) -> int:
    from .adapters.multimodal import OpenAIMultimodalError, OpenAIResponsesMultimodalDrawingAnalyzer
    from .drawing_analysis import DrawingAnalysisError, analyze_drawing_pages
    from .drawing_input import DrawingInputError, load_drawing_source, render_drawing_pages
    from .pipeline import (
        _analyze_drawing_pages_for_mode,
        _attach_analysis_metadata,
        _effective_analysis_mode,
        _effective_ocr_engine,
    )

    context = _parse_context_json(context_json)
    try:
        active_analysis_mode = _effective_analysis_mode(analysis_mode, context)
        active_ocr_engine = _effective_ocr_engine(ocr_engine, context)
        context["analysis_mode"] = active_analysis_mode
        context["ocr_engine"] = active_ocr_engine
        source = load_drawing_source(drawing_input)
        pages = render_drawing_pages(source, pages_output_dir)
        target_dir = (
            Path(pages_output_dir)
            if pages_output_dir
            else Path(output).parent
            if output
            else Path(drawing_input).resolve().parent
        )
        bundle, warnings, analysis_source, errors = _analyze_drawing_pages_for_mode(
            source,
            pages,
            target_dir,
            context,
            analysis_mode=active_analysis_mode,
            ocr_engine=active_ocr_engine,
            ocr_adapter=None,
            analyzer=None,
            default_analyzer_factory=OpenAIResponsesMultimodalDrawingAnalyzer,
            analyze_drawing_pages=analyze_drawing_pages,
        )
        _attach_analysis_metadata(
            bundle,
            analysis_mode=active_analysis_mode,
            ocr_engine=active_ocr_engine,
            analysis_source=analysis_source,
            warnings=warnings,
            errors=errors,
        )
    except (
        DrawingInputError,
        DrawingAnalysisError,
        OpenAIMultimodalError,
        FileNotFoundError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"图纸分析失败：{exc}")
        return 2

    text = json.dumps(bundle, ensure_ascii=False, indent=2)
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        print(f"图纸分析结果已保存：{destination}")
    else:
        print(text)
    return 0


def _parse_context_json(context_json: str) -> dict[str, Any]:
    payload = json.loads(context_json or "{}")
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("context JSON must be an object", context_json, 0)
    return payload


def _generate_three_tables(
    drawing_input: str,
    output_dir: str,
    result_output: str | None,
    context_json: str,
    export_mode: str,
    analysis_mode: str,
    ocr_engine: str,
) -> int:
    from .adapters.multimodal import OpenAIMultimodalError
    from .drawing_analysis import DrawingAnalysisError
    from .drawing_input import DrawingInputError
    from .pipeline import generate_three_tables_from_drawing

    try:
        result = generate_three_tables_from_drawing(
            drawing_input,
            output_dir,
            context=_parse_context_json(context_json),
            export_mode=export_mode,
            analysis_mode=analysis_mode,
            ocr_engine=ocr_engine,
        )
    except (
        DrawingInputError,
        DrawingAnalysisError,
        OpenAIMultimodalError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"三表生成失败：{exc}")
        return 2

    destination = Path(result_output) if result_output else Path(output_dir) / "three_table_generation_result.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"三表生成结果已保存：{destination}")
    print(f"状态：{result.get('status_display') or result.get('status')}")
    manual_review = result.get("manual_review")
    if isinstance(manual_review, dict):
        summary = manual_review.get("summary")
        if isinstance(summary, dict) and summary.get("message"):
            print(str(summary["message"]))
    if result.get("exports"):
        print(json.dumps(result["exports"], ensure_ascii=False, indent=2))
    return 0 if result.get("status") != "blocked" else 2


def _write_demo_drawing(output: str) -> int:
    from .demo_acceptance import write_safe_demo_drawing_png

    path = write_safe_demo_drawing_png(output)
    print(f"安全演示图纸已保存：{path}")
    return 0


def _accept_three_tables(result_path: str) -> int:
    from .adapters.fixture_json import read_json_object
    from .demo_acceptance import summarize_three_table_acceptance

    try:
        payload = read_json_object(result_path)
        summary = summarize_three_table_acceptance(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"三表验收检查失败：{exc}")
        return 2
    payload = {
        "ok": summary.ok,
        "errors": list(summary.errors),
        "warnings": list(summary.warnings),
        "workbook_checks": {
            name: {
                "path": check.path,
                "ok": check.ok,
                "errors": list(check.errors),
                "worksheet_count": len(check.worksheets),
            }
            for name, check in summary.workbook_checks.items()
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if summary.ok else 2


def _validate(fixture: str) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    chain = APQPChain(**load_fixture_payload(fixture))
    result = validate_chain(chain)
    if not result:
        print(str(result))
        return 2
    print(f"OK: {chain.slug}")
    return 0


def _export(fixture: str, output: str, label: str, manifest_output: str | None) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    from .pipeline import export_fixture
    from .quality_gates import ExportGateError

    payload = load_fixture_payload(fixture)
    if payload.get("document_type") == "apqp_chain_review_result":
        payload = payload.get("patched_chain")
    if label:
        payload["label"] = label
    try:
        result = export_fixture(payload, output, manifest_output)
    except ExportGateError as exc:
        print(str(exc))
        return 2
    print(f"Exported: {result}")
    return 0


def _export_draft(
    fixture: str, output: str, label: str, manifest_output: str | None
) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    from .pipeline import export_draft_fixture

    payload = load_fixture_payload(fixture)
    if payload.get("document_type") == "apqp_chain_draft_result":
        payload = payload.get("draft")
    if label:
        payload["label"] = label
    result = export_draft_fixture(payload, output, manifest_output)
    print(f"Draft exported: {result}")
    return 0


def _audit(fixture: str, as_json: bool) -> int:
    if not fixture:
        raise ValueError("--fixture or --input is required")
    from .audit import audit_chain, audit_report_json

    report = audit_chain(load_fixture_payload(fixture))
    print(audit_report_json(report) if as_json else report.to_text())
    return 0


def _generate_draft(
    evidence_input: str, output: str | None, manifest_output: str | None
) -> int:
    from .pipeline import generate_draft

    result = generate_draft(evidence_input, output, manifest_output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "draft_ready" else 2


def _apply_review(
    review_input: str | None,
    review_patch: str,
    output: str | None,
    manifest_output: str | None,
) -> int:
    if not review_input:
        raise ValueError("--input, --draft-result, or --apqp-chain is required")
    from .pipeline import apply_review
    from .review_patch import ReviewPatchError

    try:
        result = apply_review(review_input, review_patch, output, manifest_output)
    except (ReviewPatchError, TypeError, ValueError) as exc:
        print(f"人工复核应用失败：{exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _review_template(draft_result: str, output: str) -> int:
    from .adapters.fixture_json import read_json_object
    from .review_patch import build_review_patch_template

    template = build_review_patch_template(read_json_object(Path(draft_result)))
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(template, ensure_ascii=False, indent=2))
    return 0


def _convert_legacy(
    workbook: str,
    output_dir: str,
    sample_id: str,
    display_name: str,
    profile: str | None,
) -> int:
    from .adapters.legacy_excel import convert_legacy_workbook

    paths = convert_legacy_workbook(
        workbook, output_dir, sample_id, display_name, profile
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
