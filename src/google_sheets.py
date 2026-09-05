import platform
import time
import uuid

from datetime import datetime
import json
from pathlib import Path

import gspread

from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CABECERAS = [
    "Fecha/Hora",
    "ID Ejecución",
    "PC",
    "SO",
    "Módulo",
    "Acción/Paso",
    "Estado",
    "Detalle",
    "Duración (seg)",
    "Hora Término",
    "Registros",
    "Evidencia Drive",
]


class GoogleSheetsAuditoria:

    def __init__(self):
        self.raiz_proyecto = Path(__file__).resolve().parent.parent
        self.configuracion = self._cargar_configuracion()
        self.hoja = self._conectar()
        self._inicializar_encabezados()

    def _cargar_configuracion(self):
        ruta_config = self.raiz_proyecto / "config" / "config.json"

        if not ruta_config.exists():
            raise FileNotFoundError(f"No se encontró config.json en: {ruta_config}")

        with open(ruta_config, "r", encoding="utf-8") as archivo:
            return json.load(archivo)

    def _conectar(self):
        configuracion_google = self.configuracion["google"]

        ruta_credenciales = (
            self.raiz_proyecto / configuracion_google["credenciales_path"]
        )

        if not ruta_credenciales.exists():
            raise FileNotFoundError(
                f"No se encontraron las credenciales en: {ruta_credenciales}"
            )

        credenciales = Credentials.from_service_account_file(
            str(ruta_credenciales),
            scopes=SCOPES,
        )

        cliente = gspread.authorize(credenciales)

        documento = cliente.open_by_key(configuracion_google["spreadsheet_id"])

        return documento.worksheet(configuracion_google["worksheet_name"])

    def _inicializar_encabezados(self):
        encabezados_actuales = self.hoja.row_values(1)

        if not encabezados_actuales:
            self.hoja.update(
                values=[CABECERAS],
                range_name="A1:L1",
            )
            print("[SHEETS] Encabezados creados correctamente.")

        elif encabezados_actuales != CABECERAS:
            print(
                "[ERROR SHEETS] Los encabezados existentes no coinciden con los requeridos."
            )
            print(f"[ACTUALES] {encabezados_actuales}")
            print(f"[ESPERADOS] {CABECERAS}")

            raise ValueError(
                "Los encabezados existentes no coinciden con los "
                "encabezados requeridos por el RPA."
            )

    def probar_conexion(self):
        print("[OK] Conexión con Google Sheets exitosa.")
        print(f"[OK] Pestaña encontrada: {self.hoja.title}")

    @staticmethod
    def crear_id_ejecucion():
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        codigo = uuid.uuid4().hex[:6].upper()

        return f"RPA_{fecha}_{codigo}"

    def registrar_evento(
        self,
        id_ejecucion,
        modulo,
        accion,
        estado,
        detalle="",
        tiempo_inicio=None,
        registros=0,
        evidencia_drive="",
    ):
        try:
            ahora = datetime.now()

            if tiempo_inicio is None:
                duracion = 0
            else:
                duracion = round(
                    time.perf_counter() - tiempo_inicio,
                    2,
                )

            fila = [
                ahora.strftime("%Y-%m-%d %H:%M:%S"),
                id_ejecucion,
                platform.node(),
                platform.system(),
                modulo,
                accion,
                estado,
                detalle,
                duracion,
                ahora.strftime("%H:%M:%S"),
                registros,
                evidencia_drive,
            ]

            self.hoja.append_row(
                fila,
                value_input_option="USER_ENTERED",
            )

            print(f"[AUDITORÍA] {accion} -> {estado}")
            return True

        except Exception as error:
            print(f"[ERROR SHEETS] No se pudo registrar el evento: {error}")
            return False
