"""
Subproceso 4b (Evaluación 3): PERFORMER. Procesa la cola caso por caso.

    py scripts/performer_correos.py --canal simulacion --exportar-excel <reporte_final_X.xlsx>

Por cada caso:
1. Lo toma de la cola (queda EN_PROCESO; nadie más lo toma).
2. Lo envía por el canal elegido.
3. Lo marca ENVIADO, o ERROR / FALLIDO con el motivo, y SIGUE con el
   próximo. Un correo que falla no detiene a los demás.
4. Los casos en ERROR se reintentan al final, hasta 3 intentos.

Reglas de envío responsable:
- ``--max-envios``: tope de correos por ejecución. Lo que sobra queda
  PENDIENTE para la próxima corrida. En un canal real el tope nunca supera
  ``TOPE_REAL`` (50), aunque se pida más.
- ``--pausa``: segundos entre correos (canal real: 10 por defecto, muy
  por debajo del límite de 30 por minuto de Microsoft 365).
- Direcciones @example.com nunca salen por un canal real.

Al terminar exporta el tracker a la hoja "Seguimiento de envíos" del
Excel indicado (si Excel lo tiene abierto, lo deja en un archivo aparte).

stdout: UNA línea JSON. Salida 0 si el performer corrió (aunque haya
casos con error: eso queda en el tracker), 2 si no pudo partir.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.bitacora import Bitacora, crear_id_ejecucion  # noqa: E402
from src.canales_correo import (  # noqa: E402
    CanalSimulacion, CanalSMTP, ErrorCanal, ErrorEnvio, ErrorEnvioPermanente,
)
from src.config_correo import cargar_config_correo, describir  # noqa: E402
from src.cola_correos import ENVIADO, FALLIDO, RUTA_COLA, ColaCorreos  # noqa: E402
from src.rutas import carpeta_salida, ultimo_archivo  # noqa: E402

TOPE_REAL = 50
HOJA_TRACKER = "Seguimiento de envíos"
COLORES_ESTADO = {
    "ENVIADO": "E3F6EE", "ERROR": "FFF4D6", "FALLIDO": "FDE8E8",
    "PENDIENTE": "F0EFEC", "EN_PROCESO": "E6F0FC",
}


def crear_canal(nombre: str, args) -> Any:
    if nombre == "simulacion":
        carpeta = args.carpeta_simulacion or (RAIZ / "data" / "salida" / "correos_simulados")
        return CanalSimulacion(carpeta, fallos_pasajeros=set(args.demo_fallo_pasajero or ()))
    if nombre == "smtp":
        return CanalSMTP(cargar_config_correo())
    raise ValueError(f"Canal desconocido: {nombre} (usa simulacion o smtp)")


def procesar(cola: ColaCorreos, canal, bitacora: Bitacora, max_envios: int, pausa: float) -> dict[str, Any]:
    conteo = {"procesados": 0, "enviados": 0, "errores": 0, "fallidos": 0, "detenido_por": None}
    liberados = cola.liberar_atascados()
    if liberados:
        bitacora.advertencia("Performer: %d casos atascados EN_PROCESO volvieron a PENDIENTE.", liberados)

    # Cada caso se intenta como máximo 2 veces por corrida (el reintento va
    # al final). Reintentar en el mismo segundo un "servidor ocupado" no
    # sirve: el intento que queda se hace en la próxima corrida.
    intentos_corrida: dict[int, int] = {}
    while max_envios == 0 or conteo["procesados"] < max_envios:
        excluir = [i for i, n in intentos_corrida.items() if n >= 2]
        caso = cola.tomar_siguiente(bitacora.id_ejecucion, excluir=excluir)
        if caso is None:
            break
        intentos_corrida[caso["id"]] = intentos_corrida.get(caso["id"], 0) + 1
        conteo["procesados"] += 1
        etiqueta = f"caso {caso['id']} -> {caso['destinatario']} (intento {caso['intentos']}/{caso['max_intentos']})"
        try:
            evidencia = canal.enviar(caso)
            cola.marcar_enviado(caso["id"])
            conteo["enviados"] += 1
            bitacora.info("Performer: %s ENVIADO %s", etiqueta, Path(evidencia).name if evidencia else "")
        except ErrorEnvioPermanente as error:
            cola.marcar_error(caso["id"], str(error), permanente=True)
            conteo["fallidos"] += 1
            bitacora.advertencia("Performer: %s FALLIDO (no se reintenta): %s. Sigue con el siguiente.", etiqueta, error)
        except ErrorEnvio as error:
            estado = cola.marcar_error(caso["id"], str(error))
            conteo["errores" if estado != FALLIDO else "fallidos"] += 1
            bitacora.advertencia("Performer: %s %s: %s. Sigue con el siguiente.", etiqueta, estado, error)
        except ErrorCanal as error:
            cola.marcar_error(caso["id"], f"Canal detenido: {error}")
            conteo["detenido_por"] = str(error)
            bitacora.error("Performer: el canal dejó de funcionar (%s). Se detiene; el resto queda en la cola.", error)
            break
        except Exception as error:  # cualquier sorpresa: se registra y se sigue
            estado = cola.marcar_error(caso["id"], f"{type(error).__name__}: {error}")
            conteo["errores" if estado != FALLIDO else "fallidos"] += 1
            bitacora.error("Performer: %s error inesperado (%s). Sigue con el siguiente.", etiqueta, error)

        if pausa:
            time.sleep(pausa)
    return conteo


def exportar_tracker(cola: ColaCorreos, excel: Path, lote: str | None, bitacora: Bitacora) -> str:
    filas = cola.listar(lote)
    resumen = cola.resumen(lote)

    def volcar(libro) -> None:
        if HOJA_TRACKER in libro.sheetnames:
            del libro[HOJA_TRACKER]
        hoja = libro.create_sheet(HOJA_TRACKER)
        hoja.append([f"Tracker de la cola de correos{' - lote ' + lote if lote else ''}",
                     f"Exportado {datetime.now():%Y-%m-%d %H:%M:%S}"])
        hoja.append([f"{k}: {v}" for k, v in resumen.items()])
        hoja.append([])
        columnas = ["id", "lote", "destinatario", "asunto", "casos", "prioridad", "estado", "intentos",
                    "ultimo_error", "creado_en", "tomado_en", "procesado_en", "ejecucion_performer", "pc_performer",
                    "respuesta", "respuesta_de", "respuesta_en"]
        hoja.append(columnas)
        for celda in hoja[4]:
            celda.font = Font(bold=True)
            celda.fill = PatternFill("solid", fgColor="E6F0FC")
        for fila in filas:
            fila = dict(fila, casos=", ".join(json.loads(fila["casos"]))[:200])
            hoja.append([fila.get(c) for c in columnas])
            color = COLORES_ESTADO.get(fila["estado"])
            if color:
                hoja.cell(row=hoja.max_row, column=columnas.index("estado") + 1).fill = PatternFill("solid", fgColor=color)
        hoja.freeze_panes = "A5"
        for letra, ancho in zip("ABCDEFGHIJKLMNOPQ", (6, 22, 30, 50, 30, 9, 12, 9, 50, 20, 20, 20, 32, 16, 12, 30, 20)):
            hoja.column_dimensions[letra].width = ancho

    try:
        libro = load_workbook(excel) if excel.exists() else Workbook()
        volcar(libro)
        if "Sheet" in libro.sheetnames and len(libro.sheetnames) > 1 and not excel.exists():
            del libro["Sheet"]
        libro.save(excel)
        return str(excel)
    except PermissionError:
        # Excel tiene el archivo abierto: no se pisa, se guarda al lado.
        alterno = excel.with_name(f"seguimiento_envios_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
        libro = Workbook()
        volcar(libro)
        del libro["Sheet"]
        libro.save(alterno)
        bitacora.advertencia("El Excel estaba abierto; el tracker se guardó en %s.", alterno.name)
        return str(alterno)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Performer: envía los correos de la cola.")
    parser.add_argument("--canal", default="simulacion", choices=["simulacion", "smtp"],
                        help="simulacion (guarda .eml) o smtp (envío real con el servidor de config.json)")
    parser.add_argument("--max-envios", type=int, default=None,
                        help="Tope por ejecución (0 = sin tope; solo en simulación). Real: 20 por defecto")
    parser.add_argument("--pausa", type=float, default=None, help="Segundos entre correos (real: 10)")
    parser.add_argument("--cola", type=Path, default=RUTA_COLA)
    parser.add_argument("--exportar-excel", type=Path, help="Excel donde dejar la hoja de seguimiento")
    parser.add_argument("--exportar-ultimo", action="store_true",
                        help="Exporta el tracker al reporte_final más reciente de la carpeta de salida")
    parser.add_argument("--lote", help="Lote a mostrar en el tracker exportado (por defecto, todos)")
    parser.add_argument("--carpeta-simulacion", type=Path, help="Dónde guardar los .eml simulados")
    parser.add_argument("--demo-fallo-pasajero", type=int, nargs="*",
                        help="IDs que fallan en su primer intento (demo de reintento)")
    parser.add_argument("--id-ejecucion", default=None)
    parser.add_argument("--sin-sheets", action="store_true")
    args = parser.parse_args(argv)

    bitacora = Bitacora(args.id_ejecucion or crear_id_ejecucion(), usar_sheets=not args.sin_sheets)
    inicio = time.perf_counter()
    try:
        canal = crear_canal(args.canal, args)
        cola = ColaCorreos(args.cola)
    except Exception as error:
        bitacora.evento("Performer", "Procesar cola de correos", "Fallido", str(error), inicio)
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    if canal.es_real:
        max_envios = min(args.max_envios or 20, TOPE_REAL)
        pausa = 10.0 if args.pausa is None else max(args.pausa, 2.0)
    else:
        max_envios = args.max_envios or 0
        pausa = args.pausa or 0.0

    bitacora.info("Performer: canal=%s, tope=%s, pausa=%ss", canal.nombre, max_envios or "sin tope", pausa)
    if canal.es_real:
        bitacora.info("Performer: servidor %s", describir(canal.config))
    try:
        conteo = procesar(cola, canal, bitacora, max_envios, pausa)
    finally:
        if hasattr(canal, "cerrar"):
            canal.cerrar()
    resumen = cola.resumen()
    estado = "Fallido" if conteo["detenido_por"] else (
        "Advertencia" if conteo["errores"] or conteo["fallidos"] else "Exitoso")
    bitacora.evento(
        "Performer", "Procesar cola de correos", estado,
        f"canal {canal.nombre}: {conteo['enviados']} enviados, {conteo['errores']} en error (se reintentan), "
        f"{conteo['fallidos']} fallidos; quedan {resumen['PENDIENTE'] + resumen['ERROR']} por procesar",
        inicio, registros=conteo["procesados"],
    )

    tracker = None
    if args.exportar_ultimo and not args.exportar_excel:
        try:
            args.exportar_excel = ultimo_archivo(carpeta_salida(), "reporte_final_2*.xlsx")
        except FileNotFoundError as error:
            bitacora.advertencia("No se exportó el tracker: %s", error)
    if args.exportar_excel:
        inicio_export = time.perf_counter()
        tracker = exportar_tracker(cola, args.exportar_excel, args.lote, bitacora)
        bitacora.evento("Tracker", "Exportar Seguimiento de envíos", "Exitoso", Path(tracker).name,
                        inicio_export, registros=resumen["TOTAL"])

    print(json.dumps({
        "ok": True, "id_ejecucion": bitacora.id_ejecucion, "canal": canal.nombre,
        **conteo, "cola": resumen, "tracker": tracker,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
