# -*- coding: utf-8 -*-
r"""网格密度的可行性分析：用真实数据先看一眼"做出来会是什么样"。

要回答三个问题（不靠猜）：
  1. 21 条 GeoLife 轨迹的点，按不同格边长分桶后有多少个非空格子？分布长什么样？
  2. 「点数密度」和「轨迹条数密度」会不会给出**不同的**热区？（这是口径问题，和上一阶段同源）
  3. 格子用【度数】和用【米】差多少？（纬度 40° 时 0.001° 经度只有 85 米，不是 111 米）

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\analyze-density.py
"""
import json
import math
import urllib.request
from collections import defaultdict

BASE = "http://localhost:8080"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    pts = []   # (trackId, source, lon, lat)
    for t in get("/api/tracks?limit=500")["items"]:
        for p in get(f"/api/tracks/{t['id']}")["points"]:
            pts.append((t["id"], t.get("source"), p["lon"], p["lat"]))

    geo = [p for p in pts if p[1] == "geolife"]
    print(f"总点数 {len(pts):,}，其中 GeoLife {len(geo):,} 个，来自 "
          f"{len({p[0] for p in geo})} 条轨迹")

    lons = [p[2] for p in geo]
    lats = [p[3] for p in geo]
    print(f"GeoLife 范围：经度 {min(lons):.4f}~{max(lons):.4f} "
          f"({(max(lons)-min(lons))*85280:.0f} 米)，"
          f"纬度 {min(lats):.4f}~{max(lats):.4f} ({(max(lats)-min(lats))*110574:.0f} 米)")

    print("\n=== 格子用【度数】时，实际是多少米？（纬度 40°）===")
    for size in (0.0005, 0.001, 0.002, 0.005):
        print(f"  {size}° → 东西 {(size*85280):>6.1f} 米，南北 {(size*110574):>6.1f} 米"
              f"（宽高比 {size*85280/(size*110574):.2f}）")

    print("\n=== 不同格边长下的分桶结果 ===")
    for size in (0.0005, 0.001, 0.002, 0.005):
        cells = defaultdict(lambda: [0, set()])   # key -> [点数, 轨迹集合]
        for tid, src, lon, lat in geo:
            k = (math.floor(lon / size), math.floor(lat / size))
            cells[k][0] += 1
            cells[k][1].add(tid)
        counts = sorted((v[0] for v in cells.values()), reverse=True)
        tracks = sorted((len(v[1]) for v in cells.values()), reverse=True)
        multi = sum(1 for v in cells.values() if len(v[1]) >= 3)
        print(f"  {size}°: {len(cells):>5} 个非空格子 | "
              f"点数 Top5 {counts[:5]} | 轨迹数 Top5 {tracks[:5]} | "
              f"≥3 条轨迹的格子 {multi} 个")

    print("\n=== 口径对比：0.001° 下『点数最多』vs『轨迹条数最多』的前 8 个格子 ===")
    size = 0.001
    cells = defaultdict(lambda: [0, set()])
    for tid, src, lon, lat in geo:
        k = (math.floor(lon / size), math.floor(lat / size))
        cells[k][0] += 1
        cells[k][1].add(tid)

    by_pts = sorted(cells.items(), key=lambda kv: -kv[1][0])[:8]
    by_trk = sorted(cells.items(), key=lambda kv: -len(kv[1][1]))[:8]
    print("  按点数：")
    for k, v in by_pts:
        lon = k[0] * size + size / 2
        lat = k[1] * size + size / 2
        print(f"    ({lat:.4f}, {lon:.4f})  {v[0]:>5} 点 / {len(v[1])} 条轨迹")
    print("  按轨迹条数：")
    for k, v in by_trk:
        lon = k[0] * size + size / 2
        lat = k[1] * size + size / 2
        print(f"    ({lat:.4f}, {lon:.4f})  {v[0]:>5} 点 / {len(v[1])} 条轨迹")

    same = [k for k, _ in by_pts[:5]] == [k for k, _ in by_trk[:5]]
    print(f"\n  两种口径的 Top5 是否一致：{'是' if same else '否'}")

    # 分位：决定"什么叫热"的阈值
    print("\n=== 0.001° 下点数的分位数（用来定「热」的阈值）===")
    c = sorted((v[0] for v in cells.values()))
    for q in (0.5, 0.75, 0.9, 0.95, 0.99, 1.0):
        i = min(len(c) - 1, int(q * len(c)))
        print(f"  {int(q*100):>3}% 分位 = {c[i]} 点")


main()
