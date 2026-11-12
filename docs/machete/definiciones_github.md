# Repositorio y CI/CD — ops-sistema-gestion

Definición: `02 - Definiciones/github.md`. Versión de machete: ver [readme.md](readme.md).

Solo los IDs que el repo ya respondió: la adopción es parcial (ver [readme.md](readme.md)).

| ID | Título | Decisión | Dónde / evidencia | Fecha |
|---|---|---|---|---|
| 02-GHB-06 | Aviso de deploy | PENDIENTE | Paso «Notificar a Webex» en [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml), copiado de `03 - Plantillas/github/deploy.yml` (machete-v9); cambia solo `COMPONENTE`. Falta cargar `WEBEX_BOT_TOKEN` (secret) y `WEBEX_ROOM_DEPLOYS` (var) en el environment `prod`, con los nombres de 02-GHB-02, y verlo en un deploy. Mientras falten, el paso no hace nada. Entra en la release siguiente a 1.22.2; se sigue en director: PG-35 (el paso) y PG-36 (la carga, a cargo de la persona). | 2026-10-23 |
