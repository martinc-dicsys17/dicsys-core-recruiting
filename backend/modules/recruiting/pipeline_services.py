"""Servicios del Pipeline de Recruiting (ítem «gestion_busquedas»).

Origen: GestionBusquedaService, MotivoDescarteService y las partes de PostulacionService del módulo original
(modulo-recluiter, backend/modules/recruiting/services.py). Reutiliza la visibilidad y el anonimato de EXTERNOS de
services.py (CandidatosDeBusquedaService, OcultadorCandidatosEnBusqueda) y no duplica el alta, la desvinculación ni el
recálculo de contadores, que ya viven ahí.
"""

import logging
import os
import unicodedata
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import exists, false, func, or_
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.recruiting.models import (
    Candidato,
    CandidatoDuplicado,
    EtapaArchivo,
    GestionBusqueda,
    HistorialPipeline,
    Postulacion,
    RecruitingEtapa,
    RecruitingMotivoDescarte,
    RecruitingMotivoDescarteEtapa,
    RecrutingConfig,
    Solicitud,
    TransicionEstado,
)
from backend.modules.recruiting.schemas import (
    AsignarCandidatoRequest,
    CambiarEtapaRequest,
    CandidatoCreate,
    RechazoPostulacionRequest,
    lista_de_textos,
)
from backend.modules.recruiting.services import (
    MENSAJE_ERROR_INTERNO,
    PARTES_NOMBRE_GRUPO_RECRUITING,
    CandidatoService,
    CandidatosDeBusquedaService,
    CVDuplicadoDistintoError,
    CVEmailDuplicadoError,
    CVPersistenciaError,
    OcultadorCandidatosEnBusqueda,
    OportunidadService,
    usuario_es_grupo_externos,
)
from backend.modules.usuarios.models import Usuario

SIN_IDENTIFICAR = "Sin identificar"
ESTADO_DESCARTADO = "Descartado"
ETAPA_DESCARTADOS = "Descartados"

EXTENSIONES_ADJUNTO = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".txt", ".zip", ".rar"}
MAX_BYTES_ADJUNTO = 10 * 1024 * 1024


def _sin_tildes(texto: str) -> str:
    """Mayúsculas y sin diacríticos (robusto ante NFC y NFD)."""
    descompuesto = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


