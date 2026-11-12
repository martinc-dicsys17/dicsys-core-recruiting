"""Forma estable de los errores de la API (F07-P08), la que lee la SPA y genera su cliente desde el OpenAPI.

- Todo error lleva `detail`: un texto en castellano para mostrar tal cual (Flask lo muestra así desde siempre).
- El 422 de validación suma `errores`: un ítem por campo, con su ruta (`nombre`, `domicilios.0.calle`) y el mensaje
  sin la etiqueta, para marcar cada campo del formulario.

El handler de 422 es propio (main.validation_exception_handler); FastAPI declaraba en el OpenAPI su HTTPValidationError
(detail como lista de objetos), que no es lo que responde (PG-14). `con_errores_propios` cambia esa declaración por
ErrorDeValidacion en todas las operaciones.
"""

from pydantic import BaseModel, Field


class Error(BaseModel):
    """Un error de la API: 400, 401, 403, 404, 409, 422 de negocio o 429."""

    detail: str = Field(description="Qué pasó, en castellano, para mostrar tal cual")


class ErrorDeCampo(BaseModel):
    campo: str = Field(
        description="Ruta del campo dentro del cuerpo, la query o el path ('nombre', 'items.0.cantidad')"
    )
    mensaje: str = Field(description="Qué corregir, sin el nombre del campo")


class ErrorDeValidacion(Error):
    """422: los datos no pasan la validación. `detail` los junta en un texto; `errores` los da uno por campo (no viene
    en los 422 que levanta la lógica del endpoint)."""

    errores: list[ErrorDeCampo] = Field(default_factory=list)


def responde(*codigos: int) -> dict:
    """`responses=` de un endpoint o un router: esos códigos con el esquema Error."""
    return {codigo: {"model": Error} for codigo in codigos}


def con_errores_propios(esquema: dict) -> dict:
    """El OpenAPI de FastAPI con ErrorDeValidacion en lugar de HTTPValidationError y ValidationError. Idempotente."""
    componentes = esquema.get("components", {}).get("schemas", {})
    if "HTTPValidationError" not in componentes:
        return esquema
    componentes.pop("HTTPValidationError")
    componentes.pop("ValidationError", None)
    propio = ErrorDeValidacion.model_json_schema(ref_template="#/components/schemas/{model}")
    componentes.update(propio.pop("$defs", {}))
    componentes["ErrorDeValidacion"] = propio
    _cambiar_referencias(esquema, "#/components/schemas/HTTPValidationError", "#/components/schemas/ErrorDeValidacion")
    return esquema


def _cambiar_referencias(nodo, vieja: str, nueva: str) -> None:
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave == "$ref" and valor == vieja:
                nodo[clave] = nueva
            else:
                _cambiar_referencias(valor, vieja, nueva)
    elif isinstance(nodo, list):
        for valor in nodo:
            _cambiar_referencias(valor, vieja, nueva)
