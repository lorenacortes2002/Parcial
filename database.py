"""
database.py
-------------------------------------------------
Acceso a la base de datos. Hay dos motores, según DB_MOTOR (archivo .env):

  - mariadb -> MariaDB (motor principal). La app escribe SOLO en el servidor
               MAESTRO (PC de la sede principal, Chiriquí) y MariaDB replica
               cada cambio por sí solo al servidor ESCLAVO de la máquina
               virtual (sucursal Veraguas): replicación nativa maestro-esclavo
               con el registro binario (binlog).
  - sqlite  -> (por defecto) dos archivos SQLite: db_local.sqlite3 y
               db_replica.sqlite3, y la app copia cada escritura a la réplica.
               Se usa en las pruebas automáticas y en equipos sin MariaDB.

Todas las operaciones están protegidas con TRY/EXCEPT, tal como lo pide
el examen (control de errores en los campos / operaciones).
-------------------------------------------------
"""

import os
import re
import sqlite3

import pymysql

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_LOCAL_PATH = os.path.join(BASE_DIR, "db_local.sqlite3")
DB_REPLICA_PATH = os.path.join(BASE_DIR, "db_replica.sqlite3")

# Errores de base de datos de ambos motores (para usar en "except Error").
Error = (sqlite3.Error, pymysql.MySQLError)

TABLAS = ("pizzas", "pedidos", "pedido_items", "pagos", "cobros_yappy")


def motor():
    """Motor configurado: "mariadb" o "sqlite" (por defecto)."""
    return os.environ.get("DB_MOTOR", "sqlite").strip().lower()


def usa_mariadb():
    return motor() == "mariadb"


def es_duplicado(error):
    """True si el error es una violación de clave única (en SQLite o MariaDB)."""
    texto = str(error or "")
    return "UNIQUE" in texto or "Duplicate entry" in texto


# ----------------------------------------------------------------------
# MariaDB: conexión con la misma interfaz que sqlite3 (conn.execute,
# "with conn", filas que se leen por nombre o por posición)
# ----------------------------------------------------------------------
class Fila(tuple):
    """Fila que se lee por posición (fila[0]) o por nombre (fila["id"])."""

    def __new__(cls, valores, indices):
        fila = super().__new__(cls, valores)
        fila._indices = indices
        return fila

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return tuple.__getitem__(self, self._indices[clave])
        return tuple.__getitem__(self, clave)

    def keys(self):
        return list(self._indices)


class _CursorMariaDB:
    def __init__(self, cursor):
        self._cursor = cursor
        columnas = [c[0] for c in cursor.description] if cursor.description else []
        self._indices = {nombre: i for i, nombre in enumerate(columnas)}
        self.description = cursor.description
        self.lastrowid = cursor.lastrowid

    def fetchone(self):
        fila = self._cursor.fetchone()
        return Fila(fila, self._indices) if fila is not None else None

    def fetchall(self):
        return [Fila(fila, self._indices) for fila in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class ConexionMariaDB:
    """Envuelve una conexión PyMySQL para usarla igual que una de sqlite3."""

    def __init__(self, conexion):
        self._conexion = conexion

    @staticmethod
    def _traducir(sql):
        # sqlite3 usa "?" como marcador y PyMySQL "%s" (los "%" literales van dobles).
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql, params=()):
        cursor = self._conexion.cursor()
        cursor.execute(self._traducir(sql), tuple(params))
        return _CursorMariaDB(cursor)

    def commit(self):
        self._conexion.commit()

    def rollback(self):
        self._conexion.rollback()

    def close(self):
        self._conexion.close()

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traza):
        # Igual que sqlite3: confirma si todo salió bien, deshace si hubo error.
        if tipo is None:
            self.commit()
        else:
            self.rollback()
        return False


