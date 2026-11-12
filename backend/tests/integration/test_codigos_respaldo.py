"""Códigos de respaldo del 2FA guardados como HMAC, de un solo uso, y migración de los viejos en claro (F02-P02)."""

import json
import re
from datetime import timedelta

import pyotp
import pytest

from backend.modules.auth.routers import create_access_token
from backend.modules.usuarios import secretos

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

PASSWORD = "clave-de-prueba-larga"


def _con_2fa(data_factory, db_session, guardados: str):
    usuario = data_factory.usuario(password=PASSWORD)
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    usuario.totp_secret = pyotp.random_base32()
    usuario.totp_enabled = True
    usuario.totp_backup_codes = guardados
    db_session.flush()
    return usuario


def _verificar(client, usuario, codigo):
    r = client.post("/api/v1/auth/login", json={"email": usuario.email, "password": PASSWORD})
    assert r.status_code == 200 and r.json()["requires_2fa"], r.text
    return client.post("/api/v1/auth/verify-2fa", json={"temp_token": r.json()["temp_token"], "code": codigo})


def test_generar_devuelve_codigos_de_10_caracteres_y_guarda_solo_hashes():
    codigos, guardados = secretos.generar()
    assert len(codigos) == 8 and len(set(codigos)) == 8
    assert all(re.fullmatch(r"[0-9a-f]{5}-[0-9a-f]{5}", c) for c in codigos)
    hashes = json.loads(guardados)
    assert all(h.startswith(secretos.PREFIJO) for h in hashes)
    assert not any(secretos.normalizar(c) in guardados or c in guardados for c in codigos)


def test_un_codigo_de_respaldo_sirve_una_vez_y_se_normaliza(client, data_factory, db_session):
    codigos, guardados = secretos.generar()
    usuario = _con_2fa(data_factory, db_session, guardados)

    r = _verificar(client, usuario, codigos[0].upper().replace("-", " "))
    assert r.status_code == 200, r.text
    assert _verificar(client, usuario, codigos[0]).status_code == 401, "el mismo código no sirve dos veces"
    assert _verificar(client, usuario, "00000-00000").status_code == 401
    assert _verificar(client, usuario, codigos[1]).status_code == 200
    db_session.refresh(usuario)
    assert len(json.loads(usuario.totp_backup_codes)) == 6


def test_los_codigos_viejos_en_claro_siguen_valiendo_despues_de_migrar(client, data_factory, db_session):
    viejos = ["a1b2c3d4", "e5f6a7b8"]  # formato anterior: 8 hex en claro
    usuario = _con_2fa(data_factory, db_session, json.dumps(viejos))
    assert _verificar(client, usuario, viejos[0]).status_code == 401, "en claro ya no se comparan"

    migrados = secretos.migrar(usuario.totp_backup_codes)
    assert migrados is not None and "a1b2c3d4" not in migrados
    assert secretos.migrar(migrados) is None, "la migración es idempotente"
    usuario.totp_backup_codes = migrados
    db_session.flush()

    assert _verificar(client, usuario, viejos[0]).status_code == 200
    assert _verificar(client, usuario, viejos[0]).status_code == 401


def test_activar_el_2fa_devuelve_los_codigos_una_vez_y_guarda_hashes(client, data_factory, db_session):
    usuario = data_factory.usuario()
    token = create_access_token(
        {"sub": usuario.email, "user_id": str(usuario.id), "purpose": "2fa_setup"}, timedelta(minutes=15)
    )
    headers = {"Authorization": f"Bearer {token}"}
    secreto = client.post("/api/v1/auth/me/2fa/setup", headers=headers).json()["secret_manual"]

    r = client.post("/api/v1/auth/me/2fa/enable", headers=headers, json={"code": pyotp.TOTP(secreto).now()})
    assert r.status_code == 200, r.text
    codigos = r.json()["backup_codes"]
    assert len(codigos) == 8 and all(len(secretos.normalizar(c)) == 10 for c in codigos)
    db_session.refresh(usuario)
    assert not any(secretos.normalizar(c) in usuario.totp_backup_codes for c in codigos)
