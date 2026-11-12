"""
Servicio para exportar recibos de sueldo agrupados por cliente y mes.

Cruza la tabla staging `administracion_recibos_export` (DNIs cargados desde CSV)
con `nomina_empleados` (CUIL) y `recibos_recibos` (CUIL extraído del PDF).
"""

import io
import re
import uuid
import zipfile
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.storage import cloud_storage
from backend.modules.administracion.export_recibos_models import AdministracionReciboExport
from backend.modules.nomina.models import Empleado
from backend.modules.recibos.models import LoteRecibo, Recibo


def _safe_filename(value: str) -> str:
    """Reemplaza caracteres no válidos para nombre de archivo/carpeta."""
    if not value:
        return "sin_dato"
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(value)).strip().strip(".")
    return cleaned or "sin_dato"


def _formatear_cuil(cuil) -> Optional[str]:
    """Formatea un CUIL (int o str) a XX-XXXXXXXX-X. Devuelve None si inválido."""
    if cuil is None:
        return None
    digitos = re.sub(r"\D", "", str(cuil))
    if len(digitos) != 11:
        return digitos or None
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10:]}"


# Clave sentinela para el grupo de empleados sin recibos (mismo shape que
# las claves reales (periodo, tipo_liquidacion) para poder ordenarlas juntas).
SIN_RECIBOS = (None, None)


def _archivo_y_sufijo(recibo) -> Tuple[str, str]:
    """Elige el archivo a descargar y el sufijo del nombre.

    Firmado si existe (naming sin cambios). Si no hay firmado, el DUPLICADO
    marcado como '(SIN FIRMAR)' para evitar confundirlo con uno firmado.

    El duplicado es opcional: cuando el recibo viene en una sola hoja se usa el
    original, que es el único archivo que hay. Se pregunta por el dato y no por
    el formato del lote para no tener que ramificar en cada lectura.
    """
    if recibo.archivo_firmado:
        return recibo.archivo_firmado, "firmado"
    if recibo.archivo_duplicado:
        return recibo.archivo_duplicado, "(SIN FIRMAR)"
    return recibo.archivo_original, "(SIN FIRMAR)"


