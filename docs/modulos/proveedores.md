# Proveedores y evaluación de proveedores

Registro de proveedores y herramientas y su evaluación anual por campañas, dentro de
**Administración**. Cubre los controles ISO/IEC 27001:2022 A.5.19 a A.5.22 (registro de
proveedores, acuerdos y revisión periódica). Es el port del módulo del sandbox
`dicsys-sandbox-ema`, rehecho sobre el login, los permisos y la base de este sistema.

El plan y las decisiones viven en `director` (fase **F18**, decisiones **D-61 a D-86**).
Modelo de datos: [`docs/modelo-datos/proveedores.dbml`](../modelo-datos/proveedores.dbml).

## Menú y permisos

Tres pantallas anidadas en Administración (`admin_contable`). El anidado es solo de
presentación (D-86): cada pantalla tiene su propia clave de permiso.

| Menú | Ruta | Permiso | Para quién |
|---|---|---|---|
| Proveedores | `/administracion/proveedores` | `admin_contable.proveedores` | Quien administra el registro |
| └ Evaluación de Proveedores | `/administracion/evaluaciones-proveedores` | `admin_contable.evaluacion_proveedores` | Evaluadores |
| └ Configuración | `/administracion/config-evaluaciones-proveedores` | `admin_contable.evaluacion_config` | Admin del módulo |

- Quien tiene `evaluacion_config` es admin del módulo: en el tablero ve todos los ítems y
  puede mirar evaluaciones anteriores (D-76).
- Los demás ven solo lo asignado a su empleado. El usuario logueado se vincula con la
  nómina por **DNI**, igual que el login.
- Editan una evaluación el referente asignado al ítem y el admin del módulo (D-72, D-87). La
  auditoría registra quién lo hizo.
- Si el usuario no tiene permiso propio sobre «Proveedores» pero sí sobre un hijo, el padre
  aparece como rótulo sin link.

## Registro

Tabla `proveedores_proveedores`. La fuente de verdad es la app (D-70). El Sheet solo
da de alta proveedores nuevos y propone cambios de referente.

| Campo | Notas |
|---|---|
| Nombre | De fantasía o herramienta. Único por empresa sin importar acentos ni mayúsculas |
| Razón social | |
| CUIT | Opcional (los del exterior no tienen). Como en Clientes: 11 dígitos con dígito verificador; se guarda `XX-XXXXXXXX-X` y se busca con o sin guiones (D-92) |
| Tipo de IVA | Las responsabilidades AFIP de Clientes, con «Proveedor del Exterior» en vez de «Cliente del Exterior» (D-92) |
| Nro. Ingresos Brutos | Texto, hasta 50 caracteres (D-92) |
| Tipo | Proveedor, Herramienta o Sin clasificar. Define qué se pregunta en la evaluación (D-78) |
| Usuario referente | **Obligatorio.** Empleado activo de la nómina; se cambia, no se quita. Vacío («sin definir») solo en registros anteriores a la obligatoriedad |
| Servicio provisto, tipo de información | Texto. **Obligatorios** |
| Email, WhatsApp, página web | El WhatsApp se guarda solo con dígitos y abre WhatsApp Web |
| Acuerdo de servicio firmado | **Obligatorio: Sí / No** (los «N/A» de antes pasaron a vacío y se piden al editar) |
| Política de seguridad / NDA | Texto o enlace, y un archivo adjunto. Con acuerdo **Sí**, el adjunto es obligatorio; con **No**, el texto o enlace es obligatorio |
| Observaciones | Texto libre, como en Clientes (D-92) |

Pantallas, como Nómina → Empleados:

- **Listado:** el nombre lleva a la vista; las acciones son íconos (editar, inactivar, activar).
- **Vista** (`/administracion/proveedores/<id>`): página de solo lectura con pestañas Datos,
  Oficinas, Contactos, Documentos y Evaluaciones, sin cantidad de registros. El adjunto y los
  documentos se pueden descargar, no cambiar. Tiene el botón **Editar**.
- **Edición** (`/administracion/proveedores/<id>/editar`) y **alta** (`/nuevo`): las oficinas,
  los contactos, los documentos y el estado se gestionan solo en edición. En el alta con
  acuerdo Sí, el archivo se elige en el mismo formulario y viaja con los datos
  (`POST /api/v1/proveedores/con-adjunto`, multipart): el proveedor no existe sin su adjunto.
  Al crear un proveedor se pasa directo a su edición. La edición tiene pestañas Datos,
  Contacto, Seguridad y acuerdos, Oficinas, Contactos y Documentos; las tres primeras son un
  solo formulario con un único Guardar. El alta tiene esas tres pestañas.
