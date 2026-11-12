"""
Configuración centralizada de la aplicación.
"""

from typing import List

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores de ejemplo de .env.template: con ENVIRONMENT=production el backend no arranca si aparecen (F02-P05)
SECRETOS_DEL_TEMPLATE = {
    "secret_key": "tu-clave-secreta-aqui-cambiar-en-produccion",
    "jwt_secret_key": "jwt-secret-key-cambiar-en-produccion",
}
PASSWORD_POSTGRES_DEL_TEMPLATE = "postgres123"


class Settings(BaseSettings):
    """Configuración de la aplicación usando Pydantic Settings."""

    # Información de la aplicación
    app_name: str
    app_version: str
    description: str = "Sistema de gestión empresarial con FastAPI y PostgreSQL"

    # Configuración del servidor
    debug: bool
    host: str
    port: int
    reload: bool

    # Seguridad
    secret_key: str
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    # Refresh token de la sesión del navegador (F07-P03, D-12): cada uno vive estos días desde que se emite y rota en
    # cada refresh, así que una sesión activa no vence; una que no se usa en ese plazo, sí
    refresh_token_expire_days: int = 7
    # Puente de sesión (F07-P05): con esto prendido, login, 2FA, Google y elegir o cambiar de empresa emiten también el
    # refresh en la cookie. Apagado, todo sigue como antes de F07 (rollback). Secure de esa cookie: sin valor, fuera de
    # desarrollo; el stack de QA, que corre por http, lo apaga como hace con SESSION_COOKIE_SECURE del frontend
    auth_refresh_enabled: bool = False
    refresh_cookie_secure: bool | None = None
    # Límite de intentos en el ingreso (F07-P07, backend/core/limites.py), en 15 minutos: fallos de contraseña por
    # cuenta, códigos 2FA incorrectos por cuenta, correos de recuperación por email y, por IP, todo eso junto con los
    # enlaces inválidos. Por proceso: con N workers el tope efectivo puede llegar a N veces este. X-Cliente-IP (la IP
    # del navegador que manda Flask) se cree solo si el pedido llega de estas redes
    # Página de prueba de la sesión del navegador (F07-P12): /prueba/sesion.html, servida por la API. Para desarrollo y
    # QA; necesita AUTH_REFRESH_ENABLED para que el login emita la cookie
    pagina_de_prueba_de_sesion: bool = False
    limite_login_por_cuenta: int = 10
    limite_2fa_por_cuenta: int = 5
    limite_correos_por_cuenta: int = 3
    limite_intentos_por_ip: int = 50
    ips_confiables: str = "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1/128,fc00::/7"

    # Base de datos PostgreSQL
    database_url: str

    # Entorno
    environment: str = "development"
    # Tareas programadas (F06-P01, D-10): el programador de F19 arranca solo en el proceso con CRON_ENABLED=true, el
    # servicio scheduler del compose (una réplica). El backend que atiende la API lo tiene apagado
    cron_enabled: bool = False

    # CORS: los orígenes que pueden llamar a la API desde el navegador con credenciales. En producción la SPA y la API
    # comparten origen; en desarrollo, Vite (http://localhost:5173) sin el proxy de F08 (F07-P10). Nunca "*": con la
    # cookie del refresh, cualquier sitio podría pedir /auth/refresh y leer el access token
    cors_origins: List[str]

    # URL pública del frontend (para links en emails, etc.)
    frontend_url: str = "http://localhost"

    # Configuración de la API
    api_v1_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    # Email (SendGrid)
    sendgrid_api_key: str = ""
    email_from: str = "noreply@example.com"

    # Storage
    storage_local_path: str = "/data/files"

    # Google Cloud Storage (para datos críticos)
    gcs_bucket_name: str = ""
    gcs_credentials_path: str = ""

    # Google Sheets (solo lectura): cuenta de servicio propia; vacío = la del bucket
    google_sheets_credentials_path: str = ""

    # Webex Teams
    webex_bot_token: str = ""
    webex_default_room_id: str = ""

    # Dominios de email permitidos (coma) para la sincronización de membresías Webex.
    webex_sync_allowed_domains: str = "dicsys.com,dicsys.ai"

    # Webex integración "lectora" (OAuth): los bots no pueden leer el historial
    # de salas grupales, así que la lectura del canal de presentaciones usa los
    # tokens de una cuenta de usuario autorizada vía OAuth.
    webex_reader_client_id: str = ""
    webex_reader_client_secret: str = ""
    # Override opcional del redirect URI; si está vacío se deriva del host del
    # frontend en cada request (funciona igual en localhost y producción).
    webex_reader_redirect_uri: str = ""

    # Whitelist de emails para admin de recibos (separados por coma)
    recibos_admin_allowed_emails: str = ""

    # Contraseña del admin que el seed crea en una base vacía (solo desarrollo). Vacía: se genera una aleatoria,
    # que no se muestra en ningún lado.
    seed_admin_password: str = ""

    # Pepper de los códigos de respaldo del 2FA (HMAC, fuera de la base). Vacío: usa SECRET_KEY. Cambiarlo invalida
    # los códigos guardados.
    backup_codes_pepper: str = ""

    # LLM (Google Gemini)
    llm_enabled: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llm_storage_path: str = "/data/llm"

    # Proveedor OpenID Connect (F21, docs/OIDC.md). issuer: la URL pública de Core, exacta y sin barra final (vacío:
    # frontend_url). Claves de firma: un PEM por kid en oidc_claves_dir; firma oidc_kid_activa (vacío: OIDC apagado).
    oidc_issuer: str = ""
    oidc_claves_dir: str = "/app/secrets/oidc"
    oidc_kid_activa: str = ""

    # Ingreso con Google (F22, docs/IngresoGoogle.md): cliente OAuth del Workspace de dicsys.ai. Vacíos: apagado.
    # La URL de vuelta registrada en Google es frontend_url + /login/google/callback.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("refresh_cookie_secure", mode="before")
    @classmethod
    def _vacio_es_sin_valor(cls, valor):
        """REFRESH_COOKIE_SECURE= (vacía en el .env) es lo mismo que no ponerla: Secure según el entorno."""
        return None if isinstance(valor, str) and not valor.strip() else valor

    @field_validator("cors_origins")
    @classmethod
    def _sin_comodin(cls, origenes: List[str]) -> List[str]:
        if "*" in origenes:
            raise ValueError(
                'CORS_ORIGINS no admite "*": la API acepta credenciales (la cookie del refresh) y con el comodín '
                "cualquier sitio podría usarlas. Listá los orígenes uno por uno."
            )
        return origenes

    @model_validator(mode="after")
    def _guarda_de_produccion(self):
        """En producción no se arranca con DEBUG activo ni con los secretos de ejemplo del .env.template."""
        if self.environment.strip().lower() != "production":
            return self
        problemas = []
        if self.debug:
            problemas.append("DEBUG está activo")
        problemas += [
            f"{campo.upper()} es el valor de ejemplo del .env.template"
            for campo, ejemplo in SECRETOS_DEL_TEMPLATE.items()
            if getattr(self, campo) == ejemplo
        ]
        if f":{PASSWORD_POSTGRES_DEL_TEMPLATE}@" in self.database_url:
            problemas.append("DATABASE_URL usa la contraseña de ejemplo del .env.template")
        if problemas:
            raise ValueError("ENVIRONMENT=production no arranca: " + "; ".join(problemas))
        return self


