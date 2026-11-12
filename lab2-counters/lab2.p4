/* lab2.p4: contadores y estadísticas de tráfico (Implementación 2) */

#include <core.p4>
#include <v1model.p4>

const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_ICMP = 1;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;

// Posiciones del contador por protocolo
const bit<32> IDX_TCP   = 0;
const bit<32> IDX_UDP   = 1;
const bit<32> IDX_ICMP  = 2;
const bit<32> IDX_OTROS = 3;

#define MAX_FLUJOS 64
#define NUM_RANGOS 5

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************************************************************
*********************** C A B E C E R A S ********************************
*************************************************************************/

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    bit<32> flujo_id;
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
}

/*************************************************************************
*************************** P A R S E R **********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition accept;
    }
}

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    // Paquetes y bytes por protocolo: 0 TCP, 1 UDP, 2 ICMP, 3 otros
    counter(4, CounterType.packets_and_bytes) contador_protocolo;

    // Paquetes y bytes de cada entrada de la tabla flujos
    direct_counter(CounterType.packets_and_bytes) contador_flujo;

    // Bytes acumulados por flujo, para detectar flujos elefante
    register<bit<64>>(MAX_FLUJOS) bytes_flujo;

    // Tamaño del paquete más grande visto en cada flujo
    register<bit<32>>(MAX_FLUJOS) tam_max_flujo;

    // 1 si el flujo ya pasó el umbral
    register<bit<8>>(MAX_FLUJOS) flujo_elefante;

    // Umbral de bytes para marcar un flujo como elefante
    register<bit<64>>(1) umbral_elefante;

    // Cantidad de paquetes en cada rango de tamaño
    register<bit<32>>(NUM_RANGOS) histograma_tam;

    action drop() {
        mark_to_drop(standard_metadata);
    }

    action reenviar(egressSpec_t puerto) {
        standard_metadata.egress_spec = puerto;
    }

    // Puerto de salida según la IP destino
    table ipv4_reenvio {
        key = {
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            reenviar;
            drop;
        }
        size = 16;
        default_action = drop();
    }

    action contar_flujo(bit<32> id) {
        meta.flujo_id = id;
    }

    // Un flujo por cada par IP origen + IP destino
    table flujos {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
        }
        actions = {
            contar_flujo;
            NoAction;
        }
        counters = contador_flujo;
        size = MAX_FLUJOS;
        default_action = NoAction();
    }

    apply {
        bit<32> largo = standard_metadata.packet_length;

        // Clasifica el paquete por protocolo
        bit<32> proto = IDX_OTROS;
        if (hdr.ipv4.isValid()) {
            if (hdr.ipv4.protocol == PROTO_TCP) {
                proto = IDX_TCP;
            } else if (hdr.ipv4.protocol == PROTO_UDP) {
                proto = IDX_UDP;
            } else if (hdr.ipv4.protocol == PROTO_ICMP) {
                proto = IDX_ICMP;
            }
        }
        contador_protocolo.count(proto);

        // Suma el paquete al rango de tamaño que le toca
        bit<32> rango;
        if (largo < 128) {
            rango = 0;
        } else if (largo < 256) {
            rango = 1;
        } else if (largo < 512) {
            rango = 2;
        } else if (largo < 1024) {
            rango = 3;
        } else {
            rango = 4;
        }
        bit<32> cantidad;
        histograma_tam.read(cantidad, rango);
        histograma_tam.write(rango, cantidad + 1);

        if (hdr.ipv4.isValid()) {
            if (flujos.apply().hit) {
                // Acumula los bytes del flujo
                bit<64> total;
                bytes_flujo.read(total, meta.flujo_id);
                total = total + (bit<64>) largo;
                bytes_flujo.write(meta.flujo_id, total);

                // Guarda el tamaño máximo del flujo
                bit<32> tam_max;
                tam_max_flujo.read(tam_max, meta.flujo_id);
                if (largo > tam_max) {
                    tam_max_flujo.write(meta.flujo_id, largo);
                }

                // Marca el flujo si pasó el umbral
                bit<64> umbral;
                umbral_elefante.read(umbral, 0);
                if (total > umbral) {
                    flujo_elefante.write(meta.flujo_id, 1);
                }
            }
            ipv4_reenvio.apply();
        } else {
            drop();
        }
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

// No se cambia ningún campo de IPv4, así que el checksum queda igual
control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
