"""
Cola de correos COMPARTIDA en Postgres (Neon), para encolar en un PC y procesar en otros.

Es la misma cola de ``cola_correos.py`` (mismos estados, mismos métodos),
pero en una base a la que llegan todos los PCs por internet:

    PC 1  Robot Encolador   ──►  Neon (Postgres)  ◄──  PC 2..N  Robot Procesador

Bloqueos, como en el pizarrón:

- ENCOLAR: el dispatcher pide un bloqueo de la cola (``pg_advisory_xact_lock``).
  Si otro PC está encolando, espera su turno. Lee la entrada, encola y, al
  confirmar la transacción, el bloqueo se libera solo (DESBLOQUEAR).
- LEER COLA: cada procesador toma un caso con ``SELECT ... FOR UPDATE SKIP
  LOCKED``: bloquea esa fila y salta las que otro PC ya tiene tomadas, así
  dos procesadores nunca envían el mismo correo.

El Excel adjunto se guarda DENTRO de la base (tabla ``adjuntos``): el PC que
envía no tiene el archivo del PC que encoló, así que lo descarga de la cola.

La URL de conexión va en config/config.json -> ``"cola": {"url": "..."}`` o
en la variable de entorno ``RPA_COLA_URL``.
"""

from __future__ import annotations

import json
import platform
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

import psycopg
from psycopg.rows import dict_row

from src.cola_correos import EN_PROCESO, ENVIADO, ERROR, ESTADOS, FALLIDO, PENDIENTE

