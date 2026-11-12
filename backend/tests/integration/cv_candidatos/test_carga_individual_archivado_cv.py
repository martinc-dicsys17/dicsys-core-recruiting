"""Archivado del CV original en la carga individual (mismas carpetas y CV_STORAGE_DIR que la carga masiva)."""

import os
import threading

import pytest

from backend.modules.recruiting.models import Candidato
from backend.modules.recruiting.services import CandidatoService
from backend.tests.integration.cv_candidatos.test_carga_cv_email import (  # noqa: F401
    CV_SIN_EMAIL,
    CV_VALIDO,
    _pdf,
    _subir,
    escenario,
)


def _archivos(tmp_path, carpeta):
    ruta = tmp_path / "cv_storage" / carpeta
    return (
        sorted(n for n in os.listdir(ruta) if not n.startswith(".")) if ruta.exists() else []
    )  # ignora el indice oculto de motivos


@pytest.mark.integration
def test_individual_creado_va_a_cv_procesados_ok(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]
    assert (tmp_path / "cv_storage" / "cv_procesados_ok" / "Laura Gomez.pdf").read_bytes() == CV_VALIDO
    assert _archivos(tmp_path, "cv_errores") == [] and _archivos(tmp_path, "cv_duplicados") == []


@pytest.mark.integration
def test_individual_duplicado_va_a_cv_duplicados(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 409
    assert _archivos(tmp_path, "cv_duplicados") == ["Laura Gomez.pdf"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]
    assert _archivos(tmp_path, "cv_errores") == []


@pytest.mark.integration
def test_individual_con_error_va_a_cv_errores(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_SIN_EMAIL, "Sin Email.pdf").status_code == 422
    assert _archivos(tmp_path, "cv_errores") == ["Sin Email.pdf"]
    assert _archivos(tmp_path, "cv_procesados_ok") == [] and _archivos(tmp_path, "cv_duplicados") == []


@pytest.mark.integration
def test_individual_mismo_nombre_no_sobrescribe(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_SIN_EMAIL, "cv.pdf").status_code == 422
    assert _subir(client, headers, CV_SIN_EMAIL, "cv.pdf").status_code == 422
    assert _archivos(tmp_path, "cv_errores") == ["cv.pdf", "cv_1.pdf"]


@pytest.mark.integration
def test_individual_falla_el_archivado_y_la_carga_continua(client, escenario, monkeypatch, tmp_path):  # noqa: F811
    archivo = tmp_path / "bloqueo"
    archivo.write_bytes(b"")
    monkeypatch.setenv("CV_STORAGE_DIR", str(archivo))  # no se puede crear una carpeta dentro de un archivo
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201


@pytest.mark.integration
def test_individual_sin_nombre_de_archivo_no_se_archiva(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    r = client.post(
        "/api/v1/recruiting/candidatos/cargar-cv",
        headers=headers,
        files={"archivo": ("", CV_VALIDO, "application/pdf")},
    )
    assert r.status_code >= 400
    assert not (tmp_path / "cv_storage").exists()


# --- Confirmacion de la actualizacion de un CV duplicado: el original se MUEVE de cv_duplicados a cv_procesados_ok ---

URL_ACTUALIZAR = "/api/v1/recruiting/candidatos/actualizar-cv"
CV_DISTINTO = _pdf("Laura Gomez", "Desarrolladora Backend", "laura.gomez@example.com", "Rosario, Argentina")
CV_DISTINTO_2 = _pdf("Laura Gomez", "Desarrolladora Frontend", "laura.gomez@example.com", "Mendoza, Argentina")


def _actualizar(client, headers, contenido, nombre):
    return client.post(URL_ACTUALIZAR, headers=headers, files={"archivo": (nombre, contenido, "application/pdf")})


def _leer(tmp_path, carpeta, nombre):
    return (tmp_path / "cv_storage" / carpeta / nombre).read_bytes()


def _candidatos_laura(db_session, empresa):  # noqa: F811
    return (
        db_session.query(Candidato)
        .filter(Candidato.empresa_id == empresa.id, Candidato.email == "laura.gomez@example.com")
        .all()
    )


@pytest.mark.integration
def test_actualizar_duplicado_mueve_el_archivo_a_procesados_ok(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    original = _candidatos_laura(db_session, empresa)[0]
    id_original, headline_original = original.id, original.headline

    # 1-2. CV duplicado (contenido distinto): queda en cv_duplicados
    assert _subir(client, headers, CV_DISTINTO, "Laura Gomez nuevo.pdf").status_code == 409
    assert _archivos(tmp_path, "cv_duplicados") == ["Laura Gomez nuevo.pdf"]

    # 3-4. Se confirma la actualizacion: se actualiza el candidato existente, sin crear otro
    assert _actualizar(client, headers, CV_DISTINTO, "Laura Gomez nuevo.pdf").status_code == 201
    db_session.expire_all()
    candidatos = _candidatos_laura(db_session, empresa)
    assert len(candidatos) == 1 and candidatos[0].id == id_original
    assert candidatos[0].headline != headline_original or candidatos[0].ubicacion != "Cordoba, Argentina"

    # 5-7. El archivo esta en cv_procesados_ok, ya no esta en cv_duplicados y no hay copias adicionales
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez nuevo.pdf", "Laura Gomez.pdf"]
    assert _leer(tmp_path, "cv_procesados_ok", "Laura Gomez nuevo.pdf") == CV_DISTINTO
    assert _archivos(tmp_path, "cv_duplicados") == []
    assert _archivos(tmp_path, "cv_errores") == []


@pytest.mark.integration
def test_actualizar_duplicado_mueve_la_copia_correcta_con_nombres_repetidos(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409
    assert _subir(client, headers, CV_DISTINTO_2, "nuevo.pdf").status_code == 409
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf", "nuevo_1.pdf"]

    # Se confirma el segundo: solo se mueve su copia (nuevo_1.pdf); la otra permanece intacta en duplicados
    assert _actualizar(client, headers, CV_DISTINTO_2, "nuevo.pdf").status_code == 201
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf"]
    assert _leer(tmp_path, "cv_duplicados", "nuevo.pdf") == CV_DISTINTO
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf", "nuevo.pdf"]
    assert _leer(tmp_path, "cv_procesados_ok", "nuevo.pdf") == CV_DISTINTO_2


@pytest.mark.integration
def test_actualizar_duplicado_con_nombre_ocupado_en_ok_no_sobrescribe(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert (
        _subir(client, headers, CV_DISTINTO, "Laura Gomez.pdf").status_code == 409
    )  # mismo nombre que el ya procesado
    assert _actualizar(client, headers, CV_DISTINTO, "Laura Gomez.pdf").status_code == 201
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf", "Laura Gomez_1.pdf"]
    assert _leer(tmp_path, "cv_procesados_ok", "Laura Gomez.pdf") == CV_VALIDO
    assert _leer(tmp_path, "cv_procesados_ok", "Laura Gomez_1.pdf") == CV_DISTINTO
    assert _archivos(tmp_path, "cv_duplicados") == []


@pytest.mark.integration
def test_actualizacion_fallida_no_mueve_el_archivo_de_duplicados(client, escenario, monkeypatch, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409

    def _falla(*a, **k):
        raise RuntimeError("fallo al actualizar")

    monkeypatch.setattr(CandidatoService, "_actualizar_desde_cv", _falla)
    assert _actualizar(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 500
    assert _leer(tmp_path, "cv_duplicados", "nuevo.pdf") == CV_DISTINTO  # permanece en duplicados
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf"]  # sin copias adicionales
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]  # nada se movio a OK
    assert _archivos(tmp_path, "cv_errores") == []  # tampoco se agrega otra copia como error


@pytest.mark.integration
def test_actualizacion_rechazada_por_la_base_no_pisa_el_cv_vinculado_ni_la_ficha(
    client,
    escenario,  # noqa: F811
    db_session,
    fake_storage,
    tmp_path,
):
    """Si la base rechaza la actualizacion confirmada, la ficha, su CV vinculado en el storage y el PDF de cv_duplicados quedan intactos."""
    from sqlalchemy import event

    headers, empresa = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    original = _candidatos_laura(db_session, empresa)[0]
    clave, headline, ubicacion = original.cv_url, original.headline, original.ubicacion
    assert fake_storage.files[clave]["content"] == CV_VALIDO
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409

    def _rechazar(session, flush_context, instances):
        raise RuntimeError("la base rechazo el cambio")

    event.listen(db_session, "before_flush", _rechazar)
    try:
        assert _actualizar(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 500
    finally:
        event.remove(db_session, "before_flush", _rechazar)

    db_session.expire_all()
    ficha = _candidatos_laura(db_session, empresa)[0]
    assert (ficha.cv_url, ficha.headline, ficha.ubicacion) == (clave, headline, ubicacion)
    assert fake_storage.files[clave]["content"] == CV_VALIDO  # el CV vinculado NO fue reemplazado por el rechazado
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]
    assert _archivos(tmp_path, "cv_errores") == []


@pytest.mark.integration
def test_cancelar_la_actualizacion_deja_el_archivo_en_duplicados(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409
    # El usuario cancela: el frontend no llama a actualizar-cv
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]


@pytest.mark.integration
def test_falla_el_movimiento_el_original_sigue_en_duplicados(client, escenario, monkeypatch, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409
    original = CandidatoService._escribir_cv_exclusivo

    def _destino_roto(carpeta, nombre, contenido):
        if carpeta.endswith("cv_procesados_ok"):
            raise OSError("disco lleno")
        return original(carpeta, nombre, contenido)

    monkeypatch.setattr(CandidatoService, "_escribir_cv_exclusivo", staticmethod(_destino_roto))
    # La actualizacion del candidato termina bien: un fallo del archivado nunca la interrumpe
    assert _actualizar(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 201
    assert _archivos(tmp_path, "cv_duplicados") == ["nuevo.pdf"]  # sin restos temporales
    assert _leer(tmp_path, "cv_duplicados", "nuevo.pdf") == CV_DISTINTO  # el origen no se perdio
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf"]


@pytest.mark.integration
def test_actualizar_sin_copia_previa_en_duplicados_se_archiva_en_ok(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _actualizar(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 201  # no hubo archivado previo
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf", "nuevo.pdf"]
    assert _archivos(tmp_path, "cv_duplicados") == []


@pytest.mark.integration
def test_confirmaciones_concurrentes_no_generan_copias_repetidas(client, escenario, tmp_path):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409
    barrera = threading.Barrier(8)

    def _mover():
        barrera.wait()
        CandidatoService._mover_cv_duplicado_a_ok("nuevo.pdf", CV_DISTINTO)

    hilos = [threading.Thread(target=_mover) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert _archivos(tmp_path, "cv_procesados_ok") == ["Laura Gomez.pdf", "nuevo.pdf"]
    assert _leer(tmp_path, "cv_procesados_ok", "nuevo.pdf") == CV_DISTINTO
    assert _archivos(tmp_path, "cv_duplicados") == []
