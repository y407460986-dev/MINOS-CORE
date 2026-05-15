"""Infer process-flow drafts from AI drawing analysis bundles."""

from __future__ import annotations

from typing import Any

from minos_core._text_utils import row_text, string_list, flow_type_display


_PROCESS_LIBRARY: dict[str, dict[str, Any]] = {
    "incoming inspection": {
        "operation": "来料检验",
        "process_function": "确认来料、图纸版本和供应商放行状态符合要求",
        "equipment": "来料检验清单、材质证明、基础量检具",
    },
    "material preparation": {
        "operation": "材料准备",
        "process_function": "准备生产所需材料、毛坯、批次和流转信息",
        "equipment": "物料架、流转卡、下料或备料工具",
    },
    "blanking": {
        "operation": "落料",
        "process_function": "形成毛坯轮廓或初始板料形状",
        "equipment": "压力机、落料模、送料装置",
    },
    "piercing": {
        "operation": "冲孔",
        "process_function": "按图纸要求形成孔、槽或冲切特征",
        "equipment": "压力机、冲孔模、冲头、定位夹具",
    },
    "forming": {
        "operation": "成形",
        "process_function": "按图纸要求形成几何形状、折弯或轮廓",
        "equipment": "压力机、成形模、定位夹具",
    },
    "bending": {
        "operation": "折弯",
        "process_function": "将零件折弯到规定角度、高度或轮廓",
        "equipment": "折弯机或成形工装",
    },
    "machining": {
        "operation": "机加工",
        "process_function": "加工关键特征以满足尺寸要求",
        "equipment": "CNC 设备、刀具、夹具",
    },
    "drilling": {
        "operation": "钻孔",
        "process_function": "加工钻孔或二次孔类特征",
        "equipment": "钻床、加工夹具、刀具",
    },
    "tapping": {
        "operation": "攻丝",
        "process_function": "按要求加工内螺纹",
        "equipment": "丝锥、攻丝设备、螺纹规",
    },
    "deburr": {
        "operation": "去毛刺",
        "process_function": "去除功能面和搬运面的毛刺及锐边",
        "equipment": "去毛刺工具、滚抛设备、毛刷、外观样件",
    },
    "cleaning": {
        "operation": "清洗",
        "process_function": "去除油污、切屑、灰尘或污染物，确保进入下道工序",
        "equipment": "清洗工位、清洗剂或清洗机、干燥装置",
    },
    "heat treatment": {
        "operation": "热处理",
        "process_function": "获得规定硬度、强度或材料状态",
        "equipment": "热处理炉、淬火系统、硬度计",
    },
    "surface treatment": {
        "operation": "表面处理",
        "process_function": "实施或确认涂层、电镀、喷涂或表面防护",
        "equipment": "表面处理线、膜厚仪、外观标准",
    },
    "plating": {
        "operation": "电镀",
        "process_function": "按要求形成电镀层或涂层厚度及覆盖范围",
        "equipment": "电镀线、槽液控制、膜厚仪",
    },
    "painting": {
        "operation": "喷涂",
        "process_function": "按要求形成涂装外观和防护性能",
        "equipment": "喷涂线、固化系统、膜厚仪",
    },
    "welding": {
        "operation": "焊接",
        "process_function": "按规定位置、强度和外观要求连接零件",
        "equipment": "焊接设备、焊接夹具、焊缝检具",
    },
    "riveting": {
        "operation": "铆接",
        "process_function": "通过铆接高度、保持力或推出力控制完成零件连接",
        "equipment": "铆接机、定位夹具、高度检具",
    },
    "press fitting": {
        "operation": "压装",
        "process_function": "将零件压装到规定配合、压力或位置",
        "equipment": "压机、装配夹具、压力或位移监控装置",
    },
    "assembly": {
        "operation": "装配",
        "process_function": "装配零部件以满足功能和尺寸要求",
        "equipment": "装配夹具、手工具、扭矩或压力工具",
    },
    "injection molding": {
        "operation": "注塑",
        "process_function": "成型塑料件特征以满足尺寸和外观要求",
        "equipment": "注塑机、模具、干燥设备",
    },
    "trimming": {
        "operation": "修边",
        "process_function": "去除浇口、飞边或成型后的多余材料",
        "equipment": "修边夹具、刀具、切刀、外观标准",
    },
    "process inspection": {
        "operation": "过程检验",
        "process_function": "在生产过程中确认关键产品和过程特性",
        "equipment": "过程量检具、检具、检验记录",
    },
    "final inspection": {
        "operation": "最终检验",
        "process_function": "按图纸、特殊特性和检验要求确认成品",
        "equipment": "终检量检具、检具、外观标准",
    },
    "packaging": {
        "operation": "包装",
        "process_function": "对合格产品进行包装、标识和防护以便发运",
        "equipment": "包装材料、标签打印机、条码扫描器",
    },
    "lubrication": {
        "operation": "润滑",
        "process_function": "对铰链转动副涂抹规定润滑脂以满足力矩和寿命要求",
        "equipment": "注脂设备、润滑脂、力矩测试仪",
    },
    "functional inspection": {
        "operation": "功能检验",
        "process_function": "验证产品功能、性能或客户特定要求是否满足",
        "equipment": "功能测试台、力矩测试仪、角度检具",
    },
}

