#!/usr/bin/env bash
# Script para instalar p4c, BMv2, Mininet, Scapy e iperf en Ubuntu o Debian.
set -euo pipefail

. /etc/os-release
case "${ID}" in
    ubuntu)
        REPO_OS="xUbuntu_${VERSION_ID}"
        ;;
    debian)
        REPO_OS="Debian_${VERSION_ID}"
        ;;
    *)
        echo "Distribución no soportada: ${ID}. Use Ubuntu o Debian."
        exit 1
        ;;
esac

echo "=== 1. Instalando paquetes base, Mininet, Scapy e iperf ==="
sudo apt-get update
sudo apt-get install -y \
    git curl ca-certificates gnupg \
    python3 python3-scapy python3-grpcio python3-protobuf python3-matplotlib \
    mininet iperf tcpdump wireshark-common ethtool

echo "=== 2. Configurando repositorio de P4lang (${REPO_OS}) ==="
OBS_URL="https://download.opensuse.org/repositories/home:/p4lang/${REPO_OS}"
echo "deb ${OBS_URL}/ /" | sudo tee /etc/apt/sources.list.d/home:p4lang.list
curl -fsSL "${OBS_URL}/Release.key" | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_p4lang.gpg > /dev/null

sudo apt-get update
sudo apt-get install -y p4lang-p4c p4lang-bmv2 p4lang-pi

echo "=== 3. Verificando versiones instaladas ==="
p4c --version
simple_switch --version | head -n 1
echo "Entorno listo."
