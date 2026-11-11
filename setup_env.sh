#!/usr/bin/env bash
# Script de instalación del entorno P4 para Ubuntu 20.04 / 22.04 LTS
# Instala: p4c, BMv2 (simple_switch / simple_switch_grpc), Mininet, Scapy e iperf
set -euo pipefail

echo "=== 1. Instalando paquetes base, Mininet, Scapy e iperf ==="
sudo apt-get update
sudo apt-get install -y \
    git curl wget ca-certificates gnupg lsb-release \
    python3 python3-pip python3-scapy \
    mininet iperf tcpdump wireshark-common ethtool net-tools

echo "=== 2. Configurando repositorio de P4lang (p4c, bmv2, PI) ==="
. /etc/os-release
REPO_OS="xUbuntu_${VERSION_ID}"
OBS_URL="https://download.opensuse.org/repositories/home:/p4lang/${REPO_OS}"

echo "deb ${OBS_URL}/ /" | sudo tee /etc/apt/sources.list.d/home:p4lang.list
curl -fsSL "${OBS_URL}/Release.key" | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_p4lang.gpg > /dev/null

sudo apt-get update
sudo apt-get install -y p4lang-p4c p4lang-bmv2 p4lang-pi

echo "=== 3. Instalando librerías de Python para P4Runtime y gráficas ==="
pip3 install --upgrade grpcio protobuf scapy matplotlib

echo "=== 4. Verificando versiones instaladas ==="
p4c --version
simple_switch --version | head -n 1
echo "Entorno listo."
