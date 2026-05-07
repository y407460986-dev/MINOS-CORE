import unittest

from minos_core.quality_matching import overlap_score, quality_tokens


class QualityMatchingTests(unittest.TestCase):
    def test_quality_tokens_add_canonical_engineering_aliases(self):
        tokens = quality_tokens("压入力 5MPa", "防错自动监控", "生产日期追溯")

        self.assertIn("pressure", tokens)
        self.assertIn("poka_yoke", tokens)
        self.assertIn("marking", tokens)

    def test_overlap_score_is_zero_for_empty_side(self):
        self.assertEqual(overlap_score(set(), {"pressure"}), 0)
        self.assertGreater(
            overlap_score(
                quality_tokens("力矩 Nm"),
                quality_tokens("扭矩确认"),
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