- **Al guardar**, lo que falta o tiene error se marca en rojo, la pestaña lleva un punto rojo
  y se abre la del campo con el aviso; los errores del servidor (nombre repetido, URL, CUIT,
  adjunto) se muestran debajo del campo.
- **Oficinas y contactos**, en la vista y en la edición: se ven en **Tabla** o en **Cards**. La
  elección se recuerda en el navegador y es la misma para las dos pantallas.
- **Agregar o editar una oficina o un contacto** se hace en su propia página, como el domicilio
  en Clientes (D-93): `/proveedores/<id>/oficinas/nueva`, `/oficinas/<oficina>/editar`,
  `/contactos/nuevo` y `/contactos/<contacto>/editar`. Al guardar se vuelve a la edición, en
  la pestaña de la que se vino. Eliminar sigue en la lista.
- **Pestañas:** todas las pantallas del módulo usan el estilo de `/perfil` (subrayado), el
  mismo de Clientes y Empresa (D-93).

Además, cada proveedor tiene:

- **Oficinas:** un domicilio por oficina, con a lo sumo un domicilio legal.
- **Contactos:** con a lo sumo un contacto principal; cada contacto puede indicar su oficina.
- **Documentos:** los archivos que se quieran guardar del proveedor (ver abajo).
- **Historial de evaluaciones:** el resultado del proveedor en cada campaña.

Reglas:

- **Estado** (campo `activo`; se elige en la edición, pestaña Datos, o con los íconos del
  listado):
  - **Activo:** se usa para todo.
  - **Inactivo:** se sigue viendo y conserva su historial (evaluaciones, documentos), pero no
    entra en evaluaciones nuevas: ni por el Sheet, ni por la auto-generación, ni con «Agregar
    proveedor» (aparece marcado y hay que activarlo antes; ya no se reactiva solo). Tampoco
    se va a poder usar en facturas o pedidos cuando esos módulos existan. De la evaluación
    activa sale solo si estaba pendiente; si ya estaba evaluado, conserva el resultado. Queda
    en la auditoría como `baja` / `reactivar`.
- **Alta o activación:** el proveedor **no** entra solo a la evaluación activa. Se evalúan
  solo los que llegan por la importación del Sheet o con «Agregar proveedor» (reemplaza a
  D-75).
- **Cambio de referente:** también cambia el evaluador del ítem en la evaluación activa.
  Las campañas anteriores no se tocan.
- **Eliminar:** solo si el proveedor nunca fue evaluado; si no, se pasa a Inactivo.

**Adjunto de NDA (D-84):**

- Acepta pdf, jpg, png, doc y docx, hasta 10 MB. El tipo se valida por el contenido del
  archivo, no por la extensión.
- Se guarda en el storage privado con una clave aleatoria y se descarga solo por
  `GET /api/v1/proveedores/{id}/nda`, que valida el permiso.
- Los tipos y el tamaño definitivos dependen de D-56.
- **Obligatorio con acuerdo Sí:** el alta lo trae en el mismo pedido; la edición no guarda
  «Sí» sin adjunto (422) y, mientras el acuerdo guardado sea Sí, el adjunto se puede
  reemplazar pero no quitar (409). Un alta del Sheet con Sí entra sin archivo: la ficha
  muestra «Falta el adjunto del acuerdo» y la edición lo pide antes de guardar.

**Documentos (pestaña Documentos):**

- Se suben varios a la vez (hasta 20 por subida; arrastrando o eligiéndolos): pdf, xlsx,
  png, jpg, jpeg, doc y docx, hasta 10 MB cada uno, con el tipo validado por el contenido.
  Todos o ninguno: si uno no es válido, el mensaje dice cuál y no se sube nada.
- En el bucket van con un UUID: `{empresa_id}/proveedores/{proveedor_id}/{uuid}{ext}`; el
  nombre original queda en la base (`proveedores_documentos`) y es el que se ve y con el que
  se descarga. Se descargan solo por la API, con el permiso del módulo.
