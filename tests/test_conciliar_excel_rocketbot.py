"""Pruebas de scripts/conciliar_excel_rocketbot.py (sin red, con SQLite temporal)."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from scripts import conciliar_excel_rocketbot as cer

RAIZ = Path(__file__).resolve().parent.parent
ENCABEZADO = ["Transaction ID", "Transaction Time", "Account ID", "Action", "Amount"]


@pytest.fixture()
def db(tmp_path):
    ruta = tmp_path / "master.db"
    con = sqlite3.connect(ruta)
    con.execute(
        "CREATE TABLE movimientos_master (id_transaccion TEXT PRIMARY KEY, "
        "fecha_hora TEXT NOT NULL, id_cuenta TEXT NOT NULL, accion TEXT NOT NULL, "
        "monto TEXT NOT NULL, fecha_hora_original TEXT, accion_original TEXT, monto_original TEXT)"
    )
    con.executemany(
        "INSERT INTO movimientos_master (id_transaccion, fecha_hora, id_cuenta, accion, monto) "
        "VALUES (?,?,?,?,?)",
        [
            ("100", "2026-10-17 11:04", "800003", "withdrawal", "-1.00"),
            ("101", "2026-10-17 11:04", "800002", "deposit", "1.00"),
            ("102", "2026-10-17 11:05", "800003", "deposit", "0.01"),
            ("999", "2026-10-17 10:00", "800002", "deposit", "5.00"),
        ],
    )
    con.commit()
    con.close()
    return ruta


def _excel(ruta: Path, filas, con_encabezado=True):
    libro = Workbook()
    hoja = libro.active
    if con_encabezado:
        hoja.append(ENCABEZADO)
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)
    return ruta


def test_clasifica_conciliado_diferencia_y_solo_en_cada_lado(tmp_path, db):
    excel = _excel(
        tmp_path / "c.xlsx",
        [
            ["100", "2026-10-17 11:04", "800003", "Withdrawal", "-$1.00"],  # coincide
            ["101", "2026-10-17 11:04", "800002", "Deposit", "$2.00"],  # monto distinto
            ["200", "2026-10-17 11:06", "800002", "Deposit", "$3.00"],  # solo web
        ],
    )

    resumen = cer.ejecutar(excel, db, tmp_path / "out")

    assert resumen["conciliados"] == 1
    assert resumen["con_diferencias"] == 1
    assert resumen["solo_testfire"] == 1
    assert resumen["solo_maestro"] == 2  # 102 y 999
    assert resumen["filas_rechazadas"] == 0
    assert (tmp_path / "out" / "resumen_conciliacion.json").exists()


def test_encabezado_opcional(tmp_path, db):
    excel = _excel(
        tmp_path / "c.xlsx",
        [["100", "2026-10-17 11:04", "800003", "Withdrawal", "-$1.00"]],
        con_encabezado=False,
    )
    assert cer.ejecutar(excel, db, tmp_path / "out")["conciliados"] == 1


def test_fila_invalida_y_duplicada_se_rechazan_sin_abortar(tmp_path, db):
    excel = _excel(
        tmp_path / "c.xlsx",
        [
            ["100", "2026-10-17 11:04", "800003", "Withdrawal", "-$1.00"],
            ["100", "2026-10-17 11:04", "800003", "Withdrawal", "-$1.00"],  # duplicado
            ["300", "2026-10-17 11:07", "800003", "Deposit", "no-es-monto"],  # monto ilegible
            [None, None, None, None, None],  # fila vacía: se ignora
        ],
    )

    resumen = cer.ejecutar(excel, db, tmp_path / "out")

    assert resumen["filas_leidas"] == 3
    assert resumen["filas_rechazadas"] == 2
    assert resumen["conciliados"] == 1
    hoja = load_workbook(resumen["reporte"])["Rechazados"]
    assert hoja.max_row == 3  # encabezado + 2 rechazadas


def test_monto_extremo_no_pierde_precision(tmp_path, db):
    excel = _excel(
        tmp_path / "c.xlsx",
        [["400", "2026-10-17 11:04", "800003", "Deposit", "$1000000000000000000.00"]],
    )
    resumen = cer.ejecutar(excel, db, tmp_path / "out")
    hoja = load_workbook(resumen["reporte"])["Resultado"]
    montos = [fila[4].value for fila in hoja.iter_rows(min_row=2)]
    assert "1000000000000000000.00" in montos


def test_cli_devuelve_json_en_una_linea_y_codigo_0(tmp_path, db):
    excel = _excel(
        tmp_path / "c.xlsx",
        [["100", "2026-10-17 11:04", "800003", "Withdrawal", "-$1.00"]],
    )
    proc = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "conciliar_excel_rocketbot.py"),
         "--excel", str(excel), "--db", str(db), "--salida", str(tmp_path / "out")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0
    lineas = proc.stdout.strip().splitlines()
    assert len(lineas) == 1
    assert json.loads(lineas[0])["ok"] is True


def test_cli_excel_inexistente_devuelve_codigo_2(tmp_path, db):
    proc = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "conciliar_excel_rocketbot.py"),
         "--excel", str(tmp_path / "no_existe.xlsx"), "--db", str(db), "--salida", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["ok"] is False
