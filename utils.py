"""
utils.py
-------------------------------------------------
Funciones auxiliares:
  - generar_json_pedido / generar_json_pago: crean el archivo JSON que
    se "envía" por correo electrónico a la empresa/cliente/operario.
  - enviar_correo: intenta enviar el JSON por SMTP; si no hay servidor
    de correo configurado (entorno de prueba/local), captura el error
    con try/except y deja constancia en un log, sin tumbar la app.
  - generar_codigo_cobro / qr_svg: crean el código del cobro Yappy y su QR.
  - simular_pago_yappy: simula la captura de pago con Yappy Comercial.
-------------------------------------------------
"""

import json
import os
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime

import segno

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PEDIDOS_JSON_DIR = os.path.join(BASE_DIR, "pedidos_json")
PAGOS_JSON_DIR = os.path.join(BASE_DIR, "pagos_json")
LOG_PATH = os.path.join(BASE_DIR, "correos_enviados.log")

# --- Configuración SMTP (editar con los datos reales del servidor) -------
SMTP_HOST = os.environ.get("SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 25))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
EMPRESA_CORREO = os.environ.get("EMPRESA_CORREO", "pedidos@chinoscafe.local")

# --- Datos del comercio en Yappy (editar con los reales) --------------------
YAPPY_TELEFONO = os.environ.get("YAPPY_TELEFONO", "6123-4567")
YAPPY_DIRECTORIO = os.environ.get("YAPPY_DIRECTORIO", "@ChinosCafe")


def _guardar_json(data, carpeta, prefijo):
    try:
        os.makedirs(carpeta, exist_ok=True)
        nombre = f"{prefijo}_{data['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        ruta = os.path.join(carpeta, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return ruta
    except (OSError, TypeError, ValueError) as e:
        print(f"[ERROR JSON] No se pudo guardar el archivo JSON: {e}")
        return None


def generar_json_pedido(pedido):
    data = {
        "tipo": "CONFIRMACION_PEDIDO",
        "id": pedido["id"],
        "cliente": pedido["cliente"],
        "correo_cliente": pedido["correo_cliente"],
        "pizza": pedido["pizza_nombre"],
        "refresco": pedido["refresco"],
        "refresco_cantidad": pedido.get("refresco_cantidad"),
        "refresco_tamano": pedido.get("refresco_tamano"),
        "refrescos_detalle": pedido.get("refrescos_detalle", []),
        "cantidad": pedido["cantidad"],
        "total": pedido["total"],
        "retiro_o_flete": pedido["retiro_o_flete"],
        "direccion": pedido.get("direccion"),
        "estado": pedido["estado"],
        "fecha": pedido["fecha"],
    }
    return data, _guardar_json(data, PEDIDOS_JSON_DIR, "pedido")


def generar_json_pago(pago, pedido):
    data = {
        "tipo": "CONFIRMACION_PAGO",
        "id": pago["id"],
        "pedido_id": pago["pedido_id"],
        "cliente": pedido["cliente"],
        "metodo": pago["metodo"],
        "monto": pago["monto"],
        "estado": pago["estado"],
        "retiro_o_flete": pedido["retiro_o_flete"],
        "direccion": pedido.get("direccion"),
        "fecha": pago["fecha"],
    }
    return data, _guardar_json(data, PAGOS_JSON_DIR, "pago")


def enviar_correo(destinatario, asunto, json_data, ruta_json):
    """
    Intenta enviar el archivo JSON adjunto por correo electrónico.
    Si no hay un servidor SMTP disponible (caso típico en pruebas locales),
    el error se captura y se registra en un log, sin interrumpir el flujo
    de la aplicación (requisito de control Try-Catch del examen).
    """
    enviado = False
    error_msg = None
    try:
        msg = EmailMessage()
        msg["Subject"] = asunto
        msg["From"] = EMPRESA_CORREO
        msg["To"] = destinatario
        msg.set_content(
            f"Se adjunta la confirmación en formato JSON.\n\n{json.dumps(json_data, indent=2, ensure_ascii=False)}"
        )
        if ruta_json and os.path.exists(ruta_json):
            with open(ruta_json, "rb") as f:
                msg.add_attachment(
                    f.read(), maintype="application", subtype="json",
                    filename=os.path.basename(ruta_json)
                )

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5) as server:
            if SMTP_USER:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        enviado = True
    except (smtplib.SMTPException, OSError, ConnectionRefusedError, TimeoutError) as e:
        error_msg = str(e)
        print(f"[AVISO] No se pudo enviar el correo real (se registró en log): {e}")
    finally:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as log:
                estado = "ENVIADO" if enviado else f"SIMULADO/NO ENVIADO ({error_msg})"
                log.write(f"{datetime.now()} -> Para: {destinatario} | Asunto: {asunto} | {estado}\n")
        except OSError as e:
            print(f"[ERROR LOG] No se pudo escribir el log de correos: {e}")

    return enviado, error_msg


def simular_pago_yappy(monto):
    """
    Simula la captura de pago con 'Yappy Comercial'.
    En producción aquí iría la integración real con la API de Yappy.
    """
    try:
        monto = float(monto)
        if monto <= 0:
            raise ValueError("El monto debe ser mayor a cero.")
        referencia = f"YAPPY-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return True, referencia, None
    except (ValueError, TypeError) as e:
        return False, None, str(e)


def generar_codigo_cobro():
    """Código corto que el cliente escribe en el mensaje del pago Yappy."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O ni 1/I para evitar confusiones
    return "CC-" + "".join(secrets.choice(alfabeto) for _ in range(6))


def qr_svg(contenido):
    """Devuelve el código QR de `contenido` como SVG listo para incrustar en HTML."""
    return segno.make(contenido, error="m").svg_inline(
        scale=6, border=2, dark="#193a2b", light="#ffffff"
    )
