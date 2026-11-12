"""Routers del módulo Recruiting.

Montado en main.py con require_modulo('recruiting'); cada endpoint exige además el permiso de su ítem del menú
('recruiting.<codigo>'). Dashboard, Manager Dashboard (solo administradores) y Candidatos.
"""

import logging
import uuid
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.core.errores import responde
from backend.core.paginacion import MAXIMO, POR_PAGINA, paginar
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_admin, require_submodulo
from backend.modules.recruiting.manager_dashboard import ManagerDashboardService
from backend.modules.recruiting.schemas import (
    CandidatoCreate,
    CandidatoEliminado,
    CandidatoPagina,
    CandidatoResponse,
    CandidatoUpdate,
    CargaCVDuplicadoResponse,
    CargaCVResponse,
    CargaMasivaFallido,
    CargaMasivaResponse,
    CiudadResponse,
    ComparacionCV,
    LoteCargaMasivaResponse,
    ManagerDashboard,
    ManagerDashboardFiltros,
    NivelSeniorityResponse,
    PermisosCandidatos,
    ProvinciaResponse,
    RecruitingDashboard,
    SkillCatalogoResponse,
)
from backend.modules.recruiting.services import (
    MENSAJE_ERROR_INTERNO,
    CandidatoService,
    CatalogoCandidatosService,
    CVDuplicadoDistintoError,
    DashboardService,
)
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/recruiting", tags=["recruiting"], responses=responde(401, 403))
logger = logging.getLogger(__name__)


def _email_usuario(usuario: Usuario) -> Optional[str]:
    """Email de quien opera, para la auditoría (updated_by) de lo que guarda el servicio."""
    return getattr(usuario, "email", None)


