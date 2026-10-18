"""
Prueba de precisión de selectores sobre el HTML descargado con cURL (IL 2.2).

Compara los mismos selectores que usa el robot de Rocketbot (ID, XPath
relativo y XPath absoluto) contra el HTML crudo que entrega el servidor.

Uso:
    py scripts\\verificar_xpath_curl.py --html transaction.html
    py scripts\\verificar_xpath_curl.py --html transaction.html --salida precision_selectores.json

Requiere ``lxml`` (py -m pip install lxml).

Por qué hay dos XPath absolutos: el navegador inserta ``<tbody>`` al armar
el DOM, pero el HTML crudo (cURL) puede no traerlo. Un XPath absoluto copiado
del navegador puede fallar sobre la fuente, y eso es parte de lo que se mide.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lxml import html

ID_TABLA = "_ctl0__ctl0_Content_Main_MyTransactions"
COLUMNAS_ESPERADAS = 5

SELECTORES = {
    "id": f'//*[@id="{ID_TABLA}"]',
    "xpath_relativo": f'//table[@id="{ID_TABLA}"]',
    "xpath_absoluto_dom_navegador": "/html/body/table[2]/tbody/tr/td[2]/div/form/table[2]",
    "xpath_absoluto_fuente_sin_tbody": "/html/body/table[2]/tr/td[2]/div/form/table[2]",
}


def medir(arbol: Any, xpath: str) -> dict[str, Any]:
    tablas = arbol.xpath(xpath)
    if not tablas:
        return {"xpath": xpath, "tablas": 0, "filas_tr": 0, "filas_datos": 0, "filas_vacias": 0}

    filas = tablas[0].xpath(".//tr")
    datos = [f for f in filas if len(f.xpath("./td|./th")) == COLUMNAS_ESPERADAS]
    # El encabezado también tiene 5 celdas: se descuenta para contar solo datos.
    datos_sin_encabezado = max(len(datos) - 1, 0)
    return {
        "xpath": xpath,
        "tablas": len(tablas),
        "filas_tr": len(filas),
        "filas_datos": datos_sin_encabezado,
        "filas_vacias": len(filas) - len(datos),
    }


def verificar(ruta_html: Path) -> dict[str, dict[str, Any]]:
    if not ruta_html.exists():
        raise FileNotFoundError(f"No existe el HTML: {ruta_html}")
    arbol = html.fromstring(ruta_html.read_bytes())
    return {nombre: medir(arbol, xp) for nombre, xp in SELECTORES.items()}


def imprimir(resultados: dict[str, dict[str, Any]]) -> None:
    print(f"{'selector':36}{'tablas':>7}{'tr':>6}{'datos':>7}{'vacias':>8}")
    for nombre, r in resultados.items():
        print(f"{nombre:36}{r['tablas']:>7}{r['filas_tr']:>6}{r['filas_datos']:>7}{r['filas_vacias']:>8}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html", type=Path, required=True, help="HTML descargado con cURL")
    parser.add_argument("--salida", type=Path, default=None, help="JSON opcional con el resultado")
    args = parser.parse_args(argv)

    try:
        resultados = verificar(args.html)
    except FileNotFoundError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2

    imprimir(resultados)
    if args.salida:
        args.salida.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nResultado guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
