#!/usr/bin/env python3
"""Topología en Mininet para el Laboratorio 3: Telemetría In-Band (INT).

Topología en diamante con 4 switches P4, dos caminos alternativos, 3 hosts
generadores/receptores de tráfico y 1 host colector:

            +-- s2 (id=2) --+
  h1 ---+   |               |   +--- h3 (destino)
        s1 -+               +- s4
  h2 ---+   |               |   +--- c1 (colector)
            +-- s3 (id=3) --+
"""

import argparse
import os
import socket
import subprocess
import sys
import time

from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import Switch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(BASE_DIR, "build")
PCAP_DIR = os.path.join(BASE_DIR, "pcaps")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# (nombre, ip/mascara, mac, gw_ip, gw_mac, switch, puerto_switch)
HOSTS = [
    ("h1", "10.0.1.1/24", "08:00:00:00:01:01", "10.0.1.254", "08:00:00:01:01:00", "s1", 1),
    ("h2", "10.0.2.1/24", "08:00:00:00:02:02", "10.0.2.254", "08:00:00:01:02:00", "s1", 2),
    ("h3", "10.0.3.1/24", "08:00:00:00:03:03", "10.0.3.254", "08:00:00:04:01:00", "s4", 1),
    ("c1", "10.0.4.1/24", "08:00:00:00:04:04", "10.0.4.254", "08:00:00:04:04:00", "s4", 4),
]

# (nombre, device_id, thrift_port, archivo_reglas)
SWITCHES = [
    ("s1", 1, 9090, os.path.join(BASE_DIR, "s1-commands.txt")),
    ("s2", 2, 9091, os.path.join(BASE_DIR, "s2-commands.txt")),
    ("s3", 3, 9092, os.path.join(BASE_DIR, "s3-commands.txt")),
    ("s4", 4, 9093, os.path.join(BASE_DIR, "s4-commands.txt")),
]


class P4INTSwitch(Switch):
    """Switch BMv2 (simple_switch) administrado desde Mininet."""

    def __init__(self, name, device_id=1, thrift_port=9090, **kwargs):
        super().__init__(name, **kwargs)
        self.device_id = device_id
        self.thrift_port = thrift_port
        self.proc = None
        self._log_file = None

    def start(self, controllers):
        cmd = [
            "simple_switch",
            "--device-id", str(self.device_id),
            "--thrift-port", str(self.thrift_port),
            "--pcap", "pcaps",
        ]
        for port, intf in sorted(self.intfs.items()):
            if intf.name != "lo":
                cmd.extend(["-i", f"{port}@{intf.name}"])
        cmd.append("build/int.json")

        self._log_file = open(os.path.join(LOG_DIR, f"{self.name}.log"), "w")
        self.proc = subprocess.Popen(
            cmd, cwd=BASE_DIR, stdout=self._log_file, stderr=subprocess.STDOUT
        )

    def stop(self, deleteIntfs=True):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self._log_file:
            self._log_file.close()
        super().stop(deleteIntfs)


def compilar_p4():
    """Compila int.p4 a build/int.json usando rutas relativas."""
    for carpeta in (BUILD_DIR, PCAP_DIR, LOG_DIR):
        os.makedirs(carpeta, exist_ok=True)
    subprocess.run(
        ["p4c", "--target", "bmv2", "--arch", "v1model", "int.p4", "-o", "build"],
        cwd=BASE_DIR,
        check=True,
    )


