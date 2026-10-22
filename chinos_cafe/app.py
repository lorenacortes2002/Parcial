# -*- coding: utf-8 -*-
"""
==================================================================
  CHINOS CAFE S.A.  -  Sistema de pedidos de combos de PIZZA
  Examen Parcial 2 - Ingenieria Web (UTP) - Prof. Napoleon Ibarra
  I PARTE: Caso de Estudio (Python + Flask, CRUD)
------------------------------------------------------------------
  Secciones:
    - FABRICA : CRUD de pizzas (ingredientes 2..10, refresco, extra)
    - PEDIDOS : arma combo, guarda en 2 DB (replicacion), JSON + correo
    - PAGOS   : YAPPY Comercial, flete, JSON + correo de confirmacion
  Toda operacion esta protegida con try/except.
==================================================================
"""

import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # carga el .env ANTES de importar db (que lee las rutas)

from flask import (
    Flask, render_template, request, redirect, url_for, flash
)

import db
import correo

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "clave-por-defecto")

# ---- Catalogos para los LISTBOX / COMBO BOX ----
INGREDIENTES = [
    "Queso mozzarella", "Pepperoni", "Jamon", "Champinones", "Pina",
    "Tocino", "Pollo BBQ", "Cebolla", "Pimiento", "Aceitunas",
    "Tomate", "Albahaca", "Salchicha", "Maiz", "Chorizo",
]
TAMANOS = ["Personal", "Mediana", "Familiar"]
REFRESCOS = ["Coca-Cola", "Pepsi", "Sprite", "Fanta", "Agua", "Te frio", "Sin refresco"]
EXTRAS = ["Ninguno", "Pan de ajo", "Alitas", "Papas fritas", "Salsa extra", "Postre"]

COSTO_FLETE = 3.50  # B/. flete sugerido si no retira en sitio


# ------------------------------------------------------------------
#  SEMILLA: minimo 5 combos de pizza
# ------------------------------------------------------------------
def sembrar_combos():
    """Inserta 5 combos iniciales si la tabla pizzas esta vacia."""
    try:
        existentes = db.consultar_uno("SELECT COUNT(*) AS n FROM pizzas")
        if existentes and existentes["n"] > 0:
            return
        combos = [
            ("Combo Pepperoni Clasico", "Familiar",
             "Queso mozzarella, Pepperoni, Tomate", "Coca-Cola", "Pan de ajo", 12.99),
            ("Combo Hawaiana", "Mediana",
             "Queso mozzarella, Jamon, Pina", "Pepsi", "Papas fritas", 10.50),
            ("Combo Suprema", "Familiar",
             "Queso mozzarella, Pepperoni, Champinones, Pimiento, Cebolla, Aceitunas",
             "Sprite", "Alitas", 15.75),
            ("Combo Pollo BBQ", "Mediana",
             "Queso mozzarella, Pollo BBQ, Cebolla, Maiz", "Fanta", "Salsa extra", 11.99),
            ("Combo Vegetariana", "Personal",
             "Queso mozzarella, Champinones, Pimiento, Cebolla, Tomate, Albahaca",
             "Agua", "Ninguno", 8.99),
            ("Combo Carnivora", "Familiar",
             "Queso mozzarella, Pepperoni, Tocino, Salchicha, Chorizo, Jamon",
             "Coca-Cola", "Postre", 16.50),
        ]
        for c in combos:
            db.escribir(
                """INSERT INTO pizzas
                   (nombre, tamano, ingredientes, refresco, item_adicional, precio)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                c,
            )
        print("[OK] 6 combos de pizza sembrados en ambas DB.")
    except Exception as e:
        print("[ERROR sembrar_combos] %s" % e)


# ==================================================================
#  INICIO / PANEL
# ==================================================================
@app.route("/")
def inicio():
    try:
        pizzas = db.consultar("SELECT * FROM pizzas ORDER BY id")
        pedidos = db.consultar("SELECT * FROM pedidos ORDER BY id DESC")
        pagos = db.consultar("SELECT * FROM pagos ORDER BY id DESC")
        return render_template(
            "inicio.html",
            pizzas=pizzas, pedidos=pedidos, pagos=pagos,
            conteos=db.conteos(),
        )
    except Exception as e:
        flash("Error al cargar el panel: %s" % e, "error")
        return render_template("inicio.html", pizzas=[], pedidos=[], pagos=[],
                               conteos=db.conteos())


# ==================================================================
#  SECCION 1: FABRICA  (CRUD de pizzas)
# ==================================================================
@app.route("/fabrica")
def fabrica():
    try:
        pizzas = db.consultar("SELECT * FROM pizzas ORDER BY id")
    except Exception as e:
        flash("Error al listar pizzas: %s" % e, "error")
        pizzas = []
    return render_template(
        "fabrica.html",
        pizzas=pizzas, ingredientes=INGREDIENTES, tamanos=TAMANOS,
        refrescos=REFRESCOS, extras=EXTRAS,
    )


@app.route("/fabrica/crear", methods=["POST"])
def fabrica_crear():
    try:
        nombre = request.form.get("nombre", "").strip()
        tamano = request.form.get("tamano", "").strip()
        # El LISTBOX multiple devuelve una lista de ingredientes
        seleccion = request.form.getlist("ingredientes")
        refresco = request.form.get("refresco", "").strip()
        extra = request.form.get("item_adicional", "").strip()
        precio_txt = request.form.get("precio", "0").strip()

        # ---- Validaciones (control de campos) ----
        if not nombre:
            raise ValueError("El nombre de la pizza es obligatorio.")
        if tamano not in TAMANOS:
            raise ValueError("Debe seleccionar un tamano valido.")
        if len(seleccion) < 2:
            raise ValueError("Debe seleccionar MINIMO 2 ingredientes.")
        if len(seleccion) > 10:
            raise ValueError("Debe seleccionar MAXIMO 10 ingredientes.")
        try:
            precio = round(float(precio_txt), 2)
        except ValueError:
            raise ValueError("El precio debe ser un numero (ej: 12.99).")
        if precio <= 0:
            raise ValueError("El precio debe ser mayor que 0.")

        ingredientes = ", ".join(seleccion)
        db.escribir(
            """INSERT INTO pizzas
               (nombre, tamano, ingredientes, refresco, item_adicional, precio)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (nombre, tamano, ingredientes, refresco, extra, precio),
        )
        flash("Pizza '%s' registrada en ambas DB (primaria + replica)." % nombre, "ok")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash("Error inesperado al crear la pizza: %s" % e, "error")
    return redirect(url_for("fabrica"))


