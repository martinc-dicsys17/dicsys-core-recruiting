"""
Excepciones personalizadas de la aplicación.
"""

from fastapi import HTTPException, status


class UsuarioNotFoundError(HTTPException):
    """Usuario no encontrado."""

    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")


class UsuarioAlreadyExistsError(HTTPException):
    """Usuario ya existe."""

    def __init__(self, field: str = "email"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=f"El {field} ya está registrado")


class InvalidCredentialsError(HTTPException):
    """Credenciales inválidas."""

    def __init__(self):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Credenciales inválidas")


class InsufficientPermissionsError(HTTPException):
    """Permisos insuficientes."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permisos insuficientes para realizar esta acción"
        )
