"""
Generación y cacheo del banner og:image (1200x627) para certificados.

Vive en el backend (que ya tiene Pillow + qrcode y es dueño del almacenamiento).
El banner se genera una sola vez por certificado/versión y se cachea en disco.
El nombre del archivo es el slug del empleado (minúsculas, sin tildes ni
caracteres especiales, espacios -> "_"). Ej: "José Mamani" -> "jose_mamani".
"""

import os
import re
import unicodedata

import qrcode
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 627
BG = "#0f172a"
DESIGN_VERSION = 3  # subir este número invalida todos los banners cacheados

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "og_assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
BADGE_PATH = os.path.join(ASSETS_DIR, "ai_professional.png")
GENERIC_PATH = os.path.join(ASSETS_DIR, "og-certificate.png")

_FONT_SPEC = {
    "serif": ("PlayfairDisplay.ttf", "Bold"),
    "sans": ("Inter.ttf", "Regular"),
    "sansb": ("Inter.ttf", "Bold"),
}


def slugify_name(name):
    """nombre -> minúsculas, sin tildes/ñ, sin especiales, espacios -> '_'."""
    if not name:
        return "certificado"
    n = unicodedata.normalize("NFKD", name)
    n = n.encode("ascii", "ignore").decode("ascii")  # quita tildes/ñ
    n = n.lower().strip()
    n = re.sub(r"[^a-z0-9]+", "_", n)  # no-alfanumérico -> _
    n = re.sub(r"_+", "_", n).strip("_")
    return n or "certificado"


def _font(kind, size):
    fname, variation = _FONT_SPEC[kind]
    path = os.path.join(FONTS_DIR, fname)
    if os.path.exists(path):
        f = ImageFont.truetype(path, size)
        try:
            f.set_variation_by_name(variation)  # selecciona el peso
        except Exception:
            pass
        return f
    return ImageFont.load_default()


def generate_og_image(name, verify_url, out_path):
    """Genera el PNG 1200x627 y lo guarda en out_path (escritura atómica)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill="#334155")  # barra superior

    # Badge a la izquierda
    if os.path.exists(BADGE_PATH):
        badge = Image.open(BADGE_PATH).convert("RGBA")
        badge.thumbnail((300, 300))
        img.paste(badge, (100, (H - badge.height) // 2), badge)

    # Bloque de texto
    tx = 480
    d.text((tx, 130), "DICSYS.AI", font=_font("sansb", 26), fill="#93c5fd")
    d.text((tx, 167), "AI Professional", font=_font("serif", 74), fill="#ffffff")
    d.text((tx, 262), "Certificate", font=_font("serif", 40), fill="#94a3b8")

    # Nombre con auto-ajuste: achica la fuente si el nombre es largo.
    name_txt = name or "Certificado"
    name_max_w = W - tx - 60
    name_size = 38
    while name_size > 22 and d.textlength(name_txt, font=_font("sansb", name_size)) > name_max_w:
        name_size -= 2
    d.text((tx, 343 + (38 - name_size) // 2), name_txt, font=_font("sansb", name_size), fill="#ffffff")

    d.text((tx, 398), "Issued by DICSYS S.A.", font=_font("sans", 22), fill="#64748b")

    # Pie: divider + Credential ID
    d.line([(tx, 448), (950, 448)], fill="#334155", width=1)
    d.text((tx, 460), "CREDENTIAL ID", font=_font("sansb", 15), fill="#475569")
    d.text((tx, 482), verify_url.rstrip("/").split("/")[-1], font=_font("sans", 20), fill="#94a3b8")

    # QR de verificación
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    qrimg = qr.make_image(fill_color="#0f172a", back_color="white").convert("RGB").resize((128, 128), Image.NEAREST)
    qx, qy = 972, 432
    img.paste(qrimg, (qx, qy))
    lbl = "Scan to verify"
    w = d.textlength(lbl, font=_font("sans", 16))
    d.text((qx + (128 - w) / 2, qy + 132), lbl, font=_font("sans", 16), fill="#64748b")

    # Escritura atómica: tmp -> replace
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_path = out_path + ".tmp"
    img.save(tmp_path, "PNG", optimize=True)
    os.replace(tmp_path, out_path)
    return out_path
