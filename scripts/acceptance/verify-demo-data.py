# -*- coding: utf-8 -*-
"""演示数据集验收：导入 `scripts/db/04-demo-data.sql` 之后，**五个面板是否都有东西看**。

这正是 M4 演示数据集存在的唯一理由（见 docs/superpowers/specs/2026-09-25-m4-wrapup-design.md 的 5.2）。
判据**从接口取真值**、不写死数据量（M2 的教训：9 处写死数字会同时失效）。

前置：
  1. 后端在跑（8080）
  2. 演示数据已导入**后端连着的那个库**：
     psql -U postgres -d calcite -f scripts/db/04-demo-data.sql
  （验收完记得清理：DELETE FROM track WHERE external_id LIKE 'DEMO-%';）

跑法（从仓库根目录）：
    & "E:\\python\\python_address\\python.exe" scripts\\acceptance\\verify-demo-data.py
退出码：0 = 全部通过；1 = 有失败项。
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {name}")
    else:
        fail += 1
        print(f"  FAIL {name} —— {extra}")


def get(path, **params):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    print("=== 0) 后端与演示数据是否在 ===")
    try:
        health = get("/api/health")
        print(f"  /api/health -> {health.get('status')}；{health.get('database','')[:40]}")
    except Exception as e:                                    # noqa: BLE001
        print(f"  !! 后端没起来（{type(e).__name__}: {e}）—— 先起 8080")
        return 1

    page = get("/api/tracks", limit=500)
    items = page.get("items", page if isinstance(page, list) else [])
    demo = [t for t in items if str(t.get("source")) == "demo"]
    print(f"  轨迹总数={len(items)}；其中演示（source=demo）={len(demo)}")
    check("演示数据集已导入（≥14 条 source=demo 的轨迹）", len(demo) >= 14,
          f"实际 {len(demo)} 条 —— 先跑 psql -f scripts/db/04-demo-data.sql")
    if len(demo) < 14:
        return 1

    by_name = {t["name"]: t for t in demo}

    def find(*keywords):
        for name, t in by_name.items():
            if all(k in name for k in keywords):
                return t
        return None

    print("\n=== 1) 停留点面板 ===")
    commute = find("通勤") or demo[0]
    stay = get(f"/api/tracks/{commute['id']}/stay-points")
    # 接口返回 {trackId, count, stays:[...]}（字段名以真实响应为准）
    stays = stay.get("stays", stay.get("stayPoints", stay if isinstance(stay, list) else []))
    check(f"通勤轨迹（{commute['name']}）有停留点 ≥1", len(stays) >= 1, f"实际 {len(stays)} 个")
    run = find("跑步") or find("环湖")
    if run:
        rs = get(f"/api/tracks/{run['id']}/stay-points")
        rl = rs.get("stays", rs.get("stayPoints", rs if isinstance(rs, list) else []))
        check(f"环湖跑步轨迹（{run['name']}）停留点 = 0（诚实为 0 也算通过）", len(rl) == 0,
              f"实际 {len(rl)} 个")

    print("\n=== 2) 热点面板 ===")
    hs = get("/api/analysis/hotspots", minVisits=2)
    # 接口返回 {scannedTracks, scannedStays, params, hotspots:[...]}
    clusters = hs.get("hotspots", hs.get("clusters", hs.get("items", [])))
    mx = max((c.get("trackCount", c.get("visitCount", 0)) for c in clusters), default=0)
    check("热点 ≥2 个", len(clusters) >= 2, f"实际 {len(clusters)} 个")
    check("最热的热点 trackCount ≥3（三条到访同一广场）", mx >= 3, f"实际最大 {mx}")

    print("\n=== 3) 密度面板 ===")
    bbox = "116.20,39.85,116.45,40.05"
    d1 = get("/api/analysis/density", bbox=bbox, cellSize=0.002)
    # 接口返回 {bbox, cellSize, metric, scanned, params, cells:[{lon,lat,points,tracks,value}]}
    cells = d1.get("cells", [])
    mx_cell = max((c.get("value", c.get("tracks", c.get("count", 0))) for c in cells), default=0)
    check("密度格子非空", len(cells) > 0, "实际 0 个格子")
    check("最密格子 ≥3 条轨迹", mx_cell >= 3, f"实际最大 {mx_cell}")
    d2 = get("/api/analysis/density", bbox=bbox, cellSize=0.002, hourFrom=7, hourTo=10)
    check("带时段筛选（07~10 点）结果与全天不同",
          json.dumps(d2.get("cells"), sort_keys=True) != json.dumps(cells, sort_keys=True),
          "两者完全一致 —— 演示数据没有时间分布差异？")

    print("\n=== 4) 相似度面板 ===")
    sim = get("/api/analysis/similarity", trackId=commute["id"], limit=5)
    matches = sim.get("matches", sim.get("items", []))
    top = matches[0] if matches else None
    check("通勤主线能找到相似轨迹", bool(top), "matches 为空")
    if top:
        pct = top.get("similarity", top.get("percent", 0))
        name = top.get("name", "")
        check("第一名相似度 ≥60%", pct >= 0.6 or pct >= 60, f"实际 {pct}")
        check("第一名就是那条『通勤回程』", "回程" in name, f"实际是「{name}」")

    print("\n=== 5) 圈选面板 ===")
    body = {"geometry": {"type": "Polygon", "coordinates": [[
        [116.30, 39.90], [116.42, 39.90], [116.42, 40.00], [116.30, 40.00], [116.30, 39.90]]]}}
    w = post("/api/analysis/within", body)
    stats = w.get("stats", {})
    check("圈选命中轨迹 ≥1", stats.get("trackCount", 0) >= 1, f"实际 {stats.get('trackCount')}")
    check("圈选的区域内点数 >0", stats.get("pointCount", 0) > 0, f"实际 {stats.get('pointCount')}")

    print(f"\n结果：{ok} 项通过，{fail} 项失败")
    print("提醒：验收完请清理演示数据 —— DELETE FROM track WHERE external_id LIKE 'DEMO-%';")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:                        # noqa: BLE001
        print(f"!! HTTP {e.code}: {e.read().decode()[:400]}")
        sys.exit(1)
