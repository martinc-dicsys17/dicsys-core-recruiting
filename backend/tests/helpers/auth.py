from backend.modules.auth.routers import create_access_token
from backend.modules.empresa.models import Empresa
from backend.modules.usuarios.models import Usuario


def auth_headers(
    usuario: Usuario,
    empresa: Empresa | None = None,
) -> dict[str, str]:
    token_data = {
        "sub": usuario.email,
        "user_id": str(usuario.id),
        "rol": usuario.rol,
    }
    if empresa is not None:
        token_data["empresa_id"] = str(empresa.id)

    return {
        "Authorization": f"Bearer {create_access_token(token_data)}",
    }