- **Miniatura** (`{uuid}-miniatura.png`, al lado del documento, 320 px de ancho), toda en
  Python (`proveedores_miniaturas.py`, sin LibreOffice):
  - imágenes: se achican con Pillow;
  - PDF: la primera página, con PyMuPDF;
  - xlsx: las primeras filas de la primera hoja, leídas con `openpyxl` y dibujadas como grilla
    (las columnas cortas, como fechas e importes, completas; números y fechas en formato
    argentino);
  - docx: títulos y párrafos leídos del XML del zip con la biblioteca estándar y dibujados
    como una página;
  - doc (Word 97): sin miniatura, se muestra el tipo (no hay forma confiable de leerlo en
    Python puro).

  Las de Word y Excel son una vista previa del contenido, no la página tal como la muestra
  Office. Se dibujan con Pillow y la fuente Inter de Innovación. Para no leer una bomba zip,
  un docx o xlsx que descomprime más de 50 MB queda sin miniatura, y un docx con
  declaraciones `DOCTYPE`/`ENTITY` no se procesa. Si la miniatura falla, el documento se
  sube igual.
- Los sube y los borra quien tenga permiso sobre Proveedores, también con el proveedor
  inactivo. Borrar es baja lógica del registro y saca el archivo y su miniatura del bucket.
  Subidas y bajas quedan en la auditoría (entidad `documento`).
- API: `GET/POST /api/v1/proveedores/{id}/documentos`,
  `GET/DELETE /api/v1/proveedores/{id}/documentos/{documento}` y
  `GET …/{documento}/miniatura`.

**Datos obligatorios:** la regla vive en `proveedores_comun.datos_faltantes` y la usan el
schema del alta y la edición (422 «Faltan datos obligatorios: …») y la importación del Sheet.

## Evaluaciones (campañas)

Tabla `proveedores_evaluaciones`. Cada campaña tiene un período y una fecha de apertura
y otra de cierre (D-65).

- **Una sola vigente por empresa.** Crear la siguiente finaliza la anterior (D-74).
- **Creada a mano, arranca sin proveedores.** No se evalúan todos los del registro: entran
  por la importación del Google Sheet o con «Agregar proveedor» del tablero. La que crea la
  auto-generación arranca con todos los activos.
- **Eliminar** (Configuración → Evaluaciones): baja lógica de la campaña y de sus ítems,
  también si ya tiene evaluados, con un modal que dice cuántos proveedores tiene y cuántos
  están evaluados. Deja de verse en el tablero y en la ficha de cada proveedor, el período
  se puede volver a crear y una vista previa del Sheet pendiente se descarta. Si era la
  vigente no queda ninguna: la anterior sigue finalizada. Queda en la auditoría
  (`eliminar`). `DELETE /api/v1/evaluaciones-proveedores/evaluaciones/{id}`.
- **Activa** = la vigente mientras no pasó su cierre. No se guarda como columna: se
  calcula.
- **Ventana de evaluación:** solo se puede evaluar entre la apertura y el cierre, en hora
  Argentina. Ampliar el cierre de la vigente la vuelve a abrir.
- **Estados:** programada, abierta, cerrada y finalizada (reemplazada por otra).

### Auto-generación anual

Pestaña **Configuración → Auto-generación**. Arranca apagada.

- **Período:** el año en curso. **Fecha de inicio** y **fecha de fin:** día y mes, sin año.
  Si el fin cae antes del inicio, el cierre es al año siguiente; el 29/02 cae el 28 en los
  años no bisiestos.
- **Qué hace:** al llegar la fecha de inicio, la tarea continua
  `autogeneracion_evaluacion_proveedores` (cada minuto) crea la evaluación del año con todos
  los proveedores activos, cada uno con su referente como evaluador, y reemplaza a la
  vigente como la creación manual. Queda en la auditoría como `crear` de `cron@sistema` con
  `via: autogeneracion`.
- **Una sola vez por año** (`auto_ultimo_periodo`): si ya existe la evaluación de ese año, no
  crea otra; si la creada se elimina, no la vuelve a crear. Si se activa con la ventana del
  año ya pasada, espera al año siguiente. La pestaña dice cuál es la próxima.
- `GET` y `PUT /api/v1/evaluaciones-proveedores/autogeneracion` (permiso de configuración).

### Respuestas (tablero «Evaluación de Proveedores»)

