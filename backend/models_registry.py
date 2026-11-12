"""
Todos los modelos de la app en un solo lugar: importar este módulo deja Base.metadata con el esquema completo.

Lo importan main.py (las relaciones entre modelos se resuelven por nombre y necesitan todas las clases cargadas), las
migraciones (backend/migraciones/env.py compara Base.metadata contra la base) y los tests (create_all). Un archivo de
modelos nuevo (`models.py` o `*_models.py` en backend/modules) se agrega acá: test_migraciones.py falla si falta.

El orden es el que tenía main.py.
"""

from backend.modules.administracion import (  # noqa: F401
    clientes_models,
    export_recibos_models,
    proveedores_models,
)
from backend.modules.auditoria import models as auditoria_models  # noqa: F401
from backend.modules.auth import models as auth_models  # noqa: F401
from backend.modules.empresa import models as empresa_models  # noqa: F401
from backend.modules.hrbp import models as hrbp_models  # noqa: F401
from backend.modules.innovacion import licencias_models, models as innovacion_models  # noqa: F401
from backend.modules.llm import models as llm_models  # noqa: F401
from backend.modules.nomina import models as nomina_models  # noqa: F401
from backend.modules.notificaciones import models as notificaciones_models  # noqa: F401
from backend.modules.notificaciones_internas import models as notificaciones_internas_models  # noqa: F401
from backend.modules.oidc import models as oidc_models  # noqa: F401
from backend.modules.operaciones import models as operaciones_models  # noqa: F401
from backend.modules.parametros import models as parametros_models  # noqa: F401
from backend.modules.permisos import menu_models, models as permisos_models  # noqa: F401
from backend.modules.recibos import models as recibos_models  # noqa: F401
from backend.modules.recruiting import models as recruiting_models  # noqa: F401
from backend.modules.sincronizacion import models as sincronizacion_models  # noqa: F401
from backend.modules.soporte import models as soporte_models  # noqa: F401
from backend.modules.starmiles import models as starmiles_models  # noqa: F401
from backend.modules.tareas import models as tareas_models  # noqa: F401
from backend.modules.usuarios import models as usuarios_models  # noqa: F401
