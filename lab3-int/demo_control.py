#!/usr/bin/env python3
"""Utilidad del plano de control para demos manuales del Lab 3.

Permite cambiar la ruta en vivo o activar/desactivar congestión en s2 sin
memorizar los comandos exactos de simple_switch_CLI:

    python3 demo_control.py --ruta s3
    python3 demo_control.py --ruta s2
    python3 demo_control.py --congestion 80
    python3 demo_control.py --congestion 10000
"""

import argparse
from verify_int import cambiar_ruta_h3, cli


def main():
    parser = argparse.ArgumentParser(description="Control en vivo para demos del Lab 3 (INT)")
    parser.add_argument("--ruta", choices=["s2", "s3"], help="Cambia la ruta hacia h3 por s2 o s3")
    parser.add_argument("--congestion", type=int, help="Ajusta set_queue_rate (pkts/s) en s2 puerto 2")
    args = parser.parse_args()

    if args.ruta:
        cambiar_ruta_h3(args.ruta)
        print(f"[OK] Ruta hacia h3 cambiada a s1 -> {args.ruta} -> s4")

    if args.congestion is not None:
        cli(9091, [f"set_queue_rate {args.congestion} 2"])
        print(f"[OK] Tasa de cola en s2 (puerto 2) ajustada a {args.congestion} paquetes/s")

    if not args.ruta and args.congestion is None:
        parser.print_help()


if __name__ == "__main__":
    main()
