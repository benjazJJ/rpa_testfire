"""
Ejecuta los 5 verbos HTTP contra reqres.in y deja evidencia para Rocketbot.

Indicador IL 2.4 (GET, POST, PUT, PATCH, DELETE con payload y logs).

Uso (lo invoca un .bat que ejecuta el módulo "Run application" de Rocketbot):
    python scripts/http_reqres_rocketbot.py --salida C:\\Users\\bpalm\\Rocketbot_Salida

Contrato con Rocketbot:
- Archivo ``http_reqres_log.json``: un registro por verbo con método, URL,
  payload enviado, código de estado, cuerpo de la respuesta y si el código
  fue el esperado.
- stdout: UNA línea JSON con el resumen (o ``{"ok": false, "error": ...}``).
- ``--solo PATCH`` ejecuta únicamente ese verbo (el módulo nativo de Rocketbot
  no ofrece PATCH) y escribe ``http_patch_log.json``.
- Código de salida 0 si se ejecutaron los 5 verbos y todos devolvieron el
  código esperado; 1 si alguno no lo hizo; 2 si no se pudo ejecutar.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.demo_http_reqres import DemoHttpReqres  # noqa: E402


def ejecutar(salida: Path, tiempo_espera: int = 15, solo: str | None = None) -> dict[str, Any]:
    demo = DemoHttpReqres(tiempo_espera=tiempo_espera)
    if solo is None:
        resultados = demo.ejecutar_demo_completa()
        nombre_log = "http_reqres_log.json"
    elif solo.upper() == "PATCH":
        resultados = [demo.actualizar_parcial_usuario(2, "RPA Architect")]
        nombre_log = "http_patch_log.json"
    else:
        raise ValueError(f"Verbo no soportado en modo --solo: {solo}")

    salida.mkdir(parents=True, exist_ok=True)
    ruta_log = salida / nombre_log
    ruta_log.write_text(
        json.dumps(
            {"fecha": datetime.now().isoformat(timespec="seconds"), "resultados": resultados},
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )

    validos = sum(1 for r in resultados if r.get("valido"))
    return {
        "ok": validos == len(resultados),
        "validos": validos,
        "total": len(resultados),
        "metodos": [
            {
                "metodo": r.get("metodo"),
                "codigo_estado": r.get("codigo_estado"),
                "valido": r.get("valido"),
                "respuesta": r.get("cuerpo_respuesta"),
            }
            for r in resultados
        ],
        "log": str(ruta_log),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta donde se guarda http_reqres_log.json")
    parser.add_argument("--solo", choices=["PATCH"], default=None, help="Ejecuta solo ese verbo")
    parser.add_argument("--timeout", type=int, default=15, help="Tiempo de espera por llamada, en segundos")
    args = parser.parse_args(argv)

    try:
        resumen = ejecutar(args.salida, args.timeout, args.solo)
    except Exception as error:  # noqa: BLE001  (cualquier fallo de red/IO debe salir como JSON)
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}, ensure_ascii=False))
        return 2

    print(json.dumps(resumen, ensure_ascii=False))
    return 0 if resumen["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
