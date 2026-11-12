"""
Rutas de autenticación.
"""

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, File, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core import descargas
from backend.core.config import settings
from backend.core.email import email_service
from backend.core.files import delete_profile_image, save_profile_image
from backend.core.limites import Intentos
from backend.core.tokens import crear_token, decodificar
from backend.core.utils import utc_now
from backend.database import get_db
from backend.dependencies import get_empresa_activa
from backend.modules.auth import refresco
from backend.modules.auth.schemas import (
    ChangePasswordRequest,
    DescargaFirmada,
    EmpleadoEnEmpresa,
    EmpresaResumen,
    ForgotPasswordRequest,
    LoginRequest,
    MiPerfilUpdate,
    ModuloMenu,
    PedidoDescarga,
    ProfileUpdate,
    RefrescoResponse,
    ResetPasswordRequest,
    SeleccionarEmpresaRequest,
    SesionActual,
    TokenResponse,
    TwoFactorCodeRequest,
    TwoFactorEnableResponse,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
)
from backend.modules.empresa.services import EmpresaService
from backend.modules.nomina.models import Empleado
from backend.modules.permisos.menu_routers import menu_del_usuario
from backend.modules.permisos.services import GrupoService
from backend.modules.usuarios import emails, emails_corporativos, secretos
from backend.modules.usuarios.services import UsuarioService

router = APIRouter(prefix="/auth", tags=["autenticación"])

# Propósito del token intermedio del alta del 2FA obligatorio: solo lo aceptan me/2fa/setup y me/2fa/enable
ALTA_2FA = ("2fa_setup",)

# Esquema de seguridad Bearer para Swagger (auto_error=False para manejar el error manualmente)
security = HTTPBearer(auto_error=False)


