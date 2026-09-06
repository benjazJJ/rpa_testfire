"""
Registro HTTP de ejecuciones del RPA Demo TestFire.

Este módulo envía mediante HTTP POST un resumen en formato JSON hacia
un webhook. La URL se obtiene desde ``config/config.json`` para evitar
escribir configuraciones privadas directamente en el código Python.

El payload contiene solamente información operativa. Nunca incluye el
usuario bancario, la contraseña ni las credenciales de Google.
"""

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests import Response
from requests.exceptions import RequestException


class RegistroHttpWebhook:
    """
    Envía eventos de trazabilidad hacia un webhook mediante HTTP POST.

    La clase centraliza la lectura de configuración, la construcción del
    JSON y el control de errores HTTP para mantener ``main.py`` ordenado.
    """

    def __init__(
        self,
        ruta_config: str | Path | None = None,
        tiempo_espera: int = 15,
    ):
        """
        Inicializa el cliente HTTP y carga la URL configurada.

        Args:
            ruta_config:
                Ruta opcional de ``config.json``. Si no se entrega, se
                utiliza ``config/config.json`` desde la raíz del proyecto.

            tiempo_espera:
                Segundos máximos permitidos para completar cada solicitud.
        """

        raiz_proyecto = Path(__file__).resolve().parent.parent

        if ruta_config is None:
            self.ruta_config = raiz_proyecto / "config" / "config.json"
        else:
            self.ruta_config = Path(ruta_config).resolve()

        if tiempo_espera <= 0:
            raise ValueError(
                "El tiempo de espera HTTP debe ser mayor que cero."
            )

        self.tiempo_espera = tiempo_espera
        self.webhook_url = self._cargar_webhook_url()

    def _cargar_webhook_url(self) -> str:
        """
        Lee y valida ``webhook_url`` desde el archivo de configuración.

        Returns:
            str:
                URL HTTP o HTTPS lista para recibir eventos.

        Raises:
            FileNotFoundError:
                Cuando no existe ``config/config.json``.

            ValueError:
                Cuando el JSON es inválido, falta la propiedad o la URL no
                utiliza el protocolo HTTP/HTTPS.
        """

        if not self.ruta_config.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo de configuración: "
                f"{self.ruta_config}"
            )

        try:
            with self.ruta_config.open(
                "r",
                encoding="utf-8",
            ) as archivo:
                configuracion = json.load(archivo)
        except json.JSONDecodeError as error:
            raise ValueError(
                "config/config.json no contiene un JSON válido."
            ) from error

        webhook_url = str(
            configuracion.get("webhook_url", "")
        ).strip()

        if not webhook_url:
            raise ValueError(
                "Falta configurar 'webhook_url' en config/config.json."
            )

        url_analizada = urlparse(webhook_url)

        if (
            url_analizada.scheme not in {"http", "https"}
            or not url_analizada.netloc
        ):
            raise ValueError(
                "La propiedad 'webhook_url' no contiene una URL "
                "HTTP/HTTPS válida."
            )

        return webhook_url

    @staticmethod
    def _validar_diccionario(
        nombre: str,
        valor: dict[str, Any],
    ) -> None:
        """
        Comprueba que estados y métricas sean diccionarios serializables.

        Esta validación permite detectar el problema antes de intentar
        comunicarse con el servicio externo.
        """

        if not isinstance(valor, dict):
            raise TypeError(
                f"'{nombre}' debe ser un diccionario."
            )

        try:
            json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"'{nombre}' contiene valores no serializables a JSON."
            ) from error

    def _enviar_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Ejecuta el HTTP POST y controla errores de red o de servidor.

        Returns:
            tuple[bool, str]:
                Resultado del envío y una descripción apta para auditoría.

        Notes:
            Por seguridad, los detalles de error no incluyen la URL completa
            del webhook, ya que contiene un identificador privado.
        """

        try:
            respuesta: Response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.tiempo_espera,
            )

            respuesta.raise_for_status()

        except RequestException as error:
            detalle = (
                "No fue posible completar el HTTP POST. "
                f"Tipo de error: {type(error).__name__}."
            )

            print(f"[HTTP] {detalle}")
            return False, detalle

        detalle = (
            "Resumen enviado mediante HTTP POST. "
            f"Código recibido: {respuesta.status_code}."
        )

        print(f"[HTTP] {detalle}")
        return True, detalle

    def probar_conexion(self) -> tuple[bool, str]:
        """
        Envía un evento pequeño para verificar la configuración.

        El evento de prueba no contiene movimientos, credenciales ni enlaces.
        """

        payload = {
            "tipo_evento": "prueba_conexion",
            "fecha_hora": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "origen": "RPA Demo TestFire",
            "pc": platform.node(),
            "sistema_operativo": platform.system(),
        }

        return self._enviar_payload(payload)

    def enviar_resumen(
        self,
        id_ejecucion: str,
        estados: dict[str, Any],
        metricas: dict[str, Any],
        enlace_reporte: str = "",
    ) -> tuple[bool, str]:
        """
        Envía el resumen final de una ejecución del robot.

        Args:
            id_ejecucion:
                Identificador utilizado por Google Sheets, Drive y evidencias.

            estados:
                Resultados de login, extracción, conciliación y reporte.

            metricas:
                Cantidades de movimientos y resultados de conciliación.

            enlace_reporte:
                Enlace de Google Drive correspondiente al Excel generado.

        Returns:
            tuple[bool, str]:
                Resultado del POST y detalle para la auditoría.

        Raises:
            ValueError:
                Cuando falta el ID de ejecución.

            TypeError:
                Cuando estados o métricas no son diccionarios.
        """

        if not str(id_ejecucion).strip():
            raise ValueError(
                "El ID de ejecución no puede estar vacío."
            )

        self._validar_diccionario("estados", estados)
        self._validar_diccionario("metricas", metricas)

        payload = {
            "tipo_evento": "resumen_ejecucion",
            "fecha_hora": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "origen": "RPA Demo TestFire",
            "id_ejecucion": id_ejecucion,
            "pc": platform.node(),
            "sistema_operativo": platform.system(),
            "estados": estados,
            "metricas": metricas,
            "reporte_drive": enlace_reporte,
        }

        return self._enviar_payload(payload)
