# Recruiting

Migración por pantallas del módulo original (`moduloRecluit/modulo-recluiter`, solo lectura mientras dure la
migración) al Core. Las pantallas se migran de a una y cada ítem del menú lleva su `ruta` recién cuando su pantalla
existe; los pendientes se ven como «Próx.».

Código: `backend/modules/recruiting/` (`models.py`, `routers.py`, `schemas.py`, `services.py`, más
`manager_dashboard.py`, `pipeline_services.py`, `parametros_services.py`, `headline_cv.py`, `pdf_texto_cv.py` y `historial_cargas_services.py`) y
`frontend/modulos/recruiting/`. Permisos: `recruiting` y `recruiting.<ítem>`; cada endpoint exige el de su ítem.

| Ítem | Estado |
|---|---|
| Dashboard Recruiting (y Manager Dashboard, solo administradores) | migrado |
| Candidatos | migrado (ver abajo) |
| Búsquedas | migrado (ver abajo) |
| Pipeline | migrado (ver abajo) |
| Parámetros | migrado (ver abajo) |

## Candidatos (`recruiting.candidatos`, `/recruiting/candidatos`)

Pantallas: listado con filtros y paginación del servidor, alta, ficha (ver y editar), baja lógica, carga de CV
individual (con modal de comparación si el email ya existe con otro CV), carga masiva en segundo plano (CV sueltos,
`.zip` o `.rar`) y subida de CV a un candidato existente.

### API (`/api/v1/recruiting`, `operation_id` `recruiting_candidatos_<acción>`)

| Método y ruta | Qué hace |
|---|---|
| `GET /candidatos` | Listado paginado (`pagina`, `por_pagina`) con `busqueda`, `estado`, `fuente`, `seniority`, `ubicacion`, `puesto`, `categorias`, `skills` |
| `POST /candidatos` | Alta; con el email de uno existente actualiza esa ficha (400 si la cargó otro usuario) |
| `GET/PUT/DELETE /candidatos/{id}` | Ficha, edición y baja lógica |
| `POST /candidatos/{id}/cv` | Sube el CV (PDF, DOC o DOCX, hasta 2 MB) |
| `POST /candidatos/cargar-cv`, `/actualizar-cv` | Carga un CV, extrae los datos y crea (o actualiza) el candidato; 409 con `requiere_comparacion` si el email existe con un CV distinto |
| `POST /candidatos/cargar-cv-masivo` | Carga masiva sincrónica (API; la pantalla usa la de segundo plano). Siempre 200: un problema del lote llega con `ok` en false y el motivo en `errores` |
| `POST /candidatos/cargar-cv-masivo/iniciar`, `GET .../{lote}/estado`, `POST .../{lote}/cancelar` | Carga masiva en segundo plano y su avance |
| `GET /candidatos/permisos`, `GET /candidatos/perfiles-puesto` | Acciones habilitadas del usuario y perfiles para el combo «Puesto» |
| `GET /skills`, `/habilidades`, `/niveles-seniority`, `/provincias`, `/ciudades` | Catálogos de solo lectura para los combos (su ABM es de Parámetros) |

### Reglas

- **Empresa activa del JWT**: toda consulta filtra por `empresa_id`; un candidato de otra empresa responde 404.
- **Visibilidad** (`aplicar_filtro_ownership_candidatos`): administradores y grupos de Recruiting (nombre con
  «recruit», «reclut» o «recluit») ven todos los candidatos; cualquier otro usuario, el grupo EXTERNOS incluido, solo
  los que cargó él (`creador_id`). Otro usuario recibe 403 al abrir una ficha ajena.
- **EXTERNOS**: no elimina candidatos ni carga CV desde el listado general (solo desde una búsqueda asignada, que se
  migra con Búsquedas).
- **Ubicación**: provincia y ciudad salen del catálogo; la ciudad debe ser de la provincia elegida y arma el texto
  `Ciudad, Provincia`.