def conectar_mariadb(host=None, port=None, user=None, password=None, database=None):
    """Abre una conexión a MariaDB (por defecto, el maestro configurado en .env)."""
    conexion = pymysql.connect(
        host=host or os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(port or os.environ.get("DB_PORT", 3306)),
        user=user or os.environ.get("DB_USER", "chinos_app"),
        password=password if password is not None else os.environ.get("DB_PASSWORD", ""),
        database=database or os.environ.get("DB_NAME", "chinos_cafe"),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=5,
    )
    # "||" concatena textos, igual que en SQLite (por defecto en MariaDB es OR).
    with conexion.cursor() as cursor:
        cursor.execute("SET SESSION sql_mode = CONCAT(@@SESSION.sql_mode, ',PIPES_AS_CONCAT')")
    return ConexionMariaDB(conexion)


SCHEMA_MARIADB = [
    """
    CREATE TABLE IF NOT EXISTS pizzas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(120) NOT NULL,
        ingredientes TEXT NOT NULL,
        refresco VARCHAR(40) NULL,
        precio DOUBLE NOT NULL DEFAULT 5.00,
        entrega VARCHAR(20) NOT NULL DEFAULT 'AMBOS',
        tipo VARCHAR(10) NOT NULL DEFAULT 'COMBO',
        pizza1_id INT NULL,
        pizza2_id INT NULL,
        FOREIGN KEY (pizza1_id) REFERENCES pizzas(id),
        FOREIGN KEY (pizza2_id) REFERENCES pizzas(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS pedidos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        cliente VARCHAR(120) NOT NULL,
        correo_cliente VARCHAR(160) NOT NULL,
        pizza_id INT NOT NULL,
        refresco TEXT NULL,
        refresco_cantidad INT NOT NULL DEFAULT 1,
        refresco_tamano VARCHAR(20) NULL,
        cantidad INT NOT NULL DEFAULT 1,
        subtotal DOUBLE NULL,
        flete DOUBLE NOT NULL DEFAULT 0,
        total DOUBLE NOT NULL,
        estado VARCHAR(40) NOT NULL DEFAULT 'PENDIENTE',
        retiro_o_flete VARCHAR(20) NOT NULL DEFAULT 'RETIRO EN SITIO',
        direccion VARCHAR(300) NULL,
        fecha VARCHAR(19) NOT NULL,
        detalle TEXT NULL,
        json_pedido MEDIUMTEXT NULL,
        FOREIGN KEY (pizza_id) REFERENCES pizzas(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS pagos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL UNIQUE,
        metodo VARCHAR(160) NOT NULL DEFAULT 'YAPPY COMERCIAL',
        monto DOUBLE NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'CONFIRMADO',
        fecha VARCHAR(19) NOT NULL,
        json_pago MEDIUMTEXT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS pedido_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        pizza_id INT NOT NULL,
        cantidad INT NOT NULL,
        precio_unitario DOUBLE NOT NULL,
        borde VARCHAR(20) NOT NULL DEFAULT 'CLASICO',
        precio_borde DOUBLE NOT NULL DEFAULT 0,
        sodas TEXT NOT NULL,
        sodas_cantidad INT NOT NULL DEFAULT 0,
        sodas_tamano VARCHAR(20) NULL,
        precio_sodas DOUBLE NOT NULL DEFAULT 0,
        subtotal DOUBLE NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
        FOREIGN KEY (pizza_id) REFERENCES pizzas(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS cobros_yappy (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        codigo VARCHAR(20) NOT NULL UNIQUE,
        monto DOUBLE NOT NULL,
        estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
        referencia VARCHAR(40) NULL,
        fecha VARCHAR(19) NOT NULL,
        fecha_pago VARCHAR(19) NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

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
    subtotal REAL,                              -- productos (sin flete)
    flete REAL NOT NULL DEFAULT 0,              -- 5% del subtotal si es a domicilio
    total REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',   -- PENDIENTE / CONFIRMADO / PAGADO / DESPACHADO
    retiro_o_flete TEXT NOT NULL DEFAULT 'RETIRO EN SITIO',
    direccion TEXT,                             -- obligatoria solo si es FLETE A DOMICILIO
    fecha TEXT NOT NULL,
    detalle TEXT,                               -- resumen: "2× Combo Hawaiana, 1× Pizza Margarita"
    json_pedido TEXT,                           -- JSON de confirmación del pedido
    FOREIGN KEY (pizza_id) REFERENCES pizzas(id)
);

CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    metodo TEXT NOT NULL DEFAULT 'YAPPY COMERCIAL',
    monto REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'CONFIRMADO',
    fecha TEXT NOT NULL,
    json_pago TEXT,                             -- JSON de confirmación del pago
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
);

-- Productos de cada pedido (un pedido puede tener varios combos y pizzas).
CREATE TABLE IF NOT EXISTS pedido_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER NOT NULL,
    pizza_id INTEGER NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    borde TEXT NOT NULL DEFAULT 'CLASICO',      -- CLASICO / AJO / QUESO / PEPPERONI
    precio_borde REAL NOT NULL DEFAULT 0,
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
    if "json_pedido" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN json_pedido TEXT")
    if "subtotal" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN subtotal REAL")
    if "flete" not in columnas:
        conn.execute("ALTER TABLE pedidos ADD COLUMN flete REAL NOT NULL DEFAULT 0")
    items = {row["name"] for row in conn.execute("PRAGMA table_info(pedido_items)")}
    if "borde" not in items:
        conn.execute("ALTER TABLE pedido_items ADD COLUMN borde TEXT NOT NULL DEFAULT 'CLASICO'")
    if "precio_borde" not in items:
        conn.execute("ALTER TABLE pedido_items ADD COLUMN precio_borde REAL NOT NULL DEFAULT 0")
    if "json_pago" not in {row["name"] for row in conn.execute("PRAGMA table_info(pagos)")}:
        conn.execute("ALTER TABLE pagos ADD COLUMN json_pago TEXT")
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
    """Conexión a la base principal: el maestro MariaDB o db_local.sqlite3."""
    if usa_mariadb():
        return conectar_mariadb()
    return _connect(DB_LOCAL_PATH)


def get_replica_conn():
    return _connect(DB_REPLICA_PATH)


def init_db():
    """Crea las tablas si no existen y carga el catálogo inicial."""
    if usa_mariadb():
        # En MariaDB se crean solo en el maestro: el esclavo las recibe por replicación.
        conn = get_local_conn()
        try:
            with conn:
                for sentencia in SCHEMA_MARIADB:
                    conn.execute(sentencia)
        finally:
            conn.close()
        _cargar_catalogo()
        return

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

    pizzas = _cargar_catalogo()

    # En SQLite la app copia el catálogo a la réplica con sus mismos IDs.
    try:
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
        print(f"[ERROR DB] No se pudo replicar el catálogo de ejemplo: {e}")
        raise


def _cargar_catalogo():
    """
    Garantiza el catálogo inicial (cinco combos, sus versiones individuales,
    otras pizzas individuales y combos de 2 pizzas). El queso mozzarella es la
    base de todas las pizzas, por eso no aparece en la lista de ingredientes.
    Devuelve todas las pizzas.
    """
    conn = get_local_conn()
    try:
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
        return conn.execute("SELECT * FROM pizzas ORDER BY id").fetchall()
    except Error as e:
        print(f"[ERROR DB] No se pudo preparar el catálogo de ejemplo: {e}")
        raise
    finally:
        conn.close()


def replicate_transaction(operations):
    """
    Aplica un grupo de escrituras como una sola transacción. En MariaDB se
    escribe solo en el maestro (el esclavo se actualiza por replicación nativa);
    en SQLite se copian a la réplica conservando los IDs de los inserts.
    """
    local_conn = None
    replica_conn = None
    local_ids = []
    try:
        local_conn = get_local_conn()
        with local_conn:
            for sql, params in operations:
                cur = local_conn.execute(sql, params)
                local_ids.append(cur.lastrowid)
    except Error as e:
        if local_conn is not None:
            local_conn.rollback()
        print(f"[ERROR DB LOCAL] {e}")
        return False, None, str(e)
    finally:
        if local_conn is not None:
            local_conn.close()

    if usa_mariadb():
        return True, local_ids, None

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


# ----------------------------------------------------------------------
# Estado de la replicación (página «Réplica»)
# ----------------------------------------------------------------------
def _contar_tablas(conn):
    return {
        tabla: conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in TABLAS
    }


def estado_replicacion():
    """
    Resume el estado de la replicación para mostrarlo en la app.
    En MariaDB consulta el maestro (SHOW BINLOG STATUS) y, si DB_REPLICA_HOST
    está configurado, el esclavo de la máquina virtual (SHOW SLAVE STATUS).
    """
    estado = {"motor": motor(), "maestro": None, "esclavo": None, "error_esclavo": None}

    if not usa_mariadb():
        for clave, ruta in (("maestro", DB_LOCAL_PATH), ("esclavo", DB_REPLICA_PATH)):
            conn = _connect(ruta)
            try:
                estado[clave] = {"nombre": os.path.basename(ruta), "conteos": _contar_tablas(conn)}
            finally:
                conn.close()
        return estado

    conn = get_local_conn()
    try:
        binlog = conn.execute("SHOW BINLOG STATUS").fetchone()
        estado["maestro"] = {
            "host": f"{os.environ.get('DB_HOST', '127.0.0.1')}:{os.environ.get('DB_PORT', 3306)}",
            "version": conn.execute("SELECT VERSION()").fetchone()[0],
            "server_id": conn.execute("SELECT @@server_id").fetchone()[0],
            "binlog": f"{binlog['File']} · posición {binlog['Position']}" if binlog else "desactivado",
            "gtid": conn.execute("SELECT @@gtid_binlog_pos").fetchone()[0],
            "conteos": _contar_tablas(conn),
        }
    finally:
        conn.close()

    host = os.environ.get("DB_REPLICA_HOST", "").strip()
    if not host:
        return estado
    try:
        esclavo = conectar_mariadb(
            host=host,
            port=os.environ.get("DB_REPLICA_PORT", 3306),
            user=os.environ.get("DB_REPLICA_USER", "chinos_monitor"),
            password=os.environ.get("DB_REPLICA_PASSWORD", ""),
        )
    except Error as e:
        estado["error_esclavo"] = f"No se pudo conectar con el esclavo {host}: {e}"
        return estado
    try:
        fila = esclavo.execute("SHOW SLAVE STATUS").fetchone()
        estado["esclavo"] = {
            "host": f"{host}:{os.environ.get('DB_REPLICA_PORT', 3306)}",
            "version": esclavo.execute("SELECT VERSION()").fetchone()[0],
            "server_id": esclavo.execute("SELECT @@server_id").fetchone()[0],
            "read_only": bool(esclavo.execute("SELECT @@read_only").fetchone()[0]),
            "configurado": fila is not None,
            "io": fila["Slave_IO_Running"] if fila else "No",
            "sql": fila["Slave_SQL_Running"] if fila else "No",
            "retraso": fila["Seconds_Behind_Master"] if fila else None,
            "maestro": f"{fila['Master_Host']}:{fila['Master_Port']}" if fila else "-",
            "gtid": fila["Gtid_IO_Pos"] if fila else "",
            "error": (fila["Last_IO_Error"] or fila["Last_SQL_Error"]) if fila else "",
            "conteos": _contar_tablas(esclavo),
        }
    except Error as e:
        estado["error_esclavo"] = f"No se pudo leer el estado del esclavo: {e}"
    finally:
        esclavo.close()
    return estado
