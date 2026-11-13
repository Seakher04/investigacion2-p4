#!/usr/bin/env python3
"""Prueba del Lab 2: manda tráfico conocido y lo compara con lo que contó el switch.

Se corre con: sudo python3 topology.py --verificar
"""

import time

import controlador
import trafico

CANTIDADES = {"TCP": 10, "UDP": 20, "ICMP": 15, "Otros": 5}
DATOS = 100


def revisar(nombre, esperado, contado):
    # Imprime una fila de la comparación y retorna True si coinciden
    estado = "OK" if esperado == contado else "NO COINCIDE"
    print(f"{nombre:<28}{esperado[0]:>9}{contado[0]:>9}{esperado[1]:>10}{contado[1]:>10}   {estado}")
    return esperado == contado


def buscar_flujo(sw, origen, destino):
    # Retorna los datos del flujo origen -> destino
    for flujo in controlador.leer_flujos(sw):
        if flujo["origen"] == origen and flujo["destino"] == destino:
            return flujo
    return None


def correr(net):
    h1, h2, h3, h4 = net.get("h1", "h2", "h3", "h4")
    sw = controlador.conectar(controlador.PUERTO)
    controlador.reiniciar(sw)
    todo_bien = True

    print("\n=== 1) Tráfico conocido de h1 a h2 con Scapy ===")
    h2.cmd("python3 receptor.py > logs/receptor.log 2>&1 &")
    time.sleep(1)
    print(h1.cmd(f"python3 trafico.py 10.0.0.2 --tcp {CANTIDADES['TCP']} --udp {CANTIDADES['UDP']} "
                 f"--icmp {CANTIDADES['ICMP']} --otros {CANTIDADES['Otros']} --datos {DATOS}"))
    time.sleep(1)
    h2.cmd("kill %python3; wait")
    print(h2.cmd("tail -n 1 logs/receptor.log"))

    e = trafico.esperado(CANTIDADES, DATOS)
    ida = buscar_flujo(sw, "10.0.0.1", "10.0.0.2")
    vuelta = buscar_flujo(sw, "10.0.0.2", "10.0.0.1")
    protocolos = controlador.leer_protocolos(sw)

    print(f"{'':<28}{'Paquetes':>18}{'Bytes':>20}")
    print(f"{'':<28}{'esperado':>9}{'switch':>9}{'esperado':>10}{'switch':>10}")
    todo_bien &= revisar("Flujo 10.0.0.1 -> 10.0.0.2", e["ida"], (ida["paquetes"], ida["bytes"]))
    todo_bien &= revisar("Flujo 10.0.0.2 -> 10.0.0.1", e["vuelta"], (vuelta["paquetes"], vuelta["bytes"]))
    for nombre in controlador.PROTOCOLOS:
        todo_bien &= revisar(nombre, e[nombre], protocolos[nombre])

    print("\n=== 2) Flujo grande de h3 a h4 con iperf (TCP, 5 s) ===")
    h4.cmd("iperf -s > /dev/null 2>&1 &")
    time.sleep(1)
    print(h3.cmd("iperf -c 10.0.0.4 -t 5"))
    h4.cmd("kill %iperf; wait")

    umbral = sw.bm_register_read(0, "MyIngress.umbral_elefante", 0)
    grande = buscar_flujo(sw, "10.0.0.3", "10.0.0.4")
    ida = buscar_flujo(sw, "10.0.0.1", "10.0.0.2")
    print(f"Umbral: {umbral} bytes")
    print(f"10.0.0.3 -> 10.0.0.4: {grande['bytes']} bytes, marcado como elefante: {grande['elefante'] == 1}")
    print(f"10.0.0.1 -> 10.0.0.2: {ida['bytes']} bytes, marcado como elefante: {ida['elefante'] == 1}")
    todo_bien &= grande["elefante"] == 1 and ida["elefante"] == 0

    print("\n=== 3) Así lo muestra el controlador ===")
    controlador.imprimir(sw, 1)

    print("\nResultado: " + ("todo coincide" if todo_bien else "HAY DIFERENCIAS"))
