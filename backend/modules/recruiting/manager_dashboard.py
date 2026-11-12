"""Manager Dashboard de Recruiting: análisis de desempeño de usuarios EXTERNOS (solo administradores).

Port de ManagerDashboardService del módulo original (modulo-recluiter, backend/modules/recruiting/services.py).
Mismas reglas y cálculos; lo único que cambia es el acceso: allá era el email admin@admin.com, acá es el rol "admin"
del Core, que el router exige con require_admin.
"""

import statistics
import unicodedata
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.recruiting.models import Candidato, GestionBusqueda, HistorialPipeline, Solicitud
from backend.modules.recruiting.schemas import ManagerDashboardFiltros
from backend.modules.recruiting.services import es_grupo_externos
from backend.modules.usuarios.models import Usuario

# Orden real del pipeline, de Candidato a Ingreso; Descartados queda aparte
ETAPAS_PIPELINE = (
    "Candidato",
    "Screening",
    "Entrevista RRHH",
    "Entrevista Líder Dicsys",
    "Validación Administración",
    "Entrevista Cliente",
    "Oferta",
    "Examen Médico Preocupacional",
    "Ingreso",
)
ETAPA_DESCARTE = "Descartados"


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto.upper())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar_etapa(etapa: str | None) -> str:
    """Nombre canónico de una etapa (GestionBusquedaService.normalizar_nombre_etapa del original)."""
    if not etapa:
        return "Candidato"
    valor = etapa.strip()
    mayus = _sin_tildes(valor)
    if mayus in ("DESCARTADO", "DESCARTADOS"):
        return ETAPA_DESCARTE
    if mayus in ("CANDIDATO", "POSTULADO", "COORDINANDO ENTREVISTA"):
        return "Candidato"
    if mayus == "SCREENING":
        return "Screening"
    if "RRHH" in mayus:
        return "Entrevista RRHH"
    if "LIDER" in mayus or "TECNICA" in mayus:
        return "Entrevista Líder Dicsys"
    if "ADMINISTRACION" in mayus:
        return "Validación Administración"
    if "EXAMEN" in mayus or "PREOCUPACIONAL" in mayus:
        return "Examen Médico Preocupacional"
    if "CLIENTE" in mayus:
        return "Entrevista Cliente"
    if "OFERTA" in mayus:
        return "Oferta"
    if "INGRESO" in mayus:
        return "Ingreso"
    return valor


