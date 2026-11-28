"""
Deja en la Auditoría RPA y en logs/ quién encendió o apagó el modo horario,
en qué PC y cuándo (lo llaman encender_robots.bat y apagar_robots.bat).

    py scripts/registrar_interruptor.py ENCENDIDO procesador
"""

import getpass
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402

if __name__ == "__main__":
    accion, rol = (sys.argv[1:] + ["?", "?"])[:2]
    Bitacora(crear_id_ejecucion()).evento(
        "Programador", f"Modo horario {accion}", "Exitoso",
        f"Robot {rol} {accion.lower()} por {getpass.getuser()}", time.perf_counter())
