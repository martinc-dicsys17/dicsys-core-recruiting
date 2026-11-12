import pytest

from backend.modules.permisos.services import GrupoService


@pytest.mark.integration
@pytest.mark.parametrize("attempt", [1, 2])
def test_commits_do_not_leak_between_tests(db_session, attempt):
    grupo = GrupoService.crear_grupo(
        db_session,
        {
            "nombre": "transaction-isolation-proof",
            "descripcion": f"Attempt {attempt}",
        },
    )

    assert grupo.nombre == "transaction-isolation-proof"
