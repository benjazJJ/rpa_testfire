"""
Lee la configuración del servidor de correo (SMTP + IMAP) desde config.json.

    "correo": {
      "smtp_servidor": "mail.mantistcy.cl", "smtp_puerto": 465,
      "imap_servidor": "mail.mantistcy.cl", "imap_puerto": 993,
      "usuario": "...", "clave": "...", "remitente": "...",
      "destinatarios": ["..."], "supervisor": "..."
    }

La clave puede venir también de la variable de entorno ``RPA_CORREO_CLAVE``
(tiene prioridad), para no dejarla escrita en ningún archivo si se prefiere.
config.json está en .gitignore: la clave nunca llega a GitHub.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ_PROYECTO / "config" / "config.json"

OBLIGATORIOS = ("smtp_servidor", "imap_servidor", "usuario", "clave", "remitente")


class ConfigCorreoInvalida(Exception):
    pass


def cargar_config_correo(ruta: Path = RUTA_CONFIG) -> dict[str, Any]:
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigCorreoInvalida(f"No existe {ruta}.") from None
    except ValueError as error:
        raise ConfigCorreoInvalida(f"config.json no es un JSON válido: {error}") from None

    correo = dict(datos.get("correo") or {})
    if os.environ.get("RPA_CORREO_CLAVE"):
        correo["clave"] = os.environ["RPA_CORREO_CLAVE"]

    faltan = [campo for campo in OBLIGATORIOS if not str(correo.get(campo, "")).strip()]
    if faltan:
        raise ConfigCorreoInvalida(
            "Faltan datos en la sección \"correo\" de config.json: " + ", ".join(faltan)
        )

    correo.setdefault("smtp_puerto", 465)
    correo.setdefault("imap_puerto", 993)
    correo.setdefault("ssl", True)
    correo["smtp_puerto"] = int(correo["smtp_puerto"])
    correo["imap_puerto"] = int(correo["imap_puerto"])
    return correo


def describir(config: dict[str, Any]) -> str:
    """Resumen para el log, sin la clave."""
    return (f"SMTP {config['smtp_servidor']}:{config['smtp_puerto']}, "
            f"IMAP {config['imap_servidor']}:{config['imap_puerto']}, "
            f"usuario {config['usuario']}, SSL {'sí' if config.get('ssl', True) else 'no'}")
