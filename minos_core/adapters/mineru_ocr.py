"""MinerU OCR adapter for normalized OCR result conversion."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..observability.resources import temporary_directory
from .ocr import OCRBlock, OCRDependencyError, OCRPageText, OCRResult


def _no_window_creationflags() -> int:
    """Suppress the cmd.exe console window when spawning MinerU on Windows."""
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


MinerUParser = Callable[[str, bytes], Any]


class MinerUOCRAdapter:
    """Convert MinerU parser output into the common OCR result shape."""

    engine = "mineru"

    def __init__(
        self,
        parser: MinerUParser | None = None,
        output_dir: str | Path | None = None,
        mineru_command: str | Path | None = None,
    ) -> None:
        self._parser = parser
        self._output_dir = Path(output_dir) if output_dir is not None else None
        self._mineru_command = str(mineru_command) if mineru_command else None

    def extract_text(self, source_ref: str, content: bytes) -> OCRResult:
        raw_result = (
            self._parser(source_ref, content)
            if self._parser is not None
            else self._run_local_mineru(source_ref, content)
        )
        return OCRResult(
            source_ref=source_ref,
            pages=self._pages_from_result(raw_result, source_ref),
        )

    def _run_local_mineru(self, source_ref: str, content: bytes) -> str:
        mineru_command = self._resolve_mineru_command()
        if mineru_command is None:
            raise OCRDependencyError(
                "MinerUOCRAdapter requires a parser or MinerU command. "
                "Set MINOS_MINERU_COMMAND or MINERU_COMMAND, add mineru to PATH, "
                "or use the Codex MCP config fallback in development."
            )

        source_path = Path(str(source_ref))
        with temporary_directory(prefix="mineru-") as temp_root:
            input_path = source_path if source_path.exists() else temp_root / _source_filename(source_ref)
            if not input_path.exists():
                input_path.write_bytes(content)
            output_dir = self._output_dir or temp_root / "mineru-output"
            output_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    [mineru_command, "-p", str(input_path), "-o", str(output_dir), "-b", "pipeline"],
                    check=True,
                    capture_output=True,
                    text=True,
                    creationflags=_no_window_creationflags(),
                )
            except subprocess.CalledProcessError as exc:
                markdown = _read_first_markdown(output_dir)
                if markdown is not None:
                    return markdown
                message = getattr(exc, "stderr", "") or str(exc)
                raise OCRDependencyError(f"MinerU OCR failed: {message}") from exc
            except OSError as exc:
                raise OCRDependencyError(f"MinerU OCR failed: {exc}") from exc
            markdown = _read_first_markdown(output_dir)
            if markdown is None:
                raise OCRDependencyError(
                    f"MinerU OCR did not produce markdown output in {output_dir}"
                )
            return markdown

    def _resolve_mineru_command(self) -> str | None:
        candidates = [
            self._mineru_command,
            os.environ.get("MINOS_MINERU_COMMAND"),
            os.environ.get("MINERU_COMMAND"),
            shutil.which("mineru"),
            _mineru_command_from_codex_config(),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            candidate_text = str(candidate)
            if shutil.which(candidate_text) or Path(candidate_text).exists():
                return candidate_text
        return None

    def _pages_from_result(self, raw_result: Any, source_ref: str) -> list[OCRPageText]:
        if isinstance(raw_result, str):
            return [self._page_from_text(raw_result, source_ref, 1)]

        if isinstance(raw_result, dict):
            pages = raw_result.get("pages")
            if isinstance(pages, list):
                return [
                    self._page_from_page_item(page, source_ref, index)
                    for index, page in enumerate(pages, start=1)
                ]
            text = raw_result.get("markdown", raw_result.get("text", ""))
            return [self._page_from_text(str(text), source_ref, 1)]

        if isinstance(raw_result, list):
            return [
                self._page_from_page_item(page, source_ref, index)
                for index, page in enumerate(raw_result, start=1)
            ]

        return [self._page_from_text(str(raw_result or ""), source_ref, 1)]

    def _page_from_page_item(
        self,
        page_item: Any,
        source_ref: str,
        fallback_page_number: int,
    ) -> OCRPageText:
        if isinstance(page_item, dict):
            page_number = int(page_item.get("page_number", fallback_page_number))
            text = page_item.get("markdown", page_item.get("text", ""))
            return self._page_from_text(str(text), source_ref, page_number)
        return self._page_from_text(str(page_item), source_ref, fallback_page_number)

    def _page_from_text(
        self,
        text: str,
        source_ref: str,
        page_number: int,
    ) -> OCRPageText:
        block_texts = _paragraphs(text)
        blocks = [
            OCRBlock(
                block_number=index,
                text=block_text,
                confidence=None,
                bbox=None,
                engine=self.engine,
                source_ref=f"{source_ref}#page={page_number}",
            )
            for index, block_text in enumerate(block_texts, start=1)
        ]
        return OCRPageText(
            page_number=page_number,
            text="\n".join(block_texts),
            confidence=None,
            blocks=blocks,
            bbox=None,
            engine=self.engine,
            source_ref=source_ref,
        )


def _paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    current_lines: list[str] = []

    for line in str(text).splitlines():
        stripped = line.strip()
        if stripped:
            current_lines.append(stripped)
            continue
        if current_lines:
            paragraphs.append("\n".join(current_lines))
            current_lines = []

    if current_lines:
        paragraphs.append("\n".join(current_lines))

    return paragraphs


def _read_first_markdown(output_dir: Path) -> str | None:
    markdown_files = sorted(output_dir.rglob("*.md"))
    if not markdown_files:
        return None
    return markdown_files[0].read_text(encoding="utf-8")


def _source_filename(source_ref: str) -> str:
    suffix = Path(str(source_ref)).suffix or ".pdf"
    return f"mineru-input{suffix}"


def _mineru_command_from_codex_config(config_path: Path | None = None) -> str | None:
    path = config_path or Path.home() / ".codex" / "config.toml"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    script_path = _mineru_mcp_script_from_config(text)
    if script_path is None or not script_path.exists():
        return None
    try:
        script_text = script_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        script_text = script_path.read_text(encoding="mbcs", errors="ignore")
    except OSError:
        return None
    return _mineru_command_from_cmd(script_text)


def _mineru_mcp_script_from_config(text: str) -> Path | None:
    section_match = re.search(
        r"(?ms)^\[mcp_servers\.mineru\]\s*(.*?)(?=^\[|\Z)",
        text,
    )
    if section_match is None:
        return None
    section = section_match.group(1)
    for match in re.finditer(r"['\"]([^'\"]*start-mineru-mcp\.cmd)['\"]", section):
        return Path(match.group(1))
    for match in re.finditer(r"['\"]([^'\"]*mineru[^'\"]*\.cmd)['\"]", section):
        return Path(match.group(1))
    return None


def _mineru_command_from_cmd(text: str) -> str | None:
    match = re.search(r"(?im)^\s*set\s+\"MINERU_COMMAND=([^\"]+)\"", text)
    if match:
        return match.group(1).strip()
    match = re.search(r"(?im)^\s*set\s+MINERU_COMMAND=([^\r\n]+)", text)
    return match.group(1).strip().strip('"') if match else None
