"""
Subprocesos 2 y 3 (Evaluación 3): API pública -> Excel como referencia externa.

Rocketbot lo llama con ``referencia_externa.bat`` después de conciliar:

    py scripts/referencia_externa_excel.py --excel <discrepancias_X.xlsx> --salida <carpeta>

Qué hace:
1. Consulta el dólar observado del día en mindicador.cl (con validaciones,
   reintentos y caché; ver ``src/api_dolar.py``).
2. Copia el reporte a ``reporte_final_<fecha>.xlsx`` (el original queda
   intacto para la evidencia "antes / después").
3. En cada hoja que tenga columna ``monto`` agrega la columna
   ``monto_clp`` = monto USD x dólar del día.
4. Agrega la hoja ``Referencia externa`` con la fuente, el endpoint, el
   valor usado, la fecha y una muestra del JSON recibido.
5. Guarda el JSON recibido en ``api_dolar_<fecha>.json`` (evidencia).

Contrato con Rocketbot: stdout tiene UNA línea JSON con el resultado
(``ok``, ``reporte_final``, ``dolar``, ``origen``...). Los mensajes de log
van a stderr y a ``logs/``. Código de salida 0 si se generó el reporte,
2 si no se pudo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.api_dolar import URL_DOLAR, ErrorApiDolar, obtener_dolar  # noqa: E402
from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402

COLUMNA_MONTO = "monto"
COLUMNA_CLP = "monto_clp"
HOJA_REFERENCIA = "Referencia externa"
RELLENO_ENCABEZADO = PatternFill("solid", fgColor="E6F0FC")


def a_decimal(valor: Any) -> Decimal | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        numero = Decimal(str(valor).replace("$", "").replace(",", "").strip())
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def agregar_columna_clp(hoja, dolar: Decimal) -> int:
    """Agrega ``monto_clp`` al final. Devuelve cuántas filas se convirtieron."""
    encabezados = [str(c.value or "").strip().lower() for c in hoja[1]]
    if COLUMNA_MONTO not in encabezados:
        return 0
    if COLUMNA_CLP in encabezados:  # el script ya pasó por este libro
        return 0

    col_monto = encabezados.index(COLUMNA_MONTO) + 1
    col_clp = hoja.max_column + 1
    celda = hoja.cell(row=1, column=col_clp, value=COLUMNA_CLP)
    celda.font = Font(bold=True)
    celda.fill = RELLENO_ENCABEZADO
    hoja.column_dimensions[celda.column_letter].width = 22

    convertidas = 0
    for fila in range(2, hoja.max_row + 1):
        monto = a_decimal(hoja.cell(row=fila, column=col_monto).value)
        if monto is None:
            continue
        clp = (monto * dolar).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        # Montos extremos del sitio demo (1e18) no caben en un número de Excel
        # sin perder precisión: esos se guardan como texto.
        hoja.cell(row=fila, column=col_clp, value=int(clp) if abs(clp) < 10**15 else str(clp))
        hoja.cell(row=fila, column=col_clp).number_format = '#,##0" CLP"'
        convertidas += 1
    return convertidas


def escribir_hoja_referencia(libro, dolar: dict[str, Any], filas_convertidas: int) -> None:
    if HOJA_REFERENCIA in libro.sheetnames:
        del libro[HOJA_REFERENCIA]
    hoja = libro.create_sheet(HOJA_REFERENCIA)
    filas = [
        ("Campo", "Valor"),
        ("Fuente", "mindicador.cl (datos del Banco Central de Chile)"),
        ("Endpoint", dolar.get("endpoint", URL_DOLAR)),
        ("Método / autenticación", "GET, API pública sin autenticación"),
        ("Indicador", dolar.get("nombre", "Dólar observado")),
        ("Valor usado (CLP por USD)", float(dolar["valor"])),
        ("Fecha del valor", dolar.get("fecha_valor", "")),
        ("Consultado en", dolar.get("consultado_en", "")),
        ("Origen del dato", "API en línea" if dolar["origen"] == "api" else f"Caché local ({dolar.get('motivo_cache', '')})"),
        ("Código HTTP", dolar.get("codigo_http") or "sin respuesta"),
        ("Filas convertidas a CLP", filas_convertidas),
        ("Fórmula", "monto_clp = monto (USD) x valor del dólar, redondeado a pesos"),
        ("Muestra del JSON recibido", json.dumps(dolar.get("muestra_json", {}), ensure_ascii=False)),
    ]
    for fila in filas:
        hoja.append(fila)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.fill = RELLENO_ENCABEZADO
    hoja.column_dimensions["A"].width = 30
    hoja.column_dimensions["B"].width = 90


def ejecutar(excel: Path, salida: Path, bitacora: Bitacora) -> dict[str, Any]:
    if not excel.exists():
        raise FileNotFoundError(f"No existe el Excel de entrada: {excel}")
    salida.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- Subproceso 2: API ---------------------------------------------------
    inicio = time.perf_counter()
    try:
        dolar = obtener_dolar(bitacora=bitacora)
    except ErrorApiDolar as error:
        bitacora.evento("API dólar", "Consultar mindicador.cl", "Fallido", str(error), inicio)
        raise
    estado_api = "Exitoso" if dolar["origen"] == "api" else "Advertencia"
    bitacora.evento(
        "API dólar", "Consultar mindicador.cl", estado_api,
        f"{dolar['valor']} CLP/USD ({dolar['fecha_valor']}), origen {dolar['origen']}",
        inicio, registros=1,
    )
    ruta_json = salida / f"api_dolar_{marca}.json"
    ruta_json.write_text(
        json.dumps({**dolar, "valor": str(dolar["valor"])}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- Subproceso 3: Excel -------------------------------------------------
    inicio = time.perf_counter()
    reporte_final = salida / f"reporte_final_{marca}.xlsx"
    shutil.copyfile(excel, reporte_final)
    libro = load_workbook(reporte_final)
    convertidas = {hoja.title: agregar_columna_clp(hoja, dolar["valor"]) for hoja in libro.worksheets}
    escribir_hoja_referencia(libro, dolar, sum(convertidas.values()))
    libro.save(reporte_final)
    bitacora.evento(
        "Excel", "Agregar referencia externa (monto_clp)", "Exitoso",
        f"{reporte_final.name}: " + ", ".join(f"{h}={n}" for h, n in convertidas.items() if n),
        inicio, registros=sum(convertidas.values()),
    )

    return {
        "ok": True,
        "id_ejecucion": bitacora.id_ejecucion,
        "reporte_final": str(reporte_final),
        "evidencia_json": str(ruta_json),
        "dolar": float(dolar["valor"]),
        "fecha_dolar": dolar["fecha_valor"],
        "origen": dolar["origen"],
        "filas_convertidas": convertidas,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agrega el dólar de mindicador.cl al reporte Excel.")
    parser.add_argument("--excel", type=Path, required=True, help="Reporte de discrepancias (xlsx)")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta donde dejar el reporte final")
    parser.add_argument("--id-ejecucion", default=None, help="ID de la corrida (para unir los logs)")
    parser.add_argument("--sin-sheets", action="store_true", help="No escribir en la Auditoría RPA")
    args = parser.parse_args(argv)

    bitacora = Bitacora(args.id_ejecucion or crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    try:
        resultado = ejecutar(args.excel, args.salida, bitacora)
    except Exception as error:
        bitacora.error("Referencia externa falló: %s", error)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
