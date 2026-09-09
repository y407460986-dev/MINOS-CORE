from __future__ import annotations

from pathlib import Path


def test_pipeline_and_services_public_imports_resolve_to_packages() -> None:
    import minos_core.pipeline as pipeline
    import minos_desktop.services as services

    assert Path(pipeline.__file__).name == "__init__.py"
    assert Path(services.__file__).name == "__init__.py"
    assert callable(pipeline.generate_three_tables_from_drawing)
    assert services.DesktopRunService is not None
