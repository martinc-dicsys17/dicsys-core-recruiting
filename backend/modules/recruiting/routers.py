"""Routers del módulo Recruiting.

Montado en main.py con require_modulo('recruiting'); cada endpoint exige además el permiso de su ítem del menú
('recruiting.<codigo>'). Por ahora, el Dashboard y el Manager Dashboard (solo administradores).
"""

import uuid
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.errores import responde
from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_admin, require_submodulo
from backend.modules.recruiting.manager_dashboard import ManagerDashboardService
from backend.modules.recruiting.schemas import ManagerDashboard, ManagerDashboardFiltros, RecruitingDashboard
from backend.modules.recruiting.services import DashboardService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/recruiting", tags=["recruiting"], responses=responde(401, 403))


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
