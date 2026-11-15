#!/usr/bin/env python3
"""Topología en Mininet para probar el router IPv4 estático en P4 (3 routers, 4 hosts)."""

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

HOSTS = [
    ("h1", "10.0.1.1/24", "08:00:00:00:01:01", "10.0.1.254", "08:00:00:01:01:00", "r1", 1),
    ("h2", "10.0.2.1/24", "08:00:00:00:02:02", "10.0.2.254", "08:00:00:01:02:00", "r1", 2),
    ("h3", "10.0.3.1/24", "08:00:00:00:03:03", "10.0.3.254", "08:00:00:02:01:00", "r2", 1),
    ("h4", "10.0.4.1/24", "08:00:00:00:04:04", "10.0.4.254", "08:00:00:03:01:00", "r3", 1),
]

ROUTERS = [
    ("r1", 1, 9090, os.path.join(BASE_DIR, "r1-commands.txt")),
    ("r2", 2, 9091, os.path.join(BASE_DIR, "r2-commands.txt")),
    ("r3", 3, 9092, os.path.join(BASE_DIR, "r3-commands.txt")),
]


class P4Router(Switch):
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
        cmd.append("build/router.json")

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
    """Compila router.p4 a JSON de BMv2 (rutas relativas evitan fallos de p4c/cc1 con tildes)."""
    for carpeta in (BUILD_DIR, PCAP_DIR, LOG_DIR):
        os.makedirs(carpeta, exist_ok=True)
    subprocess.run(
        ["p4c", "--target", "bmv2", "--arch", "v1model", "router.p4", "-o", "build"],
        cwd=BASE_DIR,
        check=True,
    )


def esperar_thrift(router, timeout=10.0):
    """Espera a que el puerto Thrift de simple_switch acepte conexiones."""
    limite = time.time() + timeout
    while time.time() < limite:
        if router.proc and router.proc.poll() is not None:
            raise RuntimeError(f"{router.name} terminó inesperadamente (ver logs/{router.name}.log)")
        try:
            with socket.create_connection(("127.0.0.1", router.thrift_port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Thrift de {router.name} no respondió en el puerto {router.thrift_port}")


def cargar_reglas(router, ruta_reglas):
    """Envía las reglas de ipv4_lpm al router usando simple_switch_CLI."""
    esperar_thrift(router)
    with open(ruta_reglas, encoding="utf-8") as f:
        comandos = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

    res = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(router.thrift_port)],
        input="\n".join(comandos) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    if "Error" in res.stdout or "Invalid" in res.stdout:
        raise RuntimeError(f"Error cargando reglas en {router.name}:\n{res.stdout}")


def preparar_interfaz(nombre, host=None):
    """Desactiva offload de checksum e IPv6 para evitar interferencias con BMv2 y Scapy."""
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


def crear_red():
    """Construye la red con 3 routers P4, 4 hosts y reglas estáticas."""
    net = Mininet(controller=None)
    routers = {
        nombre: net.addSwitch(nombre, cls=P4Router, device_id=dev_id, thrift_port=thrift)
        for nombre, dev_id, thrift, _ in ROUTERS
    }

    hosts = {}
    for nombre, ip, mac, gw_ip, _, router_nombre, puerto in HOSTS:
        h = net.addHost(nombre, ip=ip, mac=mac, defaultRoute=f"via {gw_ip}")
        hosts[nombre] = h
        net.addLink(h, routers[router_nombre], port1=0, port2=puerto,
                    intfName1=f"{nombre}-eth0", intfName2=f"{router_nombre}-eth{puerto}")

    # Enlaces entre routers: r1:p3 <-> r2:p2 y r2:p3 <-> r3:p2
    net.addLink(routers["r1"], routers["r2"], port1=3, port2=2,
                intfName1="r1-eth3", intfName2="r2-eth2")
    net.addLink(routers["r2"], routers["r3"], port1=3, port2=2,
                intfName1="r2-eth3", intfName2="r3-eth2")

    net.start()

    for r in routers.values():
        for intf in r.intfs.values():
            if intf.name != "lo":
                preparar_interfaz(intf.name)

    # ARP estático hacia el gateway porque los routers P4 no responden ARP.
    for nombre, _, _, gw_ip, gw_mac, _, _ in HOSTS:
        h = hosts[nombre]
        preparar_interfaz(f"{nombre}-eth0", host=h)
        h.cmd(f"ip neigh replace {gw_ip} lladdr {gw_mac} dev {nombre}-eth0 nud permanent")

    for nombre, _, _, ruta in ROUTERS:
        cargar_reglas(routers[nombre], ruta)

    return net


def correr_pruebas(net):
    """Ejecuta pingall y las pruebas Scapy desde h1."""
    perdida = net.pingAll()
    h1 = net.get("h1")
    print("\n*** Ejecutando verify_router.py desde h1...", flush=True)
    proc = h1.popen(
        ["python3", "-u", os.path.join(BASE_DIR, "verify_router.py")],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for linea in iter(proc.stdout.readline, b""):
        print(linea.decode("utf-8", errors="replace"), end="", flush=True)
    rc = proc.wait()
    return perdida == 0 and rc == 0


def main():
    if os.geteuid() != 0:
        sys.exit("Ejecute este script con sudo.")

    parser = argparse.ArgumentParser(description="Topología Lab 1: Router IPv4 estático en P4")
    parser.add_argument("--test", action="store_true", help="Ejecuta pruebas automáticas y cierra")
    args = parser.parse_args()

    setLogLevel("info")
    compilar_p4()
    net = crear_red()
    try:
        if args.test:
            ok = correr_pruebas(net)
            sys.exit(0 if ok else 1)
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