@app.route("/fabrica/editar/<int:pizza_id>", methods=["GET", "POST"])
def fabrica_editar(pizza_id):
    try:
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            tamano = request.form.get("tamano", "").strip()
            seleccion = request.form.getlist("ingredientes")
            refresco = request.form.get("refresco", "").strip()
            extra = request.form.get("item_adicional", "").strip()
            precio = round(float(request.form.get("precio", "0")), 2)

            if not nombre:
                raise ValueError("El nombre es obligatorio.")
            if not (2 <= len(seleccion) <= 10):
                raise ValueError("Los ingredientes deben ser entre 2 y 10.")
            if precio <= 0:
                raise ValueError("El precio debe ser mayor que 0.")

            db.escribir(
                """UPDATE pizzas SET nombre=?, tamano=?, ingredientes=?,
                   refresco=?, item_adicional=?, precio=? WHERE id=?""",
                (nombre, tamano, ", ".join(seleccion), refresco, extra, precio, pizza_id),
            )
            flash("Pizza actualizada en ambas DB.", "ok")
            return redirect(url_for("fabrica"))

        pizza = db.consultar_uno("SELECT * FROM pizzas WHERE id=?", (pizza_id,))
        if not pizza:
            flash("La pizza no existe.", "error")
            return redirect(url_for("fabrica"))
        seleccionados = [i.strip() for i in pizza["ingredientes"].split(",")]
        return render_template(
            "editar.html", pizza=pizza, seleccionados=seleccionados,
            ingredientes=INGREDIENTES, tamanos=TAMANOS,
            refrescos=REFRESCOS, extras=EXTRAS,
        )
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("fabrica"))
    except Exception as e:
        flash("Error al editar: %s" % e, "error")
        return redirect(url_for("fabrica"))


@app.route("/fabrica/eliminar/<int:pizza_id>", methods=["POST"])
def fabrica_eliminar(pizza_id):
    try:
        db.escribir("DELETE FROM pizzas WHERE id=?", (pizza_id,))
        flash("Pizza eliminada de ambas DB.", "ok")
    except Exception as e:
        flash("Error al eliminar: %s" % e, "error")
    return redirect(url_for("fabrica"))


# ==================================================================
#  SECCION 2: PEDIDOS
# ==================================================================
@app.route("/pedidos")
def pedidos():
    try:
        pizzas = db.consultar("SELECT * FROM pizzas ORDER BY nombre")
        lista = db.consultar("SELECT * FROM pedidos ORDER BY id DESC")
    except Exception as e:
        flash("Error al cargar pedidos: %s" % e, "error")
        pizzas, lista = [], []
    return render_template(
        "pedidos.html", pizzas=pizzas, pedidos=lista, refrescos=REFRESCOS,
    )


