import pytest


@pytest.mark.smoke
@pytest.mark.deploy_gate
def test_health_reports_healthy_without_running_production_bootstrap(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.smoke
def test_root_exposes_application_identity(client):
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["docs"] == "/docs"
    assert payload["reference"] == "/reference"


@pytest.mark.smoke
def test_openapi_json_con_operation_id_unicos(client):
    """El contrato que leen Scalar, la tool de QA y el cliente TypeScript de la SPA (F08)."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    esquema = response.json()
    assert esquema["openapi"].startswith("3.") and esquema["paths"]
    ids = [op["operationId"] for item in esquema["paths"].values() for op in item.values() if "operationId" in op]
    sin_id = [
        f"{metodo.upper()} {path}"
        for path, item in esquema["paths"].items()
        for metodo, op in item.items()
        if isinstance(op, dict) and "responses" in op and "operationId" not in op
    ]
    assert not sin_id, sin_id
    assert len(ids) == len(set(ids)), "operationId repetidos"


@pytest.mark.smoke
def test_reference_sirve_scalar_sin_proxy_ni_agente_ni_telemetria(client):
    response = client.get("/reference")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "/openapi.json" in html and "@scalar/api-reference" in html
    assert "proxy.scalar.com" not in html
    assert '"agent": {"disabled": true}' in html and '"telemetry": false' in html
