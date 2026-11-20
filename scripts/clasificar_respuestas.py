"""
Subproceso 4d (Evaluación 3): RECEPCIÓN Y CLASIFICACIÓN de respuestas por IMAP.

    py scripts/clasificar_respuestas.py            (clasifica y mueve)
    py scripts/clasificar_respuestas.py --solo-leer  (muestra qué haría, sin mover)

1. Se conecta por IMAP (SSL, 993) a la cuenta del curso (config.json).
2. Busca en la bandeja de entrada los correos con "[RPA-TF #n]" en el asunto:
   son respuestas a los correos que envió el performer.
3. Lee SOLO lo que escribió quien responde. El texto citado del correo
   original se descarta, porque incluye "APROBADO o RECHAZADO" y
   confundiría la decisión.
4. Decide:
     - APROBADO  -> dice "aprobado" (o "apruebo") y no "rechazado"
     - RECHAZADO -> dice "rechazado" (o "rechazo") y no "aprobado"
     - REVISAR   -> dice las dos, ninguna, o no trae un código de caso
5. Mueve el correo a la carpeta RPA_APROBADO, RPA_RECHAZADO o RPA_REVISAR
   (las crea si no existen) y anota la decisión en el tracker de la cola.

Los correos ya clasificados salen de la bandeja de entrada, así que
ejecutarlo de nuevo no los procesa dos veces.

stdout: UNA línea JSON con el resumen. Salida 0 si pudo revisar la bandeja,
2 si no pudo conectarse.
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import re
import ssl
import sys
import time
import unicodedata
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402
from src.canales_correo import PATRON_CODIGO  # noqa: E402
from src.cola_correos import abrir_cola  # noqa: E402
from src.config_correo import cargar_config_correo, describir  # noqa: E402

APROBADO, RECHAZADO, REVISAR = "APROBADO", "RECHAZADO", "REVISAR"
CARPETAS = {APROBADO: "RPA_APROBADO", RECHAZADO: "RPA_RECHAZADO", REVISAR: "RPA_REVISAR"}

# Dónde empieza el texto citado en las respuestas de Gmail, Outlook,
# Thunderbird, webmails y celulares.
MARCAS_CITA = [
    re.compile(r"^\s*>"),
    re.compile(r"^\s*(el|on)\b.*(escribi[oó]|wrote)\s*:?\s*$", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*(mensaje original|original message|forwarded message|mensaje reenviado)", re.IGNORECASE),
    re.compile(r"^\s*_{5,}\s*$"),
    re.compile(r"^\s*(de|from|enviado|sent)\s*:", re.IGNORECASE),
]
PALABRAS_APROBADO = re.compile(r"\b(aprobado|aprobada|apruebo)\b")
PALABRAS_RECHAZADO = re.compile(r"\b(rechazado|rechazada|rechazo)\b")


# --------------------------------------------------------------------- lógica pura

def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def texto_propio(cuerpo: str) -> str:
    """Devuelve solo lo que escribió quien responde (antes del texto citado)."""
    propio = []
    for linea in cuerpo.splitlines():
        if any(marca.search(linea) for marca in MARCAS_CITA):
            break
        propio.append(linea)
    return "\n".join(propio).strip()


def decidir(asunto: str, cuerpo: str) -> str:
    """APROBADO, RECHAZADO o REVISAR según el asunto y el texto propio."""
    asunto_limpio = PATRON_CODIGO.sub(" ", asunto or "")
    texto = sin_tildes(f"{asunto_limpio}\n{texto_propio(cuerpo or '')}")
    aprueba = bool(PALABRAS_APROBADO.search(texto))
    rechaza = bool(PALABRAS_RECHAZADO.search(texto))
    if aprueba and not rechaza:
        return APROBADO
    if rechaza and not aprueba:
        return RECHAZADO
    return REVISAR


def cuerpo_texto(mensaje) -> str:
    parte = mensaje.get_body(preferencelist=("plain", "html"))
    if parte is None:
        return ""
    contenido = parte.get_content()
    if parte.get_content_type() == "text/html":
        # Respaldo simple si el correo solo trae HTML: saltos de línea por
        # bloques y sin etiquetas, suficiente para encontrar una palabra.
        contenido = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", contenido)
        contenido = re.sub(r"(?is)<blockquote.*", "", contenido)
        contenido = re.sub(r"<[^>]+>", " ", contenido)
    return contenido


# --------------------------------------------------------------------------- IMAP

def _q(nombre: str) -> str:
    return '"' + nombre.replace("\\", "\\\\").replace('"', '\\"') + '"'


class BuzonIMAP:
    PATRON_LIST = re.compile(r'\((?P<flags>[^)]*)\) (?P<delim>"[^"]*"|NIL) (?P<nombre>.+)')

    def __init__(self, config: dict[str, Any], conexion=None, timeout: int = 30):
        if conexion is None:
            if config.get("ssl", True):
                conexion = imaplib.IMAP4_SSL(config["imap_servidor"], config["imap_puerto"],
                                             ssl_context=ssl.create_default_context(), timeout=timeout)
            else:
                conexion = imaplib.IMAP4(config["imap_servidor"], config["imap_puerto"], timeout=timeout)
            conexion.login(config["usuario"], config["clave"])
        self.imap = conexion
        self._resueltas: dict[str, str] = {}

    def cerrar(self) -> None:
        try:
            self.imap.logout()
        except Exception:
            pass

    def buscar_respuestas(self) -> list[bytes]:
        estado, _ = self.imap.select("INBOX")
        if estado != "OK":
            raise RuntimeError("No se pudo abrir la bandeja de entrada.")
        estado, datos = self.imap.uid("SEARCH", None, "SUBJECT", '"RPA-TF"')
        if estado != "OK":
            raise RuntimeError("La búsqueda IMAP falló.")
        return (datos[0] or b"").split()

    def leer(self, uid: bytes):
        estado, datos = self.imap.uid("FETCH", uid, "(BODY.PEEK[])")
        if estado != "OK" or not datos or not isinstance(datos[0], tuple):
            raise RuntimeError(f"No se pudo leer el correo UID {uid.decode()}.")
        return email.message_from_bytes(datos[0][1], policy=policy.default)

    def _carpetas_existentes(self) -> tuple[list[str], str]:
        estado, datos = self.imap.list()
        nombres, delimitador = [], "/"
        for linea in datos or []:
            if not linea:
                continue
            m = self.PATRON_LIST.match(linea.decode(errors="replace"))
            if not m:
                continue
            if m.group("delim") != "NIL":
                delimitador = m.group("delim").strip('"') or delimitador
            nombres.append(m.group("nombre").strip().strip('"'))
        return nombres, delimitador

    def carpeta(self, nombre: str) -> str:
        """Nombre real de la carpeta en el servidor (la crea si no existe)."""
        if nombre in self._resueltas:
            return self._resueltas[nombre]
        existentes, delimitador = self._carpetas_existentes()
        # Algunos servidores (cPanel, Courier) solo aceptan carpetas bajo INBOX.
        candidatas = [nombre, f"INBOX{delimitador}{nombre}"]
        real = next((c for c in candidatas if c in existentes), None)
        if real is None:
            for candidata in candidatas:
                estado, _ = self.imap.create(_q(candidata))
                if estado == "OK":
                    self.imap.subscribe(_q(candidata))
                    real = candidata
                    break
        if real is None:
            raise RuntimeError(f"No se pudo crear la carpeta {nombre} en el servidor.")
        self._resueltas[nombre] = real
        return real

    def mover(self, uid: bytes, carpeta: str) -> None:
        destino = _q(self.carpeta(carpeta))
        capacidades = getattr(self.imap, "capabilities", ())
        if "MOVE" in capacidades:
            estado, _ = self.imap.uid("MOVE", uid, destino)
            if estado == "OK":
                return
        estado, _ = self.imap.uid("COPY", uid, destino)
        if estado != "OK":
            raise RuntimeError(f"No se pudo copiar a {carpeta}.")
        self.imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        self.imap.expunge()


# --------------------------------------------------------------------- proceso

def clasificar(buzon: BuzonIMAP, cola: ColaCorreos, propio: str, bitacora: Bitacora,
               solo_leer: bool = False, maximo: int = 200) -> dict[str, Any]:
    resumen = {"revisados": 0, APROBADO: 0, RECHAZADO: 0, REVISAR: 0, "sin_caso": 0,
               "omitidos_propios": 0, "errores": 0, "detalle": []}
    for uid in buzon.buscar_respuestas()[:maximo]:
        try:
            mensaje = buzon.leer(uid)
            asunto = str(mensaje.get("Subject", ""))
            remitente = parseaddr(str(mensaje.get("From", "")))[1].lower()
            if remitente == propio.lower():
                # Copia de un correo que mandó el propio robot: no es una respuesta.
                resumen["omitidos_propios"] += 1
                continue
            resumen["revisados"] += 1
            codigo = PATRON_CODIGO.search(asunto)
            decision = decidir(asunto, cuerpo_texto(mensaje)) if codigo else REVISAR
            try:
                fecha = parsedate_to_datetime(str(mensaje["Date"])).isoformat(timespec="seconds")
            except (TypeError, ValueError):
                fecha = time.strftime("%Y-%m-%dT%H:%M:%S")

            id_caso = int(codigo.group(1)) if codigo else None
            en_cola = False
            if not solo_leer:
                if id_caso is not None:
                    en_cola = cola.registrar_respuesta(id_caso, decision, remitente, fecha)
                buzon.mover(uid, CARPETAS[decision])
            if id_caso is None or (not solo_leer and not en_cola):
                resumen["sin_caso"] += 1
            resumen[decision] += 1
            resumen["detalle"].append({"caso": id_caso, "de": remitente, "decision": decision,
                                       "asunto": asunto[:120]})
            bitacora.info("Recepción: caso %s de %s -> %s%s", id_caso, remitente, decision,
                          " (solo lectura)" if solo_leer else f", movido a {CARPETAS[decision]}")
        except Exception as error:  # un correo raro no detiene la clasificación
            resumen["errores"] += 1
            bitacora.advertencia("Recepción: no se pudo procesar el correo UID %s (%s). Sigue con el siguiente.",
                                 uid.decode(errors="replace"), error)
    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clasifica las respuestas APROBADO/RECHAZADO por IMAP.")
    parser.add_argument("--solo-leer", action="store_true", help="No mueve correos ni toca el tracker")
    parser.add_argument("--max", type=int, default=200, help="Máximo de correos por ejecución")
    parser.add_argument("--cola", type=Path, default=None, help="SQLite local para pruebas")
    parser.add_argument("--id-ejecucion", default=None)
    parser.add_argument("--sin-sheets", action="store_true")
    args = parser.parse_args(argv)

    bitacora = Bitacora(args.id_ejecucion or crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    inicio = time.perf_counter()
    try:
        config = cargar_config_correo()
        bitacora.info("Recepción: servidor %s", describir(config))
        buzon = BuzonIMAP(config)
    except imaplib.IMAP4.error as error:
        mensaje = f"El servidor IMAP rechazó usuario o clave ({error})."
        bitacora.evento("Recepción", "Clasificar respuestas", "Fallido", mensaje, inicio)
        print(json.dumps({"ok": False, "error": mensaje}, ensure_ascii=False))
        return 2
    except Exception as error:
        bitacora.evento("Recepción", "Clasificar respuestas", "Fallido", str(error), inicio)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    try:
        resumen = clasificar(buzon, abrir_cola(args.cola), config["remitente"], bitacora,
                             solo_leer=args.solo_leer, maximo=args.max)
    finally:
        buzon.cerrar()

    estado = "Advertencia" if resumen["errores"] else "Exitoso"
    bitacora.evento(
        "Recepción", "Clasificar respuestas" + (" (solo lectura)" if args.solo_leer else ""), estado,
        f"{resumen['revisados']} respuestas: {resumen[APROBADO]} aprobadas, {resumen[RECHAZADO]} rechazadas, "
        f"{resumen[REVISAR]} a revisar, {resumen['errores']} con error",
        inicio, registros=resumen["revisados"],
    )
    print(json.dumps({"ok": True, "id_ejecucion": bitacora.id_ejecucion, **resumen}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