- **Datos nuevos sin tildes** (provincias, ciudades, localidades detectadas en un CV).
- **CV**: se guardan en `recruiting/cv/…` del storage; los archivos de un lote se archivan en
  `cv_procesados_ok`, `cv_errores` y `cv_duplicados` (carpeta `CV_STORAGE_DIR`, `/data/cv`, volumen `./data/cv`), y cada carga queda en `recruiting_historial_cargas_cv`.

### Dependencias propias de la carga de CV

`python-docx` (texto de `.docx`), `rarfile` más `unrar-free` en la imagen (`.rar`), `rapidocr` + `onnxruntime` (OCR de
las páginas escaneadas de un PDF; el modelo de reconocimiento se descarga y verifica por SHA256 al construir la
imagen) y `libreoffice-writer` (vista previa en PDF de un CV Word, `GET/POST /storage/preview-pdf`). Si falta una,
la carga sigue con lo que tenga: el OCR y la vista previa nunca hacen fallar una carga.

### Acciones de Candidatos que viven en Pipeline

- **Asignar a una búsqueda** desde el listado (`GET /candidatos/{id}/busquedas-elegibles`): búsquedas Abiertas
  compatibles por skills (70 %) y seniority (30 %), sin las ya asignadas; 403 para EXTERNOS.
- **Ver detalles** del pipeline de un candidato (`GET /candidatos/{id}/pipelines`, solo los que ya tienen movimientos);
  `tiene_pipeline` viene en cada fila del listado.
- `GET /candidatos/{id}/postulaciones`, `GET /candidatos/{id}/historial` (auditoría de las postulaciones, sin responsable
  ni observaciones para EXTERNOS) y `POST /postulaciones/{id}/rechazar` (motivo obligatorio; 409 si la búsqueda está
  Ganada). Son API: el original no tiene pantalla que los use.

## Búsquedas (`recruiting.oportunidades`, `/recruiting/oportunidades`)

La tabla es `recruiting_oportunidades` (modelo `Solicitud`, alias `Oportunidad`); no hubo cambios de esquema.

Pantallas: listado con filtros (texto, estado, tipo) y paginación del servidor, alta, ficha (ver y editar en el
lugar) y, dentro de la ficha, asignar reclutador (del catálogo de Parámetros) o tomar y liberar la búsqueda, asignar o
quitar el usuario externo, los candidatos de la búsqueda y las sugerencias de Smart Matching con el botón de postular.
Cancelar una búsqueda es pasarla al estado Cancelada (nunca se borra).

### Frontend (Vue)

Las tres pantallas son Vue (`frontend-vue/src/modules/recruiting/busquedas/`, `busqueda-nueva/`, `busqueda-detalle/`) y
hablan con `/api/v1/recruiting`. Las URLs de siempre (`/recruiting/oportunidades`, `/nueva`, `/<id>`, `/<id>/editar`)
redirigen a `/v2/...` conservando los parámetros, con el ítem `recruiting.oportunidades` validado en Flask y en la API.
Los avisos que antes daba el «flash» de Flask (sin permiso de crear, búsqueda inexistente o no asignada) viajan al
listado por `sessionStorage` (`busquedas/aviso.ts`).

Lo que sigue en Flask, y por qué:

- `POST /recruiting/oportunidades/<id>/cargar-cv` y `/actualizar-cv`: la carga de CV desde una búsqueda asignada
  (EXTERNOS) es multipart y el proxy `/api/v1` no lo soporta. El equivalente de la API es
  `POST /oportunidades/{id}/candidatos/cargar-cv`. Se puede eliminar si el proxy pasa a aceptar archivos.
- `POST /recruiting/oportunidades/<id>/candidatos` (y `/oportunidades/<id>/agregar-candidato`): los usa
  `oportunidad_agregar_candidato.html`, del Pipeline. Se eliminan al migrar Pipeline.
