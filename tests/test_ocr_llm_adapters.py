import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdapterBoundaryTests(unittest.TestCase):
    def test_fake_ocr_adapter_returns_configured_text(self):
        from minos_core.adapters.ocr import FakeOCRAdapter

        result = FakeOCRAdapter("hello ocr").extract_text("drawing.pdf", b"fake")

        self.assertEqual(result.source_ref, "drawing.pdf")
        self.assertEqual(result.text, "hello ocr")
        self.assertEqual(result.pages[0].page_number, 1)
        self.assertEqual(result.pages[0].confidence, 1.0)

    def test_not_implemented_ocr_adapter_raises(self):
        from minos_core.adapters.ocr import NotImplementedOCRAdapter

        with self.assertRaises(NotImplementedError):
            NotImplementedOCRAdapter().extract_text("drawing.pdf", b"fake")

    def test_fake_llm_adapter_returns_configured_content(self):
        from minos_core.adapters.llm import FakeLLMAdapter, LLMMessage

        result = FakeLLMAdapter("analysis result").complete(
            [LLMMessage(role="user", content="input")]
        )

        self.assertEqual(result.content, "analysis result")
        self.assertEqual(result.model, "fake")
        self.assertEqual(result.metadata["message_count"], 1)

    def test_not_implemented_llm_adapter_raises(self):
        from minos_core.adapters.llm import LLMMessage, NotImplementedLLMAdapter

        with self.assertRaises(NotImplementedError):
            NotImplementedLLMAdapter().complete(
                [LLMMessage(role="user", content="input")]
            )

    def test_domain_core_does_not_import_ocr_or_llm_adapters(self):
        domain_source = (ROOT / "minos_core" / "domain.py").read_text(encoding="utf-8")

        self.assertNotIn("adapters.ocr", domain_source)
        self.assertNotIn("adapters.llm", domain_source)
        self.assertNotIn("OCRAdapter", domain_source)
        self.assertNotIn("LLMAdapter", domain_source)


if __name__ == "__main__":
    unittest.main()
