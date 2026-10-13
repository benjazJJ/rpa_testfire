"""
Migra el libro maestro de conciliación (Excel) a una base SQLite.

Uso:
    python scripts/migrar_master_a_sqlite.py
    python scripts/migrar_master_a_sqlite.py --origen data/entrada/conciliacion_master.xlsx \
                                               --destino data/entrada/conciliacion_master.db

Por qué este script y no un reemplazo directo del Excel:
- El Excel sigue siendo la fuente editable por el equipo (fácil de revisar
  a mano, versionable en el repo).
- La base SQLite es la fuente que consulta el robot (Rocketbot o Python)
  durante la ejecución: una consulta SQL indexada por ID es más rápida y
  más robusta que reabrir y recorrer el libro completo en cada corrida,
  y permite validar duplicados con una restricción UNIQUE en vez de un
  set en memoria.
- Se reutiliza la misma normalización que ``src/conciliacion.py``
  (Decimal para montos, fecha a "%Y-%m-%d %H:%M", texto en casefold) para
  que ambos caminos (Excel directo o SQLite) devuelvan exactamente los
  mismos resultados de conciliación.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from openpyxl import load_workbook

# Reutiliza las funciones de normalización ya probadas en conciliacion.py
# en vez de duplicar la lógica de parseo de montos/fechas.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.conciliacion import ConciliadorMovimientos  # noqa: E402

ENCABEZADOS_REQUERIDOS = ConciliadorMovimientos.ENCABEZADOS_REQUERIDOS

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS movimientos_master (
    id_transaccion TEXT PRIMARY KEY,
    fecha_hora     TEXT NOT NULL,
    id_cuenta      TEXT NOT NULL,
    accion         TEXT NOT NULL,
    monto          TEXT NOT NULL,   -- Decimal serializado como texto: evita errores de punto flotante
    fecha_hora_original TEXT,
    accion_original      TEXT,
    monto_original        TEXT
);
"""


def leer_master_excel(ruta_excel: Path) -> list[dict]:
    """Lee y normaliza el maestro reutilizando la clase existente."""
    conciliador = ConciliadorMovimientos(ruta_maestro=ruta_excel)
    # _leer_maestro ya valida columnas, vacíos y duplicados antes de devolver.
    return conciliador._leer_maestro()  # noqa: SLF001 (reuso intencional, mismo paquete)


def migrar(ruta_excel: Path, ruta_sqlite: Path) -> int:
    movimientos = leer_master_excel(ruta_excel)

    ruta_sqlite.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta_sqlite)

    try:
        conexion.execute("DROP TABLE IF EXISTS movimientos_master")
        conexion.executescript(ESQUEMA_SQL)

        conexion.executemany(
            """
            INSERT INTO movimientos_master
                (id_transaccion, fecha_hora, id_cuenta, accion, monto)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    m["id_transaccion"],
                    m["fecha_hora"],
                    m["id_cuenta"],
                    m["accion"],
                    str(m["monto"]),
                )
                for m in movimientos
            ],
        )
        conexion.commit()
        return len(movimientos)
    finally:
        conexion.close()


def main() -> None:
    raiz_proyecto = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--origen",
        type=Path,
        default=raiz_proyecto / "data" / "entrada" / "conciliacion_master.xlsx",
        help="Ruta del Excel maestro (por defecto: data/entrada/conciliacion_master.xlsx)",
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=raiz_proyecto / "data" / "entrada" / "conciliacion_master.db",
        help="Ruta de la base SQLite a generar (por defecto: data/entrada/conciliacion_master.db)",
    )
    args = parser.parse_args()

    total = migrar(args.origen, args.destino)
    print(f"[MIGRACIÓN] {total} movimientos cargados en {args.destino}")


if __name__ == "__main__":
    main()