Toda evaluación responde **obligatoriamente las dos preguntas**, sea cual sea el tipo del
proveedor. El **Checklist de seguridad salió de la evaluación** con sus datos: la migración
`proveedores_sin_checklist_v1` borró las columnas `checklist` y `evidencia_checklist` (la
auditoría, append-only, conserva los eventos viejos; la pantalla ya no los muestra).

| Pregunta | Opciones |
|---|---|
| Herramientas: ¿hubo incidentes? | Si / No / N/A |
| Proveedores: ¿hubo mal manejo de información compartida? | Si / No |

- **Cuándo cuenta como evaluado:** con las dos respondidas.
- **Evidencia:** texto libre para links o texto. Con **Si** la evidencia aparece y es
  obligatoria (422 «Con «Si» la evidencia es obligatoria: falta la de …»); con **No** o
  **N/A** queda oculta, no se pide y se descarta al guardar (reemplaza la evidencia opcional
  de D-90).
- **Hallazgo:** incidentes = Si o mal manejo = Si. Es una columna calculada de la base,
  `con_hallazgo` (D-81).
- **Tablero:** métricas de total, evaluados, pendientes y con hallazgos; filtros por texto,
  estado y evaluador (el de evaluador, solo para el admin). El nombre lleva a la evaluación
  completa; el botón Evaluar/Editar aparece solo para el referente y el admin.
- **Evaluación completa** (`/administracion/evaluaciones-proveedores/<id>`): respuestas,
  la evidencia de cada una (con links, oculta tras «Mostrar evidencia»), quién y cuándo, y el
  historial de cambios sacado de la auditoría.
  Se edita en `/editar`, con la evaluación abierta.
- **Agregar proveedor** (con la evaluación activa): suma uno o varios proveedores a la
  evaluación, cada uno con su usuario referente como evaluador. Se buscan por nombre o razón
  social (sin importar mayúsculas ni acentos) o por CUIT (con o sin guiones); los que ya están
  aparecen marcados y sin botón. El botón de cada fila alterna entre «Agregar» y «Agregado»
  (elegido); lo elegido se conserva aunque cambie la búsqueda y «Agregar (N)» los suma
  juntos: todos o ninguno (si uno no se puede, el mensaje dice cuál y no entra ninguno).
  - El **admin** del módulo busca en todo el registro; un inactivo aparece marcado pero no se
    agrega: primero hay que activarlo en Proveedores.
  - El **evaluador** solo ve y agrega los proveedores activos que tiene asignados como
    usuario referente (su usuario tiene que estar vinculado a un empleado de la nómina).
  - Los proveedores nuevos se dan de alta en el registro (Proveedores) y después se agregan.

## Importación del Google Sheet

Se configura en **Configuración → Fuente de datos**: el link del Sheet y la hoja, que por
defecto es «Listado Proveedores» (D-79). La pestaña muestra el mail de la cuenta de servicio
con la que hay que compartir el Sheet, con un botón para copiarlo. Ahí mismo está el botón
**Cargar Sheet**, que abre la importación en su propia página
(`/administracion/config-evaluaciones-proveedores/importar`): lee lo guardado apenas abre, así
que si el link o la hoja tienen cambios sin guardar, el botón queda deshabilitado hasta guardar.
Al terminar, la página muestra el resultado y vuelve a Fuente de datos. La importación se
hace en dos pasos (D-71, D-73):

1. **Vista previa.**
   - Lee la hoja y ubica las columnas por el texto del encabezado, no por la letra.
   - Cruza cada fila con el registro, comparando el nombre sin acentos.
   - Cruza el «Referente Interno» con la nómina. Se acepta un empleado solo si su nombre
     completo contiene todas las palabras y es el único que cumple. Si no, queda «sin
     definir», como pasa con un typo o con un homónimo.
   - Clasifica cada fila dos veces:
     - en el **registro**: *alta*, *sin cambios*, *cambia el referente* (los cambios traen
       un check, marcado por defecto) o *rechazada*;
     - en la **evaluación activa**: *se agrega*, *ya está*, *de baja* (no se agrega) o
       *no entra* (rechazada).
   - Un **alta** tiene que traer los datos obligatorios del formulario: referente encontrado en
     la nómina, servicio, tipo de información, acuerdo Sí/No y, con No, la política/NDA. Si le
     falta alguno queda *rechazada* con el motivo («Falta: …») y no entra ni al registro ni a la
     evaluación. Con acuerdo Sí entra marcada «Falta el adjunto del acuerdo»: el Sheet no trae
     el archivo y la edición del proveedor lo pide.
   - El resumen arranca por lo que pasa en la evaluación: cuántos se agregan y cuántos ya
     están. Así se ve que, aunque no haya altas en el registro, igual se cargan a la
     evaluación.
   - La vista previa queda en tablas temporales (UNLOGGED).
