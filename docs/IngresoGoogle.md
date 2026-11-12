# Ingreso con Google y emails de la cuenta

Desde F22, el login de Dicsys Core tiene el botón «Entrar con Google» para cuentas `@dicsys.ai`, y la cuenta tiene
dos emails: el principal, con el que se entra, y el secundario. La ficha de nómina copia el principal. El pedido y
las decisiones están en la fase F22 de director (`director --proyecto ops-sistema-gestion get F22 --full`).

## Los emails de la cuenta

- **La cuenta es la fuente.** `core_usuarios.email` es el email con el que la persona entra y
  `core_usuarios.email_secundario` es su otro dominio (por ejemplo, el `@dicsys.com` de quien ya entra con
  `@dicsys.ai`). Los dos sirven para entrar con contraseña y para «olvidé mi contraseña».
- **Dónde se editan:** solo un admin, en Configuración › Usuarios (alta y edición). La persona no puede cambiar su
  email: ni la edición del perfil (`PUT /auth/me`) ni el email personal de «Mi perfil» lo tocan.
- **Reglas:**
  - El secundario tiene que ser distinto del principal.
  - Ninguno de los dos puede ser el email o el secundario de otra cuenta (409).
  - Si la cuenta tiene ficha de nómina (por DNI), los dos tienen que ser de un dominio de la empresa de la ficha (422).
  - Sin ficha, el dominio no se exige: cuentas de sistema o externas.
- **Dominios:** los de cada empresa (Empresas › «dominios de email»). Si la empresa no tiene dominios cargados,
  valen `dicsys.ai` y `dicsys.com`.

## El email corporativo de la ficha

- **Es una copia.** `nomina_empleados.email_corporativo` copia el email de la cuenta con el mismo DNI, siempre que
  sea de un dominio de la empresa de la ficha. Si no lo es, queda vacío.
- **Es de solo lectura en nómina.** El formulario lo muestra como texto y la API de nómina ignora ese campo. El
  detalle de la ficha también muestra el secundario de la cuenta.
- **Cuándo se copia:** al crear o editar la cuenta (email o DNI), al dar de alta una ficha o cambiarle el DNI, en el
  primer ingreso con Google y en la sincronización con Odoo de una ficha con cuenta.
- **Fichas sin cuenta:** conservan el email que trae Odoo hasta que la persona tenga cuenta. La sincronización de
  usuarios crea la cuenta con ese email.

## Control de email corporativo en el login

Si la cuenta tiene DNI y una ficha de nómina vigente (activa o dada de baja, no borrada), el email o el secundario
tienen que ser de un dominio de la empresa de alguna de sus fichas. Si no, el login responde 403:

> Tu usuario no tiene un email corporativo y no puede acceder a Dicsys Core. Comunicate con el administrador.

- Vale para el login con contraseña y para el ingreso con Google.
- Si la persona venía de otra app con «Entrar con Dicsys Core» (F21), vuelve a esa app con `access_denied`, como con
  una cuenta desactivada.
- Las sesiones abiertas no se cortan: el control actúa en el próximo login.

## Cómo funciona el ingreso con Google

```
navegador ──► /login/google ─────────────► backend POST /api/v1/auth/google/autorizacion  (URL de Google)
          ◄── 302 a accounts.google.com (state, nonce, PKCE S256, hd=dicsys.ai)
          ──► Google ──► /login/google/callback ──► backend POST /api/v1/auth/google/ingreso
                                                  canje del código con Google (server a server, con el secreto)
                                                  verificación del id_token: firma, aud, iss, exp, nonce,
                                                  email_verified y hd
```

- El frontend guarda el `state`, el `nonce` y el verificador de PKCE en una cookie firmada (`google_ingreso`, 10
  minutos), no en la sesión, porque la sesión se vacía ante cualquier 401 del backend.
- El dominio sale del claim `hd`, que firma Google. No alcanza con que el email termine en `@dicsys.ai`.
- De Google no se guarda nada: ni sus tokens, ni el `sub`, ni la foto. La cuenta se encuentra por el email.
- Después del ingreso sigue igual que con la contraseña: el control de email corporativo, el 2FA (según el
  parámetro), la elección de empresa y, si la persona venía de otra app, la vuelta a esa app.

**Quién entra.** Google no crea cuentas. Entra la cuenta que tiene ese email como principal o secundario. Si no hay
ninguna, se intenta la mudanza del primer ingreso. Si tampoco, o si el email está en dos cuentas, el ingreso se
rechaza con «Tu cuenta de Google no está asociada a un usuario de Dicsys Core».

