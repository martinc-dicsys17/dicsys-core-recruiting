"""Un ticket dado de baja no se puede consultar por id (PG-20): el listado ya lo ocultaba y el detalle lo seguía
devolviendo completo."""

import uuid

import pytest

from backend.core.utils import utc_now
from backend.modules.soporte.models import SoporteCategoria, SoporteSubcategoria, SoporteTicketsEstado, Ticket
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def ticket(db_session, data_factory):
    empresa = data_factory.empresa()
    admin = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(admin, empresa)
    estado = SoporteTicketsEstado(nombre="Abierto", clave=f"abierto-{uuid.uuid4().hex[:8]}")
    categoria = SoporteCategoria(empresa_id=empresa.id, nombre_display="Software", nombre_normalizado="software")
    subcategoria = SoporteSubcategoria(
        empresa_id=empresa.id, categoria=categoria, nombre_display="Aplicaciones", nombre_normalizado="aplicaciones"
    )
    db_session.add_all([estado, categoria, subcategoria])
    db_session.flush()
    ticket = Ticket(
        empresa_id=empresa.id,
        numero=1,
        titulo="No anda el correo",
        estado_id=estado.id,
        subcategoria_id=subcategoria.id,
        solicitante_id=data_factory.empleado(empresa).id,
    )
    db_session.add(ticket)
    db_session.flush()
    return ticket, auth_headers(admin, empresa)


def test_el_detalle_de_un_ticket_dado_de_baja_da_404(client, db_session, ticket):
    ticket, headers = ticket
    url = f"/api/v1/soporte/tickets/{ticket.id}"
    vivo = client.get(url, headers=headers)
    assert vivo.status_code == 200, vivo.text
    assert vivo.json()["titulo"] == "No anda el correo"

    ticket.deleted_at = utc_now()
    db_session.flush()

    assert client.get(url, headers=headers).status_code == 404