@router.get(
    "/dashboard",
    response_model=RecruitingDashboard,
    operation_id="recruiting_dashboard",
    dependencies=[Depends(require_submodulo("recruiting", "dashboard"))],
)
async def obtener_dashboard(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Indicadores, avisos y resumen operativo del Dashboard de Recruiting, acotados a lo que ve el usuario en la
    empresa activa."""
    return DashboardService.obtener(db, empresa_id, current_user)


@router.get(
    "/manager-dashboard",
    response_model=ManagerDashboard,
    operation_id="recruiting_manager_dashboard",
    dependencies=[Depends(require_admin)],
)
async def obtener_manager_dashboard(
    fecha_desde: Optional[date] = Query(None),
    fecha_hasta: Optional[date] = Query(None),
    tipo: Literal["todos", "freelance", "consultora"] = Query("todos"),
    usuario_ids: List[uuid.UUID] = Query([]),
    oportunidad_id: Optional[uuid.UUID] = Query(None),
    dias_estancado: int = Query(7, ge=1, le=365),
    umbral_volumen: int = Query(10, ge=1, le=100000),
    umbral_tasa_avance: float = Query(20.0, ge=0, le=100),
    umbral_actividad: int = Query(1, ge=1, le=100000),
    umbral_demora_dias: float = Query(3.0, ge=0, le=365),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
):
    """Indicadores de desempeño de los usuarios EXTERNOS (Freelance y Consultoras) de la empresa activa. Solo
    administradores: cualquier otro usuario recibe 403."""
    filtros = ManagerDashboardFiltros(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo=tipo,
        usuario_ids=usuario_ids,
        oportunidad_id=oportunidad_id,
        dias_estancado=dias_estancado,
        umbral_volumen=umbral_volumen,
        umbral_tasa_avance=umbral_tasa_avance,
        umbral_actividad=umbral_actividad,
        umbral_demora_dias=umbral_demora_dias,
    )
    return ManagerDashboardService.obtener(db, empresa_id, filtros)


# ---------------------------------------------------------------------------
# Candidatos
# ---------------------------------------------------------------------------

acceso_candidatos = Depends(require_submodulo("recruiting", "candidatos"))


@router.get(
    "/candidatos/permisos",
    response_model=PermisosCandidatos,
    operation_id="recruiting_candidatos_permisos",
    dependencies=[acceso_candidatos],
)
async def permisos_candidatos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Qué acciones de Candidatos puede hacer el usuario: el grupo EXTERNOS no elimina candidatos ni carga CV desde el
    listado general (solo desde una búsqueda asignada)."""
    return CandidatoService.permisos(db, empresa_id, current_user)


@router.get(
    "/candidatos/perfiles-puesto",
    response_model=List[str],
    operation_id="recruiting_candidatos_perfiles_puesto",
    dependencies=[acceso_candidatos],
)
async def listar_perfiles_puesto_candidatos(db: Session = Depends(get_db)):
    """Perfiles de puesto activos del catálogo; opciones del filtro del listado y del combo «Puesto» del formulario."""
    return CandidatoService.listar_perfiles_puesto(db)


@router.get(
    "/candidatos",
    response_model=CandidatoPagina,
    operation_id="recruiting_candidatos_listar",
    dependencies=[acceso_candidatos],
)
async def listar_candidatos(
    busqueda: Optional[str] = Query(None, description="Nombre, apellido, email, DNI, código o ubicación"),
    estado: Optional[str] = Query(None),
    fuente: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    ubicacion: Optional[str] = Query(None),
    puesto: Optional[str] = Query(None, max_length=255, description="Perfil de puesto (headline) exacto"),
    categorias: Optional[List[str]] = Query(None, description="Categorías de skills; al menos una skill de alguna"),
    skills: Optional[List[str]] = Query(None, description="Skills específicas; el candidato debe tener todas"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA, ge=1, le=MAXIMO),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Candidatos de la empresa activa que el usuario puede ver, con filtros y paginación."""
    consulta = CandidatoService.consulta(
        db,
        empresa_id,
        busqueda=busqueda,
        estado=estado,
        fuente=fuente,
        seniority=seniority,
        ubicacion=ubicacion,
        puesto=puesto,
        categorias=categorias,
        skills=skills,
        current_user=current_user,
    )
    items, datos = paginar(consulta, pagina, por_pagina)
    return CandidatoPagina(items=[CandidatoResponse.from_model(c) for c in items], **datos)


@router.post(
    "/candidatos",
    response_model=CandidatoResponse,
    status_code=201,
    operation_id="recruiting_candidatos_crear",
    responses=responde(400, 422),
    dependencies=[acceso_candidatos],
)
async def crear_candidato(
    datos: CandidatoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Registra un candidato en el Banco de Talentos. Si el email ya existe en la empresa se actualiza esa ficha (salvo
    que la haya cargado otro usuario: 400)."""
    candidato = CandidatoService.create(
        db=db, empresa_id=empresa_id, datos=datos, usuario=_email_usuario(current_user), current_user=current_user
    )
    return CandidatoResponse.from_model(candidato)


@router.get(
    "/candidatos/{candidato_id}",
    response_model=CandidatoResponse,
    operation_id="recruiting_candidatos_obtener",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
async def obtener_candidato(
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """La ficha de un candidato; 403 si no es de los que el usuario puede ver."""
    candidato = CandidatoService.get_ficha(db, empresa_id, str(candidato_id), current_user=current_user)
    return CandidatoResponse.from_model(candidato)


@router.put(
    "/candidatos/{candidato_id}",
    response_model=CandidatoResponse,
    operation_id="recruiting_candidatos_actualizar",
    responses=responde(400, 404),
    dependencies=[acceso_candidatos],
)
async def actualizar_candidato(
    candidato_id: uuid.UUID,
    datos: CandidatoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza la ficha de un candidato."""
    candidato = CandidatoService.update(
        db=db,
        empresa_id=empresa_id,
        id=str(candidato_id),
        datos=datos,
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )
    return CandidatoResponse.from_model(candidato)


@router.delete(
    "/candidatos/{candidato_id}",
    response_model=CandidatoEliminado,
    operation_id="recruiting_candidatos_eliminar",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
async def eliminar_candidato(
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Da de baja (baja lógica) a un candidato. El grupo EXTERNOS no puede."""
    CandidatoService.eliminar(db, empresa_id, str(candidato_id), current_user)
    return CandidatoEliminado(mensaje="Candidato dado de baja correctamente")


@router.post(
    "/candidatos/{candidato_id}/cv",
    response_model=CandidatoResponse,
    operation_id="recruiting_candidatos_subir_cv",
    responses=responde(400, 404),
    dependencies=[acceso_candidatos],
)
async def subir_cv_candidato(
    candidato_id: uuid.UUID,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Sube el CV (PDF, DOC o DOCX, hasta 2 MB) y lo asocia al candidato."""
    CandidatoService.get_by_id(db, empresa_id, str(candidato_id), current_user=current_user)
    candidato = await CandidatoService.subir_cv(
        db=db, empresa_id=empresa_id, id=str(candidato_id), archivo=archivo, usuario=_email_usuario(current_user)
    )
    return CandidatoResponse.from_model(candidato)


async def _cargar_cv_general(
    archivo: UploadFile, db: Session, empresa_id: uuid.UUID, current_user: Usuario, actualizar: bool
):
    CandidatoService.exigir_carga_general(db, empresa_id, current_user)
    try:
        candidato = await CandidatoService.crear_desde_cv(
            db=db,
            empresa_id=empresa_id,
            archivo=archivo,
            usuario=_email_usuario(current_user),
            current_user=current_user,
            modo_duplicado="actualizar" if actualizar else "comparar",
            validar_permiso_existente=True,
        )
    except CVDuplicadoDistintoError as e:
        contenido = CargaCVDuplicadoResponse(
            error=e.detail, actual=ComparacionCV(**e.actual), nuevo=ComparacionCV(**e.nuevo)
        )
        return JSONResponse(status_code=409, content=contenido.model_dump(mode="json"))
    except HTTPException:
        raise
    except Exception:
        logger.error("Error no controlado al procesar un CV", exc_info=True)
        raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
    return CargaCVResponse(candidato=CandidatoResponse.from_model(candidato))


@router.post(
    "/candidatos/cargar-cv",
    response_model=CargaCVResponse,
    status_code=201,
    operation_id="recruiting_candidatos_cargar_cv",
    responses={**responde(403, 422), 409: {"model": CargaCVDuplicadoResponse}},
    dependencies=[acceso_candidatos],
)
async def cargar_candidato_desde_cv(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Carga individual de un CV: extrae los datos y crea el candidato. Si el email ya existe con un CV distinto no
    guarda nada y responde 409 con los datos de ambos CVs para compararlos."""
    return await _cargar_cv_general(archivo, db, empresa_id, current_user, actualizar=False)


@router.post(
    "/candidatos/actualizar-cv",
    response_model=CargaCVResponse,
    status_code=201,
    operation_id="recruiting_candidatos_actualizar_cv",
    responses=responde(403, 422),
    dependencies=[acceso_candidatos],
)
async def actualizar_candidato_desde_cv(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza el candidato existente (mismo email) con el CV nuevo y los datos que se extraen de él."""
    return await _cargar_cv_general(archivo, db, empresa_id, current_user, actualizar=True)


@router.post(
    "/candidatos/cargar-cv-masivo/iniciar",
    response_model=LoteCargaMasivaResponse,
    status_code=202,
    operation_id="recruiting_candidatos_carga_masiva_iniciar",
    responses=responde(400, 403),
    dependencies=[acceso_candidatos],
)
async def iniciar_carga_masiva_cv(
    archivos: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Inicia en segundo plano la carga masiva (.zip, .rar o hasta 100 CVs sueltos) y devuelve el lote para seguir su
    avance. El grupo EXTERNOS no puede."""
    CandidatoService.exigir_carga_masiva(db, empresa_id, current_user)
    return await CandidatoService.iniciar_carga_masiva_en_segundo_plano(
        empresa_id=empresa_id,
        archivos=archivos or [],
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )


def _carga_masiva_fallida(motivo: str) -> CargaMasivaResponse:
    """El lote no se pudo procesar: 200 con `ok` en False y el motivo (así lo consume la pantalla desde el original)."""
    fallido = [CargaMasivaFallido(archivo="—", motivo=motivo)]
    return CargaMasivaResponse(ok=False, errores=fallido, fallidos=fallido)


@router.post(
    "/candidatos/cargar-cv-masivo",
    response_model=CargaMasivaResponse,
    operation_id="recruiting_candidatos_carga_masiva",
    dependencies=[acceso_candidatos],
)
async def cargar_candidatos_masivo_cv(
    archivo: Optional[UploadFile] = File(None),
    archivos: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Carga masiva sincrónica: comprimidos (.zip o .rar) y/o CV sueltos (.pdf, .doc, .docx, hasta 100), con el resumen
    por categoría y el resultado de cada archivo. Siempre responde 200 (ver CargaMasivaResponse). El grupo EXTERNOS no
    puede (403)."""
    CandidatoService.exigir_carga_masiva(db, empresa_id, current_user)
    try:
        resultado = await CandidatoService.procesar_carga_masiva_zip_rar(
            db=db,
            empresa_id=empresa_id,
            archivo=archivo,
            archivos=archivos,
            usuario=_email_usuario(current_user),
            current_user=current_user,
        )
    except HTTPException as e:
        logger.warning(f"Carga masiva rechazada: {e.detail}")
        return _carga_masiva_fallida(str(e.detail))
    except Exception:
        logger.error("Error no controlado en la carga masiva", exc_info=True)
        return _carga_masiva_fallida(MENSAJE_ERROR_INTERNO)

    creados = []
    for candidato in resultado.get("candidatos_creados", []):
        try:
            creados.append(CandidatoResponse.from_model(candidato))
        except Exception as e:
            logger.warning(f"Error al serializar un candidato de la carga masiva: {e}")
    procesados = int(resultado.get("procesados_exitosamente", 0))
    total = int(resultado.get("total_archivos_encontrados", 0))
    fallidos = [CargaMasivaFallido(**f) for f in resultado.get("fallidos", [])]
    return CargaMasivaResponse(
        ok=True,
        lote_id=resultado.get("lote_id"),
        resumen=resultado.get("resumen"),
        resultados=resultado.get("resultados", []),
        procesados=procesados,
        creados=len(creados),
        total_encontrados=total,
        errores=fallidos,
        total_archivos_encontrados=total,
        procesados_exitosamente=procesados,
        fallidos=fallidos,
        candidatos_creados=creados,
    )


@router.get(
    "/candidatos/cargar-cv-masivo/{lote_id}/estado",
    response_model=LoteCargaMasivaResponse,
    operation_id="recruiting_candidatos_carga_masiva_estado",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
def estado_carga_masiva_cv(
    lote_id: str,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Avance real del lote (procesados sobre total) y, al terminar, su reporte final."""
    return CandidatoService.obtener_estado_carga_masiva(lote_id, empresa_id, current_user)


@router.post(
    "/candidatos/cargar-cv-masivo/{lote_id}/cancelar",
    response_model=LoteCargaMasivaResponse,
    operation_id="recruiting_candidatos_carga_masiva_cancelar",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
def cancelar_carga_masiva_cv(
    lote_id: str,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Detiene el lote antes del próximo CV; los ya procesados quedan guardados."""
    return CandidatoService.cancelar_carga_masiva(lote_id, empresa_id, current_user)


# Catálogos de solo lectura que llenan los combos del formulario y los filtros del listado (su ABM es de Parámetros)


@router.get(
    "/skills",
    response_model=List[SkillCatalogoResponse],
    operation_id="recruiting_skills_listar",
    dependencies=[acceso_candidatos],
)
async def listar_skills(db: Session = Depends(get_db)):
    """Skills activas del catálogo, por nombre."""
    return CatalogoCandidatosService.skills(db)


@router.get(
    "/habilidades",
    response_model=List[SkillCatalogoResponse],
    operation_id="recruiting_habilidades_listar",
    dependencies=[acceso_candidatos],
)
async def listar_habilidades(db: Session = Depends(get_db)):
    """Habilidades (roles y competencias) activas del catálogo, por nombre."""
    return CatalogoCandidatosService.habilidades(db)


@router.get(
    "/niveles-seniority",
    response_model=List[NivelSeniorityResponse],
    operation_id="recruiting_niveles_seniority_listar",
    dependencies=[acceso_candidatos],
)
async def listar_niveles_seniority(db: Session = Depends(get_db)):
    """Niveles de seniority del catálogo."""
    return CatalogoCandidatosService.niveles_seniority(db)


@router.get(
    "/provincias",
    response_model=List[ProvinciaResponse],
    operation_id="recruiting_provincias_listar",
    dependencies=[acceso_candidatos],
)
async def listar_provincias(db: Session = Depends(get_db)):
    """Provincias del catálogo, con la cantidad de ciudades de cada una."""
    return CatalogoCandidatosService.provincias(db)


@router.get(
    "/ciudades",
    response_model=List[CiudadResponse],
    operation_id="recruiting_ciudades_listar",
    dependencies=[acceso_candidatos],
)
async def listar_ciudades(provincia_id: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db)):
    """Ciudades del catálogo, opcionalmente solo las de una provincia."""
    return CatalogoCandidatosService.ciudades(db, provincia_id)
