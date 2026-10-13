"""
Demostración de los 5 métodos HTTP (GET, POST, PUT, PATCH, DELETE) exigidos
por la pauta de Evaluación 2 (IL 2.4), contra la API dummy ``reqres.in``.

Por qué reqres.in:
- No requiere autenticación ni API key propia.
- Soporta nativamente los 5 verbos sobre el mismo recurso (/api/users),
  a diferencia del webhook propio del RPA (src/logs.py), que solo recibe
  POST. Así se evita modificar infraestructura productiva solo para
  cumplir un requisito de la pauta.
- Devuelve JSON real y códigos de estado estándar (200, 201, 204, 404),
  lo que permite validar cada respuesta tal como pide la pauta.

Cada método devuelve un diccionario uniforme con:
    metodo, url, payload_enviado, codigo_estado, cuerpo_respuesta, valido

``valido`` es la validación de código HTTP esperado por operación
(ej.: POST -> 201, DELETE -> 204), no solo "la request no reventó".

Pensado para invocarse:
- Como script Python independiente (ver bloque __main__: corre los 5
  métodos en orden y deja un log JSON listo para pegar en el informe
  técnico o mostrar en vivo durante la presentación).
- Desde un paso "Script (Python)" de Rocketbot, importando la clase.
"""

from __future__ import annotations

from typing import Any

import requests
from requests import Response
from requests.exceptions import RequestException

BASE_URL = "https://reqres.in/api/users"


class DemoHttpReqres:
    """Ejecuta y valida los 5 métodos HTTP contra reqres.in."""

    def __init__(self, tiempo_espera: int = 15):
        if tiempo_espera <= 0:
            raise ValueError("El tiempo de espera HTTP debe ser mayor que cero.")
        self.tiempo_espera = tiempo_espera

    def _ejecutar(
        self,
        metodo: str,
        url: str,
        payload: dict[str, Any] | None,
        codigo_esperado: int,
    ) -> dict[str, Any]:
        """Ejecuta una solicitud y la empaqueta en el formato uniforme de log."""

        try:
            respuesta: Response = requests.request(
                metodo,
                url,
                json=payload,
                timeout=self.tiempo_espera,
            )
        except RequestException as error:
            return {
                "metodo": metodo,
                "url": url,
                "payload_enviado": payload,
                "codigo_estado": None,
                "cuerpo_respuesta": None,
                "valido": False,
                "detalle": f"Error de red: {type(error).__name__}",
            }

        try:
            cuerpo = respuesta.json() if respuesta.content else {}
        except ValueError:
            cuerpo = {"_raw": respuesta.text}

        resultado = {
            "metodo": metodo,
            "url": url,
            "payload_enviado": payload,
            "codigo_estado": respuesta.status_code,
            "cuerpo_respuesta": cuerpo,
            "valido": respuesta.status_code == codigo_esperado,
            "detalle": (
                f"Código esperado {codigo_esperado}, recibido {respuesta.status_code}."
            ),
        }

        print(
            f"[HTTP] {metodo} {url} -> {respuesta.status_code} "
            f"({'OK' if resultado['valido'] else 'INESPERADO'})"
        )
        return resultado

    def listar_usuarios(self, pagina: int = 2) -> dict[str, Any]:
        """GET /api/users?page=N — lista usuarios (código esperado 200)."""
        return self._ejecutar("GET", f"{BASE_URL}?page={pagina}", None, 200)

    def crear_usuario(self, nombre: str, puesto: str) -> dict[str, Any]:
        """POST /api/users — crea un usuario (código esperado 201)."""
        payload = {"name": nombre, "job": puesto}
        return self._ejecutar("POST", BASE_URL, payload, 201)

    def actualizar_usuario(self, id_usuario: int, nombre: str, puesto: str) -> dict[str, Any]:
        """PUT /api/users/{id} — reemplaza el recurso completo (código esperado 200)."""
        payload = {"name": nombre, "job": puesto}
        return self._ejecutar("PUT", f"{BASE_URL}/{id_usuario}", payload, 200)

    def actualizar_parcial_usuario(self, id_usuario: int, puesto: str) -> dict[str, Any]:
        """PATCH /api/users/{id} — actualiza un campo parcial (código esperado 200)."""
        payload = {"job": puesto}
        return self._ejecutar("PATCH", f"{BASE_URL}/{id_usuario}", payload, 200)

    def eliminar_usuario(self, id_usuario: int) -> dict[str, Any]:
        """DELETE /api/users/{id} — elimina el recurso (código esperado 204)."""
        return self._ejecutar("DELETE", f"{BASE_URL}/{id_usuario}", None, 204)

    def ejecutar_demo_completa(self) -> list[dict[str, Any]]:
        """
        Corre los 5 métodos en secuencia sobre el mismo usuario simulado.

        Returns:
            list[dict[str, Any]]:
                Un resultado por método, en el orden GET, POST, PUT,
                PATCH, DELETE — listo para volcar a JSON en el informe
                técnico o mostrar en la presentación en vivo.
        """

        resultados = [self.listar_usuarios()]

        creado = self.crear_usuario("Benjamin Palma", "RPA Developer")
        resultados.append(creado)

        # reqres.in no persiste datos reales: el ID se simula para poder
        # encadenar PUT/PATCH/DELETE sobre "el mismo" recurso creado.
        id_simulado = 2

        resultados.append(
            self.actualizar_usuario(id_simulado, "Benjamin Palma", "RPA Lead")
        )
        resultados.append(
            self.actualizar_parcial_usuario(id_simulado, "RPA Architect")
        )
        resultados.append(self.eliminar_usuario(id_simulado))

        return resultados


if __name__ == "__main__":
    import json

    demo = DemoHttpReqres()
    resultados = demo.ejecutar_demo_completa()

    print("\n=== RESUMEN ===")
    print(json.dumps(resultados, indent=2, ensure_ascii=False))

    total = len(resultados)
    validos = sum(1 for r in resultados if r["valido"])
    print(f"\n{validos}/{total} métodos HTTP devolvieron el código esperado.")