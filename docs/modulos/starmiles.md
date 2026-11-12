# Star Miles

Por ahora este documento cubre los avisos del módulo; el resto de Star Miles (desafíos,
inscripciones, catálogo y canjes) todavía no está documentado acá.

## Aviso de canje nuevo (F20)

Cuando un empleado registra un canje (`CanjeService.crear`), sale una card al room de Webex de
quienes aprueban, para que se enteren sin tener que entrar a mirar.

- **Room:** parámetro `webex_room_starmiles_canjes_id`, en **Configuración → Parámetros →
  Notificaciones → Webex** («Sala de Notificación de Canjes de Star Miles»). Vacío: no se
  avisa (queda en el log). El bot tiene que estar en el room.
- **La card:** quién pidió el canje, el premio, la cantidad, las Star Miles, el precio y el
  link si es de MercadoLibre, el comentario y la fecha del pedido en hora Argentina. Botones:
  «Revisar canjes pendientes» (`/starmiles/aprobador/canjes`) y, si corresponde, «Ver en
  MercadoLibre».
- **Cómo sale:** por la cola de envíos del motor de tareas ([tareas.md](tareas.md)). Se encola
  en la misma transacción que el canje (origen `starmiles_canjes`, clave
  `starmiles_canje:<id>`, así un canje avisa una sola vez), el programador la despacha, se
  reintenta si Webex falla y, si no sale, llega la alerta de fallo. Se ve en
  **Configuración → Tareas programadas → Envíos**.
- **Nunca frena el canje:** el aviso se arma en un savepoint; si algo falla al armarlo, se
  descarta solo el aviso y el canje se registra igual.

Código: `backend/modules/starmiles/avisos.py`. Tests: `backend/tests/integration/test_starmiles_avisos.py`.
