/*
 * int.p4 - Telemetría In-Band (INT) simplificada estilo INT-MD (Laboratorio 3)
 *
 * Implementa en un solo programa P4_16 (arquitectura v1model sobre BMv2) los tres
 * roles de INT configurados desde el plano de control:
 *   - INT Source : identifica flujos en la tabla `int_watchlist` e inserta la
 *                  cabecera de control `int_ctrl` más el primer salto.
 *   - INT Transit: agrega a la pila `int_hops` los metadatos locales del switch
 *                  (switch_id, puertos, latencia del salto y profundidad de cola)
 *                  respetando `max_hops` y marcando `overflow` si se alcanza.
 *   - INT Sink   : clona el paquete hacia el colector (con toda la telemetría,
 *                  incluido el último salto) y remueve las cabeceras INT del
 *                  paquete original antes de entregarlo intacto al host destino.
 *
 * Señalización en IPv4:
 *   Se usa el campo `ipv4.diffserv = 0x5c` (DSCP 23 experimental) para indicar
 *   que inmediatamente después de IPv4 vienen `int_ctrl` y la pila `int_hops`.
 *   El valor original de `diffserv` se guarda en `int_ctrl.orig_diffserv` y se
 *   restaura en el INT Sink.
 */

#include <core.p4>
#include <v1model.p4>

/* Constantes de protocolos y señalización INT */
const bit<16> TYPE_IPV4  = 0x0800;
const bit<8>  PROTO_TCP  = 6;
const bit<8>  PROTO_UDP  = 17;
const bit<8>  DSCP_INT   = 0x5c; /* DSCP 23 (0x17 << 2) para marcar paquetes con INT */

/* Identificadores de instancia y lista de campos para clonación I2E en v1model */
const bit<32> PKT_INSTANCE_TYPE_INGRESS_CLONE = 1;
const bit<8>  CLONE_FL_1                      = 1;

/* Tamaño máximo de la pila de saltos INT soportada por el parser/deparser */
#define MAX_HOPS 8
const bit<16> INT_CTRL_BYTES = 4;
const bit<16> INT_HOP_BYTES  = 16;

typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************************************************************
 *********************** C A B E C E R A S *******************************
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

/* Cabecera de control INT (4 bytes) */
header int_ctrl_t {
    bit<8> hop_count;      /* Cantidad de saltos registrados en la pila */
    bit<8> max_hops;       /* Máximo de saltos permitido para este flujo */
    bit<1> overflow;       /* 1 si algún switch no pudo agregar su registro */
    bit<7> reserved;       /* Reservado (0) */
    bit<8> orig_diffserv;  /* Valor original de ipv4.diffserv para restaurar */
}

/* Registro de metadatos de un salto INT (16 bytes) */
header int_hop_t {
    bit<32> switch_id;     /* Identificador único del switch */
    bit<16> ingress_port;  /* Puerto físico de entrada */
    bit<16> egress_port;   /* Puerto físico de salida */
    bit<32> hop_latency;   /* Latencia en el switch (microsegundos) */
    bit<32> qdepth;        /* Profundidad de cola en paquetes al encolarse */
}

/* Cabeceras de capa 4 para que la watchlist pueda filtrar por puerto */
header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<4>  res;
    bit<8>  flags;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

header udp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<16> length_;
    bit<16> checksum;
}

/* Metadatos internos que acompañan al paquete dentro del switch */
struct metadata {
    bit<8>  remaining_hops;
    bit<16> l4_src_port;
    bit<16> l4_dst_port;
    bit<32> switch_id;

    /* Campos preservados al clonar de Ingress a Egress (I2E) */
    @field_list(CLONE_FL_1)
    bit<1>  is_int_source;
    @field_list(CLONE_FL_1)
    bit<8>  max_hops;
    @field_list(CLONE_FL_1)
    bit<1>  is_int_sink;
    @field_list(CLONE_FL_1)
    bit<9>  orig_ingress_port;
    @field_list(CLONE_FL_1)
    bit<9>  orig_egress_port;
}

struct headers {
    ethernet_t         ethernet;
    ipv4_t             ipv4;
    int_ctrl_t         int_ctrl;
    int_hop_t[MAX_HOPS] int_hops;
    tcp_t              tcp;
    udp_t              udp;
}

