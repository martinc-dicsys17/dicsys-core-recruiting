"""Carga masiva de CVs: duplicados por email, resultado individual por archivo y resumen final del lote."""

import io
import zipfile
from datetime import datetime

import fitz
import pytest

from backend.modules.recruiting import services as recruiting_services
from backend.modules.recruiting.models import Candidato
from backend.modules.recruiting.services import CandidatoService
from backend.tests.helpers.auth import auth_headers

URL_MASIVO = "/api/v1/recruiting/candidatos/cargar-cv-masivo"

CAMPOS_RESUMEN = (
    "creados",
    "duplicados_omitidos",
    "sin_email",
    "rechazados_formato_tamano",
    "errores_lectura",
    "errores_validacion",
    "errores_persistencia",
    "errores_otros",
)


def _pdf(*lineas: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


def _cv(nombre: str, email: str) -> bytes:
    return _pdf(nombre, "Analista QA", email, "Cordoba, Argentina")


def _zip(**archivos) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre, contenido in archivos.items():
            zf.writestr(nombre, contenido)
    return buffer.getvalue()


def _zip_lista(archivos) -> bytes:
    """Como _zip pero permite repetir nombres base (distintas carpetas) o nombres con espacios."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre, contenido in archivos:
            zf.writestr(nombre, contenido)
    return buffer.getvalue()


@pytest.fixture
def escenario(data_factory, db_session, fake_storage):  # noqa: F811
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.flush()
    return auth_headers(usuario, empresa), empresa


def _cargar(client, headers, contenido_zip, nombre="lote.zip"):  # noqa: F811
    r = client.post(URL_MASIVO, headers=headers, files={"archivo": (nombre, contenido_zip, "application/zip")})
    assert r.status_code == 200, r.text
    return r.json()


def _candidatos(db_session, empresa):  # noqa: F811
    return db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).all()


def _foto(candidato: Candidato) -> dict:
    """Todas las columnas de una ficha (datos, CV asociado y auditoría) para comparar antes y después."""
    return {c.name: getattr(candidato, c.name) for c in Candidato.__table__.columns}


def _por_archivo(body: dict) -> dict:
    return {r["archivo"]: r for r in body["resultados"]}


def _assert_resumen_consistente(body: dict) -> None:
    """Cada archivo tiene un único resultado final y el total es la suma de las categorías excluyentes."""
    resumen = body["resumen"]
    assert resumen["total_archivos"] == len(body["resultados"])
    assert sum(resumen[c] for c in CAMPOS_RESUMEN) == resumen["total_archivos"]
    nombres = [r["archivo"] for r in body["resultados"]]
    assert len(nombres) == len(set(nombres))


# 1 y 2 ---------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_email_existente_se_omite_y_la_ficha_queda_intacta(client, db_session, escenario, fake_storage):  # noqa: F811
    headers, empresa = escenario
    primero = _cargar(client, headers, _zip(**{"Laura Gomez.pdf": _cv("Laura Gomez", "laura.gomez@example.com")}))
    assert primero["resumen"]["creados"] == 1
    existente = _candidatos(db_session, empresa)[0]
    antes = _foto(existente)
    archivos_antes = dict(fake_storage.files)

    # Otro CV con el mismo email pero distinto contenido: no debe actualizar nombre, skills, CV ni auditoría
    body = _cargar(
        client,
        headers,
        _zip(
            **{
                "Otro nombre.pdf": _pdf(
                    "Laura Beatriz Gomez Perez",
                    "Desarrolladora Python Senior Django AWS",
                    "laura.gomez@example.com",
                    "Rosario, Santa Fe",
                )
            }
        ),
    )

    assert body["resumen"]["duplicados_omitidos"] == 1
    assert body["resumen"]["creados"] == 0
    assert body["candidatos_creados"] == []
    assert _por_archivo(body)["Otro nombre.pdf"]["resultado"] == "duplicado"
    assert "laura.gomez@example.com" in _por_archivo(body)["Otro nombre.pdf"]["mensaje"]
    db_session.expire_all()
    candidatos = _candidatos(db_session, empresa)
    assert len(candidatos) == 1
    assert _foto(candidatos[0]) == antes
    assert dict(fake_storage.files) == archivos_antes
    _assert_resumen_consistente(body)


# 3 ------------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_email_nuevo_crea_el_candidato(client, db_session, escenario, fake_storage):  # noqa: F811
    headers, empresa = escenario
    body = _cargar(client, headers, _zip(**{"Laura Gomez.pdf": _cv("Laura Gomez", "laura.gomez@example.com")}))

    assert body["resumen"]["creados"] == 1
    assert body["procesados_exitosamente"] == 1
    resultado = _por_archivo(body)["Laura Gomez.pdf"]
    assert resultado["resultado"] == "creado"
    candidatos = _candidatos(db_session, empresa)
    assert [c.email for c in candidatos] == ["laura.gomez@example.com"]
    assert resultado["candidato_id"] == str(candidatos[0].id)
    assert candidatos[0].cv_url in fake_storage.files
    _assert_resumen_consistente(body)


# 4 ------------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_cv_sin_email_se_cuenta_como_sin_email(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    body = _cargar(
        client,
        headers,
        _zip(
            **{
                "Laura Gomez.pdf": _cv("Laura Gomez", "laura.gomez@example.com"),
                "Nicolas Tosi.pdf": _pdf("Nicolas Marcelo Tosi", "Desarrollador .NET", "Buenos Aires, Argentina"),
            }
        ),
    )

    assert body["resumen"]["sin_email"] == 1
    assert body["resumen"]["creados"] == 1
    assert _por_archivo(body)["Nicolas Tosi.pdf"]["resultado"] == "sin_email"
    assert _por_archivo(body)["Nicolas Tosi.pdf"]["mensaje"] == CandidatoService.MENSAJE_CV_SIN_EMAIL
    assert [c.email for c in _candidatos(db_session, empresa)] == ["laura.gomez@example.com"]
    _assert_resumen_consistente(body)


# 5 ------------------------------------------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "email_guardado",
    [
        "LAURA.GOMEZ@EXAMPLE.COM",
        "  laura.gomez@example.com  ",
        " Laura.Gomez@Example.com",
    ],
    ids=["mayusculas", "espacios", "mixto"],
)
def test_email_con_distinto_formato_se_reconoce_como_duplicado(
    client, db_session, data_factory, escenario, email_guardado
):  # noqa: F811
    headers, empresa = escenario
    existente = Candidato(
        empresa_id=empresa.id,
        codigo="C-9001",
        nombre="Laura",
        apellido="Existente",
        email=email_guardado,
        estado="Activo",
        fuente="Portal Propio",
        skills=["Java"],
        moneda_pretension="ARS",
    )
    db_session.add(existente)
    db_session.flush()
    antes = _foto(existente)

    body = _cargar(client, headers, _zip(**{"Laura Gomez.pdf": _cv("Laura Gomez", "Laura.Gomez@example.com")}))

    assert body["resumen"]["duplicados_omitidos"] == 1
    assert body["resumen"]["creados"] == 0
    db_session.expire_all()
    candidatos = _candidatos(db_session, empresa)
    assert len(candidatos) == 1
    assert _foto(candidatos[0]) == antes


@pytest.mark.integration
def test_el_duplicado_se_detecta_por_email_y_no_por_nombre(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    _cargar(client, headers, _zip(**{"Laura Gomez.pdf": _cv("Laura Gomez", "laura.gomez@example.com")}))

    # Mismo nombre y distinto email: es un candidato nuevo
    body = _cargar(client, headers, _zip(**{"Laura Gomez 2.pdf": _cv("Laura Gomez", "laura.gomez.otra@example.com")}))

    assert body["resumen"]["creados"] == 1
    assert body["resumen"]["duplicados_omitidos"] == 0
    assert len(_candidatos(db_session, empresa)) == 2


# 6 ------------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_dos_cv_del_mismo_lote_con_el_mismo_email_crean_un_solo_candidato(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    body = _cargar(
        client,
        headers,
        _zip_lista(
            [
                ("a/Laura Gomez.pdf", _cv("Laura Gomez", "laura.gomez@example.com")),
                ("b/Laura G.pdf", _cv("Laura G", "LAURA.GOMEZ@example.com ")),
            ]
        ),
    )

    assert body["resumen"]["creados"] == 1
    assert body["resumen"]["duplicados_omitidos"] == 1
    assert len(_candidatos(db_session, empresa)) == 1
    estados = {r["archivo"]: r["resultado"] for r in body["resultados"]}
    assert estados == {"Laura Gomez.pdf": "creado", "Laura G.pdf": "duplicado"}
    _assert_resumen_consistente(body)


# 7 ------------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_un_error_individual_no_interrumpe_el_resto_del_lote(client, db_session, escenario, monkeypatch):  # noqa: F811
    headers, empresa = escenario
    original = CandidatoService._generar_siguiente_codigo
    llamadas = {"n": 0}

    def codigo_que_falla_una_vez(db, empresa_id):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("fallo inesperado simulado")
        return original(db, empresa_id)

    monkeypatch.setattr(CandidatoService, "_generar_siguiente_codigo", staticmethod(codigo_que_falla_una_vez))

    body = _cargar(
        client,
        headers,
        _zip(
            **{
                "A.pdf": _cv("Ana Uno", "ana.uno@example.com"),
                "B.pdf": _cv("Beto Dos", "beto.dos@example.com"),
                "C.pdf": _cv("Carla Tres", "carla.tres@example.com"),
            }
        ),
    )

    assert body["resumen"]["creados"] == 2
    assert body["resumen"]["errores_otros"] == 1
    assert _por_archivo(body)["B.pdf"]["resultado"] == "error_otro"
    assert _por_archivo(body)["B.pdf"]["mensaje"] == recruiting_services.MENSAJE_ERROR_INTERNO  # sin exponer la causa
    assert sorted(c.email for c in _candidatos(db_session, empresa)) == [
        "ana.uno@example.com",
        "carla.tres@example.com",
    ]
    _assert_resumen_consistente(body)


@pytest.mark.integration
def test_error_de_persistencia_no_se_cuenta_como_creado(client, db_session, escenario, monkeypatch):  # noqa: F811
    headers, empresa = escenario
    original_codigo = CandidatoService._generar_siguiente_codigo
    original_utc_now = recruiting_services.utc_now
    estado = {"codigos": 0, "romper": False}

    def codigo(db, empresa_id):
        estado["codigos"] += 1
        estado["romper"] = estado["codigos"] == 2  # justo antes de guardar el segundo candidato
        return original_codigo(db, empresa_id)

    def utc_now_que_falla_al_guardar():
        if estado["romper"]:
            estado["romper"] = False
            raise RuntimeError("fallo de base de datos simulado")
        return original_utc_now()

    monkeypatch.setattr(CandidatoService, "_generar_siguiente_codigo", staticmethod(codigo))
    monkeypatch.setattr(recruiting_services, "utc_now", utc_now_que_falla_al_guardar)

    body = _cargar(
        client,
        headers,
        _zip(
            **{
                "A.pdf": _cv("Ana Uno", "ana.uno@example.com"),
                "B.pdf": _cv("Beto Dos", "beto.dos@example.com"),
                "C.pdf": _cv("Carla Tres", "carla.tres@example.com"),
            }
        ),
    )

    assert body["resumen"]["creados"] == 2
    assert body["resumen"]["errores_persistencia"] == 1
    assert _por_archivo(body)["B.pdf"]["resultado"] == "error_persistencia"
    assert _por_archivo(body)["B.pdf"]["candidato_id"] is None
    assert sorted(c.email for c in _candidatos(db_session, empresa)) == [
        "ana.uno@example.com",
        "carla.tres@example.com",
    ]
    _assert_resumen_consistente(body)


# 10 -----------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_estadisticas_con_todos_los_casos_no_suman_dos_veces_un_archivo(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    _cargar(client, headers, _zip(**{"Previo.pdf": _cv("Pablo Previo", "pablo.previo@example.com")}))
    cantidad_previa = len(_candidatos(db_session, empresa))

    body = _cargar(
        client,
        headers,
        _zip(
            **{
                "Nuevo 1.pdf": _cv("Nora Uno", "nora.uno@example.com"),
                "Nuevo 2.pdf": _cv("Nico Dos", "nico.dos@example.com"),
                "Repetido.pdf": _cv("Pablo Previo", "pablo.previo@example.com"),
                "Sin email.pdf": _pdf("Sin Correo", "Analista"),
                "notas.txt": b"no es un CV",
                "Enorme.pdf": b"\0" * (10 * 1024 * 1024 + 1),
            }
        ),
    )

    resumen = body["resumen"]
    assert resumen["total_archivos"] == 6
    assert resumen["creados"] == 2
    assert resumen["duplicados_omitidos"] == 1
    assert resumen["sin_email"] == 1
    assert resumen["rechazados_formato_tamano"] == 2
    assert _por_archivo(body)["notas.txt"]["resultado"] == "formato_tamano"
    assert _por_archivo(body)["Enorme.pdf"]["resultado"] == "formato_tamano"
    assert len(_candidatos(db_session, empresa)) == cantidad_previa + resumen["creados"]
    assert body["procesados_exitosamente"] == resumen["creados"]
    # Los fallidos históricos no incluyen ni creados ni duplicados omitidos
    assert sorted(f["archivo"] for f in body["fallidos"]) == ["Enorme.pdf", "Sin email.pdf", "notas.txt"]
    _assert_resumen_consistente(body)


# 11 -----------------------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_una_carga_nueva_no_incorpora_los_resultados_del_lote_anterior(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    primero = _cargar(
        client,
        headers,
        _zip(
            **{
                "A.pdf": _cv("Ana Uno", "ana.uno@example.com"),
                "B.pdf": _pdf("Sin Correo"),
            }
        ),
    )
    segundo = _cargar(client, headers, _zip(**{"C.pdf": _cv("Carla Tres", "carla.tres@example.com")}))

    assert primero["lote_id"] != segundo["lote_id"]
    assert [r["archivo"] for r in segundo["resultados"]] == ["C.pdf"]
    assert segundo["resumen"]["total_archivos"] == 1
    assert segundo["resumen"]["creados"] == 1
    assert segundo["resumen"]["sin_email"] == 0
    assert len(primero["resultados"]) == 2


@pytest.mark.integration
def test_comprimido_vacio_devuelve_resumen_en_cero(client, escenario):  # noqa: F811
    headers, _ = escenario
    body = _cargar(client, headers, _zip(**{"__MACOSX/._A.pdf": b"x", ".oculto.pdf": b"x"}))

    assert body["resumen"]["total_archivos"] == 0
    assert all(body["resumen"][c] == 0 for c in CAMPOS_RESUMEN)
    assert body["resultados"] == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "campos",
    [
        {"estado": "Activo"},
        {"estado": "Inactivo"},
        {"estado": "Contratado"},
        {"activo": False},
        {"deleted_at": datetime(2026, 1, 1)},
    ],
    ids=["activo", "inactivo", "contratado", "activo_false", "deleted_at"],
)
def test_cualquier_email_existente_se_omite_sin_filtrar_por_estado(client, db_session, escenario, campos):  # noqa: F811
    headers, empresa = escenario
    datos = {"estado": "Activo", "activo": True, "deleted_at": None, **campos}
    existente = Candidato(
        empresa_id=empresa.id,
        codigo="C-9002",
        nombre="Laura",
        apellido="Existente",
        email="laura.gomez@example.com",
        fuente="Portal Propio",
        skills=["Java"],
        moneda_pretension="ARS",
        cv_url="recruiting/cv/original.pdf",
        **datos,
    )
    db_session.add(existente)
    db_session.flush()
    antes = _foto(existente)

    body = _cargar(client, headers, _zip(**{"Laura Gomez.pdf": _cv("Laura Gomez", "laura.gomez@example.com")}))

    assert body["resumen"]["duplicados_omitidos"] == 1
    assert body["resumen"]["creados"] == 0
    db_session.expire_all()
    candidatos = _candidatos(db_session, empresa)
    assert len(candidatos) == 1
    assert _foto(candidatos[0]) == antes
