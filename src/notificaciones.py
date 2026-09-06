"""
Envío de reportes del RPA Demo TestFire mediante Gmail API.

Este módulo utiliza OAuth 2.0 para autorizar el envío de correos sin
guardar la contraseña de Gmail. El permiso solicitado es ``gmail.send``,
por lo que el RPA puede enviar mensajes, pero no leer la bandeja de entrada.

El token de Gmail se guarda separado del token de Google Drive para que
los permisos de una integración no interfieran con la otra.
"""

import base64
import json
import mimetypes
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Permiso mínimo requerido para enviar correos mediante Gmail API.
# Este alcance no permite leer ni eliminar mensajes del usuario.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class NotificadorGmail:
    """
    Administra la autenticación OAuth y el envío de reportes por Gmail.

    La clase recibe las rutas desde ``config/config.json``, construye un
    mensaje MIME, adjunta el Excel generado y lo envía mediante Gmail API.
    """

    def __init__(self, ruta_config: str | Path | None = None):
        """
        Inicializa el servicio de Gmail.

        Args:
            ruta_config:
                Ruta opcional hacia ``config.json``. Cuando no se entrega,
                se utiliza ``config/config.json`` desde la raíz del proyecto.
        """

        raiz_proyecto = Path(__file__).resolve().parent.parent

        if ruta_config is None:
            self.ruta_config = raiz_proyecto / "config" / "config.json"
        else:
            self.ruta_config = Path(ruta_config).resolve()

        self.raiz_proyecto = raiz_proyecto
        self.configuracion = self._cargar_configuracion()

        configuracion_google = self.configuracion.get("google", {})

        # Se reutiliza el mismo cliente OAuth de escritorio utilizado
        # por Drive. Gmail tendrá un token independiente.
        ruta_oauth = configuracion_google.get(
            "oauth_gmail_path",
            configuracion_google.get("oauth_drive_path", ""),
        )
        ruta_token = configuracion_google.get(
            "token_gmail_path",
            "config/token_gmail.json",
        )

        # Gmail exige que el mensaje MIME identifique al remitente.
        # Esta dirección debe pertenecer a la cuenta que autorizó OAuth.
        self.correo_remitente = self._validar_correo(
            configuracion_google.get("correo_remitente", "")
        )

        # Los destinatarios se mantienen en config.json para que puedan
        # cambiarse sin modificar el código fuente del robot.
        self.destinatarios_configurados = self._validar_destinatarios(
            configuracion_google.get("correos_destinatarios", [])
        )

        self.ruta_oauth = self._resolver_ruta(ruta_oauth)
        self.ruta_token = self._resolver_ruta(ruta_token)
        self._validar_archivos_configuracion()

        # La construcción del servicio puede abrir el navegador durante
        # la primera ejecución para solicitar la autorización del usuario.
        self.servicio = self._conectar()

    def _cargar_configuracion(self) -> dict:
        """
        Lee y valida el archivo JSON general del proyecto.

        Returns:
            dict: Configuración completa del RPA.

        Raises:
            FileNotFoundError: Si ``config.json`` no existe.
            ValueError: Si el archivo no contiene un JSON válido.
        """

        if not self.ruta_config.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo: {self.ruta_config}"
            )

        try:
            with self.ruta_config.open("r", encoding="utf-8") as archivo:
                return json.load(archivo)
        except json.JSONDecodeError as error:
            raise ValueError(
                "config/config.json no contiene un JSON válido."
            ) from error

    def _resolver_ruta(self, ruta: str) -> Path:
        """
        Convierte una ruta de configuración en una ruta absoluta.

        Las rutas relativas se interpretan desde la raíz del proyecto,
        independientemente de la carpeta desde la cual se ejecute Python.
        """

        ruta_objeto = Path(str(ruta).strip())

        if ruta_objeto.is_absolute():
            return ruta_objeto

        return self.raiz_proyecto / ruta_objeto

    def _validar_archivos_configuracion(self) -> None:
        """Comprueba que exista el archivo del cliente OAuth."""

        if not str(self.ruta_oauth).strip() or not self.ruta_oauth.exists():
            raise FileNotFoundError(
                "No se encontró el archivo OAuth para Gmail: "
                f"{self.ruta_oauth}"
            )

        # Creamos la carpeta del token si todavía no existe.
        self.ruta_token.parent.mkdir(parents=True, exist_ok=True)

    def _obtener_credenciales(self) -> Credentials:
        """
        Obtiene credenciales OAuth válidas para Gmail API.

        El orden utilizado es:

        1. Cargar ``token_gmail.json`` si ya existe.
        2. Renovar el token si expiró y posee ``refresh_token``.
        3. Abrir el navegador para autorizar Gmail si no existe un token.
        4. Guardar el token actualizado para futuras ejecuciones.
        """

        credenciales = None

        if self.ruta_token.exists():
            try:
                credenciales = Credentials.from_authorized_user_file(
                    str(self.ruta_token),
                    SCOPES,
                )
            except (ValueError, json.JSONDecodeError):
                # Si el token está vacío o dañado, se inicia una nueva
                # autorización en vez de detener todo el RPA.
                credenciales = None

        if credenciales and credenciales.expired:
            if credenciales.refresh_token:
                credenciales.refresh(Request())
            else:
                credenciales = None

        if not credenciales or not credenciales.valid:
            flujo = InstalledAppFlow.from_client_secrets_file(
                str(self.ruta_oauth),
                SCOPES,
            )

            # port=0 selecciona automáticamente un puerto local disponible.
            credenciales = flujo.run_local_server(port=0)

        # Guardamos solamente el token OAuth. Nunca se almacena la
        # contraseña de la cuenta de Gmail.
        self.ruta_token.write_text(
            credenciales.to_json(),
            encoding="utf-8",
        )

        return credenciales

    def _conectar(self):
        """Construye y devuelve el cliente oficial de Gmail API."""

        credenciales = self._obtener_credenciales()

        return build(
            "gmail",
            "v1",
            credentials=credenciales,
            cache_discovery=False,
        )

    @staticmethod
    def _validar_correo(correo: str) -> str:
        """
        Realiza una validación básica de la dirección destinataria.

        Esta comprobación detecta campos vacíos o direcciones claramente
        incompletas antes de llamar a Gmail API.
        """

        correo_limpio = str(correo).strip()

        if (
            not correo_limpio
            or "@" not in correo_limpio
            or correo_limpio.startswith("@")
            or correo_limpio.endswith("@")
        ):
            raise ValueError(
                "La dirección de correo destinataria no es válida."
            )

        return correo_limpio

    @classmethod
    def _validar_destinatarios(
        cls,
        destinatarios: str | list[str] | tuple[str, ...],
    ) -> list[str]:
        """
        Valida uno o varios destinatarios y elimina duplicados.

        Args:
            destinatarios:
                Una dirección individual o una lista/tupla de direcciones.

        Returns:
            list[str]: Direcciones válidas, limpias y sin duplicados.
        """

        if isinstance(destinatarios, str):
            lista_original = [destinatarios]
        elif isinstance(destinatarios, (list, tuple)):
            lista_original = list(destinatarios)
        else:
            raise TypeError(
                "Los destinatarios deben ser un correo o una lista "
                "de correos."
            )

        if not lista_original:
            raise ValueError(
                "Debe indicarse al menos un correo destinatario."
            )

        correos_validados = []

        for correo in lista_original:
            correo_limpio = cls._validar_correo(correo)

            if correo_limpio not in correos_validados:
                correos_validados.append(correo_limpio)

        return correos_validados

    @staticmethod
    def _adjuntar_archivo(
        mensaje: EmailMessage,
        ruta_archivo: Path,
    ) -> None:
        """Lee un archivo local y lo agrega al mensaje como adjunto."""

        tipo_mime, _ = mimetypes.guess_type(ruta_archivo.name)

        if tipo_mime:
            tipo_principal, subtipo = tipo_mime.split("/", 1)
        else:
            tipo_principal = "application"
            subtipo = "octet-stream"

        mensaje.add_attachment(
            ruta_archivo.read_bytes(),
            maintype=tipo_principal,
            subtype=subtipo,
            filename=ruta_archivo.name,
        )

    def enviar_reporte(
        self,
        destinatario: str | list[str] | tuple[str, ...],
        ruta_reporte: str | Path,
        id_ejecucion: str,
        estado_conciliacion: str,
        cantidad_movimientos: int,
        enlace_drive: str = "",
    ) -> tuple[bool, str]:
        """
        Envía el reporte Excel y un resumen de la ejecución.

        Args:
            destinatario:
                Dirección individual o lista de direcciones que recibirán
                el mismo mensaje y el reporte adjunto.

            ruta_reporte:
                Ruta local del archivo Excel generado por el RPA.

            id_ejecucion:
                Identificador de trazabilidad compartido por la ejecución.

            estado_conciliacion:
                Resultado funcional de la conciliación.

            cantidad_movimientos:
                Número de movimientos extraídos desde TestFire.

            enlace_drive:
                Enlace opcional al reporte almacenado en Google Drive.

        Returns:
            tuple[bool, str]:
                ``True`` y un detalle si Gmail aceptó el mensaje; de lo
                contrario, ``False`` y una descripción apta para auditoría.
        """

        correos_destino = self._validar_destinatarios(destinatario)
        archivo_reporte = Path(ruta_reporte).resolve()

        if not archivo_reporte.is_file():
            raise FileNotFoundError(
                f"No se encontró el reporte para adjuntar: "
                f"{archivo_reporte}"
            )

        mensaje = EmailMessage()
        mensaje["From"] = self.correo_remitente
        # EmailMessage utiliza una cadena separada por comas para representar
        # correctamente varios destinatarios en el encabezado "Para".
        mensaje["To"] = ", ".join(correos_destino)
        mensaje["Subject"] = (
            f"Reporte RPA Demo TestFire - {id_ejecucion}"
        )

        cuerpo = [
            "Hola:",
            "",
            "El RPA Demo TestFire finalizó el procesamiento.",
            "",
            f"ID de ejecución: {id_ejecucion}",
            f"Movimientos extraídos: {cantidad_movimientos}",
            f"Resultado de conciliación: {estado_conciliacion}",
        ]

        if enlace_drive:
            cuerpo.extend(
                [
                    f"Reporte en Google Drive: {enlace_drive}",
                ]
            )

        cuerpo.extend(
            [
                "",
                "El reporte Excel también se encuentra adjunto.",
                "",
                "Mensaje enviado automáticamente por el RPA.",
            ]
        )

        mensaje.set_content("\n".join(cuerpo))
        self._adjuntar_archivo(mensaje, archivo_reporte)

        # Gmail API exige enviar el mensaje MIME codificado con base64url.
        mensaje_codificado = base64.urlsafe_b64encode(
            mensaje.as_bytes()
        ).decode("utf-8")

        try:
            respuesta = (
                self.servicio.users()
                .messages()
                .send(
                    userId="me",
                    body={"raw": mensaje_codificado},
                )
                .execute()
            )
        except HttpError as error:
            codigo = getattr(error.resp, "status", "desconocido")

            # _get_reason() entrega la explicación enviada por Gmail sin
            # revelar el token OAuth ni las credenciales del proyecto.
            motivo = error._get_reason() or "Motivo no informado por Gmail."
            detalle = (
                "No fue posible enviar el correo mediante Gmail API. "
                f"Código HTTP: {codigo}. "
                f"Motivo: {motivo[:300]}"
            )
            print(f"[GMAIL] {detalle}")
            return False, detalle

        id_mensaje = respuesta.get("id", "sin identificador")
        detalle = (
            "Reporte enviado correctamente mediante Gmail API. "
            f"ID del mensaje: {id_mensaje}."
        )

        print(f"[GMAIL] {detalle}")
        return True, detalle