def get_user_id_from_token(credentials: HTTPAuthorizationCredentials, propositos: tuple[str, ...] = ()) -> str:
    """Extrae el user_id del token JWT. Un token intermedio del 2FA solo pasa si su propósito está en `propositos`."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    payload = decodificar(credentials.credentials, propositos)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")
    return user_id


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """Crea un token JWT."""
    return crear_token(data, expires_delta)


@router.post("/login", operation_id="auth_login")
async def login(
    credentials: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(None),
    intentos: Intentos = Depends(Intentos),
):
    """Autentica un usuario y devuelve un token JWT.

    Flujo multi-empresa:
    - 0 empresas → error 403
    - 1 empresa → JWT con empresa_id (acceso directo)
    - >1 empresas → JWT temporal (5 min) sin empresa_id + lista de empresas

    El email puede ser el del usuario o el corporativo, principal o secundario, de su ficha (F22).

    Límite de intentos (F07-P07): los fallos cuentan por cuenta (con cualquiera de sus emails) y por IP.
    """
    usuario = UsuarioService.obtener_usuario_para_ingreso(db, credentials.email)
    cuenta = str(usuario.id) if usuario else credentials.email.lower()
    intentos.frenar(login=cuenta)

    if not usuario or not usuario.verify_password(credentials.password):
        intentos.contar(login=cuenta)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    intentos.olvidar(login=cuenta)

    return con_refresco(ingresar(db, usuario), response, db, refresh_token)


def ingresar(db: Session, usuario, pedir_2fa: bool = True):
    """Lo que sigue a identificar a la persona, con su contraseña o con Google (F22): la cuenta activa, el email
    corporativo, el 2FA, las empresas y el token. Con `pedir_2fa=False` no se piden ni el código ni el alta del 2FA."""
    if not usuario.activo:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario desactivado")

    # Con DNI y ficha de nómina, el email o el secundario tienen que ser de un dominio de la empresa (F22)
    if not emails_corporativos.tiene_email_corporativo(db, usuario):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=emails_corporativos.SIN_EMAIL_CORPORATIVO)

    # ─── 2FA: si tiene TOTP habilitado, devolver temp_token ───────────────
    if pedir_2fa and usuario.totp_enabled and usuario.totp_secret:
        temp_token = create_access_token(
            data={"sub": usuario.email, "user_id": str(usuario.id), "purpose": "2fa"},
            expires_delta=timedelta(minutes=5),
        )
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "user": {"nombre": usuario.nombre, "email": usuario.email},
        }

    # ─── 2FA requerido pero no configurado: forzar setup ──────────────────
    if pedir_2fa and usuario.totp_required and not usuario.totp_enabled:
        setup_token = create_access_token(
            data={"sub": usuario.email, "user_id": str(usuario.id), "purpose": "2fa_setup"},
            expires_delta=timedelta(minutes=15),
        )
        return {
            "requires_2fa_setup": True,
            "setup_token": setup_token,
            "user": {"nombre": usuario.nombre, "email": usuario.email},
        }

    UsuarioService.actualizar_ultimo_login(db, str(usuario.id))

    # ─── Multi-empresa: consultar empresas del usuario ────────────────────
    empresas = EmpresaService.listar_empresas_usuario(db, str(usuario.id))

    if len(empresas) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No tenés empresas asignadas. Contactá al administrador."
        )

    # Buscar empleado por DNI (JOIN lógico)
    # Si tiene 1 empresa, filtrar por ella. Si tiene varias, buscar en la primera.
    empleado_id = None
    empleado_foto = None
    empleado_foto_thumbnail = None
    empleado_perfil_nombre = None
    if usuario.dni and empresas:
        empleado = (
            db.query(Empleado)
            .filter(Empleado.dni == usuario.dni, Empleado.empresa_id == empresas[0].id, Empleado.deleted_at.is_(None))
            .first()
        )
        if empleado:
            empleado_id = str(empleado.id)
            empleado_foto = empleado.foto
            empleado_foto_thumbnail = (
                empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if empleado.foto else None
            )
            if empleado.perfil_rel:
                empleado_perfil_nombre = empleado.perfil_rel.nombre

    user_data = {
        "id": str(usuario.id),
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "dni": usuario.dni,
        "rol": usuario.rol,
        "avatar_url": usuario.avatar_url,
        "empleado_id": empleado_id,
        "empleado_foto": empleado_foto,
        "empleado_foto_thumbnail": empleado_foto_thumbnail,
        "empleado_perfil_nombre": empleado_perfil_nombre,
    }

    token_data = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol}

    if len(empresas) == 1:
        # Una sola empresa → JWT con empresa_id, acceso directo
        token_data["empresa_id"] = str(empresas[0].id)
        access_token = create_access_token(data=token_data)
        return TokenResponse(
            access_token=access_token,
            user=user_data,
            empresas=[EmpresaResumen.model_validate(empresas[0])],
            requiere_seleccion_empresa=False,
        )
    else:
        # Múltiples empresas → JWT temporal (5 min) sin empresa_id + lista
        access_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=5))
        empresas_resumen = [EmpresaResumen.model_validate(emp) for emp in empresas]
        return TokenResponse(
            access_token=access_token, user=user_data, empresas=empresas_resumen, requiere_seleccion_empresa=True
        )


@router.post("/seleccionar-empresa", response_model=TokenResponse, operation_id="auth_seleccionar_empresa")
async def seleccionar_empresa(
    datos: SeleccionarEmpresaRequest,
    response: Response,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    refresh_token: str | None = Cookie(None),
):
    """Selecciona una empresa después del login multi-empresa.

    Requiere JWT válido (puede ser temporal sin empresa_id).
    Valida que el usuario tenga acceso a la empresa solicitada.
    Genera nuevo JWT con empresa_id incluido.
    """
    user_id = get_user_id_from_token(credentials)

    # Verificar que el usuario existe y está activo
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario desactivado")

    # Verificar que el usuario tiene acceso a esa empresa
    empresas = EmpresaService.listar_empresas_usuario(db, user_id)
    empresa_seleccionada = None
    for emp in empresas:
        if str(emp.id) == datos.empresa_id:
            empresa_seleccionada = emp
            break

    if not empresa_seleccionada:
        raise HTTPException(status_code=403, detail="No tenés acceso a la empresa seleccionada")

    # Buscar empleado por DNI y empresa seleccionada
    empleado_id = None
    empleado_foto = None
    empleado_foto_thumbnail = None
    empleado_perfil_nombre = None
    if usuario.dni:
        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.dni == usuario.dni,
                Empleado.empresa_id == empresa_seleccionada.id,
                Empleado.deleted_at.is_(None),
            )
            .first()
        )
        if empleado:
            empleado_id = str(empleado.id)
            empleado_foto = empleado.foto
            empleado_foto_thumbnail = (
                empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if empleado.foto else None
            )
            if empleado.perfil_rel:
                empleado_perfil_nombre = empleado.perfil_rel.nombre

    # Generar nuevo JWT con empresa_id
    token_data = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol, "empresa_id": datos.empresa_id}
    access_token = create_access_token(data=token_data)

    user_data = {
        "id": str(usuario.id),
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "dni": usuario.dni,
        "rol": usuario.rol,
        "avatar_url": usuario.avatar_url,
        "empleado_id": empleado_id,
        "empleado_foto": empleado_foto,
        "empleado_foto_thumbnail": empleado_foto_thumbnail,
        "empleado_perfil_nombre": empleado_perfil_nombre,
    }

    return con_refresco(
        TokenResponse(access_token=access_token, user=user_data, requiere_seleccion_empresa=False),
        response,
        db,
        refresh_token,
    )


@router.post("/cambiar-empresa", response_model=TokenResponse, operation_id="auth_cambiar_empresa")
async def cambiar_empresa(
    datos: SeleccionarEmpresaRequest,
    response: Response,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    empresa_activa: str = Depends(get_empresa_activa),
    refresh_token: str | None = Cookie(None),
):
    """Cambia la empresa activa sin cerrar sesión.

    Requiere JWT con empresa_id previo (ya seleccionó una empresa).
    Valida que el usuario tenga acceso a la nueva empresa.
    Genera nuevo JWT con el nuevo empresa_id.
    """
    user_id = get_user_id_from_token(credentials)

    # Verificar que el usuario existe y está activo
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario desactivado")

    # Verificar que el usuario tiene acceso a esa empresa
    empresas = EmpresaService.listar_empresas_usuario(db, user_id)
    empresa_seleccionada = None
    for emp in empresas:
        if str(emp.id) == datos.empresa_id:
            empresa_seleccionada = emp
            break

    if not empresa_seleccionada:
        raise HTTPException(status_code=403, detail="No tenés acceso a la empresa seleccionada")

    # Buscar empleado por DNI y empresa seleccionada
    empleado_id = None
    empleado_foto = None
    empleado_foto_thumbnail = None
    empleado_perfil_nombre = None
    if usuario.dni:
        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.dni == usuario.dni,
                Empleado.empresa_id == empresa_seleccionada.id,
                Empleado.deleted_at.is_(None),
            )
            .first()
        )
        if empleado:
            empleado_id = str(empleado.id)
            empleado_foto = empleado.foto
            empleado_foto_thumbnail = (
                empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if empleado.foto else None
            )
            if empleado.perfil_rel:
                empleado_perfil_nombre = empleado.perfil_rel.nombre

    # Generar nuevo JWT con el nuevo empresa_id
    token_data = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol, "empresa_id": datos.empresa_id}
    access_token = create_access_token(data=token_data)

    user_data = {
        "id": str(usuario.id),
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "dni": usuario.dni,
        "rol": usuario.rol,
        "avatar_url": usuario.avatar_url,
        "empleado_id": empleado_id,
        "empleado_foto": empleado_foto,
        "empleado_foto_thumbnail": empleado_foto_thumbnail,
        "empleado_perfil_nombre": empleado_perfil_nombre,
    }

    return con_refresco(
        TokenResponse(access_token=access_token, user=user_data, requiere_seleccion_empresa=False),
        response,
        db,
        refresh_token,
    )


@router.get("/mis-empresas")
async def mis_empresas(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Lista las empresas del usuario autenticado (no requiere admin)."""
    user_id = get_user_id_from_token(credentials)
    empresas = EmpresaService.listar_empresas_usuario(db, user_id)
    return [EmpresaResumen.model_validate(e) for e in empresas]


