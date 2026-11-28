"""
Rutas comunes de la Evaluación 3, iguales en cualquier PC.

La carpeta de salida es ``%USERPROFILE%\\Rocketbot_Salida`` (en el PC de
Benjamín, C:\\Users\\bpalm\\Rocketbot_Salida; en el de Gustavo, la de su
usuario), salvo que la variable de entorno ``RPA_SALIDA`` indique otra.
Es la misma regla que usa ``scripts\\entorno.bat``.
"""

from __future__ import annotations

import os
from pathlib import Path


def carpeta_salida() -> Path:
    if os.environ.get("RPA_SALIDA"):
        return Path(os.environ["RPA_SALIDA"])
    return Path.home() / "Rocketbot_Salida"


def ultimo_archivo(carpeta: Path, patron: str) -> Path:
    """El archivo más reciente que calza con ``patron`` (p. ej. "reporte_final_*.xlsx")."""
    candidatos = [p for p in Path(carpeta).glob(patron) if not p.name.startswith("~$")]
    if not candidatos:
        raise FileNotFoundError(f"No hay archivos {patron} en {carpeta}.")
    return max(candidatos, key=lambda p: p.stat().st_mtime)
