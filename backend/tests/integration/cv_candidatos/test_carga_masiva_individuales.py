"""Carga masiva de CVs: CVs individuales (.pdf/.doc/.docx), carga mixta con ZIP, limite de 100, formatos invalidos y errores parciales."""

import io
import struct
import zipfile

import fitz
import pytest

from backend.modules.recruiting.models import Candidato
from backend.tests.helpers.auth import auth_headers

URL_MASIVO = "/api/v1/recruiting/candidatos/cargar-cv-masivo"


def _cv(nombre: str, email: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate((nombre, "Analista QA", email, "Cordoba, Argentina")):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


def _zip(**archivos) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for nombre, contenido in archivos.items():
            zf.writestr(nombre, contenido)
    return buffer.getvalue()


@pytest.fixture
def escenario(data_factory, db_session, fake_storage):  # noqa: F811
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.flush()
    return auth_headers(usuario, empresa), empresa


def _enviar(client, headers, archivos):  # noqa: F811
    files = [("archivos", (nombre, contenido, "application/octet-stream")) for nombre, contenido in archivos]
    r = client.post(URL_MASIVO, headers=headers, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def _por_archivo(body):
    return {r["archivo"]: r for r in body["resultados"]}


@pytest.mark.integration
def test_un_pdf_individual_se_importa_sin_comprimir(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    body = _enviar(client, headers, [("Ana Perez.pdf", _cv("Ana Perez", "ana.perez@example.com"))])

    assert body["resumen"]["creados"] == 1
    assert _por_archivo(body)["Ana Perez.pdf"]["resultado"] == "creado"
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 1


@pytest.mark.integration
def test_varios_cvs_individuales_en_una_operacion(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    archivos = [(f"cv{i}.pdf", _cv(f"Persona Numero{i}", f"persona{i}@example.com")) for i in range(5)]
    body = _enviar(client, headers, archivos)

    assert body["resumen"]["total_archivos"] == 5
    assert body["resumen"]["creados"] == 5
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 5


@pytest.mark.integration
def test_carga_mixta_individuales_y_zip(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    paquete = _zip(**{"dentro.pdf": _cv("Juan Zip", "juan.zip@example.com")})
    body = _enviar(
        client,
        headers,
        [
            ("suelto.pdf", _cv("Maria Suelta", "maria.suelta@example.com")),
            ("lote.zip", paquete),
        ],
    )

    assert body["resumen"]["creados"] == 2
    assert set(_por_archivo(body)) == {"suelto.pdf", "dentro.pdf"}


@pytest.mark.integration
def test_zip_solo_mantiene_comportamiento_previo(client, escenario):  # noqa: F811
    headers, _ = escenario
    r = client.post(
        URL_MASIVO,
        headers=headers,
        files={"archivo": ("lote.zip", _zip(**{"a.pdf": _cv("Zeta Uno", "zeta.uno@example.com")}), "application/zip")},
    )
    assert r.status_code == 200
    assert r.json()["resumen"]["creados"] == 1


@pytest.mark.integration
def test_mas_de_100_individuales_se_rechaza_sin_procesar(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    archivos = [(f"cv{i}.pdf", _cv(f"Persona Numero{i}", f"limite{i}@example.com")) for i in range(101)]
    body = _enviar(client, headers, archivos)

    assert body["ok"] is False
    assert "100" in body["errores"][0]["motivo"]
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 0


@pytest.mark.integration
def test_exactamente_100_individuales_se_aceptan_y_el_zip_no_cuenta(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    archivos = [(f"cv{i}.pdf", _cv(f"Persona Numero{i}", f"tope{i}@example.com")) for i in range(100)]
    paquete = _zip(
        **{"zip1.pdf": _cv("Zip Uno", "zip.uno@example.com"), "zip2.pdf": _cv("Zip Dos", "zip.dos@example.com")}
    )
    body = _enviar(client, headers, archivos + [("lote.zip", paquete)])

    # 100 individuales + 2 dentro del ZIP: el ZIP no cuenta para el limite
    assert body["resumen"]["total_archivos"] == 102
    assert body["resumen"]["creados"] == 102


@pytest.mark.integration
def test_formato_invalido_unico_informa_error(client, escenario):  # noqa: F811
    headers, _ = escenario
    body = _enviar(client, headers, [("nota.txt", b"hola")])

    assert body["ok"] is False
    assert ".pdf" in body["errores"][0]["motivo"]


@pytest.mark.integration
def test_errores_parciales_no_interrumpen_los_demas(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    body = _enviar(
        client,
        headers,
        [
            ("bueno.pdf", _cv("Bueno Uno", "bueno.uno@example.com")),
            ("nota.txt", b"hola"),
            ("roto.pdf", b"esto no es un pdf"),
            ("repetido.pdf", _cv("Bueno Uno", "bueno.uno@example.com")),
            ("otro.pdf", _cv("Otro Dos", "otro.dos@example.com")),
        ],
    )

    por = _por_archivo(body)
    assert body["resumen"]["creados"] == 2
    assert por["bueno.pdf"]["resultado"] == "creado"
    assert por["otro.pdf"]["resultado"] == "creado"
    assert por["nota.txt"]["resultado"] == "formato_tamano"
    assert por["roto.pdf"]["resultado"] != "creado"
    assert por["repetido.pdf"]["resultado"] == "duplicado"
    assert body["resumen"]["total_archivos"] == 5
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 2


@pytest.mark.integration
def test_zip_danado_en_carga_mixta_no_corta_el_resto(client, escenario):  # noqa: F811
    headers, _ = escenario
    body = _enviar(
        client,
        headers,
        [
            ("malo.zip", b"no es zip"),
            ("ok.pdf", _cv("Ok Uno", "ok.uno@example.com")),
        ],
    )

    por = _por_archivo(body)
    assert por["malo.zip"]["resultado"] == "error_lectura"
    assert por["ok.pdf"]["resultado"] == "creado"


# --- .doc binario (Word 97-2003) ----------------------------------------------------------------------------------


def _doc_binario(*lineas: str) -> bytes:
    """Arma un .doc binario valido (contenedor OLE2 + WordDocument + 1Table con tabla de piezas), sin dependencias."""
    texto = ("\r".join(lineas) + "\r").encode("cp1252")
    sector, fin = 512, 0xFFFFFFFE
    wd = bytearray(9 * sector)
    struct.pack_into("<H", wd, 0, 0xA5EC)
    struct.pack_into("<H", wd, 0x0A, 0x0200)  # usa 1Table
    struct.pack_into("<I", wd, 0x4C, len(texto))
    struct.pack_into("<II", wd, 0x1A2, 0, 16)  # fcClx, lcbClx
    wd[0x800 : 0x800 + len(texto)] = texto
    clx = bytearray(8 * sector)
    clx[0] = 2
    struct.pack_into("<I", clx, 1, 16)
    struct.pack_into("<II", clx, 5, 0, len(texto))  # CPs
    struct.pack_into("<HIH", clx, 13, 0, (0x800 * 2) | 0x40000000, 0)  # PCD comprimido (cp1252)

    fat = [0xFFFFFFFD, fin] + list(range(3, 11)) + [fin] + list(range(12, 19)) + [fin]
    fat += [0xFFFFFFFF] * (128 - len(fat))
    header = bytearray(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") + bytearray(504)
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIII", header, 44, 1, 1, 0, 4096, fin, 0, fin, 0)
    struct.pack_into("<I", header, 76, 0)
    for i in range(1, 109):
        struct.pack_into("<I", header, 76 + 4 * i, 0xFFFFFFFF)

    def entrada(nombre, tipo, inicio, tam):
        e = bytearray(128)
        cod = nombre.encode("utf-16-le")
        e[: len(cod)] = cod
        struct.pack_into("<H", e, 64, len(cod) + 2)
        e[66] = tipo
        struct.pack_into("<III", e, 68, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
        struct.pack_into("<II", e, 116, inicio, tam)
        return bytes(e)

    directorio = (
        entrada("Root Entry", 5, fin, 0)
        + entrada("WordDocument", 2, 2, len(wd))
        + entrada("1Table", 2, 11, len(clx))
        + bytes(128)
    )
    return bytes(header) + struct.pack("<128I", *fat) + directorio + bytes(wd) + bytes(clx)


def _docx(*lineas: str) -> bytes:
    import docx

    documento = docx.Document()
    for linea in lineas:
        documento.add_paragraph(linea)
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


@pytest.mark.integration
def test_doc_binario_valido_se_importa(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    cv = _doc_binario("Laura Gomez", "Analista QA", "laura.doc@example.com", "Cordoba, Argentina")
    body = _enviar(client, headers, [("CV Laura.doc", cv)])

    assert body["resumen"]["creados"] == 1
    assert _por_archivo(body)["CV Laura.doc"]["resultado"] == "creado"
    candidato = db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).one()
    assert candidato.email == "laura.doc@example.com"


@pytest.mark.integration
def test_doc_invalido_informa_error_y_no_corta_la_carga_mixta(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    ole_corrupto = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600
    body = _enviar(
        client,
        headers,
        [
            ("falso.doc", b"esto no es un doc"),
            ("corrupto.doc", ole_corrupto),
            ("valido.doc", _doc_binario("Mario Doc", "Analista", "mario.doc@example.com", "Cordoba, Argentina")),
            ("cv.pdf", _cv("Pablo Pdf", "pablo.pdf@example.com")),
            ("cv.docx", _docx("Dora Docx", "Analista QA", "dora.docx@example.com", "Cordoba, Argentina")),
            ("lote.zip", _zip(**{"dentro.pdf": _cv("Zoe Zip", "zoe.zip@example.com")})),
        ],
    )

    por = _por_archivo(body)
    assert por["falso.doc"]["resultado"] != "creado"
    assert por["corrupto.doc"]["resultado"] != "creado"
    for nombre in ("valido.doc", "cv.pdf", "cv.docx", "dentro.pdf"):
        assert por[nombre]["resultado"] == "creado", por[nombre]
    assert body["resumen"]["creados"] == 4
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 4


@pytest.mark.integration
def test_el_limite_de_100_incluye_los_doc(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    archivos = [(f"cv{i}.doc", b"x") for i in range(101)]
    body = _enviar(client, headers, archivos)

    assert body["ok"] is False
    assert "100" in body["errores"][0]["motivo"]
