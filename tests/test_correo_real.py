"""Pruebas del canal SMTP y del clasificador IMAP, con servidores falsos (sin red)."""

import smtplib
from email.message import EmailMessage

import pytest

from scripts import clasificar_respuestas as cr
from src.bitacora import Bitacora
from src.canales_correo import CanalSMTP, ErrorCanal, ErrorEnvio, ErrorEnvioPermanente
from src.cola_correos import ColaCorreos

CFG = {"smtp_servidor": "smtp.prueba", "smtp_puerto": 465, "imap_servidor": "imap.prueba",
       "imap_puerto": 993, "usuario": "robot", "clave": "x", "remitente": "robot@curso.cl"}
CASO = {"id": 7, "destinatario": "be.palmap@duocuc.cl", "asunto": "Excepciones", "cuerpo": "Hola", "intentos": 1}


# ------------------------------------------------------------------ SMTP

class SMTPFalso:
    def __init__(self, *a, falla=None, **k):
        self.falla = falla
        self.enviados = []

    def login(self, usuario, clave):
        if clave == "mala":
            raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")

    def send_message(self, mensaje):
        if self.falla:
            raise self.falla
        self.enviados.append(mensaje)
        return {}

    def quit(self):
        pass

    def close(self):
        pass


def canal_con(monkeypatch, falla=None, clave="x"):
    servidor = SMTPFalso(falla=falla)
    monkeypatch.setattr(smtplib, "SMTP_SSL", lambda *a, **k: servidor)
    return CanalSMTP({**CFG, "clave": clave}), servidor


def test_smtp_envia_con_codigo_de_caso_en_el_asunto(monkeypatch):
    canal, servidor = canal_con(monkeypatch)
    assert canal.enviar(CASO).startswith("SMTP 250")
    assert servidor.enviados[0]["Subject"] == "[RPA-TF #7] Excepciones"
    assert servidor.enviados[0]["From"] == "robot@curso.cl"


@pytest.mark.parametrize("falla, error", [
    (smtplib.SMTPRecipientsRefused({"x": (550, b"no existe")}), ErrorEnvioPermanente),
    (smtplib.SMTPRecipientsRefused({"x": (451, b"ocupado")}), ErrorEnvio),
    (smtplib.SMTPServerDisconnected("se corto"), ErrorEnvio),
    (smtplib.SMTPSenderRefused(553, b"remitente", "robot@curso.cl"), ErrorCanal),
])
def test_smtp_traduce_cada_error(monkeypatch, falla, error):
    canal, _ = canal_con(monkeypatch, falla=falla)
    with pytest.raises(error):
        canal.enviar(CASO)


def test_smtp_clave_mala_detiene_el_canal(monkeypatch):
    canal, _ = canal_con(monkeypatch, clave="mala")
    with pytest.raises(ErrorCanal, match="usuario o clave"):
        canal.enviar(CASO)


def test_smtp_nunca_envia_a_example_com(monkeypatch):
    canal, servidor = canal_con(monkeypatch)
    with pytest.raises(ErrorEnvioPermanente):
        canal.enviar({**CASO, "destinatario": "analista1@example.com"})
    assert servidor.enviados == []


# ------------------------------------------------------------------ decisión

CITA_OUTLOOK = "\n\nDe: robot@curso.cl\nEnviado: martes\nResponda con APROBADO o RECHAZADO"
CITA_GMAIL = "\n\nEl mar, 18 nov 2026 a las 15:00, robot <robot@curso.cl> escribió:\n> Responda APROBADO o RECHAZADO"


@pytest.mark.parametrize("asunto, cuerpo, esperado", [
    ("RE: [RPA-TF #3] x", "Aprobado, gracias" + CITA_OUTLOOK, cr.APROBADO),
    ("RE: [RPA-TF #3] x", "RECHAZADO: el monto no cuadra" + CITA_GMAIL, cr.RECHAZADO),
    ("RE: [RPA-TF #3] APROBADO", "" + CITA_GMAIL, cr.APROBADO),
    ("RE: [RPA-TF #3] x", "Lo reviso mañana" + CITA_GMAIL, cr.REVISAR),
    ("RE: [RPA-TF #3] x", "aprobado y rechazado?" + CITA_GMAIL, cr.REVISAR),
    ("RE: [RPA-TF #3] x", "Apruebo los 9 casos", cr.APROBADO),
])
def test_decide_solo_con_el_texto_propio(asunto, cuerpo, esperado):
    assert cr.decidir(asunto, cuerpo) == esperado


# ------------------------------------------------------------------ IMAP

def correo(uid, de, asunto, cuerpo):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = de, "robot@curso.cl", asunto
    m["Date"] = "Wed, 18 Nov 2026 15:20:00 -0300"
    m.set_content(cuerpo)
    return uid, bytes(m)


