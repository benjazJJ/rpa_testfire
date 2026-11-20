"""
Mejora creativa (Evaluación 3): ejecución programada con horario permitido.

El Programador de tareas de Windows corre ``ejecutar_robot.bat`` a las 09:00;
ese .bat llama a este script, que:

1. Revisa si AHORA está dentro del horario permitido (por defecto lunes a
   viernes de 08:00 a 18:00).
2. Fuera de horario: NO lanza el robot y registra el intento (quién, en qué
   PC, a qué hora) en el .log y en la Auditoría RPA. Salida 3.
3. Dentro de horario: lanza el robot de Rocketbot por línea de comandos
   (``rocketbot.exe -start=<robot> -db="<ruta>"``, según la documentación de
   Rocketbot), espera a que termine y registra el resultado.

Configuración en config/config.json (cada PC pone sus propias rutas):

    "ejecucion": {
      "rocketbot_exe": "C:\\\\Rocketbot\\\\rocketbot.exe",
      "robot": "RPA_TestFire_Eval3",
      "db": "C:\\\\Rocketbot\\\\robot.db",
      "horario": {"dias": [0, 1, 2, 3, 4], "desde": "08:00", "hasta": "18:00"},
      "tiempo_maximo_min": 30
    }

``dias``: 0 = lunes ... 6 = domingo. ``--forzar`` salta el control de
horario (para pruebas manuales, y queda registrado que se forzó).
"""

from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
import time
from datetime import datetime, time as hora
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402

RUTA_CONFIG = RAIZ / "config" / "config.json"
HORARIO_DEFECTO = {"dias": [0, 1, 2, 3, 4], "desde": "08:00", "hasta": "18:00"}
NOMBRES_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def cargar_config(ruta: Path = RUTA_CONFIG) -> dict[str, Any]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8")).get("ejecucion") or {}
    except (OSError, ValueError):
        return {}


def dentro_de_horario(momento: datetime, horario: dict[str, Any]) -> tuple[bool, str]:
    dias = horario.get("dias", HORARIO_DEFECTO["dias"])
    desde = hora.fromisoformat(horario.get("desde", HORARIO_DEFECTO["desde"]))
    hasta = hora.fromisoformat(horario.get("hasta", HORARIO_DEFECTO["hasta"]))
    permitido = ", ".join(NOMBRES_DIAS[d] for d in dias) + f" de {desde:%H:%M} a {hasta:%H:%M}"
    if momento.weekday() not in dias:
        return False, f"{NOMBRES_DIAS[momento.weekday()]} no es un día permitido ({permitido})"
    if not desde <= momento.time() <= hasta:
        return False, f"{momento:%H:%M} está fuera del horario permitido ({permitido})"
    return True, f"dentro del horario permitido ({permitido})"


def revisar_instalacion(config: dict[str, Any]) -> int:
    """Para encender_robots.bat: avisa antes de programar si Rocketbot no se va a poder lanzar."""
    exe, db = config.get("rocketbot_exe"), config.get("db")
    errores = []
    if not exe or not Path(exe).exists():
        errores.append(f'rocketbot_exe: no existe "{exe}". Pon la ruta real de rocketbot.exe.')
    if not db or not Path(db).exists():
        errores.append(f'db: no existe "{db}". Pon la ruta de la base de robots de Rocketbot.')
    for error in errores:
        print(f"[X] {error}")
    if not errores:
        print(f"[OK] Rocketbot: {exe}")
    return 1 if errores else 0


def main(argv: list[str] | None = None, ahora: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lanza el robot solo dentro del horario permitido.")
    parser.add_argument("--forzar", action="store_true", help="Ignora el horario (queda registrado)")
    parser.add_argument("--solo-revisar", action="store_true", help="Revisa el horario sin lanzar el robot")
    parser.add_argument("--rol", choices=("encolador", "procesador"),
                        help="Robot a lanzar: RPA_TestFire_Encolador o RPA_TestFire_Procesador")
    parser.add_argument("--revisar-instalacion", action="store_true",
                        help="Solo revisa que config.json tenga Rocketbot bien configurado")
    parser.add_argument("--sin-sheets", action="store_true")
    args = parser.parse_args(argv)

    if args.revisar_instalacion:
        return revisar_instalacion(cargar_config())

    config = cargar_config()
    bitacora = Bitacora(crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    usuario = getpass.getuser()
    momento = ahora or datetime.now()
    inicio = time.perf_counter()

    permitido, motivo = dentro_de_horario(momento, config.get("horario", HORARIO_DEFECTO))
    if not permitido and not args.forzar:
        bitacora.evento("Programador", "Intento de ejecución fuera de horario", "Advertencia",
                        f"Bloqueado: {motivo}. Usuario de Windows: {usuario}", inicio)
        print(json.dumps({"ok": False, "fuera_de_horario": True, "motivo": motivo, "usuario": usuario},
                         ensure_ascii=False))
        return 3
    if not permitido:
        bitacora.evento("Programador", "Ejecución forzada fuera de horario", "Advertencia",
                        f"{motivo}. Forzada por {usuario}", inicio)
    else:
        bitacora.info("Programador: %s; usuario %s", motivo, usuario)

    if args.solo_revisar:
        print(json.dumps({"ok": True, "permitido": permitido, "motivo": motivo}, ensure_ascii=False))
        return 0

    exe, robot, db = config.get("rocketbot_exe"), config.get("robot"), config.get("db")
    if args.rol:
        robot = f"RPA_TestFire_{args.rol.capitalize()}"
    if not (exe and robot and db):
        mensaje = "Falta \"ejecucion\" en config.json (rocketbot_exe, robot y db)."
        bitacora.evento("Programador", "Lanzar robot Rocketbot", "Fallido", mensaje, inicio)
        print(json.dumps({"ok": False, "error": mensaje}, ensure_ascii=False))
        return 2
    if not Path(exe).exists():
        mensaje = f"No existe Rocketbot en {exe}."
        bitacora.evento("Programador", "Lanzar robot Rocketbot", "Fallido", mensaje, inicio)
        print(json.dumps({"ok": False, "error": mensaje}, ensure_ascii=False))
        return 2

    comando = [exe, f"-start={robot}", f"-db={db}"]
    bitacora.evento("Programador", "Lanzar robot Rocketbot", "En proceso", " ".join(comando), inicio)
    limite = int(config.get("tiempo_maximo_min", 30)) * 60
    try:
        resultado = subprocess.run(comando, cwd=Path(exe).parent, timeout=limite)
        codigo = resultado.returncode
    except subprocess.TimeoutExpired:
        bitacora.evento("Programador", "Robot Rocketbot terminó", "Fallido",
                        f"Superó el tiempo máximo de {limite // 60} minutos", inicio)
        print(json.dumps({"ok": False, "error": "tiempo máximo superado"}, ensure_ascii=False))
        return 2

    estado = "Exitoso" if codigo == 0 else "Fallido"
    bitacora.evento("Programador", "Robot Rocketbot terminó", estado, f"Código de salida {codigo}", inicio)
    print(json.dumps({"ok": codigo == 0, "codigo_salida": codigo}, ensure_ascii=False))
    return 0 if codigo == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
