import sys
from pathlib import Path

import pytest

FRONTEND_ROOT = Path(__file__).resolve().parents[1]
if str(FRONTEND_ROOT) not in sys.path:
    sys.path.insert(0, str(FRONTEND_ROOT))

from app import create_app  # noqa: E402
from tests.fakes import FakeApi  # noqa: E402


@pytest.fixture
def fake_api():
    return FakeApi()


@pytest.fixture
def frontend_app(fake_api):
    return create_app(
        config={
            "TESTING": True,
            "SECRET_KEY": "frontend-test-secret",
            "API_URL": "http://backend.test",
        },
        api_request_func=fake_api,
    )


@pytest.fixture
def frontend_client(frontend_app):
    return frontend_app.test_client()
