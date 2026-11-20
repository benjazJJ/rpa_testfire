"""
Cola de correos con tracker (Subproceso 4 de la Evaluación 3).

Patrón dispatcher / performer:

- El DISPATCHER solo encola: crea una fila por correo a enviar, en estado
  PENDIENTE. No envía nada.
- El PERFORMER toma de a un caso, lo marca EN_PROCESO, intenta enviarlo y
  lo deja en ENVIADO o ERROR. Un error no lo detiene: sigue con el próximo.

Estados de cada caso (el "tracker"):

    PENDIENTE ──► EN_PROCESO ──► ENVIADO
        ▲              │
        │              ├──► ERROR    (se reintenta al final, hasta max_intentos)
        └──────────────┘      │
                              └──► FALLIDO  (agotó los intentos o el error es permanente,
                                             p. ej. dirección mal escrita)

Por qué SQLite: el estado de cada caso tiene que sobrevivir a una caída del
robot. Si se cae en el caso 650, la próxima ejecución parte en el 651
porque del 1 al 650 ya están ENVIADO. Y "tomar" un caso es un UPDATE
atómico, así que dos performers en paralelo nunca toman el mismo.
"""

from __future__ import annotations

import json
import platform
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_COLA = RAIZ_PROYECTO / "data" / "cola" / "cola_correos.db"

