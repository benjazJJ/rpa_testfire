"""
Pruebas de la cola compartida en Postgres (la de Neon).

Se saltan si no existe TEST_COLA_URL. Para correrlas, apunta a una base de
PRUEBA (borra sus tablas):  set TEST_COLA_URL=postgresql://...
"""

import os
import threading
import time

import pytest

URL = os.environ.get("TEST_COLA_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_COLA_URL no definida")

if URL:
    import psycopg

    from src.cola_postgres import ColaCorreosPG


@pytest.fixture
def cola(tmp_path):
    with psycopg.connect(URL, autocommit=True) as con:
        con.execute("DROP TABLE IF EXISTS cola_correos; DROP TABLE IF EXISTS adjuntos;")
    return ColaCorreosPG(URL, carpeta_adjuntos=tmp_path / "pc_procesador")


def casos(n, adjunto=True):
    return [{"clave_unica": f"L|{i}", "destinatario": f"a{i}@duocuc.cl", "asunto": "x", "cuerpo": "y",
             "casos": [str(i)], "prioridad": 2, "adjunto": "reporte.xlsx" if adjunto else None}
            for i in range(1, n + 1)]


def test_encola_sin_duplicar_y_guarda_el_adjunto(cola, tmp_path):
    excel = tmp_path / "reporte_final_X.xlsx"
    excel.write_bytes(b"contenido del excel")
    assert cola.encolar(casos(3), "L", "E1", adjunto=excel)["encolados"] == 3
    assert cola.encolar(casos(3), "L", "E2", adjunto=excel)["encolados"] == 0
    caso = cola.tomar_siguiente("P1")
    # El procesador (otro PC) recibe el adjunto desde la base, no desde el disco del encolador.
    assert caso["adjunto"].startswith(str(tmp_path / "pc_procesador"))
    assert open(caso["adjunto"], "rb").read() == b"contenido del excel"
    assert cola.ultimo_lote() == "L"


def test_dos_procesadores_en_paralelo_nunca_toman_el_mismo_caso(cola):
    cola.encolar(casos(40, adjunto=False), "L", "E")
    tomados = {"P1": [], "P2": []}

    def procesador(nombre):
        while (caso := cola.tomar_siguiente(nombre)) is not None:
            tomados[nombre].append(caso["id"])
            cola.marcar_enviado(caso["id"])

    hilos = [threading.Thread(target=procesador, args=(n,)) for n in tomados]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    todos = tomados["P1"] + tomados["P2"]
    assert sorted(todos) == list(range(1, 41))  # los 40, cada uno una sola vez
    assert cola.resumen()["ENVIADO"] == 40


def test_encolar_espera_si_otro_pc_tiene_el_bloqueo(cola):
    avisos = []
    otra = ColaCorreosPG(URL, avisar=avisos.append)
    with psycopg.connect(URL, autocommit=True) as con, con.transaction():
        con.execute("SELECT pg_advisory_xact_lock(20261124)")  # "otro PC" está encolando
        hilo = threading.Thread(target=lambda: otra.encolar(casos(2, adjunto=False), "L2", "E"))
        hilo.start()
        time.sleep(4)
        assert hilo.is_alive()  # esperando turno
    hilo.join(timeout=10)
    assert not hilo.is_alive()
    assert any("Esperando turno" in a for a in avisos)
    assert cola.resumen("L2")["PENDIENTE"] == 2


def test_errores_reintentos_y_respuestas(cola):
    cola.encolar(casos(1, adjunto=False), "L", "E")
    caso = cola.tomar_siguiente("P")
    assert cola.marcar_error(caso["id"], "timeout") == "ERROR"
    assert cola.tomar_siguiente("P", excluir=[caso["id"]]) is None
    caso = cola.tomar_siguiente("P")
    assert caso["intentos"] == 2
    assert cola.marcar_error(caso["id"], "dirección mala", permanente=True) == "FALLIDO"
    assert cola.registrar_respuesta(caso["id"], "APROBADO", "be.palmap@duocuc.cl", "2026-11-20T10:00:00")
    fila = cola.listar()[0]
    assert (fila["estado"], fila["respuesta"]) == ("FALLIDO", "APROBADO")
    assert isinstance(fila["creado_en"], str)  # exportable a Excel
