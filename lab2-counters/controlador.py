#!/usr/bin/env python3
"""Controlador del Lab 2: lee los contadores del switch por Thrift y los imprime."""

import argparse
import socket
import sys
import time

from thrift.protocol import TBinaryProtocol, TMultiplexedProtocol
from thrift.transport import TSocket, TTransport
from bm_runtime.standard import Standard

PUERTO = 9090
TABLA_FLUJOS = "MyIngress.flujos"
PROTOCOLOS = ["TCP", "UDP", "ICMP", "Otros"]
RANGOS = ["< 128 B", "128-255 B", "256-511 B", "512-1023 B", ">= 1024 B"]
REGISTROS = ["MyIngress.bytes_flujo", "MyIngress.tam_max_flujo",
             "MyIngress.flujo_elefante", "MyIngress.histograma_tam"]


def conectar(puerto):
    # Abre la conexión Thrift con simple_switch y retorna el cliente
    transporte = TTransport.TBufferedTransport(TSocket.TSocket("localhost", puerto))
    protocolo = TBinaryProtocol.TBinaryProtocol(transporte)
    servicio = TMultiplexedProtocol.TMultiplexedProtocol(protocolo, "standard")
    transporte.open()
    return Standard.Client(servicio)


def leer_flujos(sw):
    # Retorna una lista con los contadores y registros de cada flujo de la tabla
    flujos = []
    for entrada in sw.bm_mt_get_entries(0, TABLA_FLUJOS):
        flujo_id = int.from_bytes(entrada.action_entry.action_data[0], "big")
        contador = sw.bm_mt_read_counter(0, TABLA_FLUJOS, entrada.entry_handle)
        flujos.append({
            "origen": socket.inet_ntoa(entrada.match_key[0].exact.key),
            "destino": socket.inet_ntoa(entrada.match_key[1].exact.key),
            "paquetes": contador.packets,
            "bytes": contador.bytes,
            "tam_max": sw.bm_register_read(0, "MyIngress.tam_max_flujo", flujo_id),
            "elefante": sw.bm_register_read(0, "MyIngress.flujo_elefante", flujo_id),
        })
    return flujos


def leer_protocolos(sw):
    # Retorna {protocolo: (paquetes, bytes)}
    resultado = {}
    for i, nombre in enumerate(PROTOCOLOS):
        valor = sw.bm_counter_read(0, "MyIngress.contador_protocolo", i)
        resultado[nombre] = (valor.packets, valor.bytes)
    return resultado


def leer_histograma(sw):
    # Retorna la cantidad de paquetes en cada rango de tamaño
    return [sw.bm_register_read(0, "MyIngress.histograma_tam", i) for i in range(len(RANGOS))]


def reiniciar(sw):
    # Pone en cero los contadores y los registros de estadísticas
    sw.bm_mt_reset_counters(0, TABLA_FLUJOS)
    sw.bm_counter_reset_all(0, "MyIngress.contador_protocolo")
    for registro in REGISTROS:
        sw.bm_register_reset(0, registro)


def imprimir(sw, lectura):
    # Imprime en consola las tres tablas de estadísticas
    umbral = sw.bm_register_read(0, "MyIngress.umbral_elefante", 0)
    print(f"\n===== Lectura {lectura} - {time.strftime('%H:%M:%S')} - umbral elefante: {umbral} bytes =====")

    print(f"\n{'Flujo (origen -> destino)':<28}{'Paquetes':>10}{'Bytes':>12}{'Prom.':>8}{'Max.':>7}  Estado")
    activos = [f for f in leer_flujos(sw) if f["paquetes"] > 0]
    for f in activos:
        nombre = f"{f['origen']} -> {f['destino']}"
        promedio = f["bytes"] // f["paquetes"]
        estado = "ELEFANTE" if f["elefante"] else ""
        print(f"{nombre:<28}{f['paquetes']:>10}{f['bytes']:>12}{promedio:>8}{f['tam_max']:>7}  {estado}")
    if not activos:
        print("(ningún flujo tiene tráfico todavía)")

    print(f"\n{'Protocolo':<28}{'Paquetes':>10}{'Bytes':>12}")
    total_paquetes = 0
    total_bytes = 0
    for nombre, (paquetes, cantidad_bytes) in leer_protocolos(sw).items():
        print(f"{nombre:<28}{paquetes:>10}{cantidad_bytes:>12}")
        total_paquetes += paquetes
        total_bytes += cantidad_bytes
    print(f"{'Total':<28}{total_paquetes:>10}{total_bytes:>12}")

    print(f"\n{'Tamaño de trama':<28}{'Paquetes':>10}")
    for rango, cantidad in zip(RANGOS, leer_histograma(sw)):
        print(f"{rango:<28}{cantidad:>10}")


def main():
    parser = argparse.ArgumentParser(description="Lee los contadores del Lab 2 cada cierto tiempo.")
    parser.add_argument("--puerto", type=int, default=PUERTO, help="puerto Thrift del switch")
    parser.add_argument("--intervalo", type=float, default=5, help="segundos entre lecturas (máximo 5)")
    parser.add_argument("--umbral", type=int, help="nuevo umbral de bytes para los flujos elefante")
    parser.add_argument("--reiniciar", action="store_true", help="pone todo en cero antes de empezar")
    parser.add_argument("--lecturas", type=int, default=0, help="cantidad de lecturas (0 = hasta Ctrl+C)")
    args = parser.parse_args()

    if args.intervalo <= 0 or args.intervalo > 5:
        parser.error("el intervalo tiene que estar entre 0 y 5 segundos")

    try:
        sw = conectar(args.puerto)
    except TTransport.TTransportException:
        sys.exit(f"No se pudo conectar al switch en el puerto {args.puerto}. ¿Está corriendo topology.py?")

    if args.reiniciar:
        reiniciar(sw)
        print("Contadores y registros en cero.")
    if args.umbral is not None:
        sw.bm_register_write(0, "MyIngress.umbral_elefante", 0, args.umbral)
        print(f"Umbral de flujo elefante cambiado a {args.umbral} bytes.")

    lectura = 1
    try:
        while True:
            imprimir(sw, lectura)
            if lectura == args.lecturas:
                break
            lectura += 1
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nControlador detenido.")


if __name__ == "__main__":
    main()
