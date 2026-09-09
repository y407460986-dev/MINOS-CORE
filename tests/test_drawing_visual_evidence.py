from pathlib import Path

from PIL import Image

from minos_core.drawing_visual_evidence import build_visual_evidence_regions


def test_build_visual_evidence_regions_includes_declared_and_requirement_regions(tmp_path):
    image_path = tmp_path / "page.png"
    Image.new("RGB", (2000, 1400), "white").save(image_path)

    regions = build_visual_evidence_regions(
        page_image_path=image_path,
        page_evidence_id="drawing_page_001",
        technical_requirements=[
            {"text": "4. 技术要求第4条第(2)项：转动力矩(0.5~2.5)Nm", "evidence_refs": ["REQ4"]},
            {"text": "5. 技术要求第5条：GB 15086", "evidence_refs": ["REQ5"]},
        ],
    )

    by_id = {item["region_id"]: item for item in regions}
    assert "drawing_page_001_full_page" in by_id
    assert "drawing_page_001_title_block_special_counts" in by_id
    assert "drawing_page_001_key_product_characteristic_table" in by_id
    assert "drawing_page_001_technical_requirements" in by_id
    assert "drawing_page_001_technical_requirement_line_004" in by_id
    assert "drawing_page_001_technical_requirement_line_006" in by_id
    assert "drawing_page_001_technical_requirement_001" in by_id
    assert "drawing_page_001_technical_requirement_002" in by_id

    required_keys = {
        "region_id",
        "page_evidence_id",
        "label",
        "bbox",
        "image_path",
        "evidence_refs",
    }
    assert all(required_keys <= set(item) for item in regions)
    assert by_id["drawing_page_001_technical_requirement_001"]["evidence_refs"] == ["REQ4"]
    assert all(Path(item["image_path"]).exists() for item in regions)

    for item in regions:
        with Image.open(item["image_path"]) as crop:
            assert crop.width > 0
            assert crop.height > 0
