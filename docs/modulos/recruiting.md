# Recruiting

Migración por pantallas del módulo original (`moduloRecluit/modulo-recluiter`, solo lectura mientras dure la
migración) al Core. Las pantallas se migran de a una y cada ítem del menú lleva su `ruta` recién cuando su pantalla
existe; los pendientes se ven como «Próx.».

Código: `backend/modules/recruiting/` (`models.py`, `routers.py`, `schemas.py`, `services.py`, más
`manager_dashboard.py`, `pipeline_services.py`, `headline_cv.py`, `pdf_texto_cv.py` y `historial_cargas_services.py`) y
`frontend/modulos/recruiting/`. Permisos: `recruiting` y `recruiting.<ítem>`; cada endpoint exige el de su ítem.

| Ítem | Estado |
|---|---|
| Dashboard Recruiting (y Manager Dashboard, solo administradores) | migrado |
| Candidatos | migrado (ver abajo) |
| Búsquedas | migrado (ver abajo) |
| Pipeline | migrado (ver abajo) |
| Parámetros | pendiente |

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
- **Contadores del embudo** (`candidatos_pipeline`, `coordinando_entrevista`...): se recalculan al sumar o quitar un
  candidato, sobre todas las postulaciones vigentes (no dependen de quién consulta).
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