class IMAPFalso:
    capabilities = ("IMAP4REV1",)  # sin MOVE: obliga a COPY + borrar

    def __init__(self, correos, carpetas_bajo_inbox=False):
        self.bandeja = dict(correos)
        self.carpetas = {"INBOX": []}
        self.bajo_inbox = carpetas_bajo_inbox
        self.borrados = set()

    def select(self, nombre):
        return "OK", [str(len(self.bandeja)).encode()]

    def list(self):
        return "OK", [f'(\\HasNoChildren) "." "{n}"'.encode() for n in self.carpetas]

    def create(self, nombre):
        nombre = nombre.strip('"')
        if self.bajo_inbox and not nombre.startswith("INBOX."):
            return "NO", [b"solo bajo INBOX"]
        self.carpetas[nombre] = []
        return "OK", [b""]

    def subscribe(self, nombre):
        return "OK", [b""]

    def uid(self, comando, *args):
        if comando == "SEARCH":
            return "OK", [b" ".join(u for u, c in self.bandeja.items() if b"RPA-TF" in c)]
        if comando == "FETCH":
            return "OK", [(b"1 (BODY[] {n}", self.bandeja[args[0]]), b")"]
        if comando == "COPY":
            self.carpetas[args[1].strip('"')].append(args[0])
            return "OK", [b""]
        if comando == "STORE":
            self.borrados.add(args[0])
            return "OK", [b""]
        raise AssertionError(comando)

    def expunge(self):
        for uid in self.borrados:
            self.bandeja.pop(uid, None)
        self.borrados.clear()
        return "OK", [b""]

    def logout(self):
        pass


@pytest.fixture
def cola_con_casos(tmp_path):
    cola = ColaCorreos(tmp_path / "c.db")
    cola.encolar([{"clave_unica": f"L|{i}", "destinatario": "be.palmap@duocuc.cl", "asunto": "x",
                   "cuerpo": "y"} for i in range(1, 4)], "L", "E")
    return cola


@pytest.mark.parametrize("bajo_inbox", [False, True])
def test_clasifica_mueve_y_anota(tmp_path, cola_con_casos, bajo_inbox):
    imap = IMAPFalso([
        correo(b"1", "Benjamin <be.palmap@duocuc.cl>", "RE: [RPA-TF #1] 9 excepciones", "APROBADO" + CITA_OUTLOOK),
        correo(b"2", "be.palmap@duocuc.cl", "RE: [RPA-TF #2] 9 excepciones", "Rechazado, revisar montos" + CITA_GMAIL),
        correo(b"3", "be.palmap@duocuc.cl", "RE: [RPA-TF #3] 8 excepciones", "Lo veo después" + CITA_GMAIL),
        correo(b"4", "robot@curso.cl", "[RPA-TF #1] 9 excepciones", "copia del robot"),
        correo(b"5", "otro@curso.cl", "Hola", "no es del robot"),
    ], carpetas_bajo_inbox=bajo_inbox)
    bitacora = Bitacora("RPA_T", usar_sheets=False, carpeta_logs=tmp_path / "logs")
    r = cr.clasificar(cr.BuzonIMAP(CFG, conexion=imap), cola_con_casos, "robot@curso.cl", bitacora)

    assert (r[cr.APROBADO], r[cr.RECHAZADO], r[cr.REVISAR], r["omitidos_propios"]) == (1, 1, 1, 1)
    prefijo = "INBOX." if bajo_inbox else ""
    assert imap.carpetas[prefijo + "RPA_APROBADO"] == [b"1"]
    assert imap.carpetas[prefijo + "RPA_RECHAZADO"] == [b"2"]
    assert set(imap.bandeja) == {b"4", b"5"}  # los clasificados salieron de la bandeja
    respuestas = {f["id"]: f["respuesta"] for f in cola_con_casos.listar()}
    assert respuestas == {1: "APROBADO", 2: "RECHAZADO", 3: "REVISAR"}


def test_solo_leer_no_mueve_ni_anota(tmp_path, cola_con_casos):
    imap = IMAPFalso([correo(b"1", "be.palmap@duocuc.cl", "RE: [RPA-TF #1] x", "APROBADO")])
    bitacora = Bitacora("RPA_T", usar_sheets=False, carpeta_logs=tmp_path / "logs")
    r = cr.clasificar(cr.BuzonIMAP(CFG, conexion=imap), cola_con_casos, "robot@curso.cl", bitacora, solo_leer=True)
    assert r[cr.APROBADO] == 1 and b"1" in imap.bandeja
    assert cola_con_casos.listar()[0]["respuesta"] is None
