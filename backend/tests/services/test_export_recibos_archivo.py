"""Elección del archivo a exportar cuando el duplicado es opcional.

El export por cliente nunca baja el original de un recibo que tiene duplicado:
ese lleva la firma patronal y no es lo que se le manda al cliente. Pero cuando
el recibo viene en una sola hoja, el original es el único archivo que hay.
"""

import pytest

from backend.modules.administracion.export_recibos_services import _archivo_y_sufijo

pytestmark = pytest.mark.services


class ReciboStub:
    def __init__(self, original=None, duplicado=None, firmado=None):
        self.archivo_original = original
        self.archivo_duplicado = duplicado
        self.archivo_firmado = firmado


def test_con_duplicado_sin_firmar_baja_el_duplicado():
    recibo = ReciboStub(original="002_original.pdf", duplicado="001_duplicado.pdf")

    assert _archivo_y_sufijo(recibo) == ("001_duplicado.pdf", "(SIN FIRMAR)")


def test_sin_duplicado_sin_firmar_baja_el_original():
    recibo = ReciboStub(original="001_recibo.pdf", duplicado=None)

    assert _archivo_y_sufijo(recibo) == ("001_recibo.pdf", "(SIN FIRMAR)")


def test_el_firmado_gana_siempre():
    con_dup = ReciboStub("002_original.pdf", "001_duplicado.pdf", "firmados/a.pdf")
    sin_dup = ReciboStub("001_recibo.pdf", None, "firmados/b.pdf")

    assert _archivo_y_sufijo(con_dup) == ("firmados/a.pdf", "firmado")
    assert _archivo_y_sufijo(sin_dup) == ("firmados/b.pdf", "firmado")


def test_nunca_devuelve_none():
    # Devolver None hacía explotar cloud_storage.download() aguas abajo con un
    # TypeError, en vez de omitir el recibo o bajar lo que sí hay.
    for recibo in (
        ReciboStub(original="001_recibo.pdf"),
        ReciboStub(original="002_original.pdf", duplicado="001_duplicado.pdf"),
        ReciboStub(original="001_recibo.pdf", firmado="firmados/c.pdf"),
    ):
        archivo, _ = _archivo_y_sufijo(recibo)
        assert archivo is not None
