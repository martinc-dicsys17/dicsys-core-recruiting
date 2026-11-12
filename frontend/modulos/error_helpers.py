"""
Helper centralizado para formateo de errores de API.
Parsea errores de validación de Pydantic y los muestra legibles al usuario.
"""

# Mapeo de nombres de campos técnicos a etiquetas legibles
FIELD_LABELS = {
    # Empleados / Nómina
    "codigo": "Código",
    "cuil": "CUIL",
    "apellido": "Apellido",
    "nombre": "Nombre",
    "fecha_nacimiento": "Fecha de nacimiento",
    "dni": "DNI",
    "genero": "Género",
    "nacionalidad": "Nacionalidad",
    "estado_civil": "Estado civil",
    "nivel_estudio": "Nivel de estudio",
    "carrera_id": "Carrera",
    "telefono_personal": "Teléfono personal",
    "email_personal": "Email personal",
    "email_corporativo": "Email corporativo",
    "fecha_alta": "Fecha de alta",
    "fecha_baja": "Fecha de baja",
    "motivo_baja": "Motivo de baja",
    "departamento_id": "Departamento",
    "perfil_id": "Perfil",
    "hrbp_id": "HRBP",
    "seniority": "Seniority",
    "pais": "País",
    "provincia": "Provincia",
    "localidad": "Localidad",
    "codigo_postal": "Código postal",
    "barrio": "Barrio",
    "calle": "Calle",
    "numero": "Número",
    "departamento": "Departamento (dirección)",
    "contacto_emergencia": "Contacto de emergencia",
    "numero_emergencia": "Número de emergencia",
    "parentesco": "Parentesco",
    "manager_id": "Manager",
    "descripcion": "Descripción",
    # Usuarios
    "email": "Email",
    "password": "Contraseña",
    "telefono": "Teléfono",
    "rol": "Rol",
    "activo": "Activo",
    # HRBP
    "stock_actual": "Stock actual",
    "stock_minimo": "Stock mínimo",
    "item_tipo_id": "Tipo de item",
    "empleado_id": "Empleado",
    "cantidad": "Cantidad",
    "observaciones": "Observaciones",
    "motivo": "Motivo",
    # Star Miles
    "star_miles": "Star Miles",
    "star_miles_costo": "Costo en Star Miles",
    "categoria_id": "Categoría",
    "fecha_inicio": "Fecha de inicio",
    "fecha_vencimiento": "Fecha de vencimiento",
    "fecha_fin": "Fecha de fin",
    "imagen_url": "URL de imagen",
    "alcance": "Alcance",
    "tipo": "Tipo",
    "titulo": "Título",
    "contenido": "Contenido",
    "orden": "Orden",
    "visible": "Visible",
    "color": "Color",
    "icono": "Ícono",
    "stock": "Stock",
    "item_id": "Item",
    "desafio_id": "Desafío",
    "comentario": "Comentario",
    "comentario_solicitud": "Comentario de solicitud",
    # Permisos
    "permisos": "Permisos",
    "usuario_ids": "Usuarios",
    # Administración / Licencias
    "herramienta": "Herramienta",
    "costo_mensual": "Costo mensual",
    "moneda": "Moneda",
    "nro_pedido_compra": "Nro. pedido de compra",
    "estado": "Estado",
    "mercadolibre_url": "URL MercadoLibre",
    "mercadolibre_precio": "Precio MercadoLibre",
    "star_miles_calculado": "Star Miles calculado",
    # Innovación
    "tipo_certificacion": "Tipo de certificación",
    "repo_presentacion": "Repositorio Git Presentación",
    "repo_demo": "Repositorio Git Demo/Código",
    "repo_base": "Repositorio Base",
    "tematica": "Temática",
    "tecnologias": "Tecnologías",
    "fecha_presentacion": "Fecha de Presentación",
    "fecha_aprobacion": "Fecha de Aprobación",
    "cert_noncode_origen": "Origen Cert. NoN-Code",
    "cert_noncode_fecha": "Fecha Cert. NoN-Code",
    "cert_n8n_origen": "Origen Cert. n8n",
    "cert_n8n_fecha": "Fecha Cert. n8n",
    "cert_ruta1_fecha": "Fecha Cert. Ruta 1",
    "cert_ruta2_fecha": "Fecha Cert. Ruta 2",
    "cert_ruta3_fecha": "Fecha Cert. Ruta 3",
    # Parámetros
    "categoria": "Categoría",
    "subcategoria": "Subcategoría",
    "key": "Key",
    "valor": "Valor",
    "valor_default": "Valor por defecto",
}

