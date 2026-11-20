#!/usr/bin/env python3
"""Colector de Telemetría In-Band (INT) en Python con Scapy.

Recibe los paquetes clonados por el switch INT Sink (s4) en la interfaz del
host colector (c1-eth0), decodifica la cabecera de control INT y la pila de
saltos, muestra un resumen por flujo cada 5 segundos, señala alertas de
congestión configurables y opcionalmente genera gráficas con matplotlib.
"""

import argparse
from collections import defaultdict
import os
import signal
import struct
import sys
import threading
import time

from scapy.all import IP, sniff

DSCP_INT = 0x5C
INT_CTRL_FMT = "!BBBB"   # hop_count, max_hops, flags(overflow:1, res:7), orig_diffserv
INT_CTRL_LEN = struct.calcsize(INT_CTRL_FMT)
INT_HOP_FMT = "!IHHII"   # switch_id, ingress_port, egress_port, hop_latency, qdepth
INT_HOP_LEN = struct.calcsize(INT_HOP_FMT)

PROTO_NOMBRES = {1: "ICMP", 6: "TCP", 17: "UDP"}


def decodificar_reporte_int(pkt):
    """Extrae metadatos INT de un paquete IPv4 marcado con DSCP_INT.

    Retorna None si el paquete no contiene telemetría INT válida.
    """
    if not pkt.haslayer(IP):
        return None
    ip = pkt[IP]
    if ip.tos != DSCP_INT:
        return None

    payload = bytes(ip.payload)
    if len(payload) < INT_CTRL_LEN:
        return None

    hop_count, max_hops, flags, orig_dscp = struct.unpack(
        INT_CTRL_FMT, payload[:INT_CTRL_LEN]
    )
    overflow = (flags >> 7) & 0x1

    esperado = INT_CTRL_LEN + hop_count * INT_HOP_LEN
    if len(payload) < esperado:
        return None

    # La pila llega en orden inverso (último switch primero); la invertimos
    # para mostrar la ruta en orden real desde Source hasta Sink.
    saltos_inversos = []
    offset = INT_CTRL_LEN
    for _ in range(hop_count):
        sw_id, in_p, out_p, lat_us, qdepth = struct.unpack(
            INT_HOP_FMT, payload[offset : offset + INT_HOP_LEN]
        )
        saltos_inversos.append(
            {
                "switch_id": sw_id,
                "ingress_port": in_p,
                "egress_port": out_p,
                "hop_latency": lat_us,
                "qdepth": qdepth,
            }
        )
        offset += INT_HOP_LEN
    saltos = list(reversed(saltos_inversos))

    # Puerto L4 (TCP/UDP) ubicado justo después de la pila INT
    dst_port = 0
    if ip.proto in (6, 17) and len(payload) >= offset + 4:
        _, dst_port = struct.unpack("!HH", payload[offset : offset + 4])

    return {
        "src_ip": ip.src,
        "dst_ip": ip.dst,
        "proto": PROTO_NOMBRES.get(ip.proto, str(ip.proto)),
        "dst_port": dst_port,
        "hop_count": hop_count,
        "max_hops": max_hops,
        "overflow": overflow,
        "orig_dscp": orig_dscp,
        "saltos": saltos,
    }


