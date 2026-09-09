from __future__ import annotations

import json
from pathlib import Path

import pytest

from minos_core.adapters.fixture_json import load_fixture_payload


ROOT = Path(__file__).resolve().parents[1]
DEMO_PACKAGE = ROOT / "tests" / "fixtures" / "demo_input_package"


@pytest.mark.parametrize(
    ("reference_field", "outside_filename"),
    [
        ("evidence_path", "outside-evidence.json"),
        ("review_patch_path", "outside-review-patch.json"),
    ],
)
def test_input_package_rejects_json_reference_outside_package(
    tmp_path, reference_field, outside_filename
):
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    payload = json.loads((DEMO_PACKAGE / "input_package.json").read_text(encoding="utf-8"))
    payload[reference_field] = f"../{outside_filename}"
    (package_dir / "input_package.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    for filename in ("evidence.json", "review_patch.json"):
        source = DEMO_PACKAGE / filename
        (package_dir / filename).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    outside = tmp_path / outside_filename
    source_name = reference_field.removesuffix("_path") + ".json"
    outside.write_text(
        (DEMO_PACKAGE / source_name).read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        load_fixture_payload(package_dir)
