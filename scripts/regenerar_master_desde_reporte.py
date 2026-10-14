"""
Regenera el maestro de conciliación a partir de un reporte real del RPA.

Problema que resuelve: TestFire es un sitio demo público y compartido; su
tabla "Recent Transactions" avanza con el tiempo, por lo que un maestro
capturado semanas atrás ya no comparte ningún ID con la extracción de hoy
(resultado: 0 conciliados, N "Solo en TestFire", N "Solo en maestro").

Uso:
    python scripts/regenerar_master_desde_reporte.py
    python scripts/regenerar_master_desde_reporte.py --reporte data/salida/movimientos_RPA_X.xlsx
    python scripts/regenerar_master_desde_reporte.py --simular-diferencias 4

Qué hace:
1. Toma la hoja "Movimientos" del reporte (por defecto, el más reciente de
   data/salida/). Tiene las mismas 5 columnas que exige el maestro.
2. Respalda el maestro actual como conciliacion_master_<fecha>.xlsx (nunca
   lo sobrescribe sin copia).
3. Escribe el maestro nuevo y regenera la base SQLite.

``--simular-diferencias N`` (opcional, por defecto 0) altera N filas del
maestro NUEVO para que la conciliación tenga casos reales que mostrar
(monto distinto, acción distinta, ID solo en TestFire, ID solo en maestro).
Sirve para la tabla "antes y después" de la evaluación. El script imprime
exactamente qué filas alteró, para poder documentarlo; no se hace nada
oculto.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrar_master_a_sqlite import migrar  # noqa: E402

ENCABEZADOS = ["ID Transacción", "Fecha/Hora", "ID Cuenta", "Acción", "Monto"]


def _reporte_mas_reciente(carpeta: Path) -> Path:
    candidatos = sorted(
        carpeta.glob("movimientos_*.xlsx"), key=lambda p: p.stat().st_mtime
    )
    if not candidatos:
        raise FileNotFoundError(
            f"No hay reportes movimientos_*.xlsx en {carpeta}. "
            "Corre primero main.py o indica uno con --reporte."
        )
    return candidatos[-1]


def _leer_movimientos(reporte: Path) -> list[list]:
    libro = load_workbook(reporte, data_only=True, read_only=True)
    try:
        if "Movimientos" not in libro.sheetnames:
            raise ValueError(f"El reporte {reporte.name} no tiene la hoja 'Movimientos'.")
        filas = list(libro["Movimientos"].iter_rows(values_only=True))
    finally:
        libro.close()

    if [str(c).strip() if c else "" for c in filas[0][:5]] != ENCABEZADOS:
        raise ValueError("La hoja 'Movimientos' no tiene los encabezados esperados.")

    datos = [list(f[:5]) for f in filas[1:] if any(v is not None for v in f)]
    if not datos:
        raise ValueError("El reporte no contiene movimientos.")
    return datos


def _simular_diferencias(datos: list[list], cantidad: int) -> list[str]:
    """Altera filas del maestro nuevo y devuelve la descripción de cada cambio."""
    cambios: list[str] = []
    if cantidad <= 0:
        return cambios

    # Se usan índices separados para que los cambios no se pisen entre sí.
    if cantidad >= 1 and len(datos) > 10:
        datos[2][4] = (datos[2][4] or 0) + 50
        cambios.append(f"ID {datos[2][0]}: monto alterado (+50) -> 'Con diferencias: Monto'")
    if cantidad >= 2 and len(datos) > 10:
        datos[5][3] = "Transfer"
        cambios.append(f"ID {datos[5][0]}: acción alterada -> 'Con diferencias: Acción'")
    if cantidad >= 3 and len(datos) > 10:
        eliminada = datos.pop(8)
        cambios.append(f"ID {eliminada[0]}: eliminado del maestro -> 'Solo en TestFire'")
    if cantidad >= 4:
        datos.append(
            ["99999", datetime.now().replace(second=0, microsecond=0), "800000", "Deposit", 100]
        )
        cambios.append("ID 99999: agregado solo al maestro -> 'Solo en maestro'")
    return cambios


def main() -> None:
    raiz = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reporte", type=Path, default=None)
    parser.add_argument(
        "--maestro", type=Path, default=raiz / "data" / "entrada" / "conciliacion_master.xlsx"
    )
    parser.add_argument(
        "--db", type=Path, default=raiz / "data" / "entrada" / "conciliacion_master.db"
    )
    parser.add_argument("--simular-diferencias", type=int, default=0, metavar="N")
    args = parser.parse_args()

    reporte = args.reporte or _reporte_mas_reciente(raiz / "data" / "salida")
    datos = _leer_movimientos(reporte)
    print(f"[MAESTRO] Fuente: {reporte.name} ({len(datos)} movimientos)")

    if args.maestro.exists():
        respaldo = args.maestro.with_name(
            f"{args.maestro.stem}_{datetime.fromtimestamp(args.maestro.stat().st_mtime):%Y-%m-%d}.xlsx"
        )
        if not respaldo.exists():
            shutil.copy2(args.maestro, respaldo)
            print(f"[MAESTRO] Respaldo del anterior: {respaldo.name}")

    cambios = _simular_diferencias(datos, args.simular_diferencias)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Movimientos"
    hoja.append(ENCABEZADOS)
    for fila in datos:
        hoja.append(fila)
    libro.save(args.maestro)
    print(f"[MAESTRO] Escrito: {args.maestro}")

    for cambio in cambios:
        print(f"[MAESTRO][SIMULADO] {cambio}")

    total = migrar(args.maestro, args.db)
    print(f"[MIGRACIÓN] {total} movimientos cargados en {args.db}")


if __name__ == "__main__":
    main()