_ROUTE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "sheet_metal": (
        "incoming inspection",
        "material preparation",
        "blanking",
        "piercing",
        "forming",
        "deburr",
        "cleaning",
        "surface treatment",
        "process inspection",
        "final inspection",
        "packaging",
    ),
    "machined": (
        "incoming inspection",
        "material preparation",
        "machining",
        "drilling",
        "tapping",
        "deburr",
        "cleaning",
        "process inspection",
        "final inspection",
        "packaging",
    ),
    "assembly": (
        "incoming inspection",
        "material preparation",
        "assembly",
        "riveting",
        "press fitting",
        "process inspection",
        "final inspection",
        "packaging",
    ),
    "plastic_molded": (
        "incoming inspection",
        "material preparation",
        "injection molding",
        "trimming",
        "cleaning",
        "process inspection",
        "final inspection",
        "packaging",
    ),
    "generic": (
        "incoming inspection",
        "material preparation",
        "process inspection",
        "final inspection",
        "packaging",
    ),
}


def infer_process_flow_from_drawing(
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a PFD draft from drawing manufacturing clues.

    The first implementation is deliberately conservative: it turns explicit
    manufacturing clues from the drawing-recognition bundle into ordered Pxx
    steps and keeps every step marked for review because the route is AI
    inferred from a drawing, not confirmed process planning.
    """
    family_context = _resolve_family_context(family_context)
    steps, pending_fields = _build_steps_from_clues(analysis_bundle, family_context)
    return _finalize_process_flow(steps, analysis_bundle, family_context, pending_fields)


def _resolve_family_context(
    family_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve family_context templates when only family_key is given."""
    if not family_context or family_context.get("process_route_templates"):
        return family_context

    family_key = family_context.get("family_key")
    if not family_key:
        return family_context

    # Try classifier templates first (operation_key format)
    try:
        from minos_core.part_family_classifier import get_default_family_index
        family_index = get_default_family_index()
        family_data = family_index.get(family_key)
        if family_data:
            family_context = dict(family_context)
            family_context["process_route_templates"] = list(
                family_data.get("process_route_templates", [])
            )
            if not family_context.get("knowledge_source_refs"):
                family_context["knowledge_source_refs"] = list(
                    family_data.get("knowledge_source_refs", [])
                )
    except (KeyError, ImportError):
        pass

    # Fallback: load from knowledge base for process_inference data
    if not family_context.get("process_route_templates") or not family_context.get("process_inference"):
        try:
            from minos_core.part_family_knowledge import load_part_family_knowledge
            knowledge = load_part_family_knowledge(family_key)
            if not family_context.get("process_route_templates"):
                family_context = dict(family_context)
                family_context["process_route_templates"] = knowledge.get(
                    "process_route_templates", []
                )
            if knowledge.get("process_inference"):
                family_context = dict(family_context) if family_context.get("process_inference") is None else family_context
                family_context["process_inference"] = knowledge["process_inference"]
            if not family_context.get("knowledge_source_refs"):
                family_context["knowledge_source_refs"] = knowledge.get(
                    "knowledge_source_refs", []
                )
        except (KeyError, FileNotFoundError, ImportError):
            pass

    return family_context


def _build_steps_from_clues(
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Iterate manufacturing clues and build the steps list."""
    clues = _expand_manufacturing_clues(analysis_bundle.get("manufacturing_clues", []))
    clues = _enrich_with_process_library(analysis_bundle, clues, family_context)
    family_knowledge_refs: list[str] = []
    if family_context:
        family_knowledge_refs = string_list(family_context.get("knowledge_source_refs", []))
    steps: list[dict[str, Any]] = []
    pending_fields = list(analysis_bundle.get("pending_fields", []))
    for index, clue in enumerate(clues, start=1):
        preserve_name = bool(clue.get("preserve_operation_name", False))
        operation = _display_operation(
            row_text(clue, "operation", "process_step", "name", "process", default=""),
            preserve=preserve_name,
        )
        refs = string_list(clue.get("evidence_refs", []))
        if not operation:
            pending_fields.append(f"manufacturing_clues[{index - 1}].operation")
            continue
        step_id = row_text(clue, "process_step_id", "step_id", default=f"P{index * 10}")
        clue_knowledge_refs = string_list(clue.get("knowledge_source_refs", []))
        all_knowledge_refs: list[str] = []
        for ref in clue_knowledge_refs + family_knowledge_refs:
            if ref not in all_knowledge_refs:
                all_knowledge_refs.append(ref)
        flow_type = row_text(clue, "flow_type", "process_type", default="")
        if not flow_type:
            flow_type = _infer_flow_type(operation)
        steps.append(
            {
                "process_step_id": _normalize_step_id(step_id, index),
                "sequence": index * 10,
                "operation": operation,
                "process_function": row_text(
                    clue,
                    "process_function",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "process_purpose": row_text(
                    clue,
                    "process_purpose",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "product_characteristics": string_list(
                    clue.get("product_characteristics", [])
                ),
                "process_characteristics": string_list(
                    clue.get("process_characteristics", [])
                ),
                "owner": row_text(clue, "owner", default=""),
                "input_refs": string_list(clue.get("input_refs", [])),
                "output_refs": string_list(clue.get("output_refs", [])),
                "equipment": row_text(
                    clue,
                    "equipment",
                    "tooling",
                    default=_library_equipment(operation),
                ),
                "tooling": row_text(clue, "tooling", "fixture", default=""),
                "gauges": string_list(
                    clue.get(
                        "gauges",
                        clue.get("inspection_gauges", clue.get("measurement_devices", [])),
                    )
                ),
                "documents": string_list(
                    clue.get("documents", clue.get("document_refs", clue.get("files", [])))
                ),
                "flow_type": flow_type,
                "flow_symbol": flow_type,
                "operation_type": flow_type_display(flow_type),
                "input_material": "",
                "output_result": operation,
                "special_characteristics": string_list(
                    clue.get("special_characteristics", clue.get("special_characteristic_refs", []))
                ),
                "evidence_refs": refs,
                "knowledge_source_refs": all_knowledge_refs,
                "ai_reasoning": row_text(
                    clue,
                    "reasoning",
                    "ai_reasoning",
                    default="根据图纸识别结果和工艺库推断",
                ),
                "confidence": _confidence(clue),
                "ai_inferred": True,
                "needs_confirmation": bool(clue.get("needs_confirmation", _confidence(clue) < 0.85)),
                "source": row_text(clue, "source", default="drawing_recognition"),
            }
        )
    return steps, pending_fields


def _finalize_process_flow(
    steps: list[dict[str, Any]],
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any] | None,
    pending_fields: list[str],
) -> dict[str, Any]:
    """Build metadata and assemble the final process_flow dict."""
    metadata: dict[str, Any] = {
        "generation_mode": "drawing_analysis_process_flow_inference",
        "llm_used": True,
        "source_stage": "drawing_analysis",
    }
    if family_context:
        metadata["family_context"] = {
            "family_key": family_context.get("family_key", ""),
            "family_name": family_context.get("family_name", ""),
            "confidence": family_context.get("confidence", 0.0),
        }

    normalize_process_flow_steps(steps)

    return {
        "document_type": "process_flow",
        "schema_version": "minos-core.generated.v1",
        "source_document_type": "drawing_analysis_bundle",
        "product": _product_from_drawing(analysis_bundle),
        "evidence": analysis_bundle.get("evidence", []),
        "drawings": [_drawing_from_identity(analysis_bundle.get("drawing_identity", {}))],
        "characteristics": _characteristics_from_drawing(analysis_bundle),
        "steps": steps,
        "links": _sequence_links(steps),
        "pending_fields": pending_fields,
        "ai_inferred_items": [step["process_step_id"] for step in steps],
        "metadata": metadata,
    }


def _sequence_links(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for current, nxt in zip(steps, steps[1:]):
        refs: list[str] = []
        for ref in current.get("evidence_refs", []) + nxt.get("evidence_refs", []):
            if ref not in refs:
                refs.append(ref)
        links.append(
            {
                "from": current["process_step_id"],
                "to": nxt["process_step_id"],
                "link_type": "sequence",
                "evidence_refs": refs,
                "ai_inferred": True,
                "needs_confirmation": current.get("needs_confirmation") or nxt.get("needs_confirmation"),
            }
        )
    return links


def _product_from_drawing(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    identity = analysis_bundle.get("drawing_identity", {})
    return {
        "part_name": row_text(identity, "part_name", "title", default=""),
        "part_number": row_text(identity, "drawing_number", "part_number", default=""),
        "revision": row_text(identity, "revision", default=""),
        "phase": "drawing_ai_draft",
    }


def _drawing_from_identity(identity: Any) -> dict[str, Any]:
    if not isinstance(identity, dict):
        identity = {}
    return {
        "drawing_id": row_text(identity, "drawing_number", "part_number", default=""),
        "title": row_text(identity, "part_name", "title", default=""),
        "revision": row_text(identity, "revision", default=""),
        "source_ref": _first_ref(identity),
    }


def _characteristics_from_drawing(analysis_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    characteristics: list[dict[str, Any]] = []
    for index, item in enumerate(analysis_bundle.get("special_characteristics", []), start=1):
        if not isinstance(item, dict):
            continue
        characteristics.append(
            {
                "characteristic_id": row_text(item, "id", "characteristic_id", default=f"SC-{index:03d}"),
                "name": row_text(item, "name", "characteristic", "description", "associated_feature", default=""),
                "classification": row_text(item, "classification", "category", default=""),
                "specification": row_text(item, "specification", "tolerance", default=""),
                "source_ref": _first_ref(item),
            }
        )
    return characteristics


def _normalize_step_id(value: str, index: int) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("P") and text[1:].isdigit():
        return f"P{int(text[1:])}"
    return f"P{index * 10}"


def _enrich_with_process_library(
    analysis_bundle: dict[str, Any],
    clues: list[dict[str, Any]],
    family_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if family_context and family_context.get("process_route_templates"):
        return _enrich_with_family_templates(analysis_bundle, clues, family_context)

    operations = [_operation_name(clue) for clue in clues]
    route_family = _route_family(analysis_bundle, operations)
    template = _ROUTE_TEMPLATES[route_family]
    evidence_refs = _bundle_evidence_refs(analysis_bundle)
    enriched: list[dict[str, Any]] = []
    added: set[str] = set()

    for operation in template:
        if _should_insert_before_clues(operation, operations):
            enriched.append(_library_clue(operation, route_family, evidence_refs))
            added.add(operation)

    for clue in clues:
        operation = _operation_name(clue)
        if not operation:
            enriched.append(clue)
            continue
        if operation not in added:
            enriched.append(_merge_library_defaults(clue, operation))
            added.add(operation)

    for operation in template:
        if operation in added:
            continue
        if _should_append_library_step(operation, route_family, operations, analysis_bundle):
            enriched.append(_library_clue(operation, route_family, evidence_refs))
            added.add(operation)

    return enriched


def _enrich_with_family_templates(
    analysis_bundle: dict[str, Any],
    clues: list[dict[str, Any]],
    family_context: dict[str, Any],
) -> list[dict[str, Any]]:
    templates = family_context.get("process_route_templates", [])
    if not templates:
        return _enrich_with_process_library(analysis_bundle, clues)

    # Pick the first template that actually has steps
    template: dict[str, Any] = {}
    template_steps: list[dict[str, Any]] = []
    for t in templates:
        steps = t.get("steps", [])
        if steps:
            template = t
            template_steps = steps
            break
    if not template_steps:
        return _enrich_with_process_library(analysis_bundle, clues)
    knowledge_refs = string_list(template.get("knowledge_source_refs", []))
    evidence_refs = _bundle_evidence_refs(analysis_bundle)

    # Normalize step format: support both operation_key (classifier) and operation (knowledge base)
    def _step_op_key(step: dict[str, Any]) -> str:
        op_key = str(step.get("operation_key", "")).strip()
        if not op_key:
            op_key = str(step.get("operation", "")).strip()
        return op_key

    def _step_op_display(step: dict[str, Any]) -> str:
        op_key = str(step.get("operation_key", "")).strip()
        if op_key:
            return _library_operation(op_key)
        return str(step.get("operation", "")).strip()

    def _step_confidence(step: dict[str, Any]) -> float:
        try:
            return float(step.get("confidence", 0.8))
        except (TypeError, ValueError):
            return 0.8

    template_ops: list[str] = []
    for step in template_steps:
        op_key = _step_op_key(step)
        if op_key:
            template_ops.append(op_key)

    # Also try process_inference variant matching
    extra_steps = _match_process_inference_variant(analysis_bundle, family_context)
    for s in extra_steps:
        op_key = _step_op_key(s)
        if op_key and op_key not in template_ops:
            template_ops.append(op_key)

    operations = [_operation_name(clue) for clue in clues]
    enriched: list[dict[str, Any]] = []
    added: set[str] = set()

    # Build a lookup: op_key -> original step dict
    all_steps_map: dict[str, dict[str, Any]] = {}
    for step in template_steps:
        op_key = _step_op_key(step)
        if op_key:
            all_steps_map[op_key] = step
    for s in extra_steps:
        op_key = _step_op_key(s)
        if op_key and op_key not in all_steps_map:
            all_steps_map[op_key] = s

    for op_key in template_ops:
        if _should_insert_before_clues(op_key, operations):
            orig_step = all_steps_map.get(op_key, {})
            enriched.append(_family_clue_from_step(
                op_key, orig_step, knowledge_refs, evidence_refs
            ))
            added.add(op_key)

    for clue in clues:
        operation = _operation_name(clue)
        if not operation:
            enriched.append(clue)
            continue
        if operation not in added:
            merged = _merge_library_defaults(clue, operation)
            if knowledge_refs:
                existing_refs = string_list(merged.get("knowledge_source_refs", []))
                for ref in knowledge_refs:
                    if ref not in existing_refs:
                        existing_refs.append(ref)
                merged["knowledge_source_refs"] = existing_refs
            merged.setdefault("source", "drawing_recognition")
            enriched.append(merged)
            added.add(operation)

    for op_key in template_ops:
        if op_key in added:
            continue
        # For family templates, append all remaining steps (not just library-compatible ones)
        if op_key not in ("incoming inspection", "material preparation"):
            orig_step = all_steps_map.get(op_key, {})
            enriched.append(_family_clue_from_step(
                op_key, orig_step, knowledge_refs, evidence_refs
            ))
            added.add(op_key)

    return enriched


def _family_clue_from_step(
    operation_key: str,
    orig_step: dict[str, Any],
    knowledge_refs: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Build a clue dict from a family template step, supporting both formats."""
    op_key = str(orig_step.get("operation_key", "")).strip()
    if op_key:
        operation = _library_operation(operation_key)
        process_function = _library_process_function(operation_key)
        equipment = _library_equipment(operation_key)
    else:
        operation = str(orig_step.get("operation", "")).strip() or _library_operation(operation_key)
        process_function = str(orig_step.get("process_function", "")).strip() or _library_process_function(operation_key)
        equipment = str(orig_step.get("equipment", "")).strip() or _library_equipment(operation_key)

    confidence = 0.8
    try:
        confidence = float(orig_step.get("confidence", 0.8))
    except (TypeError, ValueError):
        pass

    step_knowledge_refs = string_list(orig_step.get("knowledge_source_refs", []))
    all_knowledge_refs: list[str] = list(knowledge_refs)
    for ref in step_knowledge_refs:
        if ref not in all_knowledge_refs:
            all_knowledge_refs.append(ref)

    return {
        "operation": operation,
        "process_function": process_function,
        "equipment": equipment,
        "flow_type": _infer_flow_type(operation_key),
        "evidence_refs": list(evidence_refs),
        "knowledge_source_refs": all_knowledge_refs,
        "reasoning": str(orig_step.get("reasoning", "根据零件族知识库的工艺路线模板补充 PFD 工序")),
        "confidence": confidence,
        "needs_confirmation": bool(orig_step.get("needs_confirmation", True)),
        "source": "part_family_knowledge",
        "ai_inferred": True,
        "preserve_operation_name": bool(orig_step.get("preserve_operation_name", False)),
    }


def _match_process_inference_variant(
    analysis_bundle: dict[str, Any],
    family_context: dict[str, Any],
) -> list[dict[str, Any]]:
    process_inference = family_context.get("process_inference")
    if not isinstance(process_inference, dict):
        return []
    variants = process_inference.get("process_flow_variants")
    if not isinstance(variants, dict):
        # Also check extended variants
        variants = process_inference.get("process_flow_variants_extended")
        if not isinstance(variants, dict):
            return []
    search_text = " ".join(
        _analysis_text_values(
            analysis_bundle,
            ("technical_requirements", "materials", "drawing_identity"),
        )
    ).lower()
    if not search_text:
        return []
    for variant_id, variant_data in variants.items():
        if not isinstance(variant_data, dict):
            continue
        desc = str(variant_data.get("description", "")).lower()
        keywords = [str(k).lower() for k in string_list(variant_data.get("match_keywords", []))]
        # Check if significant character overlap exists between desc and search_text
        # Use 3-char ngrams to detect matching Chinese phrases despite punctuation differences
        def _ngrams(text: str, n: int = 4) -> set[str]:
            clean = ""
            for ch in text:
                if ch.isalpha() or ch in "()+-/" or '一' <= ch <= '鿿':
                    clean += ch
            return {clean[i:i+n] for i in range(len(clean) - n + 1)}

        desc_ngrams = _ngrams(desc, 4)
        search_ngrams = _ngrams(search_text, 4)
        overlap = desc_ngrams & search_ngrams
        direct_keywords = [str(k).lower() for k in keywords]
        if len(overlap) >= 2 or any(kw and kw in search_text for kw in direct_keywords):
            sequence = variant_data.get("process_sequence")
            if isinstance(sequence, list):
                return [
                    {
                        "operation": str(s.get("operation", "")).strip(),
                        "process_function": str(s.get("key_check", s.get("operation", ""))).strip(),
                        "confidence": 0.8,
                        "knowledge_source_refs": [
                            f"process_inference:{family_context.get('family_key', '')}:{variant_id}"
                        ],
                    }
                    for s in sequence
                    if isinstance(s, dict)
                ]
    return []


def _family_clue(
    operation_key: str,
    knowledge_refs: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "operation": _library_operation(operation_key),
        "process_function": _library_process_function(operation_key),
        "equipment": _library_equipment(operation_key),
        "flow_type": _infer_flow_type(operation_key),
        "evidence_refs": list(evidence_refs),
        "knowledge_source_refs": list(knowledge_refs),
        "reasoning": "根据零件族知识库的工艺路线模板补充 PFD 工序",
        "confidence": 0.8,
        "needs_confirmation": True,
        "source": "part_family_knowledge",
        "ai_inferred": True,
    }


def _operation_name(clue: dict[str, Any]) -> str:
    return _canonical_operation(
        row_text(clue, "operation", "process_step", "name", "process", default="")
    )


def _route_family(analysis_bundle: dict[str, Any], operations: list[str]) -> str:
    text = " ".join(
        operations
        + _analysis_text_values(
            analysis_bundle,
            (
                "materials",
                "surface_treatments",
                "dimensions",
                "technical_requirements",
                "inspection_requirements",
                "manufacturing_clues",
            ),
        )
    ).lower()
    if any(term in text for term in ("injection", "mold", "plastic", "resin", "注塑", "塑料", "树脂")):
        return "plastic_molded"
    if any(term in text for term in ("stamping", "sheet metal", "blanking", "piercing", "bending", "forming", "冲压", "钣金", "落料", "冲孔", "折弯", "成形")):
        return "sheet_metal"
    if any(term in text for term in ("machining", "cnc", "turning", "milling", "drilling", "tapping", "机加工", "车削", "铣削", "钻孔", "攻丝")):
        return "machined"
    if any(term in text for term in ("assembly", "rivet", "riveting", "press fit", "welding", "join", "装配", "铆接", "压装", "焊接", "连接")):
        return "assembly"
    return "generic"


def _analysis_text_values(
    value: Any, keys: tuple[str, ...] | None = None
) -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        items = value.items()
        for key, nested in items:
            if keys is not None and key not in keys:
                continue
            values.extend(_analysis_text_values(nested))
    elif isinstance(value, list):
        for item in value:
            values.extend(_analysis_text_values(item))
    elif isinstance(value, (str, int, float)):
        text = str(value).strip()
        if text:
            values.append(text)
    return values


def _bundle_evidence_refs(analysis_bundle: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for item in analysis_bundle.get("evidence", []):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("evidence_id", "")).strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _should_insert_before_clues(operation: str, operations: list[str]) -> bool:
    if not operations:
        return operation in {"incoming inspection", "material preparation"}
    return operation in {"incoming inspection", "material preparation"} and operation not in operations


def _should_append_library_step(
    operation: str,
    route_family: str,
    operations: list[str],
    analysis_bundle: dict[str, Any],
) -> bool:
    if operation in {"incoming inspection", "material preparation"}:
        return False
    if operation in {"process inspection", "final inspection", "packaging"}:
        return True
    if operation == "cleaning":
        return _has_surface_or_cleanliness_need(analysis_bundle, operations)
    if operation == "surface treatment":
        return _has_surface_treatment(analysis_bundle, operations)
    if route_family == "generic":
        return False
    if not operations:
        return True
    return operation in _template_core_operations(route_family) and not _has_related_operation(operation, operations)


def _template_core_operations(route_family: str) -> set[str]:
    return {
        "sheet_metal": {"blanking", "piercing", "forming", "deburr"},
        "machined": {"machining", "deburr"},
        "assembly": {"assembly"},
        "plastic_molded": {"injection molding", "trimming"},
    }.get(route_family, set())


def _has_related_operation(operation: str, operations: list[str]) -> bool:
    related = {
        "forming": {"forming", "bending"},
        "bending": {"forming", "bending"},
        "deburr": {"deburr", "trimming"},
        "surface treatment": {"surface treatment", "plating", "painting", "coating"},
        "machining": {"machining", "drilling", "tapping", "milling", "turning"},
        "assembly": {"assembly", "riveting", "press fitting", "welding"},
    }.get(operation, {operation})
    return any(any(term in existing for term in related) for existing in operations)


def _has_surface_treatment(analysis_bundle: dict[str, Any], operations: list[str]) -> bool:
    text = " ".join(operations + _analysis_text_values(analysis_bundle, ("surface_treatments", "technical_requirements"))).lower()
    return any(term in text for term in ("plating", "paint", "coating", "surface", "zinc", "phosphate", "anod"))


def _has_surface_or_cleanliness_need(
    analysis_bundle: dict[str, Any], operations: list[str]
) -> bool:
    text = " ".join(operations + _analysis_text_values(analysis_bundle, ("technical_requirements", "inspection_requirements"))).lower()
    return any(term in text for term in ("clean", "oil", "chip", "burr", "surface", "plating", "paint", "coating"))


def _infer_flow_type(operation_key: str) -> str:
    key = operation_key.lower()
    if any(t in key for t in ("inspection", "inspect", "test", "check", "verify", "检验")):
        return "inspection"
    if any(t in key for t in ("transport", "move", "handle")):
        return "transport"
    if any(t in key for t in ("stor", "warehouse")):
        return "storage"
    if any(t in key for t in ("rework", "repair")):
        return "rework"
    if any(t in key for t in ("outsource", "外协")):
        return "outsourced"
    return "operation"




def _library_clue(operation: str, route_family: str, evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "operation": _library_operation(operation),
        "process_function": _library_process_function(operation),
        "equipment": _library_equipment(operation),
        "flow_type": _infer_flow_type(operation),
        "evidence_refs": evidence_refs,
        "reasoning": f"根据{_route_family_text(route_family)}通用工艺库补充为常见 PFD 工序",
        "confidence": 0.72,
        "needs_confirmation": True,
        "source": "process_library",
    }


def _merge_library_defaults(clue: dict[str, Any], operation: str) -> dict[str, Any]:
    merged = dict(clue)
    merged["operation"] = _library_operation(operation)
    merged.setdefault("process_function", _library_process_function(operation))
    merged.setdefault("equipment", _library_equipment(operation))
    merged.setdefault("flow_type", _infer_flow_type(operation))
    merged.setdefault("source", "drawing_recognition")
    return merged


def _library_operation(operation: str) -> str:
    canonical = _canonical_operation(operation)
    return str(_PROCESS_LIBRARY.get(canonical, {}).get("operation", operation))


def _library_process_function(operation: str) -> str:
    canonical = _canonical_operation(operation)
    return str(
        _PROCESS_LIBRARY.get(canonical, {}).get(
            "process_function", f"执行{operation}"
        )
    )


def _library_equipment(operation: str) -> str:
    canonical = _canonical_operation(operation)
    return str(_PROCESS_LIBRARY.get(canonical, {}).get("equipment", ""))


def _expand_manufacturing_clues(value: Any) -> list[dict[str, Any]]:
    raw_clues = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    expanded: list[dict[str, Any]] = []
    sequence_index = 0
    for clue in raw_clues:
        process_sequence = clue.get("process_sequence")
        if isinstance(process_sequence, list) and process_sequence:
            for sequence_item in process_sequence:
                operation = _coerce_text(sequence_item)
                if not operation:
                    continue
                sequence_index += 1
                expanded.append(
                    {
                        "process_step_id": clue.get("process_step_id", f"P{sequence_index * 10}"),
                        "operation": operation,
                        "process_function": clue.get("process_function", ""),
                        "process_purpose": clue.get("process_purpose", clue.get("purpose", "")),
                        "product_characteristics": clue.get("product_characteristics", []),
                        "process_characteristics": clue.get("process_characteristics", []),
                        "owner": clue.get("owner", ""),
                        "equipment": clue.get("equipment", ""),
                        "tooling": clue.get("tooling", clue.get("fixture", "")),
                        "gauges": clue.get("gauges", clue.get("inspection_gauges", [])),
                        "documents": clue.get("documents", clue.get("document_refs", [])),
                        "flow_type": clue.get("flow_type", clue.get("process_type", "")),
                        "special_characteristics": clue.get(
                            "special_characteristics",
                            clue.get("special_characteristic_refs", []),
                        ),
                        "evidence_refs": clue.get("evidence_refs", []),
                        "reasoning": clue.get("reasoning", clue.get("source_text", "")),
                        "confidence": clue.get("confidence", 0.0),
                        "needs_confirmation": clue.get("needs_confirmation", False),
                    }
                )
            continue
        inferred_operations = _operations_from_free_text(
            row_text(clue, "operation", "process_step", "manufacturing_type", "clue", "basis", default="")
        )
        if inferred_operations:
            for operation in inferred_operations:
                sequence_index += 1
                expanded.append(
                    {
                        "process_step_id": clue.get("process_step_id", f"P{sequence_index * 10}"),
                        "operation": operation,
                        "process_function": clue.get("process_function", ""),
                        "process_purpose": clue.get("process_purpose", clue.get("purpose", "")),
                        "product_characteristics": clue.get("product_characteristics", []),
                        "process_characteristics": clue.get("process_characteristics", []),
                        "owner": clue.get("owner", ""),
                        "equipment": clue.get("equipment", ""),
                        "tooling": clue.get("tooling", clue.get("fixture", "")),
                        "gauges": clue.get("gauges", clue.get("inspection_gauges", [])),
                        "documents": clue.get("documents", clue.get("document_refs", [])),
                        "flow_type": clue.get("flow_type", clue.get("process_type", "")),
                        "special_characteristics": clue.get(
                            "special_characteristics",
                            clue.get("special_characteristic_refs", []),
                        ),
                        "evidence_refs": clue.get("evidence_refs", []),
                        "reasoning": clue.get("reasoning", clue.get("clue", clue.get("basis", ""))),
                        "confidence": clue.get("confidence", 0.0),
                        "needs_confirmation": True,
                    }
                )
            continue
        expanded.append(clue)
    return expanded


def _operations_from_free_text(text: str) -> list[str]:
    lowered = text.lower()
    if not lowered:
        return []
    operations: list[str] = []
    keyword_map = (
        ("blanking", "blanking"),
        ("piercing", "piercing"),
        ("bending", "bending"),
        ("forming", "forming"),
        ("welding", "welding"),
        ("assembly", "assembly"),
        ("deburr", "deburr"),
        ("plating", "plating"),
        ("painting", "painting"),
        ("inspection", "inspection"),
    )
    for needle, operation in keyword_map:
        if needle in lowered and operation not in operations:
            operations.append(operation)
    if "injection mold" in lowered or "injection molded" in lowered or "molded" in lowered:
        for operation in ("injection molding", "trimming", "inspection"):
            if operation not in operations:
                operations.append(operation)
    if "stamping" in lowered or "sheet metal" in lowered:
        for operation in ("blanking", "forming", "inspection"):
            if operation not in operations:
                operations.append(operation)
    return operations


_OPERATION_ALIASES: dict[str, str] = {
    "来料检验": "incoming inspection",
    "进料检验": "incoming inspection",
    "材料准备": "material preparation",
    "备料": "material preparation",
    "落料": "blanking",
    "下料": "blanking",
    "冲孔": "piercing",
    "折弯": "bending",
    "成形": "forming",
    "机加工": "machining",
    "钻孔": "drilling",
    "攻丝": "tapping",
    "去毛刺": "deburr",
    "清洗": "cleaning",
    "热处理": "heat treatment",
    "表面处理": "surface treatment",
    "电镀": "plating",
    "喷涂": "painting",
    "焊接": "welding",
    "铆接": "riveting",
    "压装": "press fitting",
    "装配": "assembly",
    "注塑": "injection molding",
    "修边": "trimming",
    "过程检验": "process inspection",
    "巡检": "process inspection",
    "最终检验": "final inspection",
    "终检": "final inspection",
    "包装": "packaging",
}


def _canonical_operation(operation: str) -> str:
    text = str(operation or "").strip().lower()
    if text in _PROCESS_LIBRARY:
        return text
    for alias, canonical in _OPERATION_ALIASES.items():
        if alias in str(operation or ""):
            return canonical
    return text


def _display_operation(operation: str, preserve: bool = False) -> str:
    if preserve:
        return operation
    canonical = _canonical_operation(operation)
    return _library_operation(canonical) if canonical in _PROCESS_LIBRARY else operation


def _route_family_text(route_family: str) -> str:
    return {
        "sheet_metal": "钣金/冲压",
        "machined": "机加工",
        "assembly": "装配",
        "plastic_molded": "注塑",
        "generic": "通用",
    }.get(route_family, route_family)


def normalize_process_flow_steps(
    steps: list[dict[str, Any]],
    default_input_material: str = "",
) -> None:
    """Fill in ``previous_step_ids`` / ``next_step_ids`` for linear flow.

    Existing non-empty values are preserved so that branches, rework loops,
    and outsourced steps already expressed by the knowledge base or LLM are
    not overwritten.
    """
    if not steps:
        return

    for step in steps:
        step.setdefault("previous_step_ids", [])
        step.setdefault("next_step_ids", [])

    for i, step in enumerate(steps):
        if default_input_material and i == 0 and not step.get("input_material"):
            step["input_material"] = default_input_material
        if i > 0:
            prev_id = steps[i - 1].get("process_step_id", "")
            if not step["previous_step_ids"] and prev_id:
                step["previous_step_ids"] = [prev_id]
        if i < len(steps) - 1:
            next_id = steps[i + 1].get("process_step_id", "")
            if not step["next_step_ids"] and next_id:
                step["next_step_ids"] = [next_id]


def _confidence(row: dict[str, Any]) -> float:
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _first_ref(row: dict[str, Any]) -> str:
    refs = string_list(row.get("evidence_refs", []))
    if refs:
        return refs[0]
    for value in row.values():
        if isinstance(value, dict):
            refs = string_list(value.get("evidence_refs", []))
            if refs:
                return refs[0]
    return ""


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


