"""Pruebas de la Evaluación 3: API del dólar, cola dispatcher/performer y canal simulado."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook, load_workbook

from scripts import dispatcher_correos, performer_correos, referencia_externa_excel
from src import api_dolar
from src.bitacora import Bitacora
from src.canales_correo import CanalSimulacion, ErrorEnvioPermanente, validar_destinatario
from src.cola_correos import ENVIADO, ERROR, FALLIDO, PENDIENTE, ColaCorreos

JSON_OK = {
    "version": "1.7.0", "autor": "mindicador.cl", "codigo": "dolar", "nombre": "Dólar observado",
    "unidad_medida": "Pesos",
    "serie": [{"fecha": "2026-11-16T03:00:00.000Z", "valor": 999.1},
              {"fecha": "2026-11-17T03:00:00.000Z", "valor": 1001.17}],
}


class RespuestaFalsa:
    def __init__(self, codigo, datos=None):
        self.status_code = codigo
        self._datos = datos
        self.elapsed = type("t", (), {"total_seconds": lambda self: 0.1})()

    def json(self):
        if self._datos is None:
            raise ValueError("no es JSON")
        return self._datos


@pytest.fixture
def bitacora(tmp_path):
    return Bitacora("RPA_TEST", usar_sheets=False, carpeta_logs=tmp_path / "logs")


# ------------------------------------------------------------------ API dólar

def test_validar_toma_el_valor_mas_reciente():
    r = api_dolar.validar_respuesta(JSON_OK)
    assert r["valor"] == Decimal("1001.17") and r["fecha_valor"] == "2026-11-17"


@pytest.mark.parametrize("malo", [
    [], {"codigo": "uf", "serie": [{"fecha": "2026-11-17T03:00:00Z", "valor": 1}]},
    {"codigo": "dolar", "serie": []},
    {"codigo": "dolar", "serie": [{"fecha": "2026-11-17T03:00:00Z", "valor": 5}]},  # fuera de rango
])
def test_validar_rechaza_respuestas_malas(malo):
    with pytest.raises(ValueError):
        api_dolar.validar_respuesta(malo)


def test_api_ok_guarda_cache(monkeypatch, tmp_path, bitacora):
    monkeypatch.setattr(api_dolar.requests, "get", lambda *a, **k: RespuestaFalsa(200, JSON_OK))
    r = api_dolar.obtener_dolar(ruta_cache=tmp_path / "c.json", bitacora=bitacora)
    assert r["origen"] == "api" and r["codigo_http"] == 200
    assert json.loads((tmp_path / "c.json").read_text())["valor"] == "1001.17"


def test_api_caida_usa_cache_y_reintenta(monkeypatch, tmp_path, bitacora):
    llamadas = []
    monkeypatch.setattr(api_dolar.time, "sleep", lambda s: None)
    monkeypatch.setattr(api_dolar.requests, "get", lambda *a, **k: RespuestaFalsa(200, JSON_OK))
    api_dolar.obtener_dolar(ruta_cache=tmp_path / "c.json")

    def caida(*a, **k):
        llamadas.append(1)
        raise requests.Timeout()

    monkeypatch.setattr(api_dolar.requests, "get", caida)
    r = api_dolar.obtener_dolar(ruta_cache=tmp_path / "c.json", bitacora=bitacora)
    assert len(llamadas) == 3  # 3 intentos
    assert r["origen"] == "cache" and "timeout" in r["motivo_cache"]


def test_api_4xx_no_reintenta_y_sin_cache_falla(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(api_dolar.requests, "get", lambda *a, **k: llamadas.append(1) or RespuestaFalsa(404))
    with pytest.raises(api_dolar.ErrorApiDolar):
        api_dolar.obtener_dolar(ruta_cache=tmp_path / "no_hay.json", ruta_respaldo=tmp_path / "tampoco.json")
    assert len(llamadas) == 1


def test_referencia_externa_agrega_columna_y_hoja(monkeypatch, tmp_path, bitacora):
    monkeypatch.setattr(api_dolar.requests, "get", lambda *a, **k: RespuestaFalsa(200, JSON_OK))
    monkeypatch.setattr(referencia_externa_excel, "obtener_dolar",
                        lambda **k: api_dolar.obtener_dolar(ruta_cache=tmp_path / "c.json"))
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Discrepancias"
    hoja.append(["id_transaccion", "monto", "estado_conciliacion"])
    hoja.append(["1", "-1224", "Con diferencias"])
    hoja.append(["2", "1000000000000000000", "Solo en TestFire"])  # monto extremo del sitio demo
    entrada = tmp_path / "discrepancias.xlsx"
    libro.save(entrada)

    r = referencia_externa_excel.ejecutar(entrada, tmp_path / "salida", bitacora)
    final = load_workbook(r["reporte_final"])
    filas = list(final["Discrepancias"].iter_rows(values_only=True))
    assert filas[0][-1] == "monto_clp"
    assert filas[1][-1] == -1225432          # -1224 x 1001,17
    assert filas[2][-1] == "1001170000000000000000"  # texto: no cabe en un número de Excel
    assert "Referencia externa" in final.sheetnames
    assert load_workbook(entrada).active.max_column == 3  # el original queda intacto


# ------------------------------------------------------------------ cola

def _casos(n, invalido=None):
    casos = [{"clave_unica": f"L|{i}", "destinatario": f"a{i}@example.com", "asunto": "x",
              "cuerpo": "y", "casos": [str(i)], "prioridad": 2} for i in range(1, n + 1)]
    if invalido:
        casos[invalido - 1]["destinatario"] = "malo@@example.com"
    return casos


def test_encolar_es_idempotente(tmp_path):
    cola = ColaCorreos(tmp_path / "c.db")
    assert cola.encolar(_casos(5), "L", "E1")["encolados"] == 5
    assert cola.encolar(_casos(5), "L", "E2") == {"recibidos": 5, "encolados": 0, "ya_existian": 5}


def test_un_error_no_detiene_y_se_retoma(tmp_path, bitacora):
    cola = ColaCorreos(tmp_path / "c.db")
    cola.encolar(_casos(10, invalido=4), "L", "E")
    canal = CanalSimulacion(tmp_path / "eml", fallos_pasajeros={2})

    # Primera corrida "se cae" a los 5 casos.
    c1 = performer_correos.procesar(cola, canal, bitacora, max_envios=5, pausa=0)
    assert c1 == {"procesados": 5, "enviados": 3, "errores": 1, "fallidos": 1, "detenido_por": None}
    assert cola.resumen()[PENDIENTE] == 5

    # Segunda corrida retoma en el 6 y reintenta el 2 al final.
    performer_correos.procesar(cola, canal, bitacora, max_envios=0, pausa=0)
    estados = {f["id"]: (f["estado"], f["intentos"]) for f in cola.listar()}
    assert estados[4] == (FALLIDO, 1)      # dirección inválida: no se reintenta
    assert estados[2] == (ENVIADO, 2)      # falló una vez y salió al reintentar
    assert sum(1 for e, _ in estados.values() if e == ENVIADO) == 9
    assert len(list((tmp_path / "eml").glob("*.eml"))) == 9


def test_error_pasajero_agota_intentos(tmp_path):
    cola = ColaCorreos(tmp_path / "c.db")
    cola.encolar(_casos(1), "L", "E")
    for intento in range(1, 4):
        caso = cola.tomar_siguiente("E")
        assert caso["intentos"] == intento
        estado = cola.marcar_error(caso["id"], "timeout")
    assert estado == FALLIDO and cola.tomar_siguiente("E") is None


def test_dos_performers_no_toman_el_mismo_caso(tmp_path):
    cola_a = ColaCorreos(tmp_path / "c.db")
    cola_b = ColaCorreos(tmp_path / "c.db")
    cola_a.encolar(_casos(2), "L", "E")
    assert cola_a.tomar_siguiente("A")["id"] != cola_b.tomar_siguiente("B")["id"]
    assert cola_a.tomar_siguiente("A") is None


def test_liberar_atascados(tmp_path):
    cola = ColaCorreos(tmp_path / "c.db")
    cola.encolar(_casos(1), "L", "E")
    cola.tomar_siguiente("E")
    assert cola.liberar_atascados(minutos=-1) == 1
    assert cola.resumen()[PENDIENTE] == 1


def test_canal_real_nunca_envia_a_dominios_de_prueba():
    with pytest.raises(ErrorEnvioPermanente):
        validar_destinatario("analista1@example.com", permitir_prueba=False)
    validar_destinatario("alguien@duocuc.cl", permitir_prueba=False)


# ------------------------------------------------------------------ dispatcher

def test_agrupado_manda_un_correo_por_destinatario(tmp_path):
    excepciones = [{"id_transaccion": str(i), "estado_conciliacion": "Con diferencias",
                    "detalle_conciliacion": "Campos diferentes: Monto", "monto": "10",
                    "monto_clp": 10011, "prioridad_revision": "Alta"} for i in range(100)]
    casos = dispatcher_correos.armar_agrupado(excepciones, ["a@x.cl", "b@x.cl"], "L", None)
    assert len(casos) == 2
    assert sum(len(c["casos"]) for c in casos) == 100
    assert "-$" not in dispatcher_correos.formato_clp(5) and dispatcher_correos.formato_clp(-1225432) == "-$1.225.432 CLP"


def test_demo_volumen_solo_usa_example_com():
    casos = dispatcher_correos.armar_demo_volumen([], 50, 7, "DEMO")
    assert len(casos) == 50
    assert all(c["destinatario"].endswith("@example.com") for c in casos)
    assert casos[6]["destinatario"] == "analista@@example.com"


def test_api_caida_en_pc_nuevo_usa_el_respaldo_del_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(api_dolar.requests, "get", lambda *a, **k: RespuestaFalsa(404))
    r = api_dolar.obtener_dolar(ruta_cache=tmp_path / "no_hay.json")
    assert r["origen"] == "respaldo" and r["valor"] > 0
