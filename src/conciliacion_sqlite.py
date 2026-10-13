"""
Conciliación de movimientos bancarios contra el maestro en SQLite.

Misma interfaz pública que ``ConciliadorMovimientos`` (método
``conciliar(movimientos)``), pero la fuente de verdad es la tabla
``movimientos_master`` de ``data/entrada/conciliacion_master.db`` en vez
del Excel. Generar esa base con ``scripts/migrar_master_a_sqlite.py``.

Pensado para invocarse:
- Desde el RPA en Python, en lugar de ConciliadorMovimientos.
- Desde un módulo "Script (Python)" de Rocketbot, pasándole la lista de
  movimientos extraída por el paso de scraping/XPath del flujo.
"""

from __future__ import annotations

import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

# Permite ejecutar este archivo tanto como módulo (python -m src.conciliacion_sqlite)
# como script directo (python src/conciliacion_sqlite.py), que es como lo
# invocaría un paso "Script (Python)" de Rocketbot.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# La normalización (fecha, monto, texto, ID) se reutiliza sin cambios:
# así Excel y SQLite conciliarán siempre con las mismas reglas.
from src.conciliacion import ConciliadorMovimientos  # noqa: E402


class ConciliadorMovimientosSQL:
    """Compara movimientos extraídos con el maestro almacenado en SQLite."""

    def __init__(self, ruta_db: str | Path | None = None):
        raiz_proyecto = Path(__file__).resolve().parent.parent

        self.ruta_db = (
            Path(ruta_db).resolve()
            if ruta_db is not None
            else raiz_proyecto / "data" / "entrada" / "conciliacion_master.db"
        )

        # Las funciones estáticas de normalización no dependen de instancia:
        # se reutilizan directamente desde la clase original.
        self._normalizar_movimiento = ConciliadorMovimientos._normalizar_movimiento
        self._buscar_diferencias = ConciliadorMovimientos._buscar_diferencias

    def _leer_maestro(self) -> dict[str, dict[str, Any]]:
        if not self.ruta_db.exists():
            raise FileNotFoundError(
                "No se encontró la base SQLite en: "
                f"{self.ruta_db}. Genérala con scripts/migrar_master_a_sqlite.py"
            )

        conexion = sqlite3.connect(self.ruta_db)
        try:
            filas = conexion.execute(
                "SELECT id_transaccion, fecha_hora, id_cuenta, accion, monto "
                "FROM movimientos_master"
            ).fetchall()
        finally:
            conexion.close()

        if not filas:
            raise ValueError("La base SQLite no contiene movimientos.")

        return {
            id_transaccion: {
                "id_transaccion": id_transaccion,
                "fecha_hora": fecha_hora,
                "id_cuenta": id_cuenta,
                "accion": accion,
                "monto": Decimal(monto),
            }
            for id_transaccion, fecha_hora, id_cuenta, accion, monto in filas
        }

    def conciliar(
        self, movimientos: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Misma semántica que ConciliadorMovimientos.conciliar()."""

        if not movimientos:
            raise ValueError(
                "No se recibieron movimientos de TestFire para conciliar."
            )

        maestro_por_id = self._leer_maestro()

        # self._normalizar_movimiento es un método de instancia "prestado";
        # necesita un self con _obtener_valor/_normalizar_* disponibles, por
        # eso se delega en una instancia real de la clase original.
        normalizador = ConciliadorMovimientos()
        web = [normalizador._normalizar_movimiento(m) for m in movimientos]

        ids_web: set[str] = set()
        resultados = []

        for movimiento_web in web:
            id_transaccion = movimiento_web["id_transaccion"]

            if id_transaccion in ids_web:
                raise ValueError(
                    "Los movimientos extraídos contienen el ID duplicado "
                    f"'{id_transaccion}'."
                )
            ids_web.add(id_transaccion)

            movimiento_maestro = maestro_por_id.get(id_transaccion)

            if movimiento_maestro is None:
                estado = "Solo en TestFire"
                detalle = "El ID no existe en el maestro SQLite."
            else:
                diferencias = self._buscar_diferencias(
                    movimiento_web, movimiento_maestro
                )
                if diferencias:
                    estado = "Con diferencias"
                    detalle = "Campos diferentes: " + ", ".join(diferencias)
                else:
                    estado = "Conciliado"
                    detalle = "El movimiento coincide con el maestro SQLite."

            resultados.append(
                {**movimiento_web, "estado_conciliacion": estado, "detalle_conciliacion": detalle}
            )

        for id_transaccion, movimiento_maestro in maestro_por_id.items():
            if id_transaccion in ids_web:
                continue
            resultados.append(
                {
                    **movimiento_maestro,
                    "estado_conciliacion": "Solo en maestro",
                    "detalle_conciliacion": "El ID del maestro SQLite no fue encontrado en TestFire.",
                }
            )

        conciliados = sum(1 for r in resultados if r["estado_conciliacion"] == "Conciliado")
        con_diferencias = sum(1 for r in resultados if r["estado_conciliacion"] == "Con diferencias")
        solo_testfire = sum(1 for r in resultados if r["estado_conciliacion"] == "Solo en TestFire")
        solo_maestro = sum(1 for r in resultados if r["estado_conciliacion"] == "Solo en maestro")

        resumen = {
            "total_testfire": len(web),
            "total_maestro": len(maestro_por_id),
            "conciliados": conciliados,
            "con_diferencias": con_diferencias,
            "solo_testfire": solo_testfire,
            "solo_maestro": solo_maestro,
            # Se mantiene "no_conciliados" (= todo lo que no es "Conciliado")
            # porque main.py y GeneradorReporteExcel ya dependen de esta
            # clave con el ConciliadorMovimientos original; conservarla aquí
            # permite reemplazar una clase por la otra sin tocar el resto
            # del RPA.
            "no_conciliados": con_diferencias + solo_testfire + solo_maestro,
        }

        return resultados, resumen


if __name__ == "__main__":
    # Smoke test manual: compara el maestro contra sí mismo (debe salir
    # 100% "Conciliado") para confirmar que la migración fue correcta.
    import json

    conciliador = ConciliadorMovimientosSQL()
    maestro = conciliador._leer_maestro()
    movimientos_prueba = [
        {
            "id_transaccion": m["id_transaccion"],
            "fecha_hora": m["fecha_hora"],
            "id_cuenta": m["id_cuenta"],
            "accion": m["accion"],
            "monto": str(m["monto"]),
        }
        for m in maestro.values()
    ]
    _, resumen = conciliador.conciliar(movimientos_prueba)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))