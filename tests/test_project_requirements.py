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
        self.pedidos_dir = root / "pedidos_json"
        self.pagos_dir = root / "pagos_json"

        for name, value in (
            ("DB_LOCAL_PATH", str(self.local_path)),
            ("DB_REPLICA_PATH", str(self.replica_path)),
            ("PEDIDOS_JSON_DIR", str(self.pedidos_dir)),
            ("PAGOS_JSON_DIR", str(self.pagos_dir)),
        ):
            patcher = mock.patch.object(
                database if name.startswith("DB_") else utils, name, value
            )
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

    def test_startup_has_five_catalog_items_in_both_databases(self):
        for path in (self.local_path, self.replica_path):
            rows = self._rows(path, "SELECT id, nombre FROM pizzas ORDER BY id")
            self.assertGreaterEqual(len(rows), 5)
        self.assertEqual(
            self._rows(self.local_path, "SELECT id, nombre FROM pizzas ORDER BY id"),
            self._rows(self.replica_path, "SELECT id, nombre FROM pizzas ORDER BY id"),
        )

    def test_crud_validates_fields_and_keeps_catalog_replicated(self):
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
                self._rows(path, "SELECT COUNT(*) FROM pizzas")[0][0], 5
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
                "ingredientes": ["queso mozzarella", "chorizo"],
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
                self._rows(path, "SELECT COUNT(*) FROM pizzas")[0][0], 5
            )
            self.assertEqual(
                self._rows(path, "SELECT id FROM pizzas WHERE id=?", (pizza_id,)), []
            )

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
        self.assertEqual(self.mail_mock.call_count, 2)

        order = self._rows(
            self.local_path,
            "SELECT id, total, estado, retiro_o_flete, direccion FROM pedidos",
        )[0]
        self.assertEqual(
            order[1:],
            (15.0, "CONFIRMADO", "FLETE A DOMICILIO",
             "David, Barrio Bolívar, calle 3, casa 24"),
        )
        self.assertEqual(
            self._rows(
                self.replica_path,
                "SELECT id, total, estado, retiro_o_flete, direccion FROM pedidos",
            )[0],
            order,
        )
        json_files = list(self.pedidos_dir.glob("*.json"))
        self.assertEqual(len(json_files), 1)
        order_json = json.loads(json_files[0].read_text(encoding="utf-8"))
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
        self.assertEqual(self.mail_mock.call_count, 4)
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
                [(order[0], "YAPPY COMERCIAL", 15.0)],
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
        self.assertEqual(self.mail_mock.call_count, 4)
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
        order_json = json.loads(
            next(self.pedidos_dir.glob("*.json")).read_text(encoding="utf-8")
        )
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
                "retiro_o_flete": "RETIRO EN SITIO",
            },
            follow_redirects=True,
        )
        self.assertIn(b"no se pudieron enviar", response.data)
        self.assertNotIn(b"correos de confirmaci", response.data)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pedidos")[0][0], 1
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
