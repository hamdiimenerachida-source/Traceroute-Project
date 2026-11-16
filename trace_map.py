# trace_map.py -- draws the path of a traceroute on a world map.
# Do not change this file.
#
# A fictional example, from Oran to a server in Oslo (the names and addresses are not real):
#
#     from trace_map import draw_map
#
#     hops = [(1, "192.168.1.1",    2.1),
#             (2, "198.51.100.1",   5.3),
#             (3, "10.20.30.40",    6.0),
#             (4, None,             None),       # no reply for TTL 4
#             (5, "203.0.113.17",  21.8),
#             (6, "203.0.113.90",  38.4),
#             (7, "192.0.2.25",    61.2),
#             (8, "192.0.2.80",    68.9)]        # the destination answered
#
#     draw_map("www.oslo-example.no", hops, "map-oslo.html", source=(35.70, -0.63))
#
# hops is a list of (ttl, ip, rtt_ms). Use None for ip and rtt_ms when no router answered.
# source is the GPS position (latitude, longitude) of the place where you ran the program.
# The function writes an HTML file: open it in your web browser.
#
# The positions come from the free service ip-api.com (no key, at most 15 requests per minute).
# A private address (192.168.x.x, 10.x.x.x, 172.16-31.x.x, 100.64.x.x) has no position on the map.

import ipaddress
import json
import math
import socket
import urllib.request

FIELDS = "status,query,lat,lon,city,country,as"
def _locate(ips):
    """Returns {ip: info} for the public addresses in ips."""
    public = [ip for ip in ips if ip and ipaddress.ip_address(ip).is_global]
    public = list(dict.fromkeys(public))  # remove duplicates, keep the order
    info = {}
    if public:
        req = urllib.request.Request(
            f"http://ip-api.com/batch?fields={FIELDS}",
            data=json.dumps(public[:100]).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            for item in json.load(r):
                if item.get("status") == "success":
                    info[item["query"]] = item
    return info


def _my_position():
    """Position of your public IP address (the source)."""
    with urllib.request.urlopen(f"http://ip-api.com/json/?fields={FIELDS}", timeout=10) as r:
        item = json.load(r)
    item["query"] = "you (" + item.get("query", "?") + ")"
    return item


def _distance_km(a, b):
    """Distance on the Earth between two points (lat, lon), in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def draw_map(host, hops, filename="map.html", source=None):
    """Writes a world map of the path to host.

    host:     the name or IP address of the destination
    hops:     list of (ttl, ip, rtt_ms)
    filename: the HTML file to write
    source:   your position (lat, lon), for example (35.70, -0.63) for Oran.
    If None, the position of your public IP address is used.
    """
    dst_ip = socket.gethostbyname(host)
    info = _locate([ip for _, ip, _ in hops] + [dst_ip])

    if source is None:
        src = _my_position()
    else:
        src = {"query": "you", "lat": source[0], "lon": source[1], "city": "", "country": "", "as": ""}
    src_pos = (src["lat"], src["lon"])

    points = [{"kind": "source", "label": "Source", "ip": src["query"], "lat": src["lat"], "lon": src["lon"], "place": (src.get("city", "") + ", " + src.get("country", "")).strip(", "), "as": src.get("as", ""), "rtt": None, "note": ""}]
    rows = []
    for ttl, ip, rtt in hops:
        row = {"ttl": ttl, "ip": ip or "*", "rtt": rtt, "place": "", "as": "", "note": ""}
        if ip is None:
            row["note"] = "no reply"
        elif ip not in info:
            row["note"] = "private address: no position" if not ipaddress.ip_address(ip).is_global else "no position"
        else:
            i = info[ip]
            row["place"] = i.get("city", "") + ", " + i.get("country", "")
            row["as"] = i.get("as", "")
            # Light in a fiber goes about 200 km per ms, so a reply after rtt ms
            # comes from at most rtt / 2 * 200 = rtt * 100 km.
            d = _distance_km(src_pos, (i["lat"], i["lon"]))
            if rtt is not None and d > rtt * 100:
                row["note"] = "%d km in %.1f ms: impossible, the position is wrong" % (d, rtt)
            kind = "destination" if ip == dst_ip else "router"
            points.append({"kind": kind, "label": "Hop %d" % ttl, "ip": ip, "lat": i["lat"], "lon": i["lon"], "place": row["place"], "as": row["as"], "rtt": rtt, "note": row["note"]})
        rows.append(row)

    if dst_ip not in [p["ip"] for p in points] and dst_ip in info:
        i = info[dst_ip]
        points.append({"kind": "destination", "label": "Destination (did not answer)", "ip": dst_ip,
            "lat": i["lat"], "lon": i["lon"], "place": i.get("city", "") + ", " + i.get("country", ""),
            "as": i.get("as", ""), "rtt": None, "note": ""})

    html = _PAGE.replace("__TITLE__", f"Path to {host} ({dst_ip})")
    html = html.replace("__POINTS__", json.dumps(points)).replace("__ROWS__", json.dumps(rows))
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print("Map written to", filename)


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body { font-family: sans-serif; margin: 0 16px 16px; }
#map { height: 520px; border: 1px solid #999; }
table { border-collapse: collapse; margin-top: 12px; font-size: 14px; }
td, th { border: 1px solid #bbb; padding: 3px 8px; text-align: left; }
.bad { color: #b00; }
.legend span { display: inline-block; width: 12px; height: 12px; border-radius: 6px; margin: 0 4px 0 12px; }
</style></head><body>
<h2>__TITLE__</h2>
<p class="legend"><span style="background:#2a2"></span>source
<span style="background:#27c"></span>router <span style="background:#d22"></span>destination
<span style="background:#e80"></span>impossible position (too far for the RTT)</p>
<div id="map"></div>
<table id="hops"><tr><th>TTL</th><th>IP address</th><th>RTT (ms)</th><th>Place</th><th>AS</th><th>Note</th></tr></table>
<script>
const points = __POINTS__, rows = __ROWS__;
const colour = {source: "#2a2", router: "#27c", destination: "#d22", wrong: "#e80"};
const map = L.map("map").setView([30, 10], 2);
// Esri tiles: they work when the page is opened from a file (OpenStreetMap tiles are blocked then)
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
{maxZoom: 18, attribution: "Tiles &copy; Esri"}).addTo(map);
const line = points.map(p => [p.lat, p.lon]);
// routers first, so that the source and the destination are drawn on top
const order = points.filter(p => p.kind === "router").concat(points.filter(p => p.kind !== "router"));
for (const p of order) {
const c = p.note ? colour.wrong : colour[p.kind];
L.circleMarker([p.lat, p.lon], {radius: p.kind === "router" ? 6 : 9, color: c, fillOpacity: 0.8})
.bindPopup("<b>" + p.label + "</b><br>" + p.ip + "<br>" + p.place + "<br>" + p.as +
(p.rtt !== null ? "<br>RTT: " + p.rtt + " ms" : "") +
(p.note ? "<br><span class='bad'>" + p.note + "</span>" : ""))
.bindTooltip(p.label).addTo(map);
}
if (line.length > 1) { const pl = L.polyline(line, {color: "#555"}).addTo(map); map.fitBounds(pl.getBounds().pad(0.2)); }
const t = document.getElementById("hops");
for (const r of rows) {
const tr = t.insertRow();
for (const v of [r.ttl, r.ip, r.rtt === null ? "*" : r.rtt, r.place, r.as]) tr.insertCell().textContent = v;
const c = tr.insertCell(); c.textContent = r.note; c.className = "bad";
}
</script></body></html>
"""