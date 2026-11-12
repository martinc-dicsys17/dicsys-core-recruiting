"""
Motor de tareas programadas y notificaciones (F19, D-98, D-99).

- registro: cada módulo registra sus tareas (qué ejecutar y cuándo, en hora Argentina).
- programador: un solo loop decide qué toca y lanza cada ejecución en un hilo acotado.
- cola: los envíos (mail y Webex) se despachan en orden, con reintentos y sin duplicados.
- alertas: una corrida que falla, o un envío que agota los reintentos, avisa por Webex
  al room configurado en Parámetros.

El horario y si cada tarea está activa se configuran en Parámetros (categoría
«Tareas programadas»); la pantalla Configuración → Tareas programadas muestra el
estado, el historial y la cola.
"""
