"""Pruebas de src/datos_sinteticos.py sin acceso a red."""

from unittest.mock import MagicMock

import pytest
from requests.exceptions import ConnectionError as ErrorConexion

from src import datos_sinteticos
from src.datos_sinteticos import GeneradorDatosSinteticos


def _resultado(estado, monto="100", detalle=""):
    return {
        "estado_conciliacion": estado,
        "monto": monto,
        "detalle_conciliacion": detalle,
    }


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    # Los reintentos no deben hacer lentas las pruebas.
    monkeypatch.setattr(datos_sinteticos.time, "sleep", lambda _: None)


@pytest.mark.parametrize(
    ("resultado", "esperada"),
    [
        (_resultado("Conciliado"), ""),
        (_resultado("Con diferencias", detalle="Campos diferentes: Monto"), "Alta"),
        (_resultado("Con diferencias", "1500", "Campos diferentes: Acción"), "Alta"),
        (_resultado("Con diferencias", detalle="Campos diferentes: Acción"), "Media"),
        (_resultado("Solo en TestFire", "5000"), "Media"),
        (_resultado("Solo en maestro", "-20"), "Baja"),
        (_resultado("Solo en maestro", "no-numérico"), "Baja"),
    ],
)
def test_calcular_prioridad(resultado, esperada):
    assert GeneradorDatosSinteticos.calcular_prioridad(resultado) == esperada


def test_usa_randomuser_cuando_responde(monkeypatch):
    respuesta = MagicMock(status_code=200)
    respuesta.json.return_value = {
        "results": [
            {"name": {"first": "Ana", "last": "Pérez"},
             "email": "ana.perez@example.com", "nat": "ES"},
        ]
    }
    monkeypatch.setattr(datos_sinteticos.requests, "get", lambda *a, **k: respuesta)

    generador = GeneradorDatosSinteticos(cantidad_analistas=1)
    analistas = generador.obtener_analistas()

    assert generador.origen == "RandomUser API"
    assert analistas == [
        {"nombre": "Ana Pérez", "correo": "ana.perez@example.com", "nacionalidad": "ES"}
    ]


def test_reintenta_y_usa_respaldo_local(monkeypatch):
    llamadas = []

    def falla(*args, **kwargs):
        llamadas.append(1)
        raise ErrorConexion("sin red")

    monkeypatch.setattr(datos_sinteticos.requests, "get", falla)

    generador = GeneradorDatosSinteticos(cantidad_analistas=3, max_intentos=3)
    analistas = generador.obtener_analistas()

    assert len(llamadas) == 3
    assert generador.origen == "Respaldo local"
    assert len(analistas) == 3
    assert all(a["correo"].endswith("@example.com") for a in analistas)


def test_asignar_excepciones_reparte_round_robin(monkeypatch):
    monkeypatch.setattr(datos_sinteticos.requests, "get", MagicMock(side_effect=ErrorConexion()))

    resultados = [
        _resultado("Conciliado"),
        _resultado("Con diferencias", detalle="Campos diferentes: Monto"),
        _resultado("Solo en TestFire"),
        _resultado("Solo en maestro"),
    ]
    resumen = GeneradorDatosSinteticos(cantidad_analistas=2, max_intentos=1).asignar_excepciones(
        resultados
    )

    assert resultados[0]["analista_asignado"] == ""
    assert resultados[1]["analista_asignado"] != resultados[2]["analista_asignado"]
    assert resultados[1]["analista_asignado"] == resultados[3]["analista_asignado"]
    assert resumen["excepciones_asignadas"] == 3
    assert resumen["por_prioridad"] == {"Alta": 1, "Media": 0, "Baja": 2}
    assert sum(resumen["carga_por_analista"].values()) == 3


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        GeneradorDatosSinteticos(cantidad_analistas=0)
    with pytest.raises(ValueError):
        GeneradorDatosSinteticos(max_intentos=0)
