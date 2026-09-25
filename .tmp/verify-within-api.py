# -*- coding: utf-8 -*-
"""
POST /api/analysis/within 的接口对拍。

⭐ 原则：一切期望值【从 SQL 现取】，不写死数据量（M2 各阶段的教训：
导一次数据就废一片脚本）。唯一写死的是"自交多边形返回 400"那类【代码行为】，
不是数据量。

与任务书原稿相比，本脚本额外钉住四件事（前序任务踩出来的）：
  1. ⭐ 400 响应体里的 message —— server.error.include-message=always 是后加的一行配置，
     谁把它改回 never，后端 162 项单测【一项都不会红】，而用户再也看不到"请重画"。
     所以这里直接断言响应体【字段】，不只是状态码。
  2. ⚠️ 别把两种 400 混为一谈：body 缺失 / JSON 畸形走的是 Spring 的
     HttpMessageNotReadableException，message 是 Jackson 的英文消息（"Required request
     body is missing"），不是我们的中文原因。断言只对【我们的参数校验分支】断言中文。
  3. ⭐ 时间窗口径（设计文档 11.12 的裁定）：同一块区域 + 一个把所有命中轨迹都排除的
     时间窗 → total=0【且】stats.pointCount=0。修复前 pointCount 会是 18 万 —— 这条
     正是那个缺陷的回归钉子；再加一条正常时间窗，断言 sum(items[].insidePointCount)
     == stats.pointCount（两者同源，必须自洽，11.12 论点 3）。
  4. ⚠️ 判据从 SQL 现取，不写死数据量。

用法（密码由调用方放进环境变量，脚本自己不读、也不打印密码）：
    $yaml = Get-Content backend/src/main/resources/application-local.yml -Raw
    if ($yaml -match '(?m)^\\s*password:\\s*(\\S+)') { $env:PGPASSWORD = $Matches[1] }
    $env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
    & "E:\\python\\python_address\\python.exe" .tmp\\verify-within-api.py
"""
import json
import math
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 控制台编码兜底：中文报错信息不能把脚本自己搞崩（不依赖调用方设对环境变量）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://localhost:8080/api/analysis/within"
PSQL = r"E:\PostgreSQL\bin\psql.exe"
DB = "calcite"

# 我们的参数校验分支抛出的中文原因（WithinService / RegionGeometry）。
# 用它把「我们的 400」和「Spring/Jackson 的 400」区分开。
OUR_400_HINT = "区域有交叉或面积为 0，请重画"

ok = 0
fail = 0
msgs = []


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        msgs.append(f"{name} :: {detail}")
        print(f"  [XX] {name}  {detail}")


