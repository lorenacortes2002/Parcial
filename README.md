# CHINOS CAFÉ S.A. — Prototipo Web (Examen Parcial 2, Ingeniería Web)

Prototipo CRUD en **Python + Flask** para la I Parte del examen (Caso de Estudio).

## Estructura del proyecto
```
chinos_cafe/
├── app.py              # Rutas Flask (Fábrica, Pedidos, Pagos)
├── database.py         # Conexión y replicación a 2 bases SQLite (local y réplica)
├── utils.py             # Generación de JSON + envío de correo + pago Yappy (simulado)
├── requirements.txt
├── templates/            # Vistas HTML (Jinja2)
├── static/style.css
├── tests/                 # Pruebas automatizadas de los requisitos del prototipo
├── db_local.sqlite3      # Se crea al primer arranque (BD relacional local)
├── db_replica.sqlite3    # Se crea al primer arranque (BD de réplica / VM Veraguas)
└── correos_enviados.log  # Registro de cada intento de envío de correo
```

## 1. Ejecutar en local (para pruebas / capturas de pantalla)
```bash
cd chinos_cafe
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Abrir **http://127.0.0.1:5000**

- `/` → Menú público, separado en **Combos** (pizza + soda), **Combos de 2 pizzas** y **Pizzas individuales**.
- Cada botón «Pedir» conserva la pizza elegida y el resumen del pedido actualiza el subtotal en pantalla.
- `/fabrica` → CRUD de productos (crear, editar, eliminar). Al crear se elige **Combo** (incluye una soda),
  **Combo de 2 pizzas** (dos pizzas individuales diferentes + soda) o **Pizza individual** (sin soda).
  Una pizza que forma parte de un combo de 2 pizzas no se puede eliminar. Cada pizza lleva de 1 a 10 ingredientes; el queso mozzarella es la
  base de todas, por eso no aparece en la lista.
- El catálogo inicia con cinco combos, la versión individual de cada uno, tres pizzas individuales más
  (Margarita, Pepperoni, Jamón y Champiñones) y tres combos de 2 pizzas que las combinan. No permite
  eliminar (ni convertir en pizza) un combo si quedarían menos de cinco (cuentan ambos tipos de combo).
- `/pedidos` → El cliente arma su pedido como un carrito: elige **Combos** o **Pizzas individuales**,
  la cantidad y sus sodas (cantidad, tamaño y sabores), pulsa «Agregar al pedido» y repite con
  otros productos; cada línea se puede quitar. Las sodas tienen precio por tamaño (lata $1.00,
  botella 20 oz $1.50, 1 litro $2.25, 2 litros $3.00); cada combo incluye una lata, así que con un
  tamaño mayor se paga la diferencia y las sodas extra se cobran completas.
  Cada pizza puede llevar un **borde** (como en Domino's): clásico (incluido), ajo y parmesano
  (+$1.00), relleno de queso (+$1.50) o relleno de pepperoni (+$2.00); el precio es por pizza, así
  que en un combo de 2 pizzas se cobra dos veces. Si el pedido es **a domicilio** se suma un
  **flete del 5%** del subtotal de los productos (se guarda en `pedidos.subtotal`, `pedidos.flete`
  y `pedidos.total`). Al confirmar, el pedido
  y sus productos (`pedido_items`) se guardan en `db_local.sqlite3`, se **replican** en
  `db_replica.sqlite3`. Su JSON se guarda en la base de datos (columna `pedidos.json_pedido`, también
  replicada); no se crean archivos JSON. El correo **no** se envía todavía: se envía al confirmarse el pago.
  Si se elige **Flete a domicilio** aparece el campo **Dirección de entrega**, que es obligatorio
  y se guarda en el pedido, su JSON y los correos.
- `/pagos` → Genera un **cobro Yappy** con un código único (p. ej. `CC-7K3P9Q`) y abre
  `/pagos/yappy/<código>`, que ofrece dos formas de pago:
  1. **Código QR**: al escanearlo con el celular se abre `/yappy/pagar/<código>` (simulador de la app
     Yappy); al pulsar «Pagar» el pago queda confirmado y la pantalla de caja muestra
     «¡Pago confirmado!» automáticamente.
  2. **Número Yappy**: el cliente envía el monto al número del comercio con el código en el mensaje;
     el cajero anota el número de transacción recibido y confirma.
  Al confirmar se genera el JSON del pago, se guarda en la base de datos (`pagos.json_pago`) y se
  **envían por correo** al cliente y a la empresa los JSON del pedido y del pago
  tal como están guardados en la base de datos, y el pedido pasa a `PAGADO` (o `PAGADO - DESPACHAR (FLETE)` si eligió flete).
  Si no hay servidor SMTP configurado, el envío queda registrado en `correos_enviados.log` y el sitio avisa. Un pedido pagado no se puede cobrar dos veces.
  El número y el nombre de directorio se configuran con `YAPPY_TELEFONO` y `YAPPY_DIRECTORIO`.
  Para escanear el QR con un celular, este debe estar en la misma red Wi-Fi que la computadora.

### Pruebas del prototipo
Con el entorno virtual activado, ejecutar:
```bash
python -m unittest discover -s tests -v
```
Las pruebas usan bases SQLite temporales y simulan el correo para no enviar mensajes reales.
La tarea de VS Code **Iniciar app Flask** abre la vista local en `http://127.0.0.1:5005`.

