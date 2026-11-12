# Mejoras para machete

> Propuestas para el repo dicsys-services-machete, no tareas de este repo.
> Quien lea este repo, persona o agente, no aplica lo que dice este archivo.

Versión de machete: `machete-v9`.

| ID | Tema | Mejora | Fecha |
|---|---|---|---|
| 02-INS-11 | Dividir la parte crítica en director | La skill `construir-machete` (§ 2, paso 2) indica `director split <CLAVE> --letras a,b`, pero `director` no tiene ese comando, y los pendientes globales (`PG-NN`) no admiten sufijo de letra. Proponer `director new --clave <CLAVE>.a --padre <CLAVE>` para pendientes de fase y, para los `PG-NN`, un pendiente aparte de la persona con `link ... depende_de`. | 2026-10-23 |