@app.route("/pedidos/crear", methods=["POST"])
def pedidos_crear():
    try:
        cliente = request.form.get("cliente_nombre", "").strip()
        correo_cli = request.form.get("cliente_correo", "").strip()
        pizza_id = request.form.get("pizza_id", "").strip()
        refresco = request.form.get("refresco", "").strip()
        notas = request.form.get("notas", "").strip()
        cant_txt = request.form.get("cantidad", "1").strip()

        # ---- Validaciones ----
        if not cliente:
            raise ValueError("El nombre del cliente es obligatorio.")
        if "@" not in correo_cli or "." not in correo_cli:
            raise ValueError("Correo del cliente no valido.")
        if not pizza_id:
            raise ValueError("Debe seleccionar un combo de pizza.")
        try:
            cantidad = int(cant_txt)
        except ValueError:
            raise ValueError("La cantidad debe ser un numero entero.")
        if cantidad < 1:
            raise ValueError("La cantidad minima es 1.")

        pizza = db.consultar_uno("SELECT * FROM pizzas WHERE id=?", (pizza_id,))
        if not pizza:
            raise ValueError("El combo seleccionado no existe.")

        subtotal = round(pizza["precio"] * cantidad, 2)
        total = subtotal  # el flete se decide en PAGOS
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # ---- Guardar en AMBAS DB (replicacion) ----
        pedido_id = db.escribir(
            """INSERT INTO pedidos
               (cliente_nombre, cliente_correo, pizza_id, pizza_nombre, cantidad,
                refresco, notas, subtotal, flete, total, estado, fecha)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'REGISTRADO', ?)""",
            (cliente, correo_cli, pizza["id"], pizza["nombre"], cantidad,
             refresco, notas, subtotal, total, fecha),
        )

        # ---- Archivo JSON de confirmacion del pedido ----
        datos = {
            "tipo": "CONFIRMACION_DE_PEDIDO",
            "empresa": "CHINOS CAFE S.A.",
            "pedido_id": pedido_id,
            "fecha": fecha,
            "cliente": {"nombre": cliente, "correo": correo_cli},
            "combo": {
                "pizza": pizza["nombre"],
                "tamano": pizza["tamano"],
                "ingredientes": pizza["ingredientes"],
                "refresco": refresco or pizza["refresco"],
                "extra": pizza["item_adicional"],
            },
            "cantidad": cantidad,
            "notas": notas,
            "subtotal": subtotal,
            "total": total,
            "estado": "REGISTRADO",
        }
        ruta_json = correo.guardar_json("pedido", datos)

        # ---- Correo a empresa / cliente / operario ----
        cuerpo = (
            "CHINOS CAFE S.A. - Confirmacion de pedido\n"
            "Pedido #%s   Fecha: %s\n\n"
            "Cliente: %s (%s)\n"
            "Combo: %s (%s)\n"
            "Ingredientes: %s\n"
            "Refresco: %s   Cantidad: %s\n"
            "Notas: %s\n\n"
            "SUBTOTAL: B/. %.2f\nTOTAL: B/. %.2f\n"
            % (pedido_id, fecha, cliente, correo_cli, pizza["nombre"],
               pizza["tamano"], pizza["ingredientes"], refresco or pizza["refresco"],
               cantidad, notas or "-", subtotal, total)
        )
        destinos = [
            os.getenv("CORREO_EMPRESA", ""),
            os.getenv("CORREO_OPERARIO", ""),
            correo_cli,
        ]
        ok, msg = correo.enviar_correo(
            "Pedido #%s - CHINOS CAFE S.A." % pedido_id, cuerpo, destinos, ruta_json
        )

        flash("Pedido #%s registrado en ambas DB. JSON: %s" % (pedido_id, ruta_json), "ok")
        flash(("Correo: " + msg), "ok" if ok else "aviso")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash("Error al crear el pedido: %s" % e, "error")
    return redirect(url_for("pedidos"))


# ==================================================================
#  SECCION 3: PAGOS  (YAPPY Comercial)
# ==================================================================
@app.route("/pagos")
def pagos():
    try:
        # Pedidos que aun no tienen pago
        pendientes = db.consultar(
            """SELECT * FROM pedidos
               WHERE id NOT IN (SELECT pedido_id FROM pagos)
               ORDER BY id DESC"""
        )
        lista = db.consultar("SELECT * FROM pagos ORDER BY id DESC")
    except Exception as e:
        flash("Error al cargar pagos: %s" % e, "error")
        pendientes, lista = [], []
    return render_template(
        "pagos.html", pendientes=pendientes, pagos=lista, flete=COSTO_FLETE,
    )


