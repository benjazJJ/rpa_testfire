"""
Bitácora de la Evaluación 3: registra cada paso en dos niveles a la vez.

1. Archivo ``.log`` local (``logs/rpa_AAAAMMDD.log``): SIEMPRE se escribe,
   aunque no haya internet. Es el respaldo y el detalle fino.
2. Auditoría RPA en Google Sheets: las mismas 12 columnas de la
   Evaluación 1-2 (ID de ejecución, PC, módulo, estado, duración...). Si
   Sheets no está configurado o falla, se avisa en el ``.log`` y el robot
   sigue: un problema de registro nunca detiene el proceso.

El tercer nivel, el detalle por caso del correo, vive en el tracker de la
cola (``src/cola_correos.py``), no aquí: escribir una fila de Sheets por
cada correo chocaría con el límite de escrituras por minuto de su API.

Los mensajes de consola van a stderr porque los scripts que llama
Rocketbot deben dejar en stdout una sola línea JSON.
"""

from __future__ import annotations

import contextlib
import logging
import platform
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
CARPETA_LOGS = RAIZ_PROYECTO / "logs"


def crear_id_ejecucion(prefijo: str = "RPA") -> str:
    """Mismo formato que la Auditoría RPA: RPA_20261118_150102_A1B2C3."""
    return f"{prefijo}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6].upper()}"


class Bitacora:
    def __init__(
        self,
        id_ejecucion: str,
        usar_sheets: bool = True,
        carpeta_logs: Path = CARPETA_LOGS,
    ):
        self.id_ejecucion = id_ejecucion
        self.pc = platform.node()
        self._sheets = None
        self._sheets_intentado = not usar_sheets
        self.sheets_activo = False

        carpeta_logs.mkdir(parents=True, exist_ok=True)
        self.ruta_log = carpeta_logs / f"rpa_{datetime.now():%Y%m%d}.log"

        # Un logger por ejecución, para no duplicar líneas si se crean varias.
        self._log = logging.getLogger(f"rpa.{id_ejecucion}")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False
        if not self._log.handlers:
            formato = logging.Formatter(
                "%(asctime)s | %(levelname)-7s | " + id_ejecucion + " | " + self.pc + " | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            archivo = logging.FileHandler(self.ruta_log, encoding="utf-8")
            archivo.setFormatter(formato)
            consola = logging.StreamHandler(sys.stderr)
            consola.setFormatter(formato)
            self._log.addHandler(archivo)
            self._log.addHandler(consola)

    # ------------------------------------------------------------------ Sheets

    def _auditoria(self):
        """Conecta con Google Sheets solo la primera vez que se necesita."""
        if self._sheets_intentado:
            return self._sheets
        self._sheets_intentado = True
        try:
            from src.google_sheets import GoogleSheetsAuditoria

            with contextlib.redirect_stdout(sys.stderr):
                self._sheets = GoogleSheetsAuditoria()
            self.sheets_activo = True
        except Exception as error:  # sin config, sin credenciales o sin red
            self._log.warning(
                "Auditoría en Google Sheets no disponible (%s); se registra solo en %s.",
                type(error).__name__,
                self.ruta_log.name,
            )
        return self._sheets

    # ------------------------------------------------------------------ API

    def info(self, mensaje: str, *args) -> None:
        self._log.info(mensaje, *args)

    def advertencia(self, mensaje: str, *args) -> None:
        self._log.warning(mensaje, *args)

    def error(self, mensaje: str, *args) -> None:
        self._log.error(mensaje, *args)

    def evento(
        self,
        modulo: str,
        accion: str,
        estado: str,
        detalle: str = "",
        tiempo_inicio: float | None = None,
        registros: int = 0,
        evidencia: str = "",
    ) -> None:
        """
        Registra un hito (inicio o fin de fase) en el .log y en la Auditoría RPA.

        ``estado`` sigue la convención de la auditoría: Exitoso, Fallido,
        Advertencia, Omitido o En proceso.
        """
        duracion = round(time.perf_counter() - tiempo_inicio, 2) if tiempo_inicio else 0
        nivel = logging.ERROR if estado == "Fallido" else (
            logging.WARNING if estado == "Advertencia" else logging.INFO
        )
        self._log.log(
            nivel,
            "[%s] %s -> %s | %s | registros=%s | %.2fs",
            modulo, accion, estado, detalle, registros, duracion,
        )

        auditoria = self._auditoria()
        if auditoria is None:
            return
        with contextlib.redirect_stdout(sys.stderr):
            ok = auditoria.registrar_evento(
                id_ejecucion=self.id_ejecucion,
                modulo=modulo,
                accion=accion,
                estado=estado,
                detalle=detalle[:500],
                tiempo_inicio=tiempo_inicio,
                registros=registros,
                evidencia_drive=evidencia,
            )
        if not ok:
            self._log.warning("No se pudo escribir '%s' en la Auditoría RPA; queda solo en el .log.", accion)
