"""
Prueba la conexión a la cola compartida (Neon) desde este PC.

    py scripts/probar_cola.py

Revisa que config.json tenga "cola": {"url"}, que el PC llegue a la base,
crea las tablas si no existen y muestra cómo está la cola. No modifica casos.
"""

from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.cola_correos import abrir_cola, url_cola_compartida  # noqa: E402


def main() -> int:
    print(f"PC: {platform.node()}\n")
    url = url_cola_compartida()
    if not url:
        print('[X] config\\config.json no tiene la sección "cola": {"url": "postgresql://..."}')
        return 2
    servidor = url.split("@")[-1].split("/")[0]
    print(f"Conectando a {servidor} ...")
    inicio = time.perf_counter()
    try:
        cola = abrir_cola()
        resumen = cola.resumen()
        lote = cola.ultimo_lote()
    except Exception as error:
        print(f"[X] No se pudo conectar: {type(error).__name__}: {error}")
        print("    Revisa la URL en config.json y que la red permita salir por el puerto 5432.")
        return 2
    print(f"[OK] Conectado a la cola compartida en {time.perf_counter() - inicio:.1f} s")
    print(f"[OK] Último lote encolado: {lote or '(ninguno todavía)'}")
    print("[OK] Casos: " + ", ".join(f"{k} {v}" for k, v in resumen.items()))
    print("\nTodo listo: este PC puede leer y escribir la cola.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
