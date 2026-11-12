"""Keys de storage de los recibos de sueldo.

Funciones puras: no tocan GCS, ni el filesystem, ni la base. Solo arman strings.

El caso que motiva estos tests: la key no incluía el tipo de liquidación, así que
el lote de SAC de un período pisaba los PDF del lote mensual cuando un empleado
caía en la misma página en los dos. El mapa de slugs es contrato permanente —las
keys ya guardadas apuntan a esas carpetas— así que solo se agregan entradas
nuevas, nunca se edita el slug de una existente.
"""

import pytest

from backend.modules.recibos.pdf_service import (
    TIPO_LIQUIDACION_SLUGS,
    carpeta_lote,
    slug_tipo_liquidacion,
)

pytestmark = pytest.mark.services

# Los cuatro valores del select en recibos_upload.html.
TIPOS_DEL_FORMULARIO = ["Liquidación Mensual", "SAC", "Liquidación Final", "Especial"]

CUIT, PERIODO = "30710370571", "2026-12"


# ─── slug_tipo_liquidacion ────────────────────────────────────────────────────


@pytest.mark.parametrize("tipo", TIPOS_DEL_FORMULARIO)
def test_los_tipos_del_formulario_tienen_slug_propio(tipo):
    # Ninguno debe caer en el slug genérico: son los valores esperables.
    assert slug_tipo_liquidacion(tipo) in TIPO_LIQUIDACION_SLUGS.values()


@pytest.mark.parametrize(
    "variante",
    [
        "Liquidación Mensual",
        "liquidacion mensual",
        "LIQUIDACION MENSUAL",
        "  Liquidación Mensual  ",
        "Liquidacion Mensual",
    ],
)
def test_acentos_mayusculas_y_espacios_caen_en_el_mismo_slug(variante):
    assert slug_tipo_liquidacion(variante) == "mensual"


def test_un_tipo_no_previsto_cae_en_un_slug_generico():
    # El endpoint acepta el tipo como string libre, así que por API puede llegar
    # cualquier cosa y tiene que resolverse en algo usable como carpeta.
    assert slug_tipo_liquidacion("Bono Extraordinario") == "bono_extraordinario"
    assert slug_tipo_liquidacion("") == "otro"
    assert slug_tipo_liquidacion(None) == "otro"
    assert slug_tipo_liquidacion("///") == "otro"


@pytest.mark.parametrize(
    "tipo",
    [
        "con/barra",
        "con\\contrabarra",
        "..",
        "../../etc/passwd",
        "con espacios y  tabs",
        "ÑOÑO ácéntòs",
        "!@#$%^&*()",
        "x" * 200,
    ],
)
def test_el_slug_nunca_rompe_la_ruta(tipo):
    slug = slug_tipo_liquidacion(tipo)

    assert slug, "el slug nunca puede quedar vacío"
    assert "/" not in slug and "\\" not in slug
    assert ".." not in slug
    assert len(slug) <= 30
    assert slug == slug.strip("_")


def test_los_slugs_conocidos_son_distintos_entre_si():
    slugs = list(TIPO_LIQUIDACION_SLUGS.values())

    assert len(slugs) == len(set(slugs))


def test_los_slugs_conocidos_son_un_contrato_estable():
    # Cambiar un slug deja huérfanos los PDF ya guardados: las keys viven en
    # recibos_recibos y apuntan a estas carpetas. Solo se agregan entradas.
    assert TIPO_LIQUIDACION_SLUGS == {
        "liquidacion mensual": "mensual",
        "sac": "sac",
        "liquidacion final": "liqfinal",
        "especial": "especial",
    }


# ─── carpeta_lote ─────────────────────────────────────────────────────────────


def test_la_carpeta_incluye_cuit_periodo_y_tipo():
    assert carpeta_lote(CUIT, PERIODO, "Liquidación Mensual") == f"recibos-{CUIT}/{PERIODO}/mensual"


def test_dos_liquidaciones_del_mismo_periodo_no_comparten_carpeta():
    carpetas = {carpeta_lote(CUIT, PERIODO, t) for t in TIPOS_DEL_FORMULARIO}

    assert len(carpetas) == len(TIPOS_DEL_FORMULARIO)


def test_el_mismo_empleado_en_la_misma_pagina_no_colisiona_entre_liquidaciones():
    # El bug original: mismo período, misma página, mismo CUIL -> misma key,
    # y el segundo lote pisaba los PDF del primero.
    cuil, pagina = 20242496656, 1

    def key(tipo):
        return f"{carpeta_lote(CUIT, PERIODO, tipo)}/{pagina:03d}_recibo_{cuil}.pdf"

    assert key("Liquidación Mensual") != key("SAC")
