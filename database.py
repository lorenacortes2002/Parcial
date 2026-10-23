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
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_LOCAL_PATH = os.path.join(BASE_DIR, "db_local.sqlite3")
DB_REPLICA_PATH = os.path.join(BASE_DIR, "db_replica.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pizzas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ingredientes TEXT NOT NULL,      -- separados por coma, min 2 - max 10
    refresco TEXT,
    precio REAL NOT NULL DEFAULT 5.00,
    entrega TEXT NOT NULL DEFAULT 'AMBOS',  -- AMBOS / RETIRO EN SITIO / FLETE A DOMICILIO
    tipo TEXT NOT NULL DEFAULT 'COMBO',     -- COMBO / DUO (2 pizzas + soda) / PIZZA (individual)
    pizza1_id INTEGER REFERENCES pizzas(id),  -- solo DUO: las dos pizzas individuales
    pizza2_id INTEGER REFERENCES pizzas(id)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT NOT NULL,
    correo_cliente TEXT NOT NULL,
    pizza_id INTEGER NOT NULL,
    refresco TEXT,                              -- descripción, p. ej. "2× Coca-Cola, 1× Sprite (1 litro)"
    refresco_cantidad INTEGER NOT NULL DEFAULT 1,
    refresco_tamano TEXT,
    cantidad INTEGER NOT NULL DEFAULT 1,
    total REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',   -- PENDIENTE / CONFIRMADO / PAGADO / DESPACHADO
    retiro_o_flete TEXT NOT NULL DEFAULT 'RETIRO EN SITIO',
    direccion TEXT,                             -- obligatoria solo si es FLETE A DOMICILIO
    fecha TEXT NOT NULL,
    detalle TEXT,                               -- resumen: "2× Combo Hawaiana, 1× Pizza Margarita"
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

-- Productos de cada pedido (un pedido puede tener varios combos y pizzas).
CREATE TABLE IF NOT EXISTS pedido_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    pizza_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    sodas TEXT NOT NULL DEFAULT 'Ninguno',      -- p. ej. "2× Coca-Cola (Lata 12 oz)"
    sodas_cantidad INTEGER NOT NULL DEFAULT 0,
    sodas_tamano TEXT,
    precio_sodas REAL NOT NULL DEFAULT 0,
    subtotal REAL NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
    FOREIGN KEY (pizza_id) REFERENCES pizzas(id)
);

-- Cobros Yappy generados (QR / número) a la espera de que el cliente pague.
CREATE TABLE IF NOT EXISTS cobros_yappy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    codigo TEXT NOT NULL UNIQUE,
    monto REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',   -- PENDIENTE / PAGADO
    referencia TEXT,                            -- n.º de transacción Yappy al pagar
    fecha TEXT NOT NULL,
    fecha_pago TEXT,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);
