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
import socket
import math
import re
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

import database
from utils import (
    generar_json_pedido, generar_json_pago,
    enviar_correo, simular_pago_yappy, EMPRESA_CORREO,
    generar_codigo_cobro, qr_svg, YAPPY_TELEFONO, YAPPY_DIRECTORIO,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

MIN_DIRECCION = 10
MAX_DIRECCION = 300

MIN_INGREDIENTES = 1
MAX_INGREDIENTES = 10

# El queso mozzarella es la base de todas las pizzas, por eso no se ofrece
# como ingrediente (sería redundante).
INGREDIENTES_DISPONIBLES = [
    "pepperoni", "jamón", "piña", "champiñones",
    "pimentón", "cebolla", "aceitunas", "tocineta", "maíz",
    "salsa de tomate", "parmesano", "queso azul", "gouda", "chorizo",
]

REFRESCOS_DISPONIBLES = [
    "Coca-Cola", "Coca-Cola Zero", "Sprite", "Fanta", "Agua", "Ninguno"
]

# Sodas del pedido: sabores (sin "Ninguno": para no pedir soda se elige cantidad 0)
SABORES_SODA = [r for r in REFRESCOS_DISPONIBLES if r != "Ninguno"]
TAMANOS_SODA = {
    "LATA 12 OZ": "Lata 12 oz",
    "BOTELLA 20 OZ": "Botella 20 oz",
    "1 LITRO": "1 litro",
    "2 LITROS": "2 litros",
}
MAX_SODAS = 20


def _sodas_from_form():
    """
    Lee cantidad, tamaño y sabores de soda del formulario de pedidos.
    Devuelve (cantidad, tamaño, [(sabor, cantidad), ...]).
    """
    try:
        cantidad = int(request.form.get("refresco_cantidad", "0") or 0)
    except ValueError:
        raise ValueError("La cantidad de sodas debe ser un número entero.")
    if cantidad < 0 or cantidad > MAX_SODAS:
        raise ValueError(f"La cantidad de sodas debe estar entre 0 y {MAX_SODAS}.")
    if cantidad == 0:
        return 0, None, []

    tamano = request.form.get("refresco_tamano", "")
    if tamano not in TAMANOS_SODA:
        raise ValueError("Seleccione un tamaño de soda válido.")

    sabores = request.form.getlist("refrescos")
    if not sabores:
        raise ValueError("Seleccione al menos un sabor de soda.")
    if len(set(sabores)) != len(sabores) or not set(sabores).issubset(SABORES_SODA):
        raise ValueError("Seleccione sabores de soda válidos y sin duplicados.")
    if len(sabores) > cantidad:
        raise ValueError("No puede elegir más sabores que sodas.")

    if len(sabores) == 1:
        return cantidad, tamano, [(sabores[0], cantidad)]

    detalle = []
    for sabor in sabores:
        try:
            n = int(request.form.get(f"cant_{sabor}", "0"))
        except ValueError:
            n = 0
        if n < 1:
            raise ValueError(f"Indique cuántas sodas de {sabor} desea (mínimo 1).")
        detalle.append((sabor, n))
    if sum(n for _, n in detalle) != cantidad:
        raise ValueError(
            f"La suma de sodas por sabor debe ser igual a {cantidad}."
        )
    return cantidad, tamano, detalle


def _describir_sodas(cantidad, tamano, detalle):
    if cantidad == 0:
        return "Ninguno"
    sabores = ", ".join(f"{n}× {sabor}" for sabor, n in detalle)
    return f"{sabores} ({TAMANOS_SODA[tamano]})"


# Tipos de producto de la Fábrica. Los combos (de una o de dos pizzas)
# incluyen soda; las pizzas individuales no.
TIPOS_PRODUCTO = {
    "COMBO": ("Combo", "Una pizza con soda incluida"),
    "DUO": ("Combo de 2 pizzas", "Dos pizzas individuales diferentes con soda"),
    "PIZZA": ("Pizza individual", "Solo la pizza, sin soda"),
}
TIPOS_COMBO = ("COMBO", "DUO")
MIN_COMBOS = 5

# Formas de entrega que admite cada pizza (valor guardado -> texto visible).
ENTREGAS_PIZZA = {
    "AMBOS": "Domicilio y retiro en sitio",
    "RETIRO EN SITIO": "Solo retiro en sitio",
    "FLETE A DOMICILIO": "Solo a domicilio",
}


def _cargar_productos(conn):
    """
    Devuelve todos los productos como diccionarios. A los combos de 2 pizzas
    se les añade "componentes": las dos pizzas individuales que incluyen.
    """
    productos = [dict(row) for row in conn.execute("SELECT * FROM pizzas ORDER BY id")]
    por_id = {p["id"]: p for p in productos}
    for p in productos:
        if p["tipo"] == "DUO":
            p["componentes"] = [
                por_id[i] for i in (p["pizza1_id"], p["pizza2_id"]) if i in por_id
            ]
    return productos


def _pizza_fields_from_form():
    tipo = request.form.get("tipo", "COMBO")
    nombre = request.form.get("nombre", "").strip()
    ingredientes = request.form.getlist("ingredientes")
    refresco = request.form.get("refresco", "")
    precio = float(request.form.get("precio", "0"))
    entrega = request.form.get("entrega", "AMBOS")
    pizza1_id = pizza2_id = None

    if tipo not in TIPOS_PRODUCTO:
        raise ValueError("Seleccione el tipo de producto (combo, combo de 2 pizzas o pizza).")
    if not nombre:
        raise ValueError("El nombre es obligatorio.")

    if tipo == "DUO":
        # El combo de 2 pizzas se arma con dos pizzas individuales diferentes.
        try:
            pizza1_id = int(request.form.get("pizza1_id", ""))
            pizza2_id = int(request.form.get("pizza2_id", ""))
        except ValueError:
            raise ValueError("Seleccione las dos pizzas del combo.")
        if pizza1_id == pizza2_id:
            raise ValueError("Las dos pizzas del combo deben ser diferentes.")
        conn = database.get_local_conn()
        try:
            validas = conn.execute(
                "SELECT COUNT(*) FROM pizzas WHERE tipo='PIZZA' AND id IN (?, ?)",
                (pizza1_id, pizza2_id),
            ).fetchone()[0]
        finally:
            conn.close()
        if validas != 2:
            raise ValueError("Las pizzas del combo deben ser pizzas individuales del menú.")
        ingredientes = []  # se toman de las dos pizzas que lo componen
    else:
        if len(ingredientes) < MIN_INGREDIENTES or len(ingredientes) > MAX_INGREDIENTES:
            raise ValueError(
                f"Debe seleccionar entre {MIN_INGREDIENTES} y {MAX_INGREDIENTES} ingredientes "
                "(el queso mozzarella ya viene incluido)."
            )
        if len(set(ingredientes)) != len(ingredientes) or not set(ingredientes).issubset(
            INGREDIENTES_DISPONIBLES
        ):
            raise ValueError("Seleccione ingredientes válidos y sin duplicados.")

    if tipo in TIPOS_COMBO:
        if refresco not in SABORES_SODA:
            raise ValueError("Seleccione la soda que incluye el combo.")
    else:
        refresco = None  # las pizzas individuales no incluyen soda
    if not math.isfinite(precio) or precio <= 0:
        raise ValueError("El precio debe ser un número mayor a cero.")
    if entrega not in ENTREGAS_PIZZA:
        raise ValueError("Seleccione una forma de entrega válida.")

    return {
        "tipo": tipo, "nombre": nombre, "ingredientes": ",".join(ingredientes),
        "refresco": refresco, "precio": precio, "entrega": entrega,
        "pizza1_id": pizza1_id, "pizza2_id": pizza2_id,
    }


def _contar_combos(excluir_id=None):
    conn = database.get_local_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM pizzas WHERE tipo IN ('COMBO', 'DUO') AND id IS NOT ?",
            (excluir_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def _combos_que_usan(pizza_id):
    """Nombres de los combos de 2 pizzas que incluyen esta pizza individual."""
    conn = database.get_local_conn()
    try:
        return [
            row["nombre"] for row in conn.execute(
                "SELECT nombre FROM pizzas WHERE tipo='DUO' AND ? IN (pizza1_id, pizza2_id)",
                (pizza_id,),
            )
        ]
    finally:
        conn.close()


def _fabrica_form_context(pizza, tipo_actual, entrega_actual, ingredientes_actuales):
    conn = database.get_local_conn()
    try:
        individuales = conn.execute(
            "SELECT id, nombre, precio FROM pizzas WHERE tipo='PIZZA' ORDER BY nombre"
        ).fetchall()
    finally:
        conn.close()
    return dict(
        pizza=pizza,
        ingredientes_disponibles=INGREDIENTES_DISPONIBLES,
        sabores_soda=SABORES_SODA,
        tipos_producto=TIPOS_PRODUCTO, tipo_actual=tipo_actual,
        entregas_pizza=ENTREGAS_PIZZA, entrega_actual=entrega_actual,
        ingredientes_actuales=ingredientes_actuales,
        pizzas_individuales=individuales,
        min_ing=MIN_INGREDIENTES, max_ing=MAX_INGREDIENTES,
    )


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
        productos = _cargar_productos(conn)
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar el menú: {e}", "danger")
        productos = []
    return render_template(
        "index.html",
        combos=[p for p in productos if p["tipo"] == "COMBO"],
        duos=[p for p in productos if p["tipo"] == "DUO"],
        individuales=[p for p in productos if p["tipo"] == "PIZZA"],
        entregas_pizza=ENTREGAS_PIZZA,
    )


# ----------------------------------------------------------------------
# FABRICA — CRUD de combos y pizzas (ingredientes, refrescos)
# ----------------------------------------------------------------------
@app.route("/fabrica")
def fabrica():
    try:
        conn = database.get_local_conn()
        pizzas = _cargar_productos(conn)
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al consultar pizzas: {e}", "danger")
        pizzas = []
    return render_template(
        "fabrica.html", pizzas=pizzas, entregas_pizza=ENTREGAS_PIZZA,
        tipos_producto=TIPOS_PRODUCTO,
        total_combos=sum(1 for p in pizzas if p["tipo"] in TIPOS_COMBO), min_combos=MIN_COMBOS,
    )


@app.route("/fabrica/nueva", methods=["GET", "POST"])
def fabrica_nueva():
    if request.method == "POST":
        try:
            datos = _pizza_fields_from_form()

            ok, last_id, error = database.replicate_write(
                "INSERT INTO pizzas (nombre, ingredientes, refresco, precio, entrega, tipo, "
                "pizza1_id, pizza2_id) VALUES (?,?,?,?,?,?,?,?)",
                (datos["nombre"], datos["ingredientes"], datos["refresco"], datos["precio"],
                 datos["entrega"], datos["tipo"], datos["pizza1_id"], datos["pizza2_id"]),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            producto = TIPOS_PRODUCTO[datos["tipo"]][0]
            flash(
                f"{producto} '{datos['nombre']}' creado correctamente (guardado y replicado).",
                "success",
            )
            return redirect(url_for("fabrica"))

        except (ValueError, RuntimeError, sqlite3.Error) as e:
            flash(f"Error: {e}", "danger")

    tipo_actual = request.form.get("tipo") or request.args.get("tipo", "COMBO")
    previo = None
    if request.method == "POST":
        previo = {
            "refresco": request.form.get("refresco"),
            "pizza1_id": request.form.get("pizza1_id", type=int),
            "pizza2_id": request.form.get("pizza2_id", type=int),
        }
    return render_template(
        "fabrica_form.html",
        **_fabrica_form_context(
            previo,
            tipo_actual if tipo_actual in TIPOS_PRODUCTO else "COMBO",
            request.form.get("entrega", "AMBOS"),
            request.form.getlist("ingredientes"),
        ),
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
            datos = _pizza_fields_from_form()
            if (
                pizza["tipo"] in TIPOS_COMBO and datos["tipo"] not in TIPOS_COMBO
                and _contar_combos(excluir_id=pizza_id) < MIN_COMBOS
            ):
                raise ValueError(
                    f"El catálogo debe conservar al menos {MIN_COMBOS} combos; "
                    "no se puede convertir este combo en pizza individual."
                )
            if pizza["tipo"] == "PIZZA" and datos["tipo"] != "PIZZA":
                usados = _combos_que_usan(pizza_id)
                if usados:
                    raise ValueError(
                        "Esta pizza forma parte de: " + ", ".join(usados)
                        + ". Debe seguir siendo una pizza individual."
                    )

            ok, _, error = database.replicate_write(
                "UPDATE pizzas SET nombre=?, ingredientes=?, refresco=?, precio=?, entrega=?, "
                "tipo=?, pizza1_id=?, pizza2_id=? WHERE id=?",
                (datos["nombre"], datos["ingredientes"], datos["refresco"], datos["precio"],
                 datos["entrega"], datos["tipo"], datos["pizza1_id"], datos["pizza2_id"],
                 pizza_id),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            flash(f"'{datos['nombre']}' actualizado correctamente.", "success")
            return redirect(url_for("fabrica"))

        except (ValueError, RuntimeError, sqlite3.Error) as e:
            flash(f"Error: {e}", "danger")

    ingredientes_actuales = pizza["ingredientes"].split(",") if pizza["ingredientes"] else []
    return render_template(
        "fabrica_form.html",
        **_fabrica_form_context(pizza, pizza["tipo"], pizza["entrega"], ingredientes_actuales),
    )


@app.route("/fabrica/eliminar/<int:pizza_id>", methods=["POST"])
def fabrica_eliminar(pizza_id):
    try:
        conn = database.get_local_conn()
        pizza = conn.execute("SELECT tipo FROM pizzas WHERE id=?", (pizza_id,)).fetchone()
        conn.close()
        combos_restantes = _contar_combos(excluir_id=pizza_id)
        usados = _combos_que_usan(pizza_id)
    except sqlite3.Error as e:
        flash(f"Error al comprobar el catálogo: {e}", "danger")
        return redirect(url_for("fabrica"))

    if pizza is not None and pizza["tipo"] in TIPOS_COMBO and combos_restantes < MIN_COMBOS:
        flash("El catálogo debe conservar al menos cinco combos.", "warning")
        return redirect(url_for("fabrica"))
    if usados:
        flash(
            "No se puede eliminar: esta pizza forma parte de " + ", ".join(usados) + ".",
            "warning",
        )
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
            cantidad = int(request.form.get("cantidad", 1))
            retiro_o_flete = request.form.get("retiro_o_flete", "RETIRO EN SITIO")
            direccion = " ".join(request.form.get("direccion", "").split())

            if not cliente or not correo_cliente:
                raise ValueError("Debe indicar nombre y correo del cliente.")
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo_cliente):
                raise ValueError("Indique un correo electrónico válido.")
            if cantidad < 1:
                raise ValueError("La cantidad debe ser al menos 1.")
            if retiro_o_flete not in ("RETIRO EN SITIO", "FLETE A DOMICILIO"):
                raise ValueError("Seleccione un método de entrega válido.")
            if retiro_o_flete == "FLETE A DOMICILIO":
                if len(direccion) < MIN_DIRECCION:
                    raise ValueError(
                        "Para el envío a domicilio indique la dirección completa "
                        "(barrio, calle, casa/apto y un punto de referencia)."
                    )
                if len(direccion) > MAX_DIRECCION:
                    raise ValueError(
                        f"La dirección no puede superar {MAX_DIRECCION} caracteres."
                    )
            else:
                direccion = None

            conn = database.get_local_conn()
            pizza = conn.execute("SELECT * FROM pizzas WHERE id=?", (pizza_id,)).fetchone()
            conn.close()
            if pizza is None:
                raise ValueError("La pizza seleccionada no existe.")
            if pizza["tipo"] in TIPOS_COMBO:
                sodas_cantidad, sodas_tamano, sodas_detalle = _sodas_from_form()
            else:
                # Solo los combos incluyen sodas.
                sodas_cantidad, sodas_tamano, sodas_detalle = 0, None, []
            refresco = _describir_sodas(sodas_cantidad, sodas_tamano, sodas_detalle)
            if pizza["entrega"] != "AMBOS" and retiro_o_flete != pizza["entrega"]:
                raise ValueError(
                    f"La pizza '{pizza['nombre']}' solo está disponible para "
                    f"{ENTREGAS_PIZZA[pizza['entrega']].removeprefix('Solo ')}."
                )

            total = round(pizza["precio"] * cantidad, 2)
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ok, pedido_id, error = database.replicate_write(
                "INSERT INTO pedidos (cliente, correo_cliente, pizza_id, refresco, "
                "refresco_cantidad, refresco_tamano, "
                "cantidad, total, estado, retiro_o_flete, direccion, fecha) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (cliente, correo_cliente, pizza_id, refresco,
                 sodas_cantidad, sodas_tamano, cantidad, total,
                 "CONFIRMADO", retiro_o_flete, direccion, fecha),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")

            pedido_dict = {
                "id": pedido_id, "cliente": cliente, "correo_cliente": correo_cliente,
                "pizza_nombre": pizza["nombre"], "refresco": refresco, "cantidad": cantidad,
                "refresco_cantidad": sodas_cantidad,
                "refresco_tamano": TAMANOS_SODA.get(sodas_tamano),
                "refrescos_detalle": [
                    {"sabor": sabor, "cantidad": n} for sabor, n in sodas_detalle
                ],
                "total": total, "retiro_o_flete": retiro_o_flete,
                "direccion": direccion, "estado": "CONFIRMADO", "fecha": fecha,
            }
            # El JSON del pedido queda registrado, pero solo se envía por correo
            # (junto con el pago) cuando el pedido se paga.
            _, ruta_json = generar_json_pedido(pedido_dict)
            if not ruta_json:
                flash("No se pudo crear el archivo JSON del pedido.", "warning")
            flash(
                "Recibirás la confirmación en JSON por correo cuando se realice el pago.",
                "success",
            )

            flash(f"Pedido #{pedido_id} confirmado y guardado en ambas bases.", "success")
            return redirect(url_for("pedidos"))

        except (ValueError, RuntimeError, TypeError) as e:
            flash(f"Error al crear el pedido: {e}", "danger")

    return render_template(
        "pedidos.html", pizzas=pizzas, pedidos=lista_pedidos, entregas_pizza=ENTREGAS_PIZZA,
        sabores_soda=SABORES_SODA, tamanos_soda=TAMANOS_SODA, max_sodas=MAX_SODAS,
        sabores_elegidos=request.form.getlist("refrescos") if request.method == "POST" else [],
        selected_pizza_id=selected_pizza_id,
        form=request.form if request.method == "POST" else {},
        min_direccion=MIN_DIRECCION, max_direccion=MAX_DIRECCION,
    )


# ----------------------------------------------------------------------
# PAGOS — cobro con Yappy Comercial:
#   1. Se elige el pedido y se genera un cobro con código único.
#   2. El cliente escanea el QR o envía el monto al número del comercio
#      escribiendo el código en el mensaje.
#   3. Al confirmarse, se registra el pago, se actualiza el pedido y se
#      muestra la confirmación (la pantalla de caja se actualiza sola).
# ----------------------------------------------------------------------
ESTADOS_PAGADOS = ("PAGADO", "PAGADO - DESPACHAR (FLETE)")


def _obtener_pedido(conn, pedido_id):
    return conn.execute(
        "SELECT pedidos.*, pizzas.nombre AS pizza_nombre FROM pedidos "
        "JOIN pizzas ON pedidos.pizza_id = pizzas.id WHERE pedidos.id=?",
        (pedido_id,),
    ).fetchone()


def _obtener_cobro(codigo):
    conn = database.get_local_conn()
    try:
        cobro = conn.execute(
            "SELECT * FROM cobros_yappy WHERE codigo=?", (codigo,)
        ).fetchone()
        pedido = _obtener_pedido(conn, cobro["pedido_id"]) if cobro else None
        return cobro, pedido
    finally:
        conn.close()


def _url_publica(endpoint, **values):
    """
    URL absoluta para el QR. Si la app se abrió como localhost, se usa la IP
    de la red local para que un celular en la misma red Wi-Fi pueda abrirla.
    """
    url = url_for(endpoint, _external=True, **values)
    host = request.host.split(":")[0]
    if host in ("127.0.0.1", "localhost"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))
                ip_lan = s.getsockname()[0]
            url = url.replace(f"//{host}", f"//{ip_lan}", 1)
        except OSError:
            pass
    return url


def _confirmar_cobro(cobro, pedido, referencia):
    """Registra el pago del cobro en ambas bases y envía las confirmaciones."""
    if cobro["estado"] == "PAGADO" or pedido["estado"] in ESTADOS_PAGADOS:
        raise ValueError("Este pedido ya fue pagado.")

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nuevo_estado = (
        "PAGADO" if pedido["retiro_o_flete"] == "RETIRO EN SITIO"
        else "PAGADO - DESPACHAR (FLETE)"
    )
    ok, operation_ids, error = database.replicate_transaction(
        [
            (
                "INSERT INTO pagos (pedido_id, metodo, monto, estado, fecha) "
                "VALUES (?,?,?,?,?)",
                (pedido["id"], "YAPPY COMERCIAL", cobro["monto"], "CONFIRMADO", fecha),
            ),
            ("UPDATE pedidos SET estado=? WHERE id=?", (nuevo_estado, pedido["id"])),
            (
                "UPDATE cobros_yappy SET estado='PAGADO', referencia=?, fecha_pago=? "
                "WHERE id=?",
                (referencia, fecha, cobro["id"]),
            ),
        ]
    )
    if not ok:
        if "UNIQUE" in (error or ""):
            raise ValueError("Este pedido ya tiene un pago registrado.")
        raise RuntimeError(error)
    if error:
        flash(error, "warning")

    pago_dict = {
        "id": operation_ids[0], "pedido_id": pedido["id"],
        "metodo": f"YAPPY COMERCIAL ({referencia}, cobro {cobro['codigo']})",
        "monto": cobro["monto"], "estado": "CONFIRMADO", "fecha": fecha,
    }
    pedido_dict = {
        "cliente": pedido["cliente"], "correo_cliente": pedido["correo_cliente"],
        "pizza_nombre": pedido["pizza_nombre"], "cantidad": pedido["cantidad"],
        "refresco": pedido["refresco"], "total": pedido["total"],
        "retiro_o_flete": pedido["retiro_o_flete"], "direccion": pedido["direccion"],
        "fecha": pedido["fecha"],
    }
    json_data, ruta_json = generar_json_pago(pago_dict, pedido_dict)
    _notify_json_recipients(
        (pedido["correo_cliente"], EMPRESA_CORREO),
        f"Confirmación de pago - Pedido #{pedido['id']}",
        json_data, ruta_json,
    )


@app.route("/pagos", methods=["GET", "POST"])
def pagos():
    if request.method == "POST":
        try:
            pedido_id = int(request.form.get("pedido_id"))

            conn = database.get_local_conn()
            try:
                pedido = _obtener_pedido(conn, pedido_id)
                if pedido is None:
                    raise ValueError("El pedido indicado no existe.")
                if pedido["estado"] in ESTADOS_PAGADOS or conn.execute(
                    "SELECT 1 FROM pagos WHERE pedido_id=?", (pedido_id,)
                ).fetchone():
                    raise ValueError("Este pedido ya fue pagado.")
                cobro = conn.execute(
                    "SELECT codigo FROM cobros_yappy "
                    "WHERE pedido_id=? AND estado='PENDIENTE'",
                    (pedido_id,),
                ).fetchone()
            finally:
                conn.close()

            # Si el pedido ya tenía un cobro pendiente, se reutiliza el mismo código.
            if cobro:
                return redirect(url_for("cobro_yappy", codigo=cobro["codigo"]))

            codigo = generar_codigo_cobro()
            ok, _, error = database.replicate_write(
                "INSERT INTO cobros_yappy (pedido_id, codigo, monto, estado, fecha) "
                "VALUES (?,?,?,?,?)",
                (pedido_id, codigo, pedido["total"], "PENDIENTE",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            if not ok:
                raise RuntimeError(error)
            if error:
                flash(error, "warning")
            return redirect(url_for("cobro_yappy", codigo=codigo))

        except (ValueError, RuntimeError, TypeError, sqlite3.Error) as e:
            flash(f"Error al generar el cobro: {e}", "danger")

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
            "SELECT pagos.*, pedidos.cliente, pedidos.retiro_o_flete, pedidos.direccion, "
            "cobros_yappy.codigo, cobros_yappy.referencia FROM pagos "
            "JOIN pedidos ON pagos.pedido_id = pedidos.id "
            "LEFT JOIN cobros_yappy ON cobros_yappy.pedido_id = pagos.pedido_id "
            "AND cobros_yappy.estado = 'PAGADO' "
            "ORDER BY pagos.id DESC"
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        flash(f"Error al cargar datos: {e}", "danger")
        pedidos_pendientes, historial_pagos = [], []

    return render_template(
        "pagos.html", pedidos=pedidos_pendientes, pagos=historial_pagos
    )


@app.route("/pagos/yappy/<codigo>", methods=["GET", "POST"])
def cobro_yappy(codigo):
    """Pantalla de caja: QR, número Yappy y confirmación del pago."""
    try:
        cobro, pedido = _obtener_cobro(codigo)
    except sqlite3.Error as e:
        flash(f"Error al cargar el cobro: {e}", "danger")
        return redirect(url_for("pagos"))
    if cobro is None:
        flash("El cobro Yappy indicado no existe.", "warning")
        return redirect(url_for("pagos"))

    if request.method == "POST":
        # Pago enviado al número: el cajero verifica el código en el mensaje
        # recibido en Yappy y anota el número de transacción.
        try:
            referencia = request.form.get("referencia", "").strip().upper()
            if not re.fullmatch(r"[A-Z0-9-]{4,30}", referencia):
                raise ValueError(
                    "Indique el número de transacción Yappy (4 a 30 letras, números o guiones)."
                )
            _confirmar_cobro(cobro, pedido, referencia)
            flash(f"Pago del pedido #{pedido['id']} confirmado (ref. {referencia}).", "success")
            return redirect(url_for("cobro_yappy", codigo=codigo))
        except (ValueError, RuntimeError, sqlite3.Error) as e:
            flash(f"Error al confirmar el pago: {e}", "danger")

    url_pago = _url_publica("yappy_pagar", codigo=codigo)
    return render_template(
        "cobro_yappy.html", cobro=cobro, pedido=pedido,
        qr=qr_svg(url_pago), url_pago=url_pago,
        yappy_telefono=YAPPY_TELEFONO, yappy_directorio=YAPPY_DIRECTORIO,
    )


@app.route("/pagos/yappy/<codigo>/estado")
def cobro_yappy_estado(codigo):
    """Consulta ligera que usa la pantalla de caja para detectar el pago."""
    try:
        cobro, _ = _obtener_cobro(codigo)
    except sqlite3.Error as e:
        return jsonify(error=str(e)), 500
    if cobro is None:
        return jsonify(error="Cobro no encontrado"), 404
    return jsonify(
        estado=cobro["estado"], referencia=cobro["referencia"],
        fecha_pago=cobro["fecha_pago"],
    )


@app.route("/yappy/pagar/<codigo>", methods=["GET", "POST"])
def yappy_pagar(codigo):
    """
    Página que abre el celular al escanear el QR. Simula la app de Yappy:
    muestra el comercio y el monto, y al pulsar «Pagar» confirma el cobro.
    En producción este paso lo haría la app real de Yappy (botón de pago / webhook).
    """
    try:
        cobro, pedido = _obtener_cobro(codigo)
    except sqlite3.Error as e:
        flash(f"Error al cargar el cobro: {e}", "danger")
        cobro = pedido = None
    if cobro is None:
        return render_template("yappy_pagar.html", cobro=None), 404

    if request.method == "POST" and cobro["estado"] == "PENDIENTE":
        try:
            ok_pago, referencia, error_pago = simular_pago_yappy(cobro["monto"])
            if not ok_pago:
                raise RuntimeError(f"No se pudo procesar el pago con Yappy: {error_pago}")
            _confirmar_cobro(cobro, pedido, referencia)
            return redirect(url_for("yappy_pagar", codigo=codigo))
        except (ValueError, RuntimeError, sqlite3.Error) as e:
            flash(f"Error al procesar el pago: {e}", "danger")

    return render_template(
        "yappy_pagar.html", cobro=cobro, pedido=pedido,
        yappy_directorio=YAPPY_DIRECTORIO,
    )


if __name__ == "__main__":
    database.init_db()
    # host="0.0.0.0" permite exponerlo en la red LAN / detrás de NGINX
    app.run(host="0.0.0.0", port=5000, debug=True)