def poner_cookie_de_refresco(response: Response, token: str) -> None:
    """La cookie del refresh: httpOnly, solo para /api/v1/auth, SameSite=Lax y Secure fuera de desarrollo."""
    response.set_cookie(
        refresco.COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=refresco.RUTA_COOKIE,
        httponly=True,
        secure=_cookie_segura(),
        samesite="lax",
    )


def _cookie_segura() -> bool:
    if settings.refresh_cookie_secure is not None:
        return settings.refresh_cookie_secure
    return settings.environment.strip().lower() != "development"


def con_refresco(respuesta, response: Response, db: Session, refresh_actual: str | None):
    """Puente de sesión (F07-P05): con AUTH_REFRESH_ENABLED, una respuesta que es una sesión completa (login, 2FA,
    Google, elegir o cambiar de empresa) lleva también el refresh en la cookie, con la empresa del token. Si el pedido
    traía uno (cambio de empresa), esa sesión se cierra. La selección de empresa pendiente y el 2FA en curso no
    emiten nada."""
    if not settings.auth_refresh_enabled or not isinstance(respuesta, TokenResponse):
        return respuesta
    if respuesta.requiere_seleccion_empresa:
        return respuesta
    datos = decodificar(respuesta.access_token)
    if refresh_actual:
        refresco.revocar(db, refresh_actual)
    empresa = uuid.UUID(datos["empresa_id"]) if datos.get("empresa_id") else None
    poner_cookie_de_refresco(response, refresco.emitir(db, uuid.UUID(datos["user_id"]), empresa))
    return respuesta


