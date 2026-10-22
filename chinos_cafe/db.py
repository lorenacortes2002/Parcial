# -*- coding: utf-8 -*-
"""
db.py  -  Capa de base de datos y REPLICACION  (CHINOS CAFE S.A.)
------------------------------------------------------------------
Se trabajan DOS bases de datos relacionales (SQLite):

    - PRIMARIA  (DB_PRIMARY)  -> base de datos principal
    - REPLICA   (DB_REPLICA)  -> copia / sincronizacion

Toda escritura (INSERT / UPDATE / DELETE) se ejecuta en AMBAS bases,
de modo que "la data debe estar en ambas (2) DB" (requisito del enunciado).
Ademas se incluye replicar_total() para forzar una sincronizacion
completa Primaria -> Replica.
"""

import os
import sqlite3

# Rutas de las 2 bases de datos (se leen del .env desde app.py)
DB_PRIMARY = os.getenv("DB_PRIMARY", "database/chinos_primary.db")
DB_REPLICA = os.getenv("DB_REPLICA", "database/chinos_replica.db")

# Esquema relacional (3 tablas: pizzas, pedidos, pagos)
ESQUEMA = """
CREATE TABLE IF NOT EXISTS pizzas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT    NOT NULL,
    tamano          TEXT    NOT NULL,
    ingredientes    TEXT    NOT NULL,   -- lista separada por comas (min 2, max 10)
    refresco        TEXT,
    item_adicional  TEXT,
    precio          REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS pedidos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_nombre  TEXT    NOT NULL,
    cliente_correo  TEXT    NOT NULL,
    pizza_id        INTEGER NOT NULL,
    pizza_nombre    TEXT    NOT NULL,
    cantidad        INTEGER NOT NULL,
    refresco        TEXT,
    notas           TEXT,
    subtotal        REAL    NOT NULL,
    flete           REAL    DEFAULT 0,
    total           REAL    NOT NULL,
    estado          TEXT    DEFAULT 'REGISTRADO',
    fecha           TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS pagos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id       INTEGER NOT NULL,
    metodo          TEXT    NOT NULL,   -- YAPPY COMERCIAL
    referencia      TEXT,
    monto           REAL    NOT NULL,
    entrega         TEXT,               -- RETIRO EN SITIO / FLETE A DOMICILIO
    estado          TEXT    DEFAULT 'PAGADO',
    fecha           TEXT    NOT NULL
);
"""


def _conectar(ruta):
    """Abre una conexion SQLite creando la carpeta si no existe."""
    carpeta = os.path.dirname(ruta)
    if carpeta and not os.path.exists(carpeta):
        os.makedirs(carpeta, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row  # permite acceder por nombre de columna
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_db():
    """Crea el esquema en AMBAS bases de datos."""
    for ruta in (DB_PRIMARY, DB_REPLICA):
        try:
            con = _conectar(ruta)
            con.executescript(ESQUEMA)
            con.commit()
            con.close()
        except sqlite3.Error as e:
            print("[ERROR init_db] %s -> %s" % (ruta, e))
            raise


def consultar(sql, params=()):
    """Lectura: SIEMPRE desde la base PRIMARIA. Devuelve lista de filas."""
    try:
        con = _conectar(DB_PRIMARY)
        filas = con.execute(sql, params).fetchall()
        con.close()
        return filas
    except sqlite3.Error as e:
        print("[ERROR consultar] %s" % e)
        return []


def consultar_uno(sql, params=()):
    """Lectura de una sola fila desde la PRIMARIA."""
    filas = consultar(sql, params)
    return filas[0] if filas else None


def escribir(sql, params=()):
    """
    Escritura REPLICADA: ejecuta el mismo INSERT/UPDATE/DELETE en las 2 DB.
    Devuelve el lastrowid de la base PRIMARIA.
    """
    last_id = None
    for ruta in (DB_PRIMARY, DB_REPLICA):
        try:
            con = _conectar(ruta)
            cur = con.execute(sql, params)
            con.commit()
            if ruta == DB_PRIMARY:
                last_id = cur.lastrowid
            con.close()
        except sqlite3.Error as e:
            # Si falla la replica no se detiene la app, solo se avisa.
            print("[ERROR escribir] %s -> %s" % (ruta, e))
            if ruta == DB_PRIMARY:
                raise  # un fallo en la primaria si es critico
    return last_id


def replicar_total():
    """
    Sincronizacion COMPLETA Primaria -> Replica.
    Copia esquemas + datos de las 3 tablas (proceso de replicacion manual).
    Devuelve un dict con el conteo replicado por tabla.
    """
    resumen = {}
    try:
        origen = _conectar(DB_PRIMARY)
        destino = _conectar(DB_REPLICA)
        destino.executescript(ESQUEMA)  # asegura esquema

        for tabla in ("pizzas", "pedidos", "pagos"):
            filas = origen.execute("SELECT * FROM %s" % tabla).fetchall()
            destino.execute("DELETE FROM %s" % tabla)  # limpia replica
            for fila in filas:
                columnas = fila.keys()
                marc = ",".join(["?"] * len(columnas))
                cols = ",".join(columnas)
                destino.execute(
                    "INSERT INTO %s (%s) VALUES (%s)" % (tabla, cols, marc),
                    tuple(fila),
                )
            resumen[tabla] = len(filas)

        destino.commit()
        origen.close()
        destino.close()
    except sqlite3.Error as e:
        print("[ERROR replicar_total] %s" % e)
        raise
    return resumen


def conteos():
    """Devuelve cuantas filas hay en cada DB (para evidenciar replicacion)."""
    info = {}
    for nombre, ruta in (("PRIMARIA", DB_PRIMARY), ("REPLICA", DB_REPLICA)):
        try:
            con = _conectar(ruta)
            info[nombre] = {
                "pizzas": con.execute("SELECT COUNT(*) FROM pizzas").fetchone()[0],
                "pedidos": con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0],
                "pagos": con.execute("SELECT COUNT(*) FROM pagos").fetchone()[0],
            }
            con.close()
        except sqlite3.Error as e:
            print("[ERROR conteos] %s" % e)
            info[nombre] = {"pizzas": 0, "pedidos": 0, "pagos": 0}
    return info
