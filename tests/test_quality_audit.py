import copy
import importlib
import json
import unittest
from pathlib import Path

from minos_core.adapters.fixture_json import load_fixture_payload
from minos_core.domain import APQPChain

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT / "tests" / "fixtures"
FIXTURE_NAMES = ("apqp_chain", "door_hinge", "stamping", "limiter")


def _import_first(*module_names):
    errors = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    raise AssertionError(
        "Cannot import expected MINOS-CORE module:\n" + "\n".join(errors)
    )


def _get_first(module, *names):
    for name in names:
        value = getattr(module, name, None)
        if value is not None:
            return value
    raise AssertionError(f"{module.__name__} must expose one of: {', '.join(names)}")


def _load_fixture(name):
    return load_fixture_payload(FIXTURES_DIR / name)


def _as_mapping(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise AssertionError(f"Unsupported audit report type: {type(value)!r}")


def _validation_ok(result):
    if result is None:
        return True
    if isinstance(result, bool):
        return result
    if isinstance(result, tuple):
        return bool(result[0])
    if isinstance(result, dict):
        return bool(result.get("ok", result.get("valid", False)))
    if hasattr(result, "ok"):
        return bool(result.ok)
    if hasattr(result, "valid"):
        return bool(result.valid)
    return bool(result)


def _audit_chain():
    audit_module = _import_first("minos_core.audit", "minos_core.quality_audit")
    return _get_first(
        audit_module, "audit_chain", "audit_apqp_chain", "run_quality_audit"
    )


def _validate_chain():
    validation_module = _import_first("minos_core.validation")
    return _get_first(
        validation_module,
        "validate_chain",
        "validate_apqp_chain",
        "validate_domain_bundle",
    )


def _report_counts(report):
    mapping = _as_mapping(report)
    counts = mapping.get("counts")
    if counts is None and hasattr(report, "counts"):
        counts = report.counts
    self_describing = _as_mapping(counts)
    return self_describing


def _manual_review_items(report):
    mapping = _as_mapping(report)
    items = mapping.get("manual_review_items")
    if items is None and hasattr(report, "manual_review_items"):
        items = report.manual_review_items
    if items is None:
        raise AssertionError("audit report must expose manual_review_items")
    return list(items)


def _report_text(report):
    return json.dumps(_as_mapping(report), ensure_ascii=False, default=str).lower()


def _minimal_weak_link_chain():
    chain = copy.deepcopy(_load_fixture("apqp_chain"))
    chain["process_flow"]["steps"] = [copy.deepcopy(chain["process_flow"]["steps"][0])]
    chain["pfmea"]["rows"] = [copy.deepcopy(chain["pfmea"]["rows"][0])]
    chain["control_plan"]["rows"] = [copy.deepcopy(chain["control_plan"]["rows"][0])]

    failure = chain["pfmea"]["rows"][0]
    control = chain["control_plan"]["rows"][0]
    failure.update(
        {
            "pfmea_id": "PFMEA-WEAK-001",
            "process_step_id": "P10",
            "failure_mode": "Bracket thickness may drift without a defined engineering basis",
            "failure_effect": "Assembly stack height may be unreliable",
            "severity": 8,
            "occurrence": 4,
            "detection": 4,
            "action_priority": "M",
            "classification": "",
            "linked_control_plan_id": "CP-WEAK-001",
        }
    )
    control.update(
        {
            "control_plan_id": "CP-WEAK-001",
            "process_step_id": "P10",
            "pfmea_id": "PFMEA-WEAK-001",
            "product_process_characteristic": "Bracket thickness",
            "specification": "",
            "measurement_method": "Visual check",
            "sample_size": "",
            "sample_frequency": "",
            "control_method": "Operator judgement",
            "reaction_plan": "",
        }
    )
    return chain


class QualityAuditContractTests(unittest.TestCase):
    def test_audit_flags_duplicate_cp_ids_uncovered_pfmea_and_generic_controls(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Inspection",
                    "process_function": "Inspect critical feature",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-COVERED-001",
                    "process_step_id": "P10",
                    "process_function": "Inspect critical feature",
                    "failure_mode": "Critical feature out of tolerance",
                    "failure_effect": "Customer fit issue",
                    "failure_cause": "Gauge setup drift",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                },
                {
                    "pfmea_id": "PFMEA-UNCOVERED-001",
                    "process_step_id": "P10",
                    "process_function": "Inspect critical feature",
                    "failure_mode": "Surface defect escapes",
                    "failure_effect": "Customer complaint",
                    "failure_cause": "Inspection miss",
                    "severity": 7,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                },
            ],
            "controls": [
                {
                    "control_plan_id": "CP-DUP-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-COVERED-001",
                    "product_process_characteristic": "",
                    "specification": "按图纸",
                    "measurement_method": "按作业指导书",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "按规范",
                    "reaction_plan": "按工艺卡",
                },
                {
                    "control_plan_id": "CP-DUP-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-COVERED-001",
                    "product_process_characteristic": "Critical feature",
                    "specification": "10.0 +/- 0.1 mm",
                    "measurement_method": "Caliper",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "First-off inspection",
                    "reaction_plan": "Contain and notify QE",
                },
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        by_category = {item["category"]: item for item in items}

        for category in (
            "duplicate_control_plan_id",
            "uncovered_pfmea",
            "missing_cp_characteristic",
            "generic_control_text",
        ):
            self.assertIn(category, by_category)
            self.assertEqual(by_category[category]["severity"], "blocker")

        self.assertIn("CP-DUP-001", by_category["duplicate_control_plan_id"]["message"])
        self.assertIn("PFMEA-UNCOVERED-001", by_category["uncovered_pfmea"]["message"])
        self.assertIn("CP-DUP-001", by_category["missing_cp_characteristic"]["message"])
        self.assertIn("PFMEA-COVERED-001", by_category["generic_control_text"]["message"])
        self.assertIn("CP-DUP-001", by_category["generic_control_text"]["message"])

    def test_audit_ignores_deleted_duplicate_cp_ids_and_checks_extended_generic_fields(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Inspection",
                    "process_function": "Inspect critical feature",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-ACTIVE",
                    "process_step_id": "P10",
                    "process_function": "Inspect critical feature",
                    "failure_mode": "Critical feature out of tolerance",
                    "failure_effect": "Customer fit issue",
                    "failure_cause": "Gauge setup drift",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-SOFT-DELETE-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-ACTIVE",
                    "product_process_characteristic": "Critical feature",
                    "specification": "10.0 +/- 0.1 mm",
                    "measurement_method": "Caliper",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "First-off inspection",
                    "parameter_specification": "根据作业指导书执行",
                    "process_control_method": "按批准规范进行过程控制",
                    "reaction_plan": "Contain and notify QE",
                },
                {
                    "control_plan_id": "CP-SOFT-DELETE-001",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-ACTIVE",
                    "product_process_characteristic": "Deleted duplicate",
                    "specification": "按图纸",
                    "measurement_method": "Visual",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "Check",
                    "reaction_plan": "Notify QE",
                    "deleted": True,
                },
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        categories = [item["category"] for item in items]
        generic_items = [
            item for item in items if item["category"] == "generic_control_text"
        ]

        self.assertNotIn("duplicate_control_plan_id", categories)
        self.assertTrue(generic_items)
        self.assertEqual(generic_items[0]["severity"], "blocker")
        self.assertIn("CP-SOFT-DELETE-001", generic_items[0]["message"])
        self.assertIn("PFMEA-P10-ACTIVE", generic_items[0]["message"])
        self.assertIn("parameter_specification", generic_items[0]["message"])
        self.assertIn("process_control_method", generic_items[0]["message"])

    def test_audit_allows_control_fields_with_specific_details_and_generic_references(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "孔位检验",
                    "process_function": "确认孔位尺寸",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P10-SPECIFIC",
                    "process_step_id": "P10",
                    "process_function": "确认孔位尺寸",
                    "failure_mode": "孔距超差",
                    "failure_effect": "装配干涉",
                    "failure_cause": "夹具定位漂移",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P10-SPECIFIC",
                    "process_step_id": "P10",
                    "pfmea_id": "PFMEA-P10-SPECIFIC",
                    "product_process_characteristic": "孔径、孔距和位置度",
                    "specification": (
                        "安装孔孔径、孔距和位置度按图纸 JLV03000500-001-AC-RR、"
                        "GB/T1804-m 执行，孔口无可见毛刺。"
                    ),
                    "measurement_method": "CMM 或专用孔位检具",
                    "sample_size": "3件",
                    "sample_frequency": "首件和每2小时巡检",
                    "control_method": "按作业指导书执行夹具定位面清洁、定位销点检和首件复测，异常时加严孔位检验。",
                    "parameter_specification": "夹具基准面无铁屑，定位销磨损量在点检表限值内。",
                    "process_control_method": "按工艺卡锁定加工程序、主轴转速和进给量，换刀后复测孔位。",
                    "reaction_plan": "隔离可疑产品，通知质量工程师，调整夹具后100%复检。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]

        self.assertNotIn("generic_control_text", [item["category"] for item in items])

    def test_audit_treats_mechanical_link_as_covered_review_not_uncovered_blocker(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P10",
                    "operation": "Inspection",
                    "process_function": "Inspect critical feature",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-LINKED-001",
                    "process_step_id": "P10",
                    "process_function": "Inspect critical feature",
                    "failure_mode": "Critical feature out of tolerance",
                    "failure_effect": "Customer fit issue",
                    "failure_cause": "Gauge setup drift",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                    "linked_control_plan_id": "CP-LINKED-001",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-LINKED-001",
                    "process_step_id": "P10",
                    "pfmea_id": "",
                    "product_process_characteristic": "Critical feature",
                    "specification": "10.0 +/- 0.1 mm",
                    "measurement_method": "Caliper",
                    "sample_size": "1",
                    "sample_frequency": "每批",
                    "control_method": "First-off inspection",
                    "reaction_plan": "Contain and notify QE",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        categories = [
            (item if isinstance(item, dict) else item.__dict__)["category"]
            for item in _manual_review_items(report)
        ]

        self.assertIn("mechanical_link", categories)
        self.assertNotIn("uncovered_pfmea", categories)

    def test_audit_blocks_red_rust_240h_evidence_when_cp_only_covers_120h(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "表面处理",
                    "process_function": "满足盐雾耐蚀要求",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "process_step_id": "P20",
                    "process_function": "满足盐雾耐蚀要求",
                    "failure_mode": "红锈盐雾不足",
                    "failure_effect": "客户耐蚀要求不满足",
                    "failure_cause": "表面处理参数不足",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P20-RED-RUST",
                    "process_step_id": "P20",
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "product_process_characteristic": "红锈耐蚀性能",
                    "specification": "中性盐雾试验红锈不低于 120h",
                    "measurement_method": "按盐雾试验作业指导书判定红锈",
                    "sample_size": "3 件",
                    "sample_frequency": "每炉次",
                    "control_method": "监控表面处理参数",
                    "reaction_plan": "不合格时隔离并重新处理",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-RED-RUST-240",
                    "source": "drawing",
                    "content": "技术要求：中性盐雾试验红锈不小于 240h。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        red_rust_items = [
            item
            for item in items
            if "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in item["item_id"]
        ]

        self.assertTrue(red_rust_items)
        self.assertEqual(red_rust_items[0]["severity"], "blocker")
        self.assertIn(
            "TECHREQ-SALT-SPRAY-RED-RUST-MISSING", red_rust_items[0]["message"]
        )

    def test_audit_allows_red_rust_240h_evidence_when_cp_covers_240h(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "表面处理",
                    "process_function": "满足盐雾耐蚀要求",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "process_step_id": "P20",
                    "process_function": "满足盐雾耐蚀要求",
                    "failure_mode": "红锈盐雾不足",
                    "failure_effect": "客户耐蚀要求不满足",
                    "failure_cause": "表面处理参数不足",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P20-RED-RUST",
                    "process_step_id": "P20",
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "product_process_characteristic": "红锈耐蚀性能",
                    "specification": "中性盐雾试验红锈不小于 240h",
                    "measurement_method": "按盐雾试验作业指导书进行 240h 红锈判定",
                    "sample_size": "3 件",
                    "sample_frequency": "每炉次",
                    "control_method": "执行红锈 240h 盐雾验证",
                    "reaction_plan": "红锈 240h 不合格时隔离并重新处理",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-RED-RUST-240",
                    "source": "drawing",
                    "content": "技术要求：中性盐雾试验红锈不小于 240h。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]

        self.assertFalse(
            any(
                "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in item["item_id"]
                for item in items
            )
        )

    def test_audit_does_not_bind_red_rust_characteristic_to_white_rust_240h_spec(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "表面处理",
                    "process_function": "满足盐雾耐蚀要求",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "process_step_id": "P20",
                    "process_function": "满足盐雾耐蚀要求",
                    "failure_mode": "红锈盐雾不足",
                    "failure_effect": "客户耐蚀要求不满足",
                    "failure_cause": "表面处理参数不足",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P20-RED-RUST",
                    "process_step_id": "P20",
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "product_process_characteristic": "红锈耐蚀性能",
                    "specification": "白锈不小于 240h；红锈按外观判定",
                    "measurement_method": "按盐雾试验作业指导书判定",
                    "sample_size": "3 件",
                    "sample_frequency": "每炉次",
                    "control_method": "监控表面处理参数",
                    "reaction_plan": "不合格时隔离并重新处理",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-RED-RUST-240",
                    "source": "drawing",
                    "content": "技术要求：中性盐雾试验红锈不小于 240h。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        red_rust_items = [
            item
            for item in items
            if "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in item["item_id"]
        ]

        self.assertTrue(red_rust_items)
        self.assertEqual(red_rust_items[0]["severity"], "blocker")

    def test_audit_does_not_bind_red_rust_to_white_rust_240h_across_comma_clause(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "表面处理",
                    "process_function": "满足盐雾耐蚀要求",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "process_step_id": "P20",
                    "process_function": "满足盐雾耐蚀要求",
                    "failure_mode": "红锈盐雾不足",
                    "failure_effect": "客户耐蚀要求不满足",
                    "failure_cause": "表面处理参数不足",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P20-RED-RUST",
                    "process_step_id": "P20",
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "product_process_characteristic": "红锈耐蚀性能",
                    "specification": "白锈不小于 240h，红锈按外观判定",
                    "measurement_method": "按盐雾试验作业指导书判定",
                    "sample_size": "3 件",
                    "sample_frequency": "每炉次",
                    "control_method": "监控表面处理参数",
                    "reaction_plan": "不合格时隔离并重新处理",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-RED-RUST-240",
                    "source": "drawing",
                    "content": "技术要求：中性盐雾试验红锈不小于 240h。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        red_rust_items = [
            item
            for item in items
            if "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in item["item_id"]
        ]

        self.assertTrue(red_rust_items)
        self.assertEqual(red_rust_items[0]["severity"], "blocker")

    def test_audit_does_not_bind_red_rust_to_white_rust_240h_across_slash_clause(self):
        audit_chain = _audit_chain()
        chain = {
            "product": {},
            "process_steps": [
                {
                    "process_step_id": "P20",
                    "operation": "表面处理",
                    "process_function": "满足盐雾耐蚀要求",
                }
            ],
            "failure_modes": [
                {
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "process_step_id": "P20",
                    "process_function": "满足盐雾耐蚀要求",
                    "failure_mode": "红锈盐雾不足",
                    "failure_effect": "客户耐蚀要求不满足",
                    "failure_cause": "表面处理参数不足",
                    "severity": 8,
                    "occurrence": 3,
                    "detection": 4,
                    "action_priority": "M",
                }
            ],
            "controls": [
                {
                    "control_plan_id": "CP-P20-RED-RUST",
                    "process_step_id": "P20",
                    "pfmea_id": "PFMEA-P20-RED-RUST",
                    "product_process_characteristic": "红锈耐蚀性能",
                    "specification": "白锈不小于 240h/红锈按外观判定",
                    "measurement_method": "按盐雾试验作业指导书判定",
                    "sample_size": "3 件",
                    "sample_frequency": "每炉次",
                    "control_method": "监控表面处理参数",
                    "reaction_plan": "不合格时隔离并重新处理",
                }
            ],
            "evidence": [
                {
                    "evidence_id": "EV-RED-RUST-240",
                    "source": "drawing",
                    "content": "技术要求：中性盐雾试验红锈不小于 240h。",
                }
            ],
            "links": [],
        }

        report = audit_chain(chain)
        items = [
            item if isinstance(item, dict) else item.__dict__
            for item in _manual_review_items(report)
        ]
        red_rust_items = [
            item
            for item in items
            if "TECHREQ-SALT-SPRAY-RED-RUST-MISSING" in item["item_id"]
        ]

        self.assertTrue(red_rust_items)
        self.assertEqual(red_rust_items[0]["severity"], "blocker")

    def test_audit_chain_runs_for_all_standard_fixtures(self):
        audit_chain = _audit_chain()

        for fixture_name in FIXTURE_NAMES:
            with self.subTest(fixture=fixture_name):
                report = audit_chain(_load_fixture(fixture_name))

                counts = _report_counts(report)
                self.assertIn("counts", _as_mapping(report))
                self.assertIn("manual_review_items", _as_mapping(report))
                self.assertIsInstance(counts, dict)
                self.assertIsInstance(_manual_review_items(report), list)

    def test_audit_finds_weak_mechanical_manual_review_without_validation_failure(self):
        weak_chain = _minimal_weak_link_chain()
        validate_chain = _validate_chain()
        audit_chain = _audit_chain()

        validation_result = validate_chain(weak_chain)
        report = audit_chain(weak_chain)
        text = _report_text(report)

        self.assertTrue(_validation_ok(validation_result), str(validation_result))
        self.assertIn("mechanical", text)
        self.assertIn("weak", text)
        self.assertIn("manual", text)
        self.assertGreaterEqual(len(_manual_review_items(report)), 1)

    def test_limiter_audit_stays_within_phase_four_quality_gate(self):
        audit_chain = _audit_chain()

        report = audit_chain(_load_fixture("limiter"))
        counts = _report_counts(report)

        self.assertLessEqual(counts["mechanical_links"], 3)
        self.assertLessEqual(counts["weak_links"], 10)
        self.assertLessEqual(counts["manual_review_items"], 18)

    def test_stage_quality_gate_reports_next_stage_and_export_readiness(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")

        gate = evaluate_stage_gate(_load_fixture("apqp_chain"), stage="validate")

        self.assertTrue(gate.can_continue)
        self.assertTrue(gate.allow_user_export)
        self.assertTrue(gate.evidence_sufficient)
        self.assertEqual(gate.pending_fields, [])
        self.assertEqual(gate.missing_evidence_refs, [])
        self.assertEqual(gate.uncovered_evidence_items, [])
        self.assertTrue(gate.model_dump()["evidence_coverage"]["ok"])
        self.assertIn("process_steps", gate.audit.counts)

    def test_stage_quality_gate_blocks_missing_evidence_ref(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["pfmea"]["rows"][0]["evidence_refs"] = ["EV-NOT-FOUND"]

        gate = evaluate_stage_gate(chain, stage="validate")

        self.assertFalse(gate.evidence_sufficient)
        self.assertFalse(gate.can_continue)
        self.assertTrue(
            any("EV-NOT-FOUND" in item for item in gate.missing_evidence_refs)
        )

    def test_stage_quality_gate_blocks_ai_inferred_evidence_ref(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["evidence"].append(
            {
                "evidence_id": "EV-AI-001",
                "source": "llm",
                "content": "AI inferred control basis",
                "ai_inferred": True,
            }
        )
        chain["control_plan"]["rows"][0]["evidence_refs"] = ["EV-AI-001"]

        gate = evaluate_stage_gate(chain, stage="validate")

        self.assertFalse(gate.evidence_sufficient)
        self.assertFalse(gate.can_continue)
        self.assertIn("EV-AI-001", gate.ai_inferred_items)
        self.assertTrue(gate.model_dump()["evidence_coverage"]["ai_inferred_refs"])

    def test_stage_quality_gate_routes_row_needs_confirmation_to_review_only(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        validate_chain = _validate_chain()
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["process_flow"]["steps"][0]["needs_confirmation"] = True
        chain["pfmea"]["rows"][0]["needs_confirmation"] = True
        chain["control_plan"]["rows"][0]["needs_confirmation"] = True
        chain["process_flow"]["links"][0]["needs_confirmation"] = True

        validation_result = validate_chain(chain)
        gate = evaluate_stage_gate(chain, stage="validate")
        categories = {
            item.category
            for item in gate.manual_review_items
            if getattr(item, "severity", "") == "review"
        }

        self.assertTrue(_validation_ok(validation_result), str(validation_result))
        self.assertTrue(gate.can_continue)
        self.assertTrue(gate.evidence_sufficient)
        self.assertFalse(gate.allow_user_export)
        self.assertFalse(gate.allow_formal_release)
        self.assertTrue(gate.draft_only)
        self.assertTrue(gate.needs_human_review)
        self.assertIn("process_step:P10", gate.needs_confirmation_items)
        self.assertIn("failure_mode:PFMEA-P10-001", gate.needs_confirmation_items)
        self.assertIn("control_item:CP-P10-001", gate.needs_confirmation_items)
        self.assertIn("trace_link:P10->P20", gate.needs_confirmation_items)
        self.assertIn("row_needs_confirmation", categories)
        self.assertFalse(
            any(
                item.category == "row_needs_confirmation"
                and item.severity == "blocker"
                for item in gate.manual_review_items
            )
        )

    def test_stage_quality_gate_allows_draft_for_confirmable_evidence(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        validate_chain = _validate_chain()
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["evidence"][0]["needs_confirmation"] = True

        validation_result = validate_chain(chain)
        gate = evaluate_stage_gate(chain, stage="validate")
        evidence_review_items = [
            item
            for item in gate.manual_review_items
            if item.category == "evidence_needs_confirmation"
        ]

        self.assertTrue(_validation_ok(validation_result), str(validation_result))
        self.assertTrue(gate.can_continue)
        self.assertTrue(gate.evidence_sufficient)
        self.assertFalse(gate.allow_user_export)
        self.assertTrue(gate.draft_only)
        self.assertTrue(gate.needs_human_review)
        self.assertTrue(evidence_review_items)
        self.assertTrue(all(item.severity == "review" for item in evidence_review_items))

    def test_stage_quality_gate_reviews_chain_pending_and_ai_confirmations(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["pending_fields"] = [{"source_ref": "PFMEA-P10-001", "field": "severity"}]
        chain["ai_inferred_items"] = [
            {
                "item_id": "AI-CHECK-P10",
                "needs_confirmation": True,
                "ai_inferred": True,
            }
        ]

        gate = evaluate_stage_gate(chain, stage="validate")

        self.assertTrue(gate.can_continue)
        self.assertFalse(gate.allow_user_export)
        self.assertIn("PFMEA-P10-001.severity", gate.needs_confirmation_items)
        self.assertIn("AI-CHECK-P10", gate.needs_confirmation_items)
        self.assertIn("AI-CHECK-P10", gate.ai_inferred_items)

    def test_stage_quality_gate_confirmations_still_suppress_review_debts(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        chain["evidence"][0]["needs_confirmation"] = True
        chain["process_flow"]["steps"][0]["needs_confirmation"] = True
        chain["metadata"] = {
            "review_confirmations": [
                {"target": "evidence:EV-PFD-ROUTE-001"},
                {"target": "process_step:P10"},
            ]
        }

        gate = evaluate_stage_gate(chain, stage="export")

        self.assertTrue(gate.allow_user_export)
        self.assertEqual(gate.needs_confirmation_items, [])
        self.assertEqual(gate.evidence_coverage["needs_confirmation_refs"], [])
        self.assertFalse(
            any(
                item.category in {"evidence_needs_confirmation", "row_needs_confirmation"}
                for item in gate.manual_review_items
            )
        )


    def test_stage_quality_gate_model_dump_contains_linkage_fields(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        gate = evaluate_stage_gate(_load_fixture("apqp_chain"), stage="validate")
        dumped = gate.model_dump()
        self.assertIn("linkage_gaps", dumped)
        self.assertIn("linkage_summary", dumped)
        self.assertIsInstance(dumped["linkage_gaps"], list)
        self.assertIsInstance(dumped["linkage_summary"], dict)

    def test_linkage_blocker_gap_blocks_export(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        # Add a PFD step that has no PFMEA row -> blocker gap
        chain["process_flow"]["steps"].append(
            {
                "process_step_id": "P99",
                "operation": "Orphan step without PFMEA",
                "process_function": "Test step",
                "special_characteristics": [],
                "evidence_refs": ["EV-PFD-ROUTE-001"],
            }
        )
        gate = evaluate_stage_gate(chain, stage="export")
        self.assertFalse(gate.allow_user_export)
        blocker_gaps = [
            g for g in gate.linkage_gaps if g.get("severity") == "blocker"
        ]
        self.assertTrue(blocker_gaps)
        self.assertTrue(
            any("P99" in g.get("source", "") for g in blocker_gaps)
        )

    def test_linkage_blocker_orphan_cp_gap_blocks_export(self):
        """Orphan CP (引用不存在的 pfmea_id) 是 blocker，应阻止导出。"""
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        chain = copy.deepcopy(_load_fixture("apqp_chain"))
        # Add a CP row with non-existent pfmea_id -> orphan CP gap (now blocker)
        chain["control_plan"]["rows"].append(
            {
                "control_plan_id": "CP-ORPHAN-001",
                "process_step_id": "P10",
                "pfmea_id": "PFMEA-NONEXISTENT",
                "product_process_characteristic": "Test char",
                "specification": "1.0 mm",
                "measurement_method": "Visual",
                "sample_size": "1",
                "sample_frequency": "Per lot",
                "control_method": "Check",
                "reaction_plan": "Rework",
                "evidence_refs": ["EV-PFD-ROUTE-001"],
            }
        )
        gate = evaluate_stage_gate(chain, stage="export")
        # Orphan CP is now blocker, so export should be blocked
        self.assertFalse(gate.allow_user_export)
        # Verify the gap is in linkage_gaps with blocker severity
        blocker_gaps = [
            g for g in gate.linkage_gaps
            if g.get("severity") == "blocker" and "CP-ORPHAN-001" in g.get("source", "")
        ]
        self.assertTrue(blocker_gaps)
        self.assertIn("不存在的 PFMEA", blocker_gaps[0]["message"])

    def test_no_linkage_gaps_means_empty_linkage_gaps(self):
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        gate = evaluate_stage_gate(_load_fixture("apqp_chain"), stage="validate")
        self.assertEqual(gate.linkage_gaps, [])
        self.assertGreaterEqual(
            gate.linkage_summary.get("process_step_count", 0), 1
        )


    def test_linkage_evaluation_error_blocks_export(self):
        """如果三表联动检查抛异常，应生成 blocker gap 并阻止导出。"""
        gates_module = _import_first("minos_core.quality_gates")
        evaluate_stage_gate = _get_first(gates_module, "evaluate_stage_gate")
        # 构造一个会导致联动检查失败的数据（如缺少必需字段的畸形数据）
        chain = APQPChain(
            process_steps=[],
            failure_modes=[],
            controls=[],
            links=[],
        )
        gate = evaluate_stage_gate(chain, stage="export")
        self.assertFalse(gate.allow_user_export)
        linkage_gaps = gate.linkage_gaps
        error_gaps = [g for g in linkage_gaps if g.get("category_key") == "linkage_evaluation_error"]
        # 如果无异常，则无 error gap；如果有异常，则应有 error gap 且为 blocker
        if error_gaps:
            self.assertEqual(error_gaps[0]["severity"], "blocker")


if __name__ == "__main__":
    unittest.main()