2. **Confirmar.**
   - Da de alta los proveedores nuevos (las rechazadas no; tampoco un alta cuyo referente dejó
     la nómina después de la vista previa).
   - Actualiza el referente solo en las filas que quedaron marcadas.
   - Agrega a la evaluación activa todos los proveedores del Sheet que todavía no están, con
     su referente como evaluador (los dados de baja, no). Es la forma de cargar la
     evaluación, que arranca vacía.
   - El resultado dice cuántos se agregaron y cuántos ya estaban, las altas y cambios de
     referente del registro y las filas rechazadas.
   - Borra la vista previa y deja un evento `confirmar_importacion` en la auditoría.
   - Cancelar también la borra. Una vista previa abandonada se borra al empezar otra.

Si la lectura o el encabezado fallan, no se escribe nada. Las evaluaciones anteriores
nunca se tocan (D-68).

La lectura usa `backend/core/google_sheets.py`, de solo lectura (scope
`spreadsheets.readonly`). Se autentica con una cuenta de servicio propia, sin roles en el
proyecto: `sheets-lectura@dicsys-core-public.iam.gserviceaccount.com`, con el JSON de
`GOOGLE_SHEETS_CREDENTIALS_PATH` (en Docker, `secrets/sheets-lectura.json` montado en
`/app/secrets/sheets-service-account.json`). Si la variable está vacía, usa la del bucket
(`GCS_CREDENTIALS_PATH`) y, si esa también, las credenciales del entorno.

La API de Google Sheets ya está habilitada en `dicsys-core-public`. Para leer un Sheet
alcanza con compartirlo con el mail de la cuenta como **Lector** (F18-P08); compartir una
carpeta da acceso a todo lo que tiene adentro.

## Avisos

Se configuran en **Configuración**, en las pestañas **Recordatorios** y **Canales** (D-93).
Es configuración global del submódulo, una fila por empresa (D-64), y todo arranca apagado.
Las pestañas Fuente de datos, Recordatorios y Canales guardan la misma configuración: el
botón Guardar de cualquiera la guarda entera.

- **Recordatorios (D-66):**
  - al abrir;
  - el día anterior al cierre;
  - cada 1 o cada 2 días (se elige uno o ninguno);
  - hora de envío en hora Argentina (por defecto, 09:00).
- **Canales (D-63, D-77):**
  - **Email** al email corporativo del evaluador, con CC opcional. Solo sale si el mail
    es `@dicsys.com` o `@dicsys.ai` (`WEBEX_SYNC_ALLOWED_DOMAINS`).
  - **Webex personal:** mensaje directo al evaluador.
  - **Webex en canal:** un resumen por room.
  - **Probar canales** (D-94): en la pestaña Canales se elige un evaluador y se le manda
    de verdad su aviso, marcado `[Prueba]`, por los canales tildados en pantalla (aunque no
    estén guardados). Con «Webex en canal» tildado también publica el resumen en el room,
    marcado. Pide confirmación y muestra el resultado por canal. No cuenta como aviso: no
    entra en el historial ni frena los del job; queda en la auditoría (`probar_canales`).
- **Formato:**
  - **Email:** HTML con la marca de Dicsys Core (D-96): encabezado con el nombre de la app en
    los azules del tema, el período y el cierre, la lista de pendientes, el botón «Ir a
    Evaluación de Proveedores» y un pie. Usa el layout común `backend/core/email_layout.py`
    (D-97), el mismo de los mails de bienvenida y de restablecer contraseña.
  - **Webex (personal y canal):** solo Adaptive Card (D-95): título, pendientes y botón al
    tablero; en el room, la lista de evaluadores con sus pendientes. El texto plano queda
    como texto alternativo (lo que muestra la notificación).
  - En las pruebas, la nota `[Prueba]` va destacada en amarillo en los dos formatos.
    Endpoint: `POST /api/v1/evaluaciones-proveedores/seguimiento/probar`.
  - **Errores de Webex:** se muestran legibles en vez del JSON de la API, con
    `describir_error` de `backend/core/webex.py` (D-97), que comparten cumpleaños e innovación. Los conocidos
    dicen qué hacer: el bot no es miembro del equipo del room (hay que invitarlo al equipo),
    el room no existe o el token del bot no es válido.