PENDIENTE, EN_PROCESO, ENVIADO, ERROR, FALLIDO = (
    "PENDIENTE", "EN_PROCESO", "ENVIADO", "ERROR", "FALLIDO",
)
ESTADOS = (PENDIENTE, EN_PROCESO, ENVIADO, ERROR, FALLIDO)

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS cola_correos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    lote              TEXT    NOT NULL,              -- una carga del dispatcher
    clave_unica       TEXT    NOT NULL UNIQUE,       -- evita encolar dos veces lo mismo
    destinatario      TEXT    NOT NULL,
    nombre_destino    TEXT,
    asunto            TEXT    NOT NULL,
    cuerpo            TEXT    NOT NULL,
    adjunto           TEXT,
    casos             TEXT    NOT NULL DEFAULT '[]', -- IDs de transacción incluidos (JSON)
    prioridad         INTEGER NOT NULL DEFAULT 3,    -- 1 Alta, 2 Media, 3 Baja
    estado            TEXT    NOT NULL DEFAULT '{PENDIENTE}'
                      CHECK (estado IN {ESTADOS}),
    intentos          INTEGER NOT NULL DEFAULT 0,
    max_intentos      INTEGER NOT NULL DEFAULT 3,
    ultimo_error      TEXT,
    creado_en         TEXT    NOT NULL,
    tomado_en         TEXT,
    procesado_en      TEXT,
    ejecucion_dispatcher TEXT,
    ejecucion_performer  TEXT,
    pc_performer      TEXT
);
CREATE INDEX IF NOT EXISTS idx_cola_estado ON cola_correos (estado, intentos, prioridad, id);
CREATE INDEX IF NOT EXISTS idx_cola_lote   ON cola_correos (lote);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ColaCorreos:
    def __init__(self, ruta: Path = RUTA_COLA):
        self.ruta = Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as con:
            con.executescript(ESQUEMA)
            # Columnas de la recepción (Subproceso 4d). Se agregan si la cola
            # se creó con una versión anterior del script.
            existentes = {f["name"] for f in con.execute("PRAGMA table_info(cola_correos)")}
            for columna in ("respuesta", "respuesta_de", "respuesta_en"):
                if columna not in existentes:
                    con.execute(f"ALTER TABLE cola_correos ADD COLUMN {columna} TEXT")

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        # timeout: si otro performer tiene la base tomada, espera en vez de fallar.
        con = sqlite3.connect(self.ruta, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")  # lecturas mientras otro escribe
            yield con
        finally:
            con.close()

    # ------------------------------------------------------------- dispatcher

    compartida = False

    def encolar(self, casos: list[dict[str, Any]], lote: str, id_ejecucion: str,
                adjunto: Path | None = None) -> dict[str, int]:
        """
        Inserta los casos como PENDIENTE. Los que ya existen (misma
        ``clave_unica``) se omiten: re-ejecutar el dispatcher no duplica correos.
        """
        nuevos = 0
        with self._conexion() as con:
            con.execute("BEGIN IMMEDIATE")
            for caso in casos:
                cursor = con.execute(
                    """
                    INSERT OR IGNORE INTO cola_correos
                        (lote, clave_unica, destinatario, nombre_destino, asunto, cuerpo,
                         adjunto, casos, prioridad, max_intentos, creado_en, ejecucion_dispatcher)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lote, caso["clave_unica"], caso["destinatario"], caso.get("nombre_destino"),
                        caso["asunto"], caso["cuerpo"], caso.get("adjunto"),
                        json.dumps(caso.get("casos", []), ensure_ascii=False),
                        int(caso.get("prioridad", 3)), int(caso.get("max_intentos", 3)),
                        _ahora(), id_ejecucion,
                    ),
                )
                nuevos += cursor.rowcount
            con.execute("COMMIT")
        return {"recibidos": len(casos), "encolados": nuevos, "ya_existian": len(casos) - nuevos}

    # -------------------------------------------------------------- performer

    def liberar_atascados(self, minutos: int = 15) -> int:
        """
        Casos EN_PROCESO hace más de ``minutos``: el performer que los tomó
        murió a mitad de camino. Vuelven a PENDIENTE para que otro los tome.
        """
        limite = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
        with self._conexion() as con:
            cursor = con.execute(
                f"UPDATE cola_correos SET estado = '{PENDIENTE}', "
                "ultimo_error = 'Liberado: el performer anterior no terminó' "
                f"WHERE estado = '{EN_PROCESO}' AND tomado_en < ?",
                (limite,),
            )
            return cursor.rowcount

    def tomar_siguiente(self, id_ejecucion: str, excluir: Iterable[int] = ()) -> dict[str, Any] | None:
        """
        Toma el próximo caso de forma atómica y lo marca EN_PROCESO.

        Orden: primero los PENDIENTE nunca intentados (por prioridad y orden
        de llegada); los ERROR se reintentan después, al final de la cola.
        ``excluir``: IDs que esta corrida ya no debe volver a tomar.
        """
        excluir = [int(i) for i in excluir]
        filtro = f"AND id NOT IN ({','.join('?' * len(excluir))})" if excluir else ""
        with self._conexion() as con:
            con.execute("BEGIN IMMEDIATE")  # bloquea escritura: nadie más toma este caso
            fila = con.execute(
                f"""
                SELECT id FROM cola_correos
                WHERE (estado = '{PENDIENTE}'
                       OR (estado = '{ERROR}' AND intentos < max_intentos))
                  {filtro}
                ORDER BY CASE estado WHEN '{PENDIENTE}' THEN 0 ELSE 1 END,
                         intentos, prioridad, id
                LIMIT 1
                """,
                excluir,
            ).fetchone()
            if fila is None:
                con.execute("COMMIT")
                return None
            con.execute(
                f"UPDATE cola_correos SET estado = '{EN_PROCESO}', intentos = intentos + 1, "
                "tomado_en = ?, ejecucion_performer = ?, pc_performer = ? WHERE id = ?",
                (_ahora(), id_ejecucion, platform.node(), fila["id"]),
            )
            caso = dict(con.execute("SELECT * FROM cola_correos WHERE id = ?", (fila["id"],)).fetchone())
            con.execute("COMMIT")
        caso["casos"] = json.loads(caso["casos"])
        return caso

    def marcar_enviado(self, id_caso: int) -> None:
        with self._conexion() as con:
            con.execute(
                f"UPDATE cola_correos SET estado = '{ENVIADO}', procesado_en = ?, ultimo_error = NULL "
                "WHERE id = ?",
                (_ahora(), id_caso),
            )

    def marcar_error(self, id_caso: int, motivo: str, permanente: bool = False) -> str:
        """
        Deja el caso en ERROR (se reintentará) o FALLIDO (no se reintenta).
        Devuelve el estado final.
        """
        with self._conexion() as con:
            fila = con.execute(
                "SELECT intentos, max_intentos FROM cola_correos WHERE id = ?", (id_caso,)
            ).fetchone()
            agotado = fila["intentos"] >= fila["max_intentos"]
            estado = FALLIDO if (permanente or agotado) else ERROR
            con.execute(
                "UPDATE cola_correos SET estado = ?, procesado_en = ?, ultimo_error = ? WHERE id = ?",
                (estado, _ahora(), motivo[:300], id_caso),
            )
        return estado

    # -------------------------------------------------------------- recepción

    def registrar_respuesta(self, id_caso: int, decision: str, de: str, fecha: str) -> bool:
        """Anota la respuesta (APROBADO / RECHAZADO / REVISAR). False si el caso no existe."""
        with self._conexion() as con:
            cursor = con.execute(
                "UPDATE cola_correos SET respuesta = ?, respuesta_de = ?, respuesta_en = ? WHERE id = ?",
                (decision, de[:200], fecha, int(id_caso)),
            )
            return cursor.rowcount == 1

    # ---------------------------------------------------------------- tracker

    def resumen(self, lote: str | None = None) -> dict[str, int]:
        filtro, params = ("WHERE lote = ?", (lote,)) if lote else ("", ())
        with self._conexion() as con:
            filas = con.execute(
                f"SELECT estado, count(*) AS n FROM cola_correos {filtro} GROUP BY estado", params
            ).fetchall()
        conteo = {estado: 0 for estado in ESTADOS}
        conteo.update({f["estado"]: f["n"] for f in filas})
        conteo["TOTAL"] = sum(conteo[e] for e in ESTADOS)
        return conteo

    def ultimo_lote(self) -> str | None:
        with self._conexion() as con:
            fila = con.execute("SELECT lote FROM cola_correos ORDER BY id DESC LIMIT 1").fetchone()
        return fila["lote"] if fila else None

    def descargar_ultimo_adjunto(self, destino: Path) -> Path | None:
        """En la cola local el adjunto ya es un archivo de este PC: no hay nada que descargar."""
        return None

    def listar(self, lote: str | None = None) -> list[dict[str, Any]]:
        filtro, params = ("WHERE lote = ?", (lote,)) if lote else ("", ())
        with self._conexion() as con:
            filas = con.execute(
                "SELECT id, lote, destinatario, nombre_destino, asunto, casos, prioridad, estado, "
                "intentos, ultimo_error, creado_en, tomado_en, procesado_en, "
                "ejecucion_performer, pc_performer, respuesta, respuesta_de, respuesta_en "
                f"FROM cola_correos {filtro} ORDER BY id",
                params,
            ).fetchall()
        return [dict(f) for f in filas]


# ------------------------------------------------------------------ fábrica

def url_cola_compartida() -> str | None:
    """URL de la cola en Neon (config.json -> "cola": {"url"} o RPA_COLA_URL), o None."""
    import os

    if os.environ.get("RPA_COLA_URL"):
        return os.environ["RPA_COLA_URL"]
    try:
        config = json.loads((RAIZ_PROYECTO / "config" / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = str((config.get("cola") or {}).get("url", "")).strip()
    return url if url.startswith("postgres") else None


def abrir_cola(ruta: Path | None = None, avisar=None):
    """
    La cola que corresponde a este PC:
    - ``ruta`` indicada (pruebas y demo)  -> SQLite local en esa ruta;
    - URL de Neon en config.json         -> cola COMPARTIDA entre PCs (Postgres);
    - nada configurado                    -> SQLite local en data/cola/.
    """
    if ruta is not None:
        return ColaCorreos(ruta)
    url = url_cola_compartida()
    if url:
        from src.cola_postgres import ColaCorreosPG

        return ColaCorreosPG(url, avisar=avisar)
    return ColaCorreos(RUTA_COLA)
