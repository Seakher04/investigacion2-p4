#!/usr/bin/env python3
"""Recibe el tráfico de trafico.py sin contestar: UDP en el puerto 5001 y el protocolo 253."""

import select
import signal
import socket
import sys

PUERTO = 5001
PROTO_OTRO = 253


def main():
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("0.0.0.0", PUERTO))
    # Con un socket abierto para el protocolo 253 el kernel no contesta "protocolo inalcanzable"
    otros = socket.socket(socket.AF_INET, socket.SOCK_RAW, PROTO_OTRO)
    recibidos = {"UDP": 0, "Otros": 0}

    # Al detenerlo imprime cuántos paquetes llegaron
    def terminar(*_):
        print(f"Receptor: llegaron {recibidos['UDP']} UDP y {recibidos['Otros']} de protocolo {PROTO_OTRO}")
        sys.exit(0)

    signal.signal(signal.SIGTERM, terminar)
    signal.signal(signal.SIGINT, terminar)
    print(f"Receptor escuchando UDP {PUERTO} y protocolo {PROTO_OTRO}", flush=True)

    while True:
        listos, _, _ = select.select([udp, otros], [], [])
        for s in listos:
            s.recv(2048)
            recibidos["UDP" if s is udp else "Otros"] += 1


if __name__ == "__main__":
    main()
