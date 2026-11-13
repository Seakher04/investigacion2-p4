# Laboratorio 2: Contadores y Estadísticas de Tráfico (`/lab2-counters`)

Implementación 2, a cargo de Marina Castro Peralta.

Un switch P4 (BMv2, arquitectura v1model) reenvía el tráfico de cuatro hosts y lleva estadísticas en el plano de datos:

- **Contadores directos por flujo.** La tabla `flujos` tiene una entrada por cada par IP origen + IP destino y un `direct_counter` que cuenta paquetes y bytes de cada entrada.
- **Contadores globales por protocolo.** Un `counter` de 4 posiciones: TCP, UDP, ICMP y otros (todo lo que no es TCP, UDP ni ICMP, incluso lo que no es IPv4).
- **Tamaño de los paquetes con registers.** `histograma_tam` cuenta cuántos paquetes caen en cada rango de tamaño y `tam_max_flujo` guarda el paquete más grande de cada flujo.
- **Flujos elefante.** `bytes_flujo` acumula los bytes de cada flujo. Cuando pasan el umbral guardado en `umbral_elefante`, el switch pone `flujo_elefante` en 1. El umbral se cambia en tiempo de ejecución desde el controlador.

## Archivos

| Archivo | Qué hace |
|---|---|
| `lab2.p4` | Programa P4 del switch |
| `s1-commands.txt` | Entradas de las tablas y umbral inicial (1 000 000 bytes) |
| `topology.py` | Compila el P4 y levanta en Mininet 1 switch y 4 hosts (`h1` a `h4`, 10.0.0.1 a 10.0.0.4) |
| `controlador.py` | Lee por Thrift los contadores y registros y los imprime cada 5 segundos |
| `trafico.py` | Envía con Scapy una cantidad exacta de paquetes TCP, UDP, ICMP y de protocolo 253, e imprime lo que el switch debería contar |
| `receptor.py` | Recibe el UDP y el protocolo 253 en el destino para que no conteste con errores ICMP |
| `verificar.py` | Prueba automática: compara lo enviado contra los contadores y revisa la marca de flujo elefante |

## Requisitos

`p4c`, `simple_switch` (BMv2), Mininet, Scapy, iperf y el módulo `thrift` de Python. Se instalan con `../setup_env.sh`.

## Cómo correrlo

Todo desde la carpeta `lab2-counters`.

Prueba automática (al final debe decir `Resultado: todo coincide`):

```bash
sudo python3 topology.py --verificar
```

Prueba manual. En una terminal se levanta la red y queda abierta la consola de Mininet:

```bash
sudo python3 topology.py
```

En otra terminal se corre el controlador:

```bash
python3 controlador.py --reiniciar
```

Opciones del controlador: `--intervalo N` (segundos entre lecturas, máximo 5), `--umbral N` (nuevo umbral de bytes), `--reiniciar` (pone todo en cero) y `--lecturas N` (se detiene después de N lecturas).

Tráfico de prueba desde la consola de Mininet:

```text
mininet> h2 python3 receptor.py > logs/receptor.log 2>&1 &
mininet> h1 python3 trafico.py 10.0.0.2
mininet> pingall
mininet> h4 iperf -s > /dev/null &
mininet> h3 iperf -c 10.0.0.4 -t 10
mininet> h1 iperf -s -u > /dev/null &
mininet> h4 iperf -c 10.0.0.1 -u -b 500K -t 5
```

`trafico.py` imprime cuántos paquetes y bytes debería contar el switch. El destino contesta un RST por cada SYN y un echo reply por cada ping, y eso también se cuenta. El flujo de iperf de `h3` a `h4` pasa el umbral y el controlador lo muestra como `ELEFANTE`.

Si algo queda colgado: `sudo mn -c`.

## Detalles

- Los bytes que cuenta BMv2 son los de la trama Ethernet sin el FCS. Un ping de 56 bytes de datos mide 98 bytes (14 Ethernet + 20 IPv4 + 8 ICMP + 56).
- El switch descarta lo que no es IPv4, así que `topology.py` pone ARP estático en los hosts.
- `topology.py` apaga IPv6 en los hosts y en los puertos del switch. Si no, el kernel manda *router solicitations* que se cuentan en "Otros".
- `p4c` no acepta rutas con espacios, por eso `topology.py` compila con rutas relativas dentro de la carpeta.
