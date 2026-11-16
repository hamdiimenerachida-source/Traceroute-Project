#!/usr/bin/env python3
"""traceroute.py -- traceroute en ICMP avec raw socket, puis carte du chemin.

Usage (administrateur sous Windows, sudo sous Linux):
    python traceroute.py www.usthb.dz
    python traceroute.py www.u-tokyo.ac.jp --source 35.70 -0.63

Avant de lancer: remplis FIRST_NAME, LAST_NAME et SOURCE ci-dessous.
Le fichier trace_map.py doit etre dans le meme dossier (le fichier donne, sans modification).
"""

import argparse
import os
import select
import socket
import struct
import sys
import time
import ipaddress

FIRST_NAME = "Hamdi"          # ton prenom, sans accent
LAST_NAME = "Imene"              # ton nom, sans accent
SOURCE = (35.56, 0.63)        # ta position GPS (latitude, longitude), prise sur ton telephone
PAYLOAD = f"{FIRST_NAME} {LAST_NAME}".encode("ascii")
PROBES_PER_TTL = 3
MAX_TTL = 30
TIMEOUT = 3.0

_seq = 0


def checksum(data):
    """Somme de controle Internet (RFC 1071)."""
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def build_echo(ident, seq):
    """Paquet ICMP Echo Request: type 8, code 0, checksum, id, seq, donnees."""
    header = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
    csum = checksum(header + PAYLOAD)
    return struct.pack("!BBHHH", 8, 0, csum, ident, seq) + PAYLOAD


def parse_reply(packet, ident, seq):
    """Analyse un paquet recu (avec son entete IP).

    Retourne (type, ip_source) si le paquet repond a NOTRE sonde, sinon None.
    type = "reply" (Echo Reply), "time_exceeded" (type 11) ou "unreachable" (type 3).
    """
    if len(packet) < 28:
        return None
    ihl = (packet[0] & 0x0F) * 4
    src = socket.inet_ntoa(packet[12:16])
    icmp = packet[ihl:]
    if len(icmp) < 8:
        return None
    icmp_type = icmp[0]
    if icmp_type == 0:                                   # Echo Reply
        rid, rseq = struct.unpack("!HH", icmp[4:8])
        if rid == ident and rseq == seq:
            return ("reply", src)
    elif icmp_type in (11, 3):                           # Time Exceeded / Unreachable
        inner = icmp[8:]                                 # entete IP originale + 8 octets
        if len(inner) < 28:
            return None
        inner_ihl = (inner[0] & 0x0F) * 4
        orig = inner[inner_ihl:inner_ihl + 8]            # notre entete ICMP
        if len(orig) < 8 or orig[0] != 8:
            return None
        rid, rseq = struct.unpack("!HH", orig[4:8])
        if rid == ident and rseq == seq:
            return ("time_exceeded" if icmp_type == 11 else "unreachable", src)
    return None


def local_ip(dst):
    """Adresse locale utilisee pour joindre dst (necessaire pour bind sous Windows)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((dst, 80))
        return s.getsockname()[0]
    finally:
        s.close()


def open_socket(dst):
    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    sock.bind((local_ip(dst), 0))
    if os.name == "nt":
        # Windows: recevoir tous les paquets IP de l'interface (inclut les ICMP Time Exceeded)
        try:
            sock.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
        except (OSError, AttributeError):
            pass
    return sock


def send_probe(sock, dst, ttl, ident, timeout):
    """Envoie UNE sonde et attend sa reponse (ou le timeout).

    Retourne (type, ip, rtt_ms) ou None.
    """
    global _seq
    _seq = (_seq + 1) & 0xFFFF
    seq = _seq
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    packet = build_echo(ident, seq)
    t0 = time.perf_counter()
    sock.sendto(packet, (dst, 0))
    deadline = t0 + timeout
    while True:
        left = deadline - time.perf_counter()
        if left <= 0:
            return None
        ready, _, _ = select.select([sock], [], [], left)
        if not ready:
            return None
        data, _addr = sock.recvfrom(65535)
        t1 = time.perf_counter()
        if result := parse_reply(data, ident, seq):
            return result[0], result[1], (t1 - t0) * 1000.0


_dns_cache = {}


def reverse_dns(ip):
    if ip not in _dns_cache:
        try:
            _dns_cache[ip] = socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror, OSError):
            _dns_cache[ip] = "-"
    return _dns_cache[ip]


def main():
    ap = argparse.ArgumentParser(description="traceroute ICMP + carte")
    ap.add_argument("host")
    ap.add_argument("--source", nargs=2, type=float, metavar=("LAT", "LON"),
                    help="ta position GPS (sinon la constante SOURCE)")
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--max-ttl", type=int, default=MAX_TTL)
    ap.add_argument("--no-map", action="store_true", help="ne pas dessiner la carte")
    args = ap.parse_args()
    source = tuple(args.source) if args.source else SOURCE

    try:
        dst = socket.gethostbyname(args.host)
    except socket.gaierror as e:
        sys.exit(f"Impossible de resoudre {args.host}: {e}")

    txt_name = f"output-{args.host}.txt"
    with open(txt_name, "w", encoding="utf-8") as out:
        def say(line=""):
            print(line, flush=True)
            out.write(line + "\n")
            out.flush()

        try:
            sock = open_socket(dst)
        except PermissionError:
            sys.exit("Raw socket refuse: lance le programme en administrateur (Windows) ou avec sudo (Linux).")

        ident = os.getpid() & 0xFFFF
        say("traceroute to %s (%s), %d hops max, data = '%s'" % (args.host, dst, args.max_ttl, PAYLOAD.decode()))

        hops = []
        no_reply, private = [], []
        reached = False
        for ttl in range(1, args.max_ttl + 1):
            results = []
            for _ in range(PROBES_PER_TTL):
                results.append(send_probe(sock, dst, ttl, ident, args.timeout))   # une sonde a la fois

            answered = [r for r in results if r]
            if not answered:
                say("%2d  %-15s  %-45s  %8s %8s %8s" % (ttl, "*", "", "*", "*", "*"))
                hops.append((ttl, None, None))
                no_reply.append(ttl)
                continue

            best = min(answered, key=lambda r: r[2])            # plus petit RTT: donne l'IP et le RTT du hop
            ip, rtt = best[1], best[2]
            rtts = ["%.2f" % r[2] if r else "*" for r in results]
            others = sorted({r[1] for r in answered if r[1] != ip})
            name = reverse_dns(ip)
            line = "%2d  %-15s  %-45s  %8s %8s %8s" % (ttl, ip, name, rtts[0], rtts[1], rtts[2])
            if others:
                line += f'   (autres routeurs: {", ".join(others)})'
            say(line)
            hops.append((ttl, ip, rtt))
            if not ipaddress.ip_address(ip).is_global:
                private.append(ttl)
            if any(r[0] == "reply" or (r[0] == "unreachable" and r[1] == dst) for r in answered):
                reached = True
                break

        say()
        say(f'Destination atteinte: {"oui" if reached else "non (TTL max)"}')
        say(f'TTL sans reponse: {no_reply or "aucun"}')
        say(f'TTL avec adresse privee: {private or "aucun"}')
    print("Sortie ecrite dans", txt_name)

    if not args.no_map:
        try:
            from trace_map import draw_map
            draw_map(args.host, hops, f"map-{args.host}.html", source=source)
        except ImportError:
            print("trace_map.py introuvable: mets-le dans le meme dossier (nom exact: trace_map.py).")
        except Exception as e:                                # reseau, limite ip-api, etc.
            print("Carte non dessinee:", e)


if __name__ == "__main__":
    main()