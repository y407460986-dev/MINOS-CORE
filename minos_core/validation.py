"""Validation rules for APQP chains and input validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any

from .domain import APQPChain

MOJIBAKE_MARKERS = ("�", "Ã", "Â", "å", "æ", "ä¸", "é", "ï¿½")


@dataclass(frozen=True)
class ChainValidationResult:
    ok: bool
    messages: list[str]
    chain: APQPChain

    @property
    def valid(self) -> bool:
        return self.ok

    def __bool__(self) -> bool:
        return self.ok

    def __str__(self) -> str:
        return "OK" if self.ok else "\n".join(self.messages)


def validate_chain(chain: APQPChain | dict[str, Any]) -> ChainValidationResult:
    """Validate text integrity and PFD/PFMEA/CP linkage rules."""

    if isinstance(chain, dict):
        chain = APQPChain(**chain)
    issues: list[str] = []
    issues.extend(_mojibake_issues(chain))
    issues.extend(_pfd_pfmea_issues(chain))
    issues.extend(_mandatory_cp_issues(chain))
    if _strict_three_table_linkage_enabled(chain):
        issues.extend(_three_table_linkage_issues(chain))
    return ChainValidationResult(ok=not issues, messages=issues, chain=chain)


def _strict_three_table_linkage_enabled(chain: APQPChain) -> bool:
    metadata = chain.metadata if isinstance(chain.metadata, dict) else {}
    if metadata.get("strict_three_table_linkage"):
        return True
    if metadata.get("generated") is True:
        return True
    if metadata.get("edit_history"):
        return True
    generation_mode = str(metadata.get("generation_mode", "")).strip()
    if generation_mode in {
        "ai_drawing_three_table_generation",
        "human_edited_three_table_generation",
    }:
        return True
    generation_modes = metadata.get("generation_modes", [])
    if isinstance(generation_modes, list):
        return any(
            str(mode).strip()
            in {
                "drawing_analysis_process_flow_inference",
                "process_flow_pfmea_ai_draft",
                "pfmea_control_plan_rules",
            }
            for mode in generation_modes
        )
    return False


def _mojibake_issues(value: Any, path: str = "chain") -> list[str]:
    issues: list[str] = []
    if isinstance(value, str):
        if any(marker in value for marker in MOJIBAKE_MARKERS):
            issues.append(f"{path} contains possible mojibake: {value!r}")
        return issues
    if is_dataclass(value):
        for item in fields(value):
            issues.extend(_mojibake_issues(getattr(value, item.name), f"{path}.{item.name}"))
        return issues
    if isinstance(value, dict):
        for key, item in value.items():
            issues.extend(_mojibake_issues(item, f"{path}.{key}"))
        return issues
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            issues.extend(_mojibake_issues(item, f"{path}[{index}]"))
    return issues


def _pfd_pfmea_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    step_ids = {step.process_step_id for step in chain.process_steps}
    pfmea_step_ids = {item.process_step_id for item in chain.failure_modes}

    for step_id in sorted(step_ids - pfmea_step_ids):
        issues.append(f"process step {step_id!r} has no PFMEA row")
    for step_id in sorted(pfmea_step_ids - step_ids):
        issues.append(f"PFMEA references missing process step {step_id!r}")
    return issues


def _mandatory_cp_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    control_ids = {item.control_plan_id for item in chain.controls}
    controlled_pfmea_ids = {item.pfmea_id for item in chain.controls if item.pfmea_id}

    for failure in chain.failure_modes:
        if not failure.is_mandatory_control:
            continue
        has_linked_control = bool(failure.linked_control_plan_id and failure.linked_control_plan_id in control_ids)
        has_pfmea_control = failure.pfmea_id in controlled_pfmea_ids
        if not (has_linked_control or has_pfmea_control):
            issues.append(
                f"mandatory/high-risk PFMEA {failure.pfmea_id!r} is not covered by control plan"
            )
    return issues


def _three_table_linkage_issues(chain: APQPChain) -> list[str]:
    issues: list[str] = []
    steps_by_id = {step.process_step_id: step for step in chain.process_steps}
    {failure.pfmea_id: failure for failure in chain.failure_modes}
    controls_by_pfmea: dict[str, list[Any]] = {}
    for control in chain.controls:
        if control.process_step_id and control.process_step_id not in steps_by_id:
            issues.append(
                f"control plan {control.control_plan_id!r} references missing process step {control.process_step_id!r}"
            )
        if control.pfmea_id:
            controls_by_pfmea.setdefault(control.pfmea_id, []).append(control)

    for step_id, step in sorted(steps_by_id.items()):
        step_failures = [
            failure for failure in chain.failure_modes if failure.process_step_id == step_id
        ]
        if step_failures:
            continue
        if _has_step_characteristics(step):
            issues.append(
                f"process step {step_id!r} has characteristics but no PFMEA risk row"
            )

    for failure in chain.failure_modes:
        linked_step = steps_by_id.get(failure.process_step_id)
        if linked_step is None:
            continue
        if not _text_matches_any(
            failure.process_function,
            [linked_step.process_function, linked_step.process_purpose, linked_step.operation],
        ):
            issues.append(
                f"PFMEA {failure.pfmea_id!r} does not inherit function from PFD step {failure.process_step_id!r}"
            )
        if _special_refs(failure) and not _special_refs(failure).issubset(
            _special_refs(linked_step)
        ):
            issues.append(
                f"PFMEA {failure.pfmea_id!r} special characteristics are not carried "
                f"from PFD step {failure.process_step_id!r}"
            )
        if not failure.is_mandatory_control:
            continue
        controls = controls_by_pfmea.get(failure.pfmea_id, [])
        if not controls:
            continue
        if not any(_control_covers_failure(control, failure) for control in controls):
            issues.append(
                f"high-risk PFMEA {failure.pfmea_id!r} has CP rows but no effective control content"
            )

    for step in chain.process_steps:
        step_specials = _special_refs(step)
        if not step_specials:
            continue
        pfmea_specials = {
            ref
            for failure in chain.failure_modes
            if failure.process_step_id == step.process_step_id
            for ref in _special_refs(failure)
        }
        cp_specials = {
            ref
            for control in chain.controls
            if control.process_step_id == step.process_step_id
            for ref in _special_refs(control)
        }
        missing_pfmea = sorted(step_specials - pfmea_specials)
        missing_cp = sorted(step_specials - cp_specials)
        if missing_pfmea:
            issues.append(
                f"special characteristics on PFD step {step.process_step_id!r} "
                f"missing from PFMEA: {', '.join(missing_pfmea)}"
            )
        if missing_cp:
            issues.append(
                f"special characteristics on PFD step {step.process_step_id!r} "
                f"missing from control plan: {', '.join(missing_cp)}"
            )

    for control in chain.controls:
        for field_name, value in (
            ("measurement_method", control.measurement_method),
            ("sample_frequency", control.sample_frequency),
            ("reaction_plan", control.reaction_plan),
        ):
            if not str(value).strip():
                issues.append(
                    f"control plan {control.control_plan_id!r} is missing {field_name}"
                )
    return issues


def _has_step_characteristics(step: Any) -> bool:
    return bool(
        _string_values(getattr(step, "special_characteristics", []))
        or _string_values(getattr(step, "product_characteristics", []))
        or _string_values(getattr(step, "process_characteristics", []))
    )


def _special_refs(item: Any) -> set[str]:
    refs: set[str] = set()
    for field_name in (
        "special_characteristics",
        "characteristic_refs",
        "source_special_characteristics",
    ):
        refs.update(_string_values(getattr(item, field_name, [])))
    classification = str(getattr(item, "classification", "")).strip()
    if classification in {"SC", "CC"}:
        refs.update(_string_values(classification.split(",")))
    return refs


def _control_covers_failure(control: Any, failure: Any) -> bool:
    control_text = " ".join(
        str(value)
        for value in (
            control.control_method,
            control.measurement_method,
            control.product_process_characteristic,
            control.specification,
            control.source_failure_cause,
            control.source_prevention_control,
            control.source_detection_control,
        )
        if str(value).strip()
    ).lower()
    required = [
        failure.failure_cause,
        failure.prevention_control,
        failure.detection_control,
    ]
    return any(_text_matches_any(value, [control_text]) for value in required) or bool(
        str(control.control_method).strip()
        and str(control.measurement_method).strip()
        and str(control.reaction_plan).strip()
    )


def _text_matches_any(value: str, candidates: list[str]) -> bool:
    text = " ".join(str(value or "").lower().split())
    if not text:
        return False
    return any(text in " ".join(str(candidate or "").lower().split()) for candidate in candidates)


def _string_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        values: list[Any] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return {str(item).strip() for item in values if str(item).strip()}


# Input Validation Classes


class ValidationError(Exception):
    """Base validation error."""
    pass


class FileValidationError(ValidationError):
    """File validation error."""
    pass


class PathValidationError(ValidationError):
    """Path validation error."""
    pass


class InputValidator:
    """Validates user inputs for security and correctness."""

    # File type magic numbers (first few bytes)
    MAGIC_NUMBERS = {
        "pdf": [b"%PDF"],
        "png": [b"\x89PNG\r\n\x1a\n"],
        "jpg": [b"\xff\xd8\xff"],
        "jpeg": [b"\xff\xd8\xff"],
        "gif": [b"GIF87a", b"GIF89a"],
        "bmp": [b"BM"],
        "tiff": [b"II*\x00", b"MM\x00*"],
        "zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
        "docx": [b"PK\x03\x04"],  # DOCX is a ZIP
        "xlsx": [b"PK\x03\x04"],  # XLSX is a ZIP
        "pptx": [b"PK\x03\x04"],  # PPTX is a ZIP
    }

    # Default max file size: 100MB
    DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024

    # Allowed file extensions by category
    ALLOWED_EXTENSIONS = {
        "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"},
        "document": {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"},
        "drawing": {".pdf", ".dwg", ".dxf", ".png", ".jpg", ".jpeg"},
        "archive": {".zip", ".tar", ".gz", ".7z"},
    }

    @classmethod
    def validate_file_type(
        cls,
        file_path: Path | str,
        allowed_extensions: set[str] | None = None,
        check_magic: bool = True,
    ) -> None:
        """
        Validate file type by extension and optionally by magic number.

        Args:
            file_path: Path to the file
            allowed_extensions: Set of allowed extensions (e.g., {'.pdf', '.png'})
            check_magic: Whether to verify file magic number

        Raises:
            FileValidationError: If file type is not allowed or magic number doesn't match
        """
        path = Path(file_path)

        if not path.exists():
            raise FileValidationError(f"File does not exist: {path}")

        if not path.is_file():
            raise FileValidationError(f"Path is not a file: {path}")

        # Check extension
        ext = path.suffix.lower()
        if allowed_extensions and ext not in allowed_extensions:
            raise FileValidationError(
                f"File extension '{ext}' not allowed. Allowed: {allowed_extensions}"
            )

        # Check magic number if requested
        if check_magic:
            cls._validate_magic_number(path, ext)

    @classmethod
    def _validate_magic_number(cls, path: Path, expected_ext: str) -> None:
        """Validate file magic number matches extension."""
        # Remove leading dot from extension
        ext_key = expected_ext.lstrip(".")

        if ext_key not in cls.MAGIC_NUMBERS:
            # No magic number defined for this type, skip check
            return

        expected_magics = cls.MAGIC_NUMBERS[ext_key]

        with open(path, "rb") as f:
            # Read first 16 bytes (enough for most magic numbers)
            header = f.read(16)

        # Check if any expected magic number matches
        matches = any(header.startswith(magic) for magic in expected_magics)

        if not matches:
            raise FileValidationError(
                f"File magic number does not match extension '{expected_ext}'. "
                f"File may be corrupted or misnamed."
            )

    @classmethod
    def validate_file_size(
        cls,
        file_path: Path | str,
        max_size: int = DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        """
        Validate file size is within limits.

        Args:
            file_path: Path to the file
            max_size: Maximum allowed file size in bytes

        Raises:
            FileValidationError: If file exceeds size limit
        """
        path = Path(file_path)

        if not path.exists():
            raise FileValidationError(f"File does not exist: {path}")

        file_size = path.stat().st_size

        if file_size > max_size:
            raise FileValidationError(
                f"File size {file_size} bytes exceeds maximum {max_size} bytes "
                f"({max_size / (1024 * 1024):.1f} MB)"
            )

    @classmethod
    def validate_path_traversal(
        cls,
        file_path: Path | str,
        base_dir: Path | str,
    ) -> Path:
        """
        Validate path does not escape base directory (path traversal attack).

        Args:
            file_path: Path to validate
            base_dir: Base directory that path must be within

        Returns:
            Resolved absolute path

        Raises:
            PathValidationError: If path escapes base directory
        """
        base = Path(base_dir).resolve()
        target = Path(file_path).resolve()

        # Check if target is within base directory
        try:
            target.relative_to(base)
        except ValueError:
            raise PathValidationError(
                f"Path '{file_path}' attempts to escape base directory '{base_dir}'"
            ) from None

        return target

    @classmethod
    def validate_filename(
        cls,
        filename: str,
        max_length: int = 255,
        allow_unicode: bool = True,
    ) -> None:
        """
        Validate filename for security and filesystem compatibility.

        Args:
            filename: Filename to validate
            max_length: Maximum filename length
            allow_unicode: Whether to allow unicode characters

        Raises:
            ValidationError: If filename is invalid
        """
        if not filename:
            raise ValidationError("Filename cannot be empty")

        if len(filename) > max_length:
            raise ValidationError(
                f"Filename too long: {len(filename)} > {max_length} characters"
            )

        # Check for path separators
        if "/" in filename or "\\" in filename:
            raise ValidationError("Filename cannot contain path separators")

        # Check for null bytes
        if "\x00" in filename:
            raise ValidationError("Filename cannot contain null bytes")

        # Check for dangerous patterns
        dangerous_patterns = ["..", "~", "$"]
        for pattern in dangerous_patterns:
            if pattern in filename:
                raise ValidationError(
                    f"Filename cannot contain dangerous pattern: {pattern}"
                )

        # Check unicode if not allowed
        if not allow_unicode:
            try:
                filename.encode("ascii")
            except UnicodeEncodeError:
                raise ValidationError("Filename must be ASCII only") from None

    @classmethod
    def validate_file(
        cls,
        file_path: Path | str,
        allowed_extensions: set[str] | None = None,
        max_size: int = DEFAULT_MAX_FILE_SIZE,
        base_dir: Path | str | None = None,
        check_magic: bool = True,
    ) -> Path:
        """
        Comprehensive file validation.

        Args:
            file_path: Path to the file
            allowed_extensions: Set of allowed extensions
            max_size: Maximum file size in bytes
            base_dir: Base directory for path traversal check
            check_magic: Whether to verify file magic number

        Returns:
            Validated absolute path

        Raises:
            ValidationError: If any validation fails
        """
        path = Path(file_path)

        # Validate filename
        cls.validate_filename(path.name)

        # Validate path traversal if base_dir provided
        if base_dir:
            path = cls.validate_path_traversal(path, base_dir)

        # Validate file type
        cls.validate_file_type(path, allowed_extensions, check_magic)

        # Validate file size
        cls.validate_file_size(path, max_size)

        return path

    @classmethod
    def sanitize_filename(cls, filename: str, replacement: str = "_") -> str:
        """
        Sanitize filename by replacing dangerous characters.

        Args:
            filename: Original filename
            replacement: Character to replace dangerous chars with

        Returns:
            Sanitized filename
        """
        # Replace path separators
        sanitized = filename.replace("/", replacement).replace("\\", replacement)

        # Replace null bytes
        sanitized = sanitized.replace("\x00", replacement)

        # Replace dangerous patterns
        sanitized = sanitized.replace("..", replacement)
        sanitized = sanitized.replace("~", replacement)
        sanitized = sanitized.replace("$", replacement)

        # Limit length
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            max_name_len = 255 - len(ext)
            sanitized = name[:max_name_len] + ext

        return sanitized


DRAWING_INPUT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _reject_null_byte(value: str) -> None:
    if "\x00" in value:
        raise PathValidationError("Path cannot contain null bytes")


def validate_drawing_input_file(file_path: str | Path) -> Path:
    """Validate a user-selected drawing file for desktop API ingestion."""
    text = str(file_path)
    _reject_null_byte(text)
    return InputValidator.validate_file(
        text,
        allowed_extensions=DRAWING_INPUT_EXTENSIONS,
        check_magic=True,
    ).resolve()


def validate_output_directory(directory_path: str | Path) -> Path:
    """Validate a user-selected output directory path."""
    text = str(directory_path).strip()
    if not text:
        raise PathValidationError("Output directory is required")
    _reject_null_byte(text)
    path = Path(text)
    if path.exists() and not path.is_dir():
        raise PathValidationError(f"Output path is not a directory: {path}")
    return path.resolve()


def validate_user_selected_directory(directory_path: str | Path) -> Path:
    """Validate a directory selected by the user before storing it."""
    return validate_output_directory(directory_path)