- `POST|PUT /recruiting/oportunidades...` de asignar, editar, reclutador y externo: ya no los usa ninguna
  plantilla ni pantalla Vue (verificado con una búsqueda en `templates/`); quedan sin uso y se pueden borrar junto con
  sus tests de `test_recruiting_oportunidades.py`.

### API (`/api/v1/recruiting`, `operation_id` `recruiting_oportunidades_<acción>`)

| Método y ruta | Qué hace |
|---|---|
| `GET /oportunidades` | Listado paginado (`pagina`, `por_pagina`) con `busqueda`, `estado`, `cliente`, `tipo` |
| `POST /oportunidades` | Alta (403 para EXTERNOS; 400 si el estado o el puesto no son válidos o ya existe el título para el cliente) |
| `GET/PUT /oportunidades/{id}` | Ficha y edición parcial (409 si está Ganada) |
| `POST /oportunidades/{id}/asignar`, `/desasignar` | El reclutador toma la búsqueda o la libera |
| `POST /oportunidades/{id}/reclutador` | Asigna o reasigna el reclutador con un nombre activo del catálogo |
| `PUT/DELETE /oportunidades/{id}/externo` | Asigna, reemplaza o quita el usuario externo (admin y grupos de Recruiting) |
| `GET /oportunidades/{id}/candidatos` | Candidatos del pipeline de la búsqueda (anónimos los que un EXTERNOS no presentó) |
| `GET /oportunidades/{id}/candidatos-compatibles` | Smart Matching (`q` opcional); 403 para EXTERNOS |
| `POST /oportunidades/{id}/candidatos` | Suma un candidato a una búsqueda Abierta (postulación y pipeline) |
| `DELETE /oportunidades/{id}/candidatos/{candidato_id}` | Lo quita de la búsqueda sin tocar su ficha |
| `GET /oportunidades/permisos`, `/externos-disponibles`, `/lideres`, `/reclutadores`, `/config` | Acciones habilitadas y catálogos de solo lectura (el umbral de Smart Matching se edita en Parámetros) |

### Reglas

- **Empresa activa del JWT**: una búsqueda de otra empresa responde 404.
- **Visibilidad**: todos los usuarios con el ítem ven todas las búsquedas; el grupo EXTERNOS solo las que tiene
  asignadas (`externo_id`, 403 al abrir otra) y solo las de tipo Efectiva. No crea, cancela ni asigna candidatos ni
  reclutadores, y no ve el líder, el tipo ni Smart Matching.
- **Búsqueda Ganada = cerrada**: no admite cambios, asignaciones ni candidatos (409). Pasa a Ganada sola cuando un
  candidato llega a Ingreso.
- **Contadores del embudo** (`candidatos_pipeline`, `coordinando_entrevista`...): salen del Pipeline real
  (`recruiting_gestionBusqueda`), no dependen de quién consulta, no cuentan descartados y el listado y el detalle los
  calculan al responder. Se persisten al sumar, quitar, mover o descartar un candidato. Coordinando = Candidato y
  Screening; Entrevistados RRHH = Entrevista RRHH; Presentación al líder = Entrevista Líder Dicsys; Feedback líder =
  Validación Administración; Presentación al cliente = Entrevista Cliente; «Candidatos en Pipeline» y Q Activos = todos
  los que no están descartados.
- **Modalidad y prioridad** se guardan sin tildes (`Hibrido`, `Critica`) y la pantalla las muestra con su tilde.
- **Dependencia de permisos**: los combos del formulario (skills, habilidades, perfiles de puesto) salen de los
  catálogos de Candidatos, así que quien usa Búsquedas necesita también `recruiting.candidatos`.

## Pipeline (`recruiting.gestion_busquedas`, `/recruiting/gestion-busquedas`)

Código: `backend/modules/recruiting/pipeline_services.py` (`PipelineService`, `MotivoDescarteService`,
`PostulacionService`, `AltaEnBusquedaService`, `CandidatoDuplicadoService`). No hubo cambios de esquema: usa
`recruiting_gestionBusqueda`, `recruiting_historial_pipeline`, `recruiting_etapa_archivos`, `recruiting_etapas`,
`recruiting_motivos_descarte*` y `recruiting_candidatos_duplicados`.

