"""Paginación uniforme de los listados (F07-P08): la que ya usaban la mayoría de los módulos, con un tipo y un helper.

Query: `pagina` (desde 1) y `por_pagina` (20 por defecto, hasta 100). Respuesta: `items`, `total`, `pagina`,
`por_pagina` y `total_paginas` (1 si no hay ítems). Un listado puede sumar campos propios heredando de Pagina[T].
"""

import math
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Query

T = TypeVar("T")

POR_PAGINA = 20
MAXIMO = 100


class Pagina(BaseModel, Generic[T]):
    items: list[T]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


def paginar(consulta: Query, pagina: int, por_pagina: int) -> tuple[list, dict]:
    """Los ítems de la página y los datos de paginación, para armar la respuesta con `Pagina(items=..., **datos)`."""
    total = consulta.order_by(None).count()
    items = consulta.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    datos = {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": max(1, math.ceil(total / por_pagina)),
    }
    return items, datos
