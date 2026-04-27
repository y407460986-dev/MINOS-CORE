"""Infer process-flow drafts from AI drawing analysis bundles."""

from __future__ import annotations

from typing import Any


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


def infer_process_flow_from_drawing(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a PFD draft from drawing manufacturing clues.

    The first implementation is deliberately conservative: it turns explicit
    manufacturing clues from the drawing-recognition bundle into ordered Pxx
    steps and keeps every step marked for review because the route is AI
    inferred from a drawing, not confirmed process planning.
    """

    clues = _expand_manufacturing_clues(analysis_bundle.get("manufacturing_clues", []))
    clues = _enrich_with_process_library(analysis_bundle, clues)
    steps: list[dict[str, Any]] = []
    pending_fields = list(analysis_bundle.get("pending_fields", []))
    for index, clue in enumerate(clues, start=1):
        operation = _display_operation(
            _text(clue, "operation", "process_step", "name", "process", default="")
        )
        refs = _string_list(clue.get("evidence_refs", []))
        if not operation:
            pending_fields.append(f"manufacturing_clues[{index - 1}].operation")
            continue
        step_id = _text(clue, "process_step_id", "step_id", default=f"P{index * 10}")
        steps.append(
            {
                "process_step_id": _normalize_step_id(step_id, index),
                "sequence": index * 10,
                "operation": operation,
                "process_function": _text(
                    clue,
                    "process_function",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "process_purpose": _text(
                    clue,
                    "process_purpose",
                    "purpose",
                    default=_library_process_function(operation),
                ),
                "product_characteristics": _string_list(
                    clue.get("product_characteristics", [])
                ),
                "process_characteristics": _string_list(
                    clue.get("process_characteristics", [])
                ),
                "owner": _text(clue, "owner", default=""),
                "input_refs": _string_list(clue.get("input_refs", [])),
                "output_refs": _string_list(clue.get("output_refs", [])),
                "equipment": _text(
                    clue,
                    "equipment",
                    "tooling",
                    default=_library_equipment(operation),
                ),
                "tooling": _text(clue, "tooling", "fixture", default=""),
                "gauges": _string_list(
                    clue.get(
                        "gauges",
                        clue.get("inspection_gauges", clue.get("measurement_devices", [])),
                    )
                ),
                "documents": _string_list(
                    clue.get("documents", clue.get("document_refs", clue.get("files", [])))
                ),
                "flow_type": _text(clue, "flow_type", "process_type", default=""),
                "special_characteristics": _string_list(
                    clue.get("special_characteristics", clue.get("special_characteristic_refs", []))
                ),
                "evidence_refs": refs,
                "ai_reasoning": _text(
                    clue,
                    "reasoning",
                    "ai_reasoning",
                    default="根据图纸识别结果和工艺库推断",
                ),
                "confidence": _confidence(clue),
                "ai_inferred": True,
                "needs_confirmation": bool(clue.get("needs_confirmation", _confidence(clue) < 0.85)),
                "source": _text(clue, "source", default="drawing_recognition"),
            }
        )

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
        "metadata": {
            "generation_mode": "drawing_analysis_process_flow_inference",
            "llm_used": True,
            "source_stage": "drawing_analysis",
        },
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
        "part_name": _text(identity, "part_name", "title", default=""),
        "part_number": _text(identity, "drawing_number", "part_number", default=""),
        "revision": _text(identity, "revision", default=""),
        "phase": "drawing_ai_draft",
    }


def _drawing_from_identity(identity: Any) -> dict[str, Any]:
    if not isinstance(identity, dict):
        identity = {}
    return {
        "drawing_id": _text(identity, "drawing_number", "part_number", default=""),
        "title": _text(identity, "part_name", "title", default=""),
        "revision": _text(identity, "revision", default=""),
        "source_ref": _first_ref(identity),
    }


def _characteristics_from_drawing(analysis_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    characteristics: list[dict[str, Any]] = []
    for index, item in enumerate(analysis_bundle.get("special_characteristics", []), start=1):
        if not isinstance(item, dict):
            continue
        characteristics.append(
            {
                "characteristic_id": _text(item, "id", "characteristic_id", default=f"SC-{index:03d}"),
                "name": _text(item, "name", "characteristic", "description", "associated_feature", default=""),
                "classification": _text(item, "classification", "category", default=""),
                "specification": _text(item, "specification", "tolerance", default=""),
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
    analysis_bundle: dict[str, Any], clues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
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


def _operation_name(clue: dict[str, Any]) -> str:
    return _canonical_operation(
        _text(clue, "operation", "process_step", "name", "process", default="")
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


def _library_clue(operation: str, route_family: str, evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "operation": _library_operation(operation),
        "process_function": _library_process_function(operation),
        "equipment": _library_equipment(operation),
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
            _text(clue, "operation", "process_step", "manufacturing_type", "clue", "basis", default="")
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


def _display_operation(operation: str) -> str:
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


def _text(row: Any, *keys: str, default: str = "") -> str:
    if not isinstance(row, dict):
        return default
    for key in keys:
        text = _coerce_text(row.get(key))
        if text:
            return text
    return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()]


def _confidence(row: dict[str, Any]) -> float:
    try:
        return float(row.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _first_ref(row: dict[str, Any]) -> str:
    refs = _string_list(row.get("evidence_refs", []))
    if refs:
        return refs[0]
    for value in row.values():
        if isinstance(value, dict):
            refs = _string_list(value.get("evidence_refs", []))
            if refs:
                return refs[0]
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    refs = _string_list(item.get("evidence_refs", []))
                    if refs:
                        return refs[0]
    return ""


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in (
            "value",
            "text",
            "name",
            "description",
            "requirement",
            "feature",
            "type",
            "id",
            "process_step",
            "operation",
        ):
            text = _coerce_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, list):
        for item in value:
            text = _coerce_text(item)
            if text:
                return text
        return ""
    return str(value).strip()
