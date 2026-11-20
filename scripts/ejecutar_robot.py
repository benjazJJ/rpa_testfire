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


PASOS_PROCESADOR = (
    ("4b · Performer: enviar la cola", ["scripts\\performer.bat"]),
    ("4c · Resumen al supervisor", [sys.executable, "scripts/resumen_supervisor.py", "--enviar"]),
    ("4d · Clasificar respuestas", ["scripts\\clasificar.bat"]),
)


def ejecutar_procesador_con_scripts(bitacora, inicio) -> int:
    resultados = {}
    for nombre, comando in PASOS_PROCESADOR:
        t0 = time.perf_counter()
        if comando[0].endswith(".bat") and sys.platform != "win32":
            resultados[nombre] = "omitido (no es Windows)"
            continue
        proceso = subprocess.run(comando if not comando[0].endswith(".bat") else ["cmd", "/c", comando[0]],
                                 cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
        salida = (proceso.stdout or "").strip()
        sin_novedades = proceso.returncode == 4 or "sin_novedades" in salida
        ok = proceso.returncode == 0 or sin_novedades
        detalle = "sin novedades: no se reenvía" if sin_novedades else (salida.splitlines() or [""])[-1][:300]
        bitacora.evento("Programador", f"Procesador {nombre}", "Exitoso" if ok else "Fallido", detalle, t0)
        resultados[nombre] = "OK" if ok else "ERROR"
        if not ok:
            break  # igual que en Rocketbot: si un paso falla, se detiene la cadena
    todo_ok = all(v != "ERROR" for v in resultados.values())
    bitacora.evento("Programador", "Procesador (modo horario) terminó", "Exitoso" if todo_ok else "Fallido",
                    json.dumps(resultados, ensure_ascii=False), inicio)
    print(json.dumps({"ok": todo_ok, "motor": "scripts", "pasos": resultados}, ensure_ascii=False))
    return 0 if todo_ok else 2


def revisar_instalacion(config: dict[str, Any], rol: str | None = None) -> int:
    """Para encender_robots.bat: avisa antes de programar si Rocketbot no se va a poder lanzar."""
    if rol == "procesador":
        print("[OK] En modo horario el Procesador corre sus pasos con los scripts del repo "
              "(no necesita la licencia de producción de Rocketbot).")
        return 0
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
        print("[!] Ojo: sin licencia de producción, Rocketbot no ejecuta robots desde la tarea programada.")
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
        return revisar_instalacion(cargar_config(), args.rol)

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

    if args.rol == "procesador":
        # Rocketbot sin licencia de producción no ejecuta robots desde la línea de
        # comandos, así que el modo horario corre los mismos pasos del Procesador
        # con sus scripts (la ejecución manual en Rocketbot no cambia).
        return ejecutar_procesador_con_scripts(bitacora, inicio)

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
