"""Límite de intentos en el ingreso (F07-P07): login, 2FA, recuperación de contraseña y magic link.

Cuenta, en una ventana deslizante de 15 minutos, los fallos (contraseña o código incorrectos, enlaces inválidos) y los
pedidos de correo de recuperación: por cuenta y por IP. Pasado el tope, el endpoint responde 429 con Retry-After antes
de verificar nada: sin probar la contraseña ni mandar el correo. Un acierto borra los fallos de esa cuenta, no los de la
IP.

Los contadores viven en la memoria de cada proceso: con N workers de uvicorn el tope efectivo puede llegar a N veces el
configurado, y se pierden al reiniciar. Alcanza para frenar la fuerza bruta; un contador compartido queda para después.
"""

import ipaddress
import math
import threading
import time
from collections import deque
from functools import lru_cache

from fastapi import HTTPException, Request

from backend.core.config import settings

VENTANA = 15 * 60  # segundos
BARRIDO = 60  # cada cuánto se borran las claves sin intentos vigentes, para que la memoria no crezca


def tope(tipo: str) -> int:
    return {
        "ip": settings.limite_intentos_por_ip,
        "login": settings.limite_login_por_cuenta,
        "codigo": settings.limite_2fa_por_cuenta,
        "correo": settings.limite_correos_por_cuenta,
    }[tipo]


class Limitador:
    """Ventana deslizante en memoria: por clave, los instantes de lo que contó."""

    def __init__(self, reloj=time.monotonic):
        self._reloj = reloj
        self._marcas: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._barrido = reloj()

    def espera(self, clave: str, tope: int) -> int:
        """Segundos hasta que la clave baje de su tope; 0 si no llegó."""
        with self._lock:
            marcas = self._vigentes(clave)
            if len(marcas) < tope:
                return 0
            return max(1, math.ceil(marcas[-tope] + VENTANA - self._reloj()))

    def sumar(self, clave: str) -> None:
        with self._lock:
            ahora = self._reloj()
            if ahora - self._barrido > BARRIDO:
                for vieja in list(self._marcas):
                    self._vigentes(vieja)
                self._barrido = ahora
            self._marcas.setdefault(clave, deque()).append(ahora)

    def olvidar(self, clave: str) -> None:
        with self._lock:
            self._marcas.pop(clave, None)

    def _vigentes(self, clave: str) -> deque[float]:
        marcas = self._marcas.get(clave)
        if marcas is None:
            return deque()
        vencidas = self._reloj() - VENTANA
        while marcas and marcas[0] <= vencidas:
            marcas.popleft()
        if not marcas:
            del self._marcas[clave]
        return marcas


@lru_cache
def _redes(confiables: str) -> tuple:
    return tuple(ipaddress.ip_network(red.strip()) for red in confiables.split(",") if red.strip())


def ip_del_cliente(request: Request) -> str:
    """La IP de quien pide. Flask llama desde la red interna y manda la del navegador en X-Cliente-IP: esa cabecera se
    cree solo si el pedido llega de una IP confiable (settings.ips_confiables), porque desde afuera cualquiera la
    inventa."""
    directa = request.client.host if request.client else ""
    reenviada = (request.headers.get("x-cliente-ip") or "").strip()[:64]
    if reenviada:
        try:
            if any(ipaddress.ip_address(directa) in red for red in _redes(settings.ips_confiables)):
                return reenviada
        except ValueError:
            pass
    return directa


class Intentos:
    """Dependencia de los endpoints del ingreso. Cada cuenta va como tipo=valor (login=<id o email>, codigo=<id>,
    correo=<email>), y la IP de quien pide entra siempre."""

    def __init__(self, request: Request):
        self.ip = ip_del_cliente(request)
        self._limitador: Limitador = request.app.state.limitador

    def frenar(self, **cuentas: str) -> None:
        """429 con Retry-After si la IP o alguna de las cuentas llegó a su tope."""
        espera = max(self._limitador.espera(clave, tope(tipo)) for tipo, clave in self._claves(cuentas))
        if espera:
            minutos = math.ceil(espera / 60)
            raise HTTPException(
                status_code=429,
                detail=f"Demasiados intentos. Probá de nuevo en {minutos} minuto{'s' if minutos > 1 else ''}.",
                headers={"Retry-After": str(espera)},
            )

    def contar(self, **cuentas: str) -> None:
        for _, clave in self._claves(cuentas):
            self._limitador.sumar(clave)

    def olvidar(self, **cuentas: str) -> None:
        """Un acierto: borra lo contado para esas cuentas (la IP sigue igual)."""
        for tipo, valor in cuentas.items():
            self._limitador.olvidar(f"{tipo}:{valor}")

    def _claves(self, cuentas: dict[str, str]) -> list[tuple[str, str]]:
        return [("ip", f"ip:{self.ip}"), *((tipo, f"{tipo}:{valor}") for tipo, valor in cuentas.items())]
