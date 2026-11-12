"""
Configuración de base de datos para FastAPI con SQLAlchemy. (v28.0 Pure)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import settings

# Motor de base de datos
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Sesión de base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()


def get_db():
    """
    Dependencia para obtener sesión de base de datos.
    Se usa con Depends() en FastAPI.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
