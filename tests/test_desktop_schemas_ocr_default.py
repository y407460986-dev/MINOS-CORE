import unittest

from minos_desktop.api.schemas import CreateProjectRequest


class CreateProjectRequestOcrDefaultTests(unittest.TestCase):
    def test_default_ocr_engine_is_mineru(self):
        request = CreateProjectRequest(project_name="demo")
        self.assertEqual(request.ocr_engine, "mineru")


if __name__ == "__main__":
    unittest.main()
