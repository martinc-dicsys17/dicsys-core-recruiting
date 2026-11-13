# Recruiting

Migración por pantallas del módulo original (`moduloRecluit/modulo-recluiter`, solo lectura mientras dure la
migración) al Core. Las pantallas se migran de a una y cada ítem del menú lleva su `ruta` recién cuando su pantalla
existe; los pendientes se ven como «Próx.».

Código: `backend/modules/recruiting/` (`models.py`, `routers.py`, `schemas.py`, `services.py`, más
`manager_dashboard.py`, `headline_cv.py`, `pdf_texto_cv.py` y `historial_cargas_services.py`) y
`frontend/modulos/recruiting/`. Permisos: `recruiting` y `recruiting.<ítem>`; cada endpoint exige el de su ítem.

| Ítem | Estado |
|---|---|
| Dashboard Recruiting (y Manager Dashboard, solo administradores) | migrado |
| Candidatos | migrado (ver abajo) |
| Búsquedas | migrado, sin etapas (ver abajo) |
| Pipeline, Parámetros | pendientes |

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

### Lo que queda para Pipeline

Asignar un candidato a una búsqueda desde el listado de Candidatos (`busquedas-elegibles`; desde la búsqueda ya se
puede, con Smart Matching), ver los pipelines y las postulaciones de un candidato, rechazar una postulación, el alta de
candidatos desde una búsqueda asignada (EXTERNOS) y la revisión de CV duplicados derivados por esos usuarios
(`CandidatoDuplicado`). El listado y la ficha de Candidatos no ofrecen esas acciones hasta entonces.

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

### Lo que queda para Pipeline

Cambio de etapa, kanban y motivos de descarte, y la pantalla «Agregar candidato» (se llega desde el Pipeline). La
carga de CV y el alta de candidatos desde una búsqueda asignada (EXTERNOS) se migran con la revisión de CV
duplicados, que es lo que recibe los casos que ese flujo deriva.