Pantallas: vista global (una fila por búsqueda Abierta con los candidatos por columna y el detalle al pasar el mouse),
selección individual, Pipeline de una búsqueda (tabla por etapa, mover de etapa con adjunto, descartar con motivo,
reingresar), ficha del pipeline de un candidato (historial y adjuntos), «Agregar candidato» y, en el Dashboard, la
revisión de CV duplicados. El filtro «Candidatos: Todos / Propios» aplica a las tres vistas.

### Frontend (Vue)

La vista global, la selección individual y el Pipeline de una búsqueda son Vue
(`frontend-vue/src/modules/recruiting/pipeline/`: `PipelinePage.vue` y `PipelineBusquedaPage.vue`). Las URLs de siempre
(`/recruiting/gestion-busquedas`, `/asignar-candidato` y `/oportunidades/<id>/pipeline`) redirigen a `/v2/...`
conservando sus parámetros (`vista`, `alcance_candidatos`, `etapas`, `columna`), con el ítem
`recruiting.gestion_busquedas` validado en Flask (también en `/v2`) y en la API. Las consultas van por el proxy
`/api/v1/recruiting`. Una búsqueda que no se puede abrir vuelve a Pipeline con el aviso (`busquedas/aviso.ts`). El ítem
del menú apunta a `/recruiting/asignar-candidato` (la URL que arma `url_for` para ese endpoint): la ruta Vue la tiene
como alias, y `/v2/recruiting/asignar-candidato` exige el mismo permiso. En el Pipeline de una búsqueda se resalta
«Pipeline», no «Búsquedas» (`meta.itemMenu` de la ruta).

Lo que sigue en Flask, y por qué:

- `PUT|POST /recruiting/oportunidades/<id>/candidatos/<cid>/etapa`: mover, descartar y reingresar. Con un adjunto es
  multipart (el proxy `/api/v1` no lo soporta): guarda el cambio y después el archivo, con las mismas validaciones.
- La ficha del pipeline de un candidato («Ver Detalles», `candidato_pipeline_detalle.html`) y «Agregar candidato»
  (`oportunidad_agregar_candidato.html`) siguen siendo pantallas Flask: la Vue enlaza a ellas como antes.
- `GET /recruiting/motivos-descarte` y `/oportunidades/<id>/pipeline-columna/<columna>`: ya no los usa ninguna pantalla
  (la Vue va a la API). `pipeline.html`, `asignar_candidato_hub.html` y sus parciales `_pipeline_*.html` quedan sin uso;
  se borran junto con esas rutas cuando se confirme la migración.

### API (`/api/v1/recruiting`, `operation_id` `recruiting_pipeline_<acción>`)

| Método y ruta | Qué hace |
|---|---|
| `GET /pipeline-permisos` | Acciones habilitadas (la usan Pipeline, Candidatos, Búsquedas y Dashboard) |
| `GET /pipeline-resumen` | Vista global: candidatos por columna (`estado`, `alcance_candidatos`) |
| `GET /oportunidades/{id}/pipeline-candidatos`, `/pipeline-contadores` | Tabla y contadores por etapa (`etapa`, `alcance_candidatos`) |
| `GET /oportunidades/{id}/pipeline-columna/{columna}` | Candidatos de una columna de la vista global |
| `GET /motivos-descarte?etapa=` | Motivos de descarte de la etapa (sin motivos propios, los de Screening) |
| `PUT /oportunidades/{id}/candidatos/{cid}/etapa` | Mover, descartar o reingresar |
| `GET /oportunidades/{id}/candidatos/{cid}/historial` | Movimientos del candidato en la búsqueda |
| `POST/GET /oportunidades/{id}/candidatos/{cid}/archivos-etapa`, `GET /archivos-etapa/{id}/descargar` | Adjuntos de etapa (hasta 10 MB) |
| `POST /oportunidades/{id}/candidatos/cargar-cv`, `/actualizar-cv`, `/nuevo` | Alta desde la búsqueda asignada (solo EXTERNOS) |
| `GET /candidatos-duplicados`, `GET .../{id}`, `POST .../{id}/resolver` | Revisión de CV duplicados (solo internos) |

