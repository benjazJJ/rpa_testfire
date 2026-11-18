"""
Prueba la cuenta de correo del curso antes de correr el robot.

    py scripts/probar_correo.py                         (solo inicia sesión)
    py scripts/probar_correo.py --enviar be.palmap@duocuc.cl  (además manda 1 correo)

Revisa, con los datos de config.json:
1. SMTP (465, SSL): conecta e inicia sesión.
2. IMAP (993, SSL): conecta, inicia sesión, lista las carpetas y cuenta
   cuántas respuestas "[RPA-TF #n]" hay en la bandeja.
3. Opcional: envía un correo de prueba con el código [RPA-TF #0].

Muestra cada resultado en pantalla, sin mostrar la clave.
"""

from __future__ import annotations

import argparse
import imaplib
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.config_correo import ConfigCorreoInvalida, cargar_config_correo, describir  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prueba la cuenta SMTP/IMAP de config.json.")
    parser.add_argument("--enviar", metavar="CORREO", help="Envía un correo de prueba a esta dirección")
    args = parser.parse_args(argv)

    try:
        cfg = cargar_config_correo()
    except ConfigCorreoInvalida as error:
        print(f"[X] {error}")
        return 2
    print(f"Probando {describir(cfg)}\n")
    contexto = ssl.create_default_context()
    todo_ok = True

    try:
        with smtplib.SMTP_SSL(cfg["smtp_servidor"], cfg["smtp_puerto"], timeout=20, context=contexto) as smtp:
            smtp.login(cfg["usuario"], cfg["clave"])
            print("[OK] SMTP: sesión iniciada")
            if args.enviar:
                m = EmailMessage()
                m["From"], m["To"] = cfg["remitente"], args.enviar
                m["Subject"] = "[RPA-TF #0] Prueba de conexión del RPA TestFire"
                m["Date"] = formatdate(localtime=True)
                m["Message-ID"] = make_msgid(domain=cfg["remitente"].rsplit("@", 1)[-1])
                m.set_content("Correo de prueba del robot. Si lo recibes, el envío SMTP funciona.\n"
                              "Responde APROBADO para probar también la clasificación.")
                smtp.send_message(m)
                print(f"[OK] SMTP: correo de prueba enviado a {args.enviar} (revisa también Spam)")
    except smtplib.SMTPAuthenticationError as error:
        todo_ok = False
        print(f"[X] SMTP: el servidor rechazó usuario o clave (código {error.smtp_code})")
    except Exception as error:
        todo_ok = False
        print(f"[X] SMTP: {type(error).__name__}: {error}")

    try:
        imap = imaplib.IMAP4_SSL(cfg["imap_servidor"], cfg["imap_puerto"], ssl_context=contexto, timeout=20)
        imap.login(cfg["usuario"], cfg["clave"])
        print("[OK] IMAP: sesión iniciada")
        _, carpetas = imap.list()
        nombres = [c.decode(errors="replace").split(' "')[-1].strip('"') for c in carpetas or [] if c]
        print(f"[OK] IMAP: carpetas -> {', '.join(nombres)}")
        imap.select("INBOX", readonly=True)
        _, datos = imap.uid("SEARCH", None, "SUBJECT", '"RPA-TF"')
        print(f"[OK] IMAP: {len((datos[0] or b'').split())} correos con [RPA-TF] en la bandeja de entrada")
        imap.logout()
    except imaplib.IMAP4.error as error:
        todo_ok = False
        print(f"[X] IMAP: el servidor rechazó usuario o clave ({error})")
    except Exception as error:
        todo_ok = False
        print(f"[X] IMAP: {type(error).__name__}: {error}")

    print("\nTodo listo." if todo_ok else "\nHay errores: revisa la sección \"correo\" de config/config.json.")
    return 0 if todo_ok else 2


if __name__ == "__main__":
    sys.exit(main())
