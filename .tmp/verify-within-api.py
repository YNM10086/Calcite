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
        print(f"  [OK] {name}", flush=True)
    else:
        fail += 1
        msgs.append(f"{name} :: {detail}")
        print(f"  [XX] {name}  {detail}", flush=True)


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

# F 段那个时间窗（多处复用，避免抄错字符串）—— 必须是**模块级**：
# check_f_section 在模块级定义，读不到 main() 的局部变量（本轮踩到过这个 NameError）。
WIN_FROM = "2008-11-01T00:00:00Z"
WIN_TO = "2008-11-30T23:59:59Z"
# 「无限宽」上界哨兵，与 WithinService.MAX_TIME 一致
TO_SENTINEL = "2999-12-31T23:59:59Z"
# 从 application.yml 读到的两个 limit（判据从真值推导，不写死数据假设）
LIMIT_MAX = 500     # calcite.within.max-limit
LIMIT_DEFAULT = 50  # calcite.within.default-limit


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


def points_by_track(wkt_sql, from_sql=None, to_sql=None):
    """SQL 真值：区域内的逐条点数（可选时间窗），返回 {trackId: inside}。

    ⚠️ 「带窗」与「不带窗」是两份**不同的**真值，不能互相顶替 —— 断言必须用与响应
    同一个口径的那一份（这是审查抓到的 Important，见报告第 11 节）。
    """
    q = (f"SELECT track_id, count(*) FROM track_point "
         f"WHERE geom && ST_GeomFromText('{wkt_sql}',4326) "
         f"AND ST_Intersects(ST_GeomFromText('{wkt_sql}',4326), geom)")
    if from_sql is not None:
        q += f" AND recorded_at BETWEEN '{from_sql}' AND '{to_sql}'"
    q += " GROUP BY track_id"
    return {int(a): int(b) for a, b in (ln.split("|") for ln in sql(q))}


def shaped_ok(res):
    """响应是否是"能继续取字段"的形状（状态 200 且关键字段在）。

    没有这道守卫时，一旦接口回 500，下面 res["total"] 会以 KeyError/TypeError
    的 traceback 结束 —— 而不是给出一行可读的 [XX]。
    """
    return (isinstance(res, dict) and "stats" in res and "items" in res
            and "region" in res and "total" in res)


def wrong_inside_ids(items, truth_map):
    """返回 items 里 insidePointCount 与 **传入的那份真值** 不符的 trackId 列表。

    ⚠️ 关键在"传入的那份"：调用方必须传与响应**同一个时间窗口径**的真值。
    审查抓到的 Important 就是这里被传了错的那一份（不带窗的真值配带窗的响应），
    而当时数据恰好让两份真值等价 → 断言绿得**没有验证它声称的东西**。

    做成参数化（而不是闭包直接读某个全局 map）正是为了让"口径"成为一个显式参数，
    并且可以被 `_red-verify-task6.py` 用一个**人造的跨窗响应**证伪。
    """
    return [i["trackId"] for i in items
            if i["insidePointCount"] != truth_map.get(i["trackId"])]


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

