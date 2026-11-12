"""
Servicio de parsing y procesamiento de PDF masivo de recibos de sueldo.

Responsabilidades:
- Validar archivos PDF por tipo y tamaño
- Extraer CUIL de texto de páginas PDF
- Agrupar páginas en pares (original/duplicado)
- Procesar PDF masivo: split, match con empleados, crear recibos
"""

import logging
import re
import unicodedata
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from sqlalchemy.orm import Session

from backend.core.storage import cloud_storage
from backend.modules.nomina.models import Empleado
from backend.modules.recibos.models import Recibo

logger = logging.getLogger(__name__)

# Regex para CUIL argentino: con o sin guiones.
# El CUIL puede venir pegado al apellido (ej: "20-24249665-6GALVAN"),
# por eso se usan lookarounds de dígito en vez de \b (que fallaría ante letras).
# Matchea: 20-24249665-6 o 20242496656
CUIL_REGEX = re.compile(r"(?<!\d)(20|23|24|27)-?\d{8}-?\d(?!\d)")

# Segmento de carpeta por tipo de liquidación. Sin esto, dos lotes del mismo
# período que ubiquen al mismo CUIL en la misma página generan la misma key y
# el segundo pisa al primero (ver plan-gcp.md).
#
# ATENCIÓN: el mapa es un contrato permanente. Las keys ya guardadas en
# recibos_recibos apuntan a estas carpetas, así que solo se agregan entradas
# nuevas — nunca se edita el slug de una existente.
TIPO_LIQUIDACION_SLUGS = {
    "liquidacion mensual": "mensual",
    "sac": "sac",
    "liquidacion final": "liqfinal",
    "especial": "especial",
}


