# Tareas programadas y notificaciones (F19)

Motor único para todo lo que corre solo: un programador decide qué toca y cuándo (en hora
Argentina), una cola despacha los mails y mensajes de Webex con reintentos, y si algo falla
sale una alerta por Webex. Reemplaza los tres crons que había (cumpleaños, membresías de Webex
y avisos de proveedores), cada uno con su hilo, su candado y su hora (D-98, D-99).

Código: `backend/modules/tareas/`. Pantalla: **Configuración → Tareas programadas**
(`/tareas-programadas`, permiso `configuracion.tareas_programadas`).

## Tareas registradas

| Tarea | Módulo | Arranca | Horario por defecto |
|---|---|---|---|
| Saludos de cumpleaños | Notificaciones | como estaba (migrado) | 09:00 |
| Refresco del token lector de Webex | Notificaciones | activa | 05:00 |
| Nómina desde Odoo | Actualización de Datos | apagada | 08:00 |
| Usuarios faltantes | Actualización de Datos | apagada | 08:00 |
| Carga masiva de StarMiles | Actualización de Datos | apagada | 08:00 |
| Charlas de innovación | Actualización de Datos | apagada | 08:00 |
| Recibos de administración | Actualización de Datos | apagada | 08:00 |
| Membresías de Webex | Actualización de Datos | como estaba (migrado) | 08:00 |
| Avisos de evaluación de proveedores | Administración | continua | cada minuto |

Cualquier proceso de Actualización de Datos se puede programar (F19-P03). Si el proceso está
desactivado en Actualización de Datos, la tarea se omite. Las continuas no tienen horario:
corren cada minuto y deciden solas (los avisos de proveedores usan la configuración de su
módulo, D-64).

## Configuración (Parámetros)

En **Configuración → Parámetros**, categoría «Tareas programadas» (regla del proyecto: la
configuración en uso vive en Parámetros, no en cada pantalla):

- `tarea_<codigo>_activa`: `1` corre sola según su horario; `0` solo a mano.
- `tarea_<codigo>_horario`, en hora Argentina:
  - `09:00` todos los días a esa hora;
  - `L-V 09:00` de lunes a viernes;
  - `cada 2h` cada N horas (1 a 24) desde la última corrida.
- `alertas_webex_room_id`: el room de Webex donde caen las alertas. Vacío: las alertas solo
  quedan en el log, y la pantalla lo avisa. El bot tiene que estar en el room (y en su equipo,
  si el room es de un equipo).

Parámetros no guarda un horario o un «activa» que el programador no entiende (responde el
error, ej. «Hora inválida: «26:00»»): si no, la tarea dejaría de correr sin aviso. Vacío vale y
usa el valor por defecto. Es un validador que el motor registra en Parámetros
(`parametros.services.registrar_validador`); cualquier módulo puede registrar el suyo.

Si el backend estaba caído a la hora de una tarea diaria, la corre al levantarse (como los
crons de antes). Una tarea solo corre si sus parámetros ya existen.

**Migración (sin cambiar el horario real):** los crons viejos guardaban la hora del servidor,
que en Docker es UTC (`notificaciones_cron_hora`, `notificaciones_refresh_token_hora`,
`sync_webex_cron_hora` y sus «activo»). Al arrancar, el motor crea los parámetros nuevos con
esos valores pasados a hora Argentina (UTC − 3) y da de baja los viejos. Es idempotente.

## Programador

- Un solo loop por proceso (`programador.py`). Entre los workers, uno solo es el líder: el que
  tiene el advisory lock de Postgres en una conexión que mantiene abierta; si ese proceso muere,
  otro toma la posta. Cada vuelta (20 s): corridas pedidas a mano, tareas que tocan, continuas
  (como mucho una vez por minuto) y la cola de envíos.
- Cada corrida programada o manual va en un hilo de trabajo acotado (3 a la vez) y una tarea no
  se superpone consigo misma: hay tareas largas (cumpleaños espera minutos entre saludos).
- Corre en el servicio `scheduler` del compose (F06-P01): la imagen del backend con
  `CRON_ENABLED=true` y un worker. El backend que atiende la API lo tiene apagado. Al arrancar
  asegura sus parámetros (`tarea_*`, el room de alertas) en cualquier entorno; antes quedaba detrás
  del corte de desarrollo y fuera de él no corría (F19-P10).
- Al tomar el liderazgo, lo que quedó «corriendo» lo cortó un reinicio: queda en error y se
  alerta.

## Historial y alertas

Cada corrida queda en `core_tareas_corridas` (programada o a mano, quién la pidió, inicio, fin,
resultado o error). Una corrida que termina en error manda una alerta por Webex al room de
alertas: una por corrida, con el error legible y el link al historial. El mismo error de la
misma tarea no se repite dentro de la hora. Las continuas solo dejan corrida si hicieron algo o
fallaron.

## Cola de envíos

`core_envios` (`cola.py`): los módulos encolan (`cola.encolar`) y el programador despacha en
orden de llegada, con una pausa entre mensajes de Webex. Si un envío falla se reintenta a los
1, 5 y 15 minutos; al tercer fallo queda en error y se alerta (una alerta por tanda). Sin
duplicados: la misma `clave` no se encola dos veces. Con `referencia` («tipo:id») el módulo se
entera del resultado (`cola.registrar_manejador`). Desde la pestaña Envíos se reintenta a mano.

`cola.mandar()` es el envío por canal (mail, Webex a una persona, Webex a un room) y lo usan
también los envíos que necesitan el resultado en el momento (manual y prueba de canales de
proveedores). Usa `core/webex.describir_error` y `core/email_layout` (D-97).

Hoy encolan los avisos automáticos de proveedores y el aviso de canje nuevo de Star Miles
([starmiles.md](starmiles.md)). Los saludos de cumpleaños siguen mandando
por su cuenta (contexto, saludo con Gemini, mención y card, con su propio registro y reintento
a mano): el motor los programa y alerta si alguno queda en error.

## Registrar una tarea nueva

En el módulo, un archivo `tareas.py` que se importa en `main.py`:

```python
from backend.modules.tareas.registro import FalloTarea, registrar_tarea

def mi_tarea(db) -> str:
    ...  # hace el trabajo
    if algo_fallo:
        raise FalloTarea('qué pasó, legible')  # corrida en error + alerta
    return 'resumen legible'

registrar_tarea(codigo='mi_tarea', nombre='Mi tarea', modulo='Mi módulo', funcion=mi_tarea,
                descripcion='Qué hace', horario_default='08:00', activa_default=False)
```

Al arrancar se crean sus parámetros (`tarea_mi_tarea_activa` y `tarea_mi_tarea_horario`) y
aparece en la pantalla. Para mandar mensajes, encolarlos con `cola.encolar(...)`.
