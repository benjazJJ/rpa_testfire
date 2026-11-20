"""
Subproceso 2 (Evaluación 3): consumo de una API pública como referencia externa.

API: mindicador.cl, indicadores económicos de Chile publicados por el
Banco Central. Pública, gratuita y sin autenticación.

    GET https://mindicador.cl/api/dolar
    {
      "version": "1.7.0", "autor": "mindicador.cl", "codigo": "dolar",
      "nombre": "Dólar observado", "unidad_medida": "Pesos",
      "serie": [{"fecha": "2026-11-17T03:00:00.000Z", "valor": 1001.17}, ...]
    }

Validaciones antes de usar el dato:
- Código HTTP 200 y cuerpo JSON.
- ``codigo == "dolar"`` y ``serie`` con al menos un valor.
- Valor numérico dentro de un rango razonable (300 a 3000 CLP por USD):
  un valor fuera de ese rango indica un error de la fuente, no un dato real.

Manejo de errores:
- Timeout o error 5xx: hasta 3 intentos con espera creciente (1 s, 2 s).
- Error 4xx o JSON inválido: no se reintenta (repetir no lo arregla).
- Si todo falla, se usa el último valor bueno guardado en caché
  (``data/cache/dolar_ultimo.json``) y se informa ``origen = "cache"``.
  Si el PC nunca ha tenido caché (primera ejecución en un PC nuevo), se usa
  el valor de respaldo versionado en el repo (``data/referencia/dolar_respaldo.json``)
  y se informa ``origen = "respaldo"``. Si tampoco existe, se lanza ``ErrorApiDolar``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

URL_DOLAR = "https://mindicador.cl/api/dolar"
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CACHE = RAIZ_PROYECTO / "data" / "cache" / "dolar_ultimo.json"
RUTA_RESPALDO = RAIZ_PROYECTO / "data" / "referencia" / "dolar_respaldo.json"
RANGO_VALIDO = (Decimal("300"), Decimal("3000"))
CABECERAS = {"User-Agent": "RPA-TestFire/1.0 (proyecto academico ATY1102)"}


class ErrorApiDolar(Exception):
    """La API falló y no hay un valor en caché para reemplazarla."""


def validar_respuesta(datos: Any) -> dict[str, Any]:
    """
    Revisa la estructura del JSON y devuelve el valor más reciente.

    Lanza ``ValueError`` con el motivo si algo no calza.
    """
    if not isinstance(datos, dict):
        raise ValueError("La respuesta no es un objeto JSON.")
    if datos.get("codigo") != "dolar":
        raise ValueError(f"Código de indicador inesperado: {datos.get('codigo')!r}.")
    serie = datos.get("serie")
    if not isinstance(serie, list) or not serie:
        raise ValueError("La serie del dólar viene vacía.")

    # La API ordena del más reciente al más antiguo, pero no se asume.
    candidatos = []
    for punto in serie:
        try:
            fecha = datetime.fromisoformat(str(punto["fecha"]).replace("Z", "+00:00"))
            valor = Decimal(str(punto["valor"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        candidatos.append((fecha, valor))
    if not candidatos:
        raise ValueError("Ningún punto de la serie tiene fecha y valor válidos.")

    fecha, valor = max(candidatos)
    if not RANGO_VALIDO[0] <= valor <= RANGO_VALIDO[1]:
        raise ValueError(f"Valor del dólar fuera de rango: {valor}.")

    return {
        "valor": valor,
        # "2026-11-17T03:00:00Z" es la medianoche del 17 en Chile: la fecha
        # UTC coincide con el día del valor.
        "fecha_valor": fecha.astimezone(timezone.utc).date().isoformat(),
        "nombre": datos.get("nombre", "Dólar observado"),
        "unidad": datos.get("unidad_medida", "Pesos"),
        "muestra_json": {
            "codigo": datos.get("codigo"),
            "nombre": datos.get("nombre"),
            "unidad_medida": datos.get("unidad_medida"),
            "serie": serie[:3],
        },
    }


def _guardar_cache(resultado: dict[str, Any], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(
            {**resultado, "valor": str(resultado["valor"])},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def _leer_cache(ruta: Path) -> dict[str, Any] | None:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datos["valor"] = Decimal(datos["valor"])
        return datos
    except (OSError, ValueError, KeyError, InvalidOperation):
        return None


def obtener_dolar(
    url: str = URL_DOLAR,
    intentos: int = 3,
    timeout: int = 20,
    ruta_cache: Path = RUTA_CACHE,
    ruta_respaldo: Path = RUTA_RESPALDO,
    bitacora=None,
) -> dict[str, Any]:
    """
    Devuelve el dólar observado más reciente.

    Resultado: ``valor`` (Decimal), ``fecha_valor``, ``consultado_en``,
    ``origen`` ("api" o "cache"), ``codigo_http``, ``intentos``, ``endpoint``,
    ``muestra_json`` (para la evidencia) y ``motivo_cache`` si se usó caché.
    """
    def log(msg, *args):
        if bitacora:
            bitacora.info(msg, *args)

    ultimo_error = "sin intentos"
    codigo_http = None
    for intento in range(1, intentos + 1):
        try:
            log("API dólar: GET %s (intento %d/%d)", url, intento, intentos)
            respuesta = requests.get(url, timeout=timeout, headers=CABECERAS)
            codigo_http = respuesta.status_code
            log("API dólar: HTTP %s en %.2fs", codigo_http, respuesta.elapsed.total_seconds())

            if respuesta.status_code >= 500:
                ultimo_error = f"HTTP {respuesta.status_code} del servidor"
            elif respuesta.status_code != 200:
                ultimo_error = f"HTTP {respuesta.status_code}"
                break  # 4xx: reintentar no sirve
            else:
                resultado = validar_respuesta(respuesta.json())
                resultado.update(
                    origen="api",
                    codigo_http=codigo_http,
                    intentos=intento,
                    endpoint=url,
                    consultado_en=datetime.now().isoformat(timespec="seconds"),
                )
                _guardar_cache(resultado, ruta_cache)
                log("API dólar: valor %s CLP (fecha %s) validado", resultado["valor"], resultado["fecha_valor"])
                return resultado
        except requests.Timeout:
            ultimo_error = f"timeout de {timeout}s"
        except requests.RequestException as error:
            ultimo_error = f"error de red: {type(error).__name__}"
        except ValueError as error:  # JSON inválido o estructura inesperada
            ultimo_error = f"respuesta inválida: {error}"
            break

        if intento < intentos:
            time.sleep(intento)  # 1 s, 2 s...

    if bitacora:
        bitacora.advertencia("API dólar falló (%s); se intenta usar la caché.", ultimo_error)
    cache = _leer_cache(ruta_cache)
    origen = "cache"
    if cache is None:
        cache = _leer_cache(ruta_respaldo)
        origen = "respaldo"
        if cache is None:
            raise ErrorApiDolar(f"La API del dólar falló ({ultimo_error}) y no hay caché.")
        if bitacora:
            bitacora.advertencia("Sin caché en este PC: se usa el valor de respaldo del repo (%s CLP, fecha %s).",
                                 cache["valor"], cache.get("fecha_valor"))
    cache.update(origen=origen, codigo_http=codigo_http, motivo_cache=ultimo_error)
    return cache