class PipelineService:
    """Etapas, vistas y movimientos del pipeline de una búsqueda (recruiting_gestionBusqueda)."""

    # Flujo secuencial: se avanza solo a la etapa inmediata siguiente o a un salto permitido
    FLUJO_SECUENCIAL = [
        "Candidato",
        "Screening",
        "Entrevista RRHH",
        "Entrevista Líder Dicsys",
        "Validación Administración",
        "Entrevista Cliente",
        "Oferta",
        "Examen Médico Preocupacional",
        "Ingreso",
    ]

    SALTOS_PERMITIDOS = {
        "Entrevista Líder Dicsys": ["Entrevista Cliente"],
        "Validación Administración": ["Oferta"],
        "Entrevista Cliente": ["Examen Médico Preocupacional"],
    }

    # Columnas de la vista global. «Presentados» no tiene etapas: el modelo no registra cuándo un candidato se presentó
    # al cliente, así que la columna queda en 0 en lugar de inventar una equivalencia.
    COLUMNAS_PIPELINE_GLOBAL = [
        {"clave": "screening", "nombre": "Screening", "etapas": ["Candidato", "Screening"]},
        {
            "clave": "submissions",
            "nombre": "Presentados",
            "etapas": [],
            "nota": "Sin dato: el sistema no registra cuándo un candidato fue presentado al cliente.",
        },
        {
            "clave": "interview",
            "nombre": "Entrevistas",
            "etapas": ["Entrevista RRHH", "Entrevista Líder Dicsys", "Validación Administración", "Entrevista Cliente"],
        },
        {"clave": "offer", "nombre": "Oferta", "etapas": ["Oferta", "Examen Médico Preocupacional"]},
        {"clave": "hire", "nombre": "Contratados", "etapas": ["Ingreso"]},
    ]

    # ---- etapas -----------------------------------------------------------------------------------------------

    @classmethod
    def normalizar_nombre_etapa(cls, etapa: Optional[str]) -> str:
        """Nombre canónico de la etapa (acepta nombres legados: Postulado, Entrevista Técnica...)."""
        if not etapa:
            return "Candidato"
        valor = etapa.strip()
        clave = _sin_tildes(valor)
        if clave in ("DESCARTADO", "DESCARTADOS"):
            return ETAPA_DESCARTADOS
        if clave in ("CANDIDATO", "POSTULADO", "COORDINANDO ENTREVISTA"):
            return "Candidato"
        if clave == "SCREENING":
            return "Screening"
        if "RRHH" in clave:
            return "Entrevista RRHH"
        if "LIDER" in clave or "TECNICA" in clave:
            return "Entrevista Líder Dicsys"
        if "ADMINISTRACION" in clave:
            return "Validación Administración"
        if "EXAMEN" in clave or "PREOCUPACIONAL" in clave:
            return "Examen Médico Preocupacional"
        if "CLIENTE" in clave:
            return "Entrevista Cliente"
        if "OFERTA" in clave:
            return "Oferta"
        if "INGRESO" in clave:
            return "Ingreso"
        return valor

    @classmethod
    def etapa_clave(cls, etapa: Optional[str]) -> str:
        """Etapa canónica en mayúsculas y sin tildes (clave de recruiting_etapas)."""
        return _sin_tildes(cls.normalizar_nombre_etapa(etapa))

    # ---- permisos -----------------------------------------------------------------------------------------------

    @staticmethod
    def permisos(db: Session, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, bool]:
        """Acciones habilitadas del Pipeline: el grupo EXTERNOS no mueve ni descarta, no asigna ni elimina, y solo
        carga CV desde una búsqueda asignada."""
        no_externo = not usuario_es_grupo_externos(db, current_user, empresa_id)
        return {
            "puede_mover_descartar": no_externo,
            "puede_eliminar_candidatos": no_externo,
            "puede_asignar_candidatos": no_externo,
            "puede_crear_busquedas": no_externo,
            "puede_eliminar_busquedas": no_externo,
            "puede_ver_lider_tipo_fecha_busqueda": no_externo,
            "puede_ver_smart_matching": no_externo,
            "puede_cargar_cv_general": no_externo,
            "puede_cargar_cv_en_busqueda": not no_externo,
        }

    # ---- alcance de candidatos --------------------------------------------------------------------------------------

    @staticmethod
    def normalizar_alcance(valor: Optional[str]) -> str:
        """'todos' (por defecto) o 'propios'; otro valor es 400."""
        v = (valor or "").strip().lower()
        if v in ("", "todos"):
            return "todos"
        if v == "propios":
            return "propios"
        raise HTTPException(status_code=400, detail="Valor inválido para alcance_candidatos: use todos o propios")

    @staticmethod
    def _condicion_alcance(alcance: Optional[str], current_user: Optional[Usuario]):
        """'propios' = candidatos que cargó el usuario actual; se suma a la visibilidad, nunca la amplía. None si es
        'todos'."""
        if PipelineService.normalizar_alcance(alcance) != "propios":
            return None
        if not current_user:
            return false()
        return Candidato.creador_id == current_user.id

    # ---- vistas de una búsqueda -------------------------------------------------------------------------------------

    @staticmethod
    def contadores(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        current_user: Optional[Usuario] = None,
        alcance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Candidatos vigentes de la búsqueda por etapa, con la misma visibilidad que la tabla del Pipeline."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        query = (
            db.query(GestionBusqueda.etapa_actual, func.count(GestionBusqueda.id))
            .join(Candidato, GestionBusqueda.candidato_id == Candidato.id)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
            )
        )
        query = CandidatosDeBusquedaService._filtro_visibilidad(query, db, empresa_id, current_user)
        condicion = PipelineService._condicion_alcance(alcance, current_user)
        if condicion is not None:
            query = query.filter(condicion)
        por_etapa = {etapa: cantidad for etapa, cantidad in query.group_by(GestionBusqueda.etapa_actual).all()}
        # «total» son los que siguen en proceso: los descartados salen del embudo (se ven en su propia etapa)
        en_proceso = sum(n for etapa, n in por_etapa.items() if PipelineService.normalizar_nombre_etapa(etapa) != ETAPA_DESCARTADOS)
        return {"total": en_proceso, "por_etapa": por_etapa}

    @staticmethod
    def candidatos_por_columna(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        columna: str,
        current_user: Optional[Usuario] = None,
        alcance: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Candidatos de una búsqueda en una columna de la vista global; mismas agrupaciones y exclusiones que el
        resumen, así que coincide con la cifra mostrada."""
        PipelineService.normalizar_alcance(alcance)
        col = next((c for c in PipelineService.COLUMNAS_PIPELINE_GLOBAL if c["clave"] == columna), None)
        if col is None:
            raise HTTPException(status_code=404, detail="Columna de pipeline no encontrada")
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        candidatos = CandidatosDeBusquedaService.listar(
            db, empresa_id, oportunidad_id, current_user, alcance=alcance
        )
        reclutador = " ".join((solicitud.recruiter_nombre or "").split()) or None

        vistos = set()
        resultado = []
        for fila in candidatos:
            etapa = PipelineService.normalizar_nombre_etapa(fila["etapa_actual"])
            if etapa == ETAPA_DESCARTADOS or (fila["estado"] or "").strip().lower() == "descartado":
                continue
            if etapa not in col["etapas"] or fila["candidato_id"] in vistos:
                continue
            vistos.add(fila["candidato_id"])
            if fila.get("es_anonimo"):
                # Anónimo: solo el nombre ya enmascarado y el seniority; el resto no viaja al navegador
                resultado.append(
                    {
                        "candidato_id": fila["candidato_id"],
                        "nombre": fila["nombre"],
                        "seniority": fila["seniority"],
                        "es_anonimo": True,
                        "etapa_actual": etapa,
                    }
                )
                continue
            resultado.append(
                {
                    "presentado_por": fila.get("presentado_por"),
                    "candidato_id": fila["candidato_id"],
                    "nombre": fila["nombre"],
                    "pretension_salarial_bruta_ars": fila["pretension_salarial_bruta_ars"],
                    "rol_actual": fila["headline"],
                    "seniority": fila["seniority"],
                    "es_anonimo": False,
                    "reclutador": reclutador,
                    "etapa_actual": etapa,
                }
            )
        return resultado

    @staticmethod
    def resumen_global(
        db: Session,
        empresa_id: uuid.UUID,
        estado: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        alcance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Vista global: una fila por búsqueda visible con la cantidad de candidatos distintos por columna, sin los
        descartados."""
        busquedas = OportunidadService.consulta(db, empresa_id, estado=estado, current_user=current_user).all()

        clave_por_etapa = {
            etapa: col["clave"] for col in PipelineService.COLUMNAS_PIPELINE_GLOBAL for etapa in col["etapas"]
        }
        conteos: Dict[Any, Dict[str, int]] = {}
        sin_clasificar: Dict[Any, int] = {}
        ids = [s.id for s in busquedas]
        if ids:
            query = (
                db.query(
                    GestionBusqueda.oportunidad_id,
                    GestionBusqueda.etapa_actual,
                    GestionBusqueda.estado,
                    func.count(func.distinct(GestionBusqueda.candidato_id)),
                )
                .join(Candidato, GestionBusqueda.candidato_id == Candidato.id)
                .filter(
                    GestionBusqueda.empresa_id == empresa_id,
                    GestionBusqueda.oportunidad_id.in_(ids),
                    GestionBusqueda.activo.is_(True),
                    GestionBusqueda.deleted_at.is_(None),
                    Candidato.deleted_at.is_(None),
                )
            )
            query = CandidatosDeBusquedaService._filtro_visibilidad(query, db, empresa_id, current_user)
            condicion = PipelineService._condicion_alcance(alcance, current_user)
            if condicion is not None:
                query = query.filter(condicion)
            filas = query.group_by(
                GestionBusqueda.oportunidad_id, GestionBusqueda.etapa_actual, GestionBusqueda.estado
            ).all()
            for op_id, etapa_raw, estado_raw, cantidad in filas:
                etapa = PipelineService.normalizar_nombre_etapa(etapa_raw)
                if etapa == ETAPA_DESCARTADOS or (estado_raw or "").strip().lower() == "descartado":
                    continue
                clave = clave_por_etapa.get(etapa)
                if clave is None:
                    sin_clasificar[op_id] = sin_clasificar.get(op_id, 0) + int(cantidad)
                    continue
                fila = conteos.setdefault(op_id, {})
                fila[clave] = fila.get(clave, 0) + int(cantidad)

        items = []
        for s in busquedas:
            columnas = {
                col["clave"]: conteos.get(s.id, {}).get(col["clave"], 0)
                for col in PipelineService.COLUMNAS_PIPELINE_GLOBAL
            }
            items.append(
                {
                    "id": str(s.id),
                    "id_busqueda": s.id_busqueda,
                    "titulo": s.titulo,
                    "cliente": s.cliente,
                    "estado": s.estado,
                    "recruiter_nombre": s.recruiter_nombre,
                    "es_externa": s.externo_id is not None,
                    "total": sum(columnas.values()),
                    "columnas": columnas,
                    "sin_clasificar": sin_clasificar.get(s.id, 0),
                }
            )
        return {"columnas": PipelineService.COLUMNAS_PIPELINE_GLOBAL, "items": items}

    # ---- pipelines de un candidato -----------------------------------------------------------------------------------

    @staticmethod
    def _nombres_presentadores(db: Session, ids_creadores: Any) -> Dict[Any, str]:
        ids = {i for i in ids_creadores if i}
        if not ids:
            return {}
        return {
            u.id: (" ".join(f"{u.nombre or ''} {u.apellido or ''}".split()) or u.email or SIN_IDENTIFICAR)
            for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()
        }

    @staticmethod
    def pipelines_de_candidato(
        db: Session,
        empresa_id: uuid.UUID,
        candidato_id: uuid.UUID,
        current_user: Optional[Usuario] = None,
        oportunidad_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Pipelines (uno por búsqueda) en los que participa el candidato y que tienen al menos un movimiento en el
        historial. Omite las búsquedas que el usuario no puede ver; con `oportunidad_id` se limita a esa búsqueda."""
        candidato = CandidatoService.get_ficha(db, empresa_id, str(candidato_id), current_user=current_user)
        solicitud_filtro = (
            OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
            if oportunidad_id
            else None
        )
        filas = (
            db.query(GestionBusqueda, Solicitud)
            .join(Solicitud, GestionBusqueda.oportunidad_id == Solicitud.id)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.candidato_id == candidato.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                Solicitud.deleted_at.is_(None),
                exists().where(
                    HistorialPipeline.empresa_id == empresa_id,
                    HistorialPipeline.oportunidad_id == GestionBusqueda.oportunidad_id,
                    HistorialPipeline.candidato_id == GestionBusqueda.candidato_id,
                ),
                *([GestionBusqueda.oportunidad_id == solicitud_filtro.id] if solicitud_filtro else []),
            )
            .order_by(GestionBusqueda.created_at.asc())
            .all()
        )

        es_externo = usuario_es_grupo_externos(db, current_user, empresa_id)
        ocultador = OcultadorCandidatosEnBusqueda(db, empresa_id, current_user)
        presentador = PipelineService._nombres_presentadores(db, [candidato.creador_id]).get(
            candidato.creador_id, SIN_IDENTIFICAR
        )
        resultado = []
        for g, s in filas:
            try:
                OportunidadService.get_by_id(db, empresa_id, s.id, current_user=current_user)
            except HTTPException:
                continue
            resultado.append(
                {
                    "presentado_por": None if ocultador.es_anonimo(candidato, g) else presentador,
                    "gestion_id": str(g.id),
                    "oportunidad_id": str(s.id),
                    "titulo": s.titulo,
                    "cliente": s.cliente,
                    "etapa_actual": g.etapa_actual,
                    "estado": g.estado,
                    # El grupo EXTERNOS no ve datos salariales
                    "pretension_salarial_bruta_ars": None if es_externo else g.pretension_salarial_bruta_ars,
                }
            )
        return resultado

    @staticmethod
    def candidatos_con_pipeline(
        db: Session,
        empresa_id: uuid.UUID,
        candidato_ids: List[uuid.UUID],
        current_user: Optional[Usuario] = None,
    ) -> set:
        """Ids (texto) de los candidatos dados con al menos un pipeline visible: mismo criterio que
        `pipelines_de_candidato`, resuelto con una sola consulta para todo el listado."""
        if not candidato_ids:
            return set()
        filtros = [
            GestionBusqueda.empresa_id == empresa_id,
            GestionBusqueda.candidato_id.in_(candidato_ids),
            GestionBusqueda.activo.is_(True),
            GestionBusqueda.deleted_at.is_(None),
            Solicitud.deleted_at.is_(None),
            exists().where(
                HistorialPipeline.empresa_id == empresa_id,
                HistorialPipeline.oportunidad_id == GestionBusqueda.oportunidad_id,
                HistorialPipeline.candidato_id == GestionBusqueda.candidato_id,
            ),
        ]
        if current_user and usuario_es_grupo_externos(db, current_user, empresa_id):
            filtros.append(Solicitud.externo_id == current_user.id)
        filas = (
            db.query(GestionBusqueda.candidato_id)
            .join(Solicitud, GestionBusqueda.oportunidad_id == Solicitud.id)
            .filter(*filtros)
            .distinct()
            .all()
        )
        return {str(candidato_id) for (candidato_id,) in filas}

    # ---- mover de etapa ----------------------------------------------------------------------------------------------

    @staticmethod
    def _historial(
        db: Session,
        empresa_id: uuid.UUID,
        solicitud: Solicitud,
        candidato: Candidato,
        anterior: Optional[str],
        nueva: str,
        estado: Optional[str],
        descripcion: Optional[str],
        motivo: Optional[str],
        usuario: Optional[str],
    ) -> None:
        db.add(
            HistorialPipeline(
                empresa_id=empresa_id,
                oportunidad_id=solicitud.id,
                candidato_id=candidato.id,
                etapa_anterior=anterior,
                etapa_nueva=nueva,
                estado_nuevo=estado,
                descripcion=descripcion,
                motivo_descarte=motivo,
                usuario=usuario,
            )
        )

    @staticmethod
    def cambiar_etapa(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        datos: CambiarEtapaRequest,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> GestionBusqueda:
        """Mueve, descarta o reingresa a un candidato (ver `_mover`) y deja actualizados los contadores de la búsqueda."""
        registro = PipelineService._mover(db, empresa_id, oportunidad_id, candidato_id, datos, usuario, current_user)
        solicitud = db.query(Solicitud).filter(Solicitud.id == oportunidad_id, Solicitud.empresa_id == empresa_id).first()
        if solicitud:
            CandidatosDeBusquedaService.recalcular_metricas(db, solicitud)
        return registro

    @staticmethod
    def _mover(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        datos: CambiarEtapaRequest,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> GestionBusqueda:
        """Mueve, descarta o reingresa a un candidato respetando el flujo secuencial:

        - Avance solo a la etapa inmediata siguiente o a un salto permitido; sin retrocesos.
        - Descarte desde cualquier etapa activa, con un motivo del catálogo de esa etapa.
        - Un descartado solo reingresa a Entrevista RRHH, con el motivo de reingreso obligatorio.
        - De Entrevista RRHH a Entrevista Líder Dicsys la pretensión salarial bruta es obligatoria.
        - Cada cambio deja su fila en recruiting_historial_pipeline.
        - Llegar a Ingreso cierra la búsqueda como Ganada en la misma transacción; una Ganada no admite más movimientos.
        """
        OportunidadService.exigir_no_externo(
            db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no pueden mover de etapa ni descartar candidatos"
        )
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)
        candidato = CandidatoService.validar_operable(db, empresa_id, str(candidato_id), current_user=current_user)

        registro = (
            db.query(GestionBusqueda)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.candidato_id == candidato.id,
            )
            .first()
        )
        if registro is not None and registro.deleted_at is not None:
            # Estuvo desvinculado: se reactiva la misma fila (restricción única por candidato y búsqueda)
            registro.deleted_at = None
            registro.activo = True
            registro.etapa_actual = "Candidato"
            registro.estado = "En proceso"
            registro.motivo_descarte = None
            registro.feedback_etapa = None
            registro.pretension_salarial_bruta_ars = None

        destino = PipelineService.normalizar_nombre_etapa(datos.etapa_actual)
        destino_clave = PipelineService.etapa_clave(datos.etapa_actual)
        es_descarte = destino_clave in ("DESCARTADOS", "DESCARTADO") or (
            (datos.estado or "").strip().lower() == "descartado"
        )
        motivo = (datos.motivo_descarte or "").strip()
        feedback = (datos.feedback_etapa or "").strip() or None
        ahora = utc_now()

        if registro is None:
            if es_descarte and not motivo:
                raise HTTPException(
                    status_code=400, detail="El motivo de descarte es obligatorio para registrar un descarte."
                )
            etapa_nueva = ETAPA_DESCARTADOS if es_descarte else destino
            estado_nuevo = ESTADO_DESCARTADO if es_descarte else ("Ingreso confirmado" if destino_clave == "INGRESO" else "En proceso")
            registro = GestionBusqueda(
                empresa_id=empresa_id,
                oportunidad_id=solicitud.id,
                candidato_id=candidato.id,
                etapa_actual=etapa_nueva,
                estado=estado_nuevo,
                motivo_descarte=motivo if es_descarte and motivo else None,
                feedback_etapa=feedback,
                fecha_cambio_etapa=ahora,
                activo=True,
                updated_by=usuario,
            )
            db.add(registro)
            PipelineService._historial(
                db, empresa_id, solicitud, candidato, None, etapa_nueva, estado_nuevo, feedback,
                motivo if es_descarte and motivo else None, usuario,
            )
            if not es_descarte and destino == "Ingreso":
                OportunidadService.marcar_ganada(solicitud, usuario)
            db.commit()
            db.refresh(registro)
            return registro

        origen = PipelineService.normalizar_nombre_etapa(registro.etapa_actual)
        origen_clave = PipelineService.etapa_clave(registro.etapa_actual)
        esta_descartado = origen_clave in ("DESCARTADOS", "DESCARTADO") or (
            (registro.estado or "").strip().lower() == "descartado"
        )

        # Caso 1: descartado que se vuelve a descartar o que reingresa
        if esta_descartado:
            if es_descarte:
                if motivo:
                    registro.motivo_descarte = motivo
                if datos.feedback_etapa is not None:
                    registro.feedback_etapa = feedback
                registro.updated_at = ahora
                registro.updated_by = usuario
                db.commit()
                db.refresh(registro)
                return registro
            if destino_clave != "ENTREVISTA RRHH":
                raise HTTPException(
                    status_code=400,
                    detail="Excepción de Reingreso: un candidato descartado solo puede ser reingresado al proceso a "
                    "partir de la etapa 'Entrevista RRHH'.",
                )
            if not feedback:
                raise HTTPException(
                    status_code=400, detail="El motivo de reingreso por cambio de perfil es obligatorio."
                )
            registro.etapa_actual = "Entrevista RRHH"
            registro.estado = "En proceso"
            registro.motivo_descarte = None
            registro.feedback_etapa = feedback
            registro.fecha_cambio_etapa = ahora
            registro.updated_at = ahora
            registro.updated_by = usuario
            PipelineService._historial(
                db, empresa_id, solicitud, candidato, ETAPA_DESCARTADOS, "Entrevista RRHH", "En proceso",
                f"Reingreso al proceso: {feedback}", None, usuario,
            )
            db.commit()
            db.refresh(registro)
            return registro

        # Caso 2: descarte desde una etapa activa
        if es_descarte:
            if not motivo:
                raise HTTPException(
                    status_code=400, detail="Debe seleccionar un motivo de descarte válido para la etapa actual."
                )
            if not MotivoDescarteService.existe_motivo_en_etapa(db, motivo, registro.etapa_actual):
                raise HTTPException(
                    status_code=400,
                    detail="El motivo de descarte seleccionado no corresponde a la etapa actual del candidato.",
                )
            etapa_anterior = registro.etapa_actual
            registro.etapa_actual = ETAPA_DESCARTADOS
            registro.estado = ESTADO_DESCARTADO
            registro.motivo_descarte = motivo
            if datos.feedback_etapa is not None:
                registro.feedback_etapa = feedback
            registro.fecha_cambio_etapa = ahora
            registro.updated_at = ahora
            registro.updated_by = usuario
            PipelineService._historial(
                db, empresa_id, solicitud, candidato, etapa_anterior, ETAPA_DESCARTADOS, ESTADO_DESCARTADO,
                feedback, motivo, usuario,
            )
            db.commit()
            db.refresh(registro)
            return registro

        # Caso 3: avance secuencial
        flujo = PipelineService.FLUJO_SECUENCIAL
        if origen == "Ingreso":
            raise HTTPException(
                status_code=400, detail="El candidato ya se encuentra en la etapa final 'Ingreso' (etapa terminal)."
            )
        if origen in flujo:
            idx_origen = flujo.index(origen)
        elif "TECNICA" in origen_clave:
            idx_origen = 2
        else:
            idx_origen = 0
        if destino not in flujo:
            raise HTTPException(
                status_code=400, detail=f"La etapa destino '{datos.etapa_actual}' no es una etapa válida del embudo."
            )
        idx_destino = flujo.index(destino)
        saltos = PipelineService.SALTOS_PERMITIDOS.get(origen, [])
        if idx_destino != idx_origen + 1 and destino not in saltos:
            esperada = flujo[idx_origen + 1] if idx_origen + 1 < len(flujo) else "Ninguna"
            if saltos:
                esperada = " o ".join([esperada] + saltos)
            raise HTTPException(
                status_code=400,
                detail=f"Transición de etapa inválida. El avance debe ser secuencial estricto. Desde '{origen}' solo "
                f"se puede avanzar a '{esperada}' (no se permite saltear etapas ni retroceder).",
            )

        # Se valida antes de tocar nada: si la pretensión falta o es inválida no se guarda ningún cambio
        pasa_a_lider = origen == "Entrevista RRHH" and destino == "Entrevista Líder Dicsys"
        if pasa_a_lider and (datos.pretension_salarial_bruta_ars is None or datos.pretension_salarial_bruta_ars <= 0):
            raise HTTPException(
                status_code=400,
                detail="La pretensión salarial bruta es obligatoria y debe ser un importe entero positivo para "
                "avanzar a Entrevista Líder Dicsys.",
            )

        etapa_anterior = registro.etapa_actual
        nuevo_estado = "Ingreso confirmado" if destino_clave == "INGRESO" else "En proceso"
        registro.etapa_actual = destino
        registro.estado = nuevo_estado
        registro.motivo_descarte = None
        if datos.feedback_etapa is not None:
            registro.feedback_etapa = feedback
        if pasa_a_lider and datos.pretension_salarial_bruta_ars is not None:
            registro.pretension_salarial_bruta_ars = datos.pretension_salarial_bruta_ars
        registro.fecha_cambio_etapa = ahora
        registro.updated_at = ahora
        registro.updated_by = usuario
        PipelineService._historial(
            db, empresa_id, solicitud, candidato, etapa_anterior, destino, nuevo_estado, feedback, None, usuario
        )
        if destino == "Ingreso":
            OportunidadService.marcar_ganada(solicitud, usuario)
        db.commit()
        db.refresh(registro)
        return registro

    # ---- historial -------------------------------------------------------------------------------------------------

    @staticmethod
    def historial(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        current_user: Optional[Usuario] = None,
    ) -> List[Dict[str, Any]]:
        """Movimientos del candidato en la búsqueda, del más antiguo al más reciente. Sin responsable, observaciones ni
        datos salariales para el grupo EXTERNOS."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        candidato = CandidatoService.get_ficha(db, empresa_id, str(candidato_id), current_user=current_user)
        registros = (
            db.query(HistorialPipeline)
            .filter(
                HistorialPipeline.empresa_id == empresa_id,
                HistorialPipeline.oportunidad_id == solicitud.id,
                HistorialPipeline.candidato_id == candidato.id,
            )
            .order_by(HistorialPipeline.created_at.asc())
            .all()
        )
        # La pretensión vigente se muestra en el último movimiento Entrevista RRHH -> Entrevista Líder Dicsys
        pretension = (
            db.query(GestionBusqueda.pretension_salarial_bruta_ars)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.candidato_id == candidato.id,
                GestionBusqueda.deleted_at.is_(None),
            )
            .scalar()
        )
        id_mov_lider = None
        if pretension is not None:
            for r in registros:
                if (
                    PipelineService.etapa_clave(r.etapa_anterior) == "ENTREVISTA RRHH"
                    and PipelineService.normalizar_nombre_etapa(r.etapa_nueva) == "Entrevista Líder Dicsys"
                ):
                    id_mov_lider = r.id
        externo = usuario_es_grupo_externos(db, current_user, empresa_id)
        return [
            {
                "id": str(r.id),
                "etapa_anterior": r.etapa_anterior,
                "etapa_nueva": r.etapa_nueva,
                "estado_nuevo": r.estado_nuevo,
                "descripcion": None if externo else r.descripcion,
                "motivo_descarte": None if externo else r.motivo_descarte,
                "usuario": None if externo else r.usuario,
                "created_at": r.created_at,
                "pretension_salarial_bruta_ars": None if externo else (pretension if r.id == id_mov_lider else None),
            }
            for r in registros
        ]

    # ---- archivos adjuntos de etapa --------------------------------------------------------------------------------------

    # El modal «Mover etapa» sube el adjunto justo después del cambio de etapa, que ya cerró la búsqueda como Ganada
    VENTANA_ADJUNTO_INGRESO = timedelta(minutes=10)

    @staticmethod
    def _validar_adjunto_ingreso(
        db: Session,
        empresa_id: uuid.UUID,
        solicitud: Solicitud,
        candidato: Candidato,
        etapa_id: Optional[str],
        usuario: Optional[str],
    ) -> None:
        """Búsqueda Ganada: el único adjunto admitido es el del movimiento a Ingreso que la cerró (de la etapa Ingreso,
        del candidato que ingresó, del mismo usuario, dentro de la ventana y sin otro adjunto de Ingreso). Si no, 409."""
        rechazo = HTTPException(status_code=409, detail=OportunidadService.MENSAJE_BUSQUEDA_GANADA)
        if PipelineService.normalizar_nombre_etapa(etapa_id) != "Ingreso":
            raise rechazo
        movimiento = (
            db.query(HistorialPipeline)
            .filter(
                HistorialPipeline.empresa_id == empresa_id,
                HistorialPipeline.oportunidad_id == solicitud.id,
                HistorialPipeline.candidato_id == candidato.id,
            )
            .order_by(HistorialPipeline.created_at.desc())
            .first()
        )
        if (
            not movimiento
            or PipelineService.normalizar_nombre_etapa(movimiento.etapa_nueva) != "Ingreso"
            or (movimiento.usuario or "") != (usuario or "")
            or utc_now() - movimiento.created_at > PipelineService.VENTANA_ADJUNTO_INGRESO
        ):
            raise rechazo
        previos = (
            db.query(EtapaArchivo.etapa_id)
            .filter(
                EtapaArchivo.empresa_id == empresa_id,
                EtapaArchivo.busqueda_id == solicitud.id,
                EtapaArchivo.candidato_id == candidato.id,
            )
            .all()
        )
        if any(PipelineService.normalizar_nombre_etapa(e) == "Ingreso" for (e,) in previos):
            raise rechazo

    @staticmethod
    async def guardar_archivo_etapa(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        etapa_id: str,
        archivo: UploadFile,
        estado: Optional[str] = None,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> EtapaArchivo:
        """Guarda un adjunto de la combinación búsqueda + candidato + etapa (hasta 10 MB; PDF, Word, imágenes, Excel,
        texto y comprimidos)."""
        from backend.core.storage import cloud_storage

        if not archivo or not archivo.filename:
            raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo.")
        OportunidadService.exigir_no_externo(
            db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no pueden adjuntar archivos a una etapa"
        )
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        candidato = CandidatoService.validar_operable(db, empresa_id, str(candidato_id), current_user=current_user)
        # Antes de leer o subir nada: en una búsqueda Ganada solo se acepta el adjunto del movimiento a Ingreso
        if OportunidadService.es_ganada(solicitud):
            PipelineService._validar_adjunto_ingreso(db, empresa_id, solicitud, candidato, etapa_id, usuario)

        nombre_original = os.path.basename(archivo.filename.strip())
        _, ext = os.path.splitext(nombre_original.lower())
        if ext not in EXTENSIONES_ADJUNTO:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de archivo no permitido ({ext}). Extensiones permitidas: PDF, DOC, DOCX, PNG, JPG, "
                "XLSX, TXT, ZIP, RAR.",
            )
        contenido = await archivo.read()
        if len(contenido) > MAX_BYTES_ADJUNTO:
            raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo permitido de 10 MB.")

        tipo_archivo = archivo.content_type or "application/octet-stream"
        archivo_id = uuid.uuid4()
        clave = f"recruiting/cv/etapa_{archivo_id}{ext}"
        cloud_storage.upload(clave, contenido, tipo_archivo)

        nuevo = EtapaArchivo(
            id=archivo_id,
            empresa_id=empresa_id,
            busqueda_id=solicitud.id,
            candidato_id=candidato.id,
            etapa_id=etapa_id.strip() if etapa_id else "Candidato",
            estado=estado.strip() if estado else None,
            nombre_archivo=nombre_original,
            tipo_archivo=tipo_archivo,
            tamano=len(contenido),
            ruta_archivo=clave,
            created_by=usuario,
            created_at=utc_now(),
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo

    @staticmethod
    def listar_archivos_etapa(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        etapa_id: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> List[EtapaArchivo]:
        """Adjuntos de una búsqueda y un candidato (el grupo EXTERNOS no los ve)."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        candidato = CandidatoService.get_by_id(db, empresa_id, str(candidato_id), current_user=current_user)
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            return []
        query = db.query(EtapaArchivo).filter(
            EtapaArchivo.empresa_id == empresa_id,
            EtapaArchivo.busqueda_id == solicitud.id,
            EtapaArchivo.candidato_id == candidato.id,
        )
        if etapa_id and etapa_id.strip():
            query = query.filter(EtapaArchivo.etapa_id == etapa_id.strip())
        return query.order_by(EtapaArchivo.created_at.desc()).all()

    @staticmethod
    def obtener_archivo_etapa(
        db: Session, empresa_id: uuid.UUID, archivo_id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> EtapaArchivo:
        """Un adjunto de la empresa activa (404 si no existe); 403 para el grupo EXTERNOS."""
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(
                status_code=403, detail="Los usuarios del grupo EXTERNOS no tienen acceso a archivos adjuntos de etapas"
            )
        archivo = (
            db.query(EtapaArchivo)
            .filter(EtapaArchivo.id == archivo_id, EtapaArchivo.empresa_id == empresa_id)
            .first()
        )
        if not archivo:
            raise HTTPException(status_code=404, detail="Archivo adjunto no encontrado o sin permisos.")
        OportunidadService.get_by_id(db, empresa_id, archivo.busqueda_id, current_user=current_user)
        CandidatoService.get_by_id(db, empresa_id, str(archivo.candidato_id), current_user=current_user)
        return archivo

    @staticmethod
    def descargar_archivo_etapa(archivo: EtapaArchivo) -> bytes:
        from backend.core.storage import cloud_storage

        try:
            return cloud_storage.download(archivo.ruta_archivo)
        except Exception:
            raise HTTPException(status_code=404, detail="No se pudo descargar el archivo del almacenamiento.")


class MotivoDescarteService:
    """Catálogo de motivos de descarte y su relación con las etapas del workflow."""

    # Etapa cuyos motivos se usan cuando la etapa del candidato no tiene motivos propios
    ETAPA_FALLBACK = "SCREENING"

    @staticmethod
    def _clave_etapa(db: Session, etapa: Optional[str]) -> str:
        clave = PipelineService.etapa_clave(etapa)
        tiene_motivos = (
            db.query(RecruitingMotivoDescarteEtapa.motivo_id)
            .join(RecruitingEtapa, RecruitingEtapa.id == RecruitingMotivoDescarteEtapa.etapa_id)
            .filter(RecruitingEtapa.nombre == clave)
            .first()
        )
        return clave if tiene_motivos else MotivoDescarteService.ETAPA_FALLBACK

    @staticmethod
    def _consulta(db: Session, etapa: Optional[str]):
        clave = MotivoDescarteService._clave_etapa(db, etapa)
        return (
            db.query(RecruitingMotivoDescarte)
            .join(
                RecruitingMotivoDescarteEtapa, RecruitingMotivoDescarteEtapa.motivo_id == RecruitingMotivoDescarte.id
            )
            .join(RecruitingEtapa, RecruitingEtapa.id == RecruitingMotivoDescarteEtapa.etapa_id)
            .filter(RecruitingEtapa.nombre == clave)
        )

    @staticmethod
    def listar(db: Session, etapa: Optional[str]) -> List[RecruitingMotivoDescarte]:
        """Motivos de la etapa indicada, en su orden de presentación."""
        return (
            MotivoDescarteService._consulta(db, etapa)
            .order_by(RecruitingMotivoDescarteEtapa.orden.asc(), RecruitingMotivoDescarte.id.asc())
            .all()
        )

    @staticmethod
    def existe_motivo_en_etapa(db: Session, motivo: str, etapa: Optional[str]) -> bool:
        return (
            MotivoDescarteService._consulta(db, etapa).filter(RecruitingMotivoDescarte.motivo == motivo).first()
            is not None
        )


class PostulacionService:
    """Postulaciones del candidato (recruiting_postulaciones): consulta, rechazo, historial y búsquedas elegibles."""

    @staticmethod
    def de_candidato(
        db: Session, empresa_id: uuid.UUID, candidato_id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> List[Postulacion]:
        """Postulaciones vigentes del candidato. El grupo EXTERNOS solo ve las de las búsquedas que tiene asignadas."""
        candidato = CandidatoService.get_by_id(db, empresa_id, str(candidato_id), current_user=current_user)
        query = db.query(Postulacion).filter(
            Postulacion.empresa_id == empresa_id,
            Postulacion.candidato_id == candidato.id,
            Postulacion.deleted_at.is_(None),
        )
        if current_user and usuario_es_grupo_externos(db, current_user, empresa_id):
            query = query.filter(
                Postulacion.solicitud_id.in_(
                    db.query(Solicitud.id).filter(
                        Solicitud.empresa_id == empresa_id, Solicitud.externo_id == current_user.id
                    )
                )
            )
        return query.order_by(Postulacion.created_at.desc()).all()

    @staticmethod
    def rechazar(
        db: Session,
        empresa_id: uuid.UUID,
        postulacion_id: uuid.UUID,
        datos: RechazoPostulacionRequest,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Postulacion:
        """Rechaza la participación del candidato en una búsqueda: motivo obligatorio, observaciones y traza en
        recruiting_transiciones_estado. Una postulación de una búsqueda Ganada no admite cambios (409)."""
        motivo = (datos.motivo_rechazo or "").strip()
        if not motivo:
            raise HTTPException(status_code=422, detail="El motivo de rechazo es obligatorio")
        postulacion = (
            db.query(Postulacion)
            .filter(
                Postulacion.id == postulacion_id,
                Postulacion.empresa_id == empresa_id,
                Postulacion.deleted_at.is_(None),
            )
            .first()
        )
        if not postulacion:
            raise HTTPException(status_code=404, detail="Postulación no encontrada")
        CandidatoService.get_by_id(db, empresa_id, str(postulacion.candidato_id), current_user=current_user)
        if postulacion.solicitud_id:
            solicitud = (
                db.query(Solicitud)
                .filter(Solicitud.id == postulacion.solicitud_id, Solicitud.empresa_id == empresa_id)
                .first()
            )
            if solicitud:
                OportunidadService.validar_no_ganada(solicitud)

        ahora = utc_now()
        estado_anterior = postulacion.estado
        postulacion.estado = "Rechazado"
        postulacion.etapa = "Rechazado"
        postulacion.motivo_rechazo = motivo
        postulacion.observaciones = (datos.observaciones or "").strip() or None
        postulacion.updated_at = ahora
        postulacion.updated_by = usuario
        db.add(
            TransicionEstado(
                empresa_id=empresa_id,
                candidato_id=postulacion.candidato_id,
                postulacion_id=postulacion.id,
                estado_anterior=estado_anterior,
                estado_nuevo="Rechazado",
                motivo_rechazo=motivo,
                observaciones=postulacion.observaciones,
                usuario=usuario,
                created_at=ahora,
            )
        )
        db.commit()
        db.refresh(postulacion)
        return postulacion

    @staticmethod
    def historial_de_candidato(
        db: Session, empresa_id: uuid.UUID, candidato_id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> List[TransicionEstado]:
        """Cambios de estado de las postulaciones del candidato, del más reciente al más antiguo."""
        candidato = CandidatoService.get_by_id(db, empresa_id, str(candidato_id), current_user=current_user)
        return (
            db.query(TransicionEstado)
            .filter(TransicionEstado.empresa_id == empresa_id, TransicionEstado.candidato_id == candidato.id)
            .order_by(TransicionEstado.created_at.desc())
            .all()
        )

    # ---- búsquedas elegibles (Smart Matching desde el candidato) -------------------------------------------------------

    @staticmethod
    def _skills_requeridas(solicitud: Solicitud) -> List[str]:
        return [s.strip() for s in lista_de_textos(solicitud.skills) if s.strip()]

    @staticmethod
    def calcular_match_skills(candidato: Candidato, solicitud: Solicitud) -> tuple[int, List[str], List[str]]:
        """Porcentaje de las skills requeridas de la búsqueda que tiene el candidato, sus coincidentes y las requeridas.
        Una búsqueda sin skills da 0 %."""
        requeridas = PostulacionService._skills_requeridas(solicitud)
        if not requeridas:
            return 0, [], []
        del_candidato = {s.strip().lower(): s.strip() for s in lista_de_textos(candidato.skills) if s.strip()}
        coincidentes = []
        for req in requeridas:
            for clave in del_candidato:
                if req.lower() == clave or req.lower() in clave or clave in req.lower():
                    coincidentes.append(del_candidato[clave])
                    break
        return int(len(coincidentes) / len(requeridas) * 100), coincidentes, requeridas

    @staticmethod
    def _nivel_seniority(valor: Optional[str]) -> str:
        if not valor:
            return "senior"
        v = str(valor).strip().lower()
        if "trainee" in v or "pasante" in v:
            return "trainee"
        if "junior" in v or "jr" in v:
            return "junior"
        if "semi" in v or "ssr" in v:
            return "semi senior"
        if any(p in v for p in ("lead", "líder", "lider", "architect", "arquitecto", "principal", "manager")):
            return "lead"
        return "senior"

    @staticmethod
    def compatibilidad_seniority(del_candidato: Optional[str], de_la_busqueda: Optional[str]) -> tuple[int, bool]:
        """Mismo nivel 100 %, adyacente 75 %, a dos niveles 45 %, más lejos 20 % (no compatible)."""
        jerarquia = {"trainee": 1, "junior": 2, "semi senior": 3, "senior": 4, "lead": 5}
        diferencia = abs(
            jerarquia[PostulacionService._nivel_seniority(del_candidato)]
            - jerarquia[PostulacionService._nivel_seniority(de_la_busqueda)]
        )
        if diferencia == 0:
            return 100, True
        if diferencia == 1:
            return 75, True
        if diferencia == 2:
            return 45, True
        return 20, False

    @staticmethod
    def busquedas_elegibles(
        db: Session, empresa_id: uuid.UUID, candidato_id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> List[Dict[str, Any]]:
        """Búsquedas Abiertas a las que el candidato todavía no está asignado y con las que es compatible: skills (70 %)
        y seniority (30 %); sin skills en la búsqueda decide el seniority. 403 para el grupo EXTERNOS."""
        OportunidadService.exigir_no_externo(
            db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no tienen acceso a Smart Matching"
        )
        candidato = CandidatoService.get_by_id(db, empresa_id, str(candidato_id), current_user=current_user)
        config = db.query(RecrutingConfig).filter(RecrutingConfig.empresa_id == empresa_id).first()
        minimo = config.match_minimo_porcentaje if config else 50

        asignadas = {
            fila[0]
            for fila in db.query(Postulacion.solicitud_id).filter(
                Postulacion.empresa_id == empresa_id,
                Postulacion.candidato_id == candidato.id,
                Postulacion.deleted_at.is_(None),
            )
        } | {
            fila[0]
            for fila in db.query(GestionBusqueda.oportunidad_id).filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.candidato_id == candidato.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
            )
        }
        abiertas = (
            db.query(Solicitud)
            .filter(
                Solicitud.empresa_id == empresa_id,
                Solicitud.activo.is_(True),
                Solicitud.deleted_at.is_(None),
                func.lower(Solicitud.estado) == "abierta",
            )
            .order_by(Solicitud.created_at.desc())
            .all()
        )
        elegibles = []
        for b in abiertas:
            if b.id in asignadas:
                continue
            skills_pct, coincidentes, requeridas = PostulacionService.calcular_match_skills(candidato, b)
            sen_pct, sen_ok = PostulacionService.compatibilidad_seniority(candidato.seniority, b.seniority)
            if not requeridas:
                total = sen_pct
                es_elegible = sen_ok and total >= min(minimo, 45)
            else:
                total = int(round(skills_pct * 0.70 + sen_pct * 0.30))
                es_elegible = (
                    total >= minimo
                    or skills_pct >= minimo
                    or (len(coincidentes) > 0 and sen_pct >= 75 and total >= 40)
                )
            if es_elegible:
                elegibles.append(
                    {
                        "id": str(b.id),
                        "id_busqueda": b.id_busqueda or str(b.id)[:8],
                        "titulo": b.titulo,
                        "cliente": b.cliente,
                        "seniority": b.seniority or "Senior",
                        "modalidad": b.modalidad or "Remoto",
                        "estado": b.estado,
                        "skills": requeridas,
                        "skills_coincidentes": coincidentes,
                        "porcentaje_match": total,
                        "match_porcentaje": total,
                        "match_skills": skills_pct,
                        "match_seniority": sen_pct,
                        "seniority_compatible": sen_ok,
                    }
                )
        elegibles.sort(key=lambda e: -e["porcentaje_match"])
        return elegibles


class AltaEnBusquedaService:
    """Alta de candidatos desde una búsqueda asignada: solo el grupo EXTERNOS, y solo sobre una búsqueda que tiene
    asignada. Crea la ficha con el usuario como dueño y la asocia a la búsqueda."""

    @staticmethod
    def _busqueda_asignada(
        db: Session, empresa_id: uuid.UUID, oportunidad_id: uuid.UUID, current_user: Optional[Usuario]
    ) -> Solicitud:
        if not usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(
                status_code=403,
                detail="Solo los usuarios del grupo EXTERNOS pueden cargar candidatos desde una búsqueda asignada",
            )
        # get_by_id valida la asignación (403 si no es suya); antes de crear nada, una Ganada no admite candidatos
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)
        return solicitud

    @staticmethod
    def _gestion(db: Session, empresa_id: uuid.UUID, solicitud: Solicitud, candidato_id: uuid.UUID):
        return (
            db.query(GestionBusqueda)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.candidato_id == candidato_id,
                GestionBusqueda.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def _asociar(
        db: Session,
        empresa_id: uuid.UUID,
        solicitud: Solicitud,
        candidato_id: uuid.UUID,
        current_user: Optional[Usuario],
        dar_de_baja_si_falla: bool = False,
    ) -> GestionBusqueda:
        """Asocia el candidato a la búsqueda (sin duplicar si ya estaba). Si falla y la ficha se creó en esta operación,
        la da de baja (baja lógica) para no dejarla huérfana."""
        existente = AltaEnBusquedaService._gestion(db, empresa_id, solicitud, candidato_id)
        if existente:
            return existente
        try:
            CandidatosDeBusquedaService.asignar(
                db,
                empresa_id,
                solicitud.id,
                AsignarCandidatoRequest(candidato_id=candidato_id),
                usuario=getattr(current_user, "email", None),
                current_user=current_user,
                desde_busqueda_asignada=True,
            )
        except Exception:
            db.rollback()
            if dar_de_baja_si_falla:
                db.query(Candidato).filter(Candidato.id == candidato_id).update(
                    {Candidato.deleted_at: utc_now()}, synchronize_session=False
                )
                db.commit()
            raise
        return AltaEnBusquedaService._gestion(db, empresa_id, solicitud, candidato_id)

    @staticmethod
    async def cargar_cv(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        archivo: UploadFile,
        current_user: Optional[Usuario] = None,
        actualizar_existente: bool = False,
    ) -> Tuple[Candidato, GestionBusqueda, str]:
        """Carga un CV desde la búsqueda asignada. El tercer valor es el resultado: "creado", "identico" o "derivado".

        - Email existente con CV idéntico: asocia la ficha existente a la búsqueda, sin caso ni aviso.
        - Email existente con CV distinto: la asocia, guarda el CV nuevo en un almacenamiento temporal, registra el caso
          pendiente y avisa al grupo Recruiting (CandidatoDuplicadoService).
        - `actualizar_existente`: reemplaza el CV y los datos de la ficha existente y la asocia a la búsqueda.
        """
        solicitud = AltaEnBusquedaService._busqueda_asignada(db, empresa_id, oportunidad_id, current_user)
        contenido = await archivo.read() if archivo else b""
        if archivo:
            await archivo.seek(0)
        try:
            candidato = await CandidatoService.crear_desde_cv(
                db=db,
                empresa_id=empresa_id,
                archivo=archivo,
                usuario=getattr(current_user, "email", None),
                current_user=current_user,
                modo_duplicado="actualizar" if actualizar_existente else "comparar",
            )
        except CVDuplicadoDistintoError as e:
            candidato = db.query(Candidato).filter(Candidato.id == e.candidato_id, Candidato.empresa_id == empresa_id).one()
            registro = AltaEnBusquedaService._asociar(db, empresa_id, solicitud, candidato.id, current_user)
            CandidatoDuplicadoService.registrar_caso(
                db, empresa_id, solicitud, candidato, current_user, contenido, archivo.filename, e.nuevo
            )
            return candidato, registro, "derivado"
        except CVEmailDuplicadoError as e:
            if not e.candidato_id:
                raise
            candidato = db.query(Candidato).filter(Candidato.id == e.candidato_id, Candidato.empresa_id == empresa_id).one()
            registro = AltaEnBusquedaService._asociar(db, empresa_id, solicitud, candidato.id, current_user)
            return candidato, registro, "identico"
        except CVPersistenciaError as e:
            logging.getLogger(__name__).error(
                f"Error de persistencia al guardar el candidato del CV: {e.causa}", exc_info=e.causa
            )
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        # Con «actualizar» la ficha puede ser de otro usuario: el acceso ya se validó sobre la búsqueda asignada
        registro = AltaEnBusquedaService._asociar(
            db, empresa_id, solicitud, candidato.id, current_user, dar_de_baja_si_falla=not actualizar_existente
        )
        return candidato, registro, "creado"

    @staticmethod
    def crear_candidato(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        datos: CandidatoCreate,
        current_user: Optional[Usuario] = None,
    ) -> Tuple[Candidato, GestionBusqueda]:
        """Alta manual desde la búsqueda asignada: la ficha queda a nombre del usuario y asociada a la búsqueda. Si el
        email ya era un candidato propio no se da de baja al fallar la asociación."""
        solicitud = AltaEnBusquedaService._busqueda_asignada(db, empresa_id, oportunidad_id, current_user)
        preexistente = (
            db.query(Candidato.id)
            .filter(
                Candidato.empresa_id == empresa_id,
                Candidato.email.ilike(datos.email.strip().lower()),
                Candidato.deleted_at.is_(None),
            )
            .first()
            is not None
        )
        candidato = CandidatoService.create(
            db=db,
            empresa_id=empresa_id,
            datos=datos,
            usuario=getattr(current_user, "email", None),
            current_user=current_user,
        )
        registro = AltaEnBusquedaService._asociar(
            db, empresa_id, solicitud, candidato.id, current_user, dar_de_baja_si_falla=not preexistente
        )
        return candidato, registro


class CandidatoDuplicadoService:
    """Casos de CV duplicado (mismo email, archivo distinto) cargados por usuarios EXTERNOS y pendientes de revisión
    interna: el candidato ya está asociado a la búsqueda y el CV nuevo espera en un almacenamiento temporal."""

    CARPETA_TEMP = "recruiting/cv_duplicados"
    MENSAJE_DERIVADO = (
        "El candidato ya se encuentra registrado. El caso fue derivado al equipo interno para su evaluación."
    )

    @staticmethod
    def registrar_caso(
        db: Session,
        empresa_id: uuid.UUID,
        solicitud: Solicitud,
        candidato: Candidato,
        current_user: Optional[Usuario],
        contenido: bytes,
        nombre_archivo: str,
        datos_nuevo: Dict[str, Any],
    ) -> CandidatoDuplicado:
        """Guarda el CV nuevo en el almacenamiento temporal, registra el caso pendiente y avisa al grupo Recruiting."""
        from backend.core.storage import cloud_storage

        _, ext = os.path.splitext((nombre_archivo or "").lower())
        caso_id = uuid.uuid4()
        clave = f"{CandidatoDuplicadoService.CARPETA_TEMP}/{caso_id}{ext}"
        mime = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(ext, "application/octet-stream")
        cloud_storage.upload(clave, contenido, mime)
        caso = CandidatoDuplicado(
            id=caso_id,
            empresa_id=empresa_id,
            candidato_id=candidato.id,
            oportunidad_id=solicitud.id,
            presentado_por_id=current_user.id if current_user else None,
            cv_identico=False,
            archivo_temp_key=clave,
            nombre_archivo=(nombre_archivo or "")[:255],
            datos_nuevo=datos_nuevo,
            estado="pendiente",
        )
        try:
            db.add(caso)
            db.commit()
        except Exception:
            db.rollback()
            try:
                cloud_storage.delete(clave)
            except Exception:
                pass
            raise
        CandidatoDuplicadoService._notificar_recruiting(db, empresa_id, caso, solicitud, candidato, current_user)
        return caso

    @staticmethod
    def _notificar_recruiting(
        db: Session,
        empresa_id: uuid.UUID,
        caso: CandidatoDuplicado,
        solicitud: Solicitud,
        candidato: Candidato,
        current_user: Optional[Usuario],
    ) -> None:
        """Aviso en la campana interna, solo para los grupos de Recruiting; si falla, el caso queda registrado igual."""
        from backend.modules.notificaciones_internas.services import NotificacionInternaService

        try:
            grupo_ids = [
                str(g.id)
                for g in db.query(Grupo.id)
                .join(usuario_grupo, usuario_grupo.c.grupo_id == Grupo.id)
                .filter(
                    or_(*[Grupo.nombre.ilike(f"%{parte}%") for parte in PARTES_NOMBRE_GRUPO_RECRUITING]),
                    usuario_grupo.c.empresa_id == empresa_id,
                    Grupo.activo.is_(True),
                    Grupo.deleted_at.is_(None),
                )
                .distinct()
                .all()
            ]
            if not grupo_ids:
                return
            presentado = getattr(current_user, "nombre", None) or getattr(current_user, "email", None) or "Un usuario externo"
            NotificacionInternaService.enviar(
                db,
                empresa_id,
                titulo="CV duplicado pendiente de revisión",
                mensaje=f"{presentado} cargó un CV distinto para {candidato.nombre} {candidato.apellido} "
                f"({candidato.email}) en la búsqueda {solicitud.titulo}.",
                grupo_ids=grupo_ids,
                enlace=f"/recruiting/dashboard?duplicado={caso.id}",
                tipo="warning",
                origen="recruiting_cv_duplicado",
            )
        except Exception as e:
            db.rollback()
            logging.getLogger(__name__).warning(f"No se pudo notificar el caso de CV duplicado {caso.id}: {e}")

    @staticmethod
    def _exigir_interno(db: Session, empresa_id: uuid.UUID, current_user: Optional[Usuario]) -> None:
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(status_code=403, detail="Los usuarios externos no pueden revisar casos de CV duplicado")

    @staticmethod
    def _obtener(db: Session, empresa_id: uuid.UUID, caso_id: uuid.UUID) -> CandidatoDuplicado:
        caso = (
            db.query(CandidatoDuplicado)
            .filter(CandidatoDuplicado.id == caso_id, CandidatoDuplicado.empresa_id == empresa_id)
            .first()
        )
        if not caso:
            raise HTTPException(status_code=404, detail="Caso de CV duplicado no encontrado")
        return caso

    @staticmethod
    def _item(caso: CandidatoDuplicado) -> Dict[str, Any]:
        candidato, oportunidad, presentado = caso.candidato, caso.oportunidad, caso.presentado_por
        return {
            "id": str(caso.id),
            "fecha": caso.created_at,
            "oportunidad_id": str(caso.oportunidad_id),
            "busqueda": getattr(oportunidad, "titulo", None),
            "candidato_id": str(caso.candidato_id),
            "candidato": f"{candidato.nombre} {candidato.apellido}".strip() if candidato else None,
            "email": candidato.email if candidato else None,
            "presentado_por": (getattr(presentado, "nombre", None) or getattr(presentado, "email", None))
            if presentado
            else None,
            "estado": caso.estado,
            "resolucion": caso.resolucion,
        }

    @staticmethod
    def listar_pendientes(db: Session, empresa_id: uuid.UUID, current_user: Optional[Usuario]) -> List[Dict[str, Any]]:
        CandidatoDuplicadoService._exigir_interno(db, empresa_id, current_user)
        casos = (
            db.query(CandidatoDuplicado)
            .filter(CandidatoDuplicado.empresa_id == empresa_id, CandidatoDuplicado.estado == "pendiente")
            .order_by(CandidatoDuplicado.created_at.desc())
            .all()
        )
        return [CandidatoDuplicadoService._item(c) for c in casos]

    @staticmethod
    def obtener_detalle(
        db: Session, empresa_id: uuid.UUID, caso_id: uuid.UUID, current_user: Optional[Usuario]
    ) -> Dict[str, Any]:
        """El caso con el resumen del CV actual y del nuevo, para compararlos lado a lado."""
        CandidatoDuplicadoService._exigir_interno(db, empresa_id, current_user)
        caso = CandidatoDuplicadoService._obtener(db, empresa_id, caso_id)
        nuevo = dict(caso.datos_nuevo or {})
        nuevo["archivo"] = caso.nombre_archivo
        nuevo["cv_url"] = caso.archivo_temp_key
        return {
            **CandidatoDuplicadoService._item(caso),
            "actual": CandidatoService._resumen_comparacion_cv(caso.candidato),
            "nuevo": nuevo,
        }

    @staticmethod
    def resolver(
        db: Session, empresa_id: uuid.UUID, caso_id: uuid.UUID, accion: str, current_user: Optional[Usuario]
    ) -> Dict[str, Any]:
        """«conservar» mantiene el CV actual; «actualizar» reemplaza el CV y los datos de la ficha por los del nuevo. En
        ambos casos el candidato queda asociado a la búsqueda (sin duplicar la asociación) y el temporal se elimina."""
        from backend.core.storage import cloud_storage

        CandidatoDuplicadoService._exigir_interno(db, empresa_id, current_user)
        if accion not in ("conservar", "actualizar"):
            raise HTTPException(status_code=422, detail="Acción no válida")
        caso = CandidatoDuplicadoService._obtener(db, empresa_id, caso_id)
        if caso.estado != "pendiente":
            raise HTTPException(status_code=409, detail="El caso ya fue resuelto")
        candidato = caso.candidato
        usuario = getattr(current_user, "email", None)
        if accion == "actualizar":
            if not caso.archivo_temp_key:
                raise HTTPException(status_code=409, detail="El CV nuevo ya no está disponible")
            try:
                contenido = cloud_storage.download(caso.archivo_temp_key)
            except Exception:
                raise HTTPException(status_code=409, detail="El CV nuevo ya no está disponible")
            _, ext = os.path.splitext(caso.archivo_temp_key.lower())
            try:
                CandidatoService._actualizar_desde_cv(
                    db, candidato, dict(caso.datos_nuevo or {}), contenido, ext, usuario
                )
            except CVPersistenciaError as e:
                logging.getLogger(__name__).error(
                    f"Error de persistencia al actualizar el candidato desde un caso duplicado: {e.causa}",
                    exc_info=e.causa,
                )
                raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        solicitud = (
            db.query(Solicitud)
            .filter(Solicitud.id == caso.oportunidad_id, Solicitud.empresa_id == empresa_id)
            .first()
        )
        if solicitud:
            try:
                AltaEnBusquedaService._asociar(db, empresa_id, solicitud, candidato.id, current_user)
            except HTTPException:
                # La búsqueda pudo cerrarse (Ganada) o dejar de estar Abierta: el caso se resuelve igual
                db.rollback()
        clave = caso.archivo_temp_key
        caso.estado = "resuelto"
        caso.resolucion = accion
        caso.resuelto_por_id = current_user.id if current_user else None
        caso.resuelto_at = utc_now()
        caso.archivo_temp_key = None
        db.commit()
        if clave:
            try:
                cloud_storage.delete(clave)
            except Exception:
                pass
        return {"ok": True, "resolucion": accion, "candidato_id": str(candidato.id)}