Permisos: cada endpoint exige `recruiting.gestion_busquedas`, salvo los que comparten pantalla (ficha del pipeline,
historial y adjuntos: Pipeline o Candidatos; permisos: cualquiera de Pipeline, Candidatos, Búsquedas o Dashboard; alta
desde la búsqueda: Búsquedas; duplicados: Dashboard).

### Reglas

- **Flujo**: Candidato → Screening → Entrevista RRHH → Entrevista Líder Dicsys → Validación Administración → Entrevista
  Cliente → Oferta → Examen Médico Preocupacional → Ingreso. Se avanza a la etapa siguiente o a un salto permitido
  (Líder → Cliente, Validación → Oferta, Cliente → Examen); no hay retrocesos. Los nombres viejos (Postulado, Entrevista
  Técnica) se normalizan.
- **Descarte** desde cualquier etapa activa, con un motivo del catálogo de esa etapa. Un descartado solo reingresa a
  Entrevista RRHH, con el motivo de reingreso obligatorio.
- **Pretensión salarial bruta** (entero positivo, ARS) obligatoria al pasar de Entrevista RRHH a Entrevista Líder Dicsys.
- **Observación** de un movimiento: hasta 50 caracteres (el descarte no tiene límite).
- **Ingreso cierra la búsqueda** (Ganada) en la misma transacción; una Ganada no admite movimientos (409). El único
  adjunto que admite es el del movimiento a Ingreso que la cerró (mismo usuario, dentro de 10 minutos, uno por candidato).
- **Cada movimiento** deja su fila en `recruiting_historial_pipeline`.
- **EXTERNOS**: ven la tabla de sus búsquedas asignadas con los candidatos que no presentaron anónimos; no mueven,
  descartan, adjuntan ni ven adjuntos, motivos, responsables ni salarios.
- **Alta de EXTERNOS desde su búsqueda**: crea la ficha a su nombre y la asocia (la búsqueda debe estar Abierta). Con el
  email de un candidato existente y el mismo CV asocia la ficha; con un CV distinto la asocia, guarda el CV nuevo en
  `recruiting/cv_duplicados` y avisa por la campana a los grupos de Recruiting; Recruiting compara y conserva el CV
  actual o actualiza la ficha.

### Diferencias con el original

- «Agregar candidato» y la asignación desde Candidatos usan `POST /oportunidades/{id}/candidatos` (postulación y fila del
  pipeline); el original también tenía `POST /oportunidades/{id}/pipeline-candidatos` (solo la fila), que no se migró.
- No se migró `PUT /postulaciones/{id}/etapa` ni `GET /oportunidades/{id}/pipeline` (métricas del embudo): ninguna
  pantalla los usa.
- Los listados de `GET /candidatos/{id}/postulaciones` no crean una postulación de ejemplo cuando el candidato no tiene
  (el original lo hacía al consultar).
- El modal «Postular a Búsqueda» de la ficha del candidato era una simulación sin llamada real; no se migró.
- Alta de EXTERNOS: el original aceptaba cualquier búsqueda no Ganada; el Core exige Abierta, como el resto de las
  asignaciones.

## Parámetros (`recruiting.parametros`, `/recruiting/parametros`)

Código: `backend/modules/recruiting/parametros_services.py` (catálogos, Smart Matching, carpetas de CV, limpieza e
historial), `backup_services.py` e `importacion_backup_services.py` (respaldo y restauración) y `backup_schemas.py`. No
hubo cambios de esquema. Todos los endpoints exigen `recruiting.parametros` y excluyen al grupo EXTERNOS (403); los de
alcance global o destructivos, además, rol administrador.