/*************************************************************************
 *************************** P A R S E R *********************************
 *************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.diffserv) {
            DSCP_INT: parse_int_ctrl;
            default: parse_l4;
        }
    }

    /* Extrae la cabecera de control INT y decide cuántos saltos recorrer */
    state parse_int_ctrl {
        packet.extract(hdr.int_ctrl);
        meta.remaining_hops = hdr.int_ctrl.hop_count;
        transition select(meta.remaining_hops) {
            0: parse_l4;
            default: parse_int_hop;
        }
    }

    /* Bucle de estados para recorrer la pila de metadatos de longitud variable */
    state parse_int_hop {
        packet.extract(hdr.int_hops.next);
        meta.remaining_hops = meta.remaining_hops - 1;
        transition select(meta.remaining_hops) {
            0: parse_l4;
            default: parse_int_hop;
        }
    }

    /* Extrae TCP o UDP para exponer los puertos a la tabla watchlist */
    state parse_l4 {
        transition select(hdr.ipv4.protocol) {
            PROTO_TCP: parse_tcp;
            PROTO_UDP: parse_udp;
            default: accept;
        }
    }

    state parse_tcp {
        packet.extract(hdr.tcp);
        meta.l4_src_port = hdr.tcp.srcPort;
        meta.l4_dst_port = hdr.tcp.dstPort;
        transition accept;
    }

    state parse_udp {
        packet.extract(hdr.udp);
        meta.l4_src_port = hdr.udp.srcPort;
        meta.l4_dst_port = hdr.udp.dstPort;
        transition accept;
    }
}

/*************************************************************************
 *************  V E R I F I C A C I Ó N   C H E C K S U M  ***************
 *************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
 **************  I N G R E S S   P R O C E S S I N G  ********************
 *************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* Enrutamiento IPv4 estático (reutilizando la base del Lab 1) */
    action ipv4_forward(macAddr_t srcAddr, macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = srcAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = drop();
    }

    /* Rol INT Source: marca que este flujo debe recibir telemetría */
    action activate_int(bit<8> max_hops) {
        meta.is_int_source = 1;
        meta.max_hops = max_hops;
    }

    /*
     * Tabla watchlist configurada desde el control plane.
     * Usa coincidencia ternaria en el puerto destino para poder monitorear
     * tanto un puerto exacto (p. ej., UDP 5001) como cualquier puerto (0&&&0).
     */
    table int_watchlist {
        key = {
            hdr.ipv4.srcAddr: exact;
            hdr.ipv4.dstAddr: exact;
            hdr.ipv4.protocol: exact;
            meta.l4_dst_port: ternary;
        }
        actions = {
            activate_int;
            NoAction;
        }
        size = 256;
        default_action = NoAction();
    }

    /* Rol INT Sink: clona el paquete hacia el colector y marca limpieza en Egress */
    action set_int_sink(bit<32> mirror_session) {
        meta.is_int_sink = 1;
        meta.orig_ingress_port = standard_metadata.ingress_port;
        meta.orig_egress_port = standard_metadata.egress_spec;
        clone_preserving_field_list(CloneType.I2E, mirror_session, CLONE_FL_1);
    }

    table int_sink_port {
        key = {
            standard_metadata.egress_spec: exact;
        }
        actions = {
            set_int_sink;
            NoAction;
        }
        size = 64;
        default_action = NoAction();
    }

    apply {
        if (hdr.ipv4.isValid() && hdr.ipv4.ttl > 1) {
            if (ipv4_lpm.apply().hit) {
                /* Solo el nodo Source evalúa la watchlist en paquetes aún sin INT */
                if (!hdr.int_ctrl.isValid()) {
                    int_watchlist.apply();
                }

                /* Si el paquete lleva (o va a llevar) INT, comprobar si este puerto es Sink */
                if (hdr.int_ctrl.isValid() || meta.is_int_source == 1) {
                    int_sink_port.apply();
                }
            }
        } else {
            drop();
        }
    }
}

