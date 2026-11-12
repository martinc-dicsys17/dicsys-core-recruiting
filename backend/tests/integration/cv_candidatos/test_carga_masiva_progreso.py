"""Carga masiva de CVs: avance real (procesados/total), cancelacion y estado del lote publicado para el frontend."""

import asyncio
import uuid

import fitz
import pytest
from fastapi import HTTPException

from backend.modules.recruiting.models import Candidato
from backend.modules.recruiting.services import CandidatoService, _ArchivoEnMemoria


def _cv(nombre: str, email: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate((nombre, "Analista QA", email, "Cordoba, Argentina")):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


@pytest.fixture
def escenario(data_factory, db_session, fake_storage, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CV_STORAGE_DIR", str(tmp_path / "cv"))
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path / "tmp"))
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.flush()
    return empresa, usuario


def _archivos(n: int, prefijo: str = "avance"):
    return [
        _ArchivoEnMemoria(f"{prefijo}_{i}.pdf", _cv(f"Persona {i}", f"{prefijo}.{i}@example.com")) for i in range(n)
    ]


def _procesar(db, empresa, usuario, archivos, **kw):
    return asyncio.run(
        CandidatoService.procesar_carga_masiva_zip_rar(
            db=db, empresa_id=empresa.id, archivos=archivos, usuario=usuario.email, current_user=usuario, **kw
        )
    )


@pytest.mark.integration
def test_el_avance_se_informa_por_cada_cv_procesado_hasta_el_total(db_session, escenario):  # noqa: F811
    empresa, usuario = escenario
    avances = []
    resultado = _procesar(db_session, empresa, usuario, _archivos(4), progreso=lambda p, t: avances.append((p, t)))
    assert avances == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]
    assert resultado["cancelado"] is False and resultado["total_avance"] == 4


@pytest.mark.integration
def test_los_rechazados_al_clasificar_cuentan_como_procesados_desde_el_inicio(db_session, escenario):  # noqa: F811
    empresa, usuario = escenario
    archivos = _archivos(2) + [_ArchivoEnMemoria("nota.txt", b"hola")]
    avances = []
    _procesar(db_session, empresa, usuario, archivos, progreso=lambda p, t: avances.append((p, t)))
    assert avances[0] == (1, 3) and avances[-1] == (3, 3)


@pytest.mark.integration
def test_cancelar_detiene_antes_del_proximo_cv_y_conserva_los_ya_creados(db_session, escenario):  # noqa: F811
    empresa, usuario = escenario
    avances = []
    resultado = _procesar(
        db_session,
        empresa,
        usuario,
        _archivos(5, "cancel"),
        progreso=lambda p, t: avances.append(p),
        cancelado=lambda: len(avances) >= 3,  # tras 2 CVs procesados
    )
    assert resultado["cancelado"] is True
    assert len(resultado["resultados"]) == 2 and resultado["resumen"]["creados"] == 2
    assert avances[-1] == 2
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 2


@pytest.mark.integration
def test_estado_del_lote_solo_lo_ve_su_usuario_y_empresa_y_la_cancelacion_se_registra(escenario, data_factory):  # noqa: F811
    empresa, usuario = escenario
    lote_id = str(uuid.uuid4())
    CandidatoService._guardar_estado_lote(
        lote_id,
        {
            "lote_id": lote_id,
            "empresa_id": str(empresa.id),
            "usuario_id": str(usuario.id),
            "estado": "procesando",
            "procesados": 2,
            "total": 10,
            "reporte": None,
            "error": None,
        },
    )
    estado = CandidatoService.obtener_estado_carga_masiva(lote_id, empresa.id, usuario)
    assert (estado["estado"], estado["procesados"], estado["total"]) == ("procesando", 2, 10)

    otro = data_factory.usuario(rol="admin")
    with pytest.raises(HTTPException) as e:
        CandidatoService.obtener_estado_carga_masiva(lote_id, empresa.id, otro)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        CandidatoService.cancelar_carga_masiva(lote_id, uuid.uuid4(), usuario)
    with pytest.raises(HTTPException):
        CandidatoService.obtener_estado_carga_masiva("no-es-uuid", empresa.id, usuario)

    import os

    CandidatoService.cancelar_carga_masiva(lote_id, empresa.id, usuario)
    assert os.path.exists(CandidatoService._ruta_lote(lote_id, ".cancel"))


@pytest.mark.integration
def test_cancelar_un_lote_terminado_no_deja_marca_residual(escenario):  # noqa: F811
    empresa, usuario = escenario
    lote_id = str(uuid.uuid4())
    CandidatoService._guardar_estado_lote(
        lote_id,
        {
            "lote_id": lote_id,
            "empresa_id": str(empresa.id),
            "usuario_id": str(usuario.id),
            "estado": "finalizado",
            "procesados": 1,
            "total": 1,
            "reporte": {"ok": True},
            "error": None,
        },
    )
    CandidatoService.cancelar_carga_masiva(lote_id, empresa.id, usuario)
    import os

    assert not os.path.exists(CandidatoService._ruta_lote(lote_id, ".cancel"))