def check_f_section(status, res, wkt, truth_map, truth_ids, base_points):
    """F 段（时间窗）的全部断言，**自带非 200 守卫**。

    ⚠️ 抽成函数是为了让守卫能干净地包住整段（原来这十几行是平铺在 main() 里的，
    非 200 时 res["total"] / res["stats"] 会 KeyError/TypeError 崩掉，
    连最后的汇总行都不打印 —— 审查 Minor 4 第 1 条）。

    ⭐ 带窗的响应对应的**必须是带窗的真值**：`WIN_MAP = points_by_track(wkt, WIN_FROM, WIN_TO)`，
    不是调用方传进来的 `truth_map`（那是**不带窗**的）。这是审查抓到的 Important ——
    两者只在"每条命中轨迹的区域内点全落在窗内"时才相等。

    返回 WIN_MAP（失败时返回 {}），供 F2/F3 继续复用。
    """
    if not (status == 200 and shaped_ok(res)):
        check("F 段响应形状可继续断言（stats/items/total 都在）", False,
              f"status={status} res={res if isinstance(res, str) else type(res).__name__}")
        return {}
    WIN_MAP = points_by_track(wkt, WIN_FROM, WIN_TO)
    truth = sql_int(f"SELECT count(*) FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
                    f"AND start_time <= '{WIN_TO}' AND end_time >= '{WIN_FROM}'")
    check("时间窗命中数与 SQL 一致（含端点重叠）", res["total"] == truth, f'{res["total"]} vs {truth}')
    check("时间窗是收窄而不是放大", res["total"] <= len(truth_ids), res["total"])

    truth_win_points = sql_int(
        f"SELECT count(*) FROM track_point WHERE geom && ST_GeomFromText('{wkt}',4326) "
        f"AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom) "
        f"AND recorded_at BETWEEN '{WIN_FROM}' AND '{WIN_TO}'")
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
    # **未截断**时成立。所以这里用 SQL 全量逐条真值来断"同源自洽"，并显式记录截断事实。
    wrong_ids = wrong_inside_ids(res["items"], WIN_MAP)
    check("带窗时每条 item 的 insidePointCount 都等于【带窗】SQL 逐条分组值",
          not wrong_ids, f"不一致 {wrong_ids[:5]}")

    # ⭐ 口径必须是显式的：把"不带窗真值与带窗真值在当前数据上恰好等价"这个巧合
    # 摆到明面上，而不是让它偷偷撑着一条假绿的断言。
    # ⚠️ 这是**信息输出，不是断言**（审查 Minor 4 第 3 条）：出现跨窗轨迹时它**不该红** ——
    # 那时接口仍然是对的，只是 F 段的口径从此真正有区分力了。判成断言 = 假红。
    shared = set(truth_map) & set(WIN_MAP)
    n_diff = sum(1 for k in shared if truth_map[k] != WIN_MAP[k])
    if n_diff == 0:
        print(f"  info: 不带窗真值 {len(truth_map)} 条 / 带窗真值 {len(WIN_MAP)} 条；共有 {len(shared)} 条，"
              f"两份在共有轨迹上【相等】—— 当前数据没有跨窗轨迹，"
              f"口径混用查不出来，所以 F 段必须显式传 WIN_MAP")
    else:
        print(f"  info: 注意：不带窗与带窗的两份真值在共有轨迹上已不相等"
              f"（跨窗轨迹 {n_diff} 条出现了）—— F 段断言现在才真正有区分力")
    print(f"  info: 不带窗点数 {sum(truth_map.values())} / 带窗点数 {sum(WIN_MAP.values())}")

    check_stats_pointcount("⭐ pointCount == SQL 全量逐条分组求和（带时间窗，11.12 的自洽）",
                           res, WIN_MAP)
    if not res["truncated"]:
        check("⭐ 未截断时 sum(items[].insidePointCount) == stats.pointCount（brief 原式）",
              sum(i["insidePointCount"] for i in res["items"]) == res["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
    else:
        cut = sum(v for k, v in WIN_MAP.items() if k not in {i["trackId"] for i in res["items"]})
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
              f"AND start_time <= '{WIN_TO}' AND end_time >= '{WIN_FROM}'")})
    check("params 回显了 from/to/limit",
          res["params"]["from"] is not None and res["params"]["to"] is not None,
          str(res["params"]))
    return WIN_MAP


