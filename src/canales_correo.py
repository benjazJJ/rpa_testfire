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
import smtplib
import socket
import ssl
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


# Código del caso en el asunto: "[RPA-TF #12]". Las respuestas ("RE: [RPA-TF #12] ...")
# lo conservan, y así el clasificador sabe a qué caso de la cola corresponde cada una.
PATRON_CODIGO = re.compile(r"\[RPA-TF #(\d+)\]")


def codigo_caso(id_caso: int) -> str:
    return f"[RPA-TF #{id_caso}]"


def construir_mensaje(caso: dict[str, Any], remitente: str) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = caso["destinatario"]
    mensaje["Subject"] = f"{codigo_caso(caso['id'])} {caso['asunto']}"
    mensaje["Date"] = formatdate(localtime=True)
    dominio = remitente.rsplit("@", 1)[-1] if "@" in remitente else "rpa-testfire.local"
    mensaje["Message-ID"] = make_msgid(domain=dominio)
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


class CanalSMTP:
    """
    Envío real por el servidor SMTP del curso (SSL, puerto 465), con los
    datos de la sección "correo" de config.json.

    Abre UNA conexión y la reutiliza para todos los correos de la corrida
    (una sola autenticación). Traduce cada respuesta del servidor a lo que
    el performer necesita saber:

    - 535 / autenticación rechazada, remitente rechazado, servidor
      inalcanzable           -> ErrorCanal (se detiene la corrida)
    - destinatario rechazado con código 5xx (no existe, dirección mala)
                             -> ErrorEnvioPermanente (FALLIDO, no se reintenta)
    - códigos 4xx, conexión cortada o timeout a mitad de camino
                             -> ErrorEnvio (ERROR, se reintenta después)
    """

    nombre = "smtp"
    es_real = True

    def __init__(self, config: dict[str, Any], timeout: int = 30):
        self.config = config
        self.timeout = timeout
        self.remitente = config["remitente"]
        self._smtp = None

    def _conectar(self):
        servidor, puerto = self.config["smtp_servidor"], self.config["smtp_puerto"]
        try:
            if self.config.get("ssl", True):
                contexto = ssl.create_default_context()
                smtp = smtplib.SMTP_SSL(servidor, puerto, timeout=self.timeout, context=contexto)
            else:  # solo para pruebas locales
                smtp = smtplib.SMTP(servidor, puerto, timeout=self.timeout)
            smtp.login(self.config["usuario"], self.config["clave"])
        except smtplib.SMTPAuthenticationError as error:
            raise ErrorCanal(f"El servidor rechazó usuario o clave (SMTP {error.smtp_code}).") from None
        except (OSError, smtplib.SMTPException) as error:
            raise ErrorCanal(
                f"No se pudo conectar o iniciar sesión en {servidor}:{puerto} ({type(error).__name__})."
            ) from None
        self._smtp = smtp

    def _descartar_conexion(self) -> None:
        if self._smtp is not None:
            try:
                self._smtp.close()
            except Exception:
                pass
        self._smtp = None

    def enviar(self, caso: dict[str, Any]) -> str:
        validar_destinatario(caso["destinatario"], permitir_prueba=False)
        mensaje = construir_mensaje(caso, self.remitente)
        if self._smtp is None:
            self._conectar()
        try:
            rechazados = self._smtp.send_message(mensaje)
        except smtplib.SMTPRecipientsRefused as error:
            codigo, texto = next(iter(error.recipients.values()))
            detalle = f"SMTP {codigo}: {texto.decode(errors='replace') if isinstance(texto, bytes) else texto}"
            if 500 <= codigo < 600:
                raise ErrorEnvioPermanente(f"Destinatario rechazado ({detalle})") from None
            raise ErrorEnvio(f"Destinatario rechazado temporalmente ({detalle})") from None
        except smtplib.SMTPSenderRefused as error:
            raise ErrorCanal(f"El servidor rechazó el remitente (SMTP {error.smtp_code}).") from None
        except smtplib.SMTPDataError as error:
            if 500 <= error.smtp_code < 600:
                raise ErrorEnvioPermanente(f"Mensaje rechazado (SMTP {error.smtp_code})") from None
            raise ErrorEnvio(f"Mensaje rechazado temporalmente (SMTP {error.smtp_code})") from None
        except (smtplib.SMTPServerDisconnected, socket.timeout, ConnectionError) as error:
            self._descartar_conexion()  # el próximo caso reconecta
            raise ErrorEnvio(f"Conexión con el servidor interrumpida ({type(error).__name__})") from None
        if rechazados:
            raise ErrorEnvioPermanente(f"El servidor rechazó: {', '.join(rechazados)}")
        return f"SMTP 250 OK {mensaje['Message-ID']}"

    def cerrar(self) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception:
                pass
        self._smtp = None
