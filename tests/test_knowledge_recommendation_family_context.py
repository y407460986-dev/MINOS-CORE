import unittest

from minos_core.knowledge_recommendation import recommend_from_knowledge


class KnowledgeRecommendationFamilyContextTests(unittest.TestCase):
    def test_family_patterns_generate_scored_pfmea_and_control_plan_recommendations(self):
        source = _source()
        family_context = {
            "family_key": "stamping",
            "family_name": "冲压件",
            "pfmea_patterns": [
                {
                    "pattern_id": "stamping-pfmea-hole",
                    "process_step_id": "P20",
                    "failure_mode": "孔径超差",
                    "failure_cause": "冲头磨损或废料堆积",
                    "prevention_control": "换型前确认冲头状态",
                    "source_refs": [{"source_id": "seed-pfmea", "row": 18}],
                }
            ],
            "control_plan_patterns": [
                {
                    "pattern_id": "stamping-cp-hole",
                    "process_step_id": "P20",
                    "characteristic": "孔径",
                    "classification": "SC",
                    "measurement_method": "通止规和位置度检具",
                    "sample_frequency": "首件和每小时巡检",
                    "reaction_plan": "停机隔离并通知质量工程师",
                    "source_refs": [{"source_id": "seed-cp", "row": 22}],
                }
            ],
        }

        recs = recommend_from_knowledge(source, rules=[], family_context=family_context)

        pfmea_rec = next(item for item in recs if item["recommendation_type"] == "pfmea_pattern")
        self.assertEqual(pfmea_rec["score"], 100)
        self.assertEqual(pfmea_rec["match_level"], "family_operation_characteristic")
        self.assertEqual(pfmea_rec["source_refs"][0]["source_id"], "seed-pfmea")
        self.assertIn("pfmea.failure_cause", pfmea_rec["target_field_keys"])

        cp_rec = next(item for item in recs if item["recommendation_type"] == "control_plan_pattern")
        self.assertEqual(cp_rec["score"], 100)
        self.assertEqual(cp_rec["match_level"], "family_operation_characteristic")
        self.assertIn("control_plan.measurement_method", cp_rec["target_field_keys"])
        self.assertIn("pfmea.classification", cp_rec["target_field_keys"])

    def test_same_target_type_and_field_set_keeps_highest_score(self):
        family_context = {
            "family_key": "stamping",
            "family_name": "冲压件",
            "pfmea_patterns": [
                {
                    "pattern_id": "same-operation-only",
                    "process_step_id": "P20",
                    "failure_cause": "冲头磨损",
                },
                {
                    "pattern_id": "same-operation-and-characteristic",
                    "process_step_id": "P20",
                    "characteristic": "孔径",
                    "failure_cause": "冲头磨损",
                },
            ],
        }

        recs = recommend_from_knowledge(_source(), rules=[], family_context=family_context)
        pfmea_recs = [item for item in recs if item["recommendation_type"] == "pfmea_pattern"]

        self.assertEqual(len(pfmea_recs), 1)
        self.assertEqual(pfmea_recs[0]["source"], "same-operation-and-characteristic")
        self.assertEqual(pfmea_recs[0]["score"], 100)

    def test_global_family_pattern_scores_55(self):
        family_context = {
            "family_key": "stamping",
            "family_name": "冲压件",
            "pfmea_patterns": [
                {
                    "pattern_id": "global-pfmea-review",
                    "failure_cause": "按同类零件经验复核过程参数窗口",
                }
            ],
        }

        recs = recommend_from_knowledge(_source(), rules=[], family_context=family_context)

        self.assertEqual(recs[0]["score"], 55)
        self.assertEqual(recs[0]["match_level"], "global")

    def test_generic_special_characteristic_rule_has_one_primary_recommendation_per_row(self):
        rules = [
            {
                "rule_id": "KR-SC-A",
                "special_characteristic_required": True,
                "recommendation_type": "控制计划",
                "message": "补充特殊特性频次",
                "suggested_fields": {"sample_frequency": "首件"},
                "confidence": 0.7,
            },
            {
                "rule_id": "KR-SC-B",
                "special_characteristic_required": True,
                "recommendation_type": "控制计划",
                "message": "补充特殊特性反应计划",
                "suggested_fields": {"reaction_plan": "停机隔离"},
                "confidence": 0.9,
            },
        ]

        recs = recommend_from_knowledge(_source(), rules=rules)

        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["source"], "KR-SC-B")
        self.assertEqual(recs[0]["score"], 90)


def _source():
    return {
        "document_type": "apqp_chain",
        "process_steps": [
            {
                "process_step_id": "P20",
                "operation": "冲孔",
                "process_function": "形成安装孔径",
                "special_characteristics": ["孔径"],
            }
        ],
        "failure_modes": [
            {
                "pfmea_id": "PFMEA-P20-001",
                "process_step_id": "P20",
                "failure_mode": "孔径超差",
                "failure_effect": "装配困难",
                "failure_cause": "",
                "classification": "SC",
                "characteristic_refs": ["孔径"],
                "prevention_control": "",
                "detection_control": "",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
