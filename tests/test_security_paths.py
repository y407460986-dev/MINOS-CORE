from __future__ import annotations

import pytest

from minos_core.security_paths import validate_relative_reference, validate_safe_filename


def test_rejects_reference_outside_allowed_root(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        validate_relative_reference("../secret.json", root)


def test_rejects_absolute_reference(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        validate_relative_reference(str(outside), root)


def test_rejects_windows_backslash_traversal(tmp_path):
    root = tmp_path / "package"
    root.mkdir()

    with pytest.raises(ValueError):
        validate_relative_reference(r"..\secret.json", root)


@pytest.mark.parametrize("family_key", ["../../outside", r"..\..\outside"])
def test_rejects_family_key_path_separator(family_key):
    with pytest.raises(ValueError):
        validate_safe_filename(family_key)
