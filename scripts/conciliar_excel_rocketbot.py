"""
Concilia el Excel consolidado generado por Rocketbot contra el maestro SQLite.

Flujo (IL 2.3, integración Excel + SQL):
    Rocketbot extrae la tabla de TestFire -> ``consolidado.xlsx`` (A:E)
    -> este script lo compara con ``movimientos_master`` (SQLite)
    -> genera un Excel de discrepancias + un JSON de resumen.

Uso (lo invoca el módulo "Run application" de Rocketbot):
    python scripts/conciliar_excel_rocketbot.py ^
        --excel C:\\Users\\bpalm\\Rocketbot_Salida\\consolidado.xlsx ^
        --salida C:\\Users\\bpalm\\Rocketbot_Salida

Contrato con Rocketbot:
- stdout: UNA línea JSON con el resumen (o ``{"ok": false, "error": ...}``).
- Archivos: ``discrepancias_<fecha>.xlsx`` y ``resumen_conciliacion.json``
  dentro de ``--salida``.
- Código de salida 0 si se pudo conciliar (haya o no discrepancias: eso es
  resultado de negocio, no un fallo); 2 si no se pudo ejecutar.
- No usa red.

Columnas esperadas en el Excel (posición A..E, tal como las deja Rocketbot):
    Transaction ID | Transaction Time | Account ID | Action | Amount
La fila de encabezado es opcional: se detecta y se omite.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROYECTO))

from src.conciliacion import ConciliadorMovimientos  # noqa: E402
from src.conciliacion_sqlite import ConciliadorMovimientosSQL  # noqa: E402

CLAVES = ("id_transaccion", "fecha_hora", "id_cuenta", "accion", "monto")
ENCABEZADO_ID = {"transaction id", "id transacción", "id transaccion"}


def leer_excel_rocketbot(ruta: Path) -> list[tuple[int, list[Any]]]:
    """Devuelve ``(n_fila, [A..E])`` omitiendo encabezado y filas vacías."""
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el Excel de entrada: {ruta}")

    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        hoja = libro.active
        filas = []
        for n, fila in enumerate(hoja.iter_rows(min_col=1, max_col=5, values_only=True), 1):
            valores = list(fila)
            if all(v is None or str(v).strip() == "" for v in valores):
                continue
            if n == 1 and str(valores[0]).strip().casefold() in ENCABEZADO_ID:
                continue
            filas.append((n, valores))
        return filas
    finally:
        libro.close()


def preparar_movimientos(
    filas: list[tuple[int, list[Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Normaliza cada fila con las reglas de ``ConciliadorMovimientos``.

    Una fila inválida (monto ilegible, ID vacío) o un ID repetido no aborta
    el proceso: se aparta en ``rechazados`` para reportarla. Así un dato
    corrupto del sitio compartido no tumba la conciliación completa.
    """
    normalizador = ConciliadorMovimientos()
    validos: list[dict[str, Any]] = []
    rechazados: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for n_fila, valores in filas:
        crudo = dict(zip(CLAVES, valores))
        try:
            mov = normalizador._normalizar_movimiento(crudo)  # noqa: SLF001
            if mov["id_transaccion"] in vistos:
                raise ValueError(f"ID duplicado '{mov['id_transaccion']}'")
            vistos.add(mov["id_transaccion"])
            # El conciliador normaliza de nuevo: se entrega en crudo, no el
            # resultado ya normalizado, para no depender de su idempotencia.
            validos.append({k: ("" if v is None else str(v)) for k, v in crudo.items()})
        except ValueError as error:
            rechazados.append({"fila_excel": n_fila, "motivo": str(error), **{k: crudo[k] for k in CLAVES}})

    return validos, rechazados


def escribir_reporte(
    ruta: Path, resultados: list[dict[str, Any]], rechazados: list[dict[str, Any]]
) -> None:
    libro = Workbook()
    columnas = [*CLAVES, "estado_conciliacion", "detalle_conciliacion"]

    def volcar(hoja, filas, cols):
        hoja.append(cols)
        for fila in filas:
            # str(): conserva Decimal grandes (p. ej. 1e18) sin pasar por float.
            hoja.append([str(fila.get(c, "")) for c in cols])
        hoja.freeze_panes = "A2"
        for letra, ancho in zip("ABCDEFG", (16, 18, 12, 14, 26, 20, 60)):
            hoja.column_dimensions[letra].width = ancho

    volcar(libro.active, resultados, columnas)
    libro.active.title = "Resultado"
    volcar(
        libro.create_sheet("Discrepancias"),
        [r for r in resultados if r["estado_conciliacion"] != "Conciliado"],
        columnas,
    )
    volcar(
        libro.create_sheet("Rechazados"),
        rechazados,
        ["fila_excel", "motivo", *CLAVES],
    )
    libro.save(ruta)


def ejecutar(excel: Path, db: Path | None, salida: Path) -> dict[str, Any]:
    filas = leer_excel_rocketbot(excel)
    validos, rechazados = preparar_movimientos(filas)

    conciliador = ConciliadorMovimientosSQL(db)
    resultados, resumen = conciliador.conciliar(validos)

    salida.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_reporte = salida / f"discrepancias_{marca}.xlsx"
    escribir_reporte(ruta_reporte, resultados, rechazados)

    resumen_final = {
        "ok": True,
        "excel": str(excel),
        "db": str(conciliador.ruta_db),
        "filas_leidas": len(filas),
        "filas_rechazadas": len(rechazados),
        **resumen,
        "reporte": str(ruta_reporte),
    }
    (salida / "resumen_conciliacion.json").write_text(
        json.dumps(resumen_final, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return resumen_final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--excel", type=Path, required=True, help="consolidado.xlsx generado por Rocketbot")
    parser.add_argument("--db", type=Path, default=None, help="SQLite maestro (por defecto data/entrada/conciliacion_master.db)")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta de salida para reporte y JSON")
    args = parser.parse_args(argv)

    try:
        resumen = ejecutar(args.excel, args.db, args.salida)
    except (FileNotFoundError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    print(json.dumps(resumen, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