def _borrar_cookie_de_refresco(response: Response) -> None:
    response.delete_cookie(
        refresco.COOKIE,
        path=refresco.RUTA_COOKIE,
        httponly=True,
        secure=_cookie_segura(),
        samesite="lax",
    )


def exigir_x_requested_with(x_requested_with: str | None = Header(None)) -> None:
    """CSRF de los endpoints que usan la cookie del refresh (F07-P04, D-12): piden la cabecera X-Requested-With, que un
    formulario o un link de otro sitio no pueden mandar y que en un fetch de otro origen dispara un preflight que CORS
    no autoriza. Junto con SameSite=Lax, la cookie solo sirve desde la propia app. El resto de la API va con Bearer y
    no lo necesita."""
    if not x_requested_with:
        raise HTTPException(status_code=403, detail="Falta la cabecera X-Requested-With")


@router.post(
    "/refresh",
    response_model=RefrescoResponse,
    operation_id="auth_refrescar",
    dependencies=[Depends(exigir_x_requested_with)],
    responses={401: {"description": "Sin sesión o sesión inválida"}, 403: {"description": "Sin X-Requested-With"}},
)
async def refrescar(db: Session = Depends(get_db), refresh_token: str | None = Cookie(None)):
    """Canjea la cookie del refresh por un access token nuevo (F07-P03, D-12) y la rota: la cookie vieja deja de
    valer y reusarla cierra la sesión entera. Sin cookie, o con una que no sirve, 401 y la cookie se borra."""
    try:
        rotacion = refresco.rotar(db, refresh_token or "")
    except refresco.RefrescoInvalido as e:
        respuesta = JSONResponse(status_code=401, content={"detail": str(e)})
        _borrar_cookie_de_refresco(respuesta)
        return respuesta
    usuario = rotacion.usuario
    datos = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol}
    if rotacion.empresa_id:
        datos["empresa_id"] = str(rotacion.empresa_id)
    respuesta = JSONResponse(
        RefrescoResponse(
            access_token=create_access_token(datos), expires_in=settings.jwt_expire_minutes * 60
        ).model_dump()
    )
    poner_cookie_de_refresco(respuesta, rotacion.token)
    return respuesta


@router.post(
    "/logout",
    status_code=204,
    operation_id="auth_logout",
    dependencies=[Depends(exigir_x_requested_with)],
    responses={403: {"description": "Sin X-Requested-With"}},
)
async def logout(db: Session = Depends(get_db), refresh_token: str | None = Cookie(None)):
    """Cierra la sesión del navegador (F07-P03): revoca el refresh de la cookie (toda su sesión) y la borra. Sin
    cookie no hace nada. El access token que ya tenga el cliente vale hasta que venza."""
    if refresh_token:
        refresco.revocar(db, refresh_token)
    respuesta = Response(status_code=204)
    _borrar_cookie_de_refresco(respuesta)
    return respuesta


@router.post("/descargas", response_model=DescargaFirmada, operation_id="auth_firmar_descarga")
async def firmar_descarga(pedido: PedidoDescarga, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Una URL firmada de corta duración para bajar `ruta` sin Bearer, desde un <img> o un <a href> (F07-P06). La
    URL sirve solo para un GET de esa ruta exacta, como la persona que la pidió: firmar no da más acceso que el que
    ya tiene. `ruta` es un path de la API o de /storage, sin query ni fragmento."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token no proporcionado")
    sesion = decodificar(credentials.credentials)
    ruta = pedido.ruta
    if any(c in ruta for c in "?#\\") or "/../" in f"{ruta}/" or not ruta.startswith(descargas.rutas_firmables()):
        raise HTTPException(status_code=422, detail="Ruta no firmable: un path de la API o de /storage, sin query")
    return DescargaFirmada(
        url=f"{ruta}?firma={descargas.firmar(ruta, sesion)}", expira_en=int(descargas.VIGENCIA.total_seconds())
    )


