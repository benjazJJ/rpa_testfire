"""
Subproceso 4c (Evaluación 3): arma el correo de resumen para el supervisor.

Rocketbot lo envía con su comando nativo "Enviar email SMTP" (así se ve en
la demo, como en la clase). Este script solo prepara los textos:

    py scripts/resumen_supervisor.py --excel <reporte_final_X.xlsx>

Deja todo con nombres fijos en la carpeta de salida, para que Rocketbot no
tenga que buscar rutas:
- ``reporte_final_ultimo.xlsx``: copia del reporte final (el adjunto).
- ``mensaje_supervisor.txt``: el texto del correo (``resumen_supervisor.bat``
  lo imprime y Rocketbot lo guarda en una variable).

stdout: UNA línea JSON con ``para``, ``asunto``, ``mensaje`` y ``adjunto``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.cola_correos import abrir_cola  # noqa: E402
from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402
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
    parser.add_argument("--excel", type=Path, help="Reporte final (por defecto, el del último lote)")
    parser.add_argument("--cola", type=Path, default=None, help="SQLite local para pruebas")
    args = parser.parse_args(argv)

    try:
        config = json.loads(RUTA_CONFIG.read_text(encoding="utf-8")).get("correo", {})
    except (OSError, ValueError):
        config = {}
    para = config.get("supervisor") or (config.get("destinatarios") or [""])[0]
    if not para:
        print(json.dumps({"ok": False, "error": "Falta \"supervisor\" en la sección correo de config.json."},
                         ensure_ascii=False))
        return 2

    cola = abrir_cola(args.cola)
    salida = carpeta_salida()
    salida.mkdir(parents=True, exist_ok=True)
    adjunto = salida / "reporte_final_ultimo.xlsx"
    try:
        if args.excel:
            shutil.copyfile(args.excel, adjunto)
        elif not (cola.compartida and cola.descargar_ultimo_adjunto(adjunto)):
            # Cola local (un solo PC): el reporte está en la carpeta de salida.
            shutil.copyfile(ultimo_archivo(salida, "reporte_final_2*.xlsx"), adjunto)
    except FileNotFoundError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    # El reporte que va al supervisor lleva el seguimiento de envíos actualizado.
    from scripts.performer_correos import exportar_tracker

    lote = cola.ultimo_lote()
    exportar_tracker(cola, adjunto, lote, Bitacora(crear_id_ejecucion(), usar_sheets=False))
    resumen = cola.resumen(lote)
    ref = leer_referencia(adjunto)
    excepciones = contar_excepciones(adjunto)
    hoy = datetime.now().strftime("%d-%m-%Y %H:%M")
    asunto = f"[RPA TestFire] Resumen de ejecución {hoy}: {excepciones} excepciones"
    mensaje = (
        f"Hola,\n\nResumen de la ejecución del RPA TestFire ({hoy}):\n\n"
        f"- Lote: {lote or 's/d'}\n"
        f"- Excepciones de conciliación: {excepciones}\n"
        f"- Dólar usado: {ref.get('dolar', 's/d')} CLP ({ref.get('fecha', 's/d')}, {ref.get('origen', 's/d')})\n"
        f"- Correos a responsables: {resumen['ENVIADO']} enviados, {resumen['ERROR']} por reintentar, "
        f"{resumen['FALLIDO']} fallidos, {resumen['PENDIENTE']} pendientes\n\n"
        "Se adjunta el reporte final con las hojas Discrepancias, Referencia externa y "
        "Seguimiento de envíos.\n\n"
        "Correo generado automáticamente por el RPA TestFire (proyecto académico ATY1102)."
    )
    (salida / "mensaje_supervisor.txt").write_text(mensaje, encoding="utf-8")
    print(json.dumps({"ok": True, "para": para, "asunto": asunto, "mensaje": mensaje, "lote": lote,
                      "adjunto": str(adjunto)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
