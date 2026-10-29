# Parte III — Simulación de Ataque / Mitigación (laboratorio aislado)

Escenario **local y controlado, sin acceso a internet**, con dos máquinas virtuales propias:

| VM | Rol | IP fija |
|----|-----|---------|
| Servidor (Ubuntu) | Sitio web NGINX (víctima a proteger) | 172.20.10.100 |
| Atacante (Kali Linux) | Nmap, Wireshark, Hydra, Burp/ZAP | 172.20.10.50 |

> Todo se hace sobre tus propias VMs, en una red aislada. Es una práctica educativa de
> seguridad: primero se atacan los servicios y luego se **mitigan**.

## 0. Red aislada (sin internet) en VirtualBox
En las DOS VMs, con ellas apagadas: *Configuración → Red → Adaptador 1 → Conectado a:*
**Red interna**, mismo nombre en ambas (p. ej. `examen_lan`). Así quedan solas, sin internet
ni acceso al host. (Instala los programas ANTES de aislarlas, o usa un segundo adaptador NAT
temporal solo para instalar.)

### IP fija — Servidor (Ubuntu, netplan)
`/etc/netplan/99-lab.yaml`:
```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      addresses: [172.20.10.100/24]
```
```bash
sudo netplan apply
ip -4 addr   # debe mostrar 172.20.10.100
```

### IP fija — Atacante (Kali)
```bash
sudo ip addr add 172.20.10.50/24 dev eth0
sudo ip link set eth0 up
ping 172.20.10.100   # debe responder
```

## 1. Servidor web NGINX con IP fija + HTTPS (8080/8443)
En la VM servidor:
```bash
# Certificado para la red del laboratorio
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/lab.key -out /etc/nginx/ssl/lab.crt -subj "/C=PA/O=CHINOS CAFE LAB/CN=172.20.10.100"
# Sitio del laboratorio (HTTP 8080 -> HTTPS 8443) con rate-limiting
sudo cp deploy/parte3/nginx_servidor_8080.conf /etc/nginx/sites-available/servidor_lab
sudo ln -sf /etc/nginx/sites-available/servidor_lab /etc/nginx/sites-enabled/servidor_lab
sudo nginx -t && sudo systemctl reload nginx
```
Comprobar desde Kali: `curl -k https://172.20.10.100:8443` (debe responder la app).

## 2. Escaneo de puertos — Nmap (desde Kali)
```bash
nmap -sS -sV -p- 172.20.10.100            # puertos y servicios
nmap -A 172.20.10.100                      # detección de SO y versiones
nmap --script http-headers,ssl-cert -p 8443 172.20.10.100
```
Captura: el reporte de Nmap mostrando el puerto 8080/8443 (NGINX) detectado.

## 3. Captura de tráfico — Wireshark
En Kali (o en el servidor): abrir **Wireshark**, interfaz `eth0`, filtro `ip.addr == 172.20.10.100`.
Mientras corre, generar tráfico (curl o el navegador) y capturar el intercambio TLS (Client Hello,
Server Hello) y las peticiones HTTP. Captura: la ventana de Wireshark con los paquetes.

## 4. Prueba de estrés / DoS controlada (desde Kali)
> Es contra TU propio servidor en la red aislada, para observar la mitigación (rate-limiting).
```bash
# Carga con ApacheBench: 2000 peticiones, 100 concurrentes
sudo apt install -y apache2-utils
ab -n 2000 -c 100 https://172.20.10.100:8443/
```
Con el `limit_req` de NGINX activo, muchas peticiones reciben **503** (rechazadas) en vez de
tumbar el sitio. Captura: el resumen de `ab` con las peticiones fallidas y el sitio aún en línea.

## 5. Fuerza bruta — Hydra (SSH / FTP / HTTP) (desde Kali)
> Hydra prueba contraseñas. Úsalo contra TUS servicios en la red aislada, con una lista corta.
```bash
# Lista de prueba
printf 'admin\n1234\npassword\nangel\nchinos\n' > claves.txt
# SSH
hydra -l angel -P claves.txt ssh://172.20.10.100
# FTP
hydra -l angel -P claves.txt ftp://172.20.10.100
# Formulario/HTTP básico
hydra -l admin -P claves.txt 172.20.10.100 -s 8443 https-get /
```
Con **fail2ban** activo, tras 5 intentos la IP del atacante queda **baneada**. Captura: Hydra
siendo cortado y `sudo fail2ban-client status sshd` mostrando la IP baneada.

## 6. Escaneo de seguridad — Burp Suite / OWASP ZAP (desde Kali)
- **OWASP ZAP:** `zaproxy` → *Automated Scan* → URL `https://172.20.10.100:8443` → *Attack*.
- **Burp Suite Community:** configurar el navegador con el proxy de Burp (127.0.0.1:8080),
  navegar el sitio, y usar *Target → Site map* y el escáner pasivo.
Captura: el panel de alertas/hallazgos (cabeceras de seguridad, cookies, etc.).

## 7. Mitigación (defensa) — en la VM servidor
```bash
# fail2ban (banea fuerza bruta de SSH/FTP/HTTP)
sudo apt install -y fail2ban
sudo cp deploy/parte3/fail2ban_jail.local /etc/fail2ban/jail.local
sudo systemctl enable --now fail2ban
sudo fail2ban-client status

# Ya aplicadas en la Parte I y que cuentan como mitigación:
#  - HTTPS (tráfico cifrado)                -> contra sniffing de Wireshark
#  - Port Knocking (SSH/FTP ocultos)        -> contra escaneo y fuerza bruta
#  - server_tokens off + cabeceras seguras  -> contra fingerprinting
#  - limit_req en NGINX                      -> contra DoS/fuerza bruta HTTP
```

## Resumen de mitigaciones por ataque
| Ataque | Mitigación |
|--------|-----------|
| Escaneo de puertos (Nmap) | Port Knocking (22/21 ocultos), server_tokens off |
| Sniffing (Wireshark) | HTTPS (TLS) |
| DoS / estrés (ab) | limit_req (rate-limiting) en NGINX |
| Fuerza bruta (Hydra) | fail2ban + Port Knocking |
| Escaneo web (ZAP/Burp) | Cabeceras de seguridad, HTTPS, validación en la app |
