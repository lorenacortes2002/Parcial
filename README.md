# CHINOS CAFÉ S.A. — Prototipo Web (Examen Parcial 2, Ingeniería Web)

Prototipo CRUD en **Python + Flask** para la I Parte del examen (Caso de Estudio).

## Estructura del proyecto
```
chinos_cafe/
├── app.py              # Rutas Flask (Fábrica, Pedidos, Pagos)
├── database.py         # Conexión a MariaDB (maestro-esclavo) o, sin MariaDB, a 2 bases SQLite
├── utils.py             # Generación de JSON + envío de correo + pago Yappy (simulado)
├── requirements.txt
├── templates/            # Vistas HTML (Jinja2)
├── static/style.css
├── tests/                 # Pruebas automatizadas de los requisitos del prototipo
├── db_local.sqlite3      # Solo sin MariaDB: BD local (se crea al primer arranque)
├── db_replica.sqlite3    # Solo sin MariaDB: BD de réplica
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
  y sus productos (`pedido_items`) se guardan en el **maestro MariaDB**, que los **replica** al
  esclavo de la máquina virtual (sección 4). Su JSON se guarda en la base de datos (columna `pedidos.json_pedido`, también
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

Las pruebas usan SQLite (bases temporales). Si el `.env` configura MariaDB, además se ejecutan
pruebas contra una base aparte, `chinos_cafe_test` (ver `tests/test_mariadb.py`).

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

## 4. Replicación de datos: MariaDB maestro-esclavo

La app usa **MariaDB** (`DB_MOTOR=mariadb` en el `.env`) y escribe **solo en el servidor maestro**
(PC de la sede principal). MariaDB registra cada cambio en su *registro binario* (binlog) y el
servidor **esclavo** de la máquina virtual (sucursal Veraguas) lo copia automáticamente:
replicación nativa, sin que la app intervenga. El esclavo es de **solo lectura**.

```
 PC (sede principal)                         VM Ubuntu (sucursal Veraguas)
 ┌──────────────────────────┐   binlog     ┌──────────────────────────┐
 │ App Flask ──► MariaDB     │ ───────────► │ MariaDB ESCLAVO          │
 │              MAESTRO      │  (usuario    │ server_id=2, read_only   │
 │ server_id=1, puerto 3307  │  replicador) │ puerto 3306              │
 └──────────────────────────┘              └──────────────────────────┘
        192.168.56.1   ◄── red Host-only de VirtualBox ──►   192.168.56.x
