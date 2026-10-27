# Parte I — Caso de estudio CHINOS CAFÉ S.A. (resumen)

Prototipo web en **Python + Flask**, desplegado en **NGINX sobre Linux** (VM, sucursal
Veraguas), con **replicación de datos** de la PC principal (Chiriquí) a la VM, acceso seguro
por **SSH y FTP con Port Knocking**, y **HTTPS**.

## 1. La aplicación (prototipo)
- **Fábrica:** CRUD de productos. Combos (pizza + soda), combos de 2 pizzas y pizzas
  individuales. Ingredientes 1–10 (el queso mozzarella es la base), refrescos, mínimo 5 combos.
- **Pedidos:** el cliente arma su pedido (varios combos/pizzas), elige borde de la pizza y sodas
  (cantidad, tamaño, sabores). Se guarda en la base local y se **replica** en la VM. Genera un
  JSON que se guarda en la base de datos.
- **Pagos:** cobro con **Yappy** (QR o número), confirmación del pago, flete del 5 % si es a
  domicilio. Al pagar se **envían por correo** los JSON del pedido y del pago (con recibo PDF).
- Control de errores con Try-Catch en toda la app.

## 2. Replicación de datos (PC principal → VM réplica)
- La PC escribe en su base local (`db_local.sqlite3`) y envía cada cambio por HTTP a la VM.
- La VM recibe en `/api/replica`, protegida con una clave compartida (`REPLICA_TOKEN`).
- Si la VM está apagada, el pedido igual se guarda en la PC (aviso de réplica); al volver, se
  reenvía con el botón **⟳ Sincronizar réplica** de la Fábrica o al reiniciar la app de la PC.
- La data queda en **ambas** bases.

## 3. Servidor en la VM (Ubuntu)
- **NGINX** como proxy inverso hacia la app (puerto 5000), sirviendo **HTTP (80)** y **HTTPS (443)**.
- **App como servicio systemd** (`chinos_cafe`): arranca sola y se reinicia si se cae.
- **FTP** con vsftpd (login con el usuario del sistema).
- **SSH** con openssh-server.
- **Port Knocking** (knockd): SSH y FTP quedan ocultos hasta la secuencia de "toques".

---

# Comandos

## A) En la PC (app principal, Windows)
```powershell
# Entorno e instalación
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# .env (no se sube a GitHub): correo y réplica a la VM
#   SMTP_PASS=<contraseña de aplicación de Gmail>
#   REPLICA_TOKEN=<clave larga, la MISMA que en la VM>
#   REPLICA_URL=http://192.168.56.50

# Arrancar la app
python app.py          # abre http://127.0.0.1:5000
```
Sincronizar la réplica manualmente: botón **⟳ Sincronizar réplica** en /fabrica.

## B) En la VM (Ubuntu, sucursal Veraguas)
Red: en VirtualBox, adaptador **Host-only** → la VM queda en `192.168.56.50`.

```bash
# Proyecto
git clone https://github.com/lorenacortes2002/Parcial.git chinos_cafe_pizza
cd chinos_cafe_pizza
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt gunicorn
# .env en la VM: solo REPLICA_TOKEN=<la misma que en la PC>  (NO poner REPLICA_URL)

# App como servicio
sudo cp deploy/chinos_cafe.service /etc/systemd/system/chinos_cafe.service
sudo systemctl daemon-reload
sudo systemctl enable --now chinos_cafe

# HTTPS (certificado autofirmado para la red local)
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/chinos.key -out /etc/nginx/ssl/chinos.crt -subj "/C=PA/ST=Veraguas/L=Santiago/O=CHINOS CAFE/CN=192.168.56.50"
sudo cp deploy/nginx_chinos_cafe.conf /etc/nginx/sites-available/chinos_cafe
sudo ln -sf /etc/nginx/sites-available/chinos_cafe /etc/nginx/sites-enabled/chinos_cafe
sudo nginx -t && sudo systemctl reload nginx

# FTP
sudo apt install -y vsftpd
sudo cp deploy/vsftpd.conf /etc/vsftpd.conf
sudo systemctl enable --now vsftpd && sudo systemctl restart vsftpd

# SSH
sudo apt install -y openssh-server
sudo systemctl enable --now ssh

# Port Knocking (oculta SSH 22 y FTP 21)
sudo apt install -y knockd
sudo cp deploy/knockd.conf /etc/knockd.conf
sudo bash deploy/setup_knocking.sh
# Si el FTP sigue abierto por una regla vieja:
sudo iptables -D INPUT -p tcp --dport 21 -j ACCEPT
```

## C) Demostración del Port Knocking (desde un cliente Linux)
```bash
# SSH: cerrado -> tocar -> abierto
nmap -p 22 192.168.56.50                 # filtered
knock 192.168.56.50 7000 8000 9000
ssh angel@192.168.56.50                  # ahora entra
# FTP:
knock 192.168.56.50 1111 2222 3333
ftp 192.168.56.50
```

## D) Comprobaciones rápidas
```bash
systemctl status chinos_cafe nginx vsftpd knockd   # todos "active (running)"
curl -k https://192.168.56.50/fabrica              # 200 (HTTPS)
```

## Datos del escenario
| Elemento | Valor |
|---|---|
| IP de la VM (host-only) | 192.168.56.50 |
| IP de la PC (host-only) | 192.168.56.1 |
| App Flask (interno) | 127.0.0.1:5000 |
| Web | HTTP 80 / HTTPS 443 |
| Knock SSH | 7000, 8000, 9000 |
| Knock FTP | 1111, 2222, 3333 |
