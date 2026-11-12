"""GCS con la identidad del entorno (F06-P04): sin clave JSON, las URLs firmadas van por IAM signBlob."""

import logging

import pytest

from backend.core.storage import GCSStorageBackend

pytestmark = pytest.mark.services


class Blob:
    def __init__(self, key):
        self.key, self.pedido = key, None

    def generate_signed_url(self, **kwargs):
        self.pedido = kwargs
        return f"https://storage.googleapis.com/b/{self.key}?firmada"


class Bucket:
    def __init__(self):
        self.ultimo = None

    def blob(self, key):
        self.ultimo = Blob(key)
        return self.ultimo


class ConClave:
    """Service account de un JSON: firma con su clave privada."""

    def sign_bytes(self, datos):
        return b"firma"


class DeLaVm:
    """Identidad de Compute Engine: sin clave privada; email y token recién después de refrescar."""

    def __init__(self):
        self.valid, self.service_account_email, self.token = False, "default", None

    def refresh(self, request):
        self.valid, self.service_account_email, self.token = True, "core-vm@proyecto.iam.gserviceaccount.com", "tk"


def _backend(credenciales) -> GCSStorageBackend:
    backend = GCSStorageBackend.__new__(GCSStorageBackend)
    backend.credenciales, backend.bucket = credenciales, Bucket()
    return backend


def test_con_la_clave_de_un_json_firma_localmente():
    backend = _backend(ConClave())

    assert backend.get_url("a/b.pdf", expires=60).endswith("?firmada")
    pedido = backend.bucket.ultimo.pedido
    assert pedido["version"] == "v4" and pedido["method"] == "GET" and pedido["expiration"].total_seconds() == 60
    assert "service_account_email" not in pedido and "access_token" not in pedido


def test_con_la_identidad_de_la_vm_firma_por_iam_con_su_email_y_token():
    backend = _backend(DeLaVm())

    backend.get_url("a/b.pdf")

    pedido = backend.bucket.ultimo.pedido
    assert pedido["service_account_email"] == "core-vm@proyecto.iam.gserviceaccount.com"
    assert pedido["access_token"] == "tk" and pedido["version"] == "v4"


def test_sin_json_o_con_uno_que_no_existe_usa_la_identidad_del_entorno(monkeypatch, tmp_path, caplog):
    import google.auth
    from google.cloud import storage as gcs_storage

    vm = DeLaVm()
    clientes = []
    monkeypatch.setattr(google.auth, "default", lambda: (vm, "proyecto"))

    class Cliente:
        def __init__(self, credentials, project):
            clientes.append((credentials, project))

        def bucket(self, nombre):
            return Bucket()

    monkeypatch.setattr(gcs_storage, "Client", Cliente)

    GCSStorageBackend("bucket")
    with caplog.at_level(logging.WARNING):
        GCSStorageBackend("bucket", credentials_path=str(tmp_path / "no-existe.json"))

    assert clientes == [(vm, "proyecto"), (vm, "proyecto")]
    assert "no existe: uso la identidad del entorno" in caplog.text
