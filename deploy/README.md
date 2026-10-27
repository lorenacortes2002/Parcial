# Despliegue en la máquina virtual (sucursal Veraguas)

Archivos de configuración del servidor Linux. En la VM: `git pull` y copiar cada uno
a su lugar con `sudo`. Son para el escenario del examen (Parte I).

## HTTPS (NGINX)
```bash
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/chinos.key -out /etc/nginx/ssl/chinos.crt -subj "/C=PA/ST=Veraguas/L=Santiago/O=CHINOS CAFE/CN=192.168.56.50"
sudo cp deploy/nginx_chinos_cafe.conf /etc/nginx/sites-available/chinos_cafe
sudo ln -sf /etc/nginx/sites-available/chinos_cafe /etc/nginx/sites-enabled/chinos_cafe
sudo nginx -t && sudo systemctl reload nginx
```

## FTP (vsftpd)
```bash
sudo apt install -y vsftpd
sudo cp deploy/vsftpd.conf /etc/vsftpd.conf
sudo systemctl enable --now vsftpd
sudo systemctl restart vsftpd
```
Login con el usuario del sistema (angel) y su contraseña.

## Port Knocking (knockd) para SSH y FTP
Un solo comando (detecta la interfaz host-only, activa knockd y oculta 22/21):
```bash
cd ~/Desktop/chinos_cafe_pizza && git pull
sudo bash deploy/setup_knocking.sh
```
Desde el cliente (PC u otra VM), para abrir SSH: `knock 192.168.56.50 7000 8000 9000 && ssh angel@192.168.56.50`.
Para FTP: `knock 192.168.56.50 1111 2222 3333`.

> Las reglas de iptables no sobreviven al reinicio salvo que se guarden
> (`sudo apt install iptables-persistent`). Para la sustentación basta dejarlas puestas.

## App como servicio (para que no se caiga)
```bash
cd ~/Desktop/chinos_cafe_pizza && git pull
source venv/bin/activate && pip install -r requirements.txt
sudo cp deploy/chinos_cafe.service /etc/systemd/system/chinos_cafe.service
sudo fuser -k 5000/tcp 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable --now chinos_cafe
systemctl status chinos_cafe --no-pager | head -6
```
