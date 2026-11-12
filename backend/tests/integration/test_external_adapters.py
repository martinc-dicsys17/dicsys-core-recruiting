import pytest

from backend.core.llm import generate
from backend.core.webex import webex_service


@pytest.mark.integration
def test_password_recovery_uses_the_email_adapter(
    client,
    data_factory,
    fake_email,
):
    usuario = data_factory.usuario()

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": usuario.email},
    )

    assert response.status_code == 200
    assert len(fake_email.messages) == 1
    assert fake_email.messages[0]["to"] == usuario.email


@pytest.mark.integration
def test_password_recovery_answers_the_same_if_the_email_fails(client, data_factory, fake_email, monkeypatch):
    """PG-24: si el envío falla, la recuperación responde el mensaje de siempre (antes, 500 por un NameError)."""
    usuario = data_factory.usuario()

    def falla(**kwargs):
        raise RuntimeError("SendGrid no está configurado")

    monkeypatch.setattr(fake_email, "send", falla)
    response = client.post("/api/v1/auth/forgot-password", json={"email": usuario.email})

    assert response.status_code == 200
    assert response.json()["message"].startswith("Si el correo existe")


@pytest.mark.integration
def test_storage_endpoint_uses_the_configured_backend(client, fake_storage):
    fake_storage.upload("documents/test.txt", b"stored-content", "text/plain")

    response = client.get("/storage/documents/test.txt")

    assert response.status_code == 200
    assert response.content == b"stored-content"


def test_webex_adapter_records_messages(fake_webex):
    result = webex_service.send_text(
        text="Deploy ready",
        room_id="test-room",
    )

    assert result["success"] is True
    assert fake_webex.messages[0]["text"] == "Deploy ready"


def test_llm_adapter_returns_a_deterministic_result(fake_llm):
    result = generate(
        modulo="testing",
        contents="Respond only with OK",
    )

    assert result.text == "OK"
    assert fake_llm.calls[0]["modulo"] == "testing"
