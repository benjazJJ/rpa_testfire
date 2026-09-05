import json
import mimetypes
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

TIPO_CARPETA_DRIVE = "application/vnd.google-apps.folder"


class GoogleDriveEvidencias:

    def __init__(self):
        self.raiz_proyecto = Path(__file__).resolve().parent.parent
        self.configuracion = self._cargar_configuracion()
        self.carpeta_id = self.configuracion["google"]["drive_folder_id"]
        self.servicio = self._conectar()

    def _cargar_configuracion(self):
        ruta_config = self.raiz_proyecto / "config" / "config.json"

        if not ruta_config.exists():
            raise FileNotFoundError(f"No se encontró config.json en: {ruta_config}")

        with open(ruta_config, "r", encoding="utf-8") as archivo:
            return json.load(archivo)

    def _obtener_credenciales(self):
        configuracion_google = self.configuracion["google"]

        ruta_oauth = self.raiz_proyecto / configuracion_google["oauth_drive_path"]

        ruta_token = self.raiz_proyecto / configuracion_google["token_drive_path"]

        if not ruta_oauth.exists():
            raise FileNotFoundError(f"No se encontró oauth_drive.json en: {ruta_oauth}")

        credenciales = None

        if ruta_token.exists():
            credenciales = Credentials.from_authorized_user_file(
                str(ruta_token),
                SCOPES,
            )

        if not credenciales or not credenciales.valid:

            if credenciales and credenciales.expired and credenciales.refresh_token:
                credenciales.refresh(Request())

            else:
                flujo = InstalledAppFlow.from_client_secrets_file(
                    str(ruta_oauth),
                    SCOPES,
                )

                credenciales = flujo.run_local_server(
                    port=0,
                    prompt="consent",
                )

            ruta_token.write_text(
                credenciales.to_json(),
                encoding="utf-8",
            )

        return credenciales

    def _conectar(self):
        credenciales = self._obtener_credenciales()

        return build(
            "drive",
            "v3",
            credentials=credenciales,
            cache_discovery=False,
        )

    def probar_conexion(self):
        carpeta = (
            self.servicio.files()
            .get(
                fileId=self.carpeta_id,
                fields="id,name,mimeType",
                supportsAllDrives=True,
            )
            .execute()
        )

        if carpeta["mimeType"] != TIPO_CARPETA_DRIVE:
            raise ValueError("El ID configurado no corresponde a una carpeta.")

        print("[OK] Conexión con Google Drive exitosa.")
        print(f"[OK] Carpeta encontrada: {carpeta['name']}")

    def subir_archivo(self, ruta_archivo, nombre_drive=None):
        ruta_archivo = Path(ruta_archivo)

        if not ruta_archivo.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {ruta_archivo}")

        if nombre_drive is None:
            nombre_drive = ruta_archivo.name

        tipo_mime, _ = mimetypes.guess_type(str(ruta_archivo))

        metadatos = {
            "name": nombre_drive,
            "parents": [self.carpeta_id],
        }

        contenido = MediaFileUpload(
            str(ruta_archivo),
            mimetype=tipo_mime or "application/octet-stream",
            resumable=False,
        )

        archivo = (
            self.servicio.files()
            .create(
                body=metadatos,
                media_body=contenido,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        print(f"[DRIVE] Archivo subido: {archivo['name']}")

        return archivo.get("webViewLink", "")
