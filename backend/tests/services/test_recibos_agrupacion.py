"""Agrupación de páginas de un PDF masivo en recibos.

El duplicado es opcional: un lote puede traer dos páginas por empleado
(duplicado + original) o una sola hoja. La agrupación lo resuelve por CUIL,
sin que nadie tenga que declarar de qué formato viene el lote.
"""

import pytest

from backend.modules.recibos.pdf_service import PDFService

CON_DUP = [201, 201, 202, 202, 203, 203]  # dos páginas por empleado
SIN_DUP = [201, 202, 203, 204, 205, 206]  # una hoja por empleado


pytestmark = pytest.mark.services


# ─── lote_tiene_duplicados ────────────────────────────────────────────────────


def test_lote_con_pares_tiene_duplicados():
    assert PDFService.lote_tiene_duplicados(CON_DUP) is True


def test_lote_sin_pares_no_tiene_duplicados():
    assert PDFService.lote_tiene_duplicados(SIN_DUP) is False


def test_una_sola_pagina_no_puede_ser_un_par():
    assert PDFService.lote_tiene_duplicados([201]) is False


def test_lote_vacio_o_sin_cuiles_no_tiene_duplicados():
    assert PDFService.lote_tiene_duplicados([]) is False
    assert PDFService.lote_tiene_duplicados([None, None]) is False


def test_un_par_roto_no_alcanza_para_dar_vuelta_el_veredicto():
    # Un lote con duplicados sigue siéndolo aunque un par venga cruzado.
    cuils = [201, 201, 202, 203, 204, 204, 205, 205]
    assert PDFService.lote_tiene_duplicados(cuils) is True


def test_un_empleado_reimpreso_no_convierte_el_lote_en_uno_con_duplicados():
    # Una reimpresión suelta entre muchas hojas únicas no llega al umbral.
    cuils = list(range(201, 251)) + [201]
    assert PDFService.lote_tiene_duplicados(cuils) is False


# ─── agrupar_paginas: lote con duplicados ─────────────────────────────────────


def test_agrupa_pares_en_recibos_con_duplicado():
    recibos, errores = PDFService.agrupar_paginas(CON_DUP)

    assert errores == []
    assert recibos == [
        {"pagina_duplicado": 1, "pagina_original": 2, "cuil": 201},
        {"pagina_duplicado": 3, "pagina_original": 4, "cuil": 202},
        {"pagina_duplicado": 5, "pagina_original": 6, "cuil": 203},
    ]


def test_par_cruzado_reporta_error_y_no_crea_recibo_a_medias():
    # En un lote con duplicados, una página suelta es un par roto: si se creara
    # un recibo sin duplicado, el front lo trataría como de una sola hoja y
    # estamparía la firma en la posición equivocada.
    cuils = [201, 201, 202, 203, 204, 204, 205, 205]
    recibos, errores = PDFService.agrupar_paginas(cuils)

    assert [r["cuil"] for r in recibos] == [201, 204, 205]
    assert all(r["pagina_duplicado"] is not None for r in recibos)
    assert [e["tipo"] for e in errores] == [
        "error_cuil_inconsistente",
        "error_cuil_inconsistente",
    ]


def test_pagina_final_sin_par_en_lote_con_duplicados_es_huerfana():
    cuils = [201, 201, 202, 202, 203]
    recibos, errores = PDFService.agrupar_paginas(cuils)

    assert [r["cuil"] for r in recibos] == [201, 202]
    assert len(errores) == 1
    assert errores[0]["tipo"] == "error_pagina_huerfana"
    assert errores[0]["pagina"] == 5


# ─── agrupar_paginas: lote sin duplicados ─────────────────────────────────────


def test_cada_pagina_es_un_recibo_cuando_no_hay_duplicados():
    recibos, errores = PDFService.agrupar_paginas(SIN_DUP)

    assert errores == []
    assert len(recibos) == 6
    assert all(r["pagina_duplicado"] is None for r in recibos)
    assert [r["pagina_original"] for r in recibos] == [1, 2, 3, 4, 5, 6]


def test_lote_de_una_sola_hoja():
    recibos, errores = PDFService.agrupar_paginas([201])

    assert errores == []
    assert recibos == [{"pagina_duplicado": None, "pagina_original": 1, "cuil": 201}]


def test_reimpresion_suelta_no_rompe_un_lote_sin_duplicados():
    # El CUIL repetido no está en páginas consecutivas, así que no forma par.
    cuils = [201, 202, 203, 201, 204, 205]
    recibos, errores = PDFService.agrupar_paginas(cuils)

    assert errores == []
    assert len(recibos) == 6
    assert all(r["pagina_duplicado"] is None for r in recibos)


# ─── CUIL no extraído ─────────────────────────────────────────────────────────


def test_pagina_sin_cuil_reporta_error_de_extraccion():
    recibos, errores = PDFService.agrupar_paginas([201, 202, None, 204])

    assert [r["cuil"] for r in recibos] == [201, 202, 204]
    assert len(errores) == 1
    assert errores[0]["tipo"] == "error_extraccion"
    assert errores[0]["pagina"] == 3


def test_lote_entero_sin_cuiles_no_crea_recibos():
    recibos, errores = PDFService.agrupar_paginas([None, None, None])

    assert recibos == []
    assert [e["tipo"] for e in errores] == ["error_extraccion"] * 3
