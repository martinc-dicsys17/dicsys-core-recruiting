"""Revalidación de los avisos de procesamiento de un lote.

`errores_detalle` es la foto del momento de la carga. Los errores del PDF son
hechos inmutables; 'no se encontró empleado en nómina' no: si el empleado se dio
de alta después, el aviso dejó de aplicar.
"""

import uuid

import pytest

from backend.core.utils import utc_now
from backend.modules.nomina.models import Empleado
from backend.modules.recibos.models import LoteRecibo
from backend.modules.recibos.services import LoteReciboService

pytestmark = pytest.mark.services

CUIL_SIN_ALTA = 27362341820
CUIL_DADO_DE_ALTA = 20351447096


def aviso_sin_empleado(cuil, pagina=381):
    return {
        "tipo": "warning_sin_empleado",
        "pagina_original": pagina + 1,
        "pagina_duplicado": pagina,
        "cuil": str(cuil),
        "descripcion": f"CUIL {cuil}: no se encontró empleado en nómina",
    }


ERROR_DEL_PDF = {
    "tipo": "error_extraccion",
    "pagina": 7,
    "descripcion": "No se encontró CUIL en la página 7",
}


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def lote(db_session, empresa):
    lote = LoteRecibo(
        empresa_id=empresa.id,
        periodo="2026-12",
        tipo_liquidacion="Liquidación Mensual",
        estado="procesado",
        archivo_original="masivo.pdf",
        archivo_nombre="lote.pdf",
    )
    db_session.add(lote)
    db_session.flush()
    return lote


def alta_empleado(db_session, empresa, cuil, deleted=False):
    sufijo = uuid.uuid4().hex[:8]
    empleado = Empleado(
        empresa_id=empresa.id,
        codigo=f"E-{sufijo}",
        cuil=cuil,
        apellido="Perez",
        nombre="Ana",
        dni=int(str(cuil)[2:10]),
        deleted_at=utc_now() if deleted else None,
    )
    db_session.add(empleado)
    db_session.flush()
    return empleado


def test_sin_avisos_devuelve_lista_vacia(db_session, empresa, lote):
    lote.errores_detalle = None

    assert LoteReciboService.avisos_vigentes(db_session, empresa.id, lote) == []


def test_el_aviso_sigue_si_el_empleado_no_esta_en_nomina(db_session, empresa, lote):
    lote.errores_detalle = [aviso_sin_empleado(CUIL_SIN_ALTA)]

    vigentes = LoteReciboService.avisos_vigentes(db_session, empresa.id, lote)

    assert len(vigentes) == 1
    assert vigentes[0]["cuil"] == str(CUIL_SIN_ALTA)


def test_el_aviso_desaparece_cuando_el_empleado_se_da_de_alta(db_session, empresa, lote):
    alta_empleado(db_session, empresa, CUIL_DADO_DE_ALTA)
    lote.errores_detalle = [aviso_sin_empleado(CUIL_DADO_DE_ALTA)]

    assert LoteReciboService.avisos_vigentes(db_session, empresa.id, lote) == []


def test_solo_desaparecen_los_avisos_resueltos(db_session, empresa, lote):
    alta_empleado(db_session, empresa, CUIL_DADO_DE_ALTA)
    lote.errores_detalle = [
        aviso_sin_empleado(CUIL_SIN_ALTA, 381),
        aviso_sin_empleado(CUIL_DADO_DE_ALTA, 383),
    ]

    vigentes = LoteReciboService.avisos_vigentes(db_session, empresa.id, lote)

    assert [a["cuil"] for a in vigentes] == [str(CUIL_SIN_ALTA)]


def test_los_errores_del_pdf_no_se_revalidan(db_session, empresa, lote):
    # Una página sin CUIL es un hecho del archivo: dar de alta empleados no lo cambia.
    alta_empleado(db_session, empresa, CUIL_DADO_DE_ALTA)
    lote.errores_detalle = [ERROR_DEL_PDF, aviso_sin_empleado(CUIL_DADO_DE_ALTA)]

    assert LoteReciboService.avisos_vigentes(db_session, empresa.id, lote) == [ERROR_DEL_PDF]


def test_un_empleado_de_otra_empresa_no_resuelve_el_aviso(db_session, data_factory, empresa, lote):
    alta_empleado(db_session, data_factory.empresa(), CUIL_DADO_DE_ALTA)
    lote.errores_detalle = [aviso_sin_empleado(CUIL_DADO_DE_ALTA)]

    assert len(LoteReciboService.avisos_vigentes(db_session, empresa.id, lote)) == 1


def test_un_empleado_dado_de_baja_no_resuelve_el_aviso(db_session, empresa, lote):
    alta_empleado(db_session, empresa, CUIL_DADO_DE_ALTA, deleted=True)
    lote.errores_detalle = [aviso_sin_empleado(CUIL_DADO_DE_ALTA)]

    assert len(LoteReciboService.avisos_vigentes(db_session, empresa.id, lote)) == 1


def test_un_aviso_sin_cuil_no_rompe(db_session, empresa, lote):
    lote.errores_detalle = [{"tipo": "warning_sin_empleado", "descripcion": "sin cuil"}]

    assert len(LoteReciboService.avisos_vigentes(db_session, empresa.id, lote)) == 1