def sql(q):
    """跑一条 SQL，返回按行拆好的字符串列表（-A 无对齐、-t 无表头）。

    刻意检查 returncode：psql 连不上时返回空串会让"两边相等"的断言变成
    "" == "" 的**假绿** —— 这是对拍脚本最容易骗自己的地方。
    """
    env = dict(os.environ)
    env["LC_MESSAGES"] = "C"
    env["PGCLIENTENCODING"] = "UTF8"
    out = subprocess.run([PSQL, "-U", "postgres", "-h", "localhost", "-p", "5432",
                          "-d", DB, "-At", "-c", q],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", env=env)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "").strip())
    return [ln for ln in out.stdout.splitlines() if ln != ""]


def sql_int(q):
    rows = sql(q)
    if not rows:
        raise RuntimeError("SQL 返回空结果（会让断言变成假绿）：%s" % " ".join(q.split())[:160])
    return int(rows[0])


def post(body, raw=None):
    """返回 (status, json_or_text, 耗时毫秒)。

    raw 给定时直接发这段字符串（用来测 JSON 畸形 / body 缺失），否则发 json.dumps(body)。
    """
    if raw is None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = raw.encode("utf-8")
    req = urllib.request.Request(BASE, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode("utf-8")
            try:
                return r.status, json.loads(text), (time.time() - t0) * 1000
            except Exception:
                return r.status, text, (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        # ⚠️ 400 的原因在 e.read() 里，光看 e.code 会把它丢掉
        text = e.read().decode("utf-8")
        try:
            return e.code, json.loads(text), (time.time() - t0) * 1000
        except Exception:
            return e.code, text, (time.time() - t0) * 1000


def polygon_wkt(ring):
    return "POLYGON((" + ",".join(f"{x} {y}" for x, y in ring) + "))"


BEIJING_RING = [(116.28, 39.98), (116.42, 39.98), (116.42, 40.02),
                (116.28, 40.02), (116.28, 39.98)]


def poly_body(ring, **extra):
    body = {"geometry": {"type": "Polygon", "coordinates": [ring]}}
    body.update(extra)
    return body


def body_message(res):
    """从响应体里取 message 字段（不是就返回 None）。"""
    if isinstance(res, dict):
        m = res.get("message")
        return m if isinstance(m, str) else None
    return None


if not os.environ.get("PGPASSWORD"):
    print("PGPASSWORD 未设置 —— 先把 application-local.yml 里的密码放进环境变量再跑。")
    sys.exit(2)
if not os.path.exists(PSQL):
    print("找不到 psql: %s" % PSQL)
    sys.exit(2)

wkt = polygon_wkt(BEIJING_RING)

print("=== A) 北京大框 vs SQL 真值 ===")
# ⚠️ 显式给 limit=500：默认 limit=50 会把 items 截断，那样就没法用 items 与 SQL 的命中集合对拍了
status, res, ms = post(poly_body(BEIJING_RING, limit=500))
print(f"  接口耗时 {ms:.0f} ms")
check("状态 200", status == 200, status)
truth_ids = {int(x) for x in sql(
    f"SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326))")}
check("total 等于 SQL 命中数", res["total"] == len(truth_ids),
      f'{res["total"]} vs {len(truth_ids)}')
check("limit=500 时未截断", res["truncated"] is False, res["truncated"])
check("items 的 id 集合与 SQL 命中集合完全相同",
      {i["trackId"] for i in res["items"]} == truth_ids,
      f'接口 {len(res["items"])} 条 / SQL {len(truth_ids)} 条')

def points_by_track(wkt_sql, from_sql=None, to_sql=None):
    """SQL 真值：区域内的逐条点数（可选时间窗），返回 {trackId: inside}。"""
    q = (f"SELECT track_id, count(*) FROM track_point "
         f"WHERE geom && ST_GeomFromText('{wkt_sql}',4326) "
         f"AND ST_Intersects(ST_GeomFromText('{wkt_sql}',4326), geom)")
    if from_sql is not None:
        q += f" AND recorded_at BETWEEN '{from_sql}' AND '{to_sql}'"
    q += " GROUP BY track_id"
    return {int(a): int(b) for a, b in (ln.split("|") for ln in sql(q))}


def check_stats_pointcount(name, res, truth_map):
    """⭐ stats.pointCount 必须等于 SQL 逐条分组求和（全量，不受 limit 影响）。

    这是 brief 里那条 `sum(items[].insidePointCount) == stats.pointCount` 的**正确形式**：
    brief 的写法只在 items **没被截断**时成立（见 F 段的实测：命中 53 条 > 默认 limit 50，
    items 只剩 50 条，之和必然比 pointCount 少被截掉那几条的点数）。
    统计是全量的、items 是截断的 —— 所以"同源自洽"要拿 SQL 全量真值来断，不能拿 items 断。
    """
    truth_full = sum(truth_map.values())
    check(name, res["stats"]["pointCount"] == truth_full,
          f'{res["stats"]["pointCount"]} vs SQL 全量 {truth_full}')


truth_points = sql_int(
    f"SELECT count(*) FROM track_point WHERE geom && ST_GeomFromText('{wkt}',4326) "
    f"AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom)")
check("pointCount 等于 SQL 区域内点数", res["stats"]["pointCount"] == truth_points,
      f'{res["stats"]["pointCount"]} vs {truth_points}')

truth_src = dict(ln.split("|") for ln in sql(
    f"SELECT source, count(*) FROM track WHERE id IN "
    f"(SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326))) GROUP BY 1"))
check("sourceCounts 与 SQL 一致",
      {k: int(v) for k, v in res["stats"]["sourceCounts"].items()} ==
      {k: int(v) for k, v in truth_src.items()},
      f'{res["stats"]["sourceCounts"]} vs {truth_src}')

truth_dist = float(sql(
    f"SELECT coalesce(sum(distance_m),0) FROM track WHERE id IN "
    f"(SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)))")[0])
check("distanceM 与 SQL 求和一致（相对误差 <0.01）",
      abs(res["stats"]["distanceM"] - truth_dist) <= max(0.01, truth_dist * 1e-6),
      f'{res["stats"]["distanceM"]} vs {truth_dist}')

truth_map = points_by_track(wkt)
# ⭐ limit=500 时 232 条全在 items 里 → 这里 brief 那条 `sum(items[].insidePointCount)
# == stats.pointCount` **应当严格成立**（未截断是它的前提）
check("limit=500（未截断）时 sum(items[].insidePointCount) == stats.pointCount",
      sum(i["insidePointCount"] for i in res["items"]) == res["stats"]["pointCount"],
      f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
check("每条 item 的 insidePointCount 都等于 SQL 逐条分组值",
      {i["trackId"]: i["insidePointCount"] for i in res["items"]} == truth_map,
      f'不一致 {[k for k in truth_map if dict((i["trackId"], i["insidePointCount"]) for i in res["items"]).get(k) != truth_map[k]][:5]}')
check("items 内 insidePointCount 之和 ≤ pointCount",
      sum(i["insidePointCount"] for i in res["items"]) <= res["stats"]["pointCount"])
check_stats_pointcount("pointCount == SQL 全量逐条分组求和", res, truth_map)
check("items 按 insidePointCount 降序",
      all(res["items"][i]["insidePointCount"] >= res["items"][i + 1]["insidePointCount"]
          for i in range(len(res["items"]) - 1)))
check("region 回显是对象而不是字符串",
      isinstance(res["region"], dict) and res["region"].get("type") == "Polygon",
      type(res["region"]).__name__)

# ⭐ 截断语义（顺手钉住）：默认 limit=50 时命中 232 条 → items 只留 50 条，
# 但 stats/total 仍然全量。这同时解释了"为什么不能拿 items 之和去断 pointCount"。
status, res_trunc, _ = post(poly_body(BEIJING_RING))
check("默认 limit=50 时 truncated=true", res_trunc["truncated"] is True, res_trunc["truncated"])
check("默认 limit=50 时 items 恰好 50 条", len(res_trunc["items"]) == 50, len(res_trunc["items"]))
check("截断不影响 total 与 stats（仍然全量）",
      res_trunc["total"] == res["total"]
      and res_trunc["stats"]["pointCount"] == res["stats"]["pointCount"]
      and res_trunc["stats"]["trackCount"] == res["stats"]["trackCount"],
      f'total {res_trunc["total"]} vs {res["total"]}')
check("截断时 items 之和 ≤ pointCount（保留的是点数最多的那些）",
      sum(i["insidePointCount"] for i in res_trunc["items"]) <= res_trunc["stats"]["pointCount"],
      f'{sum(i["insidePointCount"] for i in res_trunc["items"])} vs {res_trunc["stats"]["pointCount"]}')

# 保存"无时间窗"的基线，F 段要用它做关系比较（而不是写死 18 万那种数字）
base_points = res["stats"]["pointCount"]
base_total = res["total"]
print(f"  info: total={base_total} pointCount={base_points} "
      f"sourceCounts={res['stats']['sourceCounts']} latest={res['stats']['latest']}")
check("latest 与 SQL 的 max(end_time) 一致",
      res["stats"]["latest"] == sql(
          f"SELECT to_char(max(end_time) AT TIME ZONE 'UTC', "
          f"'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') FROM track WHERE id IN "
          f"(SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)))")[0],
      res["stats"]["latest"])

print("=== B) 上海缓冲区：region 必须是 33 顶点的圆多边形 ===")
status, res, ms = post({"geometry": {"type": "Point", "coordinates": [121.50, 31.29]},
                        "bufferM": 1000})
print(f"  接口耗时 {ms:.0f} ms")
check("状态 200", status == 200, status)
ring = res["region"]["coordinates"][0]
check("region 顶点数 = 33", len(ring) == 33, len(ring))
check("region 首尾闭合", ring[0] == ring[-1])
truth = sql_int("SELECT count(*) FROM track WHERE ST_DWithin(geom::geography, "
                "ST_SetSRID(ST_MakePoint(121.50,31.29),4326)::geography, 1000)")
check("与球面 ST_DWithin 的结果一致（该点附近无超长边轨迹）",
      res["total"] == truth, f'{res["total"]} vs {truth}')

# ⭐ 缓冲区"看到的圈 = 查的范围"：region 是后端拿去查询的那个几何（规格 11.4）。
# 直接量它：把回显的每个顶点按等距圆柱近似换算成米，到圆心的距离应当恒等于 bufferM。
# 这条防的是"缓冲区按度算"（漏 ::geography）—— 那样半径会是 1000 度，距离差 5 个数量级。
LAT_M_PER_DEG = 111320.0
C_LON, C_LAT = 121.50, 31.29
radii_m = [
    math.hypot((lon - C_LON) * LAT_M_PER_DEG * math.cos(math.radians(C_LAT)),
               (lat - C_LAT) * LAT_M_PER_DEG)
    for lon, lat in ring
]
worst = max(abs(r - 1000.0) for r in radii_m)
print(f"  info: region 顶点到圆心的距离 {min(radii_m):.1f} ~ {max(radii_m):.1f} 米")
check("region 每个顶点都在圆心 1000 米处（±5%，排除'按度缓冲'）",
      worst <= 50.0, f"最大偏差 {worst:.1f} 米")
check("region 顶点数 33 = 1 起点 + 32 段 + 1 闭合点",
      len(ring) == 33 and 32 <= len(radii_m) <= 33, len(ring))

print("=== C) 已知边界：3 条含超长边的轨迹（设计文档 3.4，有意钉住）===")
status, res, _ = post({"geometry": {"type": "Point", "coordinates": [118.95, 35.66]},
                       "bufferM": 1500})
truth_sphere = sql_int("SELECT count(*) FROM track WHERE ST_DWithin(geom::geography, "
                       "ST_SetSRID(ST_MakePoint(118.95,35.66),4326)::geography, 1500)")
check("平面解释返回 3 条（球面是 0 条）", res["total"] == 3, res["total"])
check("同时确认球面确实是 0 条（说明这 3 条是平面解释的产物）", truth_sphere == 0, truth_sphere)
check("这 3 条正是 121/161/166", sorted(i["trackId"] for i in res["items"]) == [121, 161, 166],
      sorted(i["trackId"] for i in res["items"]))

print("=== D) 空区域 ===")
status, res, _ = post(poly_body([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]))
check("状态 200（不是错误）", status == 200, status)
check("total = 0", res["total"] == 0, res["total"])
check("items 为空数组", res["items"] == [], res["items"])
check("统计全为 0", res["stats"]["trackCount"] == 0 and res["stats"]["pointCount"] == 0
      and res["stats"]["distanceM"] == 0, res["stats"])
check("空区域的 sourceCounts 为空", res["stats"]["sourceCounts"] == {}, res["stats"]["sourceCounts"])

print("=== E) 400 分支逐条打 ===")
bad_cases = [
    ("缺 geometry", {}),
    ("类型不在白名单", {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}),
    ("环未闭合", poly_body([(0, 0), (1, 0), (1, 1), (0, 1)])),
    ("环点数 < 4", poly_body([(0, 0), (1, 0), (0, 0)])),
    ("纬度越界", poly_body([(0, 0), (1, 0), (1, 91), (0, 91), (0, 0)])),
    ("Point 没给 bufferM", {"geometry": {"type": "Point", "coordinates": [116.3, 40.0]}}),
    ("bufferM = 0", {"geometry": {"type": "Point", "coordinates": [116.3, 40.0]}, "bufferM": 0}),
    ("bufferM 超上限", {"geometry": {"type": "Point", "coordinates": [116.3, 40.0]}, "bufferM": 99999}),
    ("limit = 0", poly_body(BEIJING_RING, limit=0)),
    ("limit = 501", poly_body(BEIJING_RING, limit=501)),
    ("from > to", poly_body(BEIJING_RING, **{"from": "2009-01-01T00:00:00Z", "to": "2008-01-01T00:00:00Z"})),
    ("自交多边形（蝴蝶结）", poly_body([(116.30, 39.90), (116.50, 40.10),
                                        (116.50, 39.90), (116.30, 40.10), (116.30, 39.90)])),
]
for name, body in bad_cases:
    status, res, _ = post(body)
    check(f"400：{name}", status == 400, f"实际 {status} {res if isinstance(res, str) else res}")
    # ⭐ 硬要求 1：我们的参数校验分支必须把【中文原因】放到响应体的 message 字段里。
    # 这条防的是 server.error.include-message 被改回 never —— 那样后端单测全绿、用户却看不到原因。
    m = body_message(res)
    check(f"400 响应体带 message（不是 status 而已）：{name}", m is not None,
          f"响应体 = {res!r}")
    if m is not None:
        check(f"400 的原因是中文（我们自己的校验分支）：{name}",
              any("\u4e00" <= ch <= "\u9fff" for ch in m), m)

# ⭐ 硬要求 1 的专门一条：自交多边形必须是设计文档承诺的那句中文原因，一字不差
status, res, _ = post(poly_body([(116.30, 39.90), (116.50, 40.10),
                                 (116.50, 39.90), (116.30, 40.10), (116.30, 39.90)]))
check("自交多边形的 400 message 等于「区域有交叉或面积为 0，请重画」",
      status == 400 and body_message(res) == OUR_400_HINT,
      f"status={status} message={body_message(res)!r}")

# ⚠️ 硬要求 2：别把两种 400 混为一谈 —— body 缺失 / JSON 畸形由 Spring 的
# HttpMessageNotReadableException 处理，message 是 Jackson 的英文消息，不是我们的中文原因。
print("--- E2) 与「框架的 400」划清界限（不是我们的校验分支）---")
status, res, _ = post(None, raw="")
check("body 缺失 → 400", status == 400, status)
m_missing = body_message(res)
print(f"  info: body 缺失时 message = {m_missing!r}")
check("body 缺失的 message 不是我们的中文原因（是框架消息）",
      m_missing is not None and m_missing != OUR_400_HINT, f"{m_missing!r}")

status, res, _ = post(None, raw='{"geometry": ')
check("JSON 畸形 → 400", status == 400, status)
m_broken = body_message(res)
print(f"  info: JSON 畸形时 message = {m_broken!r}")
check("JSON 畸形的 message 不是我们的中文原因（是 Jackson 消息）",
      m_broken is not None and m_broken != OUR_400_HINT, f"{m_broken!r}")

# ⭐ 硬要求 3（规格 11.12 的裁定）：点统计必须与 id 过滤共用同一个时间窗
print("=== F) 时间窗（重叠语义）===")
status, res, _ = post(poly_body(BEIJING_RING,
                                **{"from": "2008-11-01T00:00:00Z", "to": "2008-11-30T23:59:59Z"}))
truth = sql_int(f"SELECT count(*) FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
                f"AND start_time <= '2008-11-30T23:59:59Z' AND end_time >= '2008-11-01T00:00:00Z'")
check("时间窗命中数与 SQL 一致（含端点重叠）", res["total"] == truth, f'{res["total"]} vs {truth}')
check("时间窗是收窄而不是放大", res["total"] <= len(truth_ids), res["total"])

truth_win_points = sql_int(
    f"SELECT count(*) FROM track_point WHERE geom && ST_GeomFromText('{wkt}',4326) "
    f"AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom) "
    f"AND recorded_at BETWEEN '2008-11-01T00:00:00Z' AND '2008-11-30T23:59:59Z'")
check("时间窗内 pointCount 等于 SQL 真值（点统计也吃时间窗）",
      res["stats"]["pointCount"] == truth_win_points,
      f'{res["stats"]["pointCount"]} vs {truth_win_points}')

# 关系断言，样本永远有效：时间窗是收窄的 → pointCount 必须严格小于不带窗时
print(f"  info: 带窗 pointCount={res['stats']['pointCount']} / 不带窗 {base_points}")
check("⭐ 带时间窗的 pointCount 严格小于不带时间窗（不是同一口径）",
      res["stats"]["pointCount"] < base_points,
      f'{res["stats"]["pointCount"]} vs {base_points}')

# ⭐ 硬要求 3 的核心断言：两者同源 → 必须严格自洽（规格 11.12 论点 3）
# ⚠️ brief 写的是 `sum(items[].insidePointCount) == stats.pointCount`，但那只在 items
# **未截断**时成立：本段命中 53 条 > 默认 limit 50，items 只剩 50 条，之和必然少
# 被截掉那 3 条的点数（实测少 21 点）。所以这里用 SQL 全量逐条真值来断"同源自洽"，
# 并显式记录截断事实 —— 断言不比 brief 弱，只是把"未截断"这个前提摆到明面上。
wrong_ids = [i["trackId"] for i in res["items"] if i["insidePointCount"] != truth_map.get(i["trackId"])]
check("带窗时每条 item 的 insidePointCount 都等于 SQL 逐条分组值",
      not wrong_ids, f"不一致 {wrong_ids[:5]}")
check_stats_pointcount("⭐ pointCount == SQL 全量逐条分组求和（带时间窗，11.12 的自洽）",
                       res, points_by_track(wkt, "2008-11-01T00:00:00Z", "2008-11-30T23:59:59Z"))
if not res["truncated"]:
    check("⭐ 未截断时 sum(items[].insidePointCount) == stats.pointCount（brief 原式）",
          sum(i["insidePointCount"] for i in res["items"]) == res["stats"]["pointCount"],
          f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
else:
    # 截断了：items 之和就必须**严格小于** pointCount，差额 = 被截掉那几条的点数
    cut = sum(v for k, v in points_by_track(
        wkt, "2008-11-01T00:00:00Z", "2008-11-30T23:59:59Z").items()
        if k not in {i["trackId"] for i in res["items"]})
    check("⭐ 截断时 sum(items[].insidePointCount) + 被截掉的点数 == stats.pointCount",
          sum(i["insidePointCount"] for i in res["items"]) + cut == res["stats"]["pointCount"],
          f'{sum(i["insidePointCount"] for i in res["items"])} + {cut} vs {res["stats"]["pointCount"]}')
    print(f"  info: 本段命中 {res['total']} 条 > limit {res['params']['limit']}，"
          f"items 截断到 {len(res['items'])} 条（被截掉 {cut} 点）"
          f" —— 这就是 brief 那条断言不能直接用在这里的原因")
check("带窗时 total == stats.trackCount",
      res["total"] == res["stats"]["trackCount"], f'{res["total"]} vs {res["stats"]["trackCount"]}')
check("带窗时 items 的 id 都在 SQL 命中集合里",
      {i["trackId"] for i in res["items"]} <=
      {int(x) for x in sql(
          f"SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
          f"AND start_time <= '2008-11-30T23:59:59Z' "
          f"AND end_time >= '2008-11-01T00:00:00Z'")})
check("params 回显了 from/to/limit",
      res["params"]["from"] is not None and res["params"]["to"] is not None,
      str(res["params"]))

# ⭐ 硬要求 3 的"缺陷回归钉子"：一个把所有命中轨迹都排除的时间窗
# → total 必须是 0，而且 stats.pointCount 也必须是 0（修复前是 181211）
print("--- F2) 把所有命中轨迹都排除的时间窗（规格 11.12 那个缺陷）---")
status, res, ms = post(poly_body(BEIJING_RING,
                                 **{"from": "2020-01-01T00:00:00Z", "to": "2020-12-31T00:00:00Z"}))
print(f"  接口耗时 {ms:.0f} ms")
check("状态 200", status == 200, status)
check("⭐ 2020 时间窗：total = 0", res["total"] == 0, res["total"])
check("⭐ 2020 时间窗：stats.trackCount = 0", res["stats"]["trackCount"] == 0,
      res["stats"]["trackCount"])
check("⭐ 2020 时间窗：stats.pointCount = 0（修复前是 18 万，这是缺陷的回归钉子）",
      res["stats"]["pointCount"] == 0, res["stats"]["pointCount"])
check("2020 时间窗：items 为空（不是拿到一堆不属于这段时间的轨迹）",
      res["items"] == [], f'{len(res["items"])} 条')
check("2020 时间窗：distanceM = 0", res["stats"]["distanceM"] == 0, res["stats"]["distanceM"])
# 独立性：SQL 独立确认这个窗内确实一条都没有（免得断言"永远成立"而看不到真值）
truth_2020 = sql_int(f"SELECT count(*) FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
                     f"AND start_time <= '2020-12-31T00:00:00Z' AND end_time >= '2020-01-01T00:00:00Z'")
check("SQL 独立确认该时间窗内本来就没有命中的轨迹", truth_2020 == 0, truth_2020)

# 半开窗：只给 from，不给 to —— 走"无限宽哨兵"。
# ⚠️ 期望值不能写死 0：数据里有一条 sample 轨迹是 2026-09-08（见 project 记忆的"已知数据事实"），
# 所以 from=2020 且 to 无限宽时它【应当】命中。正确做法还是从 SQL 现取真值。
print("--- F3) 只给 from（另一端无限宽哨兵）---")
FROM_2020 = "2020-01-01T00:00:00Z"
TO_SENTINEL = "2999-12-31T23:59:59Z"          # WithinService.MAX_TIME
status, res, ms = post(poly_body(BEIJING_RING, **{"from": FROM_2020}))
check("状态 200", status == 200, status)
truth_half = sql_int(
    f"SELECT count(*) FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
    f"AND start_time <= '{TO_SENTINEL}' AND end_time >= '{FROM_2020}'")
check("只给 from：total 与 SQL（另一端无限宽）一致", res["total"] == truth_half,
      f'{res["total"]} vs {truth_half}')
check("只给 from：pointCount 与 SQL 一致（哨兵两处共用）",
      res["stats"]["pointCount"] == sum(points_by_track(wkt, FROM_2020, TO_SENTINEL).values()),
      f'{res["stats"]["pointCount"]} vs '
      f'{sum(points_by_track(wkt, FROM_2020, TO_SENTINEL).values())}')
check("只给 from：total == stats.trackCount",
      res["total"] == res["stats"]["trackCount"], f'{res["total"]} vs {res["stats"]["trackCount"]}')
# 用 SQL 印证"它命中的确实是那条 2026 年的 sample 轨迹"，而不是碰巧对上了
sample_ids = {int(x) for x in sql(
    f"SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
    f"AND start_time <= '{TO_SENTINEL}' AND end_time >= '{FROM_2020}'")}
check("只给 from：items 的 id 集合与 SQL 命中集合完全相同",
      {i["trackId"] for i in res["items"]} == sample_ids,
      f'{sorted(i["trackId"] for i in res["items"])} vs {sorted(sample_ids)}')
# 无上界的窗会把"整条轨迹"也算进来，因此 pointCount 必然不为 0（只要真值不为 0）
check("只给 from：pointCount 与 2020 那条轨迹无关地自洽（说明没误用「全排除」语义）",
      res["stats"]["pointCount"] == 0 if truth_half == 0 else res["stats"]["pointCount"] > 0,
      f'truth_half={truth_half} pointCount={res["stats"]["pointCount"]}')

print()
print(f"{ok} 项通过，{fail} 项失败")
if msgs:
    print("失败明细：")
    for m in msgs:
        print("  -", m)
sys.exit(1 if fail else 0)
