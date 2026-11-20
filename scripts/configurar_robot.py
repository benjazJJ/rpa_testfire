"""
Deja un robot de Rocketbot listo para ESTE PC.

    py scripts/configurar_robot.py procesador
    py scripts/configurar_robot.py encolador

Toma la plantilla de rocketbot/ (la que está en GitHub, sin claves) y genera
``rocketbot/listo/RPA_TestFire_<Rol>_<PC>.json`` con:
- ruta_repo      = la carpeta donde está este repo en este PC;
- ruta_salida    = %USERPROFILE%\\Rocketbot_Salida (la misma que usan los .bat);
- ruta_perfil_ff = %USERPROFILE%\\Rocketbot_FF_Profile (perfil de Firefox del robot);
- la clave del correo, leída de config/config.json (nunca queda en GitHub:
  rocketbot/listo/ está en .gitignore).

Ese archivo es el que se importa en Rocketbot Studio.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.rutas import carpeta_salida  # noqa: E402

PLANTILLAS = {
    "procesador": RAIZ / "rocketbot" / "RPA_TestFire_Procesador.json",
    "encolador": RAIZ / "rocketbot" / "RPA_TestFire_Encolador.json",
}


def recorrer(comandos):
    for c in comandos:
        yield c
        yield from recorrer(c.get("children", []))
        yield from recorrer(c.get("else", []))


def configurar(rol: str) -> Path:
    datos = json.loads(PLANTILLAS[rol].read_text(encoding="utf-8"))
    proyecto = datos["project"]
    valores = {
        "ruta_repo": str(RAIZ),
        "ruta_salida": str(carpeta_salida()),
        "ruta_perfil_ff": str(Path.home() / "Rocketbot_FF_Profile").replace("\\", "/"),
    }
    for variable in proyecto["vars"]:
        if variable["name"] in valores:
            variable["data"] = valores[variable["name"]]

    try:
        config = json.loads((RAIZ / "config" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    correo = config.get("correo") or {}
    for comando in recorrer(proyecto["commands"]):
        if comando["father"] == "configemail" and correo.get("clave"):
            datos_cmd = json.loads(comando["command"])
            datos_cmd["pass"] = correo["clave"]
            if correo.get("usuario"):
                datos_cmd["user"] = correo["usuario"]
            comando["command"] = json.dumps(datos_cmd, ensure_ascii=False, separators=(",", ":"))
        if correo.get("supervisor"):
            for variable in proyecto["vars"]:
                if variable["name"] == "correo_supervisor":
                    variable["data"] = correo["supervisor"]

    carpeta = RAIZ / "rocketbot" / "listo"
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / f"RPA_TestFire_{rol.capitalize()}_{platform.node()}.json"
    salida.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    carpeta_salida().mkdir(parents=True, exist_ok=True)
    return salida


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in PLANTILLAS:
        print("Uso: configurar_robot.py procesador|encolador")
        return 2
    ruta = configurar(argv[0])
    print(f"[OK] Robot listo para este PC: {ruta}")
    print("     Impórtalo en Rocketbot Studio (Robot -> Importar) y ejecútalo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
