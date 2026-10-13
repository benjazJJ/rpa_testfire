"""
Pipeline end-to-end de la Evaluación 2: conecta la conciliación real
(Excel/SQLite) con el reporte a sistema externo vía los 5 métodos HTTP.

No es un script de ejemplo aislado: se conecta a los movimientos tal
como los entrega TestFireBot.extraer_movimientos() (ver
src/testfire_bot.py) y a la conciliación de ConciliadorMovimientosSQL.

1. Concilia contra el maestro SQLite (ConciliadorMovimientosSQL).
2. POST  -> registra el resumen real de la ejecución en reqres.in.
3. PUT   -> marca el registro como "pendiente de revisión" si hubo
            diferencias, o "conciliado sin diferencias" si no las hubo.
4. GET   -> trae usuarios de reqres.in y los usa como "responsable de
            revisión" ficticio para cada movimiento con diferencias
            (solución creativa, IL 2.5).
5. PATCH -> cierra el ciclo marcando el registro como revisado.
6. DELETE-> limpia el registro de prueba.

Dos puntos de entrada:

- ``reportar_resultado_http(resultados, resumen, id_ejecucion)``:
  solo el reporte HTTP, para usar en main.py justo después de su propio
  paso "Conciliar movimientos" (PASO 5), sin conciliar dos veces.

- ``ejecutar_integracion(movimientos, id_ejecucion)``: conciliación +
  reporte HTTP en un solo llamado, para pruebas independientes (ver
  bloque __main__) o para un paso "Script (Python)" de Rocketbot que
  reciba los movimientos ya extraídos.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.conciliacion_sqlite import ConciliadorMovimientosSQL  # noqa: E402
from src.demo_http_reqres import DemoHttpReqres  # noqa: E402

# reqres.in es un endpoint de demo: no persiste lo que se crea con POST,
# así que para encadenar PUT/PATCH/DELETE sobre "el mismo" registro se usa
# un ID que la API sí reconoce (documentado también en demo_http_reqres.py).
ID_REGISTRO_EXTERNO = 2


def reportar_resultado_http(
    resultados_conciliacion: list[dict[str, Any]],
    resumen_conciliacion: dict[str, Any],
    id_ejecucion: str,
) -> dict[str, Any]:
    """
    Reporta a reqres.in un resultado de conciliación ya calculado,
    usando los 5 métodos HTTP. Devuelve la traza completa.

    Separada de ``ejecutar_integracion`` para que main.py pueda llamarla
    justo después de su propio paso de conciliación, sin repetirlo.
    """

    diferencias = [
        r for r in resultados_conciliacion if r["estado_conciliacion"] == "Con diferencias"
    ]

    http = DemoHttpReqres()
    traza: dict[str, Any] = {
        "id_ejecucion": id_ejecucion,
        "resumen_conciliacion": resumen_conciliacion,
    }

    # 1. POST — el payload es el resumen REAL de esta conciliación.
    traza["post_registro"] = http.crear_usuario(
        nombre=f"Ejecucion {id_ejecucion}",
        puesto=(
            f"{resumen_conciliacion['conciliados']} conciliados, "
            f"{resumen_conciliacion['con_diferencias']} con diferencias, "
            f"{resumen_conciliacion['solo_testfire']} solo TestFire, "
            f"{resumen_conciliacion['solo_maestro']} solo maestro"
        ),
    )

    # 2. PUT
    estado_revision = (
        "Con diferencias, pendiente de revisión"
        if diferencias
        else "Conciliado sin diferencias"
    )
    traza["put_actualizacion"] = http.actualizar_usuario(
        ID_REGISTRO_EXTERNO, f"Ejecucion {id_ejecucion}", estado_revision
    )

    # 3. GET + enriquecimiento creativo
    enriquecimiento = http.listar_usuarios()
    traza["get_enriquecimiento"] = enriquecimiento

    if enriquecimiento["valido"] and diferencias:
        responsables = enriquecimiento["cuerpo_respuesta"].get("data", [])
        for indice, movimiento in enumerate(diferencias):
            if responsables:
                responsable = responsables[indice % len(responsables)]
                movimiento["responsable_revision"] = (
                    f"{responsable['first_name']} {responsable['last_name']}"
                )

    # 4. PATCH
    traza["patch_cierre"] = http.actualizar_parcial_usuario(
        ID_REGISTRO_EXTERNO, "Revisado por el equipo RPA"
    )

    # 5. DELETE
    traza["delete_limpieza"] = http.eliminar_usuario(ID_REGISTRO_EXTERNO)

    traza["movimientos_con_diferencias"] = diferencias

    return traza


def ejecutar_integracion(
    movimientos: list[dict[str, Any]],
    id_ejecucion: str,
) -> dict[str, Any]:
    """Concilia y reporta el resultado a reqres.in en un solo llamado."""

    resultados, resumen = ConciliadorMovimientosSQL().conciliar(movimientos)
    return reportar_resultado_http(resultados, resumen, id_ejecucion)


if __name__ == "__main__":
    import json

    # --- Prueba sin Selenium: usa el propio maestro como "web" simulada ---
    conciliador_mock = ConciliadorMovimientosSQL()
    maestro = conciliador_mock._leer_maestro()  # noqa: SLF001 (reuso intencional)

    movimientos_simulados = [
        {
            "id_transaccion": m["id_transaccion"],
            "fecha_hora": m["fecha_hora"],
            "id_cuenta": m["id_cuenta"],
            "accion": m["accion"],
            "monto": str(m["monto"]),
        }
        for m in list(maestro.values())[:5]
    ]

    # Se fuerza una diferencia real para poder mostrar el enriquecimiento
    # con datos de reqres.in en la traza de salida.
    if movimientos_simulados:
        movimientos_simulados[0]["accion"] = "Transferencia simulada (prueba)"

    traza = ejecutar_integracion(movimientos_simulados, id_ejecucion="RPA_PRUEBA_LOCAL")

    # default=str: los montos conciliados vienen como Decimal (para evitar
    # errores de redondeo), que json.dumps no serializa de forma nativa.
    print(json.dumps(traza, indent=2, ensure_ascii=False, default=str))