def _sin_acentos(texto: str) -> str:
    """Quita acentos para normalizar la clave de búsqueda del slug."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def slug_tipo_liquidacion(tipo: str) -> str:
    """Devuelve el segmento de carpeta para un tipo de liquidación.

    Los valores conocidos salen del mapa; cualquier otro cae en un slug
    genérico, porque el endpoint acepta el tipo como string libre y por API
    puede llegar un valor no previsto.
    """
    normalizado = _sin_acentos((tipo or "").strip().lower())
    if normalizado in TIPO_LIQUIDACION_SLUGS:
        return TIPO_LIQUIDACION_SLUGS[normalizado]
    generico = re.sub(r"[^a-z0-9]+", "_", normalizado).strip("_")
    return generico[:30] or "otro"


def carpeta_lote(empresa_cuit: str, periodo: str, tipo_liquidacion: str) -> str:
    """Carpeta de storage de un lote: recibos-{cuit}/{periodo}/{slug}."""
    return f"recibos-{empresa_cuit}/{periodo}/{slug_tipo_liquidacion(tipo_liquidacion)}"


class PDFService:
    """Servicio para procesamiento de PDFs de recibos de sueldo."""

    @staticmethod
    def validar_archivo_pdf(content_type: str, size: int, max_size: int) -> bool:
        """
        Valida que un archivo sea PDF y no exceda el tamaño máximo.

        Args:
            content_type: MIME type del archivo
            size: Tamaño en bytes del archivo
            max_size: Tamaño máximo permitido en bytes

        Returns:
            True si el archivo es válido

        Raises:
            ValueError: Si el archivo no es PDF o excede el tamaño máximo
        """
        if content_type != "application/pdf":
            raise ValueError("Solo se aceptan archivos PDF")
        if size > max_size:
            max_mb = max_size // (1024 * 1024)
            raise ValueError(f"El archivo excede el tamaño máximo de {max_mb}MB")
        return True

    @staticmethod
    def extraer_cuil_de_texto(texto: str) -> Optional[int]:
        """
        Extrae un CUIL argentino válido desde un texto.

        Busca un número de 11 dígitos con prefijo 20, 23, 24 o 27.

        Args:
            texto: Texto extraído de una página PDF

        Returns:
            CUIL como entero, o None si no se encontró
        """
        if not texto:
            return None
        match = CUIL_REGEX.search(texto)
        if match:
            # Limpiar guiones para obtener los 11 dígitos
            cuil_str = match.group().replace("-", "")
            return int(cuil_str)
        return None

    # Proporción de páginas que tienen que formar par con la siguiente para
    # considerar que el lote trae duplicados. Un lote con duplicados intacto
    # llega al 50% (cada par aporta una página); uno sin duplicados se queda en
    # 0%. El 25% deja pasar hasta la mitad de los pares rotos sin cambiar el
    # veredicto, y para confundir a un lote sin duplicados harían falta
    # reimpresiones adyacentes en un cuarto de las páginas.
    UMBRAL_PAGINAS_EMPAREJADAS = 0.25

    @staticmethod
    def lote_tiene_duplicados(cuils_por_pagina: List[Optional[int]]) -> bool:
        """
        Indica si el lote trae un duplicado por cada recibo.

        Cuenta cuántas páginas repiten el CUIL de la página siguiente, que es
        exactamente la señal que distingue a un lote con duplicados de uno sin
        ellos, y la compara contra UMBRAL_PAGINAS_EMPAREJADAS.

        Se contaron páginas adyacentes y no repeticiones en todo el lote porque
        la segunda medida se degrada en lotes chicos: con cuatro recibos y un
        solo par roto ya cae por debajo de cualquier umbral útil.

        Se usa solo durante el procesamiento, para saber si un recibo suelto es
        legítimo o es un par roto (ver agrupar_paginas). No se persiste: lo que
        queda guardado es el hecho concreto de si cada recibo tiene duplicado.
        """
        total_paginas = len(cuils_por_pagina)
        if total_paginas < 2:
            # Una sola página no puede formar un par.
            return False
        emparejadas = sum(
            1
            for i in range(total_paginas - 1)
            if cuils_por_pagina[i] is not None and cuils_por_pagina[i] == cuils_por_pagina[i + 1]
        )
        return emparejadas >= total_paginas * PDFService.UMBRAL_PAGINAS_EMPAREJADAS

    @staticmethod
    def agrupar_paginas(cuils_por_pagina: List[Optional[int]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Agrupa las páginas del PDF masivo en recibos.

        Regla local: si la página siguiente repite el CUIL, las dos forman un
        recibo con duplicado (impar = duplicado sin firma, par = original con
        firma del presidente). Si no lo repite, la página es un recibo sin
        duplicado: hay lotes que traen una sola hoja por empleado, ya firmada por
        el empleador y con el espacio para la firma del empleado.

        Salvaguarda: en un lote que sí trae duplicados, una página suelta no es
        un recibo de una sola hoja sino un par roto (dos páginas consecutivas
        con CUILs distintos, o un CUIL que no se pudo extraer). En ese caso se
        reporta el error en vez de crear un recibo a medias, porque el frontend
        usa la ausencia de duplicado para decidir dónde estampar la firma.

        Args:
            cuils_por_pagina: Lista de CUILs extraídos por página (None si no se encontró)

        Returns:
            Tupla de (recibos, errores)
            - recibos: lista de dicts con cuil, pagina_original y pagina_duplicado
              (este último None cuando el recibo no tiene duplicado)
            - errores: lista de dicts con tipo, pagina(s), descripcion
        """
        recibos = []
        errores = []
        total_paginas = len(cuils_por_pagina)
        con_duplicados = PDFService.lote_tiene_duplicados(cuils_por_pagina)

        i = 0
        while i < total_paginas:
            pagina = i + 1
            cuil = cuils_por_pagina[i]

            if cuil is None:
                errores.append(
                    {
                        "tipo": "error_extraccion",
                        "pagina": pagina,
                        "descripcion": f"No se encontró CUIL en la página {pagina}",
                    }
                )
                i += 1
                continue

            # Par: la página siguiente repite el CUIL.
            if i + 1 < total_paginas and cuils_por_pagina[i + 1] == cuil:
                recibos.append(
                    {
                        "pagina_duplicado": pagina,  # impar: sin firma
                        "pagina_original": pagina + 1,  # par: con firma presidente
                        "cuil": cuil,
                    }
                )
                i += 2
                continue

            # Página suelta en un lote que trae duplicados: es un par roto.
            if con_duplicados:
                cuil_siguiente = cuils_por_pagina[i + 1] if i + 1 < total_paginas else None
                if cuil_siguiente is None:
                    errores.append(
                        {
                            "tipo": "error_pagina_huerfana",
                            "pagina": pagina,
                            "cuil": str(cuil),
                            "descripcion": f"Página {pagina} sin par en un lote con duplicados",
                        }
                    )
                else:
                    errores.append(
                        {
                            "tipo": "error_cuil_inconsistente",
                            "pagina_duplicado": pagina,
                            "pagina_original": pagina + 1,
                            "cuil_duplicado": str(cuil),
                            "cuil_original": str(cuil_siguiente),
                            "descripcion": f"CUILs diferentes en par: {cuil} vs {cuil_siguiente}",
                        }
                    )
                i += 1
                continue

            # Lote sin duplicados: una página es un recibo completo.
            recibos.append(
                {
                    "pagina_duplicado": None,
                    "pagina_original": pagina,
                    "cuil": cuil,
                }
            )
            i += 1

        return recibos, errores

    # Alto y separación de la firma respecto de la línea sobre la que se apoya.
    FIRMA_ALTO = 45
    FIRMA_MARGEN_LATERAL = 10  # deja aire a los costados de la línea
    FIRMA_ANCHO_MAX = 150  # el mismo que usa el layout con duplicado
    FIRMA_SEPARACION_TEXTO = 24  # aire para los dos renglones que van bajo la firma

    @staticmethod
    def calcular_posicion_firma(pdf_bytes: bytes) -> Optional[Dict[str, float]]:
        """
        Ubica dónde estampar la firma del empleado, leyendo el PDF.

        En los recibos de una sola hoja el bloque de firmas NO está a una altura fija: se corre
        según cuántos conceptos tenga el recibo. Sobre un lote real la etiqueta
        "Firma Empleado" aparece en nueve alturas distintas, con 96 pt de
        diferencia entre la primera y la última, así que cualquier coordenada
        hardcodeada acierta en unos recibos y pisa el formulario en el resto.

        Devuelve las coordenadas en el sistema de pdf-lib (origen abajo-izquierda,
        que es el que usa el front), o None si el PDF no tiene la etiqueta —
        recibos con duplicado, donde el pie sí está a una altura fija y el front
        usa su posición de siempre.
        """
        import pymupdf  # import local, solo hace falta acá

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            if not doc.page_count:
                return None
            page = doc[0]
            alto_pagina = page.rect.height

            # "Firma Empleado" también matchea dentro de "Firma Empleador":
            # el del empleado es el de la derecha.
            hits = page.search_for("Firma Empleado")
            if not hits:
                return None
            etiqueta = max(hits, key=lambda h: h.x0)

            # La línea sobre la que se firma es la horizontal que está justo
            # encima de la etiqueta y la cubre de lado a lado.
            linea = None
            for dibujo in page.get_drawings():
                r = dibujo["rect"]
                if (
                    r.height <= 1
                    and etiqueta.y0 - 8 <= r.y1 <= etiqueta.y0
                    and r.x0 <= etiqueta.x0
                    and r.x1 >= etiqueta.x1
                ):
                    if linea is None or r.y1 > linea.y1:
                        linea = r
            if linea is None:
                # Sin la línea, se centra en la etiqueta con un ancho prudente.
                centro = (etiqueta.x0 + etiqueta.x1) / 2
                linea = pymupdf.Rect(centro - 55, etiqueta.y0 - 2, centro + 55, etiqueta.y0 - 2)

            ancho = min(PDFService.FIRMA_ANCHO_MAX, linea.width - PDFService.FIRMA_MARGEN_LATERAL)
            # Todo se apila sobre la línea, que queda de renglón de la firma:
            #   [firma] / [fecha] / [nombre] / ─── / "Firma Empleado"
            # Debajo de la línea no hay lugar: ahí está la etiqueta del formulario.
            base = alto_pagina - linea.y1
            return {
                "ancho": round(ancho, 2),
                "alto": PDFService.FIRMA_ALTO,
                # Centrada sobre la línea, arriba de las dos líneas de texto.
                "x": round(linea.x0 + (linea.width - ancho) / 2, 2),
                "y": round(base + PDFService.FIRMA_SEPARACION_TEXTO, 2),
                # Primer renglón (fecha); el segundo (nombre) va 9 pt más abajo,
                # justo encima de la línea.
                "texto_x": round(linea.x0, 2),
                "texto_y": round(base + 13, 2),
                "centro_x": round(linea.x0 + linea.width / 2, 2),
                "pie_y": 30,
            }

    @staticmethod
    def _extraer_pagina_pdf(reader: PdfReader, page_index: int) -> bytes:
        """Extrae una página del reader y retorna los bytes del PDF."""
        writer = PdfWriter()
        writer.add_page(reader.pages[page_index])
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    @staticmethod
    def procesar_pdf_masivo(
        pdf_bytes: bytes,
        empresa_id: str,
        empresa_cuit: str,
        periodo: str,
        tipo_liquidacion: str,
        lote_id: str,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Procesa un PDF masivo: extrae CUILs, agrupa en pares, genera PDFs
        individuales via StorageService y crea registros de Recibo en la DB.

        Args:
            pdf_bytes: Contenido binario del PDF masivo
            empresa_id: UUID de la empresa (string)
            empresa_cuit: CUIT de la empresa sin guiones (para keys de storage)
            periodo: Período en formato YYYY-MM
            tipo_liquidacion: Tipo de liquidación (define la carpeta del lote)
            lote_id: UUID del lote (string)
            db: Sesión de base de datos

        Returns:
            Dict con recibos_creados, errores, total_paginas, total_recibos, total_errores
        """
        reader = PdfReader(BytesIO(pdf_bytes))
        total_paginas = len(reader.pages)

        # 1. Extraer CUIL de cada página
        cuils_por_pagina = []
        for page in reader.pages:
            texto = page.extract_text() or ""
            cuil = PDFService.extraer_cuil_de_texto(texto)
            cuils_por_pagina.append(cuil)

        # 2. Agrupar páginas en recibos (con o sin duplicado)
        recibos_detectados, errores = PDFService.agrupar_paginas(cuils_por_pagina)

        # 3. Prefijo de storage: recibos-{cuit}/{periodo}/{slug}/
        folder = carpeta_lote(empresa_cuit, periodo, tipo_liquidacion)

        # 4. Procesar cada recibo detectado
        recibos_creados = []
        for detectado in recibos_detectados:
            cuil = detectado["cuil"]
            pag_orig = detectado["pagina_original"]  # con firma presidente
            pag_dup = detectado["pagina_duplicado"]  # sin firma, o None

            # Extraer PDFs individuales como bytes y subirlos al storage.
            # Sin duplicado la hoja es una sola, así que lleva un nombre propio
            # ('_recibo_') en vez de '_original_'.
            bytes_orig = PDFService._extraer_pagina_pdf(reader, pag_orig - 1)
            sufijo_orig = "original" if pag_dup else "recibo"
            key_orig = f"{folder}/{pag_orig:03d}_{sufijo_orig}_{cuil}.pdf"
            cloud_storage.upload(key_orig, bytes_orig, "application/pdf")

            key_dup = None
            if pag_dup:
                bytes_dup = PDFService._extraer_pagina_pdf(reader, pag_dup - 1)
                key_dup = f"{folder}/{pag_dup:03d}_duplicado_{cuil}.pdf"
                cloud_storage.upload(key_dup, bytes_dup, "application/pdf")

            # Buscar empleado activo por CUIL y empresa_id
            empleado = (
                db.query(Empleado)
                .filter(Empleado.cuil == cuil, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
                .first()
            )

            estado = "asignado"
            if not empleado:
                errores.append(
                    {
                        "tipo": "warning_sin_empleado",
                        "pagina_original": pag_orig,
                        "pagina_duplicado": pag_dup,
                        "cuil": str(cuil),
                        "descripcion": f"CUIL {cuil}: no se encontró empleado en nómina (se registró el recibo igualmente)",
                    }
                )

            # Crear registro de Recibo
            recibo = Recibo(
                empresa_id=empresa_id,
                lote_id=lote_id,
                cuil_extraido=cuil,
                archivo_original=key_orig,
                archivo_duplicado=key_dup,
                estado=estado,
                pagina_original=pag_orig,
                pagina_duplicado=pag_dup,
            )
            db.add(recibo)
            db.flush()

            # Registrar log de creación
            from backend.modules.recibos.models import ReciboLog

            detalle_paginas = f"páginas {pag_dup}-{pag_orig}" if pag_dup else f"página {pag_orig}"
            log = ReciboLog(
                recibo_id=recibo.id,
                empresa_id=empresa_id,
                accion="creacion",
                detalle=f"Recibo creado desde lote {lote_id}, {detalle_paginas}",
            )
            db.add(log)

            recibos_creados.append(
                {
                    "recibo_id": str(recibo.id),
                    "cuil": cuil,
                    "estado": estado,
                    "pagina_original": pag_orig,
                    "pagina_duplicado": pag_dup,
                    "archivo_original": key_orig,
                    "archivo_duplicado": key_dup,
                }
            )

        db.flush()

        return {
            "recibos_creados": recibos_creados,
            "errores": errores,
            "total_paginas": total_paginas,
            "total_recibos": len(recibos_creados),
            "total_errores": len(errores),
        }
