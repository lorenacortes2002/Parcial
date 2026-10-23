import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as webapp
import database
import utils


class ProjectRequirementsTests(unittest.TestCase):
    def setUp(self):
        # ignore_cleanup_errors evita fallos en Windows si SQLite mantiene el
        # archivo bloqueado unos milisegundos tras cerrar la conexión.
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.temp_dir.name)
        self.local_path = root / "local.sqlite3"
        self.replica_path = root / "replica.sqlite3"

        # Estas pruebas usan SQLite aunque el .env local configure MariaDB.
        motor = mock.patch.dict("os.environ", {"DB_MOTOR": "sqlite"})
        motor.start()
        self.addCleanup(motor.stop)

        for name, value in (
            ("DB_LOCAL_PATH", str(self.local_path)),
            ("DB_REPLICA_PATH", str(self.replica_path)),
        ):
            patcher = mock.patch.object(database, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        database.init_db()
        self.mail = mock.patch.object(webapp, "enviar_correo", return_value=(True, None))
        self.mail_mock = self.mail.start()
        self.addCleanup(self.mail.stop)
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _rows(self, path, query, params=()):
        # Cerramos explícitamente la conexión: en sqlite3 el bloque "with"
        # solo confirma la transacción, no cierra el archivo (clave en Windows).
        conn = sqlite3.connect(path)
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def _order_json(self):
        """JSON del primer pedido, tal como quedó guardado en la base de datos."""
        return json.loads(
            self._rows(self.local_path, "SELECT json_pedido FROM pedidos ORDER BY id")[0][0]
        )

    def _delete_duo_combos(self):
        """Deja solo los cinco combos de una pizza para probar el mínimo."""
        for (duo_id,) in self._rows(self.local_path, "SELECT id FROM pizzas WHERE tipo='DUO'"):
            self.client.post(f"/fabrica/eliminar/{duo_id}")

    def test_startup_has_five_catalog_items_in_both_databases(self):
        for path in (self.local_path, self.replica_path):
            rows = self._rows(path, "SELECT id, nombre FROM pizzas ORDER BY id")
            self.assertGreaterEqual(len(rows), 5)
        self.assertEqual(
            self._rows(self.local_path, "SELECT id, nombre FROM pizzas ORDER BY id"),
            self._rows(self.replica_path, "SELECT id, nombre FROM pizzas ORDER BY id"),
        )

    def test_crud_validates_fields_and_keeps_catalog_replicated(self):
        initial_count = self._rows(self.local_path, "SELECT COUNT(*) FROM pizzas")[0][0]
        invalid = self.client.post(
            "/fabrica/nueva",
            data={
                "nombre": "Pizza inválida",
                "ingredientes": ["pepperoni", "ingrediente inventado"],
                "refresco": "Coca-Cola",
                "precio": "8.50",
            },
        )
        self.assertIn(b"Seleccione ingredientes v", invalid.data)

        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT COUNT(*) FROM pizzas")[0][0], initial_count
            )

        created = self.client.post(
            "/fabrica/nueva",
            data={
                "nombre": "Pizza de prueba",
                "ingredientes": ["pepperoni", "jamón"],
                "refresco": "Sprite",
                "precio": "9.25",
            },
        )
        self.assertEqual(created.status_code, 302)
        pizza = self._rows(
            self.local_path,
            "SELECT id, nombre FROM pizzas WHERE nombre=?",
            ("Pizza de prueba",),
        )[0]
        self.assertEqual(
            self._rows(
                self.replica_path,
                "SELECT id, nombre FROM pizzas WHERE nombre=?",
                ("Pizza de prueba",),
            )[0],
            pizza,
        )
        pizza_id = pizza[0]

        edited = self.client.post(
            f"/fabrica/editar/{pizza_id}",
            data={
                "nombre": "Pizza editada",
                "ingredientes": ["chorizo"],
                "refresco": "Agua",
                "precio": "10.00",
            },
        )
        self.assertEqual(edited.status_code, 302)
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(
                    path, "SELECT nombre, precio FROM pizzas WHERE id=?", (pizza_id,)
                )[0],
                ("Pizza editada", 10.0),
            )

        deleted = self.client.post(f"/fabrica/eliminar/{pizza_id}")
        self.assertEqual(deleted.status_code, 302)
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT COUNT(*) FROM pizzas")[0][0], initial_count
            )
            self.assertEqual(
                self._rows(path, "SELECT id FROM pizzas WHERE id=?", (pizza_id,)), []
            )

        self._delete_duo_combos()
        protected = self.client.post("/fabrica/eliminar/1", follow_redirects=True)
        self.assertIn(b"al menos cinco combos", protected.data)

    def test_order_and_yappy_payment_are_replicated_and_not_repeated(self):
        response = self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente de prueba",
                "correo_cliente": "cliente@example.com",
                "pizza_id": "1",
                "refrescos": ["Coca-Cola"],
                "refresco_cantidad": "1",
                "refresco_tamano": "LATA 12 OZ",
                "cantidad": "2",
                "retiro_o_flete": "FLETE A DOMICILIO",
                "direccion": "David, Barrio Bolívar, calle 3, casa 24",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Pedido #", response.data)
        # El JSON solo se envía por correo después del pago.
        self.assertEqual(self.mail_mock.call_count, 0)
        # Al confirmar el pedido su JSON ya queda guardado en ambas bases.
        for path in (self.local_path, self.replica_path):
            stored = self._rows(path, "SELECT json_pedido FROM pedidos")[0][0]
            # 2 × 7.50 = 15.00 + flete a domicilio (5%) 0.75 = 15.75
            stored_json = json.loads(stored)
            self.assertEqual(
                (stored_json["subtotal"], stored_json["flete"], stored_json["total"]),
                (15.0, 0.75, 15.75),
            )

        order = self._rows(
            self.local_path,
            "SELECT id, total, estado, retiro_o_flete, direccion FROM pedidos",
        )[0]
        self.assertEqual(
            order[1:],
            (15.75, "CONFIRMADO", "FLETE A DOMICILIO",
             "David, Barrio Bolívar, calle 3, casa 24"),
        )
        self.assertEqual(
            self._rows(
                self.replica_path,
                "SELECT id, total, estado, retiro_o_flete, direccion FROM pedidos",
            )[0],
            order,
        )
        order_json = self._order_json()
        self.assertEqual(order_json["id"], order[0])
        self.assertEqual(order_json["direccion"], order[4])

        # 1) Generar el cobro: muestra QR, número Yappy y el código del cobro.
        charge = self.client.post("/pagos", data={"pedido_id": str(order[0])})
        self.assertEqual(charge.status_code, 302)
        codigo = self._rows(
            self.local_path, "SELECT codigo FROM cobros_yappy WHERE pedido_id=?",
            (order[0],),
        )[0][0]
        self.assertEqual(
            self._rows(self.replica_path, "SELECT codigo, estado FROM cobros_yappy"),
            [(codigo, "PENDIENTE")],
        )
        charge_page = self.client.get(charge.headers["Location"])
        self.assertIn(b"<svg", charge_page.data)
        self.assertIn(utils.YAPPY_TELEFONO.encode(), charge_page.data)
        self.assertIn(codigo.encode(), charge_page.data)
        self.assertEqual(
            self.client.get(f"/pagos/yappy/{codigo}/estado").get_json()["estado"],
            "PENDIENTE",
        )

        # Generar de nuevo reutiliza el mismo cobro pendiente.
        self.client.post("/pagos", data={"pedido_id": str(order[0])})
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM cobros_yappy")[0][0], 1
        )

        # 2) El cliente escanea el QR y paga; recibe la confirmación.
        payment = self.client.post(f"/yappy/pagar/{codigo}", follow_redirects=True)
        self.assertIn("¡Pago realizado!".encode(), payment.data)
        self.assertEqual(self.mail_mock.call_count, 2)
        # Los JSON del pedido y del pago se guardan (y replican) en la base de datos...
        for path in (self.local_path, self.replica_path):
            json_pedido, json_pago = self._rows(
                path,
                "SELECT pedidos.json_pedido, pagos.json_pago FROM pagos "
                "JOIN pedidos ON pedidos.id = pagos.pedido_id",
            )[0]
            self.assertEqual(json.loads(json_pedido)["tipo"], "CONFIRMACION_PEDIDO")
            self.assertEqual(json.loads(json_pago)["tipo"], "CONFIRMACION_PAGO")
        # ...y el correo envía exactamente esos JSON guardados.
        documentos = self.mail_mock.call_args.args[2]
        self.assertEqual(
            [nombre for nombre, _ in documentos],
            [f"pedido_{order[0]}.json", "pago_1.json"],
        )
        self.assertEqual(documentos, [(f"pedido_{order[0]}.json", json_pedido),
                                      ("pago_1.json", json_pago)])
        sent_pedido = json.loads(documentos[0][1])
        sent_pago = json.loads(documentos[1][1])
        self.assertEqual(sent_pedido["id"], order[0])
        self.assertEqual(sent_pago["pedido"]["cantidad"], 2)
        self.assertEqual(sent_pago["direccion"], order[4])
        status = self.client.get(f"/pagos/yappy/{codigo}/estado").get_json()
        self.assertEqual(status["estado"], "PAGADO")
        self.assertTrue(status["referencia"].startswith("YAPPY-"))
        self.assertIn(
            "¡Pago confirmado!".encode(),
            self.client.get(f"/pagos/yappy/{codigo}").data,
        )

        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(
                    path, "SELECT pedido_id, metodo, monto FROM pagos"
                ),
                [(order[0], "YAPPY COMERCIAL", 15.75)],
            )
            self.assertEqual(
                self._rows(path, "SELECT estado FROM pedidos WHERE id=?", (order[0],)),
                [("PAGADO - DESPACHAR (FLETE)",)],
            )

        repeated = self.client.post(
            "/pagos", data={"pedido_id": str(order[0])}, follow_redirects=True
        )
        self.assertIn(b"Este pedido ya fue pagado", repeated.data)
        repeated_manual = self.client.post(
            f"/pagos/yappy/{codigo}", data={"referencia": "ABC12345"},
            follow_redirects=True,
        )
        self.assertIn(b"Este pedido ya fue pagado", repeated_manual.data)
        self.client.post(f"/yappy/pagar/{codigo}")
        self.assertEqual(self.mail_mock.call_count, 2)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pagos")[0][0], 1
        )

    def test_home_delivery_requires_an_address(self):
        response = self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": "1",
                "refrescos": ["Coca-Cola"],
                "refresco_cantidad": "1",
                "refresco_tamano": "LATA 12 OZ",
                "cantidad": "1",
                "retiro_o_flete": "FLETE A DOMICILIO",
                "direccion": "  ",
            },
        )
        self.assertIn("indique la dirección completa".encode(), response.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 0
        )

        # En retiro en sitio la dirección se ignora.
        self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": "1",
                "refrescos": ["Coca-Cola"],
                "refresco_cantidad": "1",
                "refresco_tamano": "LATA 12 OZ",
                "cantidad": "1",
                "retiro_o_flete": "RETIRO EN SITIO",
                "direccion": "No debería guardarse",
            },
        )
        self.assertEqual(
            self._rows(self.local_path, "SELECT direccion FROM pedidos"), [(None,)]
        )

    def test_payment_sent_to_yappy_number_is_confirmed_with_reference(self):
        self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": "2",
                "refrescos": ["Sprite"],
                "refresco_cantidad": "1",
                "refresco_tamano": "LATA 12 OZ",
                "cantidad": "1",
                "retiro_o_flete": "RETIRO EN SITIO",
            },
        )
        pedido_id = self._rows(self.local_path, "SELECT id FROM pedidos")[0][0]
        charge = self.client.post("/pagos", data={"pedido_id": str(pedido_id)})
        codigo = charge.headers["Location"].rsplit("/", 1)[-1]

        invalid = self.client.post(f"/pagos/yappy/{codigo}", data={"referencia": "x"})
        self.assertIn("número de transacción".encode(), invalid.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pagos")[0][0], 0
        )

        confirmed = self.client.post(
            f"/pagos/yappy/{codigo}", data={"referencia": "7h3k9p2m"},
            follow_redirects=True,
        )
        self.assertIn("¡Pago confirmado!".encode(), confirmed.data)
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT estado, referencia FROM cobros_yappy"),
                [("PAGADO", "7H3K9P2M")],
            )
            self.assertEqual(
                self._rows(path, "SELECT estado FROM pedidos WHERE id=?", (pedido_id,)),
                [("PAGADO",)],
            )

    def test_pizza_delivery_option_is_saved_and_enforced_on_orders(self):
        base = {
            "ingredientes": ["pepperoni", "jamón"],
            "refresco": "Sprite",
            "precio": "9.00",
        }
        invalid = self.client.post(
            "/fabrica/nueva", data={**base, "nombre": "Mala", "entrega": "DRON"}
        )
        self.assertIn("forma de entrega válida".encode(), invalid.data)

        self.client.post(
            "/fabrica/nueva",
            data={**base, "nombre": "Solo Retiro", "entrega": "RETIRO EN SITIO"},
        )
        pizza_id = self._rows(
            self.local_path, "SELECT id FROM pizzas WHERE nombre='Solo Retiro'"
        )[0][0]
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT entrega FROM pizzas WHERE id=?", (pizza_id,)),
                [("RETIRO EN SITIO",)],
            )
        self.assertIn(b"Solo retiro en sitio", self.client.get("/fabrica").data)

        pedido = {
            "cliente": "Cliente",
            "correo_cliente": "cliente@example.com",
            "pizza_id": str(pizza_id),
            "refrescos": ["Sprite"],
            "refresco_cantidad": "1",
            "refresco_tamano": "LATA 12 OZ",
            "cantidad": "1",
        }
        rejected = self.client.post(
            "/pedidos",
            data={**pedido, "retiro_o_flete": "FLETE A DOMICILIO",
                  "direccion": "David, Barrio Bolívar, casa 24"},
        )
        self.assertIn("solo está disponible para retiro en sitio".encode(), rejected.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 0
        )

        self.client.post("/pedidos", data={**pedido, "retiro_o_flete": "RETIRO EN SITIO"})
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 1
        )

        self.client.post(
            f"/fabrica/editar/{pizza_id}",
            data={**base, "nombre": "Solo Retiro", "entrega": "AMBOS"},
        )
        self.assertEqual(
            self._rows(self.replica_path, "SELECT entrega FROM pizzas WHERE id=?", (pizza_id,)),
            [("AMBOS",)],
        )

    def test_order_sodas_quantity_flavors_and_size(self):
        pedido = {
            "cliente": "Cliente",
            "correo_cliente": "cliente@example.com",
            "pizza_id": "1",
            "cantidad": "1",
            "retiro_o_flete": "RETIRO EN SITIO",
            "refresco_cantidad": "3",
            "refresco_tamano": "1 LITRO",
            "refrescos": ["Coca-Cola", "Sprite"],
        }
        bad_sum = self.client.post(
            "/pedidos", data={**pedido, "cant_Coca-Cola": "1", "cant_Sprite": "1"}
        )
        self.assertIn("La suma de sodas por sabor debe ser igual a 3".encode(), bad_sum.data)
        too_many = self.client.post(
            "/pedidos",
            data={**pedido, "refresco_cantidad": "1", "cant_Coca-Cola": "1", "cant_Sprite": "1"},
        )
        self.assertIn("más sabores que sodas".encode(), too_many.data)
        bad_size = self.client.post(
            "/pedidos", data={**pedido, "refresco_tamano": "BALDE",
                              "cant_Coca-Cola": "2", "cant_Sprite": "1"}
        )
        self.assertIn("tamaño de soda válido".encode(), bad_size.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 0
        )

        self.client.post(
            "/pedidos", data={**pedido, "cant_Coca-Cola": "2", "cant_Sprite": "1"}
        )
        expected = [("2× Coca-Cola, 1× Sprite (1 litro)", 3, "1 LITRO")]
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT refresco, refresco_cantidad, refresco_tamano FROM pedidos"),
                expected,
            )
        order_json = self._order_json()
        self.assertEqual(
            order_json["refrescos_detalle"],
            [{"sabor": "Coca-Cola", "cantidad": 2}, {"sabor": "Sprite", "cantidad": 1}],
        )

        # Sin soda: cantidad 0 ignora sabores y tamaño.
        self.client.post(
            "/pedidos", data={**pedido, "refresco_cantidad": "0", "refrescos": []}
        )
        self.assertEqual(
            self._rows(
                self.local_path,
                "SELECT refresco, refresco_cantidad, refresco_tamano FROM pedidos ORDER BY id DESC",
            )[0],
            ("Ninguno", 0, None),
        )

    def test_combos_and_individual_pizzas(self):
        base = {"ingredientes": ["pepperoni"], "precio": "6.00"}

        # Mozzarella ya no es un ingrediente seleccionable; basta 1 ingrediente.
        form = self.client.get("/fabrica/nueva").get_data(as_text=True)
        self.assertNotIn('value="queso mozzarella"', form)
        bad = self.client.post(
            "/fabrica/nueva",
            data={**base, "tipo": "PIZZA", "nombre": "Con queso",
                  "ingredientes": ["queso mozzarella"]},
        )
        self.assertIn(b"Seleccione ingredientes v", bad.data)
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT COUNT(*) FROM pizzas WHERE ',' || ingredientes "
                                 "|| ',' LIKE '%mozzarella%'")[0][0],
                0,
            )

        # Un combo debe incluir soda; una pizza individual la ignora.
        no_soda = self.client.post(
            "/fabrica/nueva", data={**base, "tipo": "COMBO", "nombre": "Combo sin soda"}
        )
        self.assertIn(b"Seleccione la soda que incluye el combo", no_soda.data)
        self.client.post(
            "/fabrica/nueva",
            data={**base, "tipo": "PIZZA", "nombre": "Solo Pepperoni", "refresco": "Fanta"},
        )
        pizza_id, refresco = self._rows(
            self.replica_path,
            "SELECT id, refresco FROM pizzas WHERE nombre='Solo Pepperoni' AND tipo='PIZZA'",
        )[0]
        self.assertIsNone(refresco)

        menu = self.client.get("/").get_data(as_text=True)
        self.assertIn("Combos", menu)
        self.assertIn("Pizzas individuales", menu)
        self.assertLess(menu.index("Hawaiana"), menu.index("Pizzas individuales"))
        self.assertGreater(menu.index("<h3>Solo Pepperoni</h3>"), menu.index("Pizzas individuales"))

        # Las pizzas individuales también pueden llevar sodas (se cobran todas).
        self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": str(pizza_id),
                "cantidad": "1",
                "retiro_o_flete": "RETIRO EN SITIO",
                "refresco_cantidad": "2",
                "refresco_tamano": "1 LITRO",
                "refrescos": ["Sprite"],
            },
        )
        self.assertEqual(
            self._rows(self.local_path, "SELECT refresco, refresco_cantidad, total FROM pedidos"),
            [("2× Sprite (1 litro)", 2, 10.5)],  # 6.00 + 2 × 2.25
        )

        # Las pizzas individuales se pueden borrar; los combos mantienen el mínimo.
        self.client.post(
            "/fabrica/nueva", data={**base, "tipo": "PIZZA", "nombre": "Temporal"}
        )
        temporal_id = self._rows(
            self.local_path, "SELECT id FROM pizzas WHERE nombre='Temporal'"
        )[0][0]
        self.client.post(f"/fabrica/eliminar/{temporal_id}")
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT id FROM pizzas WHERE id=?", (temporal_id,)), []
            )
        self._delete_duo_combos()
        to_pizza = self.client.post(
            "/fabrica/editar/1",
            data={**base, "tipo": "PIZZA", "nombre": "Pepperoni Clásica"},
        )
        self.assertIn(b"al menos 5 combos", to_pizza.data)

    def test_combo_pizzas_are_also_individual_and_duo_combos(self):
        catalog = self._rows(self.replica_path, "SELECT nombre, tipo FROM pizzas")
        for nombre in ("Pepperoni Clásica", "Hawaiana", "Vegetariana",
                       "Suprema Chinos", "Cuatro Quesos"):
            self.assertIn((nombre, "COMBO"), catalog)
            self.assertIn((nombre, "PIZZA"), catalog)

        duos = self._rows(
            self.local_path,
            "SELECT d.nombre, p1.nombre, p2.nombre, d.refresco FROM pizzas d "
            "JOIN pizzas p1 ON p1.id = d.pizza1_id JOIN pizzas p2 ON p2.id = d.pizza2_id "
            "WHERE d.tipo='DUO' ORDER BY d.id",
        )
        self.assertEqual(
            [(d[1], d[2]) for d in duos],
            [("Margarita", "Pepperoni"), ("Pepperoni", "Jamón y Champiñones"),
             ("Jamón y Champiñones", "Margarita")],
        )
        self.assertTrue(all(d[3] for d in duos))
        menu = self.client.get("/").get_data(as_text=True)
        self.assertIn("Combos de 2 pizzas", menu)
        self.assertIn("Dúo Margarita + Pepperoni", menu)

        ids = dict(self._rows(
            self.local_path, "SELECT nombre, id FROM pizzas WHERE tipo='PIZZA'"
        ))
        base = {"tipo": "DUO", "refresco": "Agua", "precio": "12.00"}
        same = self.client.post(
            "/fabrica/nueva",
            data={**base, "nombre": "Dúo igual",
                  "pizza1_id": ids["Hawaiana"], "pizza2_id": ids["Hawaiana"]},
        )
        self.assertIn(b"deben ser diferentes", same.data)
        combo_id = self._rows(
            self.local_path, "SELECT id FROM pizzas WHERE tipo='COMBO' LIMIT 1"
        )[0][0]
        not_individual = self.client.post(
            "/fabrica/nueva",
            data={**base, "nombre": "Dúo combo",
                  "pizza1_id": ids["Hawaiana"], "pizza2_id": combo_id},
        )
        self.assertIn(b"deben ser pizzas individuales", not_individual.data)

        self.client.post(
            "/fabrica/nueva",
            data={**base, "nombre": "Dúo Hawaiana + Vegetariana",
                  "pizza1_id": ids["Hawaiana"], "pizza2_id": ids["Vegetariana"]},
        )
        new_duo = self._rows(
            self.replica_path,
            "SELECT id, pizza1_id, pizza2_id, ingredientes FROM pizzas "
            "WHERE nombre='Dúo Hawaiana + Vegetariana'",
        )[0]
        self.assertEqual(new_duo[1:], (ids["Hawaiana"], ids["Vegetariana"], ""))

        # Una pizza que forma parte de un dúo no se puede borrar.
        blocked = self.client.post(
            f"/fabrica/eliminar/{ids['Vegetariana']}", follow_redirects=True
        )
        self.assertIn("forma parte de Dúo Hawaiana + Vegetariana".encode(), blocked.data)

        # El dúo es un combo: al pedirlo se guardan las sodas.
        self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": str(new_duo[0]),
                "cantidad": "1",
                "retiro_o_flete": "RETIRO EN SITIO",
                "refresco_cantidad": "2",
                "refresco_tamano": "LATA 12 OZ",
                "refrescos": ["Agua"],
            },
        )
        self.assertEqual(
            self._rows(self.local_path, "SELECT refresco, total FROM pedidos"),
            # 1 lata incluida en el combo + 1 lata extra ($1.00).
            [("2× Agua (Lata 12 oz)", 13.0)],
        )

    def test_cart_with_several_combos_and_pizzas(self):
        ids = {
            (nombre, tipo): pid for pid, nombre, tipo in
            self._rows(self.local_path, "SELECT id, nombre, tipo FROM pizzas")
        }
        combo = ids[("Hawaiana", "COMBO")]          # $7.75, incluye lata
        pizza = ids[("Margarita", "PIZZA")]         # $5.50
        duo = ids[("Dúo Margarita + Pepperoni", "DUO")]  # $12.50

        # Combo ×2 con 2 botellas de 20 oz: 2 × (1.50 − 1.00) = 1.00 de sodas.
        self.client.post("/pedidos/agregar", data={
            "categoria": "COMBO", "pizza_id": str(combo), "cantidad": "2",
            "refresco_cantidad": "2", "refresco_tamano": "BOTELLA 20 OZ",
            "refrescos": ["Sprite", "Fanta"], "cant_Sprite": "1", "cant_Fanta": "1",
            "cliente": "Ana",
        })
        # Pizza individual con 1 lata: 5.50 + 1.00.
        self.client.post("/pedidos/agregar", data={
            "categoria": "PIZZA", "pizza_id": str(pizza), "cantidad": "1",
            "refresco_cantidad": "1", "refresco_tamano": "LATA 12 OZ",
            "refrescos": ["Coca-Cola"], "cliente": "Ana",
        })
        # Pizza individual sin soda: 5.50.
        self.client.post("/pedidos/agregar", data={
            "categoria": "PIZZA", "pizza_id": str(pizza), "cantidad": "1",
            "refresco_cantidad": "0", "cliente": "Ana",
        })
        # Combo de 2 pizzas sin soda: 12.50 (no se descuenta la lata incluida).
        self.client.post("/pedidos/agregar", data={
            "categoria": "COMBO", "pizza_id": str(duo), "cantidad": "1",
            "refresco_cantidad": "0", "cliente": "Ana",
        })
        page = self.client.get("/pedidos").get_data(as_text=True)
        self.assertIn("2× Combo Hawaiana", page)
        self.assertIn("1× Pizza Margarita", page)
        self.assertIn('value="Ana"', page)  # los datos del cliente se conservan
        self.assertIn("$41.00", page)       # 16.50 + 6.50 + 5.50 + 12.50

        # Quitar la pizza sin soda.
        self.client.post("/pedidos/quitar/2", data={"cliente": "Ana"})
        self.assertIn("$35.50", self.client.get("/pedidos").get_data(as_text=True))

        self.client.post("/pedidos", data={
            "cliente": "Ana", "correo_cliente": "ana@example.com",
            "retiro_o_flete": "RETIRO EN SITIO",
        })
        pedido = self._rows(
            self.local_path, "SELECT id, total, detalle, cantidad FROM pedidos"
        )[0]
        self.assertEqual(
            pedido[1:],
            (35.5, "2× Combo Hawaiana, 1× Pizza Margarita, 1× Dúo Margarita + Pepperoni", 4),
        )
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT pizza_id, cantidad, sodas, precio_sodas, subtotal "
                                 "FROM pedido_items WHERE pedido_id=? ORDER BY id", (pedido[0],)),
                [
                    (combo, 2, "1× Sprite, 1× Fanta (Botella 20 oz)", 1.0, 16.5),
                    (pizza, 1, "1× Coca-Cola (Lata 12 oz)", 1.0, 6.5),
                    (duo, 1, "Ninguno", 0.0, 12.5),
                ],
            )
        order_json = self._order_json()
        self.assertEqual(len(order_json["items"]), 3)
        self.assertEqual(order_json["total"], 35.5)

        # Tras confirmar, el carrito queda vacío.
        self.assertIn("Todavía no has agregado productos", self.client.get("/pedidos").get_data(as_text=True))

    def test_cart_rejects_incompatible_delivery(self):
        ids = dict(self._rows(self.local_path, "SELECT nombre, id FROM pizzas WHERE tipo='PIZZA'"))
        for nombre, entrega in (("Margarita", "RETIRO EN SITIO"), ("Pepperoni", "FLETE A DOMICILIO")):
            self.client.post(f"/fabrica/editar/{ids[nombre]}", data={
                "tipo": "PIZZA", "nombre": nombre, "ingredientes": ["pepperoni"],
                "precio": "6.00", "entrega": entrega,
            })
        self.client.post("/pedidos/agregar", data={
            "categoria": "PIZZA", "pizza_id": str(ids["Margarita"]), "cantidad": "1",
            "refresco_cantidad": "0",
        })
        rejected = self.client.post("/pedidos/agregar", data={
            "categoria": "PIZZA", "pizza_id": str(ids["Pepperoni"]), "cantidad": "1",
            "refresco_cantidad": "0",
        }, follow_redirects=True)
        self.assertIn("no se puede combinar".encode(), rejected.data)
        to_home = self.client.post("/pedidos", data={
            "cliente": "Ana", "correo_cliente": "ana@example.com",
            "retiro_o_flete": "FLETE A DOMICILIO", "direccion": "David, Barrio Bolívar, casa 24",
        }, follow_redirects=True)
        self.assertIn("solo está disponible para retiro en sitio".encode(), to_home.data)
        self.assertEqual(self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 0)

    def test_json_is_stored_only_in_the_database(self):
        self.client.post("/pedidos", data={
            "cliente": "Ana", "correo_cliente": "ana@example.com", "pizza_id": "1",
            "cantidad": "1", "retiro_o_flete": "RETIRO EN SITIO", "refresco_cantidad": "0",
        })
        self.assertFalse(hasattr(utils, "PEDIDOS_JSON_DIR"))
        self.assertFalse(hasattr(utils, "PAGOS_JSON_DIR"))
        self.assertEqual(self._order_json()["tipo"], "CONFIRMACION_PEDIDO")

    def test_crusts_are_priced_per_pizza(self):
        ids = {
            (nombre, tipo): pid for pid, nombre, tipo in
            self._rows(self.local_path, "SELECT id, nombre, tipo FROM pizzas")
        }
        base = {"refresco_cantidad": "0", "cliente": "Ana"}
        # 2 pizzas Margarita con borde de queso: 2 × 5.50 + 2 × 1.50 = 14.00
        self.client.post("/pedidos/agregar", data={
            **base, "categoria": "PIZZA", "pizza_id": str(ids[("Margarita", "PIZZA")]),
            "cantidad": "2", "borde": "QUESO",
        })
        # 1 dúo con borde de pepperoni en sus 2 pizzas: 12.50 + 2 × 2.00 = 16.50
        self.client.post("/pedidos/agregar", data={
            **base, "categoria": "COMBO", "cantidad": "1", "borde": "PEPPERONI",
            "pizza_id": str(ids[("Dúo Margarita + Pepperoni", "DUO")]),
        })
        # Sin borde elegido = borde clásico, sin costo: 7.75
        self.client.post("/pedidos/agregar", data={
            **base, "categoria": "COMBO", "cantidad": "1",
            "pizza_id": str(ids[("Hawaiana", "COMBO")]),
        })
        bad = self.client.post("/pedidos/agregar", data={
            **base, "categoria": "PIZZA", "cantidad": "1", "borde": "DIAMANTE",
            "pizza_id": str(ids[("Margarita", "PIZZA")]),
        }, follow_redirects=True)
        self.assertIn("borde válido".encode(), bad.data)

        page = self.client.get("/pedidos").get_data(as_text=True)
        self.assertIn("Relleno de queso", page)
        self.assertIn("$38.25", page)  # 14.00 + 16.50 + 7.75

        self.client.post("/pedidos", data={
            "cliente": "Ana", "correo_cliente": "ana@example.com",
            "retiro_o_flete": "RETIRO EN SITIO",
        })
        self.assertEqual(
            self._rows(self.local_path, "SELECT subtotal, flete, total, detalle FROM pedidos"),
            [(38.25, 0.0, 38.25,
              "2× Pizza Margarita (Relleno de queso), "
              "1× Dúo Margarita + Pepperoni (Relleno de pepperoni), 1× Combo Hawaiana")],
        )
        for path in (self.local_path, self.replica_path):
            self.assertEqual(
                self._rows(path, "SELECT borde, precio_borde, subtotal FROM pedido_items ORDER BY id"),
                [("QUESO", 3.0, 14.0), ("PEPPERONI", 4.0, 16.5), ("CLASICO", 0.0, 7.75)],
            )
        items = self._order_json()["items"]
        self.assertEqual([i["borde"] for i in items],
                         ["Relleno de queso", "Relleno de pepperoni", "Borde clásico"])

    def test_home_delivery_adds_five_percent_fee(self):
        pedido = {
            "cliente": "Ana", "correo_cliente": "ana@example.com", "pizza_id": "4",
            "cantidad": "3", "refresco_cantidad": "0",  # 3 × 8.90 = 26.70
        }
        self.client.post("/pedidos", data={
            **pedido, "retiro_o_flete": "FLETE A DOMICILIO",
            "direccion": "David, Barrio Bolívar, casa 24",
        })
        self.client.post("/pedidos", data={**pedido, "retiro_o_flete": "RETIRO EN SITIO"})
        self.assertEqual(
            self._rows(self.local_path, "SELECT subtotal, flete, total FROM pedidos ORDER BY id"),
            [(26.7, 1.34, 28.04), (26.7, 0.0, 26.7)],  # 5% de 26.70 = 1.335 → 1.34
        )
        # El cobro Yappy usa el total con flete.
        charge = self.client.post("/pagos", data={"pedido_id": "1"})
        codigo = charge.headers["Location"].rsplit("/", 1)[-1]
        self.assertEqual(
            self._rows(self.local_path, "SELECT monto FROM cobros_yappy WHERE codigo=?", (codigo,)),
            [(28.04,)],
        )

    def test_unknown_yappy_code_is_handled(self):
        self.assertEqual(self.client.get("/yappy/pagar/CC-NOPE00").status_code, 404)
        self.assertEqual(
            self.client.get("/pagos/yappy/CC-NOPE00/estado").status_code, 404
        )
        self.assertEqual(self.client.get("/pagos/yappy/CC-NOPE00").status_code, 302)

    def test_email_failure_is_reported_without_false_success(self):
        self.mail.stop()
        self.mail = mock.patch.object(
            webapp, "enviar_correo", return_value=(False, "SMTP no disponible")
        )
        self.mail.start()
        self.addCleanup(self.mail.stop)

        self.client.post(
            "/pedidos",
            data={
                "cliente": "Cliente",
                "correo_cliente": "cliente@example.com",
                "pizza_id": "1",
                "refrescos": ["Coca-Cola"],
                "refresco_cantidad": "1",
                "refresco_tamano": "LATA 12 OZ",
                "cantidad": "1",
                "retiro_o_flete": "RETIRO EN SITIO",
            },
        )
        charge = self.client.post("/pagos", data={"pedido_id": "1"})
        codigo = charge.headers["Location"].rsplit("/", 1)[-1]
        response = self.client.post(f"/yappy/pagar/{codigo}", follow_redirects=True)
        self.assertIn(b"no se pudieron enviar", response.data)
        self.assertNotIn(b"correos de confirmaci", response.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pagos")[0][0], 1
        )

    def test_all_application_pages_render(self):
        for path in ("/", "/fabrica", "/fabrica/nueva", "/pedidos", "/pagos"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_menu_order_link_preselects_the_requested_pizza(self):
        menu = self.client.get("/")
        self.assertIn(b"/pedidos?pizza_id=3", menu.data)

        order_page = self.client.get("/pedidos?pizza_id=3")
        self.assertEqual(order_page.status_code, 200)
        html = order_page.get_data(as_text=True)
        self.assertRegex(
            html,
            re.compile(r'<option value="3" data-price="7\.25" data-entrega="AMBOS"[^>]*\s+selected>'),
        )
        self.assertIn(b'id="summary-total"', order_page.data)
        self.assertIn(b'static/order.js', order_page.data)


if __name__ == "__main__":
    unittest.main()
