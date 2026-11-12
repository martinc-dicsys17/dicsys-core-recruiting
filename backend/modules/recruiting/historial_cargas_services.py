"""Auditoria de cargas de CV: registra cada operacion (individual o masiva) y el resultado de cada archivo.

El registro usa su PROPIA sesion y su propio commit: se conserva aunque la operacion principal falle o haga rollback, y un
error al auditar nunca interrumpe ni cambia el resultado de la carga. Solo se guardan metadatos (nombre del archivo,
resultado y motivo); nunca el contenido del CV ni datos personales extraidos de el.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from backend.database import SessionLocal
from backend.modules.recruiting.models import HistorialCargaCV, HistorialCargaCVArchivo

_log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
SIN_IDENTIFICAR = "Sin identificar"
RESULTADOS_ARCHIVO = ("creado", "duplicado", "sin_email", "rechazado")


class HistorialCargaCVService:
    @staticmethod
    def resultado_archivo(categoria: str) -> str:
        """Categoria detallada de la carga (creado, duplicado, sin_email, formato_tamano, error_*...) -> resultado de auditoria."""
        return categoria if categoria in ("creado", "duplicado", "sin_email") else "rechazado"

    @staticmethod
    def calcular_resultado(
        creados: int, duplicados: int, sin_email: int, rechazados: int, cancelado: bool = False
    ) -> str:
        """completada: todo creado o duplicado; fallida: nada creado ni duplicado; parcial: el resto; cancelada: lote detenido por el usuario."""
        if cancelado:
            return "cancelada"
        if creados + duplicados == 0:
            return "fallida"
        return "completada" if sin_email + rechazados == 0 else "parcial"

    @staticmethod
    def _limpiar_motivo(motivo: Optional[str]) -> Optional[str]:
        """Sin emails (dato personal) y acotado al largo de la columna."""
        if not motivo:
            return None
        return _EMAIL_RE.sub("[email]", str(motivo))[:500]

    @staticmethod
    def nombre_usuario(usuario: Any) -> str:
        if usuario is None:
            return SIN_IDENTIFICAR
        nombre = " ".join(f"{getattr(usuario, 'nombre', '') or ''} {getattr(usuario, 'apellido', '') or ''}".split())
        return (nombre or getattr(usuario, "email", None) or SIN_IDENTIFICAR)[:255]

    @staticmethod
    def registrar(
        empresa_id: uuid.UUID,
        usuario_id: Optional[uuid.UUID],
        usuario_nombre: str,
        tipo_carga: str,
        nombre_archivo: Optional[str],
        archivos: List[Dict[str, Any]],
        cancelado: bool = False,
        operacion_id: Optional[uuid.UUID] = None,
    ) -> Optional[uuid.UUID]:
        """
        Guarda un registro principal y una fila por archivo (`archivos`: nombre, resultado, motivo) en una transaccion propia.
        Los contadores salen de `archivos`. Idempotente por `operacion_id`. Nunca lanza: ante un error lo registra en el log y devuelve None.
        """
        operacion_id = operacion_id or uuid.uuid4()
        try:
            filas = [
                (
                    str(a.get("nombre") or "(sin nombre)")[:255],
                    HistorialCargaCVService.resultado_archivo(a.get("resultado")),
                    HistorialCargaCVService._limpiar_motivo(a.get("motivo")),
                )
                for a in archivos
            ]
            conteo = {r: sum(1 for f in filas if f[1] == r) for r in RESULTADOS_ARCHIVO}
            db = SessionLocal()
            try:
                if db.query(HistorialCargaCV.id).filter(HistorialCargaCV.operacion_id == operacion_id).first():
                    return operacion_id  # ya registrada: no se duplica
                registro = HistorialCargaCV(
                    empresa_id=empresa_id,
                    usuario_id=usuario_id,
                    usuario_nombre=usuario_nombre or SIN_IDENTIFICAR,
                    tipo_carga=tipo_carga,
                    nombre_archivo=(nombre_archivo or None) and nombre_archivo[:255],
                    total_archivos=len(filas),
                    candidatos_creados=conteo["creado"],
                    duplicados=conteo["duplicado"],
                    sin_email=conteo["sin_email"],
                    rechazados=conteo["rechazado"],
                    resultado=HistorialCargaCVService.calcular_resultado(
                        conteo["creado"], conteo["duplicado"], conteo["sin_email"], conteo["rechazado"], cancelado
                    ),
                    operacion_id=operacion_id,
                )
                db.add(registro)
                db.flush()
                for orden, (nombre, resultado, motivo) in enumerate(filas):
                    db.add(
                        HistorialCargaCVArchivo(
                            historial_id=registro.id,
                            empresa_id=empresa_id,
                            orden=orden,
                            nombre_archivo=nombre,
                            resultado=resultado,
                            motivo=motivo,
                        )
                    )
                db.commit()
                return operacion_id
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception as e:
            _log.error(f"No se pudo registrar la auditoria de la carga de CV: {e}", exc_info=True)
            return None
