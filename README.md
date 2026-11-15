# Redes Programables con P4: Investigación y Laboratorio Base

Curso: Redes de Comunicación de Datos (CI-0121)  
Escuela de Ciencias de la Computación e Informática  
Universidad de Costa Rica

## Integrantes
- Hermes Josué Rojas Sancho (C16882)
- Marina Castro Peralta (C31886)
- Sebastián Sánchez Jiménez (C4J761)

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
│   └── README.md
├── lab3-int/                  # Implementación 3: Telemetría In-Band INT (Hermes)
│   └── README.md
└── informe/                   # Informe escrito en PDF y borradores
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

- **Lab 1 (`/lab1-router`):** consulte [lab1-router/README.md](lab1-router/README.md).
- **Lab 2 (`/lab2-counters`):** consulte [lab2-counters/README.md](lab2-counters/README.md).
- **Lab 3 (`/lab3-int`):** consulte [lab3-int/README.md](lab3-int/README.md).
