import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import backend.models_registry  # noqa: F401
from backend.core.email import email_service
from backend.core.llm import llm_generator
from backend.core.storage import cloud_storage
from backend.core.webex import webex_service
from backend.database import Base, engine, get_db
from backend.main import create_app
from backend.tests.factories import CoreDataFactory
from backend.tests.fakes import (
    FakeEmailService,
    FakeLLMGenerator,
    FakeWebexService,
    InMemoryStorageBackend,
)


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    # create_all por velocidad: da el mismo esquema que las migraciones, y test_migraciones.py prueba la cadena de
    # Alembic aparte (upgrade desde cero, alembic check, adopción de bases anteriores)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session(database_schema):
    connection = engine.connect()
    transaction = connection.begin()
    testing_session = sessionmaker(
        bind=connection,
        autocommit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = testing_session()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def data_factory(db_session):
    return CoreDataFactory(db_session)


@pytest.fixture
def fake_email():
    previous = email_service.adapter
    fake = FakeEmailService()
    email_service.set_adapter(fake)
    yield fake
    email_service.set_adapter(previous)


@pytest.fixture
def fake_webex():
    previous = webex_service.adapter
    fake = FakeWebexService()
    webex_service.set_adapter(fake)
    yield fake
    webex_service.set_adapter(previous)


@pytest.fixture
def fake_storage():
    previous = cloud_storage.backend
    backend = InMemoryStorageBackend()
    cloud_storage.backend = backend
    yield backend
    cloud_storage.backend = previous


@pytest.fixture
def fake_llm():
    previous = llm_generator.adapter
    fake = FakeLLMGenerator()
    llm_generator.set_adapter(fake)
    yield fake
    llm_generator.set_adapter(previous)


@pytest.fixture
def app(db_session):
    application = create_app(testing=True)

    def override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