LLAVE_BLOQUEO_ENCOLAR = 20261124  # número fijo que identifica "la cola" para el bloqueo

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS adjuntos (
    id         BIGSERIAL PRIMARY KEY,
    lote       TEXT        NOT NULL,
    nombre     TEXT        NOT NULL,
    contenido  BYTEA       NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cola_correos (
    id                   BIGSERIAL PRIMARY KEY,
    lote                 TEXT        NOT NULL,
    clave_unica          TEXT        NOT NULL UNIQUE,
    destinatario         TEXT        NOT NULL,
    nombre_destino       TEXT,
    asunto               TEXT        NOT NULL,
    cuerpo               TEXT        NOT NULL,
    adjunto_id           BIGINT REFERENCES adjuntos (id),
    casos                TEXT        NOT NULL DEFAULT '[]',
    prioridad            INTEGER     NOT NULL DEFAULT 3,
    estado               TEXT        NOT NULL DEFAULT '{PENDIENTE}'
                         CHECK (estado IN {ESTADOS}),
    intentos             INTEGER     NOT NULL DEFAULT 0,
    max_intentos         INTEGER     NOT NULL DEFAULT 3,
    ultimo_error         TEXT,
    creado_en            TIMESTAMPTZ NOT NULL DEFAULT now(),
    tomado_en            TIMESTAMPTZ,
    procesado_en         TIMESTAMPTZ,
    ejecucion_dispatcher TEXT,
    pc_dispatcher        TEXT,
    ejecucion_performer  TEXT,
    pc_performer         TEXT,
    respuesta            TEXT,
    respuesta_de         TEXT,
    respuesta_en         TEXT
);
CREATE INDEX IF NOT EXISTS idx_cola_estado ON cola_correos (estado, intentos, prioridad, id);
CREATE INDEX IF NOT EXISTS idx_cola_lote   ON cola_correos (lote);
"""

COLUMNAS_LISTAR = (
    "id, lote, destinatario, nombre_destino, asunto, casos, prioridad, estado, intentos, ultimo_error, "
    "creado_en, tomado_en, procesado_en, ejecucion_performer, pc_performer, pc_dispatcher, "
    "respuesta, respuesta_de, respuesta_en"
)


def _texto_fecha(valor: Any) -> Any:
    """Fechas como texto local (Excel no acepta fechas con zona horaria)."""
    if isinstance(valor, datetime):
        return valor.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    return valor


class ColaCorreosPG:
    compartida = True

    def __init__(self, url: str, carpeta_adjuntos: Path | None = None, avisar=None):
        self.url = url
        self.carpeta_adjuntos = carpeta_adjuntos
        self._avisar = avisar or (lambda mensaje: None)
        with self._conexion() as con:
            # Crear las tablas también bajo el bloqueo: si dos PCs parten a la
            # vez la primera vez, no chocan creando lo mismo.
            with con.transaction():
                con.execute("SELECT pg_advisory_xact_lock(%s)", [LLAVE_BLOQUEO_ENCOLAR])
                con.execute(ESQUEMA)

    @contextmanager
    def _conexion(self) -> Iterator[psycopg.Connection]:
        # prepare_threshold=None: Neon puede pasar por PgBouncer, que no
        # siempre acepta sentencias preparadas.
        con = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=15,
                              prepare_threshold=None, autocommit=True)
        try:
            yield con
        finally:
            con.close()

    # ------------------------------------------------------------- dispatcher

    def encolar(self, casos: list[dict[str, Any]], lote: str, id_ejecucion: str,
                adjunto: Path | None = None, espera_max_seg: int = 300) -> dict[str, int]:
        """BLOQUEAR -> encolar -> DESBLOQUEAR (al confirmar la transacción)."""
        with self._conexion() as con, con.transaction():
            inicio = time.monotonic()
            while not con.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok",
                                  [LLAVE_BLOQUEO_ENCOLAR]).fetchone()["ok"]:
                if time.monotonic() - inicio > espera_max_seg:
                    raise TimeoutError("Otro PC lleva demasiado tiempo encolando; se intentará más tarde.")
                self._avisar("La cola está bloqueada: otro PC está encolando. Esperando turno...")
                time.sleep(3)
            self._avisar("Cola bloqueada para encolar.")

            adjunto_id = None
            if adjunto:
                ruta = Path(adjunto)
                adjunto_id = con.execute(
                    "INSERT INTO adjuntos (lote, nombre, contenido) VALUES (%s, %s, %s) RETURNING id",
                    [lote, ruta.name, ruta.read_bytes()],
                ).fetchone()["id"]

            nuevos = 0
            for caso in casos:
                cursor = con.execute(
                    """
                    INSERT INTO cola_correos
                        (lote, clave_unica, destinatario, nombre_destino, asunto, cuerpo, adjunto_id,
                         casos, prioridad, max_intentos, ejecucion_dispatcher, pc_dispatcher)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (clave_unica) DO NOTHING
                    """,
                    [lote, caso["clave_unica"], caso["destinatario"], caso.get("nombre_destino"),
                     caso["asunto"], caso["cuerpo"], adjunto_id if caso.get("adjunto") else None,
                     json.dumps(caso.get("casos", []), ensure_ascii=False),
                     int(caso.get("prioridad", 3)), int(caso.get("max_intentos", 3)),
                     id_ejecucion, platform.node()],
                )
                nuevos += cursor.rowcount
        self._avisar("Cola desbloqueada.")
        return {"recibidos": len(casos), "encolados": nuevos, "ya_existian": len(casos) - nuevos}

    # -------------------------------------------------------------- performer

    def liberar_atascados(self, minutos: int = 15) -> int:
        with self._conexion() as con:
            return con.execute(
                f"UPDATE cola_correos SET estado = '{PENDIENTE}', "
                "ultimo_error = 'Liberado: el procesador anterior no terminó' "
                f"WHERE estado = '{EN_PROCESO}' AND tomado_en < now() - make_interval(mins => %s)",
                [minutos],
            ).rowcount

    def tomar_siguiente(self, id_ejecucion: str, excluir: Iterable[int] = ()) -> dict[str, Any] | None:
        """Toma un caso con bloqueo de fila; salta los que otro PC ya tomó (SKIP LOCKED)."""
        excluir = [int(i) for i in excluir]
        with self._conexion() as con:
            fila = con.execute(
                f"""
                UPDATE cola_correos SET estado = '{EN_PROCESO}', intentos = intentos + 1,
                       tomado_en = now(), ejecucion_performer = %s, pc_performer = %s
                WHERE id = (
                    SELECT id FROM cola_correos
                    WHERE (estado = '{PENDIENTE}' OR (estado = '{ERROR}' AND intentos < max_intentos))
                      AND NOT (id = ANY(%s))
                    ORDER BY CASE estado WHEN '{PENDIENTE}' THEN 0 ELSE 1 END, intentos, prioridad, id
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
                """,
                [id_ejecucion, platform.node(), excluir],
            ).fetchone()
            if fila is None:
                return None
            caso = {k: _texto_fecha(v) for k, v in fila.items()}
            caso["casos"] = json.loads(caso["casos"])
            caso["adjunto"] = self._archivo_adjunto(con, caso.get("adjunto_id"))
        return caso

    def _archivo_adjunto(self, con, adjunto_id: int | None) -> str | None:
        """Descarga el adjunto de la base a la carpeta local (una vez por lote)."""
        if not adjunto_id:
            return None
        from src.rutas import carpeta_salida

        # Una subcarpeta por adjunto: el archivo conserva su nombre original en el correo.
        carpeta = (self.carpeta_adjuntos or (carpeta_salida() / "adjuntos_cola")) / str(adjunto_id)
        carpeta.mkdir(parents=True, exist_ok=True)
        existentes = [p for p in carpeta.iterdir() if p.is_file()]
        if existentes:
            return str(existentes[0])
        fila = con.execute("SELECT nombre, contenido FROM adjuntos WHERE id = %s", [adjunto_id]).fetchone()
        ruta = carpeta / fila["nombre"]
        ruta.write_bytes(bytes(fila["contenido"]))
        return str(ruta)

    def marcar_enviado(self, id_caso: int) -> None:
        with self._conexion() as con:
            con.execute(f"UPDATE cola_correos SET estado = '{ENVIADO}', procesado_en = now(), "
                        "ultimo_error = NULL WHERE id = %s", [id_caso])

    def marcar_error(self, id_caso: int, motivo: str, permanente: bool = False) -> str:
        with self._conexion() as con:
            fila = con.execute("SELECT intentos, max_intentos FROM cola_correos WHERE id = %s",
                               [id_caso]).fetchone()
            estado = FALLIDO if (permanente or fila["intentos"] >= fila["max_intentos"]) else ERROR
            con.execute("UPDATE cola_correos SET estado = %s, procesado_en = now(), ultimo_error = %s "
                        "WHERE id = %s", [estado, motivo[:300], id_caso])
        return estado

    # -------------------------------------------------------------- recepción

    def registrar_respuesta(self, id_caso: int, decision: str, de: str, fecha: str) -> bool:
        with self._conexion() as con:
            return con.execute(
                "UPDATE cola_correos SET respuesta = %s, respuesta_de = %s, respuesta_en = %s WHERE id = %s",
                [decision, de[:200], fecha, int(id_caso)],
            ).rowcount == 1

    # ---------------------------------------------------------------- tracker

    def resumen(self, lote: str | None = None) -> dict[str, int]:
        filtro, params = ("WHERE lote = %s", [lote]) if lote else ("", [])
        with self._conexion() as con:
            filas = con.execute(f"SELECT estado, count(*) AS n FROM cola_correos {filtro} GROUP BY estado",
                                params).fetchall()
        conteo = {estado: 0 for estado in ESTADOS}
        conteo.update({f["estado"]: f["n"] for f in filas})
        conteo["TOTAL"] = sum(conteo[e] for e in ESTADOS)
        return conteo

    def listar(self, lote: str | None = None) -> list[dict[str, Any]]:
        filtro, params = ("WHERE lote = %s", [lote]) if lote else ("", [])
        with self._conexion() as con:
            filas = con.execute(f"SELECT {COLUMNAS_LISTAR} FROM cola_correos {filtro} ORDER BY id",
                                params).fetchall()
        return [{k: _texto_fecha(v) for k, v in f.items()} for f in filas]

    def ultimo_lote(self) -> str | None:
        with self._conexion() as con:
            fila = con.execute("SELECT lote FROM cola_correos ORDER BY id DESC LIMIT 1").fetchone()
        return fila["lote"] if fila else None

    def descargar_ultimo_adjunto(self, destino: Path) -> Path | None:
        """Guarda en ``destino`` el reporte del último lote encolado (para el correo al supervisor)."""
        with self._conexion() as con:
            fila = con.execute("SELECT contenido FROM adjuntos ORDER BY id DESC LIMIT 1").fetchone()
        if fila is None:
            return None
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(bytes(fila["contenido"]))
        return destino
