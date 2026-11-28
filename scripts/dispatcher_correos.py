"""
Subproceso 4a (Evaluación 3): DISPATCHER. Encola los correos; no envía nada.

Lee la hoja "Discrepancias" del reporte final (ya con ``monto_clp``), le
asigna prioridad a cada excepción, la reparte entre los destinatarios y
crea los casos PENDIENTE en la cola (``data/cola/cola_correos.db``).

    py scripts/dispatcher_correos.py --excel <reporte_final_X.xlsx>

Modos:
- ``agrupado`` (por defecto): UN correo por destinatario con todas sus
  excepciones y el Excel adjunto. Es el modo responsable: 1000
  excepciones entre 3 analistas son 3 correos, no 1000.
- ``por-caso``: un correo por excepción. Solo para demostrar volumen,
  siempre con el performer en modo simulación.

Demo de volumen: ``--demo-volumen 1000 --demo-invalido 401`` encola 1000
casos sintéticos (destinatarios @example.com, que nunca salen por un canal
real) y deja el 401 con una dirección mal escrita, para mostrar que el
performer lo marca y sigue con el 402.

Destinatarios reales: ``--destinatarios a@duocuc.cl,b@duocuc.cl`` o en
``config/config.json`` -> ``"correo": {"destinatarios": [...]}``. Si no hay
ninguno, se usan direcciones de prueba @example.com.

stdout: UNA línea JSON con el resumen. Salida 0 si encoló, 2 si falló.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402
from src.cola_correos import abrir_cola  # noqa: E402
from src.datos_sinteticos import GeneradorDatosSinteticos  # noqa: E402
from src.rutas import carpeta_salida, ultimo_archivo  # noqa: E402

RUTA_CONFIG = RAIZ / "config" / "config.json"
PRIORIDAD_NUMERO = {"Alta": 1, "Media": 2, "Baja": 3, "": 3}
MAX_FILAS_EN_CUERPO = 25


def leer_excepciones(excel: Path) -> list[dict[str, Any]]:
    libro = load_workbook(excel, read_only=True, data_only=True)
    if "Discrepancias" not in libro.sheetnames:
        raise ValueError(f"{excel.name} no tiene la hoja 'Discrepancias'.")
    filas = list(libro["Discrepancias"].iter_rows(values_only=True))
    libro.close()
    if not filas:
        return []
    encabezados = [str(c or "").strip().lower() for c in filas[0]]
    excepciones = []
    for fila in filas[1:]:
        registro = dict(zip(encabezados, fila))
        if not registro.get("id_transaccion") or registro.get("estado_conciliacion") in (None, "", "Conciliado"):
            continue
        registro["prioridad_revision"] = GeneradorDatosSinteticos.calcular_prioridad(
            {k: ("" if v is None else v) for k, v in registro.items()}
        )
        excepciones.append(registro)
    return excepciones


def cargar_destinatarios(argumento: str | None) -> list[str]:
    if argumento:
        return [d.strip() for d in argumento.split(",") if d.strip()]
    try:
        config = json.loads(RUTA_CONFIG.read_text(encoding="utf-8"))
        return [d.strip() for d in config.get("correo", {}).get("destinatarios", []) if d.strip()]
    except (OSError, ValueError):
        return []


def formato_clp(valor: Any) -> str:
    try:
        numero = Decimal(str(valor))
        signo = "-" if numero < 0 else ""
        return f"{signo}${abs(numero):,.0f}".replace(",", ".") + " CLP"
    except (InvalidOperation, ValueError):
        return "s/d"


def linea_caso(e: dict[str, Any]) -> str:
    return (
        f"- [{e['prioridad_revision'] or 'Baja'}] Tx {e['id_transaccion']} | cuenta {e.get('id_cuenta', '')} | "
        f"{e.get('accion', '')} | {e.get('monto', '')} USD ({formato_clp(e.get('monto_clp'))}) | "
        f"{e['estado_conciliacion']}: {e.get('detalle_conciliacion') or ''}"
    )


PIE = (
    "\nPara cerrar la revisión, responda este correo con APROBADO o RECHAZADO en el asunto "
    "o en la primera línea. El robot clasificará su respuesta automáticamente.\n\n"
    "Correo generado automáticamente por el RPA TestFire (proyecto académico ATY1102). "
    "Datos de demotestfire.azurewebsites.net, sitio bancario ficticio: no contiene información real de clientes."
)


def armar_agrupado(excepciones, destinatarios, lote, adjunto) -> list[dict[str, Any]]:
    """Un correo por destinatario, con sus casos repartidos por turnos."""
    reparto: dict[str, list[dict[str, Any]]] = {d: [] for d in destinatarios}
    ordenadas = sorted(excepciones, key=lambda e: PRIORIDAD_NUMERO[e["prioridad_revision"]])
    for i, excepcion in enumerate(ordenadas):
        reparto[destinatarios[i % len(destinatarios)]].append(excepcion)

    casos = []
    for destinatario, suyas in reparto.items():
        if not suyas:
            continue
        altas = sum(1 for e in suyas if e["prioridad_revision"] == "Alta")
        detalle = "\n".join(linea_caso(e) for e in suyas[:MAX_FILAS_EN_CUERPO])
        if len(suyas) > MAX_FILAS_EN_CUERPO:
            detalle += f"\n... y {len(suyas) - MAX_FILAS_EN_CUERPO} más en el Excel adjunto."
        cuerpo = (
            f"Hola,\n\nEl RPA TestFire detectó {len(suyas)} excepciones de conciliación asignadas a usted "
            f"({altas} de prioridad alta). Los montos en pesos usan el dólar observado del día "
            f"(fuente: mindicador.cl).\n\n{detalle}\n{PIE}"
        )
        casos.append({
            "clave_unica": f"{lote}|{destinatario}",
            "destinatario": destinatario,
            "asunto": f"[RPA TestFire] {len(suyas)} excepciones por revisar ({altas} alta) - lote {lote}",
            "cuerpo": cuerpo,
            "adjunto": str(adjunto) if adjunto else None,
            "casos": [str(e["id_transaccion"]) for e in suyas],
            "prioridad": min(PRIORIDAD_NUMERO[e["prioridad_revision"]] for e in suyas),
        })
    return casos


def armar_por_caso(excepciones, destinatarios, lote) -> list[dict[str, Any]]:
    casos = []
    for i, e in enumerate(excepciones):
        destinatario = destinatarios[i % len(destinatarios)]
        casos.append({
            "clave_unica": f"{lote}|{e['id_transaccion']}|{e['estado_conciliacion']}",
            "destinatario": destinatario,
            "asunto": f"[RPA TestFire] Revisar transacción {e['id_transaccion']} ({e['prioridad_revision'] or 'Baja'})",
            "cuerpo": f"Hola,\n\nExcepción detectada por el RPA TestFire:\n\n{linea_caso(e)}\n{PIE}",
            "casos": [str(e["id_transaccion"])],
            "prioridad": PRIORIDAD_NUMERO[e["prioridad_revision"]],
        })
    return casos


def armar_demo_volumen(excepciones, cantidad: int, invalido: int | None, lote) -> list[dict[str, Any]]:
    """Casos sintéticos para probar la cola con volumen, solo @example.com."""
    base = excepciones or [{"id_transaccion": "0", "estado_conciliacion": "Con diferencias",
                            "prioridad_revision": "Media", "monto": "0"}]
    destinatarios = [f"analista{n}@example.com" for n in range(1, 6)]
    demo = []
    for n in range(1, cantidad + 1):
        e = dict(base[(n - 1) % len(base)])
        e["id_transaccion"] = f"DEMO{n:05d}"
        demo.append(e)
    casos = armar_por_caso(demo, destinatarios, lote)
    for caso in casos:
        caso["prioridad"] = 2  # misma prioridad: se procesan en orden 1, 2, 3... (más claro en la demo)
    if invalido and 1 <= invalido <= len(casos):
        casos[invalido - 1]["destinatario"] = "analista@@example.com"  # dirección mal escrita
    return casos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatcher: encola los correos de excepciones.")
    parser.add_argument("--excel", type=Path, help="reporte_final_X.xlsx (por defecto, el más reciente de la salida)")
    parser.add_argument("--modo", choices=["agrupado", "por-caso"], default="agrupado")
    parser.add_argument("--destinatarios", help="Correos separados por coma (si no, config.json)")
    parser.add_argument("--lote", help="Nombre del lote (por defecto, fecha y hora)")
    parser.add_argument("--sin-adjunto", action="store_true", help="No adjuntar el Excel (modo agrupado)")
    parser.add_argument("--cola", type=Path, default=None,
                        help="SQLite local para pruebas (por defecto: Neon si está en config.json)")
    parser.add_argument("--demo-volumen", type=int, default=0, help="Encola N casos sintéticos (@example.com)")
    parser.add_argument("--demo-invalido", type=int, default=None, help="Caso N de la demo con dirección inválida")
    parser.add_argument("--id-ejecucion", default=None)
    parser.add_argument("--sin-sheets", action="store_true")
    args = parser.parse_args(argv)

    bitacora = Bitacora(args.id_ejecucion or crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    inicio = time.perf_counter()
    try:
        if not args.excel and not args.demo_volumen:
            args.excel = ultimo_archivo(carpeta_salida(), "reporte_final_2*.xlsx")
        adjunto = None
        excepciones = leer_excepciones(args.excel) if args.excel else []
        if args.demo_volumen:
            lote = args.lote or f"DEMO_{datetime.now():%Y%m%d_%H%M%S}"
            casos = armar_demo_volumen(excepciones, args.demo_volumen, args.demo_invalido, lote)
            destinatarios = ["analista1..5@example.com"]
        else:
            if not args.excel:
                raise ValueError("Falta --excel (o usa --demo-volumen).")
            lote = args.lote or f"LOTE_{datetime.now():%Y%m%d_%H%M%S}"
            destinatarios = cargar_destinatarios(args.destinatarios)
            if not destinatarios:
                destinatarios = [f"analista{n}@example.com" for n in range(1, 4)]
                bitacora.advertencia("Sin destinatarios configurados: se usan direcciones de prueba @example.com.")
            adjunto = None if args.sin_adjunto else args.excel.resolve()
            casos = (armar_agrupado(excepciones, destinatarios, lote, adjunto) if args.modo == "agrupado"
                     else armar_por_caso(excepciones, destinatarios, lote))

        cola = abrir_cola(args.cola, avisar=bitacora.info)
        bitacora.info("Dispatcher: cola %s", "COMPARTIDA (Neon)" if cola.compartida else "local (SQLite)")
        resultado_cola = cola.encolar(casos, lote, bitacora.id_ejecucion, adjunto=adjunto)
    except Exception as error:
        bitacora.evento("Dispatcher", "Encolar correos", "Fallido", str(error), inicio)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    detalle = (f"Lote {lote}: {len(excepciones)} excepciones -> {resultado_cola['encolados']} correos "
               f"encolados ({resultado_cola['ya_existian']} ya estaban), modo "
               f"{'demo' if args.demo_volumen else args.modo}")
    bitacora.evento("Dispatcher", "Encolar correos", "Exitoso", detalle, inicio,
                    registros=resultado_cola["encolados"])
    print(json.dumps({
        "ok": True, "id_ejecucion": bitacora.id_ejecucion, "lote": lote,
        "excepciones": len(excepciones), "destinatarios": destinatarios, **resultado_cola,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
