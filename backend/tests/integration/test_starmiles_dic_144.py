import pytest

from backend.modules.nomina.models import Empleado
from backend.modules.starmiles.models import (
    Canje,
    Desafio,
    EmpleadoStarMiles,
    InscripcionDesafio,
    ItemCanje,
)
from backend.modules.starmiles.services import (
    CanjeService,
    InscripcionDesafioService,
)


def crear_empleado(db_session, empresa_id, sufijo):
    empleado = Empleado(
        empresa_id=empresa_id,
        codigo=f"TEST-{sufijo}",
        cuil=20_000_000_000 + sufijo,
        dni=30_000_000 + sufijo,
        nombre="Empleado",
        apellido="Prueba",
    )
    db_session.add(empleado)
    db_session.flush()
    return empleado


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_revoke_requires_reintegrating_an_approved_redemption_and_updates_both_balances(
    db_session,
    data_factory,
):
    empresa = data_factory.empresa()
    empleado = crear_empleado(db_session, empresa.id, 1)
    aprobador = crear_empleado(db_session, empresa.id, 2)
    desafio = Desafio(empresa_id=empresa.id, nombre="Desafio completado", star_miles=100)
    item = ItemCanje(
        empresa_id=empresa.id,
        nombre="Premio",
        tipo="producto",
        star_miles_costo=40,
        stock=3,
    )
    inscripcion = InscripcionDesafio(
        empresa_id=empresa.id,
        desafio=desafio,
        empleado=empleado,
        estado="completada",
    )
    cuenta = EmpleadoStarMiles(
        empresa_id=empresa.id,
        empleado=empleado,
        millas_historicas=100,
        millas_disponibles=60,
    )
    canje = Canje(
        empresa_id=empresa.id,
        item=item,
        empleado=empleado,
        cantidad=1,
        star_miles_total=40,
        estado="aprobado",
    )
    db_session.add_all([desafio, item, inscripcion, cuenta, canje])
    db_session.commit()

    with pytest.raises(ValueError, match="reintegra"):
        InscripcionDesafioService.revocar(db_session, empresa.id, str(inscripcion.id), str(aprobador.id), "Duplicada")

    CanjeService.rechazar_y_reintegrar(db_session, empresa.id, str(canje.id), str(aprobador.id), "Canje sin respaldo")
    revocada = InscripcionDesafioService.revocar(
        db_session, empresa.id, str(inscripcion.id), str(aprobador.id), "Duplicada"
    )

    db_session.refresh(cuenta)
    db_session.refresh(canje)
    assert revocada.estado == "rechazada"
    assert cuenta.millas_historicas == 0
    assert cuenta.millas_disponibles == 0
    assert canje.estado == "rechazado"
    assert item.stock == 4


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_unique_challenge_blocks_completed_duplicate_but_allows_rejected_history(
    db_session,
    data_factory,
):
    empresa = data_factory.empresa()
    empleado = crear_empleado(db_session, empresa.id, 3)
    desafio = Desafio(
        empresa_id=empresa.id,
        nombre="Desafio unico",
        star_miles=10,
        inscripcion_unica_por_empleado=True,
    )
    completada = InscripcionDesafio(
        empresa_id=empresa.id,
        desafio=desafio,
        empleado=empleado,
        estado="completada",
    )
    db_session.add_all([desafio, completada])
    db_session.commit()

    with pytest.raises(ValueError, match="Ya est"):
        InscripcionDesafioService.crear(db_session, empresa.id, str(empleado.id), {"desafio_id": str(desafio.id)})

    completada.estado = "rechazada"
    db_session.commit()
    nueva = InscripcionDesafioService.crear(db_session, empresa.id, str(empleado.id), {"desafio_id": str(desafio.id)})

    assert nueva.estado == "pendiente"