```

La página **Réplica** de la app (`/replica`) muestra el estado del maestro (archivo y posición
del binlog), el del esclavo (hilos IO/SQL, retraso, último error) y compara cuántos registros
tiene cada tabla en ambos servidores.

Sin `DB_MOTOR=mariadb` la app usa SQLite (`db_local.sqlite3` + `db_replica.sqlite3`, la app copia
cada escritura). Así funcionan las pruebas automáticas y los equipos que no tienen MariaDB.

### 4.1 Maestro (PC con Windows)
1. Instalar **MariaDB 11.4 LTS** (en esta PC ya está, como servicio `MariaDB` en el puerto **3307**
   porque el 3306 lo usa MySQL 8):
   ```powershell
   winget install --id MariaDB.Server --version 11.4.3.0 --exact
   ```
2. En `C:\Program Files\MariaDB 11.4\data\my.ini`, sección `[mysqld]`, y reiniciar el servicio:
   ```ini
   port=3307
   server_id=1
   log_bin=mariadb-bin
   binlog_format=ROW
   ```
3. Firewall: permitir el puerto 3307 desde la red de VirtualBox (como administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "MariaDB 3307 VirtualBox" -Direction Inbound -Protocol TCP `
     -LocalPort 3307 -RemoteAddress 192.168.56.0/24 -Profile Any -Action Allow
   ```
4. Base de datos y usuarios (como `root`; las contraseñas son las del `.env`):
   ```sql
   CREATE DATABASE chinos_cafe CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'chinos_app'@'localhost' IDENTIFIED BY '<DB_PASSWORD>';
   CREATE USER 'chinos_app'@'127.0.0.1' IDENTIFIED BY '<DB_PASSWORD>';
   GRANT ALL PRIVILEGES ON chinos_cafe.* TO 'chinos_app'@'localhost', 'chinos_app'@'127.0.0.1';
   GRANT BINLOG MONITOR ON *.* TO 'chinos_app'@'localhost', 'chinos_app'@'127.0.0.1';
   CREATE USER 'replicador'@'%' IDENTIFIED BY '<REPLICACION_PASSWORD>';
   GRANT REPLICATION SLAVE ON *.* TO 'replicador'@'%';
   CREATE USER 'chinos_monitor'@'%' IDENTIFIED BY '<DB_REPLICA_PASSWORD>';
   GRANT SLAVE MONITOR ON *.* TO 'chinos_monitor'@'%';
   GRANT SELECT ON chinos_cafe.* TO 'chinos_monitor'@'%';
   ```
   Como el binlog se activó **antes** de crear la base, todo su historial (tablas, catálogo y
   usuarios) está en el binlog y el esclavo lo copia completo al arrancar.
5. En el `.env` de la PC: `DB_MOTOR=mariadb`, `DB_HOST`, `DB_PORT=3307`, `DB_NAME`, `DB_USER`,
   `DB_PASSWORD` (ver `.env.example`). Al ejecutar `python app.py` se crean las tablas y el
   catálogo inicial.

### 4.2 Esclavo (máquina virtual Ubuntu en VirtualBox)
> Recomendado: **Ubuntu Server 24.04 LTS** (soporte hasta 2029). Ubuntu 25.04 ya no tiene
> soporte y `apt` puede fallar al instalar paquetes.

1. **Red:** en VirtualBox → *Configuración* → *Red*, un adaptador en **Solo anfitrión
   (Host-only)** → *VirtualBox Host-Only Ethernet Adapter*. En la VM, `ip -4 addr` muestra su IP
   `192.168.56.x`; desde la VM, la PC es `192.168.56.1`. Comprobar: `nc -zv 192.168.56.1 3307`.
2. **Instalar MariaDB 11.4** (misma versión que el maestro o más nueva) desde el repositorio
   oficial:
   ```bash
   sudo apt update && sudo apt install -y curl
   curl -LsS https://r.mariadb.com/downloads/mariadb_repo_setup | \
     sudo bash -s -- --mariadb-server-version="mariadb-11.4"
   sudo apt install -y mariadb-server
   ```
3. **Configurar como esclavo:** crear `/etc/mysql/mariadb.conf.d/60-replica.cnf`:
   ```ini
   [mysqld]
   server_id = 2
   read_only = 1
   relay_log = relay-bin
   replicate_ignore_db = chinos_cafe_test
   bind-address = 0.0.0.0
   ```
   ```bash
   sudo systemctl restart mariadb
   sudo ufw allow from 192.168.56.0/24 to any port 3306 proto tcp   # si ufw está activo
   ```
4. **Conectar con el maestro y arrancar la réplica** (`sudo mariadb`):
   ```sql
   CHANGE MASTER TO
     MASTER_HOST='192.168.56.1',
     MASTER_PORT=3307,
     MASTER_USER='replicador',
     MASTER_PASSWORD='<REPLICACION_PASSWORD del .env de la PC>',
     MASTER_USE_GTID=slave_pos;
   START SLAVE;
   SHOW SLAVE STATUS\G
   ```
   Debe mostrar `Slave_IO_Running: Yes`, `Slave_SQL_Running: Yes` y `Seconds_Behind_Master: 0`.
   Comprobar los datos: `sudo mariadb -e "SELECT tipo, COUNT(*) FROM chinos_cafe.pizzas GROUP BY tipo;"`.
5. **Ver el esclavo desde la app:** en el `.env` de la PC poner `DB_REPLICA_HOST=<IP de la VM>`
   y abrir la página **Réplica**. Al crear un pedido en la PC, aparece en el esclavo al instante.

> Si la VM está apagada, la app sigue funcionando con normalidad: al encenderla, el esclavo se
> pone al día solo, leyendo del binlog lo que se perdió.

## 5. Checklist para la sustentación / capturas
- [ ] Captura de `/fabrica` con al menos 5 pizzas creadas (fecha/hora visible en el reloj del SO)
- [ ] Captura de `/pedidos` creando un pedido y su JSON en la columna `pedidos.json_pedido`
- [ ] Captura de la página **Réplica** con el esclavo «Replicando» y las tablas «Igual»
- [ ] Captura de `SHOW SLAVE STATUS\G` en la VM y del mismo pedido consultado en el maestro y en el esclavo
- [ ] Captura de `/pagos` confirmando un pago y su JSON en la columna `pagos.json_pago`
- [ ] Captura de NGINX corriendo (`systemctl status nginx`) y el sitio accesible por IP
- [ ] Captura del `knockd` en acción (puerto cerrado → knock → puerto abierto → SSH exitoso)
