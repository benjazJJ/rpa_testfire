"""
Datos sintéticos para la gestión de excepciones de la conciliación
(Evaluación 2 / IL 2.5: solución creativa e ideación documentada).

Problema: TestFire solo entrega IDs numéricos de cuenta y transacción. Un
reporte de conciliación con N excepciones no dice a quién le toca
revisarlas ni con qué urgencia, y no se pueden usar datos de personas
reales en un sitio demo.

Solución: se consume la API pública RandomUser (https://randomuser.me) para
obtener un equipo ficticio de analistas y se asigna a cada excepción:

- ``prioridad_revision``: Alta / Media / Baja según el estado y el monto.
- ``analista_asignado`` y ``correo_analista``: perfil sintético (dominio
  example.com, nunca un correo real).

Estructuras de control explícitas (requisito de la pauta):

- ``while``: reintentos con espera creciente contra RandomUser.
- ``for``: armado de perfiles y recorrido de los resultados.
- ``if / elif / else``: validación de la respuesta HTTP, respaldo local y
  reglas de prioridad.

Si RandomUser no responde, se usa un respaldo local determinístico: el
robot nunca se detiene por un servicio de datos de prueba.

Ver la ideación completa en docs/ideacion_IL2.5.md.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from requests.exceptions import RequestException

URL_RANDOMUSER = "https://randomuser.me/api/1.4/"

# Nacionalidades hispanohablantes disponibles en RandomUser (ES y MX), para
# que los nombres sean coherentes con el resto del reporte.
NACIONALIDADES = "es,mx"

# Monto desde el cual una diferencia se considera de prioridad Alta.
UMBRAL_MONTO_ALTO = Decimal("1000")

# Respaldo local si RandomUser no responde. Mismos campos que la API.
NOMBRES_RESPALDO = [
    ("Camila", "Rojas"),
    ("Matías", "González"),
    ("Valentina", "Muñoz"),
    ("Benjamín", "Soto"),
    ("Isidora", "Contreras"),
]


class GeneradorDatosSinteticos:
    """Obtiene analistas ficticios y los asigna a las excepciones."""

    def __init__(
        self,
        cantidad_analistas: int = 5,
        semilla: str = "rpa-testfire",
        max_intentos: int = 3,
        tiempo_espera: int = 10,
    ):
        if cantidad_analistas <= 0:
            raise ValueError("La cantidad de analistas debe ser mayor que cero.")
        if max_intentos <= 0:
            raise ValueError("Debe existir al menos un intento contra RandomUser.")

        self.cantidad_analistas = cantidad_analistas
        # La semilla hace que RandomUser devuelva siempre el mismo equipo:
        # el reporte es reproducible entre corridas y en la presentación.
        self.semilla = semilla
        self.max_intentos = max_intentos
        self.tiempo_espera = tiempo_espera
        self.origen = "sin consultar"

    def _consultar_randomuser(self) -> list[dict[str, Any]] | None:
        """Consulta RandomUser con reintentos. Devuelve None si no hay datos."""

        parametros = {
            "results": self.cantidad_analistas,
            "nat": NACIONALIDADES,
            "seed": self.semilla,
            # Solo los campos necesarios: no se piden contraseñas ni fotos.
            "inc": "name,email,nat",
            "noinfo": "",
        }

        intento = 1
        espera = 1

        while intento <= self.max_intentos:
            try:
                respuesta = requests.get(
                    URL_RANDOMUSER,
                    params=parametros,
                    timeout=self.tiempo_espera,
                )

                if respuesta.status_code == 200:
                    resultados = respuesta.json().get("results", [])
                    if resultados:
                        return resultados
                    print("[SINTÉTICOS] RandomUser respondió sin resultados.")
                else:
                    print(
                        f"[SINTÉTICOS] Intento {intento}: código HTTP "
                        f"{respuesta.status_code}."
                    )

            except (RequestException, ValueError) as error:
                print(f"[SINTÉTICOS] Intento {intento} fallido: {error}")

            intento += 1
            if intento <= self.max_intentos:
                time.sleep(espera)
                espera *= 2

        return None

    def obtener_analistas(self) -> list[dict[str, str]]:
        """Devuelve el equipo ficticio de analistas (API o respaldo local)."""

        resultados = self._consultar_randomuser()
        analistas: list[dict[str, str]] = []

        if resultados:
            self.origen = "RandomUser API"
            for persona in resultados:
                analistas.append(
                    {
                        "nombre": (
                            f"{persona['name']['first']} {persona['name']['last']}"
                        ),
                        "correo": persona["email"],
                        "nacionalidad": persona.get("nat", ""),
                    }
                )
        else:
            self.origen = "Respaldo local"
            print("[SINTÉTICOS] Se usa el equipo de respaldo local.")
            for indice in range(self.cantidad_analistas):
                nombre, apellido = NOMBRES_RESPALDO[indice % len(NOMBRES_RESPALDO)]
                analistas.append(
                    {
                        "nombre": f"{nombre} {apellido}",
                        "correo": f"{nombre.lower()}.{apellido.lower()}@example.com",
                        "nacionalidad": "CL",
                    }
                )

        return analistas

    @staticmethod
    def calcular_prioridad(resultado: dict[str, Any]) -> str:
        """
        Reglas de prioridad de revisión:

        - Conciliado                  -> "" (no requiere revisión)
        - Con diferencias en el monto -> Alta
        - Con diferencias, monto alto -> Alta
        - Con diferencias (otros)     -> Media
        - Solo en TestFire / maestro  -> Media si el monto es alto, si no Baja
        """

        estado = resultado.get("estado_conciliacion", "")

        try:
            monto = abs(Decimal(str(resultado.get("monto", 0))))
        except InvalidOperation:
            monto = Decimal("0")

        if estado == "Conciliado":
            return ""
        elif estado == "Con diferencias":
            if "monto" in resultado.get("detalle_conciliacion", "").lower():
                return "Alta"
            elif monto >= UMBRAL_MONTO_ALTO:
                return "Alta"
            else:
                return "Media"
        elif monto >= UMBRAL_MONTO_ALTO:
            return "Media"
        else:
            return "Baja"

    def asignar_excepciones(
        self,
        resultados_conciliacion: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Agrega prioridad y analista a cada excepción de la conciliación.

        Modifica ``resultados_conciliacion`` en el lugar (los conciliados
        quedan con campos vacíos) y devuelve un resumen para la auditoría.
        """

        analistas = self.obtener_analistas()
        conteo = {"Alta": 0, "Media": 0, "Baja": 0}
        carga = {analista["nombre"]: 0 for analista in analistas}
        siguiente = 0

        for resultado in resultados_conciliacion:
            prioridad = self.calcular_prioridad(resultado)

            if not prioridad:
                resultado["prioridad_revision"] = ""
                resultado["analista_asignado"] = ""
                resultado["correo_analista"] = ""
                continue

            # Reparto round-robin: cada analista recibe la siguiente
            # excepción, así la carga queda equilibrada.
            analista = analistas[siguiente % len(analistas)]
            siguiente += 1

            resultado["prioridad_revision"] = prioridad
            resultado["analista_asignado"] = analista["nombre"]
            resultado["correo_analista"] = analista["correo"]

            conteo[prioridad] += 1
            carga[analista["nombre"]] += 1

        return {
            "origen": self.origen,
            "excepciones_asignadas": siguiente,
            "por_prioridad": conteo,
            "carga_por_analista": carga,
        }


if __name__ == "__main__":
    import json

    # Prueba sin Selenium: un caso de cada estado posible.
    ejemplos = [
        {"id_transaccion": "1", "monto": "100", "estado_conciliacion": "Conciliado",
         "detalle_conciliacion": ""},
        {"id_transaccion": "2", "monto": "150", "estado_conciliacion": "Con diferencias",
         "detalle_conciliacion": "Campos diferentes: Monto"},
        {"id_transaccion": "3", "monto": "20", "estado_conciliacion": "Con diferencias",
         "detalle_conciliacion": "Campos diferentes: Acción"},
        {"id_transaccion": "4", "monto": "5000", "estado_conciliacion": "Solo en TestFire",
         "detalle_conciliacion": ""},
        {"id_transaccion": "5", "monto": "100", "estado_conciliacion": "Solo en maestro",
         "detalle_conciliacion": ""},
    ]

    resumen = GeneradorDatosSinteticos().asignar_excepciones(ejemplos)
    print(json.dumps({"resumen": resumen, "resultados": ejemplos},
                     indent=2, ensure_ascii=False))
