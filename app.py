"""
app.py
-------------------------------------------------
CHINOS CAFÉ S.A. - Prototipo Web (CRUD de pizzas / pedidos / pagos)
Examen Parcial 2 - Ingeniería Web - UTP - Prof. Napoleón Ibarra

Ejecutar en desarrollo:
    pip install -r requirements.txt
    python app.py
    -> abrir http://127.0.0.1:5000

Para producción (servidor Linux con NGINX) ver README.md
-------------------------------------------------
"""

import os
import secrets
import math
import re
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash

import database
from utils import (
    generar_json_pedido, generar_json_pago,
    enviar_correo, simular_pago_yappy, EMPRESA_CORREO
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

MIN_INGREDIENTES = 2
MAX_INGREDIENTES = 10

INGREDIENTES_DISPONIBLES = [
    "queso mozzarella", "pepperoni", "jamón", "piña", "champiñones",
    "pimentón", "cebolla", "aceitunas", "tocineta", "maíz",
    "salsa de tomate", "parmesano", "queso azul", "gouda", "chorizo",
]

REFRESCOS_DISPONIBLES = [
    "Coca-Cola", "Coca-Cola Zero", "Sprite", "Fanta", "Agua", "Ninguno"
]


def _pizza_fields_from_form():
    nombre = request.form.get("nombre", "").strip()
    ingredientes = request.form.getlist("ingredientes")
    refresco = request.form.get("refresco", "")
    precio = float(request.form.get("precio", "0"))

    if not nombre:
        raise ValueError("El nombre de la pizza es obligatorio.")
    if len(ingredientes) < MIN_INGREDIENTES or len(ingredientes) > MAX_INGREDIENTES:
        raise ValueError(
            f"Debe seleccionar entre {MIN_INGREDIENTES} y {MAX_INGREDIENTES} ingredientes."
        )
    if len(set(ingredientes)) != len(ingredientes) or not set(ingredientes).issubset(
        INGREDIENTES_DISPONIBLES
    ):
        raise ValueError("Seleccione ingredientes válidos y sin duplicados.")
    if refresco not in REFRESCOS_DISPONIBLES:
        raise ValueError("Seleccione un refresco válido.")
    if not math.isfinite(precio) or precio <= 0:
        raise ValueError("El precio debe ser un número mayor a cero.")

    return nombre, ingredientes, refresco, precio


def _notify_json_recipients(recipients, subject, json_data, ruta_json):
    if not ruta_json:
        flash(
            "La transacción quedó guardada, pero no se pudo crear su archivo JSON; "
            "no se intentó enviar el correo.",
            "warning",
        )
        return

    results = [
        enviar_correo(destinatario, subject, json_data, ruta_json)
        for destinatario in recipients
    ]
    if all(sent for sent, _ in results):
        flash("Archivo JSON creado y correos de confirmación enviados.", "success")
    else:
        flash(
            "Archivo JSON creado y transacción guardada, pero no se pudieron enviar "
            "todos los correos. Verifique la configuración SMTP y el log.",
            "warning",
        )


# ----------------------------------------------------------------------
# Home
# ----------------------------------------------------------------------
@app.route("/")
def index():
    try:
        conn = database.get_local_conn()
        pizzas = conn.execute("SELECT * FROM pizzas").fetchall()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar el menú: {e}", "danger")
        pizzas = []
    return render_template("index.html", pizzas=pizzas)


# ----------------------------------------------------------------------
# FABRICA — CRUD de pizzas (ingredientes, refrescos)
# ----------------------------------------------------------------------
@app.route("/fabrica")
def fabrica():
    try:
        conn = database.get_local_conn()
        pizzas = conn.execute("SELECT * FROM pizzas ORDER BY id").fetchall()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al consultar pizzas: {e}", "danger")
        pizzas = []
    return render_template("fabrica.html", pizzas=pizzas)


@app.route("/fabrica/nueva", methods=["GET", "POST"])
def fabrica_nueva():
    if request.method == "POST":
        try:
            nombre, ingredientes, refresco, precio = _pizza_fields_from_form()

            ok, last_id, error = database.replicate_write(
                "INSERT INTO pizzas (nombre, ingredientes, refresco, precio) VALUES (?,?,?,?)",
                (nombre, ",".join(ingredientes), refresco, precio),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            flash(f"Pizza '{nombre}' creada correctamente (guardada y replicada).", "success")
            return redirect(url_for("fabrica"))

        except (ValueError, RuntimeError) as e:
            flash(f"Error: {e}", "danger")

    return render_template(
        "fabrica_form.html", pizza=None,
        ingredientes_disponibles=INGREDIENTES_DISPONIBLES,
        refrescos_disponibles=REFRESCOS_DISPONIBLES,
        min_ing=MIN_INGREDIENTES, max_ing=MAX_INGREDIENTES,
    )


@app.route("/fabrica/editar/<int:pizza_id>", methods=["GET", "POST"])
def fabrica_editar(pizza_id):
    try:
        conn = database.get_local_conn()
        pizza = conn.execute("SELECT * FROM pizzas WHERE id=?", (pizza_id,)).fetchone()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar la pizza: {e}", "danger")
        return redirect(url_for("fabrica"))

    if pizza is None:
        flash("Pizza no encontrada.", "warning")
        return redirect(url_for("fabrica"))

    if request.method == "POST":
        try:
            nombre, ingredientes, refresco, precio = _pizza_fields_from_form()

            ok, _, error = database.replicate_write(
                "UPDATE pizzas SET nombre=?, ingredientes=?, refresco=?, precio=? WHERE id=?",
                (nombre, ",".join(ingredientes), refresco, precio, pizza_id),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            flash(f"Pizza '{nombre}' actualizada correctamente.", "success")
            return redirect(url_for("fabrica"))

        except (ValueError, RuntimeError) as e:
            flash(f"Error: {e}", "danger")

    ingredientes_actuales = pizza["ingredientes"].split(",") if pizza["ingredientes"] else []
    return render_template(
        "fabrica_form.html", pizza=pizza,
        ingredientes_disponibles=INGREDIENTES_DISPONIBLES,
        refrescos_disponibles=REFRESCOS_DISPONIBLES,
        ingredientes_actuales=ingredientes_actuales,
        min_ing=MIN_INGREDIENTES, max_ing=MAX_INGREDIENTES,
    )


@app.route("/fabrica/eliminar/<int:pizza_id>", methods=["POST"])
def fabrica_eliminar(pizza_id):
    try:
        conn = database.get_local_conn()
        pizza_count = conn.execute("SELECT COUNT(*) FROM pizzas").fetchone()[0]
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al comprobar el catálogo: {e}", "danger")
        return redirect(url_for("fabrica"))

    if pizza_count <= 5:
        flash("El catálogo debe conservar al menos cinco combos.", "warning")
        return redirect(url_for("fabrica"))

    ok, _, error = database.replicate_write("DELETE FROM pizzas WHERE id=?", (pizza_id,))
    if not ok:
        flash(f"Error al eliminar: {error}", "danger")
    else:
        if error:
            flash(error, "warning")
        flash("Pizza eliminada correctamente.", "success")
    return redirect(url_for("fabrica"))


# ----------------------------------------------------------------------
# PEDIDOS — el cliente arma su combo; se confirma por JSON/correo,
# se guarda en la DB local y se replica en la DB de réplica.
# ----------------------------------------------------------------------
@app.route("/pedidos", methods=["GET", "POST"])
def pedidos():
    try:
        conn = database.get_local_conn()
        pizzas = conn.execute("SELECT * FROM pizzas ORDER BY id").fetchall()
        lista_pedidos = conn.execute(
            "SELECT pedidos.*, pizzas.nombre AS pizza_nombre "
            "FROM pedidos JOIN pizzas ON pedidos.pizza_id = pizzas.id "
            "ORDER BY pedidos.id DESC"
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar datos: {e}", "danger")
        pizzas, lista_pedidos = [], []

    selected_pizza_id = (
        request.form.get("pizza_id", "")
        if request.method == "POST"
        else request.args.get("pizza_id", "")
    )
    try:
        selected_pizza_id = int(selected_pizza_id) if selected_pizza_id else None
    except ValueError:
        selected_pizza_id = None
        flash("La pizza solicitada no es válida; selecciona una opción del menú.", "warning")

    pizza_ids = {pizza["id"] for pizza in pizzas}
    if selected_pizza_id not in pizza_ids:
        selected_pizza_id = pizzas[0]["id"] if pizzas else None

    if request.method == "POST":
        try:
            cliente = request.form.get("cliente", "").strip()
            correo_cliente = request.form.get("correo_cliente", "").strip()
            pizza_id = int(request.form.get("pizza_id"))
            refresco = request.form.get("refresco", "")
            cantidad = int(request.form.get("cantidad", 1))
            retiro_o_flete = request.form.get("retiro_o_flete", "RETIRO EN SITIO")

            if not cliente or not correo_cliente:
                raise ValueError("Debe indicar nombre y correo del cliente.")
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo_cliente):
                raise ValueError("Indique un correo electrónico válido.")
            if cantidad < 1:
                raise ValueError("La cantidad debe ser al menos 1.")
            if refresco not in REFRESCOS_DISPONIBLES:
                raise ValueError("Seleccione un refresco válido.")
            if retiro_o_flete not in ("RETIRO EN SITIO", "FLETE A DOMICILIO"):
                raise ValueError("Seleccione un método de entrega válido.")

            conn = database.get_local_conn()
            pizza = conn.execute("SELECT * FROM pizzas WHERE id=?", (pizza_id,)).fetchone()
            conn.close()
            if pizza is None:
                raise ValueError("La pizza seleccionada no existe.")

            total = round(pizza["precio"] * cantidad, 2)
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ok, pedido_id, error = database.replicate_write(
                "INSERT INTO pedidos (cliente, correo_cliente, pizza_id, refresco, "
                "cantidad, total, estado, retiro_o_flete, fecha) VALUES (?,?,?,?,?,?,?,?,?)",
                (cliente, correo_cliente, pizza_id, refresco, cantidad, total,
                 "CONFIRMADO", retiro_o_flete, fecha),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            pedido_dict = {
                "id": pedido_id, "cliente": cliente, "correo_cliente": correo_cliente,
                "pizza_nombre": pizza["nombre"], "refresco": refresco, "cantidad": cantidad,
                "total": total, "retiro_o_flete": retiro_o_flete,
                "estado": "CONFIRMADO", "fecha": fecha,
            }
            json_data, ruta_json = generar_json_pedido(pedido_dict)

            _notify_json_recipients(
                (
                    correo_cliente,
                    EMPRESA_CORREO,
                ),
                f"Confirmación del pedido #{pedido_id} - CHINOS CAFÉ S.A.",
                json_data,
                ruta_json,
            )

            flash(f"Pedido #{pedido_id} confirmado y guardado en ambas bases.", "success")
            return redirect(url_for("pedidos"))

        except (ValueError, RuntimeError, TypeError) as e:
            flash(f"Error al crear el pedido: {e}", "danger")

    return render_template(
        "pedidos.html", pizzas=pizzas, pedidos=lista_pedidos,
        refrescos_disponibles=REFRESCOS_DISPONIBLES,
        selected_pizza_id=selected_pizza_id,
    )


# ----------------------------------------------------------------------
# PAGOS — confirmación de pago (Yappy Comercial) y despacho al cliente.
# ----------------------------------------------------------------------
@app.route("/pagos", methods=["GET", "POST"])
def pagos():
    try:
        conn = database.get_local_conn()
        pedidos_pendientes = conn.execute(
            "SELECT pedidos.*, pizzas.nombre AS pizza_nombre FROM pedidos "
            "JOIN pizzas ON pedidos.pizza_id = pizzas.id "
            "WHERE pedidos.estado NOT IN ('PAGADO', 'PAGADO - DESPACHAR (FLETE)') "
            "AND NOT EXISTS (SELECT 1 FROM pagos WHERE pagos.pedido_id=pedidos.id) "
            "ORDER BY pedidos.id DESC"
        ).fetchall()
        historial_pagos = conn.execute(
            "SELECT pagos.*, pedidos.cliente, pedidos.retiro_o_flete FROM pagos "
            "JOIN pedidos ON pagos.pedido_id = pedidos.id ORDER BY pagos.id DESC"
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar datos: {e}", "danger")
        pedidos_pendientes, historial_pagos = [], []

    if request.method == "POST":
        try:
            pedido_id = int(request.form.get("pedido_id"))

            conn = database.get_local_conn()
            pedido = conn.execute(
                "SELECT pedidos.*, pizzas.nombre AS pizza_nombre FROM pedidos "
                "JOIN pizzas ON pedidos.pizza_id = pizzas.id WHERE pedidos.id=?",
                (pedido_id,)
            ).fetchone()
            conn.close()
            if pedido is None:
                raise ValueError("El pedido indicado no existe.")
            if pedido["estado"] in ("PAGADO", "PAGADO - DESPACHAR (FLETE)"):
                raise ValueError("Este pedido ya fue pagado.")
            conn = database.get_local_conn()
            pago_existente = conn.execute(
                "SELECT 1 FROM pagos WHERE pedido_id=?", (pedido_id,)
            ).fetchone()
            conn.close()
            if pago_existente:
                raise ValueError("Este pedido ya tiene un pago registrado.")

            ok_pago, referencia, error_pago = simular_pago_yappy(pedido["total"])
            if not ok_pago:
                raise RuntimeError(f"No se pudo procesar el pago con Yappy: {error_pago}")

            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            nuevo_estado = "PAGADO" if pedido["retiro_o_flete"] == "RETIRO EN SITIO" else "PAGADO - DESPACHAR (FLETE)"
            ok, operation_ids, error = database.replicate_transaction(
                [
                    (
                        "INSERT INTO pagos (pedido_id, metodo, monto, estado, fecha) "
                        "VALUES (?,?,?,?,?)",
                        (pedido_id, "YAPPY COMERCIAL", pedido["total"], "CONFIRMADO", fecha),
                    ),
                    ("UPDATE pedidos SET estado=? WHERE id=?", (nuevo_estado, pedido_id)),
                ]
            )
            if not ok:
                raise RuntimeError(error)
            pago_id = operation_ids[0]
            if error:
                flash(error, "warning")

            pago_dict = {
                "id": pago_id, "pedido_id": pedido_id, "metodo": "YAPPY COMERCIAL (" + referencia + ")",
                "monto": pedido["total"], "estado": "CONFIRMADO", "fecha": fecha,
            }
            pedido_dict = {
                "cliente": pedido["cliente"], "retiro_o_flete": pedido["retiro_o_flete"]
            }
            json_data, ruta_json = generar_json_pago(pago_dict, pedido_dict)

            _notify_json_recipients(
                (pedido["correo_cliente"], EMPRESA_CORREO),
                f"Confirmación de pago - Pedido #{pedido_id}",
                json_data, ruta_json
            )

            flash(f"Pago del pedido #{pedido_id} confirmado (ref. {referencia}).", "success")
            return redirect(url_for("pagos"))

        except (ValueError, RuntimeError, TypeError) as e:
            flash(f"Error al procesar el pago: {e}", "danger")

    return render_template(
        "pagos.html", pedidos=pedidos_pendientes, pagos=historial_pagos
    )


if __name__ == "__main__":
    database.init_db()
    # host="0.0.0.0" permite exponerlo en la red LAN / detrás de NGINX
    app.run(host="0.0.0.0", port=5000, debug=True)