class ManagerDashboardService:
    """
    Indicadores del desempeño de los usuarios EXTERNOS (Freelance y Consultoras).

    Unidad de análisis: la postulación (fila de recruiting_gestionBusqueda: un candidato en una búsqueda).
    Se considera presentada por un externo cuando la búsqueda está asignada a él (externo_id) y el candidato
    lo creó él mismo (creador_id); los candidatos que carga el equipo interno en esas búsquedas no le cuentan.
    Fecha de filtro de TODAS las métricas: fecha de presentación (created_at de la postulación); cada indicador
    es una cohorte de lo presentado en el período. El recorrido sale de recruiting_historial_pipeline y de la
    etapa actual de la postulación, sin inferir pasos que no estén registrados.
    """

    ETAPAS = list(ETAPAS_PIPELINE)
    ETAPA_INICIAL = ETAPAS[0]
    ETAPAS_ENTREVISTA = frozenset({ETAPAS[2], ETAPAS[3], ETAPAS[5]})
    ETAPAS_FINALES = frozenset({ETAPAS[6], ETAPAS[7], ETAPAS[8]})  # Oferta, Examen Médico, Ingreso
    ETAPA_OFERTA = ETAPAS[6]
    ETAPA_CONTRATADO = ETAPAS[8]  # el pipeline llama "Contratados" a la etapa Ingreso
    MAX_ESTANCADOS = 200
    # El sistema no distingue Freelance de Consultora: no se infiere por nombres, todos figuran sin clasificar
    TIPO_SIN_CLASIFICAR = "Sin clasificar"

    CRITERIOS = [
        "Presentado: postulación de un candidato creado por el usuario externo en una búsqueda que tiene asignada.",
        "Fecha de filtro: fecha de presentación de la postulación; todas las métricas son cohortes de lo presentado en el período.",
        "Avanzó: la postulación alcanzó alguna etapa posterior a Candidato (según el historial y la etapa actual).",
        "Entrevista: alcanzó Entrevista RRHH, Entrevista Líder Dicsys o Entrevista Cliente.",
        "Resultado final: alcanzó Oferta, Examen Médico Preocupacional o Ingreso. Contratado: alcanzó Ingreso.",
        "Las tasas se calculan sobre postulaciones; los candidatos únicos se informan aparte para no contar dos veces a quien está en varias búsquedas.",
        "Primera revisión: tiempo entre la presentación y el primer movimiento de etapa registrado en el historial.",
        "Estancado: postulación abierta (no descartada ni en Ingreso) sin movimiento durante los días configurados.",
        "Los umbrales de las alertas son provisionales: el sistema no define objetivos. Son configurables y se muestran los valores usados.",
    ]

    NO_DISPONIBLE = [
        {
            "indicador": "Distinción Freelance / Consultora",
            "motivo": "El sistema no registra si un usuario externo es Freelance o Consultora: Usuario no tiene ese atributo y el único grupo vigente es EXTERNOS. Todos figuran como Sin clasificar y el filtro por tipo queda deshabilitado hasta que exista ese dato.",
        },
        {
            "indicador": "Duplicados detectados",
            "motivo": "Un CV o email duplicado se rechaza con un error y no queda registrado; no hay dato para contarlos.",
        },
        {
            "indicador": "Demoras atribuibles al usuario externo",
            "motivo": "No se registran fechas de acciones del externo posteriores a la carga; todas las demoras medidas corresponden al proceso interno.",
        },
        {
            "indicador": "Presentación al cliente",
            "motivo": "No existe una etapa ni un dato de presentación al cliente (ver docs de Recruiting).",
        },
    ]

    # ---- utilidades numéricas ----
    @staticmethod
    def _pct(parte: int, total: int) -> float | None:
        return round(parte * 100.0 / total, 1) if total else None

    @staticmethod
    def _estadistica(valores: list[float]) -> dict:
        if not valores:
            return {"cantidad": 0, "promedio_dias": None, "mediana_dias": None}
        return {
            "cantidad": len(valores),
            "promedio_dias": round(sum(valores) / len(valores), 1),
            "mediana_dias": round(statistics.median(valores), 1),
        }

    @staticmethod
    def _dias(desde: datetime | None, hasta: datetime | None) -> float | None:
        """Días entre dos fechas; None si el orden es incoherente (dato no confiable)."""
        if not desde or not hasta or hasta < desde:
            return None
        return (hasta - desde).total_seconds() / 86400.0

    # ---- carga de datos (3 consultas fijas, sin N+1) ----
    @staticmethod
    def _externos(db: Session, empresa_id: uuid.UUID) -> dict:
        """Usuarios externos de la empresa: grupo EXTERNOS (sin Recruiting) o con alguna búsqueda asignada."""
        grupos: dict = {}
        filas = db.execute(
            select(usuario_grupo.c.usuario_id, Grupo.nombre)
            .join(Grupo, Grupo.id == usuario_grupo.c.grupo_id)
            .where(usuario_grupo.c.empresa_id == empresa_id, Grupo.activo.is_(True), Grupo.deleted_at.is_(None))
        ).all()
        for usuario_id, nombre in filas:
            grupos.setdefault(usuario_id, []).append(nombre or "")
        ids = {uid for uid, nombres in grupos.items() if es_grupo_externos(nombres)}
        ids |= set(
            db.scalars(
                select(Solicitud.externo_id)
                .where(
                    Solicitud.empresa_id == empresa_id,
                    Solicitud.deleted_at.is_(None),
                    Solicitud.externo_id.isnot(None),
                )
                .distinct()
            ).all()
        )
        if not ids:
            return {}
        usuarios = db.scalars(select(Usuario).where(Usuario.id.in_(ids), Usuario.deleted_at.is_(None))).all()
        return {
            u.id: {
                "nombre": f"{u.nombre or ''} {u.apellido or ''}".strip() or u.email,
                "email": u.email,
                "tipo": ManagerDashboardService.TIPO_SIN_CLASIFICAR,
            }
            for u in usuarios
        }

    @staticmethod
    def _condiciones(empresa_id: uuid.UUID, f: ManagerDashboardFiltros, externo_ids: list) -> list:
        condiciones = [
            GestionBusqueda.empresa_id == empresa_id,
            GestionBusqueda.activo.is_(True),
            GestionBusqueda.deleted_at.is_(None),
            Solicitud.deleted_at.is_(None),
            Solicitud.externo_id.in_(externo_ids),
            Candidato.deleted_at.is_(None),
            Candidato.creador_id == Solicitud.externo_id,
        ]
        if f.fecha_desde:
            condiciones.append(GestionBusqueda.created_at >= datetime.combine(f.fecha_desde, datetime.min.time()))
        if f.fecha_hasta:
            condiciones.append(
                GestionBusqueda.created_at < datetime.combine(f.fecha_hasta + timedelta(days=1), datetime.min.time())
            )
        if f.oportunidad_id:
            condiciones.append(GestionBusqueda.oportunidad_id == f.oportunidad_id)
        return condiciones

    @staticmethod
    def _cargar(db: Session, empresa_id: uuid.UUID, f: ManagerDashboardFiltros, externo_ids: list):
        condiciones = ManagerDashboardService._condiciones(empresa_id, f, externo_ids)
        postulaciones = db.execute(
            select(
                GestionBusqueda.oportunidad_id,
                GestionBusqueda.candidato_id,
                GestionBusqueda.etapa_actual,
                GestionBusqueda.estado,
                GestionBusqueda.motivo_descarte,
                GestionBusqueda.fecha_cambio_etapa,
                GestionBusqueda.created_at,
                Solicitud.externo_id,
                Solicitud.titulo,
                Solicitud.id_busqueda,
                Solicitud.cliente,
                Candidato.nombre,
                Candidato.apellido,
            )
            .select_from(GestionBusqueda)
            .join(Solicitud, Solicitud.id == GestionBusqueda.oportunidad_id)
            .join(Candidato, Candidato.id == GestionBusqueda.candidato_id)
            .where(*condiciones)
        ).all()
        historial = db.execute(
            select(
                HistorialPipeline.oportunidad_id,
                HistorialPipeline.candidato_id,
                HistorialPipeline.etapa_anterior,
                HistorialPipeline.etapa_nueva,
                HistorialPipeline.created_at,
            )
            .select_from(HistorialPipeline)
            .join(
                GestionBusqueda,
                and_(
                    GestionBusqueda.oportunidad_id == HistorialPipeline.oportunidad_id,
                    GestionBusqueda.candidato_id == HistorialPipeline.candidato_id,
                ),
            )
            .join(Solicitud, Solicitud.id == GestionBusqueda.oportunidad_id)
            .join(Candidato, Candidato.id == GestionBusqueda.candidato_id)
            .where(HistorialPipeline.empresa_id == empresa_id, *condiciones)
            .order_by(HistorialPipeline.created_at)
        ).all()
        por_par: dict = {}
        for h in historial:
            por_par.setdefault((h.oportunidad_id, h.candidato_id), []).append(h)
        return postulaciones, por_par

    # ---- análisis de cada postulación ----
    @staticmethod
    def _analizar(p, historial: list, ahora: datetime, dias_estancado: int) -> dict:
        S = ManagerDashboardService
        actual = normalizar_etapa(p.etapa_actual)
        descartado = actual == ETAPA_DESCARTE or (p.estado or "").strip().lower() == "descartado"
        movimientos = [
            (
                normalizar_etapa(h.etapa_anterior) if h.etapa_anterior else None,
                normalizar_etapa(h.etapa_nueva),
                h.created_at,
            )
            for h in historial
        ]
        visitadas = {m[1] for m in movimientos} | {actual}
        visitadas.discard(ETAPA_DESCARTE)
        visitadas.add(S.ETAPA_INICIAL)
        avanzo = any(e != S.ETAPA_INICIAL for e in visitadas)

        revision = None
        revision_sin_fecha = False
        transiciones = []
        previo_fecha, previo_etapa = p.created_at, S.ETAPA_INICIAL
        for i, (anterior, nueva, fecha) in enumerate(movimientos):
            if i == 0 and nueva != S.ETAPA_INICIAL:
                revision = S._dias(p.created_at, fecha)
                revision_sin_fecha = revision is None
            dias = S._dias(previo_fecha, fecha)
            if dias is not None:
                transiciones.append(((anterior or previo_etapa), nueva, dias))
            previo_fecha, previo_etapa = fecha, nueva

        def hasta(predicado):
            primero = next((m for m in movimientos if predicado(m[1])), None)
            return S._dias(p.created_at, primero[2]) if primero else None

        referencia = p.fecha_cambio_etapa or (movimientos[-1][2] if movimientos else None) or p.created_at
        sin_movimiento = max(0, int((ahora - referencia).total_seconds() // 86400)) if referencia else 0
        abierta = not descartado and actual != S.ETAPA_CONTRATADO
        return {
            "externo_id": p.externo_id,
            "oportunidad_id": p.oportunidad_id,
            "busqueda": p.titulo,
            "codigo": p.id_busqueda,
            "cliente": p.cliente,
            "candidato_id": p.candidato_id,
            "candidato": f"{p.nombre} {p.apellido or ''}".strip(),
            "etapa_actual": actual,
            "descartado": descartado,
            "motivo": (p.motivo_descarte or "").strip() or None,
            "visitadas": visitadas,
            "avanzo": avanzo,
            "entrevista": bool(visitadas & S.ETAPAS_ENTREVISTA),
            "final": bool(visitadas & S.ETAPAS_FINALES),
            "contratado": S.ETAPA_CONTRATADO in visitadas,
            "presentado_en": p.created_at,
            "revision": revision,
            "revision_sin_fecha": revision_sin_fecha,
            "transiciones": transiciones,
            "hasta_descarte": hasta(lambda e: e == ETAPA_DESCARTE),
            "hasta_oferta": hasta(lambda e: e == S.ETAPA_OFERTA),
            "hasta_ingreso": hasta(lambda e: e == S.ETAPA_CONTRATADO),
            "dias_sin_movimiento": sin_movimiento,
            "estancado": abierta and sin_movimiento >= dias_estancado,
        }

    @staticmethod
    def _periodo(fecha: datetime, semanal: bool) -> str:
        dia = fecha.date()
        if semanal:
            dia = dia - timedelta(days=dia.weekday())
        return dia.isoformat()

    @staticmethod
    def _resumir(pares: list, semanal: bool) -> dict:
        S = ManagerDashboardService
        n = len(pares)
        avanzaron = sum(1 for p in pares if p["avanzo"])
        entrevista = sum(1 for p in pares if p["entrevista"])
        finales = sum(1 for p in pares if p["final"])
        contratados = sum(1 for p in pares if p["contratado"])
        descartados = sum(1 for p in pares if p["descartado"])
        embudo = [{"etapa": etapa, "cantidad": sum(1 for p in pares if etapa in p["visitadas"])} for etapa in S.ETAPAS]
        for e in embudo:
            e["porcentaje"] = S._pct(e["cantidad"], n)
        motivos: dict = {}
        for p in pares:
            if p["descartado"] and p["motivo"]:
                motivos[p["motivo"]] = motivos.get(p["motivo"], 0) + 1
        evolucion: dict = {}
        for p in pares:
            punto = evolucion.setdefault(S._periodo(p["presentado_en"], semanal), [0, 0])
            punto[0] += 1
            punto[1] += 1 if p["avanzo"] else 0
        return {
            "candidatos_unicos": len({p["candidato_id"] for p in pares}),
            "postulaciones": n,
            "avanzaron": avanzaron,
            "tasa_avance": S._pct(avanzaron, n),
            "entrevista": entrevista,
            "tasa_entrevista": S._pct(entrevista, n),
            "finales": finales,
            "tasa_finales": S._pct(finales, n),
            "contratados": contratados,
            "tasa_contratados": S._pct(contratados, n),
            "descartados": descartados,
            "tasa_descartados": S._pct(descartados, n),
            "revision": S._estadistica([p["revision"] for p in pares if p["revision"] is not None]),
            "estancados": sum(1 for p in pares if p["estancado"]),
            "embudo": embudo,
            "motivos_descarte": [
                {"motivo": m, "cantidad": c} for m, c in sorted(motivos.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "evolucion": [{"periodo": k, "presentados": v[0], "avanzaron": v[1]} for k, v in sorted(evolucion.items())],
        }

    @staticmethod
    def _por_busqueda(pares: list) -> list:
        agrupado: dict = {}
        for p in pares:
            fila = agrupado.setdefault(
                p["oportunidad_id"],
                {
                    "oportunidad_id": p["oportunidad_id"],
                    "titulo": p["busqueda"],
                    "codigo": p["codigo"],
                    "cliente": p["cliente"],
                    "presentados": 0,
                    "avanzaron": 0,
                    "entrevista": 0,
                    "finales": 0,
                    "contratados": 0,
                    "descartados": 0,
                },
            )
            fila["presentados"] += 1
            fila["avanzaron"] += 1 if p["avanzo"] else 0
            fila["entrevista"] += 1 if p["entrevista"] else 0
            fila["finales"] += 1 if p["final"] else 0
            fila["contratados"] += 1 if p["contratado"] else 0
            fila["descartados"] += 1 if p["descartado"] else 0
        return sorted(agrupado.values(), key=lambda r: (-r["presentados"], r["titulo"]))

    @staticmethod
    def _tiempos(pares: list, nombres: dict) -> dict:
        S = ManagerDashboardService
        por_transicion: dict = {}
        for p in pares:
            for desde, hasta, dias in p["transiciones"]:
                por_transicion.setdefault((desde, hasta), []).append(dias)
        orden = {e: i for i, e in enumerate(S.ETAPAS + [ETAPA_DESCARTE])}
        entre_etapas = [
            {"desde": d, "hasta": h, **S._estadistica(v)}
            for (d, h), v in sorted(
                por_transicion.items(), key=lambda kv: (orden.get(kv[0][0], 99), orden.get(kv[0][1], 99))
            )
        ]
        estancados = sorted((p for p in pares if p["estancado"]), key=lambda p: -p["dias_sin_movimiento"])
        return {
            "revision": S._estadistica([p["revision"] for p in pares if p["revision"] is not None]),
            "revision_sin_fecha": sum(1 for p in pares if p["revision_sin_fecha"]),
            "entre_etapas": entre_etapas,
            "hasta_descarte": S._estadistica([p["hasta_descarte"] for p in pares if p["hasta_descarte"] is not None]),
            "hasta_oferta": S._estadistica([p["hasta_oferta"] for p in pares if p["hasta_oferta"] is not None]),
            "hasta_ingreso": S._estadistica([p["hasta_ingreso"] for p in pares if p["hasta_ingreso"] is not None]),
            "estancados": [
                {
                    "candidato_id": p["candidato_id"],
                    "candidato": p["candidato"],
                    "oportunidad_id": p["oportunidad_id"],
                    "busqueda": p["busqueda"],
                    "usuario_id": p["externo_id"],
                    "externo": nombres[p["externo_id"]]["nombre"],
                    "etapa_actual": p["etapa_actual"],
                    "dias_sin_movimiento": p["dias_sin_movimiento"],
                }
                for p in estancados[: S.MAX_ESTANCADOS]
            ],
            "atribucion": "Todas las demoras medidas corresponden al proceso interno (revisión y avance de etapas). "
            "No hay fechas de acciones del usuario externo que permitan atribuirle demoras.",
        }

    @staticmethod
    def _alertas(externos: list, f: ManagerDashboardFiltros) -> list:
        alertas = []
        for e in externos:
            base = {"usuario_id": e["usuario_id"], "externo": e["nombre"]}
            if (
                e["postulaciones"] >= f.umbral_volumen
                and e["tasa_avance"] is not None
                and e["tasa_avance"] < f.umbral_tasa_avance
            ):
                alertas.append(
                    {
                        **base,
                        "tipo": "volumen_baja_tasa",
                        "severidad": "alta",
                        "seccion": "productividad",
                        "mensaje": f"{e['postulaciones']} postulaciones con tasa de avance de {e['tasa_avance']}% (umbral {f.umbral_tasa_avance}%).",
                    }
                )
            if e["busquedas_asignadas"] > 0 and e["postulaciones"] < f.umbral_actividad:
                alertas.append(
                    {
                        **base,
                        "tipo": "actividad_reducida",
                        "severidad": "media",
                        "seccion": "productividad",
                        "mensaje": f"{e['postulaciones']} postulaciones en el período con {e['busquedas_asignadas']} búsquedas asignadas (mínimo {f.umbral_actividad}).",
                    }
                )
            if e["estancados"] > 0:
                alertas.append(
                    {
                        **base,
                        "tipo": "sin_movimiento",
                        "severidad": "media",
                        "seccion": "tiempos",
                        "mensaje": f"{e['estancados']} candidatos sin movimiento hace {f.dias_estancado} días o más.",
                    }
                )
            promedio = e["revision"]["promedio_dias"]
            if promedio is not None and promedio > f.umbral_demora_dias:
                alertas.append(
                    {
                        **base,
                        "tipo": "demora_revision",
                        "severidad": "baja",
                        "seccion": "tiempos",
                        "mensaje": f"La primera revisión de sus candidatos tarda {promedio} días en promedio (umbral {f.umbral_demora_dias}); demora del equipo interno.",
                    }
                )
        orden = {"alta": 0, "media": 1, "baja": 2}
        return sorted(alertas, key=lambda a: (orden[a["severidad"]], a["externo"]))

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, f: ManagerDashboardFiltros) -> dict:
        """El acceso (solo administradores) lo exige el router con require_admin."""
        S = ManagerDashboardService
        ahora = utc_now()
        todos = S._externos(db, empresa_id)
        visibles = {
            uid: d
            for uid, d in todos.items()
            if (f.tipo == "todos" or d["tipo"].lower() == f.tipo) and (not f.usuario_ids or uid in f.usuario_ids)
        }

        postulaciones, historial = S._cargar(db, empresa_id, f, list(visibles)) if visibles else ([], {})
        pares = [
            S._analizar(p, historial.get((p.oportunidad_id, p.candidato_id), []), ahora, f.dias_estancado)
            for p in postulaciones
        ]

        inicio = f.fecha_desde or min((p["presentado_en"].date() for p in pares), default=None)
        fin = f.fecha_hasta or max((p["presentado_en"].date() for p in pares), default=None)
        semanal = bool(inicio and fin and (fin - inicio).days > 62)

        asignadas_q = (
            select(Solicitud.externo_id, func.count(Solicitud.id))
            .where(
                Solicitud.empresa_id == empresa_id,
                Solicitud.deleted_at.is_(None),
                Solicitud.externo_id.in_(list(visibles) or [uuid.uuid4()]),
            )
            .group_by(Solicitud.externo_id)
        )
        if f.oportunidad_id:
            asignadas_q = asignadas_q.where(Solicitud.id == f.oportunidad_id)
        asignadas = dict(db.execute(asignadas_q).all())

        externos = []
        for uid, datos in visibles.items():
            propios = [p for p in pares if p["externo_id"] == uid]
            if f.oportunidad_id and not propios and not asignadas.get(uid):
                continue
            resumen = S._resumir(propios, semanal)
            cuadrante = None
            if resumen["tasa_avance"] is not None:
                alto_volumen = resumen["postulaciones"] >= f.umbral_volumen
                alta_tasa = resumen["tasa_avance"] >= f.umbral_tasa_avance
                cuadrante = (
                    ("alto" if alto_volumen else "bajo") + "_volumen_" + ("alta" if alta_tasa else "baja") + "_tasa"
                )
            externos.append(
                {
                    **resumen,
                    "usuario_id": uid,
                    "nombre": datos["nombre"],
                    "email": datos["email"],
                    "tipo": datos["tipo"],
                    "busquedas_asignadas": int(asignadas.get(uid, 0)),
                    "cuadrante": cuadrante,
                    "por_busqueda": S._por_busqueda(propios),
                }
            )
        externos.sort(key=lambda e: (-e["postulaciones"], e["nombre"]))

        return {
            "filtros": {
                "fecha_desde": f.fecha_desde,
                "fecha_hasta": f.fecha_hasta,
                "tipo": f.tipo,
                "usuario_ids": f.usuario_ids,
                "oportunidad_id": f.oportunidad_id,
            },
            "umbrales": {
                "dias_estancado": f.dias_estancado,
                "umbral_volumen": f.umbral_volumen,
                "umbral_tasa_avance": f.umbral_tasa_avance,
                "umbral_actividad": f.umbral_actividad,
                "umbral_demora_dias": f.umbral_demora_dias,
            },
            "granularidad_evolucion": "semana" if semanal else "dia",
            "criterios": S.CRITERIOS,
            "resumen": S._resumir(pares, semanal),
            "externos": externos,
            "tiempos": S._tiempos(pares, visibles),
            "alertas": S._alertas(externos, f),
            "opciones_usuarios": sorted(
                [{"id": uid, "nombre": d["nombre"], "tipo": d["tipo"]} for uid, d in todos.items()],
                key=lambda o: o["nombre"],
            ),
            "opciones_busquedas": [
                {"id": s.id, "titulo": s.titulo, "cliente": s.cliente}
                for s in db.execute(
                    select(Solicitud.id, Solicitud.titulo, Solicitud.cliente)
                    .where(
                        Solicitud.empresa_id == empresa_id,
                        Solicitud.deleted_at.is_(None),
                        Solicitud.externo_id.isnot(None),
                    )
                    .order_by(Solicitud.titulo)
                ).all()
            ],
            "no_disponible": S.NO_DISPONIBLE,
        }
