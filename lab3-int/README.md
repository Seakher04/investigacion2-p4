# Laboratorio 3: Telemetría In-Band (`/lab3-int`)

Directorio reservado para la Implementación 3 (asignada a Hermes Josué Rojas Sancho):
- Código P4 con roles INT Source, INT Transit e INT Sink y pila de cabeceras de longitud variable.
- Topología en Mininet (`topology.py`) con 4 switches P4, dos caminos entre origen y destino, 3 hosts y 1 colector.
- Colector en Python (`Scapy`) con reporte cada 5 segundos y alertas de congestión.
