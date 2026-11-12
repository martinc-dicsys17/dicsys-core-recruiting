"""Auditoria de cargas de CV: un registro por operacion (recruiting_historial_cargas_cv) y una fila por archivo (..._archivos).

La auditoria se confirma en una transaccion propia, por eso el escenario crea empresa y usuario CONFIRMADOS en PostgreSQL
(y los elimina al terminar) en lugar de usar la transaccion revertible de db_session.
"""

import io
import uuid
import zipfile

import fitz
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.database import engine
from backend.modules.recruiting.historial_cargas_services import HistorialCargaCVService
from backend.modules.recruiting.services import CandidatoService
from backend.tests.factories import CoreDataFactory
from backend.tests.helpers.auth import auth_headers

URL_MASIVO = "/api/v1/recruiting/candidatos/cargar-cv-masivo"
URL_INDIVIDUAL = "/api/v1/recruiting/candidatos/cargar-cv"


def _pdf(*lineas: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


def _email() -> str:
    return f"audit{uuid.uuid4().hex[:10]}@example.com"


def _cv(nombre: str, email: str) -> bytes:
    return _pdf(nombre, "Analista QA", email, "Cordoba, Argentina")


def _cv_sin_email(nombre: str) -> bytes:
    return _pdf(nombre, "Analista QA", "Cordoba, Argentina")


def _zip(archivos: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre, contenido in archivos.items():
            zf.writestr(nombre, contenido)
    return buffer.getvalue()


@pytest.fixture
def escenario(database_schema):  # noqa: F811
    sesion = sessionmaker(bind=engine)()
    fabrica = CoreDataFactory(sesion)
    empresa = fabrica.empresa()
    usuario = fabrica.usuario(rol="admin", nombre="Martin", apellido="Prueba")
    fabrica.asignar_empresa(usuario, empresa)
    sesion.commit()
    empresa_id, usuario_id = empresa.id, usuario.id
    headers = auth_headers(usuario, empresa)
    sesion.close()
    yield {"empresa_id": empresa_id, "usuario_id": usuario_id, "headers": headers}
    with engine.begin() as c:
        c.execute(text("DELETE FROM recruiting_historial_cargas_cv_archivos WHERE empresa_id = :e"), {"e": empresa_id})
        c.execute(text("DELETE FROM recruiting_historial_cargas_cv WHERE empresa_id = :e"), {"e": empresa_id})
        c.execute(text("DELETE FROM core_usuario_empresa WHERE usuario_id = :u"), {"u": usuario_id})
        c.execute(text("DELETE FROM core_usuarios WHERE id = :u"), {"u": usuario_id})
        c.execute(text("DELETE FROM core_empresas WHERE id = :e"), {"e": empresa_id})


def _operaciones(escenario):
    with engine.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text("SELECT * FROM recruiting_historial_cargas_cv WHERE empresa_id = :e ORDER BY fecha_operacion"),
                {"e": escenario["empresa_id"]},
            )
        ]


def _archivos(operacion_id):
    with engine.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text("SELECT * FROM recruiting_historial_cargas_cv_archivos WHERE historial_id = :h ORDER BY orden"),
                {"h": operacion_id},
            )
        ]


