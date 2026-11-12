"""
Schemas Pydantic de la evaluación de proveedores: configuración, campañas,
tablero, respuestas, importación del Sheet y seguimiento.
"""

from datetime import date, datetime, time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from backend.modules.administracion.proveedores_models import OPCIONES_INCIDENTES, OPCIONES_MAL_MANEJO


def _texto(valor):
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


# ─── Configuración global (D-64, D-66, D-63, D-77) ──────────────────────────────


class CanalesAviso(BaseModel):
    """Por dónde salen los avisos (pestaña Canales)."""

    canal_email: bool = False
    email_cc: List[EmailStr] = []
    canal_webex_personal: bool = False
    canal_webex_canal: bool = False
    webex_room_id: Optional[str] = Field(None, max_length=255)

    @field_validator("webex_room_id", mode="before")
    @classmethod
    def recortar_room(cls, valor):
        return _texto(valor)

    @field_validator("email_cc", mode="before")
    @classmethod
    def lista_de_mails(cls, valor):
        """Acepta lista o texto separado por comas, punto y coma o renglones."""
        if valor is None:
            return []
        if isinstance(valor, str):
            valor = valor.replace(";", ",").replace("\n", ",").split(",")
        return [v.strip() for v in valor if v and v.strip()]


class ConfiguracionDatos(CanalesAviso):
    sheet_url: Optional[str] = Field(None, max_length=500)
    sheet_hoja: str = Field("Listado Proveedores", min_length=1, max_length=100)
    recordar_cada_dias: Optional[Literal[1, 2]] = None
    aviso_apertura: bool = False
    aviso_previo_cierre: bool = False
    hora_envio: time = time(9, 0)

    @field_validator("sheet_url", mode="before")
    @classmethod
    def recortar(cls, valor):
        return _texto(valor)

    @field_validator("sheet_hoja", mode="before")
    @classmethod
    def hoja_por_defecto(cls, valor):
        return _texto(valor) or "Listado Proveedores"

    @model_validator(mode="after")
    def canal_necesita_room(self):
        if self.canal_webex_canal and not self.webex_room_id:
            raise ValueError("Para avisar en un canal de Webex hay que indicar el ID del room")
        return self


class PruebaCanales(CanalesAviso):
    """Prueba de los canales como están en pantalla (aunque no se hayan guardado), con el aviso de
    un evaluador. Le llega de verdad al evaluador, marcada como prueba. Las reglas (algún canal,
    el room si va al canal) las aplica el servicio, para que el mensaje llegue a la pantalla."""

    evaluador_id: str


class ConfiguracionResponse(ConfiguracionDatos):
    actualizado_por: Optional[str] = None
    actualizado_at: Optional[datetime] = None
    cuenta_sheets: Optional[str] = None  # con quién compartir el Sheet (como Lector)


# ─── Auto-generación anual ──────────────────────────────────────────────────────

# El 29/02 se acepta: en los años no bisiestos cae el 28
DIAS_POR_MES = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


class AutogeneracionDatos(BaseModel):
    """Pestaña Auto-generación: el período es el año en curso; inicio y fin, día y mes sin año."""

    activa: bool = False
    inicio_dia: Optional[int] = Field(None, ge=1, le=31)
    inicio_mes: Optional[int] = Field(None, ge=1, le=12)
    fin_dia: Optional[int] = Field(None, ge=1, le=31)
    fin_mes: Optional[int] = Field(None, ge=1, le=12)

    @model_validator(mode="after")
    def fechas_validas(self):
        for nombre, dia, mes in (("inicio", self.inicio_dia, self.inicio_mes), ("fin", self.fin_dia, self.fin_mes)):
            if (dia is None) != (mes is None):
                raise ValueError(f"La fecha de {nombre} necesita el día y el mes")
            if dia is not None and dia > DIAS_POR_MES[mes - 1]:
                raise ValueError(f"La fecha de {nombre} no existe: {dia:02d}/{mes:02d}")
        if self.activa and (self.inicio_dia is None or self.fin_dia is None):
            raise ValueError("Para activar la auto-generación hay que indicar la fecha de inicio y la de fin")
        return self


class ProximaAutogeneracion(BaseModel):
    periodo: str
    fecha_apertura: date
    fecha_cierre: date
    ya_existe: bool = False  # ya hay una evaluación de ese período: la tarea no crea otra


class AutogeneracionResponse(AutogeneracionDatos):
    ultimo_periodo: Optional[str] = None  # el último año que la tarea ya resolvió
    proxima: Optional[ProximaAutogeneracion] = None


# ─── Campañas ───────────────────────────────────────────────────────────────────


class EvaluacionCreate(BaseModel):
    periodo: str = Field(..., min_length=1, max_length=20)
    fecha_apertura: date
    fecha_cierre: date

    @field_validator("periodo", mode="before")
    @classmethod
    def recortar(cls, valor):
        return _texto(valor)

    @model_validator(mode="after")
    def fechas_en_orden(self):
        if self.fecha_cierre < self.fecha_apertura:
            raise ValueError("La fecha de cierre no puede ser anterior a la de apertura")
        return self


class EvaluacionFechas(BaseModel):
    fecha_apertura: date
    fecha_cierre: date

    @model_validator(mode="after")
    def fechas_en_orden(self):
        if self.fecha_cierre < self.fecha_apertura:
            raise ValueError("La fecha de cierre no puede ser anterior a la de apertura")
        return self


class Metricas(BaseModel):
    total: int = 0
    evaluados: int = 0
    pendientes: int = 0
    con_hallazgo: int = 0
    sin_evaluador: int = 0