def esperar_thrift(sw, timeout=10.0):
    """Espera a que el puerto Thrift del switch BMv2 acepte conexiones."""
    limite = time.time() + timeout
    while time.time() < limite:
        if sw.proc and sw.proc.poll() is not None:
            raise RuntimeError(f"{sw.name} terminó inesperadamente (ver logs/{sw.name}.log)")
        try:
            with socket.create_connection(("127.0.0.1", sw.thrift_port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Thrift de {sw.name} no respondió en el puerto {sw.thrift_port}")


def ejecutar_cli(thrift_port, comandos):
    """Envía una lista de comandos a simple_switch_CLI y valida la respuesta."""
    res = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
        input="\n".join(comandos) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    if "Error" in res.stdout or "Invalid" in res.stdout:
        raise RuntimeError(f"Error en simple_switch_CLI (puerto {thrift_port}):\n{res.stdout}")
    return res.stdout


def cargar_reglas(sw, ruta_reglas):
    """Carga un archivo de comandos en el switch vía simple_switch_CLI."""
    esperar_thrift(sw)
    with open(ruta_reglas, encoding="utf-8") as f:
        comandos = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    ejecutar_cli(sw.thrift_port, comandos)


def preparar_interfaz(nombre, host=None, mtu=None):
    """Desactiva offload de checksum e IPv6 y opcionalmente ajusta el MTU."""
    for flag in ("rx", "tx", "sg"):
        cmd = f"ethtool -K {nombre} {flag} off"
        if host:
            host.cmd(f"{cmd} >/dev/null 2>&1 || true")
        else:
            subprocess.run(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    sysctl_cmd = f"sysctl -w net.ipv6.conf.{nombre}.disable_ipv6=1"
    if host:
        host.cmd(f"{sysctl_cmd} >/dev/null 2>&1 || true")
    else:
        subprocess.run(sysctl_cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if mtu is not None:
        mtu_cmd = f"ip link set dev {nombre} mtu {mtu}"
        if host:
            host.cmd(f"{mtu_cmd} >/dev/null 2>&1 || true")
        else:
            subprocess.run(mtu_cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def crear_red():
    """Construye la red en diamante con 4 switches P4, 3 hosts y 1 colector."""
    net = Mininet(controller=None)
    switches = {
        nombre: net.addSwitch(nombre, cls=P4INTSwitch, device_id=dev_id, thrift_port=thrift)
        for nombre, dev_id, thrift, _ in SWITCHES
    }

    hosts = {}
    for nombre, ip, mac, gw_ip, _, sw_nombre, puerto in HOSTS:
        h = net.addHost(nombre, ip=ip, mac=mac, defaultRoute=f"via {gw_ip}")
        hosts[nombre] = h
        net.addLink(
            h, switches[sw_nombre], port1=0, port2=puerto,
            intfName1=f"{nombre}-eth0", intfName2=f"{sw_nombre}-eth{puerto}",
        )

    # Camino superior: s1:3 <-> s2:1 y s2:2 <-> s4:2
    net.addLink(switches["s1"], switches["s2"], port1=3, port2=1,
                intfName1="s1-eth3", intfName2="s2-eth1")
    net.addLink(switches["s2"], switches["s4"], port1=2, port2=2,
                intfName1="s2-eth2", intfName2="s4-eth2")

    # Camino inferior alternativo: s1:4 <-> s3:1 y s3:2 <-> s4:3
    net.addLink(switches["s1"], switches["s3"], port1=4, port2=1,
                intfName1="s1-eth4", intfName2="s3-eth1")
    net.addLink(switches["s3"], switches["s4"], port1=2, port2=3,
                intfName1="s3-eth2", intfName2="s4-eth3")

    net.start()

    for sw in switches.values():
        for intf in sw.intfs.values():
            if intf.name != "lo":
                # MTU mayor a 1500 en enlaces internos para acomodar las cabeceras INT
                preparar_interfaz(intf.name, mtu=1800)

    # ARP estático hacia el gateway en cada host
    for nombre, _, _, gw_ip, gw_mac, _, _ in HOSTS:
        h = hosts[nombre]
        mtu_host = 1800 if nombre == "c1" else None
        preparar_interfaz(f"{nombre}-eth0", host=h, mtu=mtu_host)
        h.cmd(f"ip neigh replace {gw_ip} lladdr {gw_mac} dev {nombre}-eth0 nud permanent")

    for nombre, _, _, ruta in SWITCHES:
        cargar_reglas(switches[nombre], ruta)

    return net


def main():
    if os.geteuid() != 0:
        sys.exit("Ejecute este script con sudo.")

    parser = argparse.ArgumentParser(description="Topología Lab 3: Telemetría In-Band (INT)")
    parser.add_argument("--test", action="store_true", help="Ejecuta pruebas automáticas y cierra")
    args = parser.parse_args()

    setLogLevel("info")
    compilar_p4()
    net = crear_red()
    try:
        if args.test:
            import verify_int
            ok = verify_int.correr_pruebas(net)
            sys.exit(0 if ok else 1)
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