- **Contenido:** el mensaje lo arma el servidor con los pendientes del momento. Nunca se
  le avisa a quien está al día.
- **Seguimiento:** muestra el avance por evaluador, la vista previa del mensaje, el envío
  manual a una selección, el resultado por evaluador y canal, y el historial de avisos.
- **Job diario:** lo corre el motor de tareas (F19, ver `docs/modulos/tareas.md`) como tarea
  «continua»: cada minuto, pasada la hora configurada, **encola** los avisos que correspondan
  ese día (un solo motivo por día: apertura, después el día anterior al cierre, después el
  recordatorio). La cola los despacha con reintentos (1, 5 y 15 minutos); lo que agota los
  reintentos queda en error en el historial de avisos, se alerta por Webex y se puede
  reintentar desde Configuración → Tareas programadas → Envíos. Con los checks apagados no
  manda nada. El envío manual desde Seguimiento y la prueba de canales salen en el momento,
  sin cola, para ver el resultado.

## Auditoría

Tabla `proveedores_auditoria`, append-only (D-67). Registra cada alta, edición, cambio de
estado y eliminación del registro, de las oficinas, de los contactos y de los documentos.
También:

- los adjuntos;
- los cambios de configuración;
- la creación, eliminación y cambios de fechas de campañas (con la ampliación del cierre);
- cada evaluación;
- las importaciones confirmadas;
- los envíos de avisos.

Cada evento guarda usuario, IP, navegador y los valores antes/después (solo lo que
cambió).

La API la llama el frontend Flask, no el navegador. Por eso `api_request` y los relays del
módulo reenvían la IP real (`request.remote_addr` con ProxyFix) y el navegador en
`X-Cliente-IP` y `X-Cliente-User-Agent`.

## Código

| Capa | Archivos |
|---|---|
| Modelos | `backend/modules/administracion/proveedores_models.py` (10 tablas); los cambios de esquema, en revisiones de Alembic (`backend/migraciones/versions`, ver [Migraciones.md](../Migraciones.md)) |
| Registro | `proveedores_schemas.py`, `proveedores_services.py`, `proveedores_routers.py` (`/api/v1/proveedores`), `proveedores_adjuntos.py` (tipos y claves del storage), `proveedores_miniaturas.py` |
| Evaluación | `evaluacion_proveedores_schemas.py`, `evaluacion_proveedores_services.py`, `evaluacion_proveedores_importacion.py`, `evaluacion_proveedores_avisos.py`, `evaluacion_proveedores_tareas.py` (avisos y auto-generación), `evaluacion_proveedores_routers.py` (`/api/v1/evaluaciones-proveedores`) |
| Compartido | `proveedores_comun.py` (hora Argentina, evaluación activa), `proveedores_auditoria.py`, `backend/core/google_sheets.py`, `backend/core/domicilio.py` |
| Menú | `backend/core/registry.py` (ítems con hijos), `permisos/menu_routers.py`, `core/base.html` |
| Frontend | `frontend/modulos/administracion/proveedores_routes.py` (páginas y relays JSON con permiso propio) y los templates `proveedores_list.html`, `proveedores_view.html`, `proveedores_form.html`, `evaluaciones_proveedores.html`, `evaluacion_proveedor_view.html`, `evaluacion_proveedor_form.html`, `config_evaluaciones_proveedores.html` y `partials/proveedores_macros.html` |

## Tests

- Backend:
  - `backend/tests/integration/test_proveedores_registro.py`
  - `test_evaluacion_proveedores.py`
  - `test_evaluacion_proveedores_importacion.py`
  - `test_evaluacion_proveedores_avisos.py`
  - `test_evaluacion_proveedores_autogeneracion.py`
  - `test_menus_anidados.py`
  - `backend/tests/services/test_google_sheets.py`
- Frontend:
  - `frontend/tests/smoke/test_proveedores.py`
  - `test_menu_anidado.py`
  - `test_api_request.py`
  - `node --test frontend/tests/proveedores_check.cjs`