class ColectorINT:
    """Agrega reportes INT por flujo, imprime resúmenes periódicos y grafica."""

    def __init__(self, intervalo, umbral_cola, umbral_latencia, ruta_grafica=None):
        self.intervalo = intervalo
        self.umbral_cola = umbral_cola
        self.umbral_latencia = umbral_latencia
        self.ruta_grafica = ruta_grafica

        self.lock = threading.Lock()
        self.inicio = time.time()
        self.total_reportes = 0
        self.num_resumen = 0

        # Estadísticas del intervalo actual agrupadas por (src, dst, proto, dst_port)
        self.ventana = self._nueva_ventana()

        # Serie temporal para graficar con matplotlib (opcional +10%)
        self.historia = defaultdict(lambda: {"t": [], "lat_us": [], "qdepth": []})

    @staticmethod
    def _nueva_ventana():
        return defaultdict(
            lambda: {
                "paquetes": 0,
                "overflows": 0,
                "rutas": defaultdict(int),
                "lat_total": [],
                "por_salto": defaultdict(lambda: {"lat": [], "q": [], "puertos": set()}),
            }
        )

    def procesar_paquete(self, pkt):
        rep = decodificar_reporte_int(pkt)
        if rep is None:
            return

        ahora = time.time() - self.inicio
        flujo = (rep["src_ip"], rep["dst_ip"], rep["proto"], rep["dst_port"])
        ruta = " -> ".join(f"s{h['switch_id']}" for h in rep["saltos"]) or "(sin saltos)"
        lat_e2e = sum(h["hop_latency"] for h in rep["saltos"])

        with self.lock:
            self.total_reportes += 1
            f = self.ventana[flujo]
            f["paquetes"] += 1
            if rep["overflow"]:
                f["overflows"] += 1
            f["rutas"][ruta] += 1
            f["lat_total"].append(lat_e2e)

            for h in rep["saltos"]:
                sw = h["switch_id"]
                slot = f["por_salto"][sw]
                slot["lat"].append(h["hop_latency"])
                slot["q"].append(h["qdepth"])
                slot["puertos"].add((h["ingress_port"], h["egress_port"]))

                hist = self.historia[sw]
                hist["t"].append(ahora)
                hist["lat_us"].append(h["hop_latency"])
                hist["qdepth"].append(h["qdepth"])

    def imprimir_resumen(self):
        with self.lock:
            datos = self.ventana
            self.ventana = self._nueva_ventana()
            self.num_resumen += 1
            n = self.num_resumen
            total = self.total_reportes

        ts = time.strftime("%H:%M:%S")
        print(f"\n{'=' * 74}", flush=True)
        print(
            f"[Resumen #{n} - {ts}] Reportes totales recibidos: {total} "
            f"(umbrales: cola >= {self.umbral_cola} pkts, latencia >= {self.umbral_latencia} us)",
            flush=True,
        )
        print(f"{'=' * 74}", flush=True)

        if not datos:
            print("  (Sin reportes INT en este intervalo)", flush=True)
            return

        for (src, dst, proto, port), f in sorted(datos.items()):
            rutas_txt = ", ".join(
                f"{r} ({c} pkts)" for r, c in sorted(f["rutas"].items(), key=lambda x: -x[1])
            )
            e2e_prom = sum(f["lat_total"]) / len(f["lat_total"])
            e2e_max = max(f["lat_total"])
            ovf_txt = f"  [OVERFLOW: {f['overflows']} pkts]" if f["overflows"] else ""

            print(
                f"\nFlujo {src} -> {dst} ({proto}/{port}) | {f['paquetes']} reportes{ovf_txt}",
                flush=True,
            )
            print(f"  Ruta(s): {rutas_txt}", flush=True)
            print(
                f"  Latencia extremo a extremo: prom={e2e_prom:.1f} us ({e2e_prom/1000:.2f} ms), "
                f"max={e2e_max} us ({e2e_max/1000:.2f} ms)",
                flush=True,
            )
            print(
                f"  {'Switch':<8} {'Puertos(in->out)':<18} {'Lat prom/max (us)':<22} "
                f"{'Cola prom/max':<16} {'Estado'}",
                flush=True,
            )

            for sw, info in sorted(f["por_salto"].items()):
                lat_prom = sum(info["lat"]) / len(info["lat"])
                lat_max = max(info["lat"])
                q_prom = sum(info["q"]) / len(info["q"])
                q_max = max(info["q"])
                puertos_str = ",".join(f"{a}->{b}" for a, b in sorted(info["puertos"]))

                alertas = []
                if q_max >= self.umbral_cola:
                    alertas.append(f"COLA={q_max}")
                if lat_max >= self.umbral_latencia:
                    alertas.append(f"LAT={lat_max}us")

                estado = f"ALERTA CONGESTION ({', '.join(alertas)})" if alertas else "OK"
                print(
                    f"  s{sw:<7} {puertos_str:<18} "
                    f"{lat_prom:>8.1f} / {lat_max:<10} "
                    f"{q_prom:>5.1f} / {q_max:<8} {estado}",
                    flush=True,
                )

    def guardar_grafica(self):
        """Genera gráfica PNG de evolución de latencia y colas por switch (opcional +10%)."""
        if not self.ruta_grafica:
            return
        with self.lock:
            copia = {
                sw: (list(v["t"]), list(v["lat_us"]), list(v["qdepth"]))
                for sw, v in self.historia.items()
                if v["t"]
            }
        if not copia:
            return

        os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-int")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        estilos = {
            1: {"color": "#1f77b4", "linestyle": "-",  "marker": "o", "markersize": 4.5, "linewidth": 2.4, "alpha": 0.85, "zorder": 3},
            2: {"color": "#ff7f0e", "linestyle": "-",  "marker": "s", "markersize": 3.5, "linewidth": 1.8, "alpha": 0.95, "zorder": 4},
            3: {"color": "#2ca02c", "linestyle": "-",  "marker": "^", "markersize": 7.0, "linewidth": 2.0, "alpha": 0.95, "zorder": 6},
            4: {"color": "#9467bd", "linestyle": "--", "marker": "x", "markersize": 5.0, "linewidth": 1.5, "alpha": 0.90, "zorder": 5},
        }

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        for sw in sorted(copia):
            t_raw, lat_raw, qd_raw = copia[sw]
            # Inserta NaN cuando hay pausas > 0.5 s para no dibujar líneas falsas en huecos sin tráfico
            t, lat_ms, qd = [], [], []
            for idx, (ti, li, qi) in enumerate(zip(t_raw, lat_raw, qd_raw)):
                if idx > 0 and (ti - t_raw[idx - 1]) > 0.5:
                    t.append(float("nan"))
                    lat_ms.append(float("nan"))
                    qd.append(float("nan"))
                t.append(ti)
                lat_ms.append(li / 1000.0)
                qd.append(qi)

            st = estilos.get(sw, {"marker": ".", "linewidth": 1.4, "markersize": 4})
            paso = max(1, len(t) // 50)
            ax1.plot(t, lat_ms, markevery=paso, label=f"s{sw}", **st)
            ax2.plot(t, qd, markevery=paso, label=f"s{sw}", **st)

        ax1.axhline(
            self.umbral_latencia / 1000.0,
            color="#d62728",
            linestyle=":",
            linewidth=1.5,
            label=f"Umbral ({self.umbral_latencia/1000:.1f} ms)",
        )
        ax1.set_ylabel("Latencia por salto (ms)")
        ax1.set_title("Telemetría In-Band (INT) - Evolución de Latencia y Profundidad de Cola")
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc="upper right", ncol=2)

        ax2.axhline(
            self.umbral_cola,
            color="#d62728",
            linestyle=":",
            linewidth=1.5,
            label=f"Umbral ({self.umbral_cola} pkts)",
        )
        ax2.set_xlabel("Tiempo (s)")
        ax2.set_ylabel("Profundidad de cola (paquetes)")
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc="upper right", ncol=2)

        os.makedirs(os.path.dirname(os.path.abspath(self.ruta_grafica)), exist_ok=True)
        fig.tight_layout()
        fig.savefig(self.ruta_grafica, dpi=140)
        plt.close(fig)
        print(f"[Colector] Gráfica guardada en {self.ruta_grafica}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Colector de Telemetría In-Band (INT)")
    parser.add_argument("--iface", default="c1-eth0", help="Interfaz de escucha (default: c1-eth0)")
    parser.add_argument("--intervalo", type=float, default=5.0, help="Segundos entre resúmenes (default: 5)")
    parser.add_argument("--umbral-cola", type=int, default=5, help="Alerta si cola >= N paquetes (default: 5)")
    parser.add_argument("--umbral-latencia", type=int, default=5000, help="Alerta si latencia >= N us (default: 5000)")
    parser.add_argument("--grafica", default="logs/telemetria.png", help="Ruta PNG de la gráfica (vacío para desactivar)")
    args = parser.parse_args()

    colector = ColectorINT(
        intervalo=args.intervalo,
        umbral_cola=args.umbral_cola,
        umbral_latencia=args.umbral_latencia,
        ruta_grafica=args.grafica or None,
    )

    detener = threading.Event()

    def manejar_senal(signum, frame):
        detener.set()

    signal.signal(signal.SIGINT, manejar_senal)
    signal.signal(signal.SIGTERM, manejar_senal)

    def ciclo_resumen():
        while not detener.wait(args.intervalo):
            colector.imprimir_resumen()
            if args.grafica:
                colector.guardar_grafica()

    hilo = threading.Thread(target=ciclo_resumen, daemon=True)
    hilo.start()

    print(
        f"[Colector INT] Escuchando en {args.iface} "
        f"(resumen cada {args.intervalo}s, umbral cola={args.umbral_cola}, "
        f"umbral latencia={args.umbral_latencia} us)...",
        flush=True,
    )

    try:
        while not detener.is_set():
            sniff(
                iface=args.iface,
                prn=colector.procesar_paquete,
                store=False,
                timeout=1.0,
                stop_filter=lambda _: detener.is_set(),
            )
    finally:
        detener.set()
        colector.imprimir_resumen()
        if args.grafica:
            colector.guardar_grafica()


if __name__ == "__main__":
    main()