**La mudanza del primer ingreso.** Si ninguna cuenta tiene `nombre@dicsys.ai` y hay una sola cuenta con
`nombre@dicsys.com` (la misma parte antes de la arroba) y sin secundario:

- El email de la cuenta pasa a ser `nombre@dicsys.ai` y `nombre@dicsys.com` queda de secundario.
- Las fichas de esa cuenta copian el `.ai`.
- La cuenta queda con `updated_by = ingreso_google` y el backend lo registra en el log.
- El `.com` y el `.ai` tienen que ser dominios de las empresas de sus fichas (o de la cuenta, si no tiene fichas).
- Una cuenta desactivada no se muda: el login la rechaza igual.

## Parámetros (Configuración › Parámetros › Seguridad › Ingreso con Google)

| Parámetro | Por defecto | Qué hace |
|---|---|---|
| `google_login_requiere_2fa` | `false` | `true`: quien entra con Google y tiene el 2FA de Core activado (o exigido) también tiene que ingresar el código. `false`: la cuenta de Google alcanza. |
| `google_login_dominio` | `dicsys.ai` | El dominio de las cuentas de Google que pueden entrar y al que se muda el email en el primer ingreso. |

## Efectos en otros módulos

- **Sincronización con Odoo:**
  - Si el email de Odoo ya es el principal o el secundario de la cuenta, no se toca la cuenta. Así la mudanza no se
    deshace mientras Odoo tenga el `.com`. Con otro email, actualiza la cuenta y sus fichas lo copian.
  - El email de Odoo solo va a las fichas sin cuenta.
  - Un email de Odoo de otro dominio no se carga y queda como error de la corrida.
- **Webex:** los mensajes personales, el saludo de cumpleaños y la sincronización de espacios usan la cuenta de
  Webex de la persona: el email principal si existe en Webex y, si no, el secundario de su cuenta. La sincronización
  no vuelve a invitar a quien ya está con cualquiera de sus dos emails, y el offboarding no le quita ninguno.
- **Apps que entran con Core (razorback):** el `sub` del `id_token` no cambia con la mudanza; el `email` pasa a ser
  el `.ai`.

## Puesta en marcha

1. **Cliente OAuth de Google.** Lo crea quien administra el Workspace de `dicsys.ai`, en un proyecto de Google Cloud
   de esa organización:
   - Pantalla de consentimiento: tipo **Interna**, para que solo entren cuentas del Workspace.
   - Credencial: «ID de cliente de OAuth», tipo **Aplicación web**.
   - URL de redireccionamiento autorizadas: `https://core.dicsys.ai/login/google/callback` y, para probar en local, la
     del stack de QA: `http://localhost:8090/login/google/callback` (con `http`: es `localhost`).
2. **Configuración** en el `.env` del backend: `GOOGLE_OAUTH_CLIENT_ID` y `GOOGLE_OAUTH_CLIENT_SECRET`. Recrear el
   backend con `docker compose up -d backend`. La URL de vuelta que se le manda a Google es `FRONTEND_URL` +
   `/login/google/callback`, así que tiene que coincidir exacta con la registrada.
3. **Verificación:** el login muestra «Entrar con Google · Con tu cuenta @dicsys.ai». Sin las dos variables el botón
   no aparece y `/login/google` responde 404.

El secreto va solo al `.env` del servidor y se pasa por un canal seguro, nunca por chat ni por mail en claro.

**Al desplegar,** la revisión de Alembic `0004` (`backend/migraciones/versions/`, la corre el servicio `migraciones`
antes del backend; en `main` era la migración ad hoc `usuarios_email_secundario_v1`):

- agrega `core_usuarios.email_secundario`;
- recorta los espacios del email de las cuentas;
- copia el email de cada cuenta a sus fichas.

Medido en producción (2026-10-12):

- 222 fichas con cuenta: todas tienen el mismo email que su cuenta.
- `ODOO-1` (`admin@dicsys.odoo.com`) y `ODOO-299` (`example@example.com`) quedan sin email corporativo y sus cuentas
  no pueden entrar. Nunca entraron.
- La cuenta de `ODOO-11` tenía un espacio al final del email: la migración lo recorta.

## Pendiente al integrar con F01–F04

`core_usuarios.email_secundario` se agrega con una migración ad hoc, como las demás de `main`. Al integrar con
`feature/upgrade-tech-stack` (Alembic) pasa a ser una revisión, junto con las tablas de OIDC (`docs/OIDC.md`).
