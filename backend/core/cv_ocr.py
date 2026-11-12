"""OCR de respaldo para CV en PDF cuyas paginas no tienen texto digital legible (escaneos, texto como imagen).

Se invoca solo para las paginas que lo necesitan (`pdf_texto_cv.pagina_necesita_ocr`) o, si el documento entero
no tiene texto, para las primeras paginas. Nunca lanza excepciones: ante cualquier problema (RapidOCR no
instalado, modelo ausente, PDF danado, falta de memoria) devuelve vacio y el CV sigue con el texto digital que ya
tenia, de modo que la importacion no falla por culpa del OCR.

Motor y modelos: `rapidocr` 3.10.0 sobre ONNX Runtime, con modelos oficiales PP-OCRv6 multilingues (entrenados
para espanol y otros idiomas latinos; diccionario de 18.708 caracteres con ñ, Ñ, vocales con tilde en mayuscula y
minuscula y ü):
- Deteccion: PP-OCRv6_det_small (incluido en el paquete `rapidocr`).
- Reconocimiento: PP-OCRv6_rec_medium (se descarga y verifica por SHA256 al construir la imagen Docker, en la
  carpeta `models` del paquete; ver backend/Dockerfile). Es el que reconoce sin alterar telefonos, emails y nombres.
Las rutas se pasan explicitas: RapidOCR nunca descarga modelos en tiempo de ejecucion. Si falta un archivo, el OCR
queda no disponible (se registra una advertencia) y el resto de la extraccion sigue igual.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Los datos de contacto estan en las primeras paginas; limitar paginas y resolucion acota memoria y tiempo de CPU.
MAX_PAGINAS_OCR = 3
LADO_MAXIMO_PIXELES = 1600
ZOOM_MAXIMO = 1.7
PRESUPUESTO_SEGUNDOS = 45.0
CONFIANZA_MINIMA = 0.5

MODELO_DETECCION = "PP-OCRv6_det_small.onnx"
MODELO_RECONOCIMIENTO = "PP-OCRv6_rec_medium.onnx"

# Caja reconocida: (x0, y0, x1, y1, texto) en coordenadas de la pagina PDF (puntos)
Caja = Tuple[float, float, float, float, str]

_motor: Optional[Any] = None
_motor_no_disponible = False
_bloqueo = threading.Lock()  # un OCR a la vez por proceso: evita multiplicar el consumo de CPU y memoria


def rutas_modelos() -> Tuple[Path, Path]:
    """Rutas de los modelos de deteccion y reconocimiento (carpeta `models` del paquete rapidocr)."""
    import rapidocr

    carpeta = Path(rapidocr.__file__).resolve().parent / "models"
    return carpeta / MODELO_DETECCION, carpeta / MODELO_RECONOCIMIENTO


def _crear_motor() -> Any:
    from rapidocr import EngineType, ModelType, OCRVersion, RapidOCR

    deteccion, reconocimiento = rutas_modelos()
    faltantes = [str(r) for r in (deteccion, reconocimiento) if not r.is_file()]
    if faltantes:
        raise FileNotFoundError(f"modelos OCR no instalados: {', '.join(faltantes)}")
    return RapidOCR(
        params={
            "Global.log_level": "warning",
            "Global.use_cls": False,  # los CV van derechos: sin clasificador de orientacion
            "Global.text_score": CONFIANZA_MINIMA,
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Det.model_type": ModelType.SMALL,
            "Det.model_path": str(deteccion),
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
            "Rec.model_type": ModelType.MEDIUM,
            "Rec.model_path": str(reconocimiento),  # el diccionario viaja dentro del modelo (metadato "character")
        }
    )


def _obtener_motor() -> Optional[Any]:
    """RapidOCR se carga en el primer uso y se reutiliza; si no se puede cargar no se reintenta en cada CV."""
    global _motor, _motor_no_disponible
    if _motor is not None or _motor_no_disponible:
        return _motor
    try:
        _motor = _crear_motor()
    except Exception as exc:  # ImportError, modelos ausentes, onnxruntime incompatible
        _motor_no_disponible = True
        logger.warning(f"OCR de CV no disponible (RapidOCR no se pudo iniciar): {exc}")
    return _motor


def _items(resultado: Any) -> List[Tuple[Any, Any, Any]]:
    """(cuadrilatero, texto, confianza) de un resultado de RapidOCR 3.x (RapidOCROutput: boxes, txts, scores)."""
    cajas = getattr(resultado, "boxes", None)
    if cajas is None:
        return []
    return list(zip(cajas, getattr(resultado, "txts", None) or (), getattr(resultado, "scores", None) or ()))


def _cajas(resultado: Any, escala: float) -> List[Caja]:
    """Cajas de RapidOCR con confianza suficiente, llevadas a coordenadas de la pagina."""
    cajas: List[Caja] = []
    for puntos, texto, confianza in _items(resultado):
        try:
            texto, confianza = str(texto).strip(), float(confianza)
            if not texto or confianza < CONFIANZA_MINIMA:
                continue
            xs, ys = [float(p[0]) for p in puntos], [float(p[1]) for p in puntos]
            cajas.append((min(xs) / escala, min(ys) / escala, max(xs) / escala, max(ys) / escala, texto))
        except TypeError, ValueError, IndexError:
            continue
    return cajas


def _lineas_ordenadas(cajas: List[Caja]) -> List[str]:
    """Orden simple de arriba hacia abajo y de izquierda a derecha (se usa cuando no hay orden por columnas)."""
    return [c[4] for c in sorted(cajas, key=lambda c: (round(c[1] / 6), c[0]))]


def reconocer_cajas_pdf(contenido: bytes, indices: Iterable[int]) -> Dict[int, List[Caja]]:
    """OCR de las paginas indicadas (como mucho MAX_PAGINAS_OCR, dentro del presupuesto de tiempo).

    Devuelve {indice de pagina: cajas}; una pagina que no se pudo reconocer no aparece. Nunca lanza excepciones.
    """
    salida: Dict[int, List[Caja]] = {}
    try:
        import fitz
        import numpy as np

        inicio = time.monotonic()
        with _bloqueo:
            motor = _obtener_motor()
            if motor is None:
                return salida
            with fitz.open(stream=contenido, filetype="pdf") as doc:
                pedidas = sorted({i for i in indices if 0 <= i < len(doc)})
                if len(pedidas) > MAX_PAGINAS_OCR:
                    logger.warning(
                        f"OCR de CV: {len(pedidas)} paginas sin texto; se reconocen las primeras {MAX_PAGINAS_OCR}"
                    )
                for indice in pedidas[:MAX_PAGINAS_OCR]:
                    if time.monotonic() - inicio > PRESUPUESTO_SEGUNDOS:
                        logger.warning(
                            "OCR de CV: se alcanzo el tiempo maximo; se usa el texto de las paginas ya leidas"
                        )
                        break
                    try:
                        pagina = doc[indice]
                        zoom = min(ZOOM_MAXIMO, LADO_MAXIMO_PIXELES / max(pagina.rect.width, pagina.rect.height, 1))
                        pix = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
                        imagen = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                        resultado = motor(np.ascontiguousarray(imagen[:, :, ::-1]), use_cls=False)  # BGR
                        salida[indice] = _cajas(resultado, zoom)
                        del imagen, pix
                    except Exception as exc:  # una pagina fallida no descarta las demas
                        logger.warning(f"OCR de CV fallido en la pagina {indice + 1}: {exc}")
    except Exception as exc:
        logger.warning(f"OCR de CV fallido: {exc}")
    return salida


def extraer_texto_pdf_por_ocr(contenido: bytes) -> str:
    """Texto reconocido en las primeras paginas del PDF, o "" si no se pudo obtener."""
    try:
        import fitz

        with fitz.open(stream=contenido, filetype="pdf") as doc:
            cantidad = len(doc)
    except Exception as exc:
        logger.warning(f"OCR de CV fallido: {exc}")
        return ""
    cajas = reconocer_cajas_pdf(contenido, range(min(cantidad, MAX_PAGINAS_OCR)))
    return "\n".join("\n".join(_lineas_ordenadas(cajas[i])) for i in sorted(cajas) if cajas[i]).strip()
