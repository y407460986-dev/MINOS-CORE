import unittest

from minos_core.domain import (
    APQPChain,
    Characteristic,
    ControlItem,
    Drawing,
    Evidence,
    FailureMode,
    FailureModeCandidate,
    ProcessStep,
    Product,
    TraceLink,
)


class DomainMappingTests(unittest.TestCase):
    def test_from_mapping_rejects_non_mapping_inputs(self):
        cases = (
            Product,
            ProcessStep,
            Drawing,
            Characteristic,
            FailureModeCandidate,
            FailureMode,
            ControlItem,
            Evidence,
            TraceLink,
        )

        for cls in cases:
            with self.subTest(cls=cls.__name__):
                with self.assertRaisesRegex(TypeError, f"{cls.__name__}.from_mapping expected a mapping"):
                    cls.from_mapping(["not", "a", "mapping"])

    def test_apqp_chain_rejects_malformed_nested_mapping(self):
        with self.assertRaisesRegex(TypeError, "Product.from_mapping expected a mapping"):
            APQPChain(product=["not", "a", "mapping"])


if __name__ == "__main__":
    unittest.main()
