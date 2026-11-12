"""
Registro de tareas programadas y su horario (F19-P01).

Cada módulo registra sus tareas al importarse (como `registrar_modulo` con el menú):

    registrar_tarea(codigo='cumpleanos', nombre='Saludos de cumpleaños', modulo='Notificaciones',
                    funcion=mi_funcion, horario_default='09:00', activa_default=True)

`funcion(db)` hace el trabajo y devuelve un resumen legible (str). Si termina con
errores levanta `FalloTarea` (o cualquier excepción): la corrida queda en error y se
manda la alerta. Las tareas `continua=True` corren en cada vuelta del programador y
deciden solas si les toca (su configuración vive en su módulo); si no hicieron nada
devuelven None y no dejan corrida en el historial.

Horario, en hora Argentina (lo que se carga en Parámetros):
    «09:00»       todos los días a esa hora
    «L-V 09:00»   de lunes a viernes a esa hora
    «cada 2h»     cada N horas (1 a 24) desde la última corrida
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

from backend.modules.parametros.services import registrar_validador

ZONA_ARGENTINA = timezone(timedelta(hours=-3))  # sin horario de verano desde 2009

# Valores de `tarea_<codigo>_activa`
VERDADERO = ("1", "true", "si", "sí")
FALSO = ("0", "false", "no")


def ahora_argentina() -> datetime:
    return datetime.now(ZONA_ARGENTINA)


def a_argentina(momento_utc: Optional[datetime]) -> Optional[datetime]:
    """De UTC naive (como se guarda en la base) a hora Argentina."""
    if momento_utc is None:
        return None
    return momento_utc.replace(tzinfo=timezone.utc).astimezone(ZONA_ARGENTINA)


class FalloTarea(Exception):
    """La tarea terminó con errores: la corrida queda en error y se alerta."""


@dataclass(frozen=True)
class Tarea:
    codigo: str
    nombre: str
    modulo: str
    funcion: Callable[[Session], Optional[str]]
    descripcion: str = ""
    horario_default: str = "08:00"
    activa_default: bool = False
    continua: bool = False


TAREAS: Dict[str, Tarea] = {}


def registrar_tarea(
    *,
    codigo: str,
    nombre: str,
    modulo: str,
    funcion: Callable[[Session], Optional[str]],
    descripcion: str = "",
    horario_default: str = "08:00",
    activa_default: bool = False,
    continua: bool = False,
) -> Tarea:
    if not re.fullmatch(r"[a-z0-9_]{3,60}", codigo):
        raise ValueError(f"Código de tarea inválido: {codigo!r}")
    if not continua:
        parsear_horario(horario_default)  # falla al importar si el default está mal
    tarea = Tarea(codigo, nombre, modulo, funcion, descripcion, horario_default, activa_default, continua)
    TAREAS[codigo] = tarea
    return tarea


def clave_activa(codigo: str) -> str:
    return f"tarea_{codigo}_activa"


def clave_horario(codigo: str) -> str:
    return f"tarea_{codigo}_horario"


# ─── Horario ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Horario:
    tipo: str  # diaria | habiles | horas
    hora: Optional[time] = None
    cada_horas: Optional[int] = None

    def texto(self) -> str:
        if self.tipo == "horas":
            return f"Cada {self.cada_horas} h"
        prefijo = "De lunes a viernes" if self.tipo == "habiles" else "Todos los días"
        return f"{prefijo} a las {self.hora:%H:%M}"


_PATRON_HORA = re.compile(r"^(?P<habiles>l\s*-\s*v\s+)?(?P<h>\d{1,2}):(?P<m>\d{2})$")
_PATRON_CADA = re.compile(r"^cada\s+(?P<n>\d{1,2})\s*h(oras?)?$")


def parsear_horario(valor: Optional[str]) -> Horario:
    """«09:00», «L-V 09:00» o «cada 2h». Levanta ValueError con un mensaje para la pantalla."""
    texto = " ".join(str(valor or "").strip().lower().split())
    coincide = _PATRON_HORA.match(texto)
    if coincide:
        h, m = int(coincide["h"]), int(coincide["m"])
        if h > 23 or m > 59:
            raise ValueError(f"Hora inválida: «{valor}»")
        return Horario("habiles" if coincide["habiles"] else "diaria", hora=time(h, m))
    coincide = _PATRON_CADA.match(texto)
    if coincide and 1 <= int(coincide["n"]) <= 24:
        return Horario("horas", cada_horas=int(coincide["n"]))
    raise ValueError(f"Horario inválido: «{valor}». Usá «09:00», «L-V 09:00» o «cada 2h»")


# Parámetros: un horario o un «activa» que el programador no entiende no se guarda (si no,
# la tarea deja de correr sin que nadie se entere). Vacío vale: se usa el valor por defecto.
def _validar_horario(valor: Optional[str]) -> None:
    if str(valor or "").strip():
        parsear_horario(valor)


def _validar_activa(valor: Optional[str]) -> None:
    texto = str(valor or "").strip().lower()
    if texto and texto not in VERDADERO + FALSO:
        raise ValueError(f"Valor inválido: «{valor}». Usá 1 (corre sola) o 0 (solo a mano)")


registrar_validador(lambda key: key.startswith("tarea_") and key.endswith("_horario"), _validar_horario)
registrar_validador(lambda key: key.startswith("tarea_") and key.endswith("_activa"), _validar_activa)


def toca(horario: Horario, ahora: datetime, ultima: Optional[datetime]) -> bool:
    """
    ¿Corresponde correr ahora? `ahora` y `ultima` (inicio de la última corrida
    programada) en hora Argentina. Si el backend estaba caído a la hora, corre al
    levantarse (como los crons de antes).
    """
    if horario.tipo == "horas":
        return ultima is None or ahora - ultima >= timedelta(hours=horario.cada_horas)
    if horario.tipo == "habiles" and ahora.weekday() >= 5:
        return False
    return ahora.time() >= horario.hora and (ultima is None or ultima.date() < ahora.date())


def proxima(horario: Horario, ahora: datetime, ultima: Optional[datetime]) -> datetime:
    """Cuándo corre la próxima vez (para la pantalla), en hora Argentina."""
    if horario.tipo == "horas":
        return ahora if ultima is None else max(ahora, ultima + timedelta(hours=horario.cada_horas))
    if toca(horario, ahora, ultima):
        return ahora
    dia: date = ahora.date()
    if ahora.time() >= horario.hora or (ultima is not None and ultima.date() >= dia):
        dia += timedelta(days=1)
    while horario.tipo == "habiles" and dia.weekday() >= 5:
        dia += timedelta(days=1)
    return datetime.combine(dia, horario.hora, tzinfo=ZONA_ARGENTINA)
