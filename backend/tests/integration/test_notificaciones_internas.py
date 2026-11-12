import pytest

from backend.modules.notificaciones_internas.models import NotificacionInterna
from backend.modules.notificaciones_internas.services import NotificacionInternaService
from backend.tests.helpers.auth import auth_headers


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_notification_service_delivers_once_to_explicit_users_and_groups(
    db_session,
    data_factory,
):
    empresa = data_factory.empresa()
    destinatario_directo = data_factory.usuario()
    destinatario_grupo = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(destinatario_directo, empresa)
    data_factory.asignar_empresa(destinatario_grupo, empresa)
    data_factory.asignar_grupo(destinatario_directo, grupo, empresa)
    data_factory.asignar_grupo(destinatario_grupo, grupo, empresa)

    enviadas = NotificacionInternaService.enviar(
        db_session,
        empresa.id,
        titulo="Accion requerida",
        mensaje="Revisa la solicitud pendiente.",
        usuario_ids=[str(destinatario_directo.id)],
        grupo_ids=[str(grupo.id)],
        origen="tests.notificaciones",
    )

    assert {notificacion.usuario_id for notificacion in enviadas} == {
        destinatario_directo.id,
        destinatario_grupo.id,
    }


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_user_can_read_delete_and_review_own_notification_history(
    client,
    db_session,
    data_factory,
):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    otro_usuario = data_factory.usuario()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_empresa(otro_usuario, empresa)

    propia = NotificacionInternaService.enviar(
        db_session,
        empresa.id,
        titulo="Aviso propio",
        mensaje="Visible solo para el destinatario.",
        usuario_ids=[str(usuario.id)],
        origen="tests.notificaciones",
    )[0]
    NotificacionInternaService.enviar(
        db_session,
        empresa.id,
        titulo="Aviso ajeno",
        mensaje="No debe aparecer en la bandeja del primer usuario.",
        usuario_ids=[str(otro_usuario.id)],
        origen="tests.notificaciones",
    )
    headers = auth_headers(usuario, empresa)

    bandeja = client.get("/api/v1/notificaciones-internas", headers=headers)

    assert bandeja.status_code == 200
    assert [item["id"] for item in bandeja.json()["items"]] == [str(propia.id)]
    assert bandeja.json()["total_no_leidas"] == 1

    lectura = client.put(f"/api/v1/notificaciones-internas/{propia.id}/leer", headers=headers)
    eliminacion = client.delete(f"/api/v1/notificaciones-internas/{propia.id}", headers=headers)
    historial = client.get("/api/v1/notificaciones-internas/historial", headers=headers)

    assert lectura.status_code == 200
    assert lectura.json()["leida_at"] is not None
    assert eliminacion.status_code == 200
    assert eliminacion.json() == {"ok": True}
    assert historial.status_code == 200
    assert historial.json()["total"] == 0

    persistida = db_session.get(NotificacionInterna, propia.id)
    assert persistida.leida_at is not None
    assert persistida.deleted_at is not None


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_notification_audit_is_only_available_to_administrators(
    client,
    db_session,
    data_factory,
):
    empresa = data_factory.empresa()
    administrador = data_factory.usuario(rol="admin")
    usuario = data_factory.usuario(email="destinatario@example.com")
    data_factory.asignar_empresa(administrador, empresa)
    data_factory.asignar_empresa(usuario, empresa)
    notificacion = NotificacionInternaService.enviar(
        db_session,
        empresa.id,
        titulo="Registro auditable",
        mensaje="Debe permanecer disponible como evidencia.",
        usuario_ids=[str(usuario.id)],
        origen="tests.auditoria",
    )[0]
    NotificacionInternaService.eliminar(db_session, empresa.id, usuario.id, str(notificacion.id))

    prohibida = client.get(
        "/api/v1/notificaciones-internas/auditoria",
        headers=auth_headers(usuario, empresa),
    )
    auditoria = client.get(
        "/api/v1/notificaciones-internas/auditoria",
        headers=auth_headers(administrador, empresa),
    )

    assert prohibida.status_code == 403
    assert auditoria.status_code == 200
    assert auditoria.json()["total"] == 1
    item = auditoria.json()["items"][0]
    assert item["usuario_email"] == usuario.email
    assert item["deleted_at"] is not None
    assert item["origen"] == "tests.auditoria"
