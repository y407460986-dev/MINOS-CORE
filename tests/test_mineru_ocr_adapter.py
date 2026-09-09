import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from minos_core.adapters.mineru_ocr import MinerUOCRAdapter, _mineru_command_from_cmd
from minos_core.adapters.ocr import OCRDependencyError


class MinerUOCRAdapterTests(unittest.TestCase):
    def test_converts_markdown_parser_output_to_single_page_blocks(self):
        adapter = MinerUOCRAdapter(
            parser=lambda source_ref, content: "# Title\n\nFirst paragraph.\n\nSecond paragraph."
        )

        result = adapter.extract_text("drawing.pdf", b"%PDF fake")

        self.assertEqual(result.source_ref, "drawing.pdf")
        self.assertEqual(result.text, "# Title\nFirst paragraph.\nSecond paragraph.")
        self.assertEqual(len(result.pages), 1)
        page = result.pages[0]
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.engine, "mineru")
        self.assertEqual(page.source_ref, "drawing.pdf")
        self.assertEqual([block.text for block in page.blocks], ["# Title", "First paragraph.", "Second paragraph."])
        self.assertEqual([block.block_number for block in page.blocks], [1, 2, 3])
        self.assertTrue(all(block.engine == "mineru" for block in page.blocks))
        self.assertTrue(all(block.bbox is None for block in page.blocks))
        self.assertTrue(all(block.confidence is None for block in page.blocks))

    def test_converts_dict_pages_parser_output_to_ocr_pages(self):
        adapter = MinerUOCRAdapter(
            parser=lambda source_ref, content: {
                "pages": [
                    {"page_number": 3, "text": "Page 3 line A\n\nPage 3 line B"},
                    {"markdown": "Page 4 md"},
                ]
            }
        )

        result = adapter.extract_text("report.pdf", b"fake")

        self.assertEqual([page.page_number for page in result.pages], [3, 2])
        self.assertEqual(result.pages[0].text, "Page 3 line A\nPage 3 line B")
        self.assertEqual([block.text for block in result.pages[0].blocks], ["Page 3 line A", "Page 3 line B"])
        self.assertEqual(result.pages[1].text, "Page 4 md")
        self.assertEqual([block.text for block in result.pages[1].blocks], ["Page 4 md"])
        self.assertTrue(all(page.engine == "mineru" for page in result.pages))

    def test_raises_dependency_error_without_parser_or_available_mineru(self):
        adapter = MinerUOCRAdapter()

        with self.assertRaisesRegex(
            OCRDependencyError,
            r"MinerU|mineru optional tool",
        ):
            adapter.extract_text("drawing.pdf", b"fake")

    def test_uses_local_mineru_cli_output_when_available(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "mineru-output"
            output_dir.mkdir()
            markdown_path = output_dir / "drawing.md"
            markdown_path.write_text("Drawing No: CLI-001\n\nPart Name: CLI Bracket", encoding="utf-8")

            def fake_run(command, check, capture_output, text, **kwargs):
                self.assertEqual(command[0], "mineru")
                self.assertIn("-o", command)
                return _CompletedProcess()

            adapter = MinerUOCRAdapter(output_dir=output_dir)
            with patch("minos_core.adapters.mineru_ocr.shutil.which", return_value="mineru"):
                with patch("minos_core.adapters.mineru_ocr.subprocess.run", side_effect=fake_run):
                    result = adapter.extract_text(str(root / "drawing.pdf"), b"%PDF fake")

        self.assertEqual(result.pages[0].engine, "mineru")
        self.assertEqual(result.pages[0].blocks[0].text, "Drawing No: CLI-001")
        self.assertEqual(result.pages[0].blocks[1].text, "Part Name: CLI Bracket")

    def test_uses_mineru_markdown_output_when_cli_reports_late_failure(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "mineru-output"
            output_dir.mkdir()

            def fake_run(command, check, capture_output, text, **kwargs):
                (output_dir / "drawing.md").write_text(
                    "Drawing No: LATE-001\n\nPart Name: Salvaged Bracket",
                    encoding="utf-8",
                )
                raise subprocess.CalledProcessError(
                    1,
                    command,
                    stderr="All connection attempts failed",
                )

            adapter = MinerUOCRAdapter(output_dir=output_dir)
            with patch("minos_core.adapters.mineru_ocr.shutil.which", return_value="mineru"):
                with patch("minos_core.adapters.mineru_ocr.subprocess.run", side_effect=fake_run):
                    result = adapter.extract_text(str(root / "drawing.pdf"), b"%PDF fake")

        self.assertEqual(result.pages[0].blocks[0].text, "Drawing No: LATE-001")
        self.assertEqual(result.pages[0].blocks[1].text, "Part Name: Salvaged Bracket")

    def test_reads_mineru_command_from_codex_mcp_start_script(self):
        script = (
            '@echo off\n'
            'set "MINERU_COMMAND=C:\\Users\\fgtan\\mineru-runtime\\.venv\\Scripts\\mineru.exe"\n'
            'set "MINERU_MODEL_SOURCE=modelscope"\n'
        )

        self.assertEqual(
            _mineru_command_from_cmd(script),
            "C:\\Users\\fgtan\\mineru-runtime\\.venv\\Scripts\\mineru.exe",
        )

    def test_uses_mineru_command_discovered_from_codex_config(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "mineru-output"
            output_dir.mkdir()
            (output_dir / "drawing.md").write_text("Drawing No: MCP-001", encoding="utf-8")
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            mineru_exe = runtime_dir / "mineru.exe"
            mineru_exe.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
            config_path = root / ".codex" / "config.toml"
            script_path = root / "start-mineru-mcp.cmd"
            config_path.parent.mkdir()
            config_path.write_text(
                "[mcp_servers.mineru]\n"
                "args = [\n"
                '    "/c",\n'
                f"    '{script_path}',\n"
                "]\n",
                encoding="utf-8",
            )
            script_path.write_text(
                f'@echo off\nset "MINERU_COMMAND={mineru_exe}"\n',
                encoding="utf-8",
            )

            def fake_run(command, check, capture_output, text, **kwargs):
                self.assertEqual(command[0], str(mineru_exe))
                return _CompletedProcess()

            adapter = MinerUOCRAdapter(output_dir=output_dir)
            with (
                patch.dict("os.environ", {}, clear=True),
                patch("minos_core.adapters.mineru_ocr.Path.home", return_value=root),
                patch("minos_core.adapters.mineru_ocr.shutil.which", return_value=None),
                patch("minos_core.adapters.mineru_ocr.subprocess.run", side_effect=fake_run),
            ):
                result = adapter.extract_text(str(root / "drawing.pdf"), b"%PDF fake")

        self.assertEqual(result.pages[0].text, "Drawing No: MCP-001")


class _CompletedProcess:
    stdout = ""
    stderr = ""


if __name__ == "__main__":
    unittest.main()
