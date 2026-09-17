# -*- coding: utf-8 -*-
r"""独立实现一遍聚类，和后端接口的结果逐个数字对拍。

这是交叉验证：Java 那边一份实现，这里 Python 再写一份。
两份独立实现算出同一个答案，才说明"从数据库到接口"这条链路是对的。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\verify-hotspot-api.py
"""
import json
import math
import sys
import urllib.request

BASE = "http://localhost:8080"
RADIUS_M = 200.0
MIN_VISITS = 2
fails = []


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def check(name, ok, detail=""):
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def hav(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    t = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, t)))


def main():
    # ---- 1. 独立算一遍 ----
    stays = []
    track_ids = []
    for t in get("/api/tracks?limit=500")["items"]:
        track_ids.append(t["id"])
        for s in get(f"/api/tracks/{t['id']}/stay-points").get("stays", []):
            stays.append({
                "trackId": t["id"], "lat": s["lat"], "lon": s["lon"],
                "durationS": s["durationS"],
                "startTime": s["startTime"], "endTime": s["endTime"],
            })

    n = len(stays)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            a, b = stays[i], stays[j]
            if hav(a["lat"], a["lon"], b["lat"], b["lon"]) <= RADIUS_M:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    expected = []
    for mem in groups.values():
        if len(mem) < MIN_VISITS:
            continue
        pts = [stays[i] for i in mem]
        c_lat = sum(p["lat"] for p in pts) / len(pts)
        c_lon = sum(p["lon"] for p in pts) / len(pts)
        expected.append({
            "visitCount": len(pts),
            "trackCount": len({p["trackId"] for p in pts}),
            "totalDurationS": sum(p["durationS"] for p in pts),
            "centerLat": c_lat,
            "centerLon": c_lon,
            "radiusM": max(hav(c_lat, c_lon, p["lat"], p["lon"]) for p in pts),
            "trackIds": sorted({p["trackId"] for p in pts}),
            "firstVisit": min(p["startTime"] for p in pts),
            "lastVisit": max(p["endTime"] for p in pts),
        })
    expected.sort(key=lambda c: (-c["trackCount"], -c["visitCount"],
                                 -c["totalDurationS"], c["centerLat"], c["centerLon"]))

    # ---- 2. 拿后端结果 ----
    api = get("/api/analysis/hotspots")

    # ---- 3. 对拍 ----
    check("scannedTracks 一致", api["scannedTracks"] == len(track_ids),
          f'API {api["scannedTracks"]} vs 期望 {len(track_ids)}')
    check("scannedStays 一致", api["scannedStays"] == n, f'API {api["scannedStays"]} vs 期望 {n}')
    check("热点个数一致", len(api["hotspots"]) == len(expected),
          f'API {len(api["hotspots"])} vs 期望 {len(expected)}')

    for k, (a, e) in enumerate(zip(api["hotspots"], expected), 1):
        check(f"第{k}名 rank", a["rank"] == k, str(a["rank"]))
        for f in ("visitCount", "trackCount", "totalDurationS"):
            check(f"第{k}名 {f}", a[f] == e[f], f'API {a[f]} vs 期望 {e[f]}')
        check(f"第{k}名 trackIds", a["trackIds"] == e["trackIds"],
              f'API {a["trackIds"]} vs 期望 {e["trackIds"]}')
        check(f"第{k}名 centerLat", abs(a["centerLat"] - e["centerLat"]) < 1e-6,
              f'API {a["centerLat"]!r} vs 期望 {e["centerLat"]!r}')
        check(f"第{k}名 centerLon", abs(a["centerLon"] - e["centerLon"]) < 1e-6,
              f'API {a["centerLon"]!r} vs 期望 {e["centerLon"]!r}')
        check(f"第{k}名 radiusM", abs(a["radiusM"] - e["radiusM"]) < 0.2,
              f'API {a["radiusM"]} vs 期望 {round(e["radiusM"], 1)}')
        check(f"第{k}名 firstVisit", a["firstVisit"] == e["firstVisit"])
        check(f"第{k}名 lastVisit", a["lastVisit"] == e["lastVisit"])

    # ---- 4. 孤立点个数能自证 ----
    counted = sum(h["visitCount"] for h in api["hotspots"])
    check("孤立点个数 = scannedStays - ΣvisitCount",
          api["scannedStays"] - counted == 1,
          f'{api["scannedStays"]} - {counted} = {api["scannedStays"] - counted}（应为 1）')

    print(f"\n{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


main()
