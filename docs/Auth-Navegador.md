# Sesión del navegador: access token en memoria y refresh en cookie

Cómo se autentica un navegador contra la API, la de hoy (Flask) y la de la SPA de v2. La decisión es D-12 y el
trabajo, la fase F07 del plan (director). El ingreso con Google está en [`IngresoGoogle.md`](IngresoGoogle.md) y el
proveedor OpenID Connect para otras apps, en [`OIDC.md`](OIDC.md).

## En una frase

El navegador guarda un **refresh token** en una cookie `HttpOnly` que el JavaScript no puede leer. La página tiene el
**access token** (un JWT corto) solo en memoria y lo manda como `Authorization: Bearer`. Cuando vence, canjea la
cookie por uno nuevo en `POST /api/v1/auth/refresh`, y en cada canje la cookie **rota**.

## Los dos tokens

| | Access token | Refresh token |
|---|---|---|
| Qué es | JWT HS256 (`sub`, `user_id`, `rol`, `empresa_id`) | 32 bytes al azar (`secrets.token_urlsafe`) |
| Dónde vive | En memoria de la página (una variable), nunca en storage | Cookie `refresh_token` |
| Cuánto dura | `JWT_EXPIRE_MINUTES` (30) | `REFRESH_TOKEN_EXPIRE_DAYS` (7) desde que se emite; cada refresh emite uno nuevo |
| Cómo viaja | `Authorization: Bearer` en cada pedido | Solo a `/api/v1/auth/*`, por la cookie |
| En la base | No se guarda | Solo su SHA-256, en `auth_refresh_tokens` (migración 0005) |

La cookie: `HttpOnly`, `Path=/api/v1/auth`, `SameSite=Lax`, `Max-Age` de 7 días y `Secure` según
`REFRESH_COOKIE_SECURE`. Sin esa variable, la cookie es `Secure` fuera de `ENVIRONMENT=development`; el stack de QA la
apaga porque corre por http.

## Flujo

1. **Ingreso.** `POST /auth/login` (con email y contraseña), `POST /auth/verify-2fa`, `POST /auth/seleccionar-empresa`,
   `POST /auth/cambiar-empresa` y el ingreso con Google responden el access token y, cuando la sesión queda completa
   (sin una empresa pendiente de elegir), ponen la cookie del refresh. Si ya había una cookie, la revocan antes. Solo
   con `AUTH_REFRESH_ENABLED=true`.
