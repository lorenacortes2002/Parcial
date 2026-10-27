#!/bin/bash
# Configura Port Knocking (knockd) para SSH y FTP en la VM. Ejecutar con: sudo bash deploy/setup_knocking.sh
set -e

# Interfaz de la red host-only (la que tiene 192.168.56.x); por defecto enp0s8.
IFACE=$(ip -4 -o addr show | awk '/192\.168\.56\./ {print $2; exit}')
IFACE=${IFACE:-enp0s8}
echo ">> Interfaz host-only detectada: $IFACE"

# Activar knockd y hacerlo escuchar en esa interfaz.
sed -i 's/^START_KNOCKD=.*/START_KNOCKD=1/' /etc/default/knockd
if grep -q '^#*KNOCKD_OPTS=' /etc/default/knockd; then
    sed -i "s|^#*KNOCKD_OPTS=.*|KNOCKD_OPTS=\"-i $IFACE\"|" /etc/default/knockd
else
    echo "KNOCKD_OPTS=\"-i $IFACE\"" >> /etc/default/knockd
fi
systemctl enable knockd >/dev/null 2>&1 || true
systemctl restart knockd

# Ocultar SSH (22) y FTP (21): quedan invisibles hasta la secuencia de toques.
iptables -D INPUT -s 192.168.56.0/24 -p tcp --dport 22 -j ACCEPT 2>/dev/null || true
iptables -C INPUT -p tcp --dport 22 -j DROP 2>/dev/null || iptables -A INPUT -p tcp --dport 22 -j DROP
iptables -C INPUT -p tcp --dport 21 -j DROP 2>/dev/null || iptables -A INPUT -p tcp --dport 21 -j DROP

echo ">> knockd: $(systemctl is-active knockd)"
echo ">> Reglas de bloqueo (22/21):"
iptables -L INPUT -n | grep -E 'tcp dpt:(22|21)' || echo "   (ninguna)"
echo ">> Listo. SSH: knock 7000 8000 9000 | FTP: knock 1111 2222 3333"