# Instancia global de configuración
settings = Settings()


def get_parameter(key: str, default_value=None, db=None):
    """
    Lee un parámetro del sistema desde core_parametros (módulo Configuración → Parámetros).
    Resolución: valor → valor_default → default_value del caller.

    Uso desde cualquier módulo:
        from backend.core import config
        room_id = config.get_parameter('webex_room_birthdate_id', settings.webex_default_room_id)

    Args:
        key: key del parámetro (ej: 'webex_room_birthdate_id').
        default_value: valor a devolver si el parámetro no existe o está vacío.
        db: sesión SQLAlchemy opcional; si no se pasa, se abre y cierra una propia.
    """
    # Imports locales para evitar import circular (database importa core.config)
    from backend.database import SessionLocal
    from backend.modules.parametros.models import Parametro

    session = db or SessionLocal()
    try:
        parametro = session.query(Parametro).filter(Parametro.key == key, Parametro.deleted_at.is_(None)).first()
        if parametro is None:
            return default_value
        if parametro.valor not in (None, ""):
            return parametro.valor
        if parametro.valor_default not in (None, ""):
            return parametro.valor_default
        return default_value
    except Exception:
        # Ante cualquier error de DB devolvemos el default para no romper al caller
        return default_value
    finally:
        if db is None:
            session.close()
