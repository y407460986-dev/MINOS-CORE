"""Tests for InputValidator."""

import tempfile
from pathlib import Path

import pytest

from minos_core.validation import (
    InputValidator,
    ValidationError,
    FileValidationError,
    PathValidationError,
)


class TestInputValidator:
    """Test InputValidator class."""

    def test_validate_file_type_valid_pdf(self, tmp_path):
        """Test validating a valid PDF file."""
        # Create a fake PDF file with correct magic number
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n")

        # Should not raise
        InputValidator.validate_file_type(pdf_file, {".pdf"}, check_magic=True)

    def test_validate_file_type_invalid_extension(self, tmp_path):
        """Test validating file with invalid extension."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("content")

        with pytest.raises(FileValidationError, match="not allowed"):
            InputValidator.validate_file_type(txt_file, {".pdf", ".png"})

    def test_validate_file_type_magic_number_mismatch(self, tmp_path):
        """Test validating file with mismatched magic number."""
        # Create a file with .pdf extension but wrong content
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("This is not a PDF")

        with pytest.raises(FileValidationError, match="magic number does not match"):
            InputValidator.validate_file_type(fake_pdf, {".pdf"}, check_magic=True)

    def test_validate_file_type_nonexistent_file(self, tmp_path):
        """Test validating nonexistent file."""
        nonexistent = tmp_path / "nonexistent.pdf"

        with pytest.raises(FileValidationError, match="does not exist"):
            InputValidator.validate_file_type(nonexistent, {".pdf"})

    def test_validate_file_type_directory(self, tmp_path):
        """Test validating a directory instead of file."""
        with pytest.raises(FileValidationError, match="not a file"):
            InputValidator.validate_file_type(tmp_path, {".pdf"})

    def test_validate_file_size_within_limit(self, tmp_path):
        """Test validating file size within limit."""
        small_file = tmp_path / "small.txt"
        small_file.write_text("small content")

        # Should not raise
        InputValidator.validate_file_size(small_file, max_size=1024)

    def test_validate_file_size_exceeds_limit(self, tmp_path):
        """Test validating file size exceeding limit."""
        large_file = tmp_path / "large.txt"
        large_file.write_bytes(b"x" * 2000)

        with pytest.raises(FileValidationError, match="exceeds maximum"):
            InputValidator.validate_file_size(large_file, max_size=1000)

    def test_validate_path_traversal_safe_path(self, tmp_path):
        """Test validating safe path within base directory."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        safe_file = base_dir / "safe.txt"
        safe_file.write_text("content")

        # Should return resolved path
        result = InputValidator.validate_path_traversal(safe_file, base_dir)
        assert result == safe_file.resolve()

    def test_validate_path_traversal_escape_attempt(self, tmp_path):
        """Test validating path that attempts to escape base directory."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        # Try to escape using ../
        escape_path = base_dir / ".." / ".." / "etc" / "passwd"

        with pytest.raises(PathValidationError, match="escape base directory"):
            InputValidator.validate_path_traversal(escape_path, base_dir)

    def test_validate_filename_valid(self):
        """Test validating valid filename."""
        # Should not raise
        InputValidator.validate_filename("valid_file.txt")
        InputValidator.validate_filename("file-123.pdf")
        InputValidator.validate_filename("文件.txt", allow_unicode=True)

    def test_validate_filename_empty(self):
        """Test validating empty filename."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            InputValidator.validate_filename("")

    def test_validate_filename_too_long(self):
        """Test validating filename that's too long."""
        long_name = "x" * 300

        with pytest.raises(ValidationError, match="too long"):
            InputValidator.validate_filename(long_name, max_length=255)

    def test_validate_filename_path_separator(self):
        """Test validating filename with path separator."""
        with pytest.raises(ValidationError, match="path separators"):
            InputValidator.validate_filename("path/to/file.txt")

        with pytest.raises(ValidationError, match="path separators"):
            InputValidator.validate_filename("path\\to\\file.txt")

    def test_validate_filename_null_byte(self):
        """Test validating filename with null byte."""
        with pytest.raises(ValidationError, match="null bytes"):
            InputValidator.validate_filename("file\x00.txt")

    def test_validate_filename_dangerous_patterns(self):
        """Test validating filename with dangerous patterns."""
        with pytest.raises(ValidationError, match="dangerous pattern"):
            InputValidator.validate_filename("..file.txt")

        with pytest.raises(ValidationError, match="dangerous pattern"):
            InputValidator.validate_filename("~file.txt")

        with pytest.raises(ValidationError, match="dangerous pattern"):
            InputValidator.validate_filename("$file.txt")

    def test_validate_filename_unicode_not_allowed(self):
        """Test validating unicode filename when not allowed."""
        with pytest.raises(ValidationError, match="ASCII only"):
            InputValidator.validate_filename("文件.txt", allow_unicode=False)

    def test_validate_file_comprehensive(self, tmp_path):
        """Test comprehensive file validation."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        # Create a valid PDF file
        pdf_file = base_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n" + b"x" * 100)

        # Should return validated path
        result = InputValidator.validate_file(
            pdf_file,
            allowed_extensions={".pdf"},
            max_size=1024,
            base_dir=base_dir,
            check_magic=True,
        )

        assert result == pdf_file.resolve()

    def test_sanitize_filename_safe(self):
        """Test sanitizing already safe filename."""
        result = InputValidator.sanitize_filename("safe_file.txt")
        assert result == "safe_file.txt"

    def test_sanitize_filename_path_separators(self):
        """Test sanitizing filename with path separators."""
        result = InputValidator.sanitize_filename("path/to/file.txt")
        assert result == "path_to_file.txt"

        result = InputValidator.sanitize_filename("path\\to\\file.txt")
        assert result == "path_to_file.txt"

    def test_sanitize_filename_dangerous_patterns(self):
        """Test sanitizing filename with dangerous patterns."""
        result = InputValidator.sanitize_filename("../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_filename_too_long(self):
        """Test sanitizing filename that's too long."""
        long_name = "x" * 300 + ".txt"
        result = InputValidator.sanitize_filename(long_name)

        # Should be truncated to 255 chars
        assert len(result) <= 255
        # Should preserve extension
        assert result.endswith(".txt")

    def test_magic_numbers_png(self, tmp_path):
        """Test PNG magic number validation."""
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)

        # Should not raise
        InputValidator.validate_file_type(png_file, {".png"}, check_magic=True)

    def test_magic_numbers_jpg(self, tmp_path):
        """Test JPEG magic number validation."""
        jpg_file = tmp_path / "test.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff" + b"x" * 100)

        # Should not raise
        InputValidator.validate_file_type(jpg_file, {".jpg"}, check_magic=True)

    def test_magic_numbers_zip(self, tmp_path):
        """Test ZIP magic number validation."""
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(b"PK\x03\x04" + b"x" * 100)

        # Should not raise
        InputValidator.validate_file_type(zip_file, {".zip"}, check_magic=True)

    def test_validate_file_type_no_magic_check(self, tmp_path):
        """Test validating file type without magic number check."""
        # Create a file with wrong content but correct extension
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("This is not a PDF")

        # Should not raise when check_magic=False
        InputValidator.validate_file_type(fake_pdf, {".pdf"}, check_magic=False)

    def test_allowed_extensions_categories(self):
        """Test predefined extension categories."""
        assert ".png" in InputValidator.ALLOWED_EXTENSIONS["image"]
        assert ".pdf" in InputValidator.ALLOWED_EXTENSIONS["document"]
        assert ".pdf" in InputValidator.ALLOWED_EXTENSIONS["drawing"]
        assert ".zip" in InputValidator.ALLOWED_EXTENSIONS["archive"]

    def test_default_max_file_size(self):
        """Test default max file size is 100MB."""
        assert InputValidator.DEFAULT_MAX_FILE_SIZE == 100 * 1024 * 1024
