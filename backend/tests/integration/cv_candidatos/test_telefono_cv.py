"""Extracción del teléfono del CV: número completo con su formato original, nunca truncado ni armado con otros datos.

Los datos son ficticios; reproducen formatos reales de CVs argentinos (característica entre paréntesis, prefijo 15,
números locales de 6 dígitos del interior, código de país con o sin "+").
"""

import pytest

from backend.modules.recruiting.services import CandidatoService


def _telefono(texto: str):
    return CandidatoService.parsear_cv_texto(texto, "cv.pdf")["telefono"]


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Característica entre paréntesis y prefijo 15 (antes no se extraía)
        ("Ana Pérez\n+54 (3548) 15572263\nCórdoba, Argentina", "+54 (3548) 15572263"),
        # Número local de 6 dígitos del interior (antes se truncaba a "54 3534 2673")
        ("Hernando, Córdoba, Argentina | +54 3534 267338 | ana@gmail.com", "+54 3534 267338"),
        # Código de país entre paréntesis (antes se perdía el "+54")
        ("CABA, Arg  |  (+54) 11 34134692  |  ana@gmail.com", "(+54) 11 34134692"),
        ("ana@gmail.com | (+54) 1151153487 | www.linkedin.com/in/ana-123456789", "(+54) 1151153487"),
        # Formatos que ya se reconocían: se conservan igual
        ("Celular: +54 9 351 805 3727", "+54 9 351 805 3727"),
        ("+543513639857", "+543513639857"),
        ("Celular: 11-3088-0023", "11-3088-0023"),
        ("Tristán Suárez, Buenos Aires, Argentina  |  11 3435-2315  |  ana@gmail.com", "11 3435-2315"),
        ("Buenos Aires, Argentina | ana@gmail.com | 011 2328-7633  | LinkedIn", "011 2328-7633"),
        ("Teléfono: 351.555.1234", "351.555.1234"),
        ("Tel: 4555-1234", "4555-1234"),
    ],
    ids=[
        "parentesis_y_15",
        "local_6_digitos",
        "pais_entre_parentesis",
        "pais_parentesis_sin_espacios",
        "con_9",
        "pegado",
        "guiones",
        "linea_de_contacto",
        "cero_inicial",
        "puntos",
        "local_8_digitos",
    ],
)
def test_telefono_completo_con_formato_original(texto, esperado):
    assert _telefono(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Experiencia\n2021 - 2024\nFeb 2018 - 2020",  # rangos de años
        "Fecha de nacimiento: 05/11/1995\n2026-11-05",  # fechas
        "DNI: 30.123.456",  # DNI con puntos
        "DNI 30123456\nCUIT: 20-30123456-9",  # documento y CUIT rotulados
        "linkedin.com/in/francisco-obaya-190142191",  # dígitos de una URL
        "ana.1155550000@gmail.com",  # dígitos de un email
        "Localidad: Villa Ballester; CP:1653.",  # código postal
        "Contacto:\n11 35\n55 1234",  # dígitos de líneas distintas no forman un número
        "Sin datos de contacto",
        "",
    ],
    ids=["anios", "fechas", "dni_puntos", "dni_cuit", "url", "email", "cp", "lineas_distintas", "sin_numero", "vacio"],
)
def test_sin_telefono_valido_devuelve_none_y_nunca_un_numero_parcial(texto):
    assert _telefono(texto) is None


def test_se_toma_el_primer_telefono_valido_y_no_el_de_una_referencia_posterior():
    texto = (
        "Julián Prueba\nContacto: 11-3105-2706\nE-mail: julian@hotmail.com\n"
        "Experiencia Laboral\n2022 - 2023\nRef. Greta (Líder directo); greta@empresa.com.ar; 11-3174-0887"
    )
    assert _telefono(texto) == "11-3105-2706"


def test_un_dato_invalido_previo_no_impide_encontrar_el_telefono():
    """Antes solo se evaluaba la primera coincidencia: si no era un teléfono, el CV quedaba sin teléfono."""
    texto = "Analista Funcional\n2019 - 2024\nDNI: 30.123.456\nCelular: +54 9 11 5555-1234"
    assert _telefono(texto) == "+54 9 11 5555-1234"