@router.get("/me", response_model=SesionActual, operation_id="auth_sesion_actual")
async def get_current_user(
    db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """La sesión actual en una sola llamada (F07-P02): el usuario, la empresa activa del token, sus empresas, su
    ficha en esa empresa, los permisos efectivos (los de GET /permisos/mis-permisos) y el menú (el de GET /menus).
    Es lo que pide el shell de la SPA al arrancar. Sin empresa en el token, o con una a la que ya no pertenece,
    empresa, empleado, permisos y menú vienen vacíos."""
    user_id = get_user_id_from_token(credentials)

    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    sesion = SesionActual(
        id=str(usuario.id),
        email=usuario.email,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        dni=usuario.dni,
        telefono=usuario.telefono,
        avatar_url=usuario.avatar_url,
        rol=usuario.rol,
        activo=usuario.activo,
        empresas=[EmpresaResumen.model_validate(e) for e in EmpresaService.listar_empresas_usuario(db, user_id)],
    )
    empresa_id = decodificar(credentials.credentials).get("empresa_id")
    sesion.empresa = next((e for e in sesion.empresas if e.id == empresa_id), None)
    if sesion.empresa is None:
        return sesion

    empresa = uuid.UUID(sesion.empresa.id)
    empleado = _empleado_en_empresa(db, usuario, empresa)
    if empleado:
        sesion.empleado = EmpleadoEnEmpresa(
            id=str(empleado.id),
            foto=empleado.foto,
            foto_thumbnail=empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/")
            if empleado.foto
            else None,
            perfil_nombre=empleado.perfil_rel.nombre if empleado.perfil_rel else None,
        )
    sesion.permisos = GrupoService.obtener_permisos_usuario(db, str(usuario.id), empresa)
    sesion.menu = [ModuloMenu.model_validate(m) for m in menu_del_usuario(db, usuario, empresa)]
    return sesion


def _empleado_en_empresa(db: Session, usuario, empresa_id: uuid.UUID) -> Empleado | None:
    """La ficha de la persona en la empresa (cuenta y ficha se unen por DNI), si tiene."""
    if not usuario.dni:
        return None
    return (
        db.query(Empleado)
        .filter(Empleado.dni == usuario.dni, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
        .first()
    )


@router.put("/me")
async def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Actualiza el perfil del usuario actual."""
    user_id = get_user_id_from_token(credentials)

    datos = profile_data.model_dump(exclude_unset=True)

    if not datos:
        raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")

    try:
        usuario = UsuarioService.actualizar_usuario(db, user_id, datos)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        return {
            "id": str(usuario.id),
            "email": usuario.email,
            "nombre": usuario.nombre,
            "apellido": usuario.apellido,
            "dni": usuario.dni,
            "telefono": usuario.telefono,
            "avatar_url": usuario.avatar_url,
            "rol": usuario.rol,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/me/password")
async def change_my_password(
    password_data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Cambia la contraseña del usuario actual."""
    user_id = get_user_id_from_token(credentials)

    try:
        UsuarioService.cambiar_password(db, user_id, password_data.password_actual, password_data.password_nueva)
        return {"message": "Contraseña actualizada correctamente"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Sube la imagen de perfil del usuario actual."""
    user_id = get_user_id_from_token(credentials)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    try:
        if usuario.avatar_url:
            delete_profile_image(usuario.avatar_url)

        avatar_url = await save_profile_image(file)
        usuario.avatar_url = avatar_url
        db.commit()
        db.refresh(usuario)
        return {"avatar_url": avatar_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir imagen: {str(e)}")


# ─── 2FA (TOTP) ──────────────────────────────────────────────────────────────


@router.post("/me/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Genera secret TOTP + QR code. No activa 2FA aún."""
    import base64
    from io import BytesIO

    import pyotp
    import qrcode

    # el alta del 2FA obligatorio llega con el token intermedio "2fa_setup"; el "2fa" (2FA ya activo) no sirve acá
    user_id = get_user_id_from_token(credentials, ALTA_2FA)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Generar secret
    secret = pyotp.random_base32()
    usuario.totp_secret = secret
    db.commit()

    # Generar QR
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=usuario.email, issuer_name="Dicsys Core")

    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return TwoFactorSetupResponse(
        qr_base64=f"data:image/png;base64,{qr_base64}",
        secret_manual=secret,
    )


@router.post("/me/2fa/enable", response_model=TwoFactorEnableResponse)
async def enable_2fa(
    data: TwoFactorCodeRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Valida código TOTP y activa 2FA. Devuelve backup codes."""
    import pyotp

    user_id = get_user_id_from_token(credentials, ALTA_2FA)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario or not usuario.totp_secret:
        raise HTTPException(status_code=400, detail="Primero ejecutá /me/2fa/setup")

    totp = pyotp.TOTP(usuario.totp_secret)
    if not totp.verify(data.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Código incorrecto")

    # 8 códigos de respaldo: se muestran esta única vez y se guardan solo sus hashes
    backup_codes, hashes = secretos.generar()
    usuario.totp_enabled = True
    usuario.totp_backup_codes = hashes
    db.commit()

    return TwoFactorEnableResponse(backup_codes=backup_codes)


@router.delete("/me/2fa")
async def disable_2fa(
    data: TwoFactorCodeRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Desactiva 2FA. Requiere código TOTP para confirmar."""
    import pyotp

    user_id = get_user_id_from_token(credentials)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario or not usuario.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA no está activado")

    totp = pyotp.TOTP(usuario.totp_secret)
    if not totp.verify(data.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Código incorrecto")

    usuario.totp_enabled = False
    usuario.totp_secret = None
    usuario.totp_backup_codes = None
    db.commit()

    return {"message": "2FA desactivado"}


@router.post("/verify-2fa", operation_id="auth_verificar_2fa")
async def verify_2fa(
    data: TwoFactorVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(None),
    intentos: Intentos = Depends(Intentos),
):
    """Verifica código 2FA durante login. Devuelve JWT final."""
    return con_refresco(await _verificar_2fa(data, db, intentos), response, db, refresh_token)


async def _verificar_2fa(data: TwoFactorVerifyRequest, db: Session, intentos: Intentos):
    import pyotp

    # Decodificar temp_token: solo el intermedio del login ("2fa") o del alta obligatoria ("2fa_setup")
    payload = decodificar(data.temp_token, ("2fa", "2fa_setup"), detalle="Token expirado o inválido. Ingresá de nuevo.")
    if payload.get("purpose") not in ("2fa", "2fa_setup"):
        raise HTTPException(status_code=401, detail="Token inválido")
    user_id = payload.get("user_id")

    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario or not usuario.totp_enabled:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    # Límite de intentos (F07-P07): los códigos incorrectos cuentan por cuenta y por IP
    intentos.frenar(codigo=user_id)

    # Verificar código TOTP
    totp = pyotp.TOTP(usuario.totp_secret)
    code_valid = totp.verify(data.code, valid_window=1)

    # Si no es TOTP válido, probar los códigos de respaldo (por hash; cada uno sirve una sola vez)
    if not code_valid:
        restantes = secretos.consumir(usuario.totp_backup_codes, data.code)
        if restantes is not None:
            usuario.totp_backup_codes = restantes
            code_valid = True

    if not code_valid:
        intentos.contar(codigo=user_id)
        raise HTTPException(status_code=401, detail="Código incorrecto")
    intentos.olvidar(codigo=user_id)

    # Código OK → generar JWT final (mismo flujo que login normal)
    UsuarioService.actualizar_ultimo_login(db, str(usuario.id))
    db.commit()

    empresas = EmpresaService.listar_empresas_usuario(db, str(usuario.id))
    if len(empresas) == 0:
        raise HTTPException(status_code=403, detail="No tenés empresas asignadas.")

    empleado_id = None
    empleado_foto = None
    empleado_foto_thumbnail = None
    empleado_perfil_nombre = None
    if usuario.dni and empresas:
        empleado = (
            db.query(Empleado)
            .filter(Empleado.dni == usuario.dni, Empleado.empresa_id == empresas[0].id, Empleado.deleted_at.is_(None))
            .first()
        )
        if empleado:
            empleado_id = str(empleado.id)
            empleado_foto = empleado.foto
            empleado_foto_thumbnail = (
                empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if empleado.foto else None
            )
            if empleado.perfil_rel:
                empleado_perfil_nombre = empleado.perfil_rel.nombre

    user_data = {
        "id": str(usuario.id),
        "email": usuario.email,
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "dni": usuario.dni,
        "rol": usuario.rol,
        "avatar_url": usuario.avatar_url,
        "empleado_id": empleado_id,
        "empleado_foto": empleado_foto,
        "empleado_foto_thumbnail": empleado_foto_thumbnail,
        "empleado_perfil_nombre": empleado_perfil_nombre,
    }

    token_data = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol}

    if len(empresas) == 1:
        token_data["empresa_id"] = str(empresas[0].id)
        access_token = create_access_token(data=token_data)
        return TokenResponse(
            access_token=access_token,
            user=user_data,
            empresas=[EmpresaResumen.model_validate(empresas[0])],
            requiere_seleccion_empresa=False,
        )
    else:
        access_token = create_access_token(data=token_data, expires_delta=timedelta(minutes=5))
        return TokenResponse(
            access_token=access_token,
            user=user_data,
            empresas=[EmpresaResumen.model_validate(e) for e in empresas],
            requiere_seleccion_empresa=True,
        )


# ─── Mi Perfil (usuario + empleado vinculado) ─────────────────────────────────


@router.get("/me/perfil")
async def get_mi_perfil(db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Devuelve datos del usuario + empleado vinculado por DNI. Solo JWT."""
    from backend.modules.nomina.models import Empleado
    from backend.modules.nomina.schemas import EmpleadoResponse

    user_id = get_user_id_from_token(credentials)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Extraer empresa_id del token
    empresa_id = decodificar(credentials.credentials).get("empresa_id")

    empleado_data = None
    if usuario.dni and empresa_id:
        import uuid as uuid_mod

        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.dni == usuario.dni,
                Empleado.empresa_id == uuid_mod.UUID(empresa_id),
                Empleado.deleted_at.is_(None),
            )
            .first()
        )
        if empleado:
            empleado_data = EmpleadoResponse.from_model(empleado).model_dump()

    return {
        "id": str(usuario.id),
        "email": usuario.email,
        "email_secundario": usuario.email_secundario,  # de la cuenta; el perfil lo muestra (F22)
        "nombre": usuario.nombre,
        "apellido": usuario.apellido,
        "dni": usuario.dni,
        "telefono": usuario.telefono,
        "avatar_url": usuario.avatar_url,
        "rol": usuario.rol,
        "totp_enabled": usuario.totp_enabled,
        "empleado": empleado_data,
    }


@router.put("/me/perfil")
async def update_mi_perfil(
    datos: MiPerfilUpdate, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Actualiza datos personales del empleado vinculado al usuario. Solo JWT."""
    from backend.modules.nomina.schemas import EmpleadoResponse
    from backend.modules.nomina.services import EmpleadoService

    user_id = get_user_id_from_token(credentials)
    usuario = UsuarioService.obtener_usuario(db, user_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not usuario.dni:
        raise HTTPException(status_code=400, detail="Tu usuario no tiene DNI cargado")

    empresa_id = decodificar(credentials.credentials).get("empresa_id")
    if not empresa_id:
        raise HTTPException(status_code=403, detail="No se ha seleccionado una empresa")

    import uuid as uuid_mod

    empleado = (
        db.query(Empleado)
        .filter(
            Empleado.dni == usuario.dni, Empleado.empresa_id == uuid_mod.UUID(empresa_id), Empleado.deleted_at.is_(None)
        )
        .first()
    )
    if not empleado:
        raise HTTPException(status_code=404, detail="No se encontró un empleado vinculado a tu DNI")

    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    try:
        empleado = EmpleadoService.actualizar(
            db, uuid_mod.UUID(empresa_id), str(empleado.id), datos_dict, usuario=usuario.email
        )
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        return EmpleadoResponse.from_model(empleado)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error en PUT /me/perfil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar perfil")


def create_reset_token(email: str) -> str:
    """Crea un token JWT para reset de contraseña (válido por 1 hora)."""
    return crear_token({"sub": email, "type": "reset"}, timedelta(hours=1))


def verify_reset_token(token: str) -> str:
    """Verifica un token de reset y retorna el email."""
    payload = decodificar(token, codigo=400)
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Token inválido")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Token inválido")
    return email


@router.post("/forgot-password")
async def forgot_password(
    data: ForgotPasswordRequest, db: Session = Depends(get_db), intentos: Intentos = Depends(Intentos)
):
    """
    Solicita recuperación de contraseña.
    Envía un email con el link de reset si el usuario existe.

    Límite de intentos (F07-P07): cada pedido cuenta, exista o no el email, por email y por IP.
    """
    correo = data.email.lower()
    intentos.frenar(correo=correo)
    intentos.contar(correo=correo)

    usuario = UsuarioService.obtener_usuario_para_ingreso(db, data.email)

    # Siempre retornamos éxito para no revelar si el email existe
    if not usuario:
        return {"message": "Si el correo existe, recibirás instrucciones para restablecer tu contraseña"}

    # Generar token de reset
    reset_token = create_reset_token(data.email)

    # Construir URL de reset (frontend)
    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"

    # Verificar configuración de email

    # Enviar email
    try:
        email_service.send(
            to=data.email,
            subject="Restablecer contraseña - " + settings.app_name,
            html=emails.restablecer_password(usuario.nombre, reset_url),
        )
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al enviar email de recuperación: {e}", exc_info=True)

    return {"message": "Si el correo existe, recibirás instrucciones para restablecer tu contraseña"}


@router.post("/reset-password")
async def reset_password(
    data: ResetPasswordRequest, db: Session = Depends(get_db), intentos: Intentos = Depends(Intentos)
):
    """Restablece la contraseña usando el token de recuperación. Un token inválido cuenta como fallo de la IP (F07-P07)."""
    intentos.frenar()
    try:
        email = verify_reset_token(data.token)
    except HTTPException:
        intentos.contar()
        raise

    # Buscar usuario
    usuario = UsuarioService.obtener_usuario_para_ingreso(db, email)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Actualizar contraseña directamente
    usuario.set_password(data.password)
    # Desactivar 2FA al resetear password
    if usuario.totp_enabled:
        usuario.totp_enabled = False
        usuario.totp_secret = None
        usuario.totp_backup_codes = None
    usuario.updated_at = utc_now()
    db.commit()

    return {"message": "Contraseña actualizada correctamente"}