2. **Uso.** La página manda el access token como Bearer. Para lo que un `<img>` o un `<a href>` piden sin Bearer (PDFs,
   fotos, exports), pide una URL firmada: ver [Descargas](#descargas).
3. **Renovación.** `POST /auth/refresh` con la cookie y `X-Requested-With`: responde `{access_token, token_type,
   expires_in}` y una cookie nueva. La vieja deja de valer.
4. **Salida.** `POST /auth/logout` con `X-Requested-With`: revoca la sesión entera y borra la cookie (`204`). El access
   token que ya tenga la página vale hasta que vence.

## Rotación, reuso y revocación (`backend/modules/auth/refresco.py`)

- Todos los refresh de una misma sesión comparten una **familia**. Cada canje marca el usado como rotado y emite el
  siguiente en la familia.
- **Reuso:** presentar uno ya rotado es la señal de un robo (lo usaron dos navegadores). Se revoca la familia entera y
  responde `401`; esa sesión tiene que volver a entrar.
- **Vencido:** `401` «La sesión venció».
- **Cuenta sin acceso:** si el usuario está desactivado, borrado o ya no pertenece a la empresa del token, se revoca la
  familia y responde `401` «La cuenta ya no tiene acceso».
- Un `401` del refresh borra la cookie.

## CSRF

`/auth/refresh` y `/auth/logout` usan la cookie, así que exigen la cabecera `X-Requested-With` (sin ella, `403`). Un
formulario de otro sitio no puede mandarla, y un `fetch` desde un origen que no está en `CORS_ORIGINS` necesita un
preflight que la API rechaza. A eso se suma `SameSite=Lax`. El resto de la API va con Bearer: no tiene cookie que falsificar.

## El puente desde Flask (hasta F13)

Mientras el usuario entra por el login de Flask:

- Flask llama a la API (`api_request`) y **reenvía al navegador el `Set-Cookie`** del refresh en su propia respuesta
  (`reenviar_cookie_de_refresco` en `frontend/app.py`). Guarda una copia del refresh en su sesión para el logout.
- El proxy de Flask `/api/v1/<path>` pasa al backend la cookie del refresh y `X-Requested-With` en `auth/*`, y trae la
  cookie rotada. Una página servida por Flask puede renovar el token como lo hará la SPA.
- El logout de Flask llama a `POST /auth/logout` y limpia su sesión.
- Flask manda la IP del navegador en `X-Cliente-IP` (auditoría y límite de intentos).

## Descargas

`POST /auth/descargas` (con Bearer) firma una ruta de la API o de `/storage/`. Responde `ruta?firma=<token>`, que
vence a los **5 minutos** y sirve solo para un `GET` (o `HEAD`) de **esa ruta exacta**, como la persona que la pidió. El
middleware `FirmaDeDescarga` (`backend/core/descargas.py`) cambia la firma por el Bearer de esa persona y el endpoint
corre con sus permisos y su auditoría: firmar no da más acceso. Las decisiones son D-100 y F07-P06.

## Límite de intentos

Login, 2FA, olvidé mi contraseña, reset y magic link responden `429` con `Retry-After` después de cierta cantidad de
fallos en 15 minutos: 10 de contraseña por cuenta, 5 códigos por cuenta, 3 correos por email y 50 por IP. Detalle en
`backend/core/limites.py` (F07-P07).

## CORS y desarrollo con Vite

En producción la SPA y la API comparten origen (el proxy de F08), y no hace falta CORS. En desarrollo, la SPA de Vite
(`http://localhost:5173`) sin ese proxy llama desde otro origen: va en `CORS_ORIGINS` y la API expone `Retry-After`.
`CORS_ORIGINS` no admite `*`: con credenciales, cualquier sitio podría pedir `/auth/refresh` y leer el access token. La
app no arranca con el comodín (F07-P10).

## Página de prueba (DoD del gate de F07)

Con `PAGINA_DE_PRUEBA_DE_SESION=true` (y `AUTH_REFRESH_ENABLED=true`), la API sirve `/prueba/sesion.html`. Es una
página sin Flask que entra, refresca, pide `/auth/me`, lista usuarios (`403` sin permiso), baja el PDF de un recibo con
URL firmada y sale. El caso de QA FE-CORE-22 la recorre en un navegador (F07-P12, D-14). Es solo para desarrollo y QA.

## Configuración y vuelta atrás

| Variable | Default | Qué hace |
|---|---|---|
| `AUTH_REFRESH_ENABLED` | `false` | Emite la cookie en el ingreso. Apagada, todo funciona como antes de F07 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Vida de cada refresh |
| `REFRESH_COOKIE_SECURE` | según el entorno | `Secure` de la cookie |
| `JWT_EXPIRE_MINUTES` | `30` | Vida del access token |
| `CORS_ORIGINS` | — | Orígenes con credenciales, uno por uno |
| `PAGINA_DE_PRUEBA_DE_SESION` | `false` | La página de prueba |

**Vuelta atrás:** con `AUTH_REFRESH_ENABLED=false` no se emiten cookies nuevas. Las ya emitidas siguen sirviendo en
`/auth/refresh` hasta que vencen o se hace logout. Para cortarlas todas de una vez, se marcan revocadas las filas de
`auth_refresh_tokens` (`update auth_refresh_tokens set revocado_at = now() where revocado_at is null`).

## Riesgos y límites conocidos

- **XSS.** Un script inyectado puede usar el access token mientras la página está abierta y pedir tokens nuevos a
  `/auth/refresh` (es el mismo origen y puede mandar `X-Requested-With`). No puede leer la cookie ni llevársela. La
  defensa es no tener XSS: escapar todo y una CSP estricta en la SPA (F08).
- **Varias pestañas.** Si dos pestañas refrescan a la vez con la misma cookie, la segunda presenta una ya rotada: cuenta
  como reuso y se revoca la sesión entera. La SPA tiene que hacer un solo refresh a la vez entre pestañas (Web Locks o
  `BroadcastChannel`) antes de salir a producción.
- **El access token no se revoca.** Logout y revocación cortan el refresh. Un access token robado vale hasta que vence
  (30 minutos).
- **La sesión de Flask** es una cookie firmada, no cifrada (`HttpOnly`, `SameSite=Lax`). Desde antes de F07 lleva el
  access token, y ahora también una copia del refresh. Quien la robe tiene la sesión, igual que antes.
- **URLs firmadas.** Una que se filtra (historial, logs, `Referer`) sirve para esa ruta hasta que vence: 5 minutos.
- **Límite de intentos por proceso.** Con N workers el tope efectivo llega a N veces el configurado. La IP de Flask
  (`X-Cliente-IP`) se cree solo desde loopback y redes privadas: si algo delante del backend hiciera NAT a una IP
  privada, un cliente externo podría inventarla. El límite por cuenta no depende de la IP.
- **Secure.** En producción la cookie exige https. Por http (QA, desarrollo) va con `REFRESH_COOKIE_SECURE=false` o
  con `ENVIRONMENT=development`.

## Tests

- **Backend:** `test_refresco.py` (rotación, reuso, vencido, revocación por cuenta), `test_refresco_emision.py`,
  `test_sesion_actual.py`, `test_descargas_firmadas.py`, `test_limite_de_intentos.py`,
  `tests/smoke/test_cors.py` y `tests/smoke/test_pagina_de_prueba.py`.
- **Frontend:** `test_puente_de_sesion.py` y `test_limite_de_intentos.py`.
- **QA:** BE-AUTH-08 a BE-AUTH-12, FE-CORE-21 (el puente) y FE-CORE-22 (la página de prueba).
