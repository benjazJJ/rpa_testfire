"""Pruebas de guardar_consolidado: la tabla completa al Excel de una vez."""

import json

import pytest
from openpyxl import load_workbook

from scripts.guardar_consolidado import guardar

ENCABEZADO = ["Transaction ID", "Transaction Time", "Account ID", "Action", "Amount"]


def test_escribe_todas_las_filas_igual_que_el_for(tmp_path):
    filas = [ENCABEZADO] + [[str(i), "2026-10-18 11:44", "800034", "Withdrawal", "-$1234.00"] for i in range(100)]
    filas.insert(5, ["fila", "rota"])  # sin 5 columnas: se descarta
    entrada = tmp_path / "filas_web.json"
    entrada.write_text(json.dumps(filas), encoding="utf-8")
    r = guardar(entrada, tmp_path / "consolidado.xlsx")
    assert (r["filas"], r["movimientos"], r["descartadas"]) == (101, 100, 1)
    hoja = load_workbook(tmp_path / "consolidado.xlsx").active
    assert (hoja.max_row, hoja.max_column) == (101, 5)  # lo mismo que valida el robot
    assert [c.value for c in hoja[1]] == ENCABEZADO
    assert [c.value for c in hoja[2]] == ["0", "2026-10-18 11:44", "800034", "Withdrawal", "-$1234.00"]


@pytest.mark.parametrize("contenido", ["[]", "{}", json.dumps([["a", "b", "c", "d", "e"]])])
def test_rechaza_tablas_invalidas(tmp_path, contenido):
    entrada = tmp_path / "filas_web.json"
    entrada.write_text(contenido, encoding="utf-8")
    with pytest.raises(ValueError):
        guardar(entrada, tmp_path / "x.xlsx")


def test_sin_archivo_falla_claro(tmp_path):
    with pytest.raises(FileNotFoundError, match="Rocketbot no dejó"):
        guardar(tmp_path / "no_existe.json", tmp_path / "x.xlsx")
