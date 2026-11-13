#!/usr/bin/env python3
"""Envía con Scapy una cantidad exacta de paquetes TCP, UDP, ICMP y de otro protocolo."""

import argparse

from scapy.all import ICMP, IP, TCP, UDP, L3RawSocket, Raw, conf, send

# Envía por el kernel para que use la tabla ARP estática de Mininet
conf.L3socket = L3RawSocket

PUERTO = 5001
PROTO_OTRO = 253   # Número de protocolo reservado para experimentos
ETHERNET = 14      # Bytes de la cabecera Ethernet que agrega el kernel


def armar_paquetes(destino, datos):
    # Retorna {protocolo: paquete} con un paquete de ejemplo de cada tipo
    relleno = Raw(b"x" * datos)
    return {
        "TCP": IP(dst=destino) / TCP(dport=PUERTO, flags="S"),
        "UDP": IP(dst=destino) / UDP(dport=PUERTO) / relleno,
        "ICMP": IP(dst=destino) / ICMP() / relleno,
        "Otros": IP(dst=destino, proto=PROTO_OTRO) / relleno,
    }


def esperado(cantidades, datos):
    # Retorna los paquetes y bytes que el switch debería contar
    tramas = {nombre: len(p) + ETHERNET for nombre, p in armar_paquetes("10.0.0.2", datos).items()}
    rst = len(IP() / TCP()) + ETHERNET

    # Lo que va del origen al destino
    ida = (sum(cantidades.values()), sum(cantidades[n] * tramas[n] for n in cantidades))

    # Lo que contesta el destino: un RST por cada SYN y un echo reply por cada ping
    vuelta = (cantidades["TCP"] + cantidades["ICMP"],
              cantidades["TCP"] * rst + cantidades["ICMP"] * tramas["ICMP"])

    return {
        "ida": ida,
        "vuelta": vuelta,
        "TCP": (2 * cantidades["TCP"], cantidades["TCP"] * (tramas["TCP"] + rst)),
        "UDP": (cantidades["UDP"], cantidades["UDP"] * tramas["UDP"]),
        "ICMP": (2 * cantidades["ICMP"], 2 * cantidades["ICMP"] * tramas["ICMP"]),
        "Otros": (cantidades["Otros"], cantidades["Otros"] * tramas["Otros"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Genera tráfico de prueba controlado.")
    parser.add_argument("destino", help="IP del host destino, por ejemplo 10.0.0.2")
    parser.add_argument("--tcp", type=int, default=10, help="cantidad de SYN TCP")
    parser.add_argument("--udp", type=int, default=20, help="cantidad de datagramas UDP")
    parser.add_argument("--icmp", type=int, default=15, help="cantidad de pings (echo request)")
    parser.add_argument("--otros", type=int, default=5, help="cantidad de paquetes de protocolo 253")
    parser.add_argument("--datos", type=int, default=100, help="bytes de datos en UDP, ICMP y otros")
    args = parser.parse_args()

    cantidades = {"TCP": args.tcp, "UDP": args.udp, "ICMP": args.icmp, "Otros": args.otros}
    paquetes = armar_paquetes(args.destino, args.datos)
    origen = paquetes["TCP"][IP].src

    print(f"Enviando de {origen} a {args.destino}:")
    for nombre, paquete in paquetes.items():
        trama = len(paquete) + ETHERNET
        print(f"  {nombre:<6} {cantidades[nombre]:>4} paquetes de {trama} bytes")
        send(paquete, count=cantidades[nombre], inter=0.01, verbose=False)

    e = esperado(cantidades, args.datos)
    print("\nLo que el switch debería contar:")
    print(f"  {'':<28}{'Paquetes':>10}{'Bytes':>10}")
    print(f"  {origen + ' -> ' + args.destino:<28}{e['ida'][0]:>10}{e['ida'][1]:>10}")
    print(f"  {args.destino + ' -> ' + origen:<28}{e['vuelta'][0]:>10}{e['vuelta'][1]:>10}")
    for nombre in cantidades:
        print(f"  {nombre:<28}{e[nombre][0]:>10}{e[nombre][1]:>10}")


if __name__ == "__main__":
    main()
