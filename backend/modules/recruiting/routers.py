"""Routers del módulo Recruiting.

Montado en main.py con require_modulo('recruiting'); cada endpoint exige además el permiso de su ítem del menú
('recruiting.<codigo>'). Dashboard, Manager Dashboard (solo administradores), Candidatos y Búsquedas (oportunidades).
"""

import logging
import uuid
from datetime import date
from urllib.parse import quote
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from backend.core.errores import responde
from backend.core.paginacion import MAXIMO, POR_PAGINA, paginar
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_admin, require_submodulo
from backend.modules.recruiting.manager_dashboard import ManagerDashboardService
from backend.modules.recruiting.pipeline_services import (
    AltaEnBusquedaService,
    CandidatoDuplicadoService,
    MotivoDescarteService,
    PipelineService,
    PostulacionService,
)
from backend.modules.recruiting.schemas import (
    AsignacionCandidatoResponse,
    AsignarCandidatoRequest,
    AsignarExternoRequest,
    AltaEnBusquedaResponse,
    AsignarReclutadorRequest,
    BusquedaElegible,
    CambiarEtapaRequest,
    CambiarEtapaResponse,
    CandidatoCompatible,
    CandidatoCreate,
    CandidatoEliminado,
    CandidatoEnBusqueda,
    CandidatoPagina,
    CandidatoResponse,
    CandidatoUpdate,
    CargaCVDuplicadoResponse,
    CargaCVResponse,
    CargaMasivaFallido,
    CargaMasivaResponse,
    CasoDuplicado,
    CasoDuplicadoDetalle,
    CasoDuplicadoLista,
    CiudadResponse,
    ComparacionCV,
    ConfigSmartMatching,
    ContadoresEtapas,
    DesvinculacionCandidatoResponse,
    EtapaArchivoResponse,
    ExternoDisponibleResponse,
    HistorialPipelineItem,
    LoteCargaMasivaResponse,
    ManagerDashboard,
    ManagerDashboardFiltros,
    MotivoDescarteResponse,
    NivelSeniorityResponse,
    OportunidadCreate,
    OportunidadPagina,
    OportunidadResponse,
    OportunidadUpdate,
    PermisosBusquedas,
    PermisosCandidatos,
    PermisosPipeline,
    PersonaCatalogoResponse,
    PipelineColumnaCandidato,
    PipelineDeCandidato,
    PipelineResumen,
    PostulacionResponse,
    ProvinciaResponse,
    RecruitingDashboard,
    RechazoPostulacionRequest,
    ResolucionCasoDuplicado,
    ResolverCasoDuplicadoRequest,
    SkillCatalogoResponse,
    TransicionEstadoResponse,
)
from backend.modules.recruiting.services import (
    MENSAJE_ERROR_INTERNO,
    CandidatosDeBusquedaService,
    CandidatoService,
    CatalogoCandidatosService,
    CVDuplicadoDistintoError,
    DashboardService,
    OportunidadService,
    usuario_es_grupo_externos,
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
    con_pipeline = PipelineService.candidatos_con_pipeline(db, empresa_id, [c.id for c in items], current_user)
    return CandidatoPagina(
        items=[
            CandidatoResponse.from_model(c).model_copy(update={"tiene_pipeline": str(c.id) in con_pipeline})
            for c in items
        ],
        **datos,
    )


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


# ---------------------------------------------------------------------------
# Búsquedas (oportunidades)
# ---------------------------------------------------------------------------

acceso_busquedas = Depends(require_submodulo("recruiting", "oportunidades"))


@router.get(
    "/oportunidades/permisos",
    response_model=PermisosBusquedas,
    operation_id="recruiting_oportunidades_permisos",
    dependencies=[acceso_busquedas],
)
async def permisos_busquedas(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Qué acciones de Búsquedas puede hacer el usuario (el grupo EXTERNOS tiene menos)."""
    return OportunidadService.permisos(db, empresa_id, current_user)


@router.get(
    "/oportunidades",
    response_model=OportunidadPagina,
    operation_id="recruiting_oportunidades_listar",
    dependencies=[acceso_busquedas],
)
async def listar_oportunidades(
    busqueda: Optional[str] = Query(None, description="ID, título, cliente, reclutador o líder"),
    estado: Optional[str] = Query(None, description="Abierta, Pre-ingreso, Suspendida, Ganada, Cancelada o todos"),
    cliente: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None, description="Efectiva, Potencial o Todas"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA, ge=1, le=MAXIMO),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Búsquedas de la empresa activa que el usuario puede ver (el grupo EXTERNOS, solo las que tiene asignadas), con
    filtros y paginación."""
    consulta = OportunidadService.consulta(
        db, empresa_id, busqueda=busqueda, estado=estado, cliente=cliente, tipo=tipo, current_user=current_user
    )
    items, datos = paginar(consulta, pagina, por_pagina)
    return OportunidadPagina(items=[OportunidadResponse.from_model(o) for o in items], **datos)


@router.post(
    "/oportunidades",
    response_model=OportunidadResponse,
    status_code=201,
    operation_id="recruiting_oportunidades_crear",
    responses=responde(400, 422),
    dependencies=[acceso_busquedas],
)
async def crear_oportunidad(
    datos: OportunidadCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea una búsqueda. 403 para el grupo EXTERNOS; 400 si el estado o el puesto no son válidos o si ya existe una con
    ese título para el cliente."""
    solicitud = OportunidadService.create(
        db, empresa_id, datos, usuario=_email_usuario(current_user), current_user=current_user
    )
    return OportunidadResponse.from_model(solicitud)


@router.get(
    "/externos-disponibles",
    response_model=List[ExternoDisponibleResponse],
    operation_id="recruiting_oportunidades_externos_disponibles",
    dependencies=[acceso_busquedas],
)
async def listar_externos_disponibles(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Usuarios habilitados del grupo EXTERNOS que se pueden asignar a una búsqueda (admin y grupos de Recruiting)."""
    return OportunidadService.listar_externos_disponibles(db, empresa_id, current_user)


@router.get(
    "/lideres",
    response_model=List[PersonaCatalogoResponse],
    operation_id="recruiting_lideres_listar",
    dependencies=[acceso_busquedas],
)
async def listar_lideres(db: Session = Depends(get_db)):
    """Líderes activos del catálogo, para el combo del formulario de una búsqueda."""
    return [PersonaCatalogoResponse.model_validate(p) for p in OportunidadService.lideres(db)]


@router.get(
    "/reclutadores",
    response_model=List[PersonaCatalogoResponse],
    operation_id="recruiting_reclutadores_listar",
    dependencies=[acceso_busquedas],
)
async def listar_reclutadores(db: Session = Depends(get_db)):
    """Reclutadores activos del catálogo, para el combo del formulario de una búsqueda y para asignarla."""
    return [PersonaCatalogoResponse.model_validate(p) for p in OportunidadService.reclutadores(db)]


@router.get(
    "/config",
    response_model=ConfigSmartMatching,
    operation_id="recruiting_config_obtener",
    dependencies=[acceso_busquedas],
)
async def obtener_config(db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa)):
    """Umbral mínimo de Smart Matching de la empresa activa (50 si no lo configuró). Su edición es de Parámetros."""
    return ConfigSmartMatching(match_minimo_porcentaje=OportunidadService.match_minimo(db, empresa_id))


@router.get(
    "/oportunidades/{oportunidad_id}",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_obtener",
    responses=responde(404),
    dependencies=[acceso_busquedas],
)
async def obtener_oportunidad(
    oportunidad_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Una búsqueda de la empresa activa; 404 si es de otra empresa y 403 si el usuario EXTERNOS no la tiene asignada."""
    return OportunidadResponse.from_model(
        OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
    )


@router.put(
    "/oportunidades/{oportunidad_id}",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_actualizar",
    responses=responde(400, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def actualizar_oportunidad(
    oportunidad_id: uuid.UUID,
    datos: OportunidadUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Edita una búsqueda (409 si está Ganada). Cancelarla (estado Cancelada) no está permitido al grupo EXTERNOS."""
    solicitud = OportunidadService.update(
        db, empresa_id, oportunidad_id, datos, usuario=_email_usuario(current_user), current_user=current_user
    )
    return OportunidadResponse.from_model(solicitud)


@router.post(
    "/oportunidades/{oportunidad_id}/asignar",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_tomar",
    responses=responde(400, 404, 409),
    dependencies=[acceso_busquedas],
)
async def tomar_oportunidad(
    oportunidad_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """El reclutador toma la búsqueda: queda como responsable y se registra la fecha de asignación."""
    solicitud = OportunidadService.tomar_asignacion(
        db, empresa_id, oportunidad_id, usuario=_email_usuario(current_user), current_user=current_user
    )
    return OportunidadResponse.from_model(solicitud)


@router.post(
    "/oportunidades/{oportunidad_id}/desasignar",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_desasignar",
    responses=responde(404, 409),
    dependencies=[acceso_busquedas],
)
async def desasignar_oportunidad(
    oportunidad_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Libera la búsqueda para que otro reclutador pueda tomarla (un administrador o el reclutador asignado)."""
    solicitud = OportunidadService.desasignar(
        db, empresa_id, oportunidad_id, usuario=_email_usuario(current_user), current_user=current_user
    )
    return OportunidadResponse.from_model(solicitud)


@router.post(
    "/oportunidades/{oportunidad_id}/reclutador",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_asignar_reclutador",
    responses=responde(400, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def asignar_reclutador_oportunidad(
    oportunidad_id: uuid.UUID,
    datos: AsignarReclutadorRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Asigna o reasigna el reclutador con una persona activa del catálogo de Reclutadores."""
    solicitud = OportunidadService.asignar_reclutador(
        db,
        empresa_id,
        oportunidad_id,
        datos.recruiter_nombre,
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )
    return OportunidadResponse.from_model(solicitud)


@router.put(
    "/oportunidades/{oportunidad_id}/externo",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_asignar_externo",
    responses=responde(400, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def asignar_externo_oportunidad(
    oportunidad_id: uuid.UUID,
    datos: AsignarExternoRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Asigna o cambia el usuario externo (grupo EXTERNOS) de la búsqueda."""
    solicitud = OportunidadService.asignar_externo(
        db,
        empresa_id,
        oportunidad_id,
        datos.externo_id,
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )
    return OportunidadResponse.from_model(solicitud)


@router.delete(
    "/oportunidades/{oportunidad_id}/externo",
    response_model=OportunidadResponse,
    operation_id="recruiting_oportunidades_quitar_externo",
    responses=responde(404, 409),
    dependencies=[acceso_busquedas],
)
async def quitar_externo_oportunidad(
    oportunidad_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Quita la asignación del usuario externo; la búsqueda y sus candidatos no se modifican."""
    solicitud = OportunidadService.quitar_externo(
        db, empresa_id, oportunidad_id, usuario=_email_usuario(current_user), current_user=current_user
    )
    return OportunidadResponse.from_model(solicitud)


@router.get(
    "/oportunidades/{oportunidad_id}/candidatos",
    response_model=List[CandidatoEnBusqueda],
    operation_id="recruiting_oportunidades_candidatos_listar",
    responses=responde(404),
    dependencies=[acceso_busquedas],
)
async def listar_candidatos_oportunidad(
    oportunidad_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Candidatos vigentes de la búsqueda con su etapa y estado (anónimos los que un usuario EXTERNOS no presentó)."""
    filas = CandidatosDeBusquedaService.listar(db, empresa_id, oportunidad_id, current_user)
    return [CandidatoEnBusqueda(**fila) for fila in filas]


@router.get(
    "/oportunidades/{oportunidad_id}/candidatos-compatibles",
    response_model=List[CandidatoCompatible],
    operation_id="recruiting_oportunidades_candidatos_compatibles",
    responses=responde(404),
    dependencies=[acceso_busquedas],
)
async def listar_candidatos_compatibles(
    oportunidad_id: uuid.UUID,
    q: Optional[str] = Query(None, description="Nombre, apellido, código o email"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Smart Matching: candidatos que comparten skills o habilidades con la búsqueda y todavía no están asignados.
    403 para el grupo EXTERNOS."""
    filas = CandidatosDeBusquedaService.compatibles(
        db, empresa_id, oportunidad_id, busqueda=q, current_user=current_user
    )
    return [CandidatoCompatible(**fila) for fila in filas]


@router.post(
    "/oportunidades/{oportunidad_id}/candidatos",
    response_model=AsignacionCandidatoResponse,
    status_code=201,
    operation_id="recruiting_oportunidades_candidatos_asignar",
    responses=responde(400, 404, 422),
    dependencies=[acceso_busquedas],
)
async def asignar_candidato_oportunidad(
    oportunidad_id: uuid.UUID,
    datos: AsignarCandidatoRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Suma un candidato a una búsqueda Abierta. 400 si ya está asignado o la búsqueda no está Abierta; 403 para el grupo
    EXTERNOS."""
    postulacion = CandidatosDeBusquedaService.asignar(
        db, empresa_id, oportunidad_id, datos, usuario=_email_usuario(current_user), current_user=current_user
    )
    return AsignacionCandidatoResponse(
        id=str(postulacion.id),
        candidato_id=str(postulacion.candidato_id),
        solicitud_id=str(postulacion.solicitud_id),
        etapa=postulacion.etapa,
        estado=postulacion.estado,
        fecha_asignacion=postulacion.fecha_asignacion,
    )


@router.delete(
    "/oportunidades/{oportunidad_id}/candidatos/{candidato_id}",
    response_model=DesvinculacionCandidatoResponse,
    operation_id="recruiting_oportunidades_candidatos_desvincular",
    responses=responde(404, 409),
    dependencies=[acceso_busquedas],
)
async def desvincular_candidato_oportunidad(
    oportunidad_id: uuid.UUID,
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Quita al candidato de la búsqueda sin eliminarlo del Banco de Talentos (409 si la búsqueda está Ganada)."""
    resultado = CandidatosDeBusquedaService.desvincular(
        db,
        empresa_id,
        oportunidad_id,
        candidato_id,
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )
    return DesvinculacionCandidatoResponse(**resultado)


# ---------------------------------------------------------------------------
# Pipeline (ítem «gestion_busquedas»)
# ---------------------------------------------------------------------------


def _acceso_a_alguno(*items: str):
    """Dependencia: alcanza con tener el permiso de cualquiera de los ítems de Recruiting dados (para lo que usan varias
    pantallas: la ficha del pipeline de un candidato se abre desde Candidatos y desde Pipeline)."""
    verificadores = [require_submodulo("recruiting", item) for item in items]

    async def _verificar(
        current_user: Usuario = Depends(get_current_user),
        db: Session = Depends(get_db),
        empresa_id: uuid.UUID = Depends(get_empresa_activa),
    ) -> Usuario:
        error: Optional[HTTPException] = None
        for verificar in verificadores:
            try:
                return await verificar(current_user, db, empresa_id)
            except HTTPException as e:
                error = e
        raise error

    return Depends(_verificar)


acceso_pipeline = Depends(require_submodulo("recruiting", "gestion_busquedas"))
acceso_pipeline_o_candidatos = _acceso_a_alguno("gestion_busquedas", "candidatos")
acceso_cualquier_pantalla = _acceso_a_alguno("gestion_busquedas", "candidatos", "oportunidades", "dashboard")


@router.get(
    "/pipeline-permisos",
    response_model=PermisosPipeline,
    operation_id="recruiting_pipeline_permisos",
    dependencies=[acceso_cualquier_pantalla],
)
async def permisos_pipeline(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Qué acciones puede hacer el usuario en Pipeline, Candidatos y Búsquedas (el grupo EXTERNOS tiene menos)."""
    return PipelineService.permisos(db, empresa_id, current_user)


@router.get(
    "/pipeline-resumen",
    response_model=PipelineResumen,
    operation_id="recruiting_pipeline_resumen",
    responses=responde(400),
    dependencies=[acceso_pipeline],
)
async def resumen_pipeline_global(
    estado: Optional[str] = Query(
        None, description="Estado de la búsqueda (Abierta, Pre-ingreso, Suspendida, Ganada, Cancelada, Todos)"
    ),
    alcance_candidatos: Optional[str] = Query(None, description="todos | propios (los que cargó el usuario)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Vista global del Pipeline: candidatos por búsqueda en Screening, Presentados, Entrevistas, Oferta y Contratados."""
    return PipelineService.resumen_global(db, empresa_id, estado, current_user, alcance_candidatos)


@router.get(
    "/oportunidades/{oportunidad_id}/pipeline-candidatos",
    response_model=List[CandidatoEnBusqueda],
    operation_id="recruiting_pipeline_candidatos",
    responses=responde(400, 404),
    dependencies=[acceso_pipeline],
)
async def listar_pipeline_candidatos(
    oportunidad_id: uuid.UUID,
    etapa: Optional[str] = Query(None, description="Etapa (Todas, Candidato, Screening, ...)"),
    alcance_candidatos: Optional[str] = Query(None, description="todos | propios (los que cargó el usuario)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Candidatos del pipeline de la búsqueda, con su etapa y estado (anónimos los que un EXTERNOS no presentó)."""
    PipelineService.normalizar_alcance(alcance_candidatos)
    filas = CandidatosDeBusquedaService.listar(
        db, empresa_id, oportunidad_id, current_user, etapa=etapa, alcance=alcance_candidatos
    )
    return [CandidatoEnBusqueda(**fila) for fila in filas]


@router.get(
    "/oportunidades/{oportunidad_id}/pipeline-contadores",
    response_model=ContadoresEtapas,
    operation_id="recruiting_pipeline_contadores",
    responses=responde(400, 404),
    dependencies=[acceso_pipeline],
)
async def obtener_contadores_pipeline(
    oportunidad_id: uuid.UUID,
    alcance_candidatos: Optional[str] = Query(None, description="todos | propios (los que cargó el usuario)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Candidatos vigentes de la búsqueda en cada etapa."""
    return PipelineService.contadores(db, empresa_id, oportunidad_id, current_user, alcance_candidatos)


@router.get(
    "/oportunidades/{oportunidad_id}/pipeline-columna/{columna}",
    response_model=List[PipelineColumnaCandidato],
    operation_id="recruiting_pipeline_columna",
    responses=responde(400, 404),
    dependencies=[acceso_pipeline],
)
async def listar_candidatos_columna_pipeline(
    oportunidad_id: uuid.UUID,
    columna: Literal["screening", "submissions", "interview", "offer", "hire"],
    alcance_candidatos: Optional[str] = Query(None, description="todos | propios (los que cargó el usuario)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Candidatos de una búsqueda en una columna de la vista global."""
    filas = PipelineService.candidatos_por_columna(
        db, empresa_id, oportunidad_id, columna, current_user, alcance_candidatos
    )
    return [PipelineColumnaCandidato(**fila) for fila in filas]


@router.get(
    "/motivos-descarte",
    response_model=List[MotivoDescarteResponse],
    operation_id="recruiting_pipeline_motivos_descarte",
    dependencies=[acceso_pipeline],
)
async def listar_motivos_descarte(
    etapa: str = Query(..., min_length=1, description="Etapa actual del candidato"),
    db: Session = Depends(get_db),
):
    """Motivos de descarte disponibles para la etapa indicada, en su orden de presentación."""
    return [MotivoDescarteResponse(id=m.id, motivo=m.motivo) for m in MotivoDescarteService.listar(db, etapa)]


@router.put(
    "/oportunidades/{oportunidad_id}/candidatos/{candidato_id}/etapa",
    response_model=CambiarEtapaResponse,
    operation_id="recruiting_pipeline_cambiar_etapa",
    responses=responde(400, 404, 409),
    dependencies=[acceso_pipeline],
)
async def cambiar_etapa_pipeline(
    oportunidad_id: uuid.UUID,
    candidato_id: uuid.UUID,
    datos: CambiarEtapaRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Mueve de etapa, descarta o reingresa a un candidato respetando el flujo secuencial. 403 para el grupo EXTERNOS;
    409 si la búsqueda está Ganada."""
    registro = PipelineService.cambiar_etapa(
        db, empresa_id, oportunidad_id, candidato_id, datos, usuario=_email_usuario(current_user), current_user=current_user
    )
    return CambiarEtapaResponse(
        id=str(registro.id),
        etapa_actual=registro.etapa_actual,
        estado=registro.estado,
        motivo_descarte=registro.motivo_descarte,
        feedback_etapa=registro.feedback_etapa,
        pretension_salarial_bruta_ars=registro.pretension_salarial_bruta_ars,
    )


@router.get(
    "/oportunidades/{oportunidad_id}/candidatos/{candidato_id}/historial",
    response_model=List[HistorialPipelineItem],
    operation_id="recruiting_pipeline_historial",
    responses=responde(404),
    dependencies=[acceso_pipeline_o_candidatos],
)
async def historial_pipeline(
    oportunidad_id: uuid.UUID,
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Movimientos del candidato en la búsqueda, del más antiguo al más reciente."""
    filas = PipelineService.historial(db, empresa_id, oportunidad_id, candidato_id, current_user)
    return [HistorialPipelineItem(**fila) for fila in filas]


def _archivo_etapa_response(archivo) -> EtapaArchivoResponse:
    return EtapaArchivoResponse(
        id=str(archivo.id),
        busqueda_id=str(archivo.busqueda_id),
        candidato_id=str(archivo.candidato_id),
        etapa_id=archivo.etapa_id,
        estado=archivo.estado,
        nombre_archivo=archivo.nombre_archivo,
        tipo_archivo=archivo.tipo_archivo,
        tamano=archivo.tamano,
        created_at=archivo.created_at,
        created_by=archivo.created_by,
        download_url=f"/api/v1/recruiting/archivos-etapa/{archivo.id}/descargar",
    )


@router.post(
    "/oportunidades/{oportunidad_id}/candidatos/{candidato_id}/archivos-etapa",
    response_model=EtapaArchivoResponse,
    status_code=201,
    operation_id="recruiting_pipeline_archivos_subir",
    responses=responde(400, 404, 409),
    dependencies=[acceso_pipeline],
)
async def subir_archivo_etapa(
    oportunidad_id: uuid.UUID,
    candidato_id: uuid.UUID,
    etapa_id: str = Query(..., min_length=1, max_length=100, description="Etapa a la que se adjunta"),
    estado: Optional[str] = Query(None, max_length=50),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Adjunta un archivo (hasta 10 MB) a la etapa del candidato en la búsqueda."""
    nuevo = await PipelineService.guardar_archivo_etapa(
        db,
        empresa_id,
        oportunidad_id,
        candidato_id,
        etapa_id,
        archivo,
        estado=estado,
        usuario=_email_usuario(current_user),
        current_user=current_user,
    )
    return _archivo_etapa_response(nuevo)


@router.get(
    "/oportunidades/{oportunidad_id}/candidatos/{candidato_id}/archivos-etapa",
    response_model=List[EtapaArchivoResponse],
    operation_id="recruiting_pipeline_archivos_listar",
    responses=responde(404),
    dependencies=[acceso_pipeline_o_candidatos],
)
async def listar_archivos_etapa(
    oportunidad_id: uuid.UUID,
    candidato_id: uuid.UUID,
    etapa_id: Optional[str] = Query(None, max_length=100, description="Filtra por etapa"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Adjuntos del candidato en la búsqueda (lista vacía para el grupo EXTERNOS)."""
    archivos = PipelineService.listar_archivos_etapa(
        db, empresa_id, oportunidad_id, candidato_id, etapa_id=etapa_id, current_user=current_user
    )
    return [_archivo_etapa_response(a) for a in archivos]


@router.get(
    "/archivos-etapa/{archivo_id}/descargar",
    operation_id="recruiting_pipeline_archivos_descargar",
    responses={**responde(403, 404), 200: {"content": {"application/octet-stream": {}}}},
    dependencies=[acceso_pipeline_o_candidatos],
)
async def descargar_archivo_etapa(
    archivo_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Descarga un adjunto de etapa."""
    archivo = PipelineService.obtener_archivo_etapa(db, empresa_id, archivo_id, current_user)
    contenido = PipelineService.descargar_archivo_etapa(archivo)
    return Response(
        content=contenido,
        media_type=archivo.tipo_archivo or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(archivo.nombre_archivo)}",
            "Content-Length": str(len(contenido)),
        },
    )


@router.get(
    "/candidatos/{candidato_id}/pipelines",
    response_model=List[PipelineDeCandidato],
    operation_id="recruiting_candidatos_pipelines",
    responses=responde(404),
    dependencies=[acceso_pipeline_o_candidatos],
)
async def listar_pipelines_candidato(
    candidato_id: uuid.UUID,
    oportunidad_id: Optional[uuid.UUID] = Query(None, description="Limita el resultado al pipeline de esta búsqueda"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Pipelines (uno por búsqueda) en los que participa el candidato."""
    filas = PipelineService.pipelines_de_candidato(db, empresa_id, candidato_id, current_user, oportunidad_id)
    return [PipelineDeCandidato(**fila) for fila in filas]


@router.get(
    "/candidatos/{candidato_id}/postulaciones",
    response_model=List[PostulacionResponse],
    operation_id="recruiting_candidatos_postulaciones",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
async def listar_postulaciones_candidato(
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Postulaciones (procesos) en los que participa el candidato."""
    return PostulacionService.de_candidato(db, empresa_id, candidato_id, current_user)


@router.get(
    "/candidatos/{candidato_id}/busquedas-elegibles",
    response_model=List[BusquedaElegible],
    operation_id="recruiting_candidatos_busquedas_elegibles",
    responses=responde(403, 404),
    dependencies=[acceso_candidatos],
)
async def listar_busquedas_elegibles_candidato(
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Búsquedas Abiertas compatibles con el candidato a las que todavía no está asignado. 403 para EXTERNOS."""
    filas = PostulacionService.busquedas_elegibles(db, empresa_id, candidato_id, current_user)
    return [BusquedaElegible(**fila) for fila in filas]


@router.post(
    "/postulaciones/{postulacion_id}/rechazar",
    response_model=PostulacionResponse,
    operation_id="recruiting_postulaciones_rechazar",
    responses=responde(404, 409, 422),
    dependencies=[acceso_candidatos],
)
async def rechazar_postulacion(
    postulacion_id: uuid.UUID,
    datos: RechazoPostulacionRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Rechaza la participación del candidato en una búsqueda, con motivo obligatorio (409 si la búsqueda está Ganada)."""
    return PostulacionService.rechazar(
        db, empresa_id, postulacion_id, datos, usuario=_email_usuario(current_user), current_user=current_user
    )


@router.get(
    "/candidatos/{candidato_id}/historial",
    response_model=List[TransicionEstadoResponse],
    operation_id="recruiting_candidatos_historial",
    responses=responde(404),
    dependencies=[acceso_candidatos],
)
async def listar_historial_candidato(
    candidato_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Historial de cambios de estado del candidato (sin responsable ni observaciones para el grupo EXTERNOS)."""
    historial = PostulacionService.historial_de_candidato(db, empresa_id, candidato_id, current_user)
    respuesta = [TransicionEstadoResponse.model_validate(t) for t in historial]
    if usuario_es_grupo_externos(db, current_user, empresa_id):
        return [t.model_copy(update={"usuario": None, "observaciones": None, "motivo_rechazo": None}) for t in respuesta]
    return respuesta


# ---------------------------------------------------------------------------
# Alta de candidatos desde una búsqueda asignada (grupo EXTERNOS) y revisión de CV duplicados
# ---------------------------------------------------------------------------


def _respuesta_alta_en_busqueda(candidato, registro, resultado: str = "creado"):
    """201 alta; 200 CV idéntico ya registrado; 202 caso derivado a Recruiting."""
    contenido = AltaEnBusquedaResponse(
        candidato=CandidatoResponse.from_model(candidato), asignacion_id=str(registro.id)
    )
    if resultado == "creado":
        return contenido
    contenido.mensaje = (
        "El candidato ya estaba registrado y fue asociado a la búsqueda."
        if resultado == "identico"
        else CandidatoDuplicadoService.MENSAJE_DERIVADO
    )
    return JSONResponse(status_code=200 if resultado == "identico" else 202, content=contenido.model_dump(mode="json"))


@router.post(
    "/oportunidades/{oportunidad_id}/candidatos/cargar-cv",
    response_model=AltaEnBusquedaResponse,
    status_code=201,
    operation_id="recruiting_oportunidades_candidatos_cargar_cv",
    responses=responde(403, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def cargar_cv_en_busqueda_asignada(
    oportunidad_id: uuid.UUID,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Carga un CV desde una búsqueda asignada (grupo EXTERNOS): crea el candidato y lo asocia a la búsqueda. Con el
    email de un candidato existente: 200 si el CV es idéntico (se asocia la ficha existente) o 202 si es distinto (se
    asocia y el caso se deriva a Recruiting)."""
    candidato, registro, resultado = await AltaEnBusquedaService.cargar_cv(
        db, empresa_id, oportunidad_id, archivo, current_user=current_user
    )
    return _respuesta_alta_en_busqueda(candidato, registro, resultado)


@router.post(
    "/oportunidades/{oportunidad_id}/candidatos/actualizar-cv",
    response_model=AltaEnBusquedaResponse,
    status_code=201,
    operation_id="recruiting_oportunidades_candidatos_actualizar_cv",
    responses=responde(403, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def actualizar_cv_en_busqueda_asignada(
    oportunidad_id: uuid.UUID,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza el candidato existente (mismo email) con el CV nuevo y lo asocia a la búsqueda asignada (EXTERNOS)."""
    candidato, registro, _ = await AltaEnBusquedaService.cargar_cv(
        db, empresa_id, oportunidad_id, archivo, current_user=current_user, actualizar_existente=True
    )
    return _respuesta_alta_en_busqueda(candidato, registro)


@router.post(
    "/oportunidades/{oportunidad_id}/candidatos/nuevo",
    response_model=AltaEnBusquedaResponse,
    status_code=201,
    operation_id="recruiting_oportunidades_candidatos_nuevo",
    responses=responde(400, 403, 404, 409, 422),
    dependencies=[acceso_busquedas],
)
async def crear_candidato_en_busqueda_asignada(
    oportunidad_id: uuid.UUID,
    datos: CandidatoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Alta manual de un candidato desde una búsqueda asignada (grupo EXTERNOS): lo crea a nombre del usuario y lo asocia
    a la búsqueda."""
    candidato, registro = AltaEnBusquedaService.crear_candidato(
        db, empresa_id, oportunidad_id, datos, current_user=current_user
    )
    return _respuesta_alta_en_busqueda(candidato, registro)


acceso_dashboard = Depends(require_submodulo("recruiting", "dashboard"))


@router.get(
    "/candidatos-duplicados",
    response_model=CasoDuplicadoLista,
    operation_id="recruiting_candidatos_duplicados_listar",
    responses=responde(403),
    dependencies=[acceso_dashboard],
)
async def listar_candidatos_duplicados_pendientes(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Casos de CV duplicado pendientes de revisión (solo usuarios internos)."""
    items = CandidatoDuplicadoService.listar_pendientes(db, empresa_id, current_user)
    return CasoDuplicadoLista(items=[CasoDuplicado(**i) for i in items], total=len(items))


@router.get(
    "/candidatos-duplicados/{caso_id}",
    response_model=CasoDuplicadoDetalle,
    operation_id="recruiting_candidatos_duplicados_obtener",
    responses=responde(403, 404),
    dependencies=[acceso_dashboard],
)
async def obtener_candidato_duplicado(
    caso_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """El caso con los datos del CV actual y del nuevo para compararlos."""
    return CasoDuplicadoDetalle(**CandidatoDuplicadoService.obtener_detalle(db, empresa_id, caso_id, current_user))


@router.post(
    "/candidatos-duplicados/{caso_id}/resolver",
    response_model=ResolucionCasoDuplicado,
    operation_id="recruiting_candidatos_duplicados_resolver",
    responses=responde(403, 404, 409, 422),
    dependencies=[acceso_dashboard],
)
async def resolver_candidato_duplicado(
    caso_id: uuid.UUID,
    datos: ResolverCasoDuplicadoRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    """Conserva el CV actual o actualiza la ficha con el CV nuevo."""
    return ResolucionCasoDuplicado(**CandidatoDuplicadoService.resolver(db, empresa_id, caso_id, datos.accion, current_user))
