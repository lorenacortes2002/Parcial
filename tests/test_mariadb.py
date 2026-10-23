"""
Pruebas de la app contra un servidor MariaDB real.

Se ejecutan solo si el .env configura MariaDB (DB_MOTOR=mariadb) y usan una
base aparte, chinos_cafe_test (nunca la base real). Para crearla, como root:
    CREATE DATABASE chinos_cafe_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    GRANT ALL PRIVILEGES ON chinos_cafe_test.* TO 'chinos_app'@'localhost';
"""

import json
import os
import unittest
from unittest import mock

import app as webapp
import database

BASE_PRUEBAS = "chinos_cafe_test"


@unittest.skipUnless(
    os.environ.get("DB_MOTOR", "").lower() == "mariadb",
    "MariaDB no está configurado en el .env (DB_MOTOR=mariadb)",
)
class MariaDBTests(unittest.TestCase):
    def setUp(self):
        entorno = mock.patch.dict("os.environ", {"DB_NAME": BASE_PRUEBAS})
        entorno.start()
        self.addCleanup(entorno.stop)

        # Base de pruebas vacía en cada prueba.
        conn = database.get_local_conn()
        try:
            conn.execute("SET FOREIGN_KEY_CHECKS = 0")
            for tabla in database.TABLAS:
                conn.execute(f"DROP TABLE IF EXISTS {tabla}")
            conn.execute("SET FOREIGN_KEY_CHECKS = 1")
            conn.commit()
        finally:
            conn.close()
        database.init_db()

        self.mail = mock.patch.object(webapp, "enviar_correo", return_value=(True, None))
        self.mail_mock = self.mail.start()
        self.addCleanup(self.mail.stop)
        self.client = webapp.app.test_client()

    def _rows(self, query, params=()):
        conn = database.get_local_conn()
        try:
            return [tuple(fila) for fila in conn.execute(query, params).fetchall()]
        finally:
            conn.close()

    def test_uses_mariadb_and_loads_the_catalog(self):
        version = self._rows("SELECT VERSION()")[0][0]
        self.assertIn("MariaDB", version)
        self.assertEqual(self._rows("SELECT DATABASE()"), [(BASE_PRUEBAS,)])
        conteo = dict(self._rows("SELECT tipo, COUNT(*) FROM pizzas GROUP BY tipo"))
        self.assertEqual(conteo, {"COMBO": 5, "DUO": 3, "PIZZA": 8})
        # Volver a iniciar no duplica el catálogo.
        database.init_db()
        self.assertEqual(self._rows("SELECT COUNT(*) FROM pizzas"), [(16,)])
        for ruta in ("/", "/fabrica", "/fabrica/nueva", "/pedidos", "/pagos"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_fabrica_crud_with_accents(self):
        self.client.post("/fabrica/nueva", data={
            "tipo": "PIZZA", "nombre": "Jamón Ñandú", "ingredientes": ["jamón", "piña"],
            "precio": "6.75", "entrega": "AMBOS",
        })
        pizza_id, nombre, ingredientes = self._rows(
            "SELECT id, nombre, ingredientes FROM pizzas WHERE nombre=?", ("Jamón Ñandú",)
        )[0]
        self.assertEqual((nombre, ingredientes), ("Jamón Ñandú", "jamón,piña"))
        self.client.post(f"/fabrica/editar/{pizza_id}", data={
            "tipo": "PIZZA", "nombre": "Jamón Ñandú", "ingredientes": ["chorizo"],
            "precio": "7.00", "entrega": "RETIRO EN SITIO",
        })
        self.assertEqual(
            self._rows("SELECT precio, entrega FROM pizzas WHERE id=?", (pizza_id,)),
            [(7.0, "RETIRO EN SITIO")],
        )
        self.client.post(f"/fabrica/eliminar/{pizza_id}")
        self.assertEqual(self._rows("SELECT id FROM pizzas WHERE id=?", (pizza_id,)), [])
        # Los combos mantienen el mínimo de cinco (usa la consulta "? IS NULL OR id <> ?").
        for (duo_id,) in self._rows("SELECT id FROM pizzas WHERE tipo='DUO'"):
            self.client.post(f"/fabrica/eliminar/{duo_id}")
        bloqueado = self.client.post("/fabrica/eliminar/1", follow_redirects=True)
        self.assertIn(b"al menos cinco combos", bloqueado.data)

    def test_full_order_with_crust_sodas_fee_and_yappy_payment(self):
        hawaiana = self._rows("SELECT id FROM pizzas WHERE nombre='Hawaiana' AND tipo='COMBO'")[0][0]
        self.client.post("/pedidos/agregar", data={
            "categoria": "COMBO", "pizza_id": str(hawaiana), "cantidad": "2", "borde": "QUESO",
            "refresco_cantidad": "2", "refresco_tamano": "BOTELLA 20 OZ",
            "refrescos": ["Sprite", "Fanta"], "cant_Sprite": "1", "cant_Fanta": "1",
        })
        self.client.post("/pedidos", data={
            "cliente": "Ángela Núñez", "correo_cliente": "angela@example.com",
            "retiro_o_flete": "FLETE A DOMICILIO", "direccion": "David, Barrio Bolívar, casa 24",
        })
        # 2 × 7.75 + 2 × 1.50 (queso) + 2 × 0.50 (diferencia botella) = 19.50; flete 0.98
        pedido = self._rows(
            "SELECT id, cliente, subtotal, flete, total, detalle, estado FROM pedidos"
        )[0]
        self.assertEqual(pedido[1:], ("Ángela Núñez", 19.5, 0.98, 20.48,
                                      "2× Combo Hawaiana (Relleno de queso)", "CONFIRMADO"))
        self.assertEqual(
            self._rows("SELECT borde, precio_borde, sodas FROM pedido_items"),
            [("QUESO", 3.0, "1× Sprite, 1× Fanta (Botella 20 oz)")],
        )
        json_pedido = json.loads(self._rows("SELECT json_pedido FROM pedidos")[0][0])
        self.assertEqual((json_pedido["cliente"], json_pedido["total"]), ("Ángela Núñez", 20.48))

        # El nombre del pedido en Pagos usa COALESCE(... || ...) (PIPES_AS_CONCAT).
        self.assertIn("2× Combo Hawaiana".encode(), self.client.get("/pagos").data)

        charge = self.client.post("/pagos", data={"pedido_id": str(pedido[0])})
        codigo = charge.headers["Location"].rsplit("/", 1)[-1]
        pago = self.client.post(f"/yappy/pagar/{codigo}", follow_redirects=True)
        self.assertIn("¡Pago realizado!".encode(), pago.data)
        self.assertEqual(
            self._rows("SELECT estado FROM pedidos"), [("PAGADO - DESPACHAR (FLETE)",)]
        )
        self.assertEqual(self._rows("SELECT monto FROM pagos"), [(20.48,)])
        documentos = self.mail_mock.call_args.args[2]
        self.assertEqual([n for n, _ in documentos],
                         [f"pedido_{pedido[0]}.json", "pago_1.json"])

        # Un pago repetido se rechaza (índice único de pagos.pedido_id).
        repetido = self.client.post(f"/pagos/yappy/{codigo}", data={"referencia": "ABC12345"},
                                    follow_redirects=True)
        self.assertIn(b"Este pedido ya fue pagado", repetido.data)
        ok, _, error = database.replicate_write(
            "INSERT INTO pagos (pedido_id, metodo, monto, estado, fecha) VALUES (?,?,?,?,?)",
            (pedido[0], "YAPPY COMERCIAL", 1.0, "CONFIRMADO", "2026-01-01 00:00:00"),
        )
        self.assertFalse(ok)
        self.assertTrue(database.es_duplicado(error))
        self.assertEqual(self._rows("SELECT COUNT(*) FROM pagos"), [(1,)])

    def test_failed_transaction_is_rolled_back(self):
        antes = self._rows("SELECT COUNT(*) FROM pizzas")[0][0]
        ok, _, error = database.replicate_transaction([
            ("INSERT INTO pizzas (nombre, ingredientes, precio, tipo) VALUES (?,?,?,?)",
             ("Temporal", "pepperoni", 5.0, "PIZZA")),
            ("INSERT INTO pedidos (cliente) VALUES (?)", ("sin columnas obligatorias",)),
        ])
        self.assertFalse(ok)
        self.assertTrue(error)
        self.assertEqual(self._rows("SELECT COUNT(*) FROM pizzas")[0][0], antes)


if __name__ == "__main__":
    unittest.main()
