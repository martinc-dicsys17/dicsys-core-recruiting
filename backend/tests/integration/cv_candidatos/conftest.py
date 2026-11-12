import pytest


@pytest.fixture(autouse=True)
def _cv_storage_dir_aislado(tmp_path, monkeypatch):
    """Las pruebas de Recruiting nunca escriben en la carpeta persistente real de CV (CV_STORAGE_DIR)."""
    monkeypatch.setenv("CV_STORAGE_DIR", str(tmp_path / "cv_storage"))