def _masivo(client, escenario, archivos: dict, nombre="lote.zip"):  # noqa: F811
    r = client.post(
        URL_MASIVO, headers=escenario["headers"], files={"archivo": (nombre, _zip(archivos), "application/zip")}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _individual(client, escenario, nombre, contenido):  # noqa: F811
    return client.post(
        URL_INDIVIDUAL, headers=escenario["headers"], files={"archivo": (nombre, contenido, "application/pdf")}
    )


@pytest.mark.integration
def test_carga_masiva_completada_registra_una_operacion_con_cada_archivo(escenario, client, fake_storage):  # noqa: F811
    _masivo(client, escenario, {"a.pdf": _cv("Ana Uno", _email()), "b.pdf": _cv("Beto Dos", _email())})
    (op,) = _operaciones(escenario)
    assert (op["tipo_carga"], op["resultado"], op["total_archivos"], op["candidatos_creados"]) == (
        "masiva",
        "completada",
        2,
        2,
    )
    assert (op["duplicados"], op["sin_email"], op["rechazados"]) == (0, 0, 0)
    assert op["usuario_id"] == escenario["usuario_id"] and op["usuario_nombre"] == "Martin Prueba"
    assert (
        op["empresa_id"] == escenario["empresa_id"]
        and op["nombre_archivo"] == "lote.zip"
        and op["fecha_operacion"] is not None
    )
    filas = _archivos(op["id"])
    assert [(f["nombre_archivo"], f["resultado"]) for f in filas] == [("a.pdf", "creado"), ("b.pdf", "creado")]
    assert all(f["empresa_id"] == escenario["empresa_id"] and f["motivo"] is None for f in filas)


@pytest.mark.integration
def test_carga_masiva_parcial_clasifica_duplicados_sin_email_y_rechazados(escenario, client, fake_storage):  # noqa: F811
    email = _email()
    _masivo(
        client,
        escenario,
        {
            "ok.pdf": _cv("Ana Uno", email),
            "repetido.pdf": _cv("Ana Otra", email),
            "sin_mail.pdf": _cv_sin_email("Sin Correo"),
            "notas.txt": b"no es un cv",
        },
    )
    (op,) = _operaciones(escenario)
    assert (
        op["resultado"],
        op["total_archivos"],
        op["candidatos_creados"],
        op["duplicados"],
        op["sin_email"],
        op["rechazados"],
    ) == ("parcial", 4, 1, 1, 1, 1)
    por_nombre = {f["nombre_archivo"]: f for f in _archivos(op["id"])}
    assert {n: f["resultado"] for n, f in por_nombre.items()} == {
        "ok.pdf": "creado",
        "repetido.pdf": "duplicado",
        "sin_mail.pdf": "sin_email",
        "notas.txt": "rechazado",
    }
    assert por_nombre["ok.pdf"]["motivo"] is None
    for nombre in ("repetido.pdf", "sin_mail.pdf", "notas.txt"):
        assert por_nombre[nombre]["motivo"]
    # Sin datos personales: el email del CV no se guarda en ningun lado de la auditoria
    assert all(email not in (f["motivo"] or "") for f in por_nombre.values())
    assert email not in str(op)


@pytest.mark.integration
def test_carga_masiva_sin_candidatos_nuevos_es_fallida(escenario, client, fake_storage):  # noqa: F811
    _masivo(client, escenario, {"sin_mail.pdf": _cv_sin_email("Sin Correo"), "notas.txt": b"x"})
    (op,) = _operaciones(escenario)
    assert (op["resultado"], op["candidatos_creados"], op["sin_email"], op["rechazados"]) == ("fallida", 0, 1, 1)


@pytest.mark.integration
def test_carga_masiva_invalida_registra_operacion_fallida(escenario, client, fake_storage):  # noqa: F811
    r = client.post(
        URL_MASIVO, headers=escenario["headers"], files={"archivo": ("roto.zip", b"no es un zip", "application/zip")}
    )
    assert r.status_code == 200 and r.json()["ok"] is False
    (op,) = _operaciones(escenario)
    assert (op["tipo_carga"], op["resultado"], op["total_archivos"], op["rechazados"], op["candidatos_creados"]) == (
        "masiva",
        "fallida",
        1,
        1,
        0,
    )
    (fila,) = _archivos(op["id"])
    assert (fila["nombre_archivo"], fila["resultado"]) == ("roto.zip", "rechazado") and fila["motivo"]


@pytest.mark.integration
def test_carga_individual_creado_duplicado_sin_email_y_rechazado(escenario, client, fake_storage):  # noqa: F811
    email = _email()
    assert _individual(client, escenario, "uno.pdf", _cv("Ana Uno", email)).status_code == 201
    assert _individual(client, escenario, "dup.pdf", _cv("Ana Uno", email)).status_code == 409
    assert _individual(client, escenario, "sin.pdf", _cv_sin_email("Sin Correo")).status_code == 422
    assert _individual(client, escenario, "x.txt", b"no es cv").status_code >= 400

    ops = _operaciones(escenario)
    assert [o["tipo_carga"] for o in ops] == ["individual"] * 4
    esperado = [
        ("uno.pdf", "creado", "completada"),
        ("dup.pdf", "duplicado", "completada"),
        ("sin.pdf", "sin_email", "fallida"),
        ("x.txt", "rechazado", "fallida"),
    ]
    for op, (nombre, resultado_archivo, resultado_general) in zip(ops, esperado):
        assert (op["nombre_archivo"], op["resultado"], op["total_archivos"]) == (nombre, resultado_general, 1)
        (fila,) = _archivos(op["id"])
        assert (fila["nombre_archivo"], fila["resultado"]) == (nombre, resultado_archivo)
        assert (fila["motivo"] is None) == (resultado_archivo == "creado")
    assert [(o["candidatos_creados"], o["duplicados"], o["sin_email"], o["rechazados"]) for o in ops] == [
        (1, 0, 0, 0),
        (0, 1, 0, 0),
        (0, 0, 1, 0),
        (0, 0, 0, 1),
    ]
    assert all(email not in (f["motivo"] or "") for o in ops for f in _archivos(o["id"]))


@pytest.mark.integration
def test_auditoria_persiste_aunque_falle_la_carga_individual(escenario, client, fake_storage, monkeypatch):  # noqa: F811
    async def _falla(*args, **kwargs):
        raise RuntimeError("fallo inesperado con detalle tecnico")

    monkeypatch.setattr(CandidatoService, "_crear_desde_cv_sin_auditoria", staticmethod(_falla))
    r = _individual(client, escenario, "boom.pdf", _cv("Ana Uno", _email()))
    assert r.status_code == 500
    (op,) = _operaciones(escenario)
    assert (op["resultado"], op["rechazados"], op["candidatos_creados"]) == ("fallida", 1, 0)
    (fila,) = _archivos(op["id"])
    assert fila["nombre_archivo"] == "boom.pdf" and "detalle tecnico" not in fila["motivo"]  # solo el mensaje generico


@pytest.mark.integration
def test_auditoria_persiste_aunque_falle_la_carga_masiva(escenario, client, fake_storage, monkeypatch):  # noqa: F811
    async def _falla(*args, **kwargs):
        raise RuntimeError("fallo inesperado")

    monkeypatch.setattr(CandidatoService, "_procesar_carga_masiva_sin_auditoria", staticmethod(_falla))
    r = client.post(
        URL_MASIVO,
        headers=escenario["headers"],
        files={"archivo": ("lote.zip", _zip({"a.pdf": b"x"}), "application/zip")},
    )
    assert r.status_code == 200 and r.json()["ok"] is False
    (op,) = _operaciones(escenario)
    assert (op["tipo_carga"], op["resultado"]) == ("masiva", "fallida")
    assert [(f["nombre_archivo"], f["resultado"]) for f in _archivos(op["id"])] == [("lote.zip", "rechazado")]


@pytest.mark.integration
def test_fallo_al_auditar_no_altera_la_carga(escenario, client, fake_storage, monkeypatch):  # noqa: F811
    def _falla(*args, **kwargs):
        raise RuntimeError("base de auditoria caida")

    monkeypatch.setattr("backend.modules.recruiting.historial_cargas_services.SessionLocal", _falla)
    assert _individual(client, escenario, "uno.pdf", _cv("Ana Uno", _email())).status_code == 201
    assert _operaciones(escenario) == []


@pytest.mark.integration
def test_registrar_es_idempotente_por_operacion(escenario):
    operacion = uuid.uuid4()
    args = (
        escenario["empresa_id"],
        escenario["usuario_id"],
        "Martin",
        "masiva",
        "lote.zip",
        [{"nombre": "a.pdf", "resultado": "creado"}],
    )
    assert HistorialCargaCVService.registrar(*args, operacion_id=operacion) == operacion
    assert HistorialCargaCVService.registrar(*args, operacion_id=operacion) == operacion
    (op,) = _operaciones(escenario)
    assert op["total_archivos"] == 1 and len(_archivos(op["id"])) == 1


@pytest.mark.integration
def test_cancelada_y_calculo_de_resultado():
    calc = HistorialCargaCVService.calcular_resultado
    assert calc(12, 2, 0, 0) == "completada"
    assert calc(0, 3, 0, 0) == "completada"
    assert calc(5, 0, 1, 0) == "parcial"
    assert calc(0, 0, 1, 2) == "fallida"
    assert calc(0, 0, 0, 0) == "fallida"
    assert calc(3, 0, 0, 0, cancelado=True) == "cancelada"


# ---------------------------------------------------------------------------
# Bloqueos de la carga masiva: lote interrumpido, archivo que se cuelga y reintentos
# ---------------------------------------------------------------------------


def _estado_lote(escenario, **extra):
    import os

    lote_id = str(uuid.uuid4())
    estado = {
        "lote_id": lote_id,
        "empresa_id": str(escenario["empresa_id"]),
        "usuario_id": str(escenario["usuario_id"]),
        "usuario_nombre": "Martin Prueba",
        "estado": "procesando",
        "procesados": 2,
        "total": 5,
        "reporte": None,
        "error": None,
        "resultados_parciales": [
            {"archivo": "a.pdf", "resultado": "creado", "mensaje": "Candidato creado correctamente."},
            {"archivo": "b.pdf", "resultado": "duplicado", "mensaje": "Ya existe un candidato con el email x@y.com"},
        ],
    }
    estado.update(extra)
    CandidatoService._guardar_estado_lote(lote_id, estado)
    return lote_id, estado, CandidatoService._ruta_lote(lote_id), os


@pytest.mark.integration
def test_lote_sin_latido_se_declara_interrumpido_y_se_audita(escenario):
    """Causa real del 7/57 eterno: el proceso murio (recarga/reinicio) y el estado quedo en 'procesando' para siempre."""
    import json
    from types import SimpleNamespace

    lote_id, estado, ruta, os = _estado_lote(escenario)
    try:
        estado["actualizado"] = 1.0  # latido viejo: nadie sigue procesando
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        usuario = SimpleNamespace(id=escenario["usuario_id"])
        r = CandidatoService.obtener_estado_carga_masiva(lote_id, escenario["empresa_id"], usuario)
        assert r["estado"] == "error" and "interrumpi" in r["error"]
        # Consultar de nuevo no duplica la auditoria y el estado es definitivo
        assert (
            CandidatoService.obtener_estado_carga_masiva(lote_id, escenario["empresa_id"], usuario)["estado"] == "error"
        )
        (op,) = _operaciones(escenario)
        assert (
            str(op["operacion_id"]) == lote_id
            and op["tipo_carga"] == "masiva"
            and op["usuario_nombre"] == "Martin Prueba"
        )
        assert (op["candidatos_creados"], op["duplicados"], op["rechazados"], op["resultado"]) == (1, 1, 1, "parcial")
        filas = _archivos(op["id"])
        assert [(f["nombre_archivo"], f["resultado"]) for f in filas] == [
            ("a.pdf", "creado"),
            ("b.pdf", "duplicado"),
            ("(archivos sin procesar)", "rechazado"),
        ]
        assert "3 archivo" in filas[2]["motivo"] and "x@y.com" not in str([f["motivo"] for f in filas])
    finally:
        if os.path.exists(ruta):
            os.remove(ruta)


@pytest.mark.integration
def test_lote_con_latido_reciente_sigue_en_proceso(escenario):
    from types import SimpleNamespace

    lote_id, _, ruta, os = _estado_lote(escenario)  # _guardar_estado_lote estampa el latido actual
    try:
        r = CandidatoService.obtener_estado_carga_masiva(
            lote_id, escenario["empresa_id"], SimpleNamespace(id=escenario["usuario_id"])
        )
        assert r["estado"] == "procesando"
        assert _operaciones(escenario) == []
    finally:
        os.remove(ruta)


@pytest.mark.integration
def test_archivo_que_se_cuelga_se_omite_y_el_lote_continua(escenario, client, fake_storage, monkeypatch):  # noqa: F811
    import threading

    original = CandidatoService.procesar_cv_bytes
    liberar = threading.Event()
    terminado = threading.Event()

    def _lento(**kwargs):
        if kwargs["nombre_archivo"] != "colgado.pdf":
            return original(**kwargs)
        try:
            liberar.wait(5)  # simula un PDF que no termina de procesarse
            return original(**kwargs)
        finally:
            terminado.set()

    monkeypatch.setattr(CandidatoService, "procesar_cv_bytes", staticmethod(_lento))
    monkeypatch.setattr(CandidatoService, "TIEMPO_MAXIMO_ARCHIVO_SEGUNDOS", 0.5)
    try:
        body = _masivo(
            client,
            escenario,
            {
                "a.pdf": _cv("Ana Uno", _email()),
                "colgado.pdf": _cv("Pedro Colgado", _email()),
                "c.pdf": _cv("Carla Tres", _email()),
            },
        )
    finally:
        liberar.set()
        terminado.wait(10)  # el hilo abandonado no debe seguir usando la sesion cuando termina el test
    assert body["resumen"]["creados"] == 2 and body["resumen"]["errores_otros"] == 1
    por_archivo = {r["archivo"]: r for r in body["resultados"]}
    assert por_archivo["colgado.pdf"]["resultado"] == "error_otro" and "tiempo" in por_archivo["colgado.pdf"]["mensaje"]
    (op,) = _operaciones(escenario)
    assert (op["resultado"], op["total_archivos"], op["candidatos_creados"], op["rechazados"]) == ("parcial", 3, 2, 1)
    assert {f["nombre_archivo"]: f["resultado"] for f in _archivos(op["id"])} == {
        "a.pdf": "creado",
        "colgado.pdf": "rechazado",
        "c.pdf": "creado",
    }


@pytest.mark.integration
def test_reintentar_el_lote_no_duplica_candidatos(escenario, client, fake_storage, db_session):  # noqa: F811
    from backend.modules.recruiting.models import Candidato

    archivos = {"a.pdf": _cv("Ana Uno", _email()), "b.pdf": _cv("Beto Dos", _email())}
    _masivo(client, escenario, archivos)
    cantidad = db_session.query(Candidato).filter(Candidato.empresa_id == escenario["empresa_id"]).count()
    body = _masivo(client, escenario, archivos)
    assert body["resumen"]["creados"] == 0 and body["resumen"]["duplicados_omitidos"] == 2
    assert db_session.query(Candidato).filter(Candidato.empresa_id == escenario["empresa_id"]).count() == cantidad == 2
    primero, segundo = _operaciones(escenario)
    assert (primero["candidatos_creados"], primero["duplicados"]) == (2, 0)
    assert (segundo["candidatos_creados"], segundo["duplicados"], segundo["resultado"]) == (0, 2, "completada")
    assert primero["operacion_id"] != segundo["operacion_id"]
