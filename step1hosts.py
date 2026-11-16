#!/usr/bin/env python3
"""step1_hosts.py -- etape 1: le serveur est-il vraiment dans le pays de son nom ?

Pour chaque host: un ping ICMP (5 essais) -> TTL de la reponse et RTT minimum.
Si le host ne repond pas a l'ICMP: RTT d'une connexion TCP sur le port 443.

Regle (physique): la lumiere dans la fibre fait ~200 km/ms, donc un aller-retour
de RTT ms couvre au plus RTT*100 km. Si RTT*100 < distance reelle jusqu'a la ville
de l'universite, le serveur n'est PAS la-bas: c'est un CDN proche de toi.
Nombre de sauts = TTL initial (32, 64, 128 ou 255) - TTL recu.

Lancer en administrateur / sudo:   python step1_hosts.py
Resultat: tableau a l'ecran + step1_results.csv
"""
import csv
import math
import os
import select
import socket
import struct
import time

from traceroute import build_echo, local_ip

SOURCE = (35.56, 0.63)

HOSTS = {
    # Algerie
    "www.univ-bejaia.dz": ("Bejaia", 36.75, 5.06), "www.cerist.dz": ("Alger", 36.70, 3.17),
    "www.ooredoo.dz": ("Alger", 36.75, 3.06), "www.esi.dz": ("Alger", 36.70, 3.17),
    # Europe
    "www.us.es": ("Seville", 37.39, -5.98), "www.ethz.ch": ("Zurich", 47.38, 8.54),
    "www.univ-amu.fr": ("Marseille", 43.30, 5.37), "www.ox.ac.uk": ("Oxford", 51.75, -1.26),
    # Asie
    "www.u-tokyo.ac.jp": ("Tokyo", 35.68, 139.76), "www.kaist.ac.kr": ("Daejeon", 36.35, 127.38),
    # Australie
    "www.anu.edu.au": ("Canberra", -35.28, 149.13), "www.uq.edu.au": ("Brisbane", -27.47, 153.03),
    # Amerique du Sud
    "www.usp.br": ("Sao Paulo", -23.55, -46.63), "www.uchile.cl": ("Santiago", -33.45, -70.67),
}


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def ping(ip, tries=5, timeout=2.0):
    """Retourne (ttl_recu, rtt_min_ms) ou (None, None)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    sock.bind((local_ip(ip), 0))
    ident = os.getpid() & 0xFFFF
    best_rtt, ttl = None, None
    for seq in range(1, tries + 1):
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 64)
        t0 = time.perf_counter()
        sock.sendto(build_echo(ident, seq), (ip, 0))
        while True:
            left = t0 + timeout - time.perf_counter()
            if left <= 0:
                break
            ready, _, _ = select.select([sock], [], [], left)
            if not ready:
                break
            data, addr = sock.recvfrom(65535)
            t1 = time.perf_counter()
            ihl = (data[0] & 0x0F) * 4
            if addr[0] == ip and data[ihl] == 0 and struct.unpack("!HH", data[ihl + 4:ihl + 8]) == (ident, seq):
                rtt = (t1 - t0) * 1000
                ttl = data[8]
                best_rtt = rtt if best_rtt is None else min(best_rtt, rtt)
                break
    sock.close()
    return ttl, best_rtt


def tcp_rtt(ip, tries=3):
    best = None
    for _ in range(tries):
        t0 = time.perf_counter()
        try:
            s = socket.create_connection((ip, 443), timeout=3)
            rtt = (time.perf_counter() - t0) * 1000
            s.close()
            best = rtt if best is None else min(best, rtt)
        except OSError:
            pass
    return best


def initial_ttl(ttl):
    for start in (32, 64, 128, 255):
        if ttl <= start:
            return start
    return 255


def main():
    rows = []
    print("%-28s %-15s %5s %5s %9s  %s" % ("host", "ip", "TTL", "sauts", "RTT(ms)", "decision"))
    for host, (city, lat, lon) in HOSTS.items():
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror:
            print("%-28s DNS impossible" % host)
            continue
        ttl, rtt = ping(ip)
        kind = "ICMP"
        if rtt is None:
            rtt, kind = tcp_rtt(ip), "TCP443"
        hops = initial_ttl(ttl) - ttl if ttl else None
        if rtt is None:
            decision = "aucune reponse (ICMP et TCP): choisir un autre host"
        else:
            dist = distance_km(SOURCE, (lat, lon))
            physical_min = dist / 100.0           # RTT minimal possible dans la fibre
            if rtt < 0.9 * physical_min:
                decision = "CDN proche (impossible d'etre a %s: %d km, RTT min %.1f ms)" % (city, dist, physical_min)
            else:
                decision = "serveur plausiblement a %s (%d km)" % (city, dist)
        rows.append([host, ip, ttl, hops, "%.1f" % rtt if rtt else "", kind, decision])
        print("%-28s %-15s %5s %5s %9s  %s [%s]" % (host, ip, ttl if ttl else "-", hops if hops is not None else "-",  "%.1f" % rtt if rtt else "-", decision, kind))
    with open("step1_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["host", "ip", "ttl_reply", "hops", "rtt_ms", "method", "decision"])
        w.writerows(rows)
    print("Ecrit: step1_results.csv")


if __name__ == "__main__":
    main()