# Mapeo de mensajes de error de Pydantic a español
ERROR_MESSAGES = {
    "less_than_equal": "debe ser menor o igual a {le}",
    "greater_than_equal": "debe ser mayor o igual a {ge}",
    "less_than": "debe ser menor a {lt}",
    "greater_than": "debe ser mayor a {gt}",
    "string_too_short": "debe tener al menos {min_length} caracteres",
    "string_too_long": "no puede tener más de {max_length} caracteres",
    "missing": "es obligatorio",
    "value_error": "debe comenzar con http:// o https://",
    "int_parsing": "debe ser un número entero",
    "string_type": "debe ser texto",
    "int_type": "debe ser un número entero",
    "float_type": "debe ser un número",
    "float_parsing": "debe ser un número válido",
    "date_from_datetime_parsing": "formato de fecha inválido",
    "date_parsing": "formato de fecha inválido",
    "enum": "valor no permitido",
    "email_parsing": "formato de email inválido",
    "url_parsing": "formato de URL inválido",
    "string_pattern_mismatch": "formato inválido",
    "bool_type": "debe ser verdadero o falso",
    "bool_parsing": "debe ser verdadero o falso",
}


def format_api_error(detail, fallback="Error en la operación"):
    """Formatea errores de la API para mostrar al usuario.

    Maneja tanto strings simples como listas de errores de validación de Pydantic.
    Retorna HTML formateado.
    """
    if isinstance(detail, str):
        return detail

    if isinstance(detail, list):
        items_html = ""
        for err in detail:
            if not isinstance(err, dict):
                items_html += f'<li class="text-sm">{err}</li>'
                continue

            # Obtener nombre del campo desde loc (ej: ['body', 'cuil'] -> 'cuil')
            loc = err.get("loc", [])
            field = loc[-1] if loc else "campo"
            label = FIELD_LABELS.get(field, str(field).replace("_", " ").capitalize())

            # Traducir mensaje de error
            err_type = err.get("type", "")
            ctx = err.get("ctx", {})

            if err_type in ERROR_MESSAGES:
                try:
                    msg = ERROR_MESSAGES[err_type].format(**ctx)
                except KeyError, IndexError:
                    msg = err.get("msg", "error de validación")
            else:
                msg = err.get("msg", "error de validación")

            items_html += f'<li class="text-sm"><span class="font-semibold">{label}</span>: {msg}</li>'

        if items_html:
            return (
                f'<div class="font-semibold mb-2">Revisá los siguientes campos:</div>'
                f'<ul class="space-y-1 ml-4 list-disc">{items_html}</ul>'
            )

    return str(detail) if detail else fallback


def error_html(
    detail,
    fallback="Error en la operación",
    css_class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4",
):
    """Genera el bloque HTML completo de error.

    Usa el sistema de toasts global de Alpine.js definido en base.html.
    """
    msg = format_api_error(detail, fallback)

    # Escapar comillas simples para JavaScript
    msg_escaped = msg.replace("\\", "\\\\").replace("'", "\\'")

    # Generar script que usa el sistema de toasts global de Alpine.js (igual que profile.html)
    return f"""
    <script>
    (function() {{
        if (typeof Alpine !== 'undefined' && Alpine.store('toasts')) {{
            Alpine.store('toasts').error('{msg_escaped}', 8000);
        }}
    }})();
    </script>
    """
