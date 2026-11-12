"""
Tareas de la evaluación de proveedores, que corre el motor de tareas cada minuto:

- Avisos (F19-P07): cuándo y por dónde avisa no se configura en Parámetros sino en
  la Configuración de la evaluación (excepción pedida por el usuario, D-64). Los
  avisos se encolan y la cola los despacha con reintentos.
- Auto-generación anual: crea la evaluación del año al llegar la fecha de inicio
  de la pestaña Auto-generación (arranca apagada).

Las dos son «continuas»: deciden solas si les toca.
"""

from typing import Optional

from sqlalchemy.orm import Session

from backend.modules.administracion import evaluacion_proveedores_avisos as avisos
from backend.modules.administracion.evaluacion_proveedores_services import AutogeneracionService
from backend.modules.tareas.registro import FalloTarea, registrar_tarea


def avisos_del_dia(db: Session) -> Optional[str]:
    resumen = avisos.procesar_avisos_del_dia(db)
    if resumen["errores"]:
        raise FalloTarea("; ".join(resumen["errores"]))
    if not resumen["encolados"]:
        return None  # nada que hacer: no deja corrida en el historial
    return f"{resumen['encolados']} aviso(s) encolado(s) para {resumen['empresas']} empresa(s)"


registrar_tarea(
    codigo="avisos_evaluacion_proveedores",
    nombre="Avisos de evaluación de proveedores",
    modulo="Administración",
    funcion=avisos_del_dia,
    continua=True,
    descripcion="Corre cada minuto. Cuándo y por dónde avisa se configura en la Configuración de la evaluación.",
)


def autogeneracion_anual(db: Session) -> Optional[str]:
    resumen = AutogeneracionService.procesar(db)
    if resumen["errores"]:
        raise FalloTarea("; ".join(resumen["errores"]))
    if not resumen["creadas"]:
        return None  # nada que hacer: no deja corrida en el historial
    return f"Evaluación creada automáticamente: {'; '.join(resumen['creadas'])}"


registrar_tarea(
    codigo="autogeneracion_evaluacion_proveedores",
    nombre="Auto-generación de la evaluación de proveedores",
    modulo="Administración",
    funcion=autogeneracion_anual,
    continua=True,
    descripcion="Corre cada minuto. Crea la evaluación del año al llegar la fecha de inicio de la pestaña "
    "Auto-generación de la Configuración de la evaluación (arranca apagada).",
)
