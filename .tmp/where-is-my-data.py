# -*- coding: utf-8 -*-
r"""查清「你的 GPX」和「GeoLife 热点」分别在地球上的哪儿，以及各自的停留点数量。

用户反馈：打开前端看热点没看懂，以为"自己的数据没有热点所以没显示"。
要回答这个问题，必须把两件事分开：
  1. 热点到底显示没显示（显示了几处、来自哪些数据）
  2. 你自己的 GPX 有没有贡献热点 —— 如果没有，是在地图上的什么位置

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\where-is-my-data.py
"""
import json
import urllib.request

BASE = "http://localhost:8080"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    tracks = get("/api/tracks?limit=500")["items"]

    by_src = {}
    for t in tracks:
        detail = get(f"/api/tracks/{t['id']}")
        pts = detail.get("points") or []
        if pts:
            lons = [p["lon"] for p in pts]
            lats = [p["lat"] for p in pts]
            bbox = (min(lons), min(lats), max(lons), max(lats))
        else:
            bbox = None
        stays = get(f"/api/tracks/{t['id']}/stay-points").get("count", 0)
        by_src.setdefault(t.get("source"), []).append(
            {"id": t["id"], "name": t.get("name"), "pts": t.get("pointCount"),
             "bbox": bbox, "stays": stays}
        )

    for src, arr in by_src.items():
        print(f"\n===== 来源 {src}：{len(arr)} 条轨迹 =====")
        for r in arr[:6]:
            b = r["bbox"]
            loc = (f"经度 {b[0]:.4f}~{b[2]:.4f}, 纬度 {b[1]:.4f}~{b[3]:.4f}"
                   if b else "（无点）")
            print(f"  id={r['id']:<3} {str(r['name'])[:26]:<26} "
                  f"{r['pts']:>5} 点  停留点 {r['stays']}   {loc}")
        if len(arr) > 6:
            print(f"  ...（其余 {len(arr)-6} 条略）")
        print(f"  → 该来源停留点合计: {sum(x['stays'] for x in arr)}")

    print("\n\n===== 结论 =====")
    gpx = by_src.get("gpx", [])
    geo = by_src.get("geolife", [])
    print(f"你自己的 GPX：{len(gpx)} 条，停留点合计 {sum(x['stays'] for x in gpx)}")
    print(f"GeoLife：{len(geo)} 条，停留点合计 {sum(x['stays'] for x in geo)}")

    if gpx and geo:
        gb = [x["bbox"] for x in gpx if x["bbox"]]
        eb = [x["bbox"] for x in geo if x["bbox"]]
        if gb and eb:
            g_lon = sum(b[0] + b[2] for b in gb) / (2 * len(gb))
            g_lat = sum(b[1] + b[3] for b in gb) / (2 * len(gb))
            e_lon = sum(b[0] + b[2] for b in eb) / (2 * len(eb))
            e_lat = sum(b[1] + b[3] for b in eb) / (2 * len(eb))
            print(f"\n你的 GPX 大致中心：({g_lat:.4f}, {g_lon:.4f})")
            print(f"GeoLife 大致中心：({e_lat:.4f}, {e_lon:.4f})")
            import math
            R = 6371008.8
            p1, p2 = math.radians(g_lat), math.radians(e_lat)
            dp = p2 - p1
            dl = math.radians(e_lon - g_lon)
            a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
            d = 2 * R * math.asin(math.sqrt(min(1.0, a)))
            print(f"两地直线距离：约 {d/1000:.1f} 公里")


main()
