"""
database.py
-------------------------------------------------
Maneja la conexión a DOS bases de datos SQLite:
  - db_local.sqlite3   -> Base de datos RELACIONAL local (Sede principal, Chiriquí)
  - db_replica.sqlite3 -> Base de datos RELACIONAL de réplica (simula la
                           "Máquina Virtual" de la sucursal de Veraguas)

Toda operación de escritura (INSERT/UPDATE/DELETE) sobre pedidos y pagos
se realiza primero en la base LOCAL y luego se REPLICA en la base de
réplica, cumpliendo con el requisito de "Replicación de Datos" del examen.

Todas las operaciones están protegidas con TRY/EXCEPT, tal como lo pide
el examen (control de errores en los campos / operaciones).
-------------------------------------------------
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_LOCAL_PATH = os.path.join(BASE_DIR, "db_local.sqlite3")
DB_REPLICA_PATH = os.path.join(BASE_DIR, "db_replica.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pizzas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ingredientes TEXT NOT NULL,      -- separados por coma, min 2 - max 10
    refresco TEXT,
    precio REAL NOT NULL DEFAULT 5.00
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT NOT NULL,
    correo_cliente TEXT NOT NULL,
    pizza_id INTEGER NOT NULL,
    refresco TEXT,
    cantidad INTEGER NOT NULL DEFAULT 1,
    total REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',   -- PENDIENTE / CONFIRMADO / PAGADO / DESPACHADO
    retiro_o_flete TEXT NOT NULL DEFAULT 'RETIRO EN SITIO',
    fecha TEXT NOT NULL,
    FOREIGN KEY (pizza_id) REFERENCES pizzas(id)
);

CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    metodo TEXT NOT NULL DEFAULT 'YAPPY COMERCIAL',
    monto REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'CONFIRMADO',
    fecha TEXT NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);
"""


def _connect(path):
    """Abre una conexión segura con manejo de errores."""
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo conectar a {path}: {e}")
        raise


def get_local_conn():
    return _connect(DB_LOCAL_PATH)


def get_replica_conn():
    return _connect(DB_REPLICA_PATH)


def init_db():
    """Crea las tablas en AMBAS bases de datos (local y réplica) si no existen."""
    for path in (DB_LOCAL_PATH, DB_REPLICA_PATH):
        try:
            conn = _connect(path)
            conn.executescript(SCHEMA)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"[ERROR DB] No se pudo inicializar {path}: {e}")

    # Datos de ejemplo (mínimo 5 combos de pizza) si la tabla está vacía
    try:
        conn = get_local_conn()
        cur = conn.execute("SELECT COUNT(*) FROM pizzas")
        count = cur.fetchone()[0]
        if count == 0:
            demo_pizzas = [
                ("Pepperoni Clásica", "queso mozzarella,pepperoni,salsa de tomate", "Coca-Cola", 7.50),
                ("Hawaiana", "queso mozzarella,jamón,piña,salsa de tomate", "Sprite", 7.75),
                ("Vegetariana", "queso mozzarella,pimentón,cebolla,champiñones,aceitunas", "Agua", 7.25),
                ("Suprema Chinos", "queso mozzarella,pepperoni,jamón,champiñones,pimentón,cebolla", "Fanta", 8.90),
                ("Cuatro Quesos", "mozzarella,parmesano,queso azul,gouda", "Coca-Cola Zero", 8.50),
            ]
            conn.executemany(
                "INSERT INTO pizzas (nombre, ingredientes, refresco, precio) VALUES (?,?,?,?)",
                demo_pizzas,
            )
            conn.commit()

            # Replicar también los datos de ejemplo
            replica_conn = get_replica_conn()
            replica_conn.executemany(
                "INSERT INTO pizzas (nombre, ingredientes, refresco, precio) VALUES (?,?,?,?)",
                demo_pizzas,
            )
            replica_conn.commit()
            replica_conn.close()
        conn.close()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudieron insertar datos de ejemplo: {e}")


def replicate_write(sql, params):
    """
    Ejecuta la misma sentencia SQL (INSERT/UPDATE/DELETE) en la base LOCAL
    y luego la replica en la base de RÉPLICA. Devuelve (ok: bool, last_id, error).
    """
    last_id = None
    try:
        local_conn = get_local_conn()
        cur = local_conn.execute(sql, params)
        local_conn.commit()
        last_id = cur.lastrowid
        local_conn.close()
    except sqlite3.Error as e:
        print(f"[ERROR DB LOCAL] {e}")
        return False, None, str(e)

    try:
        replica_conn = get_replica_conn()
        replica_conn.execute(sql, params)
        replica_conn.commit()
        replica_conn.close()
    except sqlite3.Error as e:
        # La escritura local sí se logró; solo falló la réplica.
        print(f"[ERROR DB REPLICA] {e}")
        return True, last_id, f"Guardado local OK, pero falló la réplica: {e}"

    return True, last_id, None
