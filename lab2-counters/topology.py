#!/usr/bin/env python3
"""Topología del Lab 2: un switch P4 (BMv2) con cuatro hosts en 10.0.0.0/24."""

import argparse
import os
import shlex
import socket
import subprocess
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Switch
from mininet.topo import Topo

CARPETA = os.path.dirname(os.path.abspath(__file__))
P4_JSON = os.path.join(CARPETA, "build", "lab2.json")
COMANDOS = os.path.join(CARPETA, "s1-commands.txt")
PUERTO_THRIFT = 9090


def esperar_puerto(puerto, segundos=10):
    # Espera a que simple_switch acepte conexiones en el puerto Thrift
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            socket.create_connection(("localhost", puerto), timeout=1).close()
            return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("simple_switch no arrancó, revisar logs/s1.log")


class P4Switch(Switch):
    """Switch de Mininet que corre simple_switch con el programa compilado."""

    def __init__(self, name, json_path, thrift_port, **kwargs):
        Switch.__init__(self, name, **kwargs)
        self.json_path = json_path
        self.thrift_port = thrift_port

    def start(self, controllers):
        # Arranca simple_switch con un puerto por cada interfaz del switch
        puertos = ""
        for numero, intf in self.intfs.items():
            if intf.name != "lo":
                puertos += f" -i {numero}@{intf.name}"
                # Sin esto el kernel manda IPv6 por el puerto y se cuenta en "Otros"
                self.cmd(f"sysctl -w net.ipv6.conf.{intf.name}.disable_ipv6=1 > /dev/null")
        log = os.path.join(CARPETA, "logs", f"{self.name}.log")
        self.cmd(f"simple_switch --device-id 0 --thrift-port {self.thrift_port}{puertos} "
                 f"{shlex.quote(self.json_path)} > {shlex.quote(log)} 2>&1 &")
        esperar_puerto(self.thrift_port)

    def stop(self, deleteIntfs=True):
        # Detiene simple_switch antes de borrar las interfaces
        self.cmd("kill %simple_switch")
        Switch.stop(self, deleteIntfs)


class Lab2Topo(Topo):
    """El host hN queda conectado al puerto N del switch s1."""

    def build(self):
        s1 = self.addSwitch("s1", cls=P4Switch, json_path=P4_JSON, thrift_port=PUERTO_THRIFT)
        for i in range(1, 5):
            host = self.addHost(f"h{i}", ip=f"10.0.0.{i}/24", mac=f"00:00:00:00:00:0{i}")
            self.addLink(host, s1, port2=i)


def compilar():
    # Compila lab2.p4 a build/lab2.json (p4c no acepta rutas con espacios, por eso va relativo)
    os.makedirs("build", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    subprocess.run(["p4c-bm2-ss", "--p4v", "16", "-o", "build/lab2.json", "lab2.p4"], check=True)


def preparar_hosts(net):
    # Apaga IPv6 y el offload de checksums en cada host
    for host in net.hosts:
        host.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1 > /dev/null")
        host.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1 > /dev/null")
        host.cmd(f"ethtool --offload {host.defaultIntf()} rx off tx off sg off > /dev/null 2>&1")


def cargar_reglas():
    # Instala las entradas de s1-commands.txt con simple_switch_CLI
    with open(COMANDOS) as archivo:
        comandos = archivo.read()
    salida = subprocess.run(["simple_switch_CLI", "--thrift-port", str(PUERTO_THRIFT)],
                            input=comandos, capture_output=True, text=True).stdout
    for linea in salida.splitlines():
        if "Error" in linea or "Invalid" in linea:
            print(linea)


def main():
    parser = argparse.ArgumentParser(description="Levanta la red del Lab 2 en Mininet.")
    parser.add_argument("--verificar", action="store_true",
                        help="corre la prueba automática de verificar.py y sale")
    args = parser.parse_args()

    os.chdir(CARPETA)
    compilar()
    setLogLevel("info")

    net = Mininet(topo=Lab2Topo(), controller=None)
    net.start()
    net.staticArp()
    preparar_hosts(net)
    cargar_reglas()
    info("*** Switch listo: Thrift en el puerto %d\n" % PUERTO_THRIFT)

    if args.verificar:
        import verificar
        verificar.correr(net)
    else:
        CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
