# Dicsys Core como proveedor OpenID Connect

Desde F21, Dicsys Core identifica personas para otras apps propias. La primera es razorback, que muestra el botón
«Entrar con Dicsys Core». El pedido completo está en `innovacion-razorback-platform/docs/pedido_a_dicsys_core.md`.

Core solo prueba quién es la persona: no maneja la sesión de la otra app, no da acceso a sus APIs (no hay
`refresh_token` ni `userinfo`) y no coordina el cierre de sesión.

## Respuesta al pedido de razorback

| Lo que pide | Respuesta |
|---|---|
| Discovery e issuer | `https://core.dicsys.ai/.well-known/openid-configuration`. El issuer es `https://core.dicsys.ai`, exacto y sin barra final; es el mismo valor que lleva el `iss` de cada token. |
| `client_id` y `client_secret` | Los crea un admin de Core con el comando de [Clientes](#clientes) y los pasa por un canal seguro, nunca por chat ni por mail en claro. |
| Autenticación del cliente en el token endpoint | `client_secret_post` y `client_secret_basic`: valen las dos. |
| Rotación de claves | Con solapamiento. La clave nueva se publica en el JWKS al menos una hora antes de empezar a firmar con ella, y la vieja queda publicada una hora más después del cambio. No hace falta aviso: razorback vuelve a pedir el JWKS cuando ve un `kid` que no conoce. |
| Rotación del secreto | Sin corte: durante la rotación valen el secreto viejo y el nuevo hasta que razorback confirma que ya usa el nuevo. Se avisa con al menos 7 días. |
| Personas de prueba | Las crea un admin en Core: una activa con email `@dicsys.ai` (`email_verified: true`) y una desactivada (`access_denied`). Se puede probar contra producción con el cliente de desarrollo (`http://localhost:5174/auth/core`). |

## Cómo funciona

```
navegador ──► core.dicsys.ai (frontend Flask) ──► backend /api/v1/oidc/*
             /.well-known/openid-configuration      configuracion
             /oidc/jwks                             jwks
             /oidc/authorize                        validar · autorizar · denegar
             /oidc/cancelar                         denegar
             /oidc/token        (server a server)   token
```

El frontend publica los endpoints, porque es el que atiende `core.dicsys.ai`, y le pasa cada pedido a la API interna
del backend, que tiene los clientes, los códigos y las claves. Así anda sin depender de cómo se publique el backend.

**Autorización (código + PKCE).**

- `GET /oidc/authorize` con `response_type=code`, `client_id`, `redirect_uri`, `scope` (con `openid`), `state`,
  `nonce`, `code_challenge` y `code_challenge_method=S256`. El PKCE `S256` y el `nonce` son obligatorios.
- Si no hay sesión de Core, el pedido queda en una cookie firmada que vence a los 10 minutos y la persona va al
  login. El login dice a qué app está entrando y tiene un «Cancelar». Cuando termina, sea con contraseña, con 2FA o al
  configurar el 2FA, retoma la autorización.
- Core vuelve a `redirect_uri?code=...&state=...`.
- Un `client_id` o un `redirect_uri` que no está registrado, con coincidencia exacta, se muestra como error en Core y
  no redirige a ningún lado.
- Los demás errores vuelven al `redirect_uri` con `error`, `error_description` y `state` (RFC 6749 §4.1.2.1):
  - **`access_denied`**: la persona canceló o su cuenta está desactivada.
  - **`invalid_request`**: falta el PKCE o el nonce.
  - **`invalid_scope`**: el `scope` no incluye `openid` o pide algo que el cliente no tiene permitido.
  - **`unsupported_response_type`**: el `response_type` no es `code`.

**Canje (`POST /oidc/token`, form-urlencoded).**

- Parámetros: `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`, y las credenciales del
  cliente en el cuerpo o en `Authorization: Basic`.
- El código es de un solo uso y vence a los 10 minutos. Un intento fallido también lo consume.
- Un código usado, vencido o de otro cliente, o un `redirect_uri` o `code_verifier` que no coinciden, dan `400
  invalid_grant`. Un cliente mal autenticado da `401 invalid_client`.
- La respuesta trae `id_token`, `token_type`, `expires_in` y un `access_token` sin uso (OIDC lo exige, pero ningún
  endpoint de Core lo acepta).

**El `id_token`.** RS256, con el `kid` en el encabezado y una hora de vida.

| Claim | Valor |
|---|---|
| `iss` | el issuer |
| `aud` | el `client_id` |
| `iat`, `exp` | emisión y vencimiento (una hora) |
| `nonce` | el de la autorización |
| `sub` | el id del usuario en Core (UUID). Nunca se reasigna: una persona recreada con el mismo email tiene otro |
| `email` | el email de la cuenta |
| `email_verified` | `true` si la cuenta está activa y su email es de un dominio del parámetro `oidc_dominios_verificados` (por defecto `dicsys.com,dicsys.ai`, editable en Parámetros) |
| `name` | nombre y apellido |
| `picture` | la foto de perfil como URL https, solo si la persona subió una y el issuer es https |

## Puesta en marcha

1. **Clave de firma.** Se genera en el servidor y se guarda en `secrets/oidc/`. El nombre del archivo es el `kid`;
   por ejemplo, `2026-10`:

   ```bash
   mkdir -p secrets/oidc
   docker compose exec -T backend python -m backend.modules.oidc.cli generar-clave > secrets/oidc/2026-10.pem
   sudo chown 1000:1000 secrets/oidc/2026-10.pem
   chmod 600 secrets/oidc/2026-10.pem
   ```

   El backend corre como el usuario 1000 del contenedor: si el archivo es de otro usuario con permisos 600, no lo
   puede leer y el proveedor queda apagado. En Windows, la redirección `>` de PowerShell 5 escribe en UTF-16 y el PEM
   no se puede leer: usar Git Bash o PowerShell 7.

2. **Configuración** en el `.env`: `OIDC_ISSUER=https://core.dicsys.ai` y `OIDC_KID_ACTIVA=2026-10`. Recrear el
   backend con `docker compose up -d backend`; `restart` no vuelve a leer el `.env`. Sin `OIDC_KID_ACTIVA`, o sin el
   archivo, el proveedor está apagado y todo `/oidc/*` responde 404.
3. **Cliente razorback.**

   ```bash
   docker compose exec backend python -m backend.modules.oidc.cli crear --client-id razorback \
     --nombre "razorback · Innovación Dicsys" \
     --redirect-uri https://innovacion.dicsys.ai/auth/core --redirect-uri http://localhost:5174/auth/core
   ```

   El secreto se muestra una sola vez y se le pasa a razorback por un canal seguro.

4. **Verificación:** `curl https://core.dicsys.ai/.well-known/openid-configuration` tiene que devolver el issuer
   exacto, y `curl https://core.dicsys.ai/oidc/jwks`, la clave con su `kid`.

El reverse proxy de `core.dicsys.ai` tiene que pasar al frontend todas las rutas, también `/.well-known/`.

## Clientes

Un comando en el contenedor del backend (`python -m backend.modules.oidc.cli`). No hay pantalla ni API para
administrar clientes.

| Para | Comando |
|---|---|
| Registrar un cliente (muestra el secreto una vez) | `crear --client-id X --nombre "..." --redirect-uri URI [--redirect-uri URI]` |
| Ver los clientes | `listar` |
| Empezar una rotación de secreto (el viejo sigue valiendo) | `rotar-secreto --client-id X` |
| Terminar la rotación (el viejo deja de valer) | `confirmar-rotacion --client-id X` |
| Reemplazar las redirect_uri (exactas) | `redirect-uris --client-id X --redirect-uri URI ...` |
| Cortar o volver a habilitar el acceso | `desactivar --client-id X` / `activar --client-id X` |

Las `redirect_uri` tienen que ser https; http solo se acepta para `localhost`. En la base se guarda el SHA-256 de cada
secreto, nunca el secreto en claro.

## Rotar la clave de firma

1. Generar la clave nueva en `secrets/oidc/<kid nuevo>.pem`. Queda publicada en el JWKS sin reiniciar nada: el
   backend vuelve a leer el directorio cuando cambia.
2. Esperar al menos una hora, que es lo que dura en caché el JWKS de los clientes con margen.
3. Cambiar `OIDC_KID_ACTIVA` al kid nuevo y recrear el backend.
4. Una hora después, cuando venció el último `id_token` firmado con la vieja, borrar el PEM viejo.

## Esquema

Las tablas `core_oidc_clientes` y `core_oidc_codigos` las crea la revisión de Alembic `0004`, junto con la columna
`core_usuarios.email_secundario` del ingreso con Google (F22, `docs/IngresoGoogle.md`). En una base de antes de
Alembic que ya las tenía (producción desde el 2026-10-12, por `create_all`), la `0004` no las vuelve a crear.
