"""Esquemas Pydantic del backup completo de Recruiting y de la importación (restauración) de un backup.

Los usa Parámetros > Archivos de CV. `preview`, `backup_seguridad` y `resultado` son informes que arma el servicio con
conteos por tabla y por carpeta (claves dinámicas), por eso van como diccionarios y no como modelos.
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class BackupEstadoResponse(BaseModel):
    """Estado de la generación de un backup completo de Recruiting (base de datos + CV) y datos de su descarga."""

    backup_id: str
    estado: Literal["preparando", "generando", "verificando", "finalizado", "error"]
    fase: Optional[str] = None
    porcentaje: int = 0
    mensaje: Optional[str] = None
    tablas_total: int = 0
    tablas_procesadas: int = 0
    archivos_total: int = 0
    archivos_procesados: int = 0
    bytes_total: int = 0
    bytes_procesados: int = 0
    nombre_archivo: Optional[str] = None
    tamano_bytes: Optional[int] = None
    tamano: Optional[str] = None
    sha256: Optional[str] = None
    error: Optional[str] = None
    iniciado_at: Optional[str] = None
    finalizado_at: Optional[str] = None


class ImportacionEstadoResponse(BaseModel):
    """Estado de la importación de un backup de Recruiting: validación (vista previa y limitaciones) y restauración."""

    importacion_id: str
    estado: Literal["validando", "validado", "rechazado", "restaurando", "finalizado", "error"]
    fase: Optional[str] = None
    porcentaje: int = 0
    mensaje: Optional[str] = None
    error: Optional[str] = None
    nombre_original: Optional[str] = None
    tamano_bytes: Optional[int] = None
    tamano: Optional[str] = None
    preview: Optional[dict[str, Any]] = None
    limitaciones: List[str] = Field(default_factory=list)
    avisos: List[str] = Field(default_factory=list)
    backup_seguridad: Optional[dict[str, Any]] = None
    resultado: Optional[dict[str, Any]] = None
    revertido: Optional[bool] = None
    iniciado_at: Optional[str] = None
    finalizado_at: Optional[str] = None


class ImportacionConfirmarRequest(BaseModel):
    """Segunda confirmación explícita de la restauración: `texto_confirmacion` debe ser REEMPLAZAR."""

    confirmar: bool = False
    texto_confirmacion: str = Field("", max_length=50)
    aceptar_limitaciones: bool = False
