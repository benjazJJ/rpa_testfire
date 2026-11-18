"""
Subproceso 4c (Evaluación 3): arma el correo de resumen para el supervisor.

Rocketbot lo envía con su comando nativo "Enviar email SMTP" (así se ve en
la demo, como en la clase). Este script solo prepara los textos:

    py scripts/resumen_supervisor.py --excel <reporte_final_X.xlsx>

stdout: UNA línea JSON con ``para``, ``asunto``, ``mensaje`` y ``adjunto``.
En Rocketbot se lee con "Ejecutar Python" (json.loads + SetVar) y cada
campo se pega en el comando Enviar email SMTP.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.cola_correos import RUTA_COLA, ColaCorreos  # noqa: E402
from src.config_correo import RUTA_CONFIG  # noqa: E402
from src.rutas import carpeta_salida, ultimo_archivo  # noqa: E402


def leer_referencia(excel: Path) -> dict[str, str]:
    """Valor del dólar y fecha desde la hoja Referencia externa."""
    try:
        libro = load_workbook(excel, read_only=True, data_only=True)
        filas = {str(a): b for a, b, *_ in libro["Referencia externa"].iter_rows(values_only=True) if a}
        libro.close()
    except (KeyError, OSError):
        return {}
    return {"dolar": filas.get("Valor usado (CLP por USD)"), "fecha": filas.get("Fecha del valor"),
            "origen": filas.get("Origen del dato")}


def contar_excepciones(excel: Path) -> int:
    try:
        libro = load_workbook(excel, read_only=True)
        total = max(libro["Discrepancias"].max_row - 1, 0)
        libro.close()
        return total
    except (KeyError, OSError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepara el correo de resumen para el supervisor.")
    parser.add_argument("--excel", type=Path, help="Reporte final (por defecto, el más reciente)")
    parser.add_argument("--cola", type=Path, default=RUTA_COLA)
    args = parser.parse_args(argv)
    try:
        args.excel = args.excel or ultimo_archivo(carpeta_salida(), "reporte_final_*.xlsx")
    except FileNotFoundError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    try:
        config = json.loads(RUTA_CONFIG.read_text(encoding="utf-8")).get("correo", {})
    except (OSError, ValueError):
        config = {}
    para = config.get("supervisor") or (config.get("destinatarios") or [""])[0]
    if not para:
        print(json.dumps({"ok": False, "error": "Falta \"supervisor\" en la sección correo de config.json."},
                         ensure_ascii=False))
        return 2

    cola = ColaCorreos(args.cola).resumen()
    ref = leer_referencia(args.excel)
    excepciones = contar_excepciones(args.excel)
    hoy = datetime.now().strftime("%d-%m-%Y %H:%M")
    asunto = f"[RPA TestFire] Resumen de ejecución {hoy}: {excepciones} excepciones"
    mensaje = (
        f"Hola,\n\nResumen de la ejecución del RPA TestFire ({hoy}):\n\n"
        f"- Excepciones de conciliación: {excepciones}\n"
        f"- Dólar usado: {ref.get('dolar', 's/d')} CLP ({ref.get('fecha', 's/d')}, {ref.get('origen', 's/d')})\n"
        f"- Correos a responsables: {cola['ENVIADO']} enviados, {cola['ERROR']} por reintentar, "
        f"{cola['FALLIDO']} fallidos, {cola['PENDIENTE']} pendientes\n\n"
        "Se adjunta el reporte final con las hojas Discrepancias, Referencia externa y "
        "Seguimiento de envíos.\n\n"
        "Correo generado automáticamente por el RPA TestFire (proyecto académico ATY1102)."
    )
    print(json.dumps({"ok": True, "para": para, "asunto": asunto, "mensaje": mensaje,
                      "adjunto": str(args.excel.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
