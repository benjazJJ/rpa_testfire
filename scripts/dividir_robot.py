"""
Divide rocketbot/RPA_TestFire_Eval3.json en dos robots (plantillas sin claves):

- RPA_TestFire_Encolador.json  (PC de Gustavo): login, extracción, conciliación,
  API, Excel y ENCOLAR en la cola compartida.
- RPA_TestFire_Procesador.json (cualquier PC): LEER COLA y enviar, correo al
  supervisor y clasificar respuestas.

    py scripts/dividir_robot.py
"""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "rocketbot" / "RPA_TestFire_Eval3.json"


def numerar(comandos, prefijo=""):
    for i, c in enumerate(comandos):
        c["index"] = i
        c["line"] = f"{prefijo}{i + 1}"
        numerar(c.get("children", []), c["line"] + ".")
        numerar(c.get("else", []), c["line"] + ".")


def bloque(comandos, prefijo):
    return next(c for c in comandos if c.get("description", "").startswith(prefijo))


def clon(base, **cambios):
    c = copy.deepcopy(base)
    c.update(id=str(uuid.uuid4()))
    c.update(cambios)
    return c


def armar(datos, nombre, descripcion, comandos):
    nuevo = copy.deepcopy(datos)
    p = nuevo["project"]
    p["profile"]["name"] = nombre
    p["profile"]["description"] = descripcion
    for idioma in p["expose"]["title"]:
        p["expose"]["title"][idioma] = f"{nombre} expose"
    numerar(comandos)
    p["commands"] = comandos
    return nuevo


def main() -> None:
    datos = json.loads(ORIGEN.read_text(encoding="utf-8"))
    cmds = datos["project"]["commands"]
    inicio_log, cierre = cmds[0], bloque(cmds, "Subproceso 5")
    set_continuar = next(c for c in cmds if c["father"] == "setVar" and c.get("var") == "continuar")

    def cierre_para(rol):
        c = copy.deepcopy(cierre)
        c["children"][0]["command"] = f"=== RPA TestFire · {rol} · fin OK === Revisar la Auditoría RPA y logs\\rpa_AAAAMMDD.log"
        c["else"][0]["command"] = (f"=== RPA TestFire · {rol} · fin CON ERRORES === Revisar el paso marcado arriba y "
                                   "{ruta_salida}\\*_errores.log")
        return c

    # ---- Encolador: todo hasta el dispatcher ----
    hasta = cmds.index(bloque(cmds, "Subproceso 4a")) + 1
    encolador = copy.deepcopy(cmds[:hasta])
    encolador[0]["command"] = ("=== RPA TestFire · ENCOLADOR · inicio === Lee la entrada, bloquea la cola, "
                               "encola y desbloquea. Repo en {ruta_repo}")
    encolador.append(cierre_para("ENCOLADOR"))

    # ---- Procesador: leer cola en adelante ----
    procesador = [
        clon(inicio_log, command="=== RPA TestFire · PROCESADOR · inicio === Lee la cola compartida (Neon) "
                                 "y procesa los casos. Repo en {ruta_repo}"),
        clon(set_continuar, command="True"),
        *copy.deepcopy([bloque(cmds, p) for p in ("Subproceso 4b", "Subproceso 4c", "Subproceso 4d")]),
        cierre_para("PROCESADOR"),
    ]
    procesador[2]["description"] = "Subproceso 4b · Leer cola y enviar"

    for nombre, desc, comandos in (
        ("RPA_TestFire_Encolador", "Evaluación 3 ATY1102 - PC encolador: login TestFire, extracción, "
         "conciliación, API dólar, Excel y encolar en la cola compartida", encolador),
        ("RPA_TestFire_Procesador", "Evaluación 3 ATY1102 - PC procesador: lee la cola compartida, envía los "
         "correos, resumen al supervisor y clasificación de respuestas", procesador),
    ):
        ruta = RAIZ / "rocketbot" / f"{nombre}.json"
        ruta.write_text(json.dumps(armar(datos, nombre, desc, comandos), ensure_ascii=False), encoding="utf-8")
        print(f"{ruta.name}: {len(comandos)} bloques")


if __name__ == "__main__":
    main()
