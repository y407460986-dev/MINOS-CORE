from __future__ import annotations

from types import SimpleNamespace

from minos_desktop.api.dependencies import get_run_repository, get_run_service


def test_run_dependencies_use_app_factory_and_share_repository(tmp_path) -> None:
    created = []

    def factory():
        from minos_desktop.services import RunRepository

        repository = RunRepository(tmp_path / "desktop.sqlite3")
        created.append(repository)
        return repository

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(run_repository_factory=factory)))
    repository = get_run_repository(request)
    service = get_run_service(repository)

    assert created == [repository]
    assert service.repository is repository
