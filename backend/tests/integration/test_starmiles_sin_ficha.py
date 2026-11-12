"""Un usuario sin ficha de empleado y sin permiso de aprobador no ve inscripciones ni canjes de otros (PG-21).

Antes, si el DNI del usuario no correspondía a ningún empleado, el filtro por empleado quedaba vacío y el listado
devolvía los de toda la empresa.
"""

import pytest

from backend.modules.starmiles.models import Canje, Desafio, InscripcionDesafio, ItemCanje
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(db_session, data_factory):
    empresa = data_factory.empresa()
    otro, yo = data_factory.empleado(empresa), data_factory.empleado(empresa)
    desafio = Desafio(empresa_id=empresa.id, nombre="Desafío", star_miles=100)
    item = ItemCanje(empresa_id=empresa.id, nombre="Premio", tipo="producto", star_miles_costo=40, stock=3)
    db_session.add_all(
        [
            desafio,
            item,
            InscripcionDesafio(empresa_id=empresa.id, desafio=desafio, empleado=otro, estado="pendiente"),
            Canje(empresa_id=empresa.id, item=item, empleado=otro, cantidad=1, star_miles_total=40, estado="pendiente"),
        ]
    )
    grupo = data_factory.grupo()
    data_factory.permisos(grupo, ["starmiles", "starmiles.home"])

    def usuario(dni):
        u = data_factory.usuario(dni=dni)
        data_factory.asignar_empresa(u, empresa)
        data_factory.asignar_grupo(u, grupo, empresa)
        return auth_headers(u, empresa)

    return {"empresa": empresa, "otro": otro, "yo": yo, "usuario": usuario}


@pytest.mark.parametrize("url", ["/api/v1/starmiles/inscripciones", "/api/v1/starmiles/canjes"])
@pytest.mark.parametrize("dni", [None, 99_999_999], ids=["sin_dni", "dni_sin_ficha"])
def test_sin_ficha_la_lista_sale_vacia(client, entorno, url, dni):
    respuesta = client.get(url, headers=entorno["usuario"](dni))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"] == [] and respuesta.json()["total"] == 0


@pytest.mark.parametrize("url", ["/api/v1/starmiles/inscripciones", "/api/v1/starmiles/canjes"])
def test_con_ficha_ve_solo_lo_suyo_aunque_pida_otro_empleado(client, entorno, url):
    otro = entorno["otro"]

    propio = client.get(url, headers=entorno["usuario"](otro.dni))
    ajeno_pedido = client.get(url, headers=entorno["usuario"](entorno["yo"].dni), params={"empleado_id": str(otro.id)})

    assert propio.status_code == 200 and propio.json()["total"] == 1
    assert ajeno_pedido.status_code == 200 and ajeno_pedido.json()["total"] == 0
