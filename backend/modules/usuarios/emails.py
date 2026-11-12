"""
Mails de la cuenta (bienvenida y restablecer contraseña) con el layout de la marca
(core/email_layout, D-97). Reemplazan las plantillas .html sueltas, que estaban en
violeta y no escapaban los datos; conservan su diseño (título destacado, íconos,
caja de datos, botón y aviso) y sus textos.
"""

from backend.core import email_layout as correo


def bienvenida(nombre: str, email: str, magic_url: str, expiracion_horas: int) -> str:
    """Cuenta nueva: el link para configurar la contraseña."""
    return correo.pagina(
        titulo=f"¡Bienvenido a {correo.marca()}!",
        icono="👋",
        cuerpo=(
            correo.parrafo(f"Hola <strong>{correo.e(nombre or '')}</strong>,")
            + correo.parrafo(
                f"Se creó una cuenta para vos en {correo.marca()}. "
                f"Para empezar a usar el sistema, necesitás configurar tu contraseña."
            )
            + correo.boton(magic_url, "Configurar mi contraseña", icono="🔐")
            + correo.enlace_alternativo(magic_url)
            + correo.caja(f"<strong>Tu email de acceso:</strong> {correo.e(email)}", icono="📧")
            + correo.aclaracion(
                f"Este enlace vence en <strong>{int(expiracion_horas)} horas</strong>. "
                f"Si no pediste esta cuenta, podés ignorar este correo.",
                icono="⏰",
            )
        ),
    )


def bienvenida_con_password(nombre: str, email: str, password: str, login_url: str) -> str:
    """Cuenta nueva con la contraseña inicial."""
    return correo.pagina(
        titulo=f"¡Bienvenido a {correo.marca()}!",
        icono="👋",
        cuerpo=(
            correo.parrafo(f"Hola <strong>{correo.e(nombre or '')}</strong>,")
            + correo.parrafo(f"Se creó una cuenta para vos en {correo.marca()}. Estas son tus credenciales de acceso:")
            + correo.credenciales([("📧", "Email", correo.e(email)), ("🔑", "Contraseña", correo.codigo(password))])
            + correo.boton(login_url, "Ingresar al sistema", icono="🚀")
            + correo.nota(
                "Te recomendamos cambiar tu contraseña después del primer ingreso, por seguridad.",
                titulo="Importante",
                icono="⚠️",
            )
        ),
    )


def restablecer_password(nombre: str, reset_url: str) -> str:
    """Pedido de restablecer la contraseña."""
    return correo.pagina(
        titulo="Restablecer contraseña",
        icono="🔑",
        cuerpo=(
            correo.parrafo(f"Hola <strong>{correo.e(nombre or '')}</strong>,")
            + correo.parrafo(
                "Recibimos un pedido para restablecer tu contraseña. Para elegir una nueva, usá este botón:"
            )
            + correo.boton(reset_url, "Restablecer contraseña", icono="🔐")
            + correo.enlace_alternativo(reset_url)
            + correo.aclaracion(
                "Este enlace vence en <strong>1 hora</strong>. "
                "Si no pediste este cambio, ignorá este correo: tu contraseña sigue igual.",
                icono="⏰",
            )
        ),
    )
