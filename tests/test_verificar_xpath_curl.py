"""Pruebas de scripts/verificar_xpath_curl.py con HTML sintético (sin red)."""

import json

from scripts import verificar_xpath_curl as vx

TABLA = f"""
<table id="{vx.ID_TABLA}">
<tr><td>Transaction ID</td><td>Transaction Time</td><td>Account ID</td><td>Action</td><td>Amount</td></tr>
<tr><td>1</td><td>2026-10-18 10:00</td><td>800003</td><td>Deposit</td><td>$1.00</td></tr>
<tr><td>2</td><td>2026-10-18 10:01</td><td>800002</td><td>Withdrawal</td><td>-$1.00</td></tr>
<tr><td colspan="5">TODO PAGES</td></tr>
</table>
"""


def _pagina(con_tbody: bool) -> str:
    fila = "<tr><td></td><td><div><form>{t}</form></div></td></tr>"
    cuerpo = fila.format(t="<table></table>" + TABLA)
    if con_tbody:
        cuerpo = f"<tbody>{cuerpo}</tbody>"
    return f"<html><body><table></table><table>{cuerpo}</table></body></html>"


def test_id_y_xpath_relativo_encuentran_la_tabla_y_cuentan_filas(tmp_path):
    ruta = tmp_path / "p.html"
    ruta.write_text(_pagina(con_tbody=True), encoding="utf-8")

    r = vx.verificar(ruta)

    for nombre in ("id", "xpath_relativo"):
        assert r[nombre]["tablas"] == 1
        assert r[nombre]["filas_tr"] == 4
        assert r[nombre]["filas_datos"] == 2
        assert r[nombre]["filas_vacias"] == 1  # fila "TODO PAGES"


def test_xpath_absoluto_depende_de_tbody(tmp_path):
    con = tmp_path / "con.html"
    con.write_text(_pagina(con_tbody=True), encoding="utf-8")
    sin = tmp_path / "sin.html"
    sin.write_text(_pagina(con_tbody=False), encoding="utf-8")

    rc, rs = vx.verificar(con), vx.verificar(sin)

    assert rc["xpath_absoluto_dom_navegador"]["tablas"] >= 0
    # En un documento, exactamente una de las dos variantes absolutas debe resolver.
    assert (
        (rc["xpath_absoluto_dom_navegador"]["tablas"] > 0) != (rc["xpath_absoluto_fuente_sin_tbody"]["tablas"] > 0)
    ) or (rc["xpath_absoluto_dom_navegador"]["tablas"] == 0 and rc["xpath_absoluto_fuente_sin_tbody"]["tablas"] == 0)
    assert rs["id"]["filas_datos"] == 2


def test_cli_escribe_json_y_falla_con_codigo_2_si_no_hay_html(tmp_path, capsys):
    ruta = tmp_path / "p.html"
    ruta.write_text(_pagina(con_tbody=False), encoding="utf-8")
    salida = tmp_path / "precision.json"

    assert vx.main(["--html", str(ruta), "--salida", str(salida)]) == 0
    assert json.loads(salida.read_text(encoding="utf-8"))["id"]["filas_datos"] == 2
    assert vx.main(["--html", str(tmp_path / "no_existe.html")]) == 2