def check_a_section(status, res, wkt, limit_max):
    """A 段（北京大框 vs SQL 真值）的全部断言，**自带非 200 守卫**。

    抽成函数的理由与 check_f_section 相同：守卫要干净地包住整段，
    否则非 200 时 res["total"] / res["truncated"] 会 KeyError 崩掉（审查 Minor 3 的彻底版）。

    ⚠️ brief 那条 `sum(items[].insidePointCount) == stats.pointCount` 的**前提是"未截断"**，
    这里用 `res["truncated"]` 门控，两种情形各断各的（不写死"未截断"，否则命中 > limit 时假红）。

    返回 (truth_ids, base_total, base_points, truth_map)；失败时返回 None。
    """
    if not (status == 200 and shaped_ok(res)):
        check("A 段响应形状可继续断言（stats/items/region/total 都在）", False,
              f"status={status} res={res if isinstance(res, str) else type(res).__name__}")
        print("A 段无法继续 —— 先修接口。")
        return None

    truth_ids = {int(x) for x in sql(
        f"SELECT id FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326))")}
    # "无时间窗"的基线：F 段与截断段都要用它做**关系比较**（而不是写死 18 万那种数字）
    base_total = res["total"]
    base_points = res["stats"]["pointCount"]

    truth_points = sql_int(
        f"SELECT count(*) FROM track_point WHERE geom && ST_GeomFromText('{wkt}',4326) "
        f"AND ST_Intersects(ST_GeomFromText('{wkt}',4326), geom)")
    check("pointCount 等于 SQL 区域内点数", res["stats"]["pointCount"] == truth_points,
          f'{res["stats"]["pointCount"]} vs {truth_points}')

    # ⚠️ 截断标志的判据必须由**命中数**推导，不能写死"未截断" —— 重导数据后会假红
    check(f"limit={limit_max} 时 truncated == (命中数 > {limit_max})",
          res["truncated"] == (len(truth_ids) > limit_max),
          f'truncated={res["truncated"]} 命中数={len(truth_ids)}')
    check("total 等于 SQL 命中数", res["total"] == len(truth_ids),
          f'{res["total"]} vs {len(truth_ids)}')
    check("items 的 id 集合与 SQL 命中集合完全相同",
          {i["trackId"] for i in res["items"]} == truth_ids,
          f'接口 {len(res["items"])} 条 / SQL {len(truth_ids)} 条')

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
    # ⭐ brief 那条断言的**前提是"未截断"**：不能写死，命中数 > limit 时 items 会被截断，
    # 写死"未截断"就假红了（审查 Minor 4 新发现 2）。用 res["truncated"] 门控。
    if not res["truncated"]:
        check(f"limit={limit_max}（未截断）时 sum(items[].insidePointCount) == stats.pointCount",
              sum(i["insidePointCount"] for i in res["items"]) == res["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
    else:
        a_cut = sum(v for k, v in truth_map.items() if k not in {i["trackId"] for i in res["items"]})
        check(f"limit={limit_max}（截断）时 sum(items) + 被截掉的点数 == stats.pointCount",
              sum(i["insidePointCount"] for i in res["items"]) + a_cut == res["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res["items"])} + {a_cut} vs {res["stats"]["pointCount"]}')
        print(f"  info: A 段命中 {res['total']} 条 > limit {limit_max}，items 截断到 "
              f"{len(res['items'])} 条（被截掉 {a_cut} 点）")
    # 逐条点数：只比 items 里实际出现的那几条（截断时真值里多出来的键不该算作"不一致"）
    check("每条 item 的 insidePointCount 都等于 SQL 逐条分组值",
          not wrong_inside_ids(res["items"], truth_map),
          f'不一致 {wrong_inside_ids(res["items"], truth_map)[:5]}')
    # ⭐ 未截断时这条必须**真的相等**，不能只断 ≤（本轮修）：A 段显式 limit=max，
    # 命中数小于 limit 时 items 就是全量，之和与 pointCount 同源 → 必须严格相等。
    # ⚠️ 但不能把"未截断"写死成数据假设（重导数据可能让命中数超过 limit，那样就假红了）：
    # 用 res["truncated"] 门控 —— 截断时 items 被裁过，只能 ≤（那种情况由上面 if/else 里
    # 那条"sum(items) + 被截掉的点数 == pointCount"负责，它比这条更强）。
    if not res["truncated"]:
        check(f"limit={limit_max}（未截断）时 items 内 insidePointCount 之和 == pointCount",
              sum(i["insidePointCount"] for i in res["items"]) == res["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
    else:
        check("items 内 insidePointCount 之和 ≤ pointCount（截断时 items 被裁，只能 ≤）",
              sum(i["insidePointCount"] for i in res["items"]) <= res["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res["items"])} vs {res["stats"]["pointCount"]}')
    check_stats_pointcount("pointCount == SQL 全量逐条分组求和", res, truth_map)
    check("items 按 insidePointCount 降序",
          all(res["items"][i]["insidePointCount"] >= res["items"][i + 1]["insidePointCount"]
              for i in range(len(res["items"]) - 1)))
    check("region 回显是对象而不是字符串",
          isinstance(res["region"], dict) and res["region"].get("type") == "Polygon",
          type(res["region"]).__name__)
    return truth_ids, base_total, base_points, truth_map


def main():
    # 前置检查放进 main()：这样 `import` 本文件（供 _red-verify-task6.py 抽函数）
    # 不会因为没有密码/没有 psql 就 sys.exit。
    if not os.environ.get("PGPASSWORD"):
        print("PGPASSWORD 未设置 —— 先把 application-local.yml 里的密码放进环境变量再跑。")
        sys.exit(2)
    if not os.path.exists(PSQL):
        print("找不到 psql: %s" % PSQL)
        sys.exit(2)

    wkt = polygon_wkt(BEIJING_RING)

    print("=== A) 北京大框 vs SQL 真值 ===")
    # ⚠️ 显式给 limit=max：默认 limit=50 会把 items 截断，那样就没法用 items 与 SQL 的命中集合对拍了
    status, res, ms = post(poly_body(BEIJING_RING, limit=LIMIT_MAX))
    print(f"  接口耗时 {ms:.0f} ms")
    check("状态 200", status == 200, status)
    # 整段（含非 200 守卫）在 check_a_section 里，见本文件上方定义
    a_out = check_a_section(status, res, wkt, LIMIT_MAX)
    if a_out is None:
        print(f"\n{ok} 项通过，{fail} 项失败")
        for _m in msgs:
            print("  -", _m)
        sys.exit(1)
    truth_ids, base_total, base_points, truth_map = a_out

    # ⭐ 截断语义（顺手钉住）：命中数超过默认 limit 时 items 只留 limit 条，
    # 但 stats/total 仍然全量。这同时解释了"为什么不能拿 items 之和去断 pointCount"。
    # ⚠️ 「必然截断」是**数据假设**（要求命中数 > 50），重导数据会假红 ——
    # 判据一律由 base_total（来自上面那条 200 响应的 total）推导（审查 Minor 2）。
    status, res_trunc, _ = post(poly_body(BEIJING_RING))
    # ⚠️ 与其它段同类：形状不对就不能再取字段（res_trunc 是 str 时 len(res_trunc["items"]) 会 TypeError）
    if not (status == 200 and shaped_ok(res_trunc)):
        check("截断段响应形状可继续断言", False, f"status={status}")
    else:
        print(f"  info: 默认 limit={LIMIT_DEFAULT} 时 total={base_total} "
              f"items={len(res_trunc['items'])} truncated={res_trunc['truncated']}")
        check(f"默认 limit={LIMIT_DEFAULT} 时 truncated == (total > {LIMIT_DEFAULT})",
              res_trunc["truncated"] == (base_total > LIMIT_DEFAULT),
              f'truncated={res_trunc["truncated"]} total={base_total}')
        check(f"默认 limit={LIMIT_DEFAULT} 时 items 条数 == min({LIMIT_DEFAULT}, total)",
              len(res_trunc["items"]) == min(LIMIT_DEFAULT, base_total),
              f'{len(res_trunc["items"])} vs min({LIMIT_DEFAULT}, {base_total})')
        check("截断不影响 total 与 stats（仍然全量）",
              res_trunc["total"] == res["total"]
              and res_trunc["stats"]["pointCount"] == res["stats"]["pointCount"]
              and res_trunc["stats"]["trackCount"] == res["stats"]["trackCount"],
              f'total {res_trunc["total"]} vs {res["total"]}')
        check("截断时 items 之和 ≤ pointCount（保留的是点数最多的那些）",
              sum(i["insidePointCount"] for i in res_trunc["items"]) <= res_trunc["stats"]["pointCount"],
              f'{sum(i["insidePointCount"] for i in res_trunc["items"])} vs {res_trunc["stats"]["pointCount"]}')

    # 无时间窗基线的 info 行（base_total / base_points 已在 A 段开头定义）
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
    if not (status == 200 and shaped_ok(res)):
        # ⚠️ 非 200 / 非 JSON 错误体（res 是 str）都不能再取字段：
        # res["region"]... 会 TypeError，而 res.get("total") 在 str 上会 **AttributeError**
        # —— 所以下面这条断言也必须放进守卫里（审查 Minor 4 的 B 段部分）。
        check("B 段响应形状可继续断言（region/total 在）", False,
              f"status={status} res={res if isinstance(res, str) else type(res).__name__}")
        ring = []
        radii_m = []
    else:
        ring = res["region"]["coordinates"][0]
        if ring:
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
    if radii_m:
        worst = max(abs(r - 1000.0) for r in radii_m)
        print(f"  info: region 顶点到圆心的距离 {min(radii_m):.1f} ~ {max(radii_m):.1f} 米"
              f"（含闭合点共 {len(radii_m)} 个顶点）")
        check("region 每个顶点都在圆心 1000 米处（±5%，排除'按度缓冲'）",
              worst <= 50.0, f"最大偏差 {worst:.1f} 米")

        # ⭐ 计划/任务书 Review Focus #3 点名要求的「面积 ≈ πr²」：
        # 用**鞋带公式**独立算回显多边形的平面面积（等距圆柱近似，与上面量半径同一套换算），
        # 与 π·1000² 比。这条是"圈出来的区域 = 一个半径 1000 米的圆"的另一个角度：
        # 顶点距离对 → 保证是圆；面积对 → 保证没有"缺一块/多一块"的病态多边形。
        def shoelace_m2(pts):
            """鞋带公式：返回无符号平面面积（输入已换算成米）。"""
            s = 0.0
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                s += x1 * y2 - x2 * y1
            return abs(s) / 2.0

        ring_m = [((lon - C_LON) * LAT_M_PER_DEG * math.cos(math.radians(C_LAT)),
                   (lat - C_LAT) * LAT_M_PER_DEG) for lon, lat in ring]
        area_m2 = shoelace_m2(ring_m)
        expect_area = math.pi * 1000.0 * 1000.0
        rel = abs(area_m2 - expect_area) / expect_area
        print(f"  info: region 鞋带公式面积 {area_m2:,.0f} m² vs πr² {expect_area:,.0f} m² "
              f"（相对差 {rel * 100:.2f}%）")
        check("region 面积 ≈ π·1000²（±5%，Review Focus #3）",
              rel <= 0.05, f"{area_m2:.0f} vs {expect_area:.0f}（相对差 {rel * 100:.2f}%）")

    print("=== C) 已知边界：3 条含超长边的轨迹（设计文档 3.4，有意钉住）===")
    status, res, _ = post({"geometry": {"type": "Point", "coordinates": [118.95, 35.66]},
                           "bufferM": 1500})
    truth_sphere = sql_int("SELECT count(*) FROM track WHERE ST_DWithin(geom::geography, "
                           "ST_SetSRID(ST_MakePoint(118.95,35.66),4326)::geography, 1500)")
    check("同时确认球面确实是 0 条（说明这 3 条是平面解释的产物）", truth_sphere == 0, truth_sphere)
    if not (status == 200 and shaped_ok(res)):
        check("C 段响应形状可继续断言", False, f"status={status}")
    else:
        check("平面解释返回 3 条（球面是 0 条）", res["total"] == 3, res["total"])
        check("这 3 条正是 121/161/166",
              sorted(i["trackId"] for i in res["items"]) == [121, 161, 166],
              sorted(i["trackId"] for i in res["items"]))

    print("=== D) 空区域 ===")
    status, res, _ = post(poly_body([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]))
    check("状态 200（不是错误）", status == 200, status)
    if not (status == 200 and shaped_ok(res)):
        check("D 段响应形状可继续断言", False, f"status={status}")
    else:
        check("total = 0", res["total"] == 0, res["total"])
        check("items 为空数组", res["items"] == [], res["items"])
        check("统计全为 0", res["stats"]["trackCount"] == 0 and res["stats"]["pointCount"] == 0
              and res["stats"]["distanceM"] == 0, res["stats"])
        check("空区域的 sourceCounts 为空",
              res["stats"]["sourceCounts"] == {}, res["stats"]["sourceCounts"])

    print("=== E) 400 分支逐条打 ===")
    # ⭐ 规格 9.4 点名的两条本轮补上（审查 Minor）：
    #   ① 顶点数超限 —— 必须是一个**结构完好**的多边形（环闭合、每个点在经纬度范围内、
    #      面积不为 0），否则会先被别的分支挡掉，这条就验不到"顶点数"那个分支。
    #      所以用一个 2000 段的圆：2000 个不同顶点 + 闭合点 = **2001 个顶点** > max-vertices 2000。
    #   ② 经度越界 —— lon=181（纬度那一条已有）。
    BIG_RING_N = 2000
    big_ring = [(116.4 + 0.01 * math.cos(2 * math.pi * i / BIG_RING_N),
                 40.0 + 0.01 * math.sin(2 * math.pi * i / BIG_RING_N))
                for i in range(BIG_RING_N)]
    big_ring.append(big_ring[0])          # 闭合 → 顶点数 = 2001
    bad_cases = [
        ("缺 geometry", {}),
        ("类型不在白名单", {"geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}),
        ("环未闭合", poly_body([(0, 0), (1, 0), (1, 1), (0, 1)])),
        ("环点数 < 4", poly_body([(0, 0), (1, 0), (0, 0)])),
        ("纬度越界", poly_body([(0, 0), (1, 0), (1, 91), (0, 91), (0, 0)])),
        ("经度越界（lon=181）", poly_body([(170, 0), (181, 0), (181, 10), (170, 10), (170, 0)])),
        (f"顶点数超限（{len(big_ring)} 个顶点 > 2000）", poly_body(big_ring)),
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

    # ⭐ 本轮新补的两条 400 也要**指名道姓**：E 段循环只断言"是中文"太弱 ——
    # 顶点数超限 / 经度越界都可能被**别的分支**先挡下来（消息一样是中文），
    # 那样"验到了顶点数上限"就是假的。所以再各断言一次原因里的关键词。
    status, res, _ = post(poly_body(big_ring))
    check(f"顶点数超限（{len(big_ring)} 个顶点）的 400 原因提到「顶点数」",
          status == 400 and "顶点数" in (body_message(res) or ""),
          f"status={status} message={body_message(res)!r}")
    status, res, _ = post(poly_body([(170, 0), (181, 0), (181, 10), (170, 10), (170, 0)]))
    check("经度越界（lon=181）的 400 原因提到「经度」",
          status == 400 and "经度" in (body_message(res) or ""),
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
    status, res, _ = post(poly_body(BEIJING_RING, **{"from": WIN_FROM, "to": WIN_TO}))
    check("状态 200", status == 200, status)
    # 整段（含非 200 守卫）在 check_f_section 里，见本文件上方定义
    WIN_MAP = check_f_section(status, res, wkt, truth_map, truth_ids, base_points)

    # ⭐ 硬要求 3 的"缺陷回归钉子"：一个把所有命中轨迹都排除的时间窗
    # → total 必须是 0，而且 stats.pointCount 也必须是 0（修复前是 181211）
    print("--- F2) 把所有命中轨迹都排除的时间窗（规格 11.12 那个缺陷）---")
    EMPTY_FROM = "2020-01-01T00:00:00Z"
    EMPTY_TO = "2020-12-31T00:00:00Z"
    status, res, ms = post(poly_body(BEIJING_RING, **{"from": EMPTY_FROM, "to": EMPTY_TO}))
    print(f"  接口耗时 {ms:.0f} ms")
    check("状态 200", status == 200, status)
    if not (status == 200 and shaped_ok(res)):
        check("F2 段响应形状可继续断言", False, f"status={status}")
    else:
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
                         f"AND start_time <= '{EMPTY_TO}' AND end_time >= '{EMPTY_FROM}'")
    check("SQL 独立确认该时间窗内本来就没有命中的轨迹", truth_2020 == 0, truth_2020)

    # 半开窗：只给 from，不给 to —— 走"无限宽哨兵"。
    # ⚠️ 期望值不能写死 0：数据里有一条 sample 轨迹是 2026-09-08（见 project 记忆的"已知数据事实"），
    # 所以 from=2020 且 to 无限宽时它【应当】命中。正确做法还是从 SQL 现取真值。
    print("--- F3) 只给 from（另一端无限宽哨兵）---")
    FROM_2020 = "2020-01-01T00:00:00Z"
    # TO_SENTINEL 已在文件开头定义（与 WithinService.MAX_TIME 一致）
    status, res, ms = post(poly_body(BEIJING_RING, **{"from": FROM_2020}))
    check("状态 200", status == 200, status)
    HALF_MAP = points_by_track(wkt, FROM_2020, TO_SENTINEL)
    truth_half = sql_int(
        f"SELECT count(*) FROM track WHERE ST_Intersects(geom, ST_GeomFromText('{wkt}',4326)) "
        f"AND start_time <= '{TO_SENTINEL}' AND end_time >= '{FROM_2020}'")
    if not (status == 200 and shaped_ok(res)):
        check("F3 段响应形状可继续断言", False, f"status={status}")
    else:
        check("只给 from：total 与 SQL（另一端无限宽）一致", res["total"] == truth_half,
              f'{res["total"]} vs {truth_half}')
        check("只给 from：pointCount 与 SQL 一致（哨兵两处共用）",
              res["stats"]["pointCount"] == sum(HALF_MAP.values()),
              f'{res["stats"]["pointCount"]} vs {sum(HALF_MAP.values())}')
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
        check("只给 from：pointCount 与「全排除」语义不同地自洽",
              res["stats"]["pointCount"] == 0 if truth_half == 0 else res["stats"]["pointCount"] > 0,
              f'truth_half={truth_half} pointCount={res["stats"]["pointCount"]}')

    print()
    print(f"{ok} 项通过，{fail} 项失败")
    if msgs:
        print("失败明细：")
        for m in msgs:
            print("  -", m)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