class EvaluacionResponse(BaseModel):
    id: str
    periodo: str
    fecha_apertura: date
    fecha_cierre: date
    estado: str  # programada · abierta · cerrada · reemplazada
    activa: bool
    metricas: Metricas


# ─── Tablero y respuestas (D-76, D-78, D-81, D-82) ──────────────────────────────


class Referencia(BaseModel):
    id: str
    nombre: str


class ItemTablero(BaseModel):
    id: str
    proveedor: Referencia
    tipo: str
    evaluador: Optional[Referencia] = None
    preguntas: List[str]
    incidentes: Optional[str] = None
    mal_manejo: Optional[str] = None
    con_evidencia: bool = False  # alguna pregunta tiene evidencia
    con_hallazgo: bool = False
    evaluado: bool = False
    evaluado_at: Optional[datetime] = None
    puede_editar: bool = False


class Tablero(BaseModel):
    evaluacion: Optional[EvaluacionResponse] = None
    es_admin: bool
    empleado_vinculado: bool
    puede_evaluar: bool  # la evaluación está abierta
    opciones: Dict[str, List[str]]
    metricas: Metricas
    items: List[ItemTablero]
    evaluadores: List[Referencia] = []
    evaluaciones: List[Referencia] = []  # para que el admin elija una anterior


class CambioHistorial(BaseModel):
    fecha_hora: datetime
    usuario: Optional[str] = None
    accion: str
    antes: Optional[Dict] = None
    despues: Optional[Dict] = None


class ProveedorItem(BaseModel):
    id: str
    nombre: str
    razon_social: Optional[str] = None


class ItemDetalle(BaseModel):
    """La evaluación completa de un proveedor en una campaña."""

    id: str
    proveedor: ProveedorItem
    tipo: str
    evaluacion: EvaluacionResponse
    evaluador: Optional[Referencia] = None
    preguntas: List[str]
    opciones: Dict[str, List[str]]
    incidentes: Optional[str] = None
    mal_manejo: Optional[str] = None
    evidencia_incidentes: Optional[str] = None
    evidencia_mal_manejo: Optional[str] = None
    con_hallazgo: bool = False
    evaluado: bool = False
    evaluado_at: Optional[datetime] = None
    evaluado_por: Optional[str] = None
    puede_editar: bool = False
    es_admin: bool = False
    historial: List[CambioHistorial] = []


class RespuestaEvaluacion(BaseModel):
    incidentes: Optional[Literal[OPCIONES_INCIDENTES]] = None
    mal_manejo: Optional[Literal[OPCIONES_MAL_MANEJO]] = None
    # Evidencia de cada pregunta: obligatoria con «Si» (lo valida el servicio), descartada si no
    evidencia_incidentes: Optional[str] = Field(None, max_length=5000)
    evidencia_mal_manejo: Optional[str] = Field(None, max_length=5000)

    @field_validator("incidentes", "mal_manejo", "evidencia_incidentes", "evidencia_mal_manejo", mode="before")
    @classmethod
    def recortar(cls, valor):
        return _texto(valor)


# ─── Importación del Sheet (D-71, D-73, D-79) ───────────────────────────────────


class FilaImportacion(BaseModel):
    id: str
    fila_sheet: int
    nombre: str
    referente_sheet: Optional[str] = None
    accion: str  # en el registro: alta | sin_cambios | cambio_referente | rechazada
    evaluacion: str = "se_agrega"  # en la evaluación: se_agrega | ya_esta | de_baja | no_entra
    proveedor_id: Optional[str] = None
    referente_anterior: Optional[str] = None
    referente_nuevo: Optional[str] = None
    confirmar: bool
    motivo: Optional[str] = None  # por qué se rechaza el alta
    falta_adjunto: bool = False  # alta con acuerdo Sí: el archivo se sube después, desde el form


class VistaPreviaImportacion(BaseModel):
    id: str
    evaluacion: str
    filas_leidas: int
    se_agregan: int = 0
    ya_estan: int = 0
    de_baja: int = 0
    altas: int
    sin_cambios: int
    cambios_referente: int
    rechazadas: int = 0
    sin_definir: int
    faltan_adjunto: int = 0
    filas: List[FilaImportacion]


class ConfirmacionImportacion(BaseModel):
    """IDs de las filas de cambio de referente que el admin dejó marcadas (D-73)."""

    cambios_confirmados: List[str] = []


class ResultadoImportacion(BaseModel):
    altas: int
    cambios_referente: int
    asignados: int  # agregados a la evaluación
    ya_estaban: int = 0
    rechazadas: int = 0  # altas sin los datos obligatorios


# ─── Seguimiento y avisos ───────────────────────────────────────────────────────


class MensajeAviso(BaseModel):
    asunto: str
    cuerpo: str


class SeguimientoEvaluador(BaseModel):
    evaluador: Referencia
    email: Optional[str] = None
    total: int
    evaluados: int
    pendientes: List[str]
    mensaje: Optional[MensajeAviso] = None


class Seguimiento(BaseModel):
    evaluacion: Optional[EvaluacionResponse] = None
    evaluadores: List[SeguimientoEvaluador]
    sin_evaluador: List[str]  # proveedores con referente «sin definir»
    canales: List[str]  # canales activos en la configuración


class AvisoSolicitud(BaseModel):
    evaluadores: List[str] = Field(..., min_length=1)  # IDs de empleados


class ResultadoAviso(BaseModel):
    evaluador: str
    canal: str
    destino: Optional[str] = None
    enviado: bool
    detalle: Optional[str] = None


class AvisoLog(BaseModel):
    fecha_hora: datetime
    motivo: str
    canal: str
    destino: str
    pendientes: int
    enviado: bool
    error: Optional[str] = None
