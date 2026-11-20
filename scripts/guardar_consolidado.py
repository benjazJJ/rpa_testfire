"""
Subproceso 2a (Evaluación 3): escribe la tabla extraída en consolidado.xlsx de una sola vez.

Antes, Rocketbot recorría la tabla fila por fila y celda por celda (un For
con unos 1.100 comandos para 101 filas). Ahora Rocketbot deja la tabla
completa en ``filas_web.json`` y este script la escribe en el Excel de
una vez, con validaciones:

- el JSON debe ser una lista de filas;
- cada fila debe tener exactamente 5 columnas (las demás se descartan y
  se informan, igual que el filtro ``len(f)==5`` del robot);
- la primera fila debe ser el encabezado de TestFire ("Transaction ID"...).

El Excel queda igual que el que generaba Rocketbot (una hoja, las filas
tal como vienen de la web, encabezado incluido), así la validación de
filas y columnas del robot y la conciliación siguen funcionando sin cambios.

    py scripts/guardar_consolidado.py            (lee y escribe en Rocketbot_Salida)

stdout: UNA línea JSON. Salida 0 si escribió el Excel, 2 si no.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402
from src.rutas import carpeta_salida  # noqa: E402

COLUMNAS = 5


def guardar(entrada: Path, salida: Path) -> dict:
    if not entrada.exists():
        raise FileNotFoundError(f"No existe {entrada}: Rocketbot no dejó la tabla extraída.")
    filas = json.loads(entrada.read_text(encoding="utf-8"))
    if not isinstance(filas, list) or not filas:
        raise ValueError("filas_web.json no trae filas.")

    validas = [[("" if c is None else str(c)) for c in f] for f in filas
               if isinstance(f, list) and len(f) == COLUMNAS]
    descartadas = len(filas) - len(validas)
    if not validas:
        raise ValueError("Ninguna fila tiene 5 columnas.")
    if validas[0][0].strip().lower() != "transaction id":
        raise ValueError(f"La primera fila no es el encabezado de TestFire: {validas[0][:2]}")

    libro = Workbook()
    hoja = libro.active
    for fila in validas:
        hoja.append(fila)
    salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(salida)
    return {"filas": len(validas), "movimientos": len(validas) - 1, "descartadas": descartadas,
            "excel": str(salida)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Escribe filas_web.json en consolidado.xlsx de una vez.")
    parser.add_argument("--entrada", type=Path, help="JSON con la tabla (por defecto Rocketbot_Salida/filas_web.json)")
    parser.add_argument("--salida", type=Path, help="Excel a escribir (por defecto Rocketbot_Salida/consolidado.xlsx)")
    parser.add_argument("--sin-sheets", action="store_true")
    args = parser.parse_args(argv)

    carpeta = carpeta_salida()
    entrada = args.entrada or carpeta / "filas_web.json"
    salida = args.salida or carpeta / "consolidado.xlsx"
    bitacora = Bitacora(crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    inicio = time.perf_counter()
    try:
        resultado = guardar(entrada, salida)
    except Exception as error:
        bitacora.evento("Extracción", "Guardar consolidado.xlsx", "Fallido", str(error), inicio)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    bitacora.evento("Extracción", "Guardar consolidado.xlsx", "Exitoso",
                    f"{resultado['movimientos']} movimientos en una sola escritura "
                    f"({resultado['descartadas']} filas descartadas)", inicio, registros=resultado["movimientos"])
    print(json.dumps({"ok": True, **resultado}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
