# CHINOS CAFE S.A. — Sistema de pedidos de combos de PIZZA
### Examen Parcial 2 · Ingeniería Web (UTP) · Prof. Napoleón Ibarra

Prototipo **Python + Flask** (CRUD) para la **I Parte** del examen.
Integrantes: **______________ / ______________**

---

## 1. Requisitos
- Python 3.10 o superior (probado en 3.11)
- pip

## 2. Instalación

```bash
cd chinos_cafe
python -m pip install -r requirements.txt
```

## 3. Configuración del correo (SMTP Gmail)

1. Copia `.env.example` como `.env`.
2. En Gmail, activa la verificación en 2 pasos y genera una
   **Contraseña de aplicación** en https://myaccount.google.com/apppasswords
3. Rellena en `.env`:

```
SMTP_USER=tucorreo@gmail.com
SMTP_PASS=la_contraseña_de_aplicacion_de_16_letras
CORREO_EMPRESA=correo_de_la_empresa@gmail.com
CORREO_OPERARIO=correo_del_operario@gmail.com
```

> Si no configuras SMTP, la app **no se rompe**: genera el JSON y guarda una
> copia del correo en `correos_enviados/` (gracias al `try/except`).

## 4. Ejecutar

```bash
python app.py
```

Abre el navegador en **http://127.0.0.1:5000**
(se sirve en `0.0.0.0:5000` para poder ponerlo detrás de NGINX en la Parte II/III).

Al primer arranque se crean las 2 bases de datos y se siembran **6 combos** de pizza.

---

## 5. Qué cumple del enunciado (I Parte)

| Requisito del examen | Dónde está |
|----------------------|-----------|
| Interfaz gráfica en **Python-Flask** | toda la app web |
| **FÁBRICA**: crear/registrar pizzas, ingredientes **2 a 10**, refresco, extra | `/fabrica` (listbox múltiple + combo box) |
| CRUD completo (insertar, actualizar, eliminar) | `/fabrica`, `/fabrica/editar`, `/fabrica/eliminar` |
| **Mínimo 5 combos** por sitio | 6 combos sembrados en `sembrar_combos()` |
| **PEDIDOS**: cliente arma combo (combo box) | `/pedidos` |
| Confirmación por **archivo JSON** + **correo** (empresa/cliente/operario) | `correo.py` → `pedidos_json/` + SMTP |
| Guardar en **DB local relacional** | SQLite `database/chinos_primary.db` |
| **Replicación** en una 2.ª DB (la data en ambas) | `db.escribir()` escribe en las 2 + botón "Sincronizar" |
| **PAGOS**: confirmación de pago por JSON + correo | `/pagos` |
| **YAPPY Comercial** | método de pago en `/pagos` |
| **Flete** si no retira en sitio | opción "Flete a domicilio" (+B/. 3.50) |
| Control de campos **Try/Catch** | `try/except` en todas las rutas y módulos |

### Listbox / Combo box
- **Ingredientes** → `<select multiple>` (listbox, valida 2–10).
- **Tamaño, refresco, ítem adicional, combo, tipo de entrega** → `<select>` (combo box).

### Replicación de datos
- Cada INSERT/UPDATE/DELETE se ejecuta en **`chinos_primary.db`** y **`chinos_replica.db`**.
- El botón **"Sincronizar Primaria → Réplica"** (panel de inicio) fuerza una copia
  completa de las 3 tablas (`replicar_total()`).
- Para la **Parte III** puedes apuntar `DB_REPLICA` (en `.env`) a la base de datos
  de la **Máquina Virtual Linux** en lugar del 2.º archivo local.

---

## 6. Estructura

```
chinos_cafe/
├─ app.py              # rutas Flask (FÁBRICA, PEDIDOS, PAGOS, replicar)
├─ db.py               # 2 DB SQLite + lógica de replicación
├─ correo.py           # genera JSON + envía/registra correo SMTP
├─ requirements.txt
├─ .env.example        # plantilla de configuración
├─ templates/          # base, inicio, fabrica, editar, pedidos, pagos
├─ static/estilos.css
├─ database/           # (se crea) chinos_primary.db + chinos_replica.db
├─ pedidos_json/       # (se crea) JSON de cada pedido/pago
└─ correos_enviados/   # (se crea) copia local de cada correo
```

---

## 7. Capturas para la entrega (recomendación del profesor)
Toma capturas **con fecha/hora** (la barra superior muestra un reloj en vivo) de:
1. Panel con los 6 combos y los conteos de ambas DB (replicación).
2. FÁBRICA: crear, editar y eliminar una pizza.
3. PEDIDOS: armar un combo + aviso de JSON/correo generado.
4. El archivo JSON abierto (`pedidos_json/`).
5. El correo recibido en Gmail (empresa/cliente).
6. PAGOS: pago Yappy con flete + estado "por despachar".
7. Las 2 DB con la misma data (botón sincronizar).
