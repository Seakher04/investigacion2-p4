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

El repositorio está organizado según los entregables solicitados en la sección 5.1 del enunciado:

```text
.
├── setup_env.sh               # Script para instalar p4c, BMv2,Mininet,Scapy e iperf
├── lab1-router/               # Implementación 1: Router IPv4 Estático (Sebastián)
│   └── README.md
├── lab2-counters/             # Implementación 2: Contadores y Estadísticas de Tráfico (Marina)
│   └── README.md
├── lab3-int/                  # Implementación 3: Telemetría In-Band INT (Hermes)
│   └── README.md
└── informe/                   # Informe escrito en formato PDF
    └── README.md
```

---

## Instalación del Entorno

Para que todos trabajemos con las mismas versiones de las herramientas en Ubuntu / Debian:

```bash
chmod +x setup_env.sh
./setup_env.sh
```

El script instala:
1. Herramientas base de red: Mininet, Scapy, iperf, tcpdump, wireshark-common.
2. Repositorio oficial de P4lang: `p4c` (compilador), `BMv2` (`simple_switch` y `simple_switch_grpc`) y `PI`.
3. Librerías de Python para el plano de control: `grpcio`, `protobuf`, `scapy`, `matplotlib`.

---

## Asignación de Laboratorios

- **/lab1-router/**: Router IPv4 estático, tabla LPM, reescritura de MAC, decremento de TTL y descarte por defecto.
- **/lab2-counters/**: Contadores directos por flujo, globales por protocolo, monitoreo de tamaño y flujos elefante.
- **/lab3-int/**: Telemetría In-Band (roles source, transit y sink), metadatos de latencia y colas, y colector en Python.