Pantallas (pestañas): Porcentaje de aceptación (Smart Matching), Skills / Tecnologías, Habilidades / Competencias,
Provincias, Ciudades, Líderes, Reclutadores, Perfiles profesionales, Archivos de CV e Historial de cargas de CV
(administradores).

### API (`/api/v1/recruiting/parametros`, `operation_id` `recruiting_parametros_<catálogo>_<acción>`)

| Método y ruta | Qué hace |
|---|---|
| `GET/PUT /config` | Porcentaje mínimo de Smart Matching de la empresa (1 a 100, por defecto 50) |
| `GET/POST /skills`, `/habilidades`, `/lideres`, `/reclutadores`, `/perfiles-puesto`; `PUT/DELETE .../{id}` | ABM con baja lógica (`activo_only`, `q`) |
| `GET/POST /provincias`, `/ciudades`; `PUT/DELETE .../{id}` | ABM con borrado físico (409 si tiene ciudades o está en uso) |
| `GET /archivos-cv`, `GET /archivos-cv/{carpeta}` | Cantidad y tamaño por carpeta; archivos con `pagina`, `por_pagina` (hasta 200) y `buscar` |
| `GET /archivos-cv/{carpeta}/descargar`, `.../descargar-todos` | Un CV original o la carpeta completa en ZIP |
| `POST /archivos-cv/limpiar-bd` | Limpia candidatos, búsquedas, pipeline y CV (administradores, con confirmación) |
| `POST /archivos-cv/backup/iniciar`, `GET .../{id}/estado`, `GET .../{id}/descargar` | Backup completo (base y CV) en segundo plano (administradores) |
| `POST /archivos-cv/importar/subir`, `GET .../{id}/estado`, `POST .../{id}/confirmar`, `DELETE .../{id}` | Validar y restaurar un backup (administradores) |
| `GET /historial-cargas-cv`, `GET /historial-cargas-cv/{id}` | Auditoría de las cargas de CV de la empresa activa (administradores) |

### Reglas

- **Catálogos globales**: skills, habilidades, líderes, reclutadores, perfiles, provincias y ciudades no llevan `empresa_id`
  (como en el original). Smart Matching y el historial sí son por empresa.
- **Nombres únicos** sin distinguir mayúsculas (provincias y ciudades, también sin tildes). **Los nombres nuevos o
  editados se guardan sin tildes** (la ñ se conserva); uno sin cambios se deja como estaba.
- **Baja lógica** de skills, habilidades, líderes, reclutadores y perfiles: los candidatos y las búsquedas guardan el nombre
  como texto, así que desactivar no los altera.
- **Carpetas de CV** (`cv_procesados_ok`, `cv_duplicados`, `cv_errores` en `CV_STORAGE_DIR`): globales y de solo lectura; el
  cliente nunca manda una ruta, solo la carpeta (lista fija) y un nombre simple de archivo regular.
- **Limpiar, respaldar e importar** abarcan todas las tablas `recruiting_*` y las carpetas de CV de todas las empresas, por
  eso son de administradores. La restauración reemplaza los datos de Recruiting, exige texto de confirmación y aceptar las
  limitaciones, y revierte ante cualquier error.

### Diferencias con el original

- «Solo admin@admin.com» pasa a «rol administrador» (limpiar, respaldar, importar e historial).
- La restauración solo crea las empresas y usuarios que faltan (sin secretos: el usuario creado no puede ingresar hasta
  que se le resetee la clave) y no restaura grupos ni accesos. Un backup de RECLUIT se rechaza si su `core_usuarios` o
  `core_empresas` tiene columnas que el Core no tiene.
- Las rutas del ABM pasaron de `/recruiting/skills`... a `/recruiting/parametros/skills`...: las de solo lectura que usan
  los combos de Candidatos y Búsquedas no cambian.
- `GET /recruiting/api/dashboard`, `/areas` y el resto de lo que no es Parámetros no se tocaron.