class ExportRecibosService:
    """Cruza staging de DNIs con recibos de la empresa y arma exports."""

    @staticmethod
    def listar_agrupado(db: Session, empresa_id: uuid.UUID) -> Dict:
        """Devuelve estructura cliente -> (periodo, tipo_liquidacion) -> empleado -> recibos.

        Cada liquidación es un grupo propio: el SAC de un mes no se mezcla con la
        Liquidación Mensual de ese mismo mes.
        Ordena: cliente ASC, periodo DESC, tipo_liquidacion ASC, empleado por
        apellido/nombre. Métricas por grupo: total_empleados, total_recibos,
        firmados, pendientes.
        """
        staging = (
            db.query(AdministracionReciboExport)
            .order_by(
                AdministracionReciboExport.cliente.asc(),
                AdministracionReciboExport.apellido.asc(),
            )
            .all()
        )

        if not staging:
            return {"clientes": [], "total_clientes": 0, "total_empleados": 0, "total_recibos": 0}

        dnis = list({row.dni for row in staging if row.dni})

        empleados = (
            db.query(Empleado)
            .filter(
                Empleado.dni.in_(dnis),
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .all()
            if dnis
            else []
        )
        emp_por_dni = {e.dni: e for e in empleados}

        cuils = [e.cuil for e in empleados if e.cuil]

        recibos_q = (
            (
                db.query(Recibo, LoteRecibo)
                .join(LoteRecibo, Recibo.lote_id == LoteRecibo.id)
                .filter(
                    Recibo.empresa_id == empresa_id,
                    Recibo.deleted_at.is_(None),
                    LoteRecibo.deleted_at.is_(None),
                    Recibo.cuil_extraido.in_(cuils),
                )
                .order_by(LoteRecibo.periodo.desc(), Recibo.created_at.desc())
                .all()
            )
            if cuils
            else []
        )

        recibos_por_cuil: Dict[str, List[Tuple[Recibo, LoteRecibo]]] = defaultdict(list)
        for recibo, lote in recibos_q:
            recibos_por_cuil[recibo.cuil_extraido].append((recibo, lote))

        # cliente -> (periodo, tipo_liquidacion) -> [empleados]
        clientes_dict: Dict[str, Dict[Tuple, List[Dict]]] = defaultdict(lambda: defaultdict(list))
        empleados_por_cliente: Dict[str, set] = defaultdict(set)
        recibos_por_cliente: Dict[str, int] = defaultdict(int)

        for row in staging:
            cliente = row.cliente or "SIN CLIENTE"
            empleado = emp_por_dni.get(row.dni) if row.dni else None
            cuil = empleado.cuil if empleado else None
            cuil_formato = _formatear_cuil(cuil)
            recibos_emp = recibos_por_cuil.get(cuil, []) if cuil else []

            empleados_por_cliente[cliente].add(row.dni)

            # Nombre completo desde nómina si existe; fallback al staging
            if empleado:
                nombre_completo = f"{(empleado.apellido or '').strip()} {(empleado.nombre or '').strip()}".strip()
            else:
                nombre_completo = f"{(row.apellido or '').strip()} {(row.nombre or '').strip()}".strip()
            if not nombre_completo:
                nombre_completo = "-"

            if not recibos_emp:
                clientes_dict[cliente][SIN_RECIBOS].append(
                    {
                        "dni": row.dni,
                        "cuil": cuil_formato,
                        "apellido": empleado.apellido if empleado else row.apellido,
                        "nombre": empleado.nombre if empleado else row.nombre,
                        "nombre_completo": nombre_completo,
                        "colaborador": row.colaborador,
                        "empleado_id": str(empleado.id) if empleado else None,
                        "sin_empleado": empleado is None,
                        "estado": "DNI no encontrado" if empleado is None else "Sin recibos",
                        "recibos": [],
                    }
                )
                continue

            # Una entrada por (periodo, tipo_liquidacion): el SAC va aparte del mensual
            por_grupo: Dict[Tuple, List[Dict]] = defaultdict(list)
            for recibo, lote in recibos_emp:
                por_grupo[(lote.periodo, lote.tipo_liquidacion)].append(
                    {
                        "id": str(recibo.id),
                        "tipo_liquidacion": lote.tipo_liquidacion,
                        "estado": recibo.estado,
                        "firmado": bool(recibo.archivo_firmado),
                    }
                )

            for grupo, items_recibo in por_grupo.items():
                hay_firmado = any(r["firmado"] for r in items_recibo)
                clientes_dict[cliente][grupo].append(
                    {
                        "dni": row.dni,
                        "cuil": cuil_formato,
                        "apellido": empleado.apellido if empleado else row.apellido,
                        "nombre": empleado.nombre if empleado else row.nombre,
                        "nombre_completo": nombre_completo,
                        "colaborador": row.colaborador,
                        "empleado_id": str(empleado.id) if empleado else None,
                        "sin_empleado": False,
                        "estado": "Firmado" if hay_firmado else "Pendiente",
                        "recibos": items_recibo,
                    }
                )
                recibos_por_cliente[cliente] += len(items_recibo)

        clientes = []
        total_empleados = 0
        total_recibos = 0
        # Cliente ASC
        for cliente in sorted(clientes_dict.keys()):
            grupos_dict = clientes_dict[cliente]
            periodos = []
            # Periodo DESC, y dentro del mismo mes tipo de liquidación ASC
            # (sort estable: primero el criterio secundario)
            grupos_reales = sorted(
                [g for g in grupos_dict.keys() if g != SIN_RECIBOS],
                key=lambda g: (g[1] or "").lower(),
            )
            grupos_reales.sort(key=lambda g: g[0], reverse=True)

            for periodo, tipo_liquidacion in grupos_reales:
                empleados_grupo = sorted(
                    grupos_dict[(periodo, tipo_liquidacion)],
                    key=lambda x: (x["apellido"] or "", x["nombre"] or ""),
                )
                total_recibos_grupo = sum(len(e["recibos"]) for e in empleados_grupo)
                firmados = sum(1 for e in empleados_grupo if e["estado"] == "Firmado")
                pendientes = len(empleados_grupo) - firmados
                periodos.append(
                    {
                        "periodo": periodo,
                        "tipo_liquidacion": tipo_liquidacion,
                        "total_empleados": len(empleados_grupo),
                        "total_recibos": total_recibos_grupo,
                        "firmados": firmados,
                        "pendientes": pendientes,
                        "empleados": empleados_grupo,
                    }
                )

            if SIN_RECIBOS in grupos_dict:
                empleados_sin = sorted(
                    grupos_dict[SIN_RECIBOS],
                    key=lambda x: (x["apellido"] or "", x["nombre"] or ""),
                )
                periodos.append(
                    {
                        "periodo": None,
                        "tipo_liquidacion": None,
                        "total_empleados": len(empleados_sin),
                        "total_recibos": 0,
                        "firmados": 0,
                        "pendientes": 0,
                        "empleados": empleados_sin,
                    }
                )

            cant_empleados = len(empleados_por_cliente[cliente])
            cant_recibos = recibos_por_cliente[cliente]
            total_empleados += cant_empleados
            total_recibos += cant_recibos

            clientes.append(
                {
                    "cliente": cliente,
                    "total_empleados": cant_empleados,
                    "total_recibos": cant_recibos,
                    # Meses distintos (un mes puede tener varias liquidaciones)
                    "total_periodos": len({g[0] for g in grupos_reales}),
                    "total_liquidaciones": len(grupos_reales),
                    "periodos": periodos,
                }
            )

        return {
            "clientes": clientes,
            "total_clientes": len(clientes),
            "total_empleados": total_empleados,
            "total_recibos": total_recibos,
        }

    @staticmethod
    def descargar_recibo_individual(
        db: Session,
        empresa_id: uuid.UUID,
        recibo_id: uuid.UUID,
    ) -> Tuple[bytes, str, str]:
        """Descarga un recibo individual (firmado si existe, sino el duplicado).

        Devuelve (bytes_pdf, nombre_archivo, content_type).
        """
        result = (
            db.query(Recibo, LoteRecibo)
            .join(LoteRecibo, Recibo.lote_id == LoteRecibo.id)
            .filter(
                Recibo.id == recibo_id,
                Recibo.empresa_id == empresa_id,
                Recibo.deleted_at.is_(None),
                LoteRecibo.deleted_at.is_(None),
            )
            .first()
        )
        if not result:
            raise ValueError("Recibo no encontrado")

        recibo, lote = result
        archivo_key, sufijo = _archivo_y_sufijo(recibo)

        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.cuil == recibo.cuil_extraido,
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .first()
        )

        try:
            contenido = cloud_storage.download(archivo_key)
        except FileNotFoundError:
            raise ValueError("Archivo PDF no disponible en storage")

        if empleado:
            base = f"{empleado.dni or 'sin_dni'}_{empleado.apellido or ''}_{empleado.nombre or ''}".strip("_")
        else:
            base = f"recibo_{recibo.cuil_extraido or recibo_id}"
        nombre = _safe_filename(f"{base}_{lote.periodo}_{lote.tipo_liquidacion}_{sufijo}.pdf")
        return contenido, nombre, "application/pdf"

    @staticmethod
    def generar_zip(
        db: Session,
        empresa_id: uuid.UUID,
        cliente: str,
        periodo: str,
        tipo_liquidacion: Optional[str] = None,
    ) -> Tuple[bytes, str, List[str]]:
        """Genera ZIP con los recibos de un (cliente, periodo, tipo_liquidacion).

        Sin `tipo_liquidacion` incluye todas las liquidaciones del mes (SAC +
        mensual). Usa archivo firmado si existe, sino el duplicado (marcado
        SIN FIRMAR).
        Devuelve (bytes_zip, nombre_archivo, lista_advertencias).
        """
        # 1. Staging del cliente
        staging = (
            db.query(AdministracionReciboExport)
            .filter(
                AdministracionReciboExport.cliente == cliente,
            )
            .all()
        )

        if not staging:
            raise ValueError(f"No hay registros en staging para cliente '{cliente}'")

        dnis = [s.dni for s in staging if s.dni]
        if not dnis:
            raise ValueError(f"Cliente '{cliente}' no tiene DNIs válidos en staging")

        # 2. Empleados de esos DNIs en la empresa
        empleados = (
            db.query(Empleado)
            .filter(
                Empleado.dni.in_(dnis),
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .all()
        )
        cuils = [e.cuil for e in empleados if e.cuil]

        if not cuils:
            raise ValueError(f"Cliente '{cliente}' no tiene empleados con CUIL en la empresa")

        # 3. Recibos del periodo (y tipo de liquidación) para esos CUILs
        query = (
            db.query(Recibo, LoteRecibo)
            .join(LoteRecibo, Recibo.lote_id == LoteRecibo.id)
            .filter(
                Recibo.empresa_id == empresa_id,
                Recibo.deleted_at.is_(None),
                LoteRecibo.deleted_at.is_(None),
                LoteRecibo.periodo == periodo,
                Recibo.cuil_extraido.in_(cuils),
            )
        )
        if tipo_liquidacion:
            query = query.filter(LoteRecibo.tipo_liquidacion == tipo_liquidacion)

        recibos_q = query.all()

        if not recibos_q:
            detalle = f"periodo '{periodo}'"
            if tipo_liquidacion:
                detalle += f" / '{tipo_liquidacion}'"
            raise ValueError(f"No se encontraron recibos del cliente '{cliente}' para el {detalle}")

        emp_por_cuil = {e.cuil: e for e in empleados if e.cuil}

        advertencias: List[str] = []
        buffer = io.BytesIO()
        archivos_agregados = 0

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for recibo, lote in recibos_q:
                empleado = emp_por_cuil.get(recibo.cuil_extraido)
                if not empleado:
                    advertencias.append(f"CUIL {recibo.cuil_extraido}: empleado no encontrado, recibo omitido")
                    continue

                # Firmado si existe; si no, el duplicado (marcado SIN FIRMAR)
                archivo_key, sufijo = _archivo_y_sufijo(recibo)

                try:
                    contenido = cloud_storage.download(archivo_key)
                except FileNotFoundError:
                    advertencias.append(
                        f"DNI {empleado.dni} - {empleado.apellido}: archivo no disponible ({archivo_key})"
                    )
                    continue

                carpeta_emp = _safe_filename(
                    f"{empleado.dni or 'sin_dni'} - {empleado.apellido or ''} {empleado.nombre or ''}".strip()
                )
                nombre_archivo = _safe_filename(f"{lote.periodo}_{lote.tipo_liquidacion}_{sufijo}.pdf")
                zf.writestr(f"{carpeta_emp}/{nombre_archivo}", contenido)
                archivos_agregados += 1

        if archivos_agregados == 0:
            raise ValueError(f"No se pudo agregar ningún archivo al ZIP para '{cliente}' / '{periodo}'")

        sufijo_tipo = f"_{tipo_liquidacion}" if tipo_liquidacion else ""
        nombre_zip = _safe_filename(f"recibos_{cliente}_{periodo}{sufijo_tipo}.zip")
        return buffer.getvalue(), nombre_zip, advertencias
