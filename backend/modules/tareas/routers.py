"""
API de Configuración → Tareas programadas (F19-P02).

Montado en main.py con require_submodulo('configuracion', 'tareas_programadas').
El horario y si cada tarea está activa se editan en Parámetros, no acá (regla del
proyecto: la configuración en runtime vive en Parámetros); esta API muestra el
estado, permite correr una tarea a mano y reintentar un envío.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.modules.tareas import alertas, cola
from backend.modules.tareas.models import Envio, TareaCorrida
from backend.modules.tareas.programador import configuracion, en_curso, ultima_programada
from backend.modules.tareas.registro import (
    TAREAS,
    a_argentina,
    ahora_argentina,
    clave_activa,
    clave_horario,
    proxima,
)
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/tareas", tags=["Tareas programadas"])


class CorridaResponse(BaseModel):
    id: str
    tarea: str
    nombre: str
    disparo: str
    estado: str
    solicitada_por: Optional[str] = None
    creada_at: datetime  # hora Argentina
    inicio: Optional[datetime] = None
    fin: Optional[datetime] = None
    resultado: Optional[str] = None
    error: Optional[str] = None
    alerta_enviada: bool = False


class TareaResponse(BaseModel):
    codigo: str
    nombre: str
    modulo: str
    descripcion: str
    continua: bool
    activa: bool
    horario: Optional[str] = None  # tal como está en Parámetros
    horario_texto: Optional[str] = None  # legible: «Todos los días a las 09:00»
    horario_error: Optional[str] = None
    proxima: Optional[datetime] = None
    en_curso: bool
    ultima: Optional[CorridaResponse] = None
    parametros: List[str]


class TablaTareas(BaseModel):
    tareas: List[TareaResponse]
    alertas_configuradas: bool
    parametro_alertas: str


class EnvioResponse(BaseModel):
    id: str
    origen: str
    canal: str
    destino: str
    asunto: Optional[str] = None
    estado: str
    intentos: int
    error: Optional[str] = None
    creada_at: datetime
    proximo_intento_at: Optional[datetime] = None
    enviado_at: Optional[datetime] = None


def _corrida(c: TareaCorrida) -> Dict:
    tarea = TAREAS.get(c.tarea)
    return {
        "id": str(c.id),
        "tarea": c.tarea,
        "nombre": tarea.nombre if tarea else c.tarea,
        "disparo": c.disparo,
        "estado": c.estado,
        "solicitada_por": c.solicitada_por,
        "creada_at": a_argentina(c.creada_at),
        "inicio": a_argentina(c.inicio),
        "fin": a_argentina(c.fin),
        "resultado": c.resultado,
        "error": c.error,
        "alerta_enviada": c.alerta_enviada,
    }


@router.get("", response_model=TablaTareas)
async def listar_tareas(db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    ahora = ahora_argentina()
    filas = []
    for tarea in sorted(TAREAS.values(), key=lambda t: (t.modulo, t.nombre)):
        cfg = configuracion(db, tarea)
        ultima = (
            db.query(TareaCorrida)
            .filter(TareaCorrida.tarea == tarea.codigo)
            .order_by(TareaCorrida.creada_at.desc())
            .first()
        )
        prox = None
        if cfg["activa"] and cfg["horario"] is not None:
            prox = proxima(cfg["horario"], ahora, ultima_programada(db, tarea.codigo))
        filas.append(
            {
                "codigo": tarea.codigo,
                "nombre": tarea.nombre,
                "modulo": tarea.modulo,
                "descripcion": tarea.descripcion,
                "continua": tarea.continua,
                "activa": cfg["activa"],
                "horario": cfg["horario_texto"],
                "horario_texto": cfg["horario"].texto() if cfg["horario"] else None,
                "horario_error": cfg["horario_error"],
                "proxima": prox,
                "en_curso": en_curso(db, tarea.codigo),
                "ultima": _corrida(ultima) if ultima else None,
                "parametros": [] if tarea.continua else [clave_activa(tarea.codigo), clave_horario(tarea.codigo)],
            }
        )
    return {
        "tareas": filas,
        "alertas_configuradas": alertas.room_de_alertas(db) is not None,
        "parametro_alertas": alertas.CLAVE_ROOM,
    }


@router.post("/{codigo}/ejecutar", response_model=CorridaResponse, status_code=status.HTTP_201_CREATED)
async def ejecutar_ahora(codigo: str, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)):
    """Pide una corrida a mano: el programador la toma en su próxima vuelta (unos segundos)."""
    if codigo not in TAREAS:
        raise HTTPException(status_code=404, detail="La tarea no existe")
    if en_curso(db, codigo):
        raise HTTPException(status_code=409, detail="La tarea ya está corriendo o tiene una corrida pedida")
    corrida = TareaCorrida(tarea=codigo, disparo="manual", estado="pendiente", solicitada_por=current_user.email)
    db.add(corrida)
    db.commit()
    db.refresh(corrida)
    return _corrida(corrida)


@router.get("/corridas", response_model=List[CorridaResponse])
async def historial(
    tarea: Optional[str] = None,
    estado: Optional[str] = None,
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    consulta = db.query(TareaCorrida)
    if tarea:
        consulta = consulta.filter(TareaCorrida.tarea == tarea)
    if estado:
        consulta = consulta.filter(TareaCorrida.estado == estado)
    return [_corrida(c) for c in consulta.order_by(TareaCorrida.creada_at.desc()).limit(limite).all()]


def _envio(e: Envio) -> Dict:
    return {
        "id": str(e.id),
        "origen": e.origen,
        "canal": e.canal,
        "destino": e.destino,
        "asunto": e.asunto,
        "estado": e.estado,
        "intentos": e.intentos,
        "error": e.error,
        "creada_at": a_argentina(e.creada_at),
        "proximo_intento_at": a_argentina(e.proximo_intento_at) if e.estado == "pendiente" else None,
        "enviado_at": a_argentina(e.enviado_at),
    }


@router.get("/envios", response_model=List[EnvioResponse])
async def envios(
    estado: Optional[str] = None,
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    consulta = db.query(Envio)
    if estado:
        consulta = consulta.filter(Envio.estado == estado)
    return [_envio(e) for e in consulta.order_by(Envio.creada_at.desc()).limit(limite).all()]


@router.post("/envios/{envio_id}/reintentar", response_model=EnvioResponse)
async def reintentar_envio(
    envio_id: str, db: Session = Depends(get_db), current_user: Usuario = Depends(get_current_user)
):
    try:
        envio = db.get(Envio, uuid.UUID(envio_id))
    except ValueError:
        envio = None
    if envio is None:
        raise HTTPException(status_code=404, detail="El envío no existe")
    try:
        return _envio(cola.reintentar(db, envio))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
