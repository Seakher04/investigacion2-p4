#!/usr/bin/env python3
"""Pruebas con Scapy desde h1 (10.0.1.1) para verificar el router P4."""

import sys
from scapy.all import Ether, ICMP, IP, srp1

SRC_IP = "10.0.1.1"
SRC_MAC = "08:00:00:00:01:01"
GW_MAC = "08:00:00:01:01:00"
IFACE = "h1-eth0"

RUTAS_ESPERADAS = [
    ("h2 (1 salto)", "10.0.2.1", 63),
    ("h3 (2 saltos)", "10.0.3.1", 62),
    ("h4 (3 saltos)", "10.0.4.1", 61),
]


def enviar_icmp(dst_ip, ttl, seq, timeout=0.5):
    """Envía ICMP en capa 2 directo al gateway para no disparar ARP en Scapy."""
    pkt = (
        Ether(src=SRC_MAC, dst=GW_MAC)
        / IP(src=SRC_IP, dst=dst_ip, ttl=ttl)
        / ICMP(id=0x1234, seq=seq)
    )
    return srp1(pkt, iface=IFACE, timeout=timeout, verbose=0)


def main():
    ok = True
    seq = 1

    print("=== 1. Conectividad y decremento de TTL por salto ===", flush=True)
    for nombre, dst_ip, ttl_esperado in RUTAS_ESPERADAS:
        resp = enviar_icmp(dst_ip, ttl=64, seq=seq, timeout=1.0)
        seq += 1
        if resp and resp.haslayer(ICMP) and resp[ICMP].type == 0 and resp[IP].ttl == ttl_esperado:
            print(f"[PASS] {nombre}: respuesta de {dst_ip} con TTL={resp[IP].ttl}", flush=True)
        else:
            ttl_rx = resp[IP].ttl if (resp and resp.haslayer(IP)) else None
            print(f"[FAIL] {nombre}: esperado TTL={ttl_esperado}, recibido={ttl_rx}", flush=True)
            ok = False

    print("\n=== 2. Descarte cuando TTL llega a 0 ===", flush=True)
    for ttl in (0, 1, 2, 3):
        resp = enviar_icmp("10.0.4.1", ttl=ttl, seq=seq)
        seq += 1
        if resp is None:
            print(f"[PASS] Paquete hacia 10.0.4.1 con TTL={ttl} descartado", flush=True)
        else:
            print(f"[FAIL] Paquete con TTL={ttl} no fue descartado", flush=True)
            ok = False

    resp_ttl4 = enviar_icmp("10.0.4.1", ttl=4, seq=seq, timeout=1.0)
    seq += 1
    if resp_ttl4 and resp_ttl4.haslayer(IP):
        print(
            f"[PASS] Paquete hacia 10.0.4.1 con TTL=4 completó los 3 saltos (respuesta TTL={resp_ttl4[IP].ttl})",
            flush=True,
        )
    else:
        print("[FAIL] Paquete hacia 10.0.4.1 con TTL=4 no obtuvo respuesta", flush=True)
        ok = False

    print("\n=== 3. Descarte por defecto cuando no hay ruta ===", flush=True)
    resp_sin_ruta = enviar_icmp("10.99.99.99", ttl=64, seq=seq)
    if resp_sin_ruta is None:
        print("[PASS] Paquete sin ruta hacia 10.99.99.99 descartado por ipv4_lpm", flush=True)
    else:
        print("[FAIL] Paquete sin ruta recibió respuesta inesperada", flush=True)
        ok = False

    print("\nTODAS LAS PRUEBAS PASARON" if ok else "\nALGUNAS PRUEBAS FALLARON", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
