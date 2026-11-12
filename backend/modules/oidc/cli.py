"""Administración de los clientes del proveedor OpenID Connect (F21) y de las claves de firma. Corre en el contenedor
del backend (docs/OIDC.md):

  docker compose exec backend python -m backend.modules.oidc.cli crear --client-id razorback \\
      --nombre "razorback · Innovación Dicsys" --redirect-uri https://innovacion.dicsys.ai/auth/core \\
      --redirect-uri http://localhost:5174/auth/core
  ... cli listar
  ... cli rotar-secreto --client-id razorback          # secreto nuevo; el viejo sigue valiendo
  ... cli confirmar-rotacion --client-id razorback     # cuando el cliente ya usa el nuevo: el viejo deja de valer
  ... cli redirect-uris --client-id razorback --redirect-uri ... [--redirect-uri ...]
  ... cli desactivar --client-id razorback  |  activar --client-id razorback
  ... cli generar-clave > secrets/oidc/<kid>.pem      # clave de firma nueva (el kid es el nombre del archivo)

Los secretos se muestran una sola vez: en la base queda su SHA-256.
"""

from __future__ import annotations

import argparse
import secrets
import sys

import backend.main  # noqa: F401  (todos los modelos: las relaciones entre ellos se resuelven por nombre)
from backend.core.utils import utc_now
from backend.database import SessionLocal
from backend.modules.oidc import claves
from backend.modules.oidc.models import ClienteOIDC
from backend.modules.oidc.services import SCOPES, hash_secreto


def _secreto() -> str:
    return secrets.token_urlsafe(32)


def _cliente(db, client_id: str) -> ClienteOIDC:
    cliente = db.query(ClienteOIDC).filter(ClienteOIDC.client_id == client_id).first()
    if cliente is None:
        sys.exit(f"No existe el cliente «{client_id}»")
    return cliente


def _uris(valores: list[str]) -> list[str]:
    for uri in valores:
        if not (uri.startswith("https://") or uri.startswith("http://localhost") or uri.startswith("http://127.0.0.1")):
            sys.exit(f"redirect_uri no permitida: {uri} (https, o http solo para localhost)")
    return list(dict.fromkeys(valores))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m backend.modules.oidc.cli", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("crear", help="registra un cliente y muestra su secreto (una vez)")
    c.add_argument("--client-id", required=True)
    c.add_argument("--nombre", required=True)
    c.add_argument("--redirect-uri", action="append", required=True, help="exacta (repetible)")
    c.add_argument("--scopes", default=" ".join(SCOPES))
    sub.add_parser("listar", help="clientes registrados")
    for nombre, ayuda in (
        ("rotar-secreto", "secreto nuevo; el actual sigue valiendo hasta confirmar"),
        ("confirmar-rotacion", "el secreto nuevo pasa a ser el único"),
        ("desactivar", "el cliente deja de poder autorizar y canjear"),
        ("activar", "vuelve a habilitar el cliente"),
    ):
        s = sub.add_parser(nombre, help=ayuda)
        s.add_argument("--client-id", required=True)
    r = sub.add_parser("redirect-uris", help="reemplaza las redirect_uri del cliente")
    r.add_argument("--client-id", required=True)
    r.add_argument("--redirect-uri", action="append", required=True)
    sub.add_parser("generar-clave", help="imprime una clave de firma RSA nueva en PEM (guardarla como <kid>.pem)")
    a = p.parse_args(argv)

    if a.comando == "generar-clave":
        print(claves.generar_pem(), end="")
        return 0

    db = SessionLocal()
    try:
        if a.comando == "crear":
            if db.query(ClienteOIDC).filter(ClienteOIDC.client_id == a.client_id).first():
                sys.exit(f"Ya existe el cliente «{a.client_id}»")
            if "openid" not in a.scopes.split() or not set(a.scopes.split()) <= set(SCOPES):
                sys.exit(f"scopes inválidos: tienen que incluir openid y estar entre {' '.join(SCOPES)}")
            secreto = _secreto()
            db.add(
                ClienteOIDC(
                    client_id=a.client_id,
                    nombre=a.nombre,
                    redirect_uris=_uris(a.redirect_uri),
                    scopes=a.scopes,
                    secreto_hash=hash_secreto(secreto),
                )
            )
            db.commit()
            print(f"Cliente creado: {a.client_id}\nclient_secret (se muestra una sola vez): {secreto}")
        elif a.comando == "listar":
            for cl in db.query(ClienteOIDC).order_by(ClienteOIDC.client_id).all():
                estado = "activo" if cl.activo else "desactivado"
                rotacion = " · rotación de secreto en curso" if cl.secreto_nuevo_hash else ""
                print(f"{cl.client_id} · {cl.nombre} · {estado}{rotacion}\n  scopes: {cl.scopes}")
                for uri in cl.redirect_uris or []:
                    print(f"  redirect_uri: {uri}")
        else:
            cliente = _cliente(db, a.client_id)
            if a.comando == "rotar-secreto":
                secreto = _secreto()
                cliente.secreto_nuevo_hash = hash_secreto(secreto)
                print(
                    f"client_secret nuevo (se muestra una sola vez): {secreto}\n"
                    "Valen el actual y el nuevo hasta `confirmar-rotacion`."
                )
            elif a.comando == "confirmar-rotacion":
                if not cliente.secreto_nuevo_hash:
                    sys.exit("No hay una rotación en curso")
                cliente.secreto_hash, cliente.secreto_nuevo_hash = cliente.secreto_nuevo_hash, None
                print("Rotación confirmada: el secreto anterior ya no vale.")
            elif a.comando == "redirect-uris":
                cliente.redirect_uris = _uris(a.redirect_uri)
                print("redirect_uri actualizadas.")
            else:
                cliente.activo = a.comando == "activar"
                print(f"Cliente {'activado' if cliente.activo else 'desactivado'}.")
            cliente.updated_at = utc_now()
            db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