/*************************************************************************
 ***************  E G R E S S   P R O C E S S I N G  *********************
 *************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    /* Identificador del switch configurado desde el plano de control */
    action set_switch_id(bit<32> switch_id) {
        meta.switch_id = switch_id;
    }

    table int_switch_info {
        actions = {
            set_switch_id;
            NoAction;
        }
        size = 1;
        default_action = NoAction();
    }

    /* Inserta la cabecera de control INT en el nodo Source */
    action init_int_header() {
        hdr.int_ctrl.setValid();
        hdr.int_ctrl.hop_count = 0;
        hdr.int_ctrl.max_hops = meta.max_hops;
        hdr.int_ctrl.overflow = 0;
        hdr.int_ctrl.reserved = 0;
        hdr.int_ctrl.orig_diffserv = hdr.ipv4.diffserv;
        hdr.ipv4.diffserv = DSCP_INT;
        hdr.ipv4.totalLen = hdr.ipv4.totalLen + INT_CTRL_BYTES;
    }

    /* Apila un registro de metadatos del salto actual o marca desbordamiento */
    action push_int_hop(bit<9> in_port, bit<9> out_port) {
        if (hdr.int_ctrl.hop_count < hdr.int_ctrl.max_hops &&
            hdr.int_ctrl.hop_count < MAX_HOPS) {
            hdr.int_hops.push_front(1);
            hdr.int_hops[0].setValid();
            hdr.int_hops[0].switch_id = meta.switch_id;
            hdr.int_hops[0].ingress_port = (bit<16>)in_port;
            hdr.int_hops[0].egress_port = (bit<16>)out_port;
            hdr.int_hops[0].hop_latency = (bit<32>)(
                standard_metadata.egress_global_timestamp -
                standard_metadata.ingress_global_timestamp
            );
            hdr.int_hops[0].qdepth = (bit<32>)standard_metadata.enq_qdepth;
            hdr.int_ctrl.hop_count = hdr.int_ctrl.hop_count + 1;
            hdr.ipv4.totalLen = hdr.ipv4.totalLen + INT_HOP_BYTES;
        } else {
            hdr.int_ctrl.overflow = 1;
        }
    }

    /* Elimina todas las cabeceras INT y restaura IPv4 original en el Sink */
    action strip_int_headers() {
        bit<16> int_bytes = INT_CTRL_BYTES + ((bit<16>)hdr.int_ctrl.hop_count * INT_HOP_BYTES);
        hdr.ipv4.diffserv = hdr.int_ctrl.orig_diffserv;
        hdr.ipv4.totalLen = hdr.ipv4.totalLen - int_bytes;
        hdr.int_ctrl.setInvalid();
        hdr.int_hops[0].setInvalid();
        hdr.int_hops[1].setInvalid();
        hdr.int_hops[2].setInvalid();
        hdr.int_hops[3].setInvalid();
        hdr.int_hops[4].setInvalid();
        hdr.int_hops[5].setInvalid();
        hdr.int_hops[6].setInvalid();
        hdr.int_hops[7].setInvalid();
    }

    apply {
        int_switch_info.apply();

        if (standard_metadata.instance_type == PKT_INSTANCE_TYPE_INGRESS_CLONE) {
            /*
             * Paquete clonado hacia el colector en el INT Sink:
             * agregamos el registro de este último switch usando los puertos
             * originales del flujo (preservados desde Ingress).
             */
            if (!hdr.int_ctrl.isValid() && meta.is_int_source == 1) {
                init_int_header();
            }
            if (hdr.int_ctrl.isValid()) {
                push_int_hop(meta.orig_ingress_port, meta.orig_egress_port);
            }
        } else if (meta.is_int_sink == 1) {
            /*
             * Paquete original saliendo del INT Sink hacia el host destino:
             * se eliminan las cabeceras INT para entregar el paquete limpio.
             */
            if (hdr.int_ctrl.isValid()) {
                strip_int_headers();
            }
        } else {
            /* Paquete normal en nodo INT Source o INT Transit */
            if (meta.is_int_source == 1 && !hdr.int_ctrl.isValid()) {
                init_int_header();
            }
            if (hdr.int_ctrl.isValid()) {
                push_int_hop(standard_metadata.ingress_port,
                             standard_metadata.egress_port);
            }
        }
    }
}

/*************************************************************************
 *************  C Á L C U L O   D E   C H E C K S U M  *******************
 *************************************************************************/

/* Recalcula el checksum IPv4 tras modificar TTL, diffserv y totalLen */
control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            {
                hdr.ipv4.version,
                hdr.ipv4.ihl,
                hdr.ipv4.diffserv,
                hdr.ipv4.totalLen,
                hdr.ipv4.identification,
                hdr.ipv4.flags,
                hdr.ipv4.fragOffset,
                hdr.ipv4.ttl,
                hdr.ipv4.protocol,
                hdr.ipv4.srcAddr,
                hdr.ipv4.dstAddr
            },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16
        );
    }
}

/*************************************************************************
 *************************  D E P A R S E R  *****************************
 *************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.int_ctrl);
        packet.emit(hdr.int_hops);
        packet.emit(hdr.tcp);
        packet.emit(hdr.udp);
    }
}

/*************************************************************************
 **************************  S W I T C H  ********************************
 *************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
