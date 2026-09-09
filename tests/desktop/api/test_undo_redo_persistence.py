from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from minos_desktop.api.app import create_app
from minos_desktop.services import DesktopRunService


@pytest.mark.asyncio
async def test_undo_redo_api_returns_200_and_empty_history_422(tmp_path, monkeypatch):
    monkeypatch.setenv("MINOS_DESKTOP_API_TOKEN", "test-token")
    db_path = tmp_path / "desktop.sqlite3"
    app = create_app(db_path=db_path, output_dir=tmp_path)
    service = DesktopRunService(db_path)
    before = {"status": "draft_ready", "manual_review": {"required": False, "items": []}}
    after = {"status": "needs_review", "manual_review": {"required": True, "items": []}}
    run = service.save_result(None, before, tmp_path)
    service.save_with_undo(run.id, after)
    headers = {"Authorization": "Bearer test-token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        undo = await client.post(f"/api/runs/{run.id}/undo", headers=headers)
        redo = await client.post(f"/api/runs/{run.id}/redo", headers=headers)
        empty = await client.post(f"/api/runs/{run.id}/redo", headers=headers)
        missing = await client.post("/api/runs/9999/undo", headers=headers)

    assert undo.status_code == 200
    assert redo.status_code == 200
    assert empty.status_code == 422
    assert missing.status_code == 404
