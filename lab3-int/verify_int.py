#!/usr/bin/env python3
"""Pruebas automáticas para el Laboratorio 3: Telemetría In-Band (INT).

Se ejecuta con:
    sudo python3 topology.py --test

Verifica todos los requisitos obligatorios del enunciado:
  1. Watchlist vs. no-watchlist y paquete limpio (sin cabeceras INT) en h3.
  2. Límite máximo de saltos (flag overflow = 1 cuando hop_count == max_hops).
  3. Congestión provocada con iperf + set_queue_rate y alerta en el colector.
  4. Cambio de ruta en tiempo de ejecución desde el control plane (s2 -> s3).
  5. Generación de gráfica de evolución de latencia y cola (matplotlib, +10%).
"""

import json
import os
import re
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")


def cli(thrift_port, comandos):
    """Ejecuta comandos en simple_switch_CLI y retorna stdout."""
    res = subprocess.run(
        ["simple_switch_CLI", "--thrift-port", str(thrift_port)],
        input="\n".join(comandos) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    if "Error" in res.stdout or "Invalid" in res.stdout:
        raise RuntimeError(f"Error CLI (puerto {thrift_port}):\n{res.stdout}")
    return res.stdout


def obtener_handle(thrift_port, tabla, patron):
    """Busca el entry handle de una regla en table_dump que contenga `patron`."""
    out = cli(thrift_port, [f"table_dump {tabla}"])
    handle_actual = None
    bloque = []
    for linea in out.splitlines():
        m = re.search(r"Dumping entry (0x[0-9a-fA-F]+)", linea)
        if m:
            if handle_actual is not None and patron in "\n".join(bloque):
                return int(handle_actual, 16)
            handle_actual = m.group(1)
            bloque = [linea]
        else:
            bloque.append(linea)
    if handle_actual is not None and patron in "\n".join(bloque):
        return int(handle_actual, 16)
    raise RuntimeError(f"No se encontró regla '{patron}' en {tabla} (puerto {thrift_port})")


def cambiar_ruta_h3(camino):
    """Cambia en caliente la ruta hacia 10.0.3.0/24 en s1 ('s2' o 's3')."""
    handle = obtener_handle(9090, "MyIngress.ipv4_lpm", "0a000300/24")
    if camino == "s3":
        params = "08:00:00:01:04:00 08:00:00:03:01:00 4"
    else:
        params = "08:00:00:01:03:00 08:00:00:02:01:00 3"
    cli(9090, [f"table_modify MyIngress.ipv4_lpm MyIngress.ipv4_forward {handle} {params}"])


def cambiar_max_hops_udp(max_hops):
    """Cambia max_hops de la regla UDP/5001 de h1->h3 en la watchlist de s1."""
    handle = obtener_handle(9090, "MyIngress.int_watchlist", "0a000101")
    cli(9090, [f"table_modify MyIngress.int_watchlist MyIngress.activate_int {handle} {max_hops}"])


def capturar_en_host(host, iface, timeout, modo):
    """Lanza una captura Scapy breve en un host y devuelve el resultado en JSON."""
    script = f"""
import json, struct
from scapy.all import IP, UDP, Raw, sniff

DSCP_INT = 0x5C
resultados = []

def cb(pkt):
    if not pkt.haslayer(IP):
        return
    ip = pkt[IP]
    if {modo!r} == "colector":
        if ip.tos != DSCP_INT:
            return
        payload = bytes(ip.payload)
        if len(payload) < 4:
            return
        hop_count, max_hops, flags, orig_dscp = struct.unpack("!BBBB", payload[:4])
        overflow = (flags >> 7) & 1
        saltos = []
        off = 4
        for _ in range(hop_count):
            sw, inp, outp, lat, qd = struct.unpack("!IHHII", payload[off:off+16])
            saltos.append({{"sw": sw, "in": inp, "out": outp, "lat": lat, "q": qd}})
            off += 16
        saltos.reverse()
        dport = struct.unpack("!HH", payload[off:off+4])[1] if len(payload) >= off + 4 else 0
        resultados.append({{
            "src": ip.src, "dst": ip.dst, "proto": ip.proto, "dport": dport,
            "hop_count": hop_count, "max_hops": max_hops, "overflow": overflow,
            "ruta": [s["sw"] for s in saltos], "saltos": saltos,
        }})
    else:
        if pkt.haslayer(UDP) and ip.dst == "10.0.3.1":
            data = bytes(pkt[Raw].load).decode("utf-8", errors="ignore") if pkt.haslayer(Raw) else ""
            resultados.append({{
                "src": ip.src, "dst": ip.dst, "tos": ip.tos,
                "dport": pkt[UDP].dport, "data": data,
            }})

sniff(iface={iface!r}, prn=cb, store=False, timeout={timeout})
print(json.dumps(resultados))
"""
    return host.popen(["python3", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)


HOST_INFO = {
    "h1": ("10.0.1.1", "08:00:00:00:01:01", "08:00:00:01:01:00", "h1-eth0"),
    "h2": ("10.0.2.1", "08:00:00:00:02:02", "08:00:00:01:02:00", "h2-eth0"),
}


def enviar_udp(host, dst_ip, dst_port, mensaje, cantidad=3):
    """Envía paquetes UDP en capa 2 directo al gateway con Scapy."""
    src_ip, src_mac, gw_mac, iface = HOST_INFO[host.name]
    script = (
        "from scapy.all import Ether, IP, UDP, Raw, sendp\n"
        f"pkt = Ether(src={src_mac!r}, dst={gw_mac!r}) / "
        f"IP(src={src_ip!r}, dst={dst_ip!r}, ttl=64) / "
        f"UDP(sport=44444, dport={dst_port}) / "
        f"Raw(load={mensaje!r})\n"
        f"sendp(pkt, iface={iface!r}, count={cantidad}, inter=0.05, verbose=0)\n"
    )
    proc = host.popen(["python3", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = proc.communicate(timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(f"Error enviando UDP desde {host.name}: {err.decode('utf-8', errors='replace')}")


def leer_json_proc(proc):
    out, err = proc.communicate(timeout=15)
    texto = out.decode("utf-8", errors="replace").strip()
    if not texto:
        raise RuntimeError(f"Captura sin salida. stderr: {err.decode('utf-8', errors='replace')}")
    return json.loads(texto.splitlines()[-1])


def correr_pruebas(net):
    h1, h2, h3, c1 = net.get("h1", "h2", "h3", "c1")
    ok = True

    print("\n=== 1. Watchlist vs. No-Watchlist y paquete limpio en h3 ===", flush=True)
    p_c1 = capturar_en_host(c1, "c1-eth0", timeout=3.0, modo="colector")
    p_h3 = capturar_en_host(h3, "h3-eth0", timeout=3.0, modo="destino")
    time.sleep(0.5)

    # Flujo monitoreado (en watchlist): h1 -> h3 UDP/5001
    enviar_udp(h1, "10.0.3.1", 5001, "INT-MONITOREADO", cantidad=3)
    # Flujos NO monitoreados: h2 -> h3 UDP/5001 y h1 -> h3 UDP/6000
    enviar_udp(h2, "10.0.3.1", 5001, "SIN-INT-H2", cantidad=2)
    enviar_udp(h1, "10.0.3.1", 6000, "SIN-INT-PUERTO", cantidad=2)

    reps_c1 = leer_json_proc(p_c1)
    pkts_h3 = leer_json_proc(p_h3)

    monitoreados = [r for r in reps_c1 if r["src"] == "10.0.1.1" and r["dport"] == 5001]
    no_monitoreados = [r for r in reps_c1 if not (r["src"] == "10.0.1.1" and r["dport"] == 5001)]
    if len(monitoreados) >= 3 and len(no_monitoreados) == 0 and monitoreados[0]["ruta"] == [1, 2, 4]:
        print(
            f"[PASS] Watchlist: {len(monitoreados)} reportes para h1->h3 UDP/5001 "
            f"(ruta s1->s2->s4), 0 para flujos fuera de watchlist",
            flush=True,
        )
    else:
        print(f"[FAIL] Watchlist: monitoreados={len(monitoreados)}, otros={len(no_monitoreados)}", flush=True)
        ok = False

    h3_mon = [p for p in pkts_h3 if p["data"] == "INT-MONITOREADO"]
    h3_sin = [p for p in pkts_h3 if p["data"] in ("SIN-INT-H2", "SIN-INT-PUERTO")]
    if len(h3_mon) >= 3 and all(p["tos"] == 0 for p in h3_mon) and len(h3_sin) >= 4:
        print(
            f"[PASS] Destino h3 recibió {len(h3_mon)} paquetes del flujo INT completamente limpios "
            f"(tos=0, payload intacto) y {len(h3_sin)} sin INT",
            flush=True,
        )
    else:
        print(f"[FAIL] Destino h3: h3_mon={h3_mon}, h3_sin={len(h3_sin)}", flush=True)
        ok = False

    print("\n=== 2. Límite máximo de saltos (overflow) ===", flush=True)
    cambiar_max_hops_udp(2)
    p_c1 = capturar_en_host(c1, "c1-eth0", timeout=2.5, modo="colector")
    p_h3 = capturar_en_host(h3, "h3-eth0", timeout=2.5, modo="destino")
    time.sleep(0.4)
    enviar_udp(h1, "10.0.3.1", 5001, "TEST-OVERFLOW", cantidad=2)
    reps_ovf = leer_json_proc(p_c1)
    pkts_ovf = leer_json_proc(p_h3)
    cambiar_max_hops_udp(8)

    if (
        reps_ovf
        and reps_ovf[0]["hop_count"] == 2
        and reps_ovf[0]["overflow"] == 1
        and any(p["data"] == "TEST-OVERFLOW" and p["tos"] == 0 for p in pkts_ovf)
    ):
        print(
            f"[PASS] Límite max_hops=2 respetado: hop_count={reps_ovf[0]['hop_count']}, "
            f"overflow={reps_ovf[0]['overflow']}, paquete entregado limpio a h3",
            flush=True,
        )
    else:
        print(f"[FAIL] Overflow: reps={reps_ovf}", flush=True)
        ok = False

    print("\n=== 3. Congestión con iperf + set_queue_rate y alerta en colector ===", flush=True)
    ruta_grafica = os.path.join(LOG_DIR, "telemetria.png")
    if os.path.exists(ruta_grafica):
        os.remove(ruta_grafica)

    log_col = os.path.join(LOG_DIR, "collector_test.log")
    f_col = open(log_col, "w", encoding="utf-8")
    proc_col = c1.popen(
        [
            "python3", "-u", os.path.join(BASE_DIR, "collector.py"),
            "--iface", "c1-eth0",
            "--intervalo", "5",
            "--umbral-cola", "3",
            "--umbral-latencia", "3000",
            "--grafica", ruta_grafica,
        ],
        stdout=f_col,
        stderr=subprocess.STDOUT,
    )
    time.sleep(0.8)

    proc_srv = h3.popen(["iperf", "-s", "-u", "-p", "5001"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)

    # Fase A: tráfico normal por s1 -> s2 -> s4 (sin congestión)
    h1.cmd("iperf -c 10.0.3.1 -u -p 5001 -l 1000 -b 200K -t 1 > /dev/null 2>&1")

    # Fase B: limitar la cola del puerto 2 de s2 (hacia s4) a 80 paquetes/s para provocar congestión
    cli(9091, ["set_queue_rate 80 2"])
    h1.cmd("iperf -c 10.0.3.1 -u -p 5001 -l 1000 -b 2M -t 2 > /dev/null 2>&1")

    # Fase C: restaurar la tasa de cola de s2 y enviar tráfico normal para observar recuperación
    cli(9091, ["set_queue_rate 10000 2"])
    h1.cmd("iperf -c 10.0.3.1 -u -p 5001 -l 1000 -b 200K -t 2 > /dev/null 2>&1")

    print("\n=== 4. Cambio de ruta en caliente desde el control plane (s2 -> s3) ===", flush=True)
    cambiar_ruta_h3("s3")
    time.sleep(0.2)
    h1.cmd("iperf -c 10.0.3.1 -u -p 5001 -l 1000 -b 200K -t 2 > /dev/null 2>&1")
    time.sleep(0.5)

    # Detener colector e iperf para que el colector imprima el resumen final y guarde la gráfica
    proc_col.terminate()
    try:
        proc_col.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc_col.kill()
    f_col.close()

    proc_srv.terminate()
    try:
        proc_srv.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc_srv.kill()

    with open(log_col, encoding="utf-8") as f:
        salida_col = f.read()

    print("\n--- Salida del colector (collector.py) ---", flush=True)
    print(salida_col.strip(), flush=True)
    print("--- Fin de salida del colector ---\n", flush=True)

    if "ALERTA CONGESTION" in salida_col:
        print("[PASS] Colector detectó congestión (cola/latencia por encima del umbral)", flush=True)
    else:
        print("[FAIL] Colector no reportó ALERTA CONGESTION", flush=True)
        ok = False

    if "s1 -> s3 -> s4" in salida_col:
        print("[PASS] Colector reflejó el cambio de ruta en vivo: s1 -> s3 -> s4", flush=True)
    else:
        print("[FAIL] Colector no reflejó la nueva ruta s1 -> s3 -> s4", flush=True)
        ok = False

    if os.path.exists(ruta_grafica) and os.path.getsize(ruta_grafica) > 0:
        print(f"[PASS] Gráfica matplotlib generada correctamente en {ruta_grafica}", flush=True)
    else:
        print("[FAIL] No se generó la gráfica matplotlib", flush=True)
        ok = False

    print("\nTODAS LAS PRUEBAS PASARON" if ok else "\nALGUNAS PRUEBAS FALLARON", flush=True)
    return ok