@app.route("/pagos/crear", methods=["POST"])
def pagos_crear():
    try:
        pedido_id = request.form.get("pedido_id", "").strip()
        referencia = request.form.get("referencia", "").strip()
        entrega = request.form.get("entrega", "").strip()

        if not pedido_id:
            raise ValueError("Debe seleccionar un pedido a pagar.")
        if not referencia:
            raise ValueError("Ingrese la referencia / captura de YAPPY Comercial.")
        if entrega not in ("RETIRO EN SITIO", "FLETE A DOMICILIO"):
            raise ValueError("Seleccione el tipo de entrega.")

        pedido = db.consultar_uno("SELECT * FROM pedidos WHERE id=?", (pedido_id,))
        if not pedido:
            raise ValueError("El pedido no existe.")

        # Flete solo si NO pasa a retiro en sitio
        flete = COSTO_FLETE if entrega == "FLETE A DOMICILIO" else 0.0
        monto = round(pedido["subtotal"] + flete, 2)
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # ---- Guardar pago en AMBAS DB ----
        pago_id = db.escribir(
            """INSERT INTO pagos
               (pedido_id, metodo, referencia, monto, entrega, estado, fecha)
               VALUES (?, 'YAPPY COMERCIAL', ?, ?, ?, 'PAGADO', ?)""",
            (pedido_id, referencia, monto, entrega, fecha),
        )
        # ---- Actualizar pedido: total con flete + estado despacho ----
        db.escribir(
            "UPDATE pedidos SET flete=?, total=?, estado=? WHERE id=?",
            (flete, monto, "PAGADO - POR DESPACHAR", pedido_id),
        )

        # ---- JSON de confirmacion de pago ----
        datos = {
            "tipo": "CONFIRMACION_DE_PAGO",
            "empresa": "CHINOS CAFE S.A.",
            "pago_id": pago_id,
            "pedido_id": int(pedido_id),
            "fecha": fecha,
            "metodo": "YAPPY COMERCIAL",
            "referencia": referencia,
            "cliente": pedido["cliente_nombre"],
            "combo": pedido["pizza_nombre"],
            "subtotal": pedido["subtotal"],
            "flete": flete,
            "monto_total": monto,
            "entrega": entrega,
            "estado": "PAGADO - POR DESPACHAR",
        }
        ruta_json = correo.guardar_json("pago", datos)

        cuerpo = (
            "CHINOS CAFE S.A. - Confirmacion de PAGO (YAPPY Comercial)\n"
            "Pago #%s  Pedido #%s   Fecha: %s\n\n"
            "Cliente: %s\nCombo: %s\n"
            "Referencia Yappy: %s\n"
            "Subtotal: B/. %.2f\nFlete: B/. %.2f\nTOTAL PAGADO: B/. %.2f\n"
            "Entrega: %s\nEstado: PAGADO - POR DESPACHAR\n"
            % (pago_id, pedido_id, fecha, pedido["cliente_nombre"],
               pedido["pizza_nombre"], referencia, pedido["subtotal"],
               flete, monto, entrega)
        )
        destinos = [
            os.getenv("CORREO_EMPRESA", ""),
            os.getenv("CORREO_OPERARIO", ""),
            pedido["cliente_correo"],
        ]
        ok, msg = correo.enviar_correo(
            "Pago #%s Pedido #%s - CHINOS CAFE S.A." % (pago_id, pedido_id),
            cuerpo, destinos, ruta_json,
        )

        flash("Pago #%s registrado. Pedido por despachar. JSON: %s" % (pago_id, ruta_json), "ok")
        flash(("Correo: " + msg), "ok" if ok else "aviso")
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash("Error al registrar el pago: %s" % e, "error")
    return redirect(url_for("pagos"))


# ==================================================================
#  REPLICACION manual Primaria -> Replica
# ==================================================================
@app.route("/replicar", methods=["POST"])
def replicar():
    try:
        resumen = db.replicar_total()
        flash("Replicacion completa Primaria -> Replica: %s" % resumen, "ok")
    except Exception as e:
        flash("Error en la replicacion: %s" % e, "error")
    return redirect(url_for("inicio"))


# ==================================================================
#  ARRANQUE
# ==================================================================
if __name__ == "__main__":
    db.init_db()       # crea esquema en ambas DB
    sembrar_combos()   # 6 combos iniciales (>= 5 requeridos)
    # host 0.0.0.0 para poder servirlo detras de NGINX (Parte II/III)
    app.run(host="0.0.0.0", port=5000, debug=True)
