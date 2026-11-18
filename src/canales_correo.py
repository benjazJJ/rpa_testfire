"""
Canales de envío para el performer.

El performer no sabe CÓMO se envía un correo: le pasa cada caso a un canal.
Así la cola, los reintentos y el tracker son los mismos aunque el envío
real termine siendo Outlook de escritorio, Outlook web o SMTP.

Cada canal implementa ``enviar(caso)`` y señala el resultado así:
- termina sin excepción          -> el correo salió (ENVIADO)
- ``ErrorEnvioPermanente``       -> no tiene sentido reintentar (FALLIDO)
- ``ErrorEnvio``                 -> falla pasajera, se reintenta (ERROR)
- ``ErrorCanal``                 -> el canal entero no sirve (credenciales,
                                    servicio caído): el performer se detiene
                                    para no quemar los intentos de todos los casos.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

PATRON_CORREO = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
# Dominios reservados para pruebas (RFC 2606): nunca deben salir por un canal real.
DOMINIOS_PRUEBA = ("example.com", "example.org", "example.net")


class ErrorEnvio(Exception):
    """Falla pasajera: se reintenta."""


class ErrorEnvioPermanente(ErrorEnvio):
    """Falla que no se arregla reintentando (p. ej. dirección inválida)."""


class ErrorCanal(Exception):
    """El canal no puede enviar nada (p. ej. credenciales malas)."""


def validar_destinatario(correo: str, permitir_prueba: bool) -> None:
    if not PATRON_CORREO.match(correo or ""):
        raise ErrorEnvioPermanente(f"Dirección de correo inválida: {correo!r}")
    if not permitir_prueba and correo.lower().endswith(DOMINIOS_PRUEBA):
        raise ErrorEnvioPermanente(f"Dominio de prueba no se envía por un canal real: {correo}")


def construir_mensaje(caso: dict[str, Any], remitente: str) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = caso["destinatario"]
    mensaje["Subject"] = caso["asunto"]
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(domain="rpa-testfire.local")
    # Encabezado propio: permite reconocer las respuestas a este caso en la recepción.
    mensaje["X-RPA-Caso"] = str(caso["id"])
    mensaje.set_content(caso["cuerpo"])
    adjunto = caso.get("adjunto")
    if adjunto:
        ruta = Path(adjunto)
        if not ruta.exists():
            raise ErrorEnvioPermanente(f"No existe el adjunto: {ruta.name}")
        mensaje.add_attachment(
            ruta.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=ruta.name,
        )
    return mensaje


class CanalSimulacion:
    """
    No envía nada: valida el caso y guarda el correo como archivo .eml
    (se abre con doble clic en Outlook o en el Bloc de notas).

    Sirve para probar volumen (1000 casos) sin arriesgar la cuenta.
    ``fallos_pasajeros`` simula una caída en el primer intento de esos IDs
    para mostrar el reintento en la demo.
    """

    nombre = "simulacion"
    es_real = False

    def __init__(self, carpeta: Path, remitente: str = "robot.rpa@example.com",
                 fallos_pasajeros: set[int] | None = None):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.remitente = remitente
        self.fallos_pasajeros = set(fallos_pasajeros or ())

    def enviar(self, caso: dict[str, Any]) -> str:
        validar_destinatario(caso["destinatario"], permitir_prueba=True)
        if caso["id"] in self.fallos_pasajeros and caso["intentos"] == 1:
            raise ErrorEnvio("Timeout simulado del servidor de correo (prueba de reintento)")
        mensaje = construir_mensaje(caso, self.remitente)
        ruta = self.carpeta / f"correo_{caso['id']:05d}_{datetime.now():%H%M%S}.eml"
        ruta.write_bytes(bytes(mensaje))
        return str(ruta)
