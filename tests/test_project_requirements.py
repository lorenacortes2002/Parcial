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
        self.temp_dir = tempfile.TemporaryDirectory()
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
        with sqlite3.connect(path) as conn:
            return conn.execute(query, params).fetchall()

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
                "refresco": "Coca-Cola",
                "cantidad": "2",
                "retiro_o_flete": "FLETE A DOMICILIO",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Pedido #", response.data)
        self.assertEqual(self.mail_mock.call_count, 2)

        order = self._rows(
            self.local_path,
            "SELECT id, total, estado, retiro_o_flete FROM pedidos",
        )[0]
        self.assertEqual(order[1:], (15.0, "CONFIRMADO", "FLETE A DOMICILIO"))
        self.assertEqual(
            self._rows(
                self.replica_path,
                "SELECT id, total, estado, retiro_o_flete FROM pedidos",
            )[0],
            order,
        )
        json_files = list(self.pedidos_dir.glob("*.json"))
        self.assertEqual(len(json_files), 1)
        self.assertEqual(json.loads(json_files[0].read_text())["id"], order[0])

        payment = self.client.post(
            "/pagos", data={"pedido_id": str(order[0])}, follow_redirects=True
        )
        self.assertIn(b"Pago del pedido", payment.data)
        self.assertEqual(self.mail_mock.call_count, 4)

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
        self.assertEqual(self.mail_mock.call_count, 4)
        self.assertEqual(
            self._rows(self.local_path, "SELECT COUNT(*) FROM pagos")[0][0], 1
        )

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
                "refresco": "Coca-Cola",
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
            re.compile(r'<option value="3" data-price="7\.25"\s+selected>'),
        )
        self.assertIn(b'id="summary-total"', order_page.data)
        self.assertIn(b'static/order.js', order_page.data)


if __name__ == "__main__":
    unittest.main()
