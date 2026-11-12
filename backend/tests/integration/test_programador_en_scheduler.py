"""El programador de tareas corre en el proceso con CRON_ENABLED (el servicio scheduler), en cualquier entorno
(F06-P01, F19-P10); los seeds de ejemplo siguen siendo solo de desarrollo."""

import asyncio

import pytest

import backend.main as main
from backend.core.config import settings
from backend.modules.tareas import parametros, programador

pytestmark = [pytest.mark.integration]


@pytest.fixture
def arranque(monkeypatch):
    """El lifespan sin los servicios externos: anota qué corrió."""
    corrio = []
    monkeypatch.setattr(main, "init_directories", lambda: None)
    monkeypatch.setattr("backend.core.llm.init_directories", lambda: None)
    monkeypatch.setattr("backend.core.email.init_email_service", lambda: None)
    monkeypatch.setattr("backend.core.webex.init_webex_service", lambda: None)
    monkeypatch.setattr(main, "_seeds_de_desarrollo", lambda: corrio.append("seeds"))
    monkeypatch.setattr(main, "_arrancar_programador", lambda: corrio.append("programador"))

    def correr(entorno: str, cron: bool) -> list[str]:
        corrio.clear()
        monkeypatch.setattr(settings, "environment", entorno)
        monkeypatch.setattr(settings, "cron_enabled", cron)

        async def ciclo():
            async with main.lifespan(main.app):
                pass

        asyncio.run(ciclo())
        return list(corrio)

    return correr


@pytest.mark.parametrize(
    ("entorno", "cron", "esperado"),
    [
        ("production", True, ["programador"]),  # el scheduler; antes de F19-P10 no arrancaba fuera de desarrollo
        ("production", False, []),  # el backend que atiende la API
        ("development", False, ["seeds"]),
        ("development", True, ["seeds", "programador"]),
    ],
)
def test_el_programador_corre_solo_con_cron_enabled(arranque, entorno, cron, esperado):
    assert arranque(entorno, cron) == esperado


def test_arrancar_el_programador_asegura_sus_parametros_antes(monkeypatch):
    orden = []
    monkeypatch.setattr(parametros, "asegurar_parametros", lambda db: orden.append("parametros") or False)
    monkeypatch.setattr(programador, "iniciar_programador", lambda: orden.append("programador"))

    main._arrancar_programador()

    assert orden == ["parametros", "programador"]