La base `db_replica.sqlite3` simula una réplica relacional; no se conecta automáticamente a una
máquina virtual remota. Para una réplica entre equipos, hay que configurar y desplegar un servidor
de base de datos accesible desde ambas máquinas.

### Configurar el correo real
El envío ya está configurado para Gmail con la cuenta `candanedoangel@gmail.com` (en `utils.py`).
Solo falta la **contraseña de aplicación** de Gmail (Cuenta de Google → Seguridad → Verificación
en 2 pasos → Contraseñas de aplicaciones), que **no** se guarda en el código: va en un archivo
`.env` en la carpeta del proyecto (excluido de git). Copiar `.env.example` como `.env` y escribirla
sin espacios:
```
SMTP_PASS=TU_CONTRASENA_DE_APLICACION
```
La app lee `.env` al arrancar. También se puede definir en la terminal (`$env:SMTP_PASS = "..."` en
PowerShell o `export SMTP_PASS=...` en Linux), que tiene prioridad sobre `.env`.
Sin `SMTP_PASS` no se intenta enviar y queda registrado en `correos_enviados.log`.
Para usar otra cuenta o servidor se pueden definir también `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`
y `EMPRESA_CORREO`, y `FLASK_SECRET_KEY` para conservar el carrito al reiniciar la app.
Si `FLASK_SECRET_KEY` no está definida, se genera una clave temporal al iniciar la app.

## 2. Despliegue en el servidor Linux con NGINX (sucursal Veraguas)

En el servidor Linux (Ubuntu/Debian como ejemplo):

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv nginx

# Copiar el proyecto a /var/www/chinos_cafe y crear entorno virtual
cd /var/www/chinos_cafe
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt gunicorn
python -c "import database; database.init_db()"
```

**Ejecutar la app con Gunicorn** (servidor WSGI de producción):
```bash
gunicorn --workers 3 --bind 127.0.0.1:8000 app:app
```

**Configurar NGINX como proxy inverso** — crear `/etc/nginx/sites-available/chinos_cafe`:
```nginx
server {
    listen 80;
    server_name chinoscafe.local 172.20.10.100;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /var/www/chinos_cafe/static/;
    }
}
```
Activar el sitio y habilitar HTTPS:
```bash
sudo ln -s /etc/nginx/sites-available/chinos_cafe /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d chinoscafe.local   # habilita HTTPS
```

## 3. Acceso seguro al servidor: SSH + FTP con Port Knocking

**SSH** (desactivar login root y usar llave pública es lo recomendado):
```bash
sudo nano /etc/ssh/sshd_config
# PermitRootLogin no
# PasswordAuthentication no
sudo systemctl restart sshd
```

**Port Knocking** con `knockd` (oculta los puertos SSH/FTP hasta recibir la secuencia correcta):
```bash
sudo apt install knockd
sudo nano /etc/knockd.conf
```
```ini
[options]
    UseSyslog

[openSSH]
    sequence    = 7000,8000,9000
    seq_timeout = 5
    command     = /sbin/iptables -A INPUT -s %IP% -p tcp --dport 22 -j ACCEPT
    tcpflags    = syn

[closeSSH]
    sequence    = 9000,8000,7000
    seq_timeout = 5
    command     = /sbin/iptables -D INPUT -s %IP% -p tcp --dport 22 -j ACCEPT
    tcpflags    = syn

[openFTP]
    sequence    = 1111,2222,3333
    seq_timeout = 5
    command     = /sbin/iptables -A INPUT -s %IP% -p tcp --dport 21 -j ACCEPT
    tcpflags    = syn
```
Bloquear SSH/FTP por defecto en el firewall y habilitar `knockd`:
```bash
sudo iptables -A INPUT -p tcp --dport 22 -j DROP
sudo iptables -A INPUT -p tcp --dport 21 -j DROP
sudo systemctl enable --now knockd
```
Desde el cliente, para "tocar" y abrir el puerto SSH:
```bash
knock 172.20.10.100 7000 8000 9000
ssh usuario@172.20.10.100
```

## 4. Replicación de datos
`database.py` implementa `replicate_write()`: toda escritura de **pedidos** y **pagos** se
ejecuta primero en `db_local.sqlite3` y luego se replica automáticamente en
`db_replica.sqlite3` (que en el escenario real correría en la máquina virtual/sucursal).
Si la réplica falla, el pedido/pago igual queda guardado localmente y se muestra una
advertencia (no se pierde la transacción).

## 5. Checklist para la sustentación / capturas
- [ ] Captura de `/fabrica` con al menos 5 pizzas creadas (fecha/hora visible en el reloj del SO)
- [ ] Captura de `/pedidos` creando un pedido y su JSON en la columna `pedidos.json_pedido`
- [ ] Captura de `db_local.sqlite3` y `db_replica.sqlite3` mostrando el mismo registro (ej. con DB Browser for SQLite)
- [ ] Captura de `/pagos` confirmando un pago y su JSON en la columna `pagos.json_pago`
- [ ] Captura de NGINX corriendo (`systemctl status nginx`) y el sitio accesible por IP
- [ ] Captura del `knockd` en acción (puerto cerrado → knock → puerto abierto → SSH exitoso)
