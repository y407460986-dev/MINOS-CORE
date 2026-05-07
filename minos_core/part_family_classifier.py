"""Rule-based part-family recognition from drawing analysis bundles."""

from __future__ import annotations

import copy
from typing import Any

from ._text_utils import float_value, row_text, string_list


AUTO_ACCEPT_CONFIDENCE = 0.78
CONFIRMATION_CONFIDENCE = 0.55

_SKIP_TEXT_KEYS = {
    "evidence_refs",
    "evidence_ref",
    "field_evidence_refs",
    "source_ref",
    "source_refs",
    "image_path",
    "path",
    "sha256",
    "engine",
    "page_number",
    "confidence",
    "ai_inferred",
    "ocr_inferred",
    "needs_confirmation",
    "bbox",
}


DEFAULT_FAMILY_INDEX: dict[str, dict[str, Any]] = {
    "stamping": {
        "family_key": "stamping",
        "family_name": "冲压件",
        "knowledge_source_refs": ["part_family:stamping:v1"],
        "indicators": [
            {"terms": ["冲压件", "冲压", "冲压成形件", "stamping", "stamped"], "weight": 0.34},
            {"terms": ["progressive die", "compound die", "级进模", "连续模"], "weight": 0.30},
            {"terms": ["sheet metal", "steel sheet", "板料", "钣金", "钣金件", "板金件"], "weight": 0.24},
            {"terms": ["blanking", "piercing", "落料", "冲孔", "切边", "修边"], "weight": 0.22},
            {"terms": ["forming", "bending", "flanging", "embossing", "成形", "折弯", "翻边", "加强筋"], "weight": 0.18},
            {"terms": ["press", "press line", "压力机"], "weight": 0.12},
            {"terms": ["spcc", "secc", "sgcc", "dc01", "冷轧板"], "weight": 0.10},
        ],
        "process_route_templates": [
            {
                "template_id": "route:stamping:base:v1",
                "knowledge_source_refs": ["part_family:stamping:v1", "route:stamping:base:v1"],
                "steps": [
                    {"operation_key": "incoming inspection", "confidence": 0.80},
                    {"operation_key": "material preparation", "confidence": 0.80},
                    {"operation_key": "blanking", "confidence": 0.78},
                    {"operation_key": "piercing", "confidence": 0.76},
                    {"operation_key": "forming", "confidence": 0.76},
                    {"operation_key": "deburr", "confidence": 0.74},
                    {"operation_key": "cleaning", "confidence": 0.72},
                    {"operation_key": "surface treatment", "confidence": 0.70},
                    {"operation_key": "process inspection", "confidence": 0.76},
                    {"operation_key": "final inspection", "confidence": 0.78},
                    {"operation_key": "packaging", "confidence": 0.78},
                ],
            }
        ],
    },
    "limiter": {
        "family_key": "limiter",
        "family_name": "限位器",
        "knowledge_source_refs": ["part_family:limiter:v1"],
        "indicators": [
            {"terms": ["限位器", "限位总成", "limiter", "travel limiter", "door limiter"], "weight": 0.42},
            {"terms": ["door check", "door checker", "check arm", "check strap", "车门限位", "车门限位器"], "weight": 0.38},
            {"terms": ["限位块", "止挡", "stopper", "limit stop", "限位臂", "限位杆", "限位槽"], "weight": 0.30},
            {"terms": ["保持力", "档位力", "限位力", "holding force", "detent force", "check force"], "weight": 0.20},
            {"terms": ["detent", "roller", "spring", "滚轮", "弹簧", "挡块", "限位销"], "weight": 0.16},
            {"terms": ["铆接", "压装", "riveting", "press fit"], "weight": 0.10},
        ],
        "process_route_templates": [
            {
                "template_id": "route:limiter:base:v1",
                "knowledge_source_refs": ["part_family:limiter:v1", "route:limiter:base:v1"],
                "steps": [
                    {"operation_key": "incoming inspection", "confidence": 0.80},
                    {"operation_key": "material preparation", "confidence": 0.78},
                    {"operation_key": "forming", "confidence": 0.72},
                    {"operation_key": "deburr", "confidence": 0.72},
                    {"operation_key": "surface treatment", "confidence": 0.70},
                    {"operation_key": "assembly", "confidence": 0.78},
                    {"operation_key": "riveting", "confidence": 0.76},
                    {"operation_key": "press fitting", "confidence": 0.74},
                    {"operation_key": "functional inspection", "confidence": 0.76},
                    {"operation_key": "final inspection", "confidence": 0.78},
                    {"operation_key": "packaging", "confidence": 0.78},
                ],
            }
        ],
    },
    "door_hinge": {
        "family_key": "door_hinge",
        "family_name": "门铰链",
        "knowledge_source_refs": ["part_family:door_hinge:v1"],
        "indicators": [
            {
                "terms": [
                    "门铰链", "车门铰链", "尾门铰链", "尾门较链", "背门铰链", "背门较链", "行李箱铰链",
                    "door hinge", "back door hinge", "tailgate hinge", "liftgate hinge", "rear door hinge",
                ],
                "weight": 0.46,
            },
            {
                "terms": ["hinge assembly", "hinge bracket", "hinge leaf", "dh assy", "铰链总成", "较链总成", "铰链支架", "铰链臂", "铰链座", "铰链板"],
                "weight": 0.36,
            },
            {"terms": ["hinge pin", "铰链销", "转轴销", "铰链轴", "销轴", "转轴"], "weight": 0.30},
            {"terms": ["rotation torque", "rotating torque", "转动力矩", "开闭力矩", "旋转力矩"], "weight": 0.20},
            {"terms": ["bushing", "衬套", "轴套"], "weight": 0.08},
            {"terms": ["riveting", "staking", "铆接", "旋铆"], "weight": 0.12},
            {"terms": ["opening angle", "开闭角度", "开启角度", "door opening", "润滑"], "weight": 0.12},
        ],
        "process_route_templates": [{
            "template_id": "route:door_hinge:base:v1",
            "knowledge_source_refs": ["part_family:door_hinge:v1", "route:door_hinge:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "blanking", "confidence": 0.72},
                {"operation_key": "piercing", "confidence": 0.72},
                {"operation_key": "forming", "confidence": 0.72},
                {"operation_key": "welding", "confidence": 0.66},
                {"operation_key": "surface treatment", "confidence": 0.70},
                {"operation_key": "assembly", "confidence": 0.78},
                {"operation_key": "riveting", "confidence": 0.76},
                {"operation_key": "lubrication", "confidence": 0.72},
                {"operation_key": "functional inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "stamping_bracket": {
        "family_key": "stamping_bracket",
        "family_name": "冲压支架",
        "knowledge_source_refs": ["part_family:stamping_bracket:v1"],
        "indicators": [
            {"terms": ["冲压支架", "安装支架", "mounting bracket", "stamping bracket", "bracket stamping", "プレスブラケット"], "weight": 0.40},
            {"terms": ["加强板", "reinforcement", "reinforcement plate", "补强板", "stiffener", "gusset"], "weight": 0.30},
            {"terms": ["progressive die", "级进模", "连续模", "顺送金型"], "weight": 0.26},
            {"terms": ["blanking", "piercing", "forming", "bending", "落料", "冲孔", "成形", "折弯", "曲げ加工"], "weight": 0.22},
            {"terms": ["spcc", "saph", "dc01", "冷轧板", "热轧板", "高强度钢板", "high strength steel"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:stamping_bracket:base:v1",
            "knowledge_source_refs": ["part_family:stamping_bracket:v1", "route:stamping_bracket:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "blanking", "confidence": 0.76},
                {"operation_key": "piercing", "confidence": 0.76},
                {"operation_key": "forming", "confidence": 0.74},
                {"operation_key": "bending", "confidence": 0.72},
                {"operation_key": "deburr", "confidence": 0.74},
                {"operation_key": "surface treatment", "confidence": 0.70},
                {"operation_key": "process inspection", "confidence": 0.76},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "deep_drawn_part": {
        "family_key": "deep_drawn_part",
        "family_name": "拉深件",
        "knowledge_source_refs": ["part_family:deep_drawn_part:v1"],
        "indicators": [
            {"terms": ["拉深件", "深拉深", "deep drawn", "deep drawing", "絞り加工", "深絞り"], "weight": 0.44},
            {"terms": ["油底壳", "oil pan", "端盖", "end cap", "cup", "壳体", "housing", "カップ", "ケース"], "weight": 0.30},
            {"terms": ["draw ratio", "拉深比", "limiting draw ratio", "変形率"], "weight": 0.18},
            {"terms": ["wrinkling", "earing", "fracture", "起皱", "制耳", "破裂", "しわ", "割れ"], "weight": 0.22},
            {"terms": ["spce", "spcd", "dc04", "dc06", "深冲钢板", "if steel", "アルミキルド鋼"], "weight": 0.16},
        ],
        "process_route_templates": [{
            "template_id": "route:deep_drawn_part:base:v1",
            "knowledge_source_refs": ["part_family:deep_drawn_part:v1", "route:deep_drawn_part:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "blanking", "confidence": 0.76},
                {"operation_key": "forming", "confidence": 0.74},
                {"operation_key": "piercing", "confidence": 0.72},
                {"operation_key": "deburr", "confidence": 0.74},
                {"operation_key": "cleaning", "confidence": 0.72},
                {"operation_key": "surface treatment", "confidence": 0.68},
                {"operation_key": "process inspection", "confidence": 0.76},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "spot_welded_part": {
        "family_key": "spot_welded_part",
        "family_name": "点焊组件",
        "knowledge_source_refs": ["part_family:spot_welded_part:v1"],
        "indicators": [
            {"terms": ["点焊组件", "点焊总成", "spot welded", "spot weld assembly", "スポット溶接"], "weight": 0.44},
            {"terms": ["body in white", "BIW", "车身钣金", "白车身", "sheet metal assembly", "钣金总成"], "weight": 0.34},
            {"terms": ["weld nugget", "焊核", "熔核", "nugget diameter", "ナゲット径"], "weight": 0.22},
            {"terms": ["electrode force", "weld schedule", "焊接参数", "溶接条件", "electrode cap", "电极帽"], "weight": 0.18},
            {"terms": ["expulsion", "spatter", "crack", "飞溅", "裂纹", "割れ", "チリ"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:spot_welded_part:base:v1",
            "knowledge_source_refs": ["part_family:spot_welded_part:v1", "route:spot_welded_part:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "assembly", "confidence": 0.76},
                {"operation_key": "welding", "confidence": 0.74},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "cold_headed_part": {
        "family_key": "cold_headed_part",
        "family_name": "冷镦件",
        "knowledge_source_refs": ["part_family:cold_headed_part:v1"],
        "indicators": [
            {"terms": ["冷镦件", "冷镦", "cold headed", "cold heading", "冷間鍛造", "ヘッダー加工"], "weight": 0.46},
            {"terms": ["bolt", "screw", "rivet", "pin", "螺栓", "螺钉", "铆钉", "销", "ボルト", "リベット"], "weight": 0.36},
            {"terms": ["ball stud", "球头销", "球头螺栓", "wheel bolt", "hub bolt", "ハブボルト"], "weight": 0.24},
            {"terms": ["wire coil", "coil feed", "盘条", "线材", "コイル材"], "weight": 0.16},
            {"terms": ["upsetting", "heading", "extrusion", "镦粗", "正挤压", "据込み"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:cold_headed_part:base:v1",
            "knowledge_source_refs": ["part_family:cold_headed_part:v1", "route:cold_headed_part:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "forming", "confidence": 0.74},
                {"operation_key": "deburr", "confidence": 0.72},
                {"operation_key": "heat treatment", "confidence": 0.68},
                {"operation_key": "surface treatment", "confidence": 0.66},
                {"operation_key": "process inspection", "confidence": 0.76},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "injection_molded": {
        "family_key": "injection_molded",
        "family_name": "注塑件",
        "knowledge_source_refs": ["part_family:injection_molded:v1"],
        "indicators": [
            {"terms": ["注塑件", "注塑成形", "injection molded", "injection moulded", "射出成形品", "プラスチック部品"], "weight": 0.44},
            {"terms": ["plastic part", "polymer", "树脂", "塑料", "树脂件", "プラスチック", "樹脂"], "weight": 0.34},
            {"terms": ["pa66", "pom", "pp", "abs", "pc", "pa6", "尼龙", "聚甲醛", "聚丙烯", "聚碳酸酯", "树脂", "工程塑料"], "weight": 0.22},
            {"terms": ["卡扣", "clip", "clip part", "塑料卡扣", "クリップ", "留め具", "housing cover", "壳体盖", "护套", "grommet", "索环"], "weight": 0.18},
            {"terms": ["short shot", "flash", "weld line", "sink mark", "缩水", "飞边", "熔接痕", "短射", "ヒケ", "バリ", "ウェルドライン"], "weight": 0.20},
            {"terms": ["mold cavity", "gate", "runner", "型腔", "浇口", "流道", "金型", "ゲート"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:injection_molded:base:v1",
            "knowledge_source_refs": ["part_family:injection_molded:v1", "route:injection_molded:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "injection molding", "confidence": 0.76},
                {"operation_key": "trimming", "confidence": 0.74},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "insert_molded": {
        "family_key": "insert_molded",
        "family_name": "嵌件注塑",
        "knowledge_source_refs": ["part_family:insert_molded:v1"],
        "indicators": [
            {"terms": ["嵌件注塑", "insert molding", "insert moulding", "overmolding", "インサート成形", "包胶"], "weight": 0.46},
            {"terms": ["metal insert", "金属嵌件", "bushing insert", "threaded insert", "インサート金具", "ねじインサート"], "weight": 0.34},
            {"terms": ["bond strength", "pull-out force", "torque resistance", "结合力", "拉拔力", "扭矩"], "weight": 0.20},
            {"terms": ["insert preheating", "insert placement", "嵌件预热", "嵌件放置", "位置決め"], "weight": 0.16},
        ],
        "process_route_templates": [{
            "template_id": "route:insert_molded:base:v1",
            "knowledge_source_refs": ["part_family:insert_molded:v1", "route:insert_molded:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "assembly", "confidence": 0.74},
                {"operation_key": "injection molding", "confidence": 0.72},
                {"operation_key": "trimming", "confidence": 0.72},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "die_cast_part": {
        "family_key": "die_cast_part",
        "family_name": "压铸件",
        "knowledge_source_refs": ["part_family:die_cast_part:v1"],
        "indicators": [
            {"terms": ["压铸件", "压铸", "die cast", "die casting", "ダイカスト", "アルミダイカスト"], "weight": 0.44},
            {"terms": ["aluminum casting", "zinc casting", "铝合金", "锌合金", "adc12", "a380", "アルミ合金", "亜鉛合金"], "weight": 0.34},
            {"terms": ["porosity", "cold shut", "gas porosity", "气孔", "冷隔", "缩松", "鋳巣", "引け巣"], "weight": 0.24},
            {"terms": ["hot chamber", "cold chamber", "热室", "冷室", "ホットチャンバー", "コールドチャンバー"], "weight": 0.18},
            {"terms": ["housing", "bracket", "cover", "壳体", "支架", "盖", "ケース", "カバー"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:die_cast_part:base:v1",
            "knowledge_source_refs": ["part_family:die_cast_part:v1", "route:die_cast_part:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "injection molding", "confidence": 0.74},
                {"operation_key": "trimming", "confidence": 0.74},
                {"operation_key": "deburr", "confidence": 0.72},
                {"operation_key": "machining", "confidence": 0.70},
                {"operation_key": "surface treatment", "confidence": 0.66},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "rubber_bonded": {
        "family_key": "rubber_bonded",
        "family_name": "橡胶硫化件",
        "knowledge_source_refs": ["part_family:rubber_bonded:v1"],
        "indicators": [
            {"terms": ["橡胶硫化件", "橡胶件", "rubber bonded", "rubber molding", "ゴム部品", "加硫部品"], "weight": 0.44},
            {"terms": ["rubber bushing", "rubber mount", "橡胶衬套", "橡胶减震", "减震块", "悬置", "橡胶金属", "ゴムブッシュ"], "weight": 0.34},
            {"terms": ["rubber to metal bond", "橡胶金属粘接", "加硫接着", "vulcanization"], "weight": 0.24},
            {"terms": ["nr", "nbr", "epdm", "cr", "天然橡胶", "丁腈橡胶", "氯丁橡胶"], "weight": 0.18},
            {"terms": ["compression set", "tear strength", "hardness", "永久变形", "撕裂强度", "硬度"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:rubber_bonded:base:v1",
            "knowledge_source_refs": ["part_family:rubber_bonded:v1", "route:rubber_bonded:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "surface treatment", "confidence": 0.74},
                {"operation_key": "assembly", "confidence": 0.72},
                {"operation_key": "forming", "confidence": 0.70},
                {"operation_key": "trimming", "confidence": 0.74},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "welded_assembly": {
        "family_key": "welded_assembly",
        "family_name": "焊接总成",
        "knowledge_source_refs": ["part_family:welded_assembly:v1"],
        "indicators": [
            {"terms": ["焊接总成", "焊接组件", "welded assembly", "weld assembly", "溶接アセンブリ", "溶接組立品"], "weight": 0.44},
            {"terms": ["subframe", "cross member", "beam", "副车架", "横梁", "纵梁", "サブフレーム", "クロスメンバー"], "weight": 0.32},
            {"terms": ["gmaw", "mig welding", "mag welding", "二氧化碳焊", "氩弧焊", "气体保护焊", "マグ溶接"], "weight": 0.24},
            {"terms": ["weld penetration", "weld bead", "熔深", "焊道", "溶込み", "ビード"], "weight": 0.18},
            {"terms": ["distortion", "residual stress", "变形", "残余应力", "変形", "残留応力"], "weight": 0.14},
            {"terms": ["fixture", "jig", "定位夹具", "焊接工装", "治具", "取付具"], "weight": 0.12},
        ],
        "process_route_templates": [{
            "template_id": "route:welded_assembly:base:v1",
            "knowledge_source_refs": ["part_family:welded_assembly:v1", "route:welded_assembly:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "assembly", "confidence": 0.76},
                {"operation_key": "welding", "confidence": 0.74},
                {"operation_key": "deburr", "confidence": 0.72},
                {"operation_key": "cleaning", "confidence": 0.70},
                {"operation_key": "surface treatment", "confidence": 0.68},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "machined_shaft": {
        "family_key": "machined_shaft",
        "family_name": "机加工轴类",
        "knowledge_source_refs": ["part_family:machined_shaft:v1"],
        "indicators": [
            {"terms": ["轴类零件", "转轴", "销轴", "shaft", "pin", "axle", "spindle", "シャフト", "軸", "轴", "销", "ピン"], "weight": 0.42},
            {"terms": ["turning", "cylindrical grinding", "车削", "外圆磨", "旋削", "円筒研削"], "weight": 0.30},
            {"terms": ["roundness", "cylindricity", "runout", "圆度", "圆柱度", "跳动", "真円度", "振れ"], "weight": 0.22},
            {"terms": ["cnc lathe", "centerless grinding", "数控车床", "无心磨", "NC旋盤", "心なし研削"], "weight": 0.18},
            {"terms": ["表面淬火", "渗碳", "高频淬火", "induction hardening", "carburizing"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:machined_shaft:base:v1",
            "knowledge_source_refs": ["part_family:machined_shaft:v1", "route:machined_shaft:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "machining", "confidence": 0.76},
                {"operation_key": "drilling", "confidence": 0.72},
                {"operation_key": "tapping", "confidence": 0.70},
                {"operation_key": "heat treatment", "confidence": 0.70},
                {"operation_key": "deburr", "confidence": 0.74},
                {"operation_key": "surface treatment", "confidence": 0.66},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "machined_housing": {
        "family_key": "machined_housing",
        "family_name": "机加工壳体",
        "knowledge_source_refs": ["part_family:machined_housing:v1"],
        "indicators": [
            {"terms": ["壳体", "阀体", "泵体", "housing", "valve body", "pump housing", "ケース", "ハウジング", "バルブボディ"], "weight": 0.40},
            {"terms": ["milling", "boring", "drilling", "tapping", "铣削", "镗孔", "钻孔", "攻丝", "フライス加工", "中ぐり"], "weight": 0.32},
            {"terms": ["flatness", "perpendicularity", "position tolerance", "平面度", "垂直度", "位置度"], "weight": 0.24},
            {"terms": ["machining center", "cnc mill", "加工中心", "数控铣", "マシニングセンタ", "横中ぐり盤"], "weight": 0.20},
            {"terms": ["cast iron", "aluminum alloy", "铸铁", "铝合金", "鋳鉄", "アルミ合金"], "weight": 0.14},
        ],
        "process_route_templates": [{
            "template_id": "route:machined_housing:base:v1",
            "knowledge_source_refs": ["part_family:machined_housing:v1", "route:machined_housing:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "machining", "confidence": 0.76},
                {"operation_key": "drilling", "confidence": 0.74},
                {"operation_key": "tapping", "confidence": 0.72},
                {"operation_key": "deburr", "confidence": 0.74},
                {"operation_key": "cleaning", "confidence": 0.72},
                {"operation_key": "surface treatment", "confidence": 0.68},
                {"operation_key": "process inspection", "confidence": 0.78},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
    "assembly_module": {
        "family_key": "assembly_module",
        "family_name": "装配模块",
        "knowledge_source_refs": ["part_family:assembly_module:v1"],
        "indicators": [
            {"terms": ["装配模块", "总成", "assembly module", "assembly", "組立品", "アセンブリ"], "weight": 0.42},
            {"terms": ["hinge assy", "limiter assy", "latch assy", "铰链总成", "限位器总成", "门锁总成"], "weight": 0.34},
            {"terms": ["riveting", "press fitting", "torque", "铆接", "压装", "拧紧扭矩", "かしめ", "圧入", "締付トルク"], "weight": 0.26},
            {"terms": ["poka-yoke", "error proofing", "mistake proofing", "防错", "防呆", "ポカヨケ", "フールプルーフ"], "weight": 0.20},
            {"terms": ["function test", "leak test", "torque test", "功能测试", "气密测试", "力矩测试"], "weight": 0.18},
            {"terms": ["grease application", "lubrication", "注脂", "涂油", "润滑", "グリス塗布", "潤滑"], "weight": 0.12},
        ],
        "process_route_templates": [{
            "template_id": "route:assembly_module:base:v1",
            "knowledge_source_refs": ["part_family:assembly_module:v1", "route:assembly_module:base:v1"],
            "steps": [
                {"operation_key": "incoming inspection", "confidence": 0.80},
                {"operation_key": "material preparation", "confidence": 0.78},
                {"operation_key": "assembly", "confidence": 0.76},
                {"operation_key": "riveting", "confidence": 0.74},
                {"operation_key": "press fitting", "confidence": 0.72},
                {"operation_key": "lubrication", "confidence": 0.68},
                {"operation_key": "functional inspection", "confidence": 0.80},
                {"operation_key": "final inspection", "confidence": 0.78},
                {"operation_key": "packaging", "confidence": 0.78},
            ],
        }],
    },
}


def classify_part_family(
    drawing_analysis: dict[str, Any], family_index: Any | None = None
) -> dict[str, Any]:
    """Classify a drawing analysis bundle into a known part family."""

    families = _normalize_family_index(_load_family_index(family_index))
    text_nodes = _collect_text_nodes(drawing_analysis)
    scored = [
        _score_family(family, text_nodes)
        for family in families
        if family.get("family_key")
    ]
    scored.sort(key=lambda item: item["confidence"], reverse=True)

    best = scored[0] if scored else _unknown_candidate()
    if best["confidence"] < CONFIRMATION_CONFIDENCE:
        selected = {
            "family_key": "unknown",
            "family_name": "未知零件族",
            "confidence": best["confidence"],
            "matched_evidence": best["matched_evidence"],
            "needs_confirmation": True,
        }
        selected_family: dict[str, Any] = {}
    else:
        selected = {
            "family_key": best["family_key"],
            "family_name": best["family_name"],
            "confidence": best["confidence"],
            "matched_evidence": best["matched_evidence"],
            "needs_confirmation": best["confidence"] < AUTO_ACCEPT_CONFIDENCE,
        }
        selected_family = best["family"]

    alternative_families = [
        {
            "family_key": item["family_key"],
            "family_name": item["family_name"],
            "confidence": item["confidence"],
            "matched_terms": item["matched_terms"],
            "needs_confirmation": item["confidence"] < AUTO_ACCEPT_CONFIDENCE,
        }
        for item in scored
        if item["family_key"] != selected["family_key"]
    ][:3]

    selected["alternative_families"] = alternative_families
    if selected_family:
        selected["knowledge_source_refs"] = string_list(
            selected_family.get("knowledge_source_refs", [])
        )
        selected["process_route_templates"] = copy.deepcopy(
            selected_family.get("process_route_templates", [])
        )
    else:
        selected["knowledge_source_refs"] = []
        selected["process_route_templates"] = []
    return selected


def get_default_family_index() -> dict[str, dict[str, Any]]:
    """Return the built-in family index in the expected knowledge-module shape."""

    return copy.deepcopy(DEFAULT_FAMILY_INDEX)


def _load_family_index(family_index: Any | None) -> Any:
    if family_index is not None:
        return family_index() if callable(family_index) else family_index
    try:
        from . import part_family_knowledge
    except ImportError:
        return DEFAULT_FAMILY_INDEX

    for attr in (
        "get_part_family_index",
        "PART_FAMILY_INDEX",
        "FAMILY_INDEX",
        "part_family_index",
    ):
        value = getattr(part_family_knowledge, attr, None)
        if value is None:
            continue
        return value() if callable(value) else value
    return DEFAULT_FAMILY_INDEX


def _normalize_family_index(raw_index: Any) -> list[dict[str, Any]]:
    raw_index = raw_index() if callable(raw_index) else raw_index
    if isinstance(raw_index, dict) and "families" in raw_index:
        raw_families = raw_index["families"]
    elif isinstance(raw_index, dict):
        raw_families = list(raw_index.values())
    elif isinstance(raw_index, (list, tuple)):
        raw_families = list(raw_index)
    else:
        raw_families = []

    families: list[dict[str, Any]] = []
    for item in raw_families:
        if not isinstance(item, dict):
            continue
        family = copy.deepcopy(item)
        family_key = row_text(family, "family_key", "key", "id", default="")
        family_name = row_text(family, "family_name", "name", "display_name", default=family_key)
        family["family_key"] = family_key
        family["family_name"] = family_name
        family["indicators"] = _normalize_indicators(family)
        families.append(family)
    return families


def _normalize_indicators(family: dict[str, Any]) -> list[dict[str, Any]]:
    indicators = family.get("indicators")
    if isinstance(indicators, list):
        normalized: list[dict[str, Any]] = []
        for item in indicators:
            if isinstance(item, dict):
                terms = string_list(item.get("terms", item.get("keywords", [])))
                if not terms:
                    term = row_text(item, "term", "keyword", default="")
                    terms = [term] if term else []
                if terms:
                    normalized.append(
                        {"terms": terms, "weight": float_value(item.get("weight"), 0.12)}
                    )
            else:
                term = str(item).strip()
                if term:
                    normalized.append({"terms": [term], "weight": 0.12})
        if normalized:
            return normalized

    keywords = family.get("keywords", family.get("signals", {}))
    if isinstance(keywords, dict):
        weights = {
            "strong": 0.34,
            "high": 0.34,
            "medium": 0.20,
            "mid": 0.20,
            "weak": 0.10,
            "low": 0.10,
        }
        normalized = []
        for group, terms in keywords.items():
            for term in string_list(terms):
                normalized.append({"terms": [term], "weight": weights.get(str(group), 0.12)})
        return normalized
    return [{"terms": string_list(keywords), "weight": 0.12}]


def _score_family(family: dict[str, Any], text_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    raw_score = 0.0
    matched_terms: set[str] = set()
    matched_paths: set[str] = set()
    matched_evidence: list[dict[str, Any]] = []

    for indicator in family.get("indicators", []):
        terms = sorted(string_list(indicator.get("terms", [])), key=len, reverse=True)
        weight = float_value(indicator.get("weight"), 0.12)
        for term in terms:
            term_key = term.lower()
            if term_key in matched_terms:
                continue
            match = _best_matching_node(term, text_nodes)
            if match is None:
                continue
            field_weight = float_value(match.get("field_weight"), 1.0)
            weighted_score = weight * field_weight
            matched_terms.add(term_key)
            matched_paths.add(match["field_path"])
            raw_score += weighted_score
            matched_evidence.append(
                {
                    "family_key": family["family_key"],
                    "field_path": match["field_path"],
                    "matched_term": term,
                    "evidence_refs": match["evidence_refs"],
                    "weight": round(weight, 3),
                    "field_weight": round(field_weight, 3),
                    "weighted_score": round(weighted_score, 3),
                    "text": _snippet(match["text"]),
                }
            )

    diversity_bonus = min(0.08, max(0, len(matched_paths) - 1) * 0.02)
    strong_match_bonus = 0.04 if raw_score >= 0.50 and len(matched_terms) >= 2 else 0.0
    confidence = min(0.98, raw_score + diversity_bonus + strong_match_bonus)
    return {
        "family": family,
        "family_key": family["family_key"],
        "family_name": family["family_name"],
        "confidence": round(confidence, 3),
        "matched_terms": sorted(matched_terms),
        "matched_evidence": matched_evidence,
    }


def _best_matching_node(term: str, text_nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = term.lower()
    matches: list[dict[str, Any]] = []
    for node in text_nodes:
        if needle in node["text"].lower():
            matches.append(node)
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (
            float_value(item.get("field_weight"), 1.0),
            1.0 / max(1, len(str(item.get("text", "")))),
        ),
    )


def _collect_text_nodes(value: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    _collect_text_nodes_into(value, "$", [], nodes)
    return nodes


def _collect_text_nodes_into(
    value: Any, path: str, inherited_refs: list[str], nodes: list[dict[str, Any]]
) -> None:
    if isinstance(value, dict):
        refs = _refs_from(value) or inherited_refs
        if "content" in value and "evidence_id" in value:
            _append_text_node(
                nodes,
                f"{path}.content",
                value.get("content"),
                refs,
                value,
            )
        for key, nested in value.items():
            if key == "metadata":
                summary = nested.get("ocr_analysis_summary") if isinstance(nested, dict) else None
                if isinstance(summary, dict):
                    _collect_text_nodes_into(
                        summary,
                        f"{path}.metadata.ocr_analysis_summary",
                        refs,
                        nodes,
                    )
                continue
            if key in _SKIP_TEXT_KEYS or key == "content":
                continue
            _collect_text_nodes_into(nested, f"{path}.{key}", refs, nodes)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _collect_text_nodes_into(item, f"{path}[{index}]", inherited_refs, nodes)
        return
    if isinstance(value, (str, int, float)):
        _append_text_node(nodes, path, value, inherited_refs, {})


def _append_text_node(
    nodes: list[dict[str, Any]],
    path: str,
    value: Any,
    refs: list[str],
    row: dict[str, Any],
) -> None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return
    nodes.append(
        {
            "field_path": path,
            "text": text,
            "evidence_refs": list(refs),
            "field_weight": _field_weight(path, row),
        }
    )


def _field_weight(path: str, row: dict[str, Any] | None = None) -> float:
    lowered = path.lower()
    row = row or {}
    if ".drawing_identity.part_name" in lowered or ".drawing_identity.title" in lowered:
        return 1.85
    if ".metadata.ocr_analysis_summary.drawing_identity" in lowered:
        return 1.55
    if ".evidence[" in lowered and lowered.endswith(".content"):
        source = str(row.get("source", "")).lower()
        if source == "ocr_block":
            return 1.0
        return 0.75
    if ".technical_requirements" in lowered or ".inspection_requirements" in lowered:
        return 1.0
    if ".materials" in lowered or ".surface_treatments" in lowered:
        return 0.70
    if ".uncertainties" in lowered:
        return 0.55
    return 1.0


def _refs_from(row: dict[str, Any]) -> list[str]:
    refs = string_list(row.get("evidence_refs", []))
    if refs:
        return refs
    refs = string_list(row.get("evidence_ref", []))
    if refs:
        return refs
    refs = string_list(row.get("source_ref", []))
    if refs:
        return refs
    evidence_id = str(row.get("evidence_id", "")).strip()
    return [evidence_id] if evidence_id else []


def _unknown_candidate() -> dict[str, Any]:
    return {
        "family": {},
        "family_key": "unknown",
        "family_name": "未知零件族",
        "confidence": 0.0,
        "matched_terms": [],
        "matched_evidence": [],
    }


def _snippet(text: str) -> str:
    normalized = " ".join(str(text).split())
    return normalized[:180]
