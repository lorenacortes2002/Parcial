# -*- coding: utf-8 -*-
"""
correo.py  -  Generacion de archivo JSON + envio por correo (CHINOS CAFE S.A.)
------------------------------------------------------------------------------
- guardar_json(): crea el archivo JSON de confirmacion del pedido/pago.
- enviar_correo(): envia ese JSON como adjunto por SMTP (Gmail) a la
  empresa / cliente / operario.

Si el envio SMTP falla (sin internet, credenciales, etc.), NO rompe la app:
se registra el intento en  correos_enviados/  para poder sustentar la demo.
"""

import os
import json
import ssl
import smtplib
from datetime import datetime
from email.message import EmailMessage

# Carpetas de evidencia
CARPETA_JSON = "pedidos_json"
CARPETA_LOG = "correos_enviados"


def _asegurar(carpeta):
    if not os.path.exists(carpeta):
        os.makedirs(carpeta, exist_ok=True)


def guardar_json(nombre_base, datos):
    """
    Guarda 'datos' (dict) como archivo JSON con fecha/hora en el nombre.
    Devuelve la ruta del archivo creado.
    """
    try:
        _asegurar(CARPETA_JSON)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(CARPETA_JSON, "%s_%s.json" % (nombre_base, sello))
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=4, ensure_ascii=False)
        return ruta
    except (OSError, TypeError, ValueError) as e:
        print("[ERROR guardar_json] %s" % e)
        return None


def enviar_correo(asunto, cuerpo, destinatarios, adjunto_json=None):
    """
    Envia un correo por SMTP (Gmail, STARTTLS) con el JSON adjunto.
    destinatarios: lista de correos.
    Devuelve (ok: bool, mensaje: str).
    """
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    puerto = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER", "")
    clave = os.getenv("SMTP_PASS", "")

    destinatarios = [d for d in destinatarios if d]  # quita vacios

    # Siempre dejamos evidencia local del correo (sustentacion).
    _registrar_log(asunto, cuerpo, destinatarios, adjunto_json)

    if not usuario or not clave:
        return (False, "SMTP no configurado (.env). Se guardo copia local del correo.")

    try:
        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = usuario
        msg["To"] = ", ".join(destinatarios)
        msg.set_content(cuerpo)

        # Adjuntar el JSON
        if adjunto_json and os.path.exists(adjunto_json):
            with open(adjunto_json, "rb") as f:
                contenido = f.read()
            msg.add_attachment(
                contenido,
                maintype="application",
                subtype="json",
                filename=os.path.basename(adjunto_json),
            )

        contexto = ssl.create_default_context()
        with smtplib.SMTP(host, puerto, timeout=20) as servidor:
            servidor.starttls(context=contexto)
            servidor.login(usuario, clave)
            servidor.send_message(msg)

        return (True, "Correo enviado a: %s" % ", ".join(destinatarios))

    except (smtplib.SMTPException, OSError) as e:
        # No rompe la aplicacion: queda la copia local.
        print("[ERROR enviar_correo] %s" % e)
        return (False, "No se pudo enviar por SMTP (%s). Se guardo copia local." % e)


def _registrar_log(asunto, cuerpo, destinatarios, adjunto_json):
    """Guarda una copia .txt del correo como evidencia."""
    try:
        _asegurar(CARPETA_LOG)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = os.path.join(CARPETA_LOG, "correo_%s.txt" % sello)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("FECHA/HORA : %s\n" % datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            f.write("PARA       : %s\n" % ", ".join(destinatarios))
            f.write("ASUNTO     : %s\n" % asunto)
            f.write("ADJUNTO    : %s\n" % (adjunto_json or "(ninguno)"))
            f.write("-" * 50 + "\n")
            f.write(cuerpo + "\n")
    except OSError as e:
        print("[ERROR _registrar_log] %s" % e)
