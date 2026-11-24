# Redes Programables con P4: Investigación y Laboratorio Base

Curso: Redes de Comunicación de Datos (CI-0121)  
Escuela de Ciencias de la Computación e Informática  
Universidad de Costa Rica

## Integrantes
- Hermes Josué Rojas Sancho (C16882)
- Marina Castro Peralta (C31886)
- Sebastián Sánchez Jiménez (C4J761)

---

## Video Demostrativo

- [Ver video demostrativo en YouTube](https://youtu.be/fxOKgFDrxVI)

---

## Estructura del Repositorio

El repositorio está organizado según los entregables de la sección 5.1 del enunciado:

```text
.
├── setup_env.sh               # Instala p4c, BMv2, Mininet, Scapy e iperf
├── lab1-router/               # Implementación 1: Router IPv4 estático (Sebastián)
│   ├── router.p4
│   ├── r1-commands.txt
│   ├── r2-commands.txt
│   ├── r3-commands.txt
│   ├── topology.py
│   ├── verify_router.py
│   └── README.md
├── lab2-counters/             # Implementación 2: Contadores y estadísticas (Marina)
│   ├── lab2.p4
│   ├── s1-commands.txt
│   ├── topology.py
│   ├── controlador.py
│   ├── trafico.py
│   ├── receptor.py
│   ├── verificar.py
│   └── README.md
├── lab3-int/                  # Implementación 3: Telemetría In-Band INT (Hermes)
│   ├── int.p4
│   ├── s1-commands.txt .. s4-commands.txt
│   ├── topology.py
│   ├── collector.py
│   ├── demo_control.py
│   ├── verify_int.py
│   └── README.md
└── informe/                   # Informe escrito de la investigación (informe.pdf)
```

---

## Instalación del Entorno

Probado para Ubuntu (20.04 / 22.04 / 24.04) y Debian (11 / 12 / 13) con soporte de red para Mininet:

```bash
chmod +x setup_env.sh
./setup_env.sh
```

El script instala:
1. Herramientas de red: `mininet`, `iperf`, `tcpdump`, `wireshark-common`, `ethtool`.
2. Compilador y switch P4 de P4lang: `p4lang-p4c`, `p4lang-bmv2` (`simple_switch` y `simple_switch_grpc`) y `p4lang-pi`.
3. Librerías de Python: `python3-scapy`, `python3-grpcio`, `python3-protobuf`, `python3-matplotlib`.

---

## Ejecución de los Laboratorios

Cada laboratorio incluye un modo de pruebas automáticas y un modo interactivo con Mininet:

- **Lab 1 — Router IPv4 Estático ([lab1-router/README.md](lab1-router/README.md)):**
  ```bash
  cd lab1-router && sudo mn -c && sudo python3 topology.py --test
  ```
- **Lab 2 — Contadores y Estadísticas ([lab2-counters/README.md](lab2-counters/README.md)):**
  ```bash
  cd lab2-counters && sudo mn -c && sudo python3 topology.py --verificar
  ```
- **Lab 3 — Telemetría In-Band INT ([lab3-int/README.md](lab3-int/README.md)):**
  ```bash
  cd lab3-int && sudo mn -c && sudo python3 topology.py --test
  ```

Para pruebas manuales paso a paso, ejecución interactiva y detalles de cada topología, consulte el `README.md` dentro de cada carpeta.