"""


def _migrate(conn):
    """Actualiza bases creadas con versiones anteriores del esquema."""
    columnas = {row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")}
    if "direccion" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN direccion TEXT")
    if "refresco_cantidad" not in columnas:
        conn.execute(
            "ALTER TABLE pedidos ADD COLUMN refresco_cantidad INTEGER NOT NULL DEFAULT 1"
        )
    if "refresco_tamano" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN refresco_tamano TEXT")
    if "detalle" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN detalle TEXT")
    columnas = {row["name"] for row in conn.execute("PRAGMA table_info(pizzas)")}
    if "entrega" not in columnas:
        conn.execute("ALTER TABLE pizzas ADD COLUMN entrega TEXT NOT NULL DEFAULT 'AMBOS'")
    if "tipo" not in columnas:
        conn.execute("ALTER TABLE pizzas ADD COLUMN tipo TEXT NOT NULL DEFAULT 'COMBO'")
    for columna in ("pizza1_id", "pizza2_id"):
        if columna not in columnas:
            conn.execute(
                f"ALTER TABLE pizzas ADD COLUMN {columna} INTEGER REFERENCES pizzas(id)"
            )
    try:
        # Un pedido solo puede tener un pago: evita cobros dobles simultáneos.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_pagos_pedido ON pagos(pedido_id)"
        )
    except sqlite3.IntegrityError as e:
        print(f"[AVISO DB] Hay pagos duplicados; no se creó el índice único: {e}")


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
        conn = None
        try:
            conn = _connect(path)
            conn.executescript(SCHEMA)
            _migrate(conn)
            conn.commit()
        except sqlite3.Error as e:
            print(f"[ERROR DB] No se pudo inicializar {path}: {e}")
            raise
        finally:
            if conn is not None:
                conn.close()

    # Garantiza el catálogo inicial (cinco combos, sus versiones individuales,
    # otras pizzas individuales y combos de 2 pizzas) y lo replica con sus mismos IDs. El queso mozzarella es la base de todas
    # las pizzas, por eso no aparece en la lista de ingredientes.
    try:
        conn = get_local_conn()
        demo_pizzas = [
            ("Pepperoni Clásica", "pepperoni,salsa de tomate", "Coca-Cola", 7.50, "COMBO"),
            ("Hawaiana", "jamón,piña,salsa de tomate", "Sprite", 7.75, "COMBO"),
            ("Vegetariana", "pimentón,cebolla,champiñones,aceitunas", "Agua", 7.25, "COMBO"),
            ("Suprema Chinos", "pepperoni,jamón,champiñones,pimentón,cebolla", "Fanta", 8.90, "COMBO"),
            ("Cuatro Quesos", "parmesano,queso azul,gouda", "Coca-Cola Zero", 8.50, "COMBO"),
            ("Margarita", "salsa de tomate", None, 5.50, "PIZZA"),
            ("Pepperoni", "pepperoni", None, 6.00, "PIZZA"),
            ("Jamón y Champiñones", "jamón,champiñones", None, 6.50, "PIZZA"),
            # Las pizzas de los combos también se venden solas (sin soda).
            ("Pepperoni Clásica", "pepperoni,salsa de tomate", None, 6.00, "PIZZA"),
            ("Hawaiana", "jamón,piña,salsa de tomate", None, 6.25, "PIZZA"),
            ("Vegetariana", "pimentón,cebolla,champiñones,aceitunas", None, 5.75, "PIZZA"),
            ("Suprema Chinos", "pepperoni,jamón,champiñones,pimentón,cebolla", None, 7.40, "PIZZA"),
            ("Cuatro Quesos", "parmesano,queso azul,gouda", None, 7.00, "PIZZA"),
        ]
        # Combos de 2 pizzas individuales diferentes con soda:
        # (nombre, pizza 1, pizza 2, soda, precio)
        demo_duos = [
            ("Dúo Margarita + Pepperoni", "Margarita", "Pepperoni", "Coca-Cola", 12.50),
            ("Dúo Pepperoni + Jamón y Champiñones", "Pepperoni", "Jamón y Champiñones", "Sprite", 13.50),
            ("Dúo Jamón y Champiñones + Margarita", "Jamón y Champiñones", "Margarita", "Fanta", 13.00),
        ]
        # Versiones anteriores incluían "queso mozzarella" (o "mozzarella")
        # como ingrediente: se quita porque ya es la base de todas las pizzas.
        for row in conn.execute(
            "SELECT id, ingredientes FROM pizzas "
            "WHERE ',' || ingredientes || ',' LIKE '%,mozzarella,%' "
            "OR ',' || ingredientes || ',' LIKE '%,queso mozzarella,%'"
        ).fetchall():
            restantes = [
                ing for ing in row["ingredientes"].split(",")
                if ing not in ("mozzarella", "queso mozzarella")
            ]
            if restantes:
                conn.execute(
                    "UPDATE pizzas SET ingredientes=? WHERE id=?",
                    (",".join(restantes), row["id"]),
                )
        # Un mismo nombre puede existir como combo y como pizza individual.
        existentes = {
            (row["nombre"], row["tipo"])
            for row in conn.execute("SELECT nombre, tipo FROM pizzas").fetchall()
        }
        for pizza in demo_pizzas:
            if (pizza[0], pizza[4]) not in existentes:
                conn.execute(
                    "INSERT INTO pizzas (nombre, ingredientes, refresco, precio, tipo) "
                    "VALUES (?,?,?,?,?)",
                    pizza,
                )
        individuales = {
            row["nombre"]: row["id"]
            for row in conn.execute("SELECT id, nombre FROM pizzas WHERE tipo='PIZZA'")
        }
        for nombre, pizza1, pizza2, soda, precio in demo_duos:
            if (nombre, "DUO") not in existentes and pizza1 in individuales and pizza2 in individuales:
                conn.execute(
                    "INSERT INTO pizzas (nombre, ingredientes, refresco, precio, tipo, "
                    "pizza1_id, pizza2_id) VALUES (?, '', ?, ?, 'DUO', ?, ?)",
                    (nombre, soda, precio, individuales[pizza1], individuales[pizza2]),
                )
        conn.commit()
        pizzas = conn.execute("SELECT * FROM pizzas ORDER BY id").fetchall()
        conn.close()

        replica_conn = get_replica_conn()
        try:
            with replica_conn:
                for pizza in pizzas:
                    replica_conn.execute(
                        """
                        INSERT INTO pizzas (id, nombre, ingredientes, refresco, precio, entrega, tipo,
                                            pizza1_id, pizza2_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            nombre=excluded.nombre,
                            ingredientes=excluded.ingredientes,
                            refresco=excluded.refresco,
                            precio=excluded.precio,
                            entrega=excluded.entrega,
                            tipo=excluded.tipo,
                            pizza1_id=excluded.pizza1_id,
                            pizza2_id=excluded.pizza2_id
                        """,
                        (
                            pizza["id"], pizza["nombre"], pizza["ingredientes"],
                            pizza["refresco"], pizza["precio"], pizza["entrega"],
                            pizza["tipo"], pizza["pizza1_id"], pizza["pizza2_id"],
                        ),
                    )
        finally:
            replica_conn.close()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo preparar el catálogo de ejemplo: {e}")
        raise


def replicate_transaction(operations):
    """Aplica un grupo de escrituras en ambas bases; conserva IDs al replicar inserts."""
    local_conn = None
    replica_conn = None
    local_ids = []
    try:
        local_conn = get_local_conn()
        with local_conn:
            for sql, params in operations:
                cur = local_conn.execute(sql, params)
                local_ids.append(cur.lastrowid)
    except sqlite3.Error as e:
        if local_conn is not None:
            local_conn.rollback()
        print(f"[ERROR DB LOCAL] {e}")
        return False, None, str(e)
    finally:
        if local_conn is not None:
            local_conn.close()

    try:
        replica_conn = get_replica_conn()
        with replica_conn:
            for operation_index, (sql, params) in enumerate(operations):
                replica_sql = sql
                replica_params = params
                match = re.match(
                    r"^(\s*INSERT\s+INTO\s+[A-Za-z_]\w*\s*)"
                    r"\(([^)]+)\)(\s*VALUES\s*)\(([^)]+)\)",
                    sql,
                    flags=re.IGNORECASE,
                )
                if match and "id" not in {
                    column.strip().lower() for column in match.group(2).split(",")
                }:
                    replica_sql = (
                        f"{match.group(1)}({match.group(2)}, id)"
                        f"{match.group(3)}({match.group(4)}, ?)"
                        f"{sql[match.end():]}"
                    )
                    replica_params = (*params, local_ids[operation_index])
                replica_conn.execute(replica_sql, replica_params)
    except sqlite3.Error as e:
        if replica_conn is not None:
            replica_conn.rollback()
        print(f"[ERROR DB REPLICA] {e}")
        return True, local_ids, f"Guardado local OK, pero falló la réplica: {e}"
    finally:
        if replica_conn is not None:
            replica_conn.close()

    return True, local_ids, None


def replicate_write(sql, params):
    """
    Ejecuta la misma sentencia SQL (INSERT/UPDATE/DELETE) en la base LOCAL
    y luego la replica en la base de RÉPLICA. Devuelve (ok: bool, last_id, error).
    """
    ok, last_ids, error = replicate_transaction([(sql, params)])
    last_id = last_ids[0] if last_ids else None
    return ok, last_id, error
