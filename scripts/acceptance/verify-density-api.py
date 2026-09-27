# -*- coding: utf-8 -*-
r"""网格密度接口的独立对拍（M2 第三阶段 Task 4）。

为什么要这个脚本：Java 单测只覆盖【参数校验】，覆盖不到 **SQL**；
而网格密度这个功能的价值全在 SQL 上。所以必须有独立实现来对拍。

它做两件单测做不到的事：

A. 等价性验证（本脚本最重要的一条）
   后端 SQL 用的是 round(ST_X(geom)/:cell)::int，**不是**设计文档原文写的
   ST_SnapToGrid(geom, :cell)。改写的理由是后者要排序、会落盘临时文件，慢约 2 倍。
   但"快"不能以"算出来的格子不一样"为代价，所以这里用 SQL 断言：
     ① 两种写法分出的格子**数**相同；
     ② 双向差集都为空 —— 即格子集合**逐个相同**，而不只是"个数碰巧一样"。
   注意断言是**关系的**（两种写法互比），**不写死任何历史数字**：
   设计文档里曾混入一批来自不同查询条件的数字（736 / 3867 / 3916 …），
   教训是验收标准要和"同一查询的独立实现"比，**不和历史数字比**。

   ⚠️ 2026-09-17 实测结论（本次发现，断言**没有**为此放松）：
   两者**不是处处等价**，分歧只出现在「坐标恰好落在格子边界上」的点
   （坐标是半个格边长的整数倍，如 cell=0.001 时的 116.4095）：
     - SQL：round(116.4095/0.001) —— double 除法得 116409.49999999999 → 判给**下面**那格；
     - ST_SnapToGrid：内部按边界精确值取整（.5 取偶）→ 判给**上面**那格。
   影响：cell=0.002 时全库有 7 个这样的点，它们的**归属**变了（但落到的邻格本来就有
   别的点，所以"格子集合"不变；有 14 个格子的**点数**因此不同）；
   cell=0.001 时 25 个点、格子集合 +1（8427 → 8428）；
   cell=0.0005 时 146 个点、格子集合 +2。
   也就是说：**格子集合级等价在参照档 0.002 成立，在更细的档不成立。**
   这是必须在报告里讲清的事实，不是脚本 bug。

B~G. 接口形状 / 独立实现逐格对拍 / 口径 / 时段 / 边界与上限 / 估算上界。

用法（密码由调用方放进环境变量，脚本自己不读、也不打印密码）：
    $yaml = Get-Content backend/src/main/resources/application-local.yml -Raw
    if ($yaml -match '(?m)^\s*password:\s*(\S+)') { $env:PGPASSWORD = $Matches[1] }
    $env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
    & "E:\python\python_address\python.exe" .tmp\verify-density-api.py
"""
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request

# 控制台编码兜底：中文报错信息不能把脚本自己搞崩（不依赖调用方设对环境变量）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://localhost:8080"
BBOX = "116.26,39.86,116.42,40.04"      # 参照视野（北京 GeoLife 主城区）
CELL = 0.002                            # 参照格边长（度）
PSQL = r"E:\PostgreSQL\bin\psql.exe"

# 等价性验证要跑的格边长。既包含阶梯里的档（0.002 / 0.001 / 0.0005），
# 也包含一个更粗的档（0.01）——粗档更容易暴露"取整方向"类的差异。
EQ_CELLS = (0.01, 0.002, 0.001, 0.0005)

W, S, E, N = (float(x) for x in BBOX.split(","))

fails = []
STAT = {"n": 0}


def check(name, ok, detail=""):
    """打一行结果，并累计检查项数、记住失败项。"""
    STAT["n"] += 1
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def get(path):
    """打接口，返回解析后的 JSON。"""
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def psql(sql):
    r"""跑一条 SQL 并返回结果（-t -A：不要表头、不要对齐，多列用 | 分隔）。

    刻意检查 returncode：
    如果 psql 连接失败/写错 SQL 而返回空串，下面所有"两边相等"的断言
    会变成 "" == "" 的**假绿** —— 这是对拍脚本最容易骗自己的地方。
    """
    out = subprocess.run(
        [PSQL, "-U", "postgres", "-h", "localhost", "-p", "5432", "-d", "calcite",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if out.returncode != 0:
        raise RuntimeError("psql failed (exit %s): %s" % (out.returncode, (out.stderr or "").strip()))
    txt = (out.stdout or "").strip()
    if txt == "":
        raise RuntimeError("psql returned empty output for: %s" % " ".join(sql.split())[:160])
    return txt


def tie_diagnostics(cell, where=""):
    """诊断（**不是**断言）：两种写法到底差在哪。

    回答三个问题：
      diff_points —— 有多少个点被两种写法分进了**不同的格子**；
      tie_points  —— 其中有多少个点"坐标恰好落在格子边界上"
                     （坐标 ×(1/cell) 的小数部分 = 0.5，例如 cell=0.001 时的 116.4095）；
      count_diff_cells —— 有多少个格子的**点数**不同（即使格子集合相同，
                     边界点的归属变化也会让点数不同）。

    有这组数字，"等价性"就不是一句"通过了/没通过"，而是能说清边界在哪。
    """
    cond = (
        "(round(ST_X(geom)/%s)::int, round(ST_Y(geom)/%s)::int) IS DISTINCT FROM "
        "(round(ST_X(ST_SnapToGrid(geom,%s))/%s)::int, "
        "round(ST_Y(ST_SnapToGrid(geom,%s))/%s)::int)"
        % (cell, cell, cell, cell, cell, cell))
    w = (" WHERE " + where + " AND " + cond) if where else (" WHERE " + cond)
    inv = 1.0 / cell
    sql = (
        "SELECT count(*), "
        # PostGIS 没有 mod(float8,float8)，所以用 x - floor(x) 取小数部分
        "count(*) FILTER (WHERE abs((ST_X(geom)*%r::float8 - floor(ST_X(geom)*%r::float8)) - 0.5) < 1e-6 "
        "OR abs((ST_Y(geom)*%r::float8 - floor(ST_Y(geom)*%r::float8)) - 0.5) < 1e-6), "
        "coalesce(min(id), 0) FROM track_point%s;"
        % (inv, inv, inv, inv, w))
    n_diff, n_tie, sample = (int(x) for x in psql(sql).split("|"))

    src = "FROM track_point" + (" WHERE " + where if where else "")
    sql2 = (
        "WITH a AS (SELECT round(ST_X(geom)/%s)::int nx, round(ST_Y(geom)/%s)::int ny, count(*) p "
        "%s GROUP BY 1,2), "
        "b AS (SELECT round(ST_X(ST_SnapToGrid(geom,%s))/%s)::int nx, "
        "round(ST_Y(ST_SnapToGrid(geom,%s))/%s)::int ny, count(*) p %s GROUP BY 1,2) "
        "SELECT count(*) FROM a FULL JOIN b USING (nx,ny) WHERE a.p IS DISTINCT FROM b.p;"
        % (cell, cell, src, cell, cell, cell, cell, src))
    n_count_diff = int(psql(sql2))
    return {"diff_points": n_diff, "tie_points": n_tie, "sample_id": sample,
            "count_diff_cells": n_count_diff}


def equivalence(cell, where=""):
    """比较 round 写法与 ST_SnapToGrid 写法的格子集合。

    返回 (round 格子数, snap 格子数, 只在 round 里的格子数, 只在 snap 里的格子数)。

    为什么要把两边都"投影成整数网格索引"再比：
    ST_SnapToGrid 的格子身份就是它吐出来的那个点；而"点落在哪一格"=
    (round(x/cell), round(y/cell)) 这对整数，且这个映射在每个格子内是单射，
    所以【整数索引对集合相同】等价于【snapped 点集合相同】。
    直接比 ST_AsText 会因浮点打印尾数（0.002 无法用二进制精确表示）产生假红。
    """
    src = "FROM track_point" + (" WHERE " + where if where else "")
    sql = (
        "WITH a AS (SELECT round(ST_X(geom)/%s)::int nx, round(ST_Y(geom)/%s)::int ny %s GROUP BY 1,2), "
        "b AS (SELECT round(ST_X(ST_SnapToGrid(geom,%s))/%s)::int nx, "
        "round(ST_Y(ST_SnapToGrid(geom,%s))/%s)::int ny %s GROUP BY 1,2) "
        "SELECT (SELECT count(*) FROM a), (SELECT count(*) FROM b), "
        "(SELECT count(*) FROM (SELECT * FROM a EXCEPT SELECT * FROM b) x), "
        "(SELECT count(*) FROM (SELECT * FROM b EXCEPT SELECT * FROM a) y);"
        % (cell, cell, src, cell, cell, cell, cell, src)
    )
    parts = psql(sql).split("|")
    return tuple(int(p) for p in parts)


def independent_cells(hour_from=None, hour_to=None):
    """独立实现一遍网格聚合：直接问数据库，但**不走**后端那套参数管线。

    对拍的关键是"另一条实现路径"，所以北京时间的表达刻意换一种写法：
        后端 SQL： extract(hour FROM recorded_at AT TIME ZONE 'Asia/Shanghai')
        本脚本  ： extract(hour FROM (recorded_at AT TIME ZONE 'UTC') + interval '8 hours')
    recorded_at 是 timestamptz（库里存 UTC）；Asia/Shanghai 全年 UTC+8、无夏令时，
    两条表达式应完全等价，但走的是不同代码路径 —— 这样才验得出"时区到底生效没有"。

    返回 {(格子中心经度, 格子中心纬度): (点数, 轨迹数)}。
    """
    where = ["geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)" % (W, S, E, N)]
    if hour_from is not None:
        where.append(
            "extract(hour FROM (recorded_at AT TIME ZONE 'UTC') + interval '8 hours') "
            "BETWEEN %d AND %d" % (hour_from, hour_to))
    sql = (
        "SELECT round(ST_X(geom)/%s)::int AS nx, round(ST_Y(geom)/%s)::int AS ny, "
        "count(*) AS pts, count(DISTINCT track_id) AS trks "
        "FROM track_point WHERE %s GROUP BY 1,2"
        % (CELL, CELL, " AND ".join(where))
    )
    raw = psql("SELECT json_agg(row_to_json(t)) FROM (%s) t;" % sql)
    rows = json.loads(raw) if raw and raw != "" else []
    if rows is None:
        rows = []
    out = {}
    for row in rows:
        # 和 DensityGrid.indexToLon/ indexToLat 一致：格子中心 = 索引 × 格边长
        out[(round(row["nx"] * CELL, 9), round(row["ny"] * CELL, 9))] = (row["pts"], row["trks"])
    return out


def api_cells(payload):
    """把接口返回的 cells 压成同样的 {(lon,lat): (points,tracks)} 方便逐格比。"""
    return {(round(c["lon"], 9), round(c["lat"], 9)): (c["points"], c["tracks"])
            for c in payload["cells"]}


def diff_report(api, mine):
    """返回 (只在接口里, 只在独立实现里, 数值不一致的格子列表) —— 报告要能指出具体格子。"""
    only_api = sorted(set(api) - set(mine))
    only_mine = sorted(set(mine) - set(api))
    bad = sorted((k, api[k], mine[k]) for k in set(api) & set(mine) if api[k] != mine[k])
    return only_api, only_mine, bad


def main():
    if not os.environ.get("PGPASSWORD"):
        print("PGPASSWORD 未设置 —— 先把 application-local.yml 里的密码放进环境变量再跑。")
        sys.exit(2)
    if not os.path.exists(PSQL):
        print("找不到 psql: %s" % PSQL)
        sys.exit(2)

    # ---- A. 等价性验证（本脚本最重要的一条）----
    # 防的是：将来谁把 round 写法改回/改成别的形式，格子错位却没人发现。
    print("=== A. round(ST_X/cell) 与 ST_SnapToGrid(geom, cell) 等价性 ===")
    scopes = [
        ("all-data", ""),
        ("ref-bbox", "geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)" % (W, S, E, N)),
    ]
    for label, where in scopes:
        for cell in EQ_CELLS:
            n_round, n_snap, only_round, only_snap = equivalence(cell, where)
            d = tie_diagnostics(cell, where)

            # ── 断言 1：所有"归属不同"的点，必须【恰好落在格子边界上】 ──
            # 这是两种写法唯一的真实分歧来源。实测 8 组全部满足（diff == tie）。
            # 换句话说：只要一个点不在边界上，两种写法给它分的格子就完全一样。
            check("[%s] cell=%s 归属不同的点全都是格子边界点" % (label, cell),
                  d["diff_points"] == d["tie_points"],
                  "%d 个点换了格子，其中恰好 %d 个在边界上"
                  % (d["diff_points"], d["tie_points"]))

            # ── 断言 2：round 的格子集合必须是 snap 的子集 ──
            # 即：round 只会"少"格子（边界点被并进邻格），不会凭空多出格子。
            check("[%s] cell=%s round 的格子是 snap 的子集" % (label, cell),
                  only_round == 0, "only-in-round=%d" % only_round)

            # ── 断言 3：差集必须极小（边界点最多只挪动一两个格子） ──
            # 注意这里【不能】要求严格相等：0.001 / 0.0005 档确实会差 1~2 个格子，
            # 原因是浮点除法在边界半格上的精度（116.4095/0.001 = 116409.49999999999）。
            check("[%s] cell=%s snap 比 round 最多多 2 个格子" % (label, cell),
                  only_snap <= 2, "only-in-snap=%d" % only_snap)

            # ── 断言 4：实际启用的默认档 0.002 上必须【严格相同】 ──
            # 这条最要紧：用户实际看到的就是这一档（前端挑档后落在 0.002 附近）。
            if abs(cell - 0.002) < 1e-12:
                check("[%s] cell=0.002 默认档：两种写法严格相同" % label,
                      only_round == 0 and only_snap == 0 and n_round == n_snap,
                      "snap=%d round=%d only-in-round=%d only-in-snap=%d"
                      % (n_snap, n_round, only_round, only_snap))

            # 诊断（不是断言）：把"点数因此不同的格子数"打出来，方便看边界点的影响面
            if d["diff_points"] or d["count_diff_cells"] or n_round != n_snap:
                print("  info: [%s] cell=%s round=%d snap=%d；%d 个边界点换了格子（例 id=%d），"
                      "%d 个格子的点数因此差 1"
                      % (label, cell, n_round, n_snap, d["diff_points"],
                         d["sample_id"], d["count_diff_cells"]))

    # ---- B. 接口基本形状 ----
    print("\n=== B. 接口基本形状 ===")
    r = get("/api/analysis/density?bbox=%s&cellSize=%s" % (BBOX, CELL))
    print("  info: cells=%d points=%d maxTracks=%d" %
          (len(r["cells"]), r["scanned"]["points"], r["scanned"]["maxTracks"]))
    check("cellSize 回显正确", abs(r["cellSize"] - CELL) < 1e-12, str(r["cellSize"]))
    check("bbox 回显正确", r["bbox"] == [W, S, E, N], str(r["bbox"]))
    check("默认 metric=tracks", r["metric"] == "tracks", r["metric"])
    check("cells 非空", len(r["cells"]) > 0, str(len(r["cells"])))
    # 下面三条是"接口自洽"：scanned 是后端自己数的，必须和 cells 加总对得上
    check("scanned.cells == len(cells)", r["scanned"]["cells"] == len(r["cells"]),
          "%d vs %d" % (r["scanned"]["cells"], len(r["cells"])))
    check("scanned.points == sum(cells.points)",
          r["scanned"]["points"] == sum(c["points"] for c in r["cells"]),
          "%d vs %d" % (r["scanned"]["points"], sum(c["points"] for c in r["cells"])))
    check("scanned.maxTracks == max(cells.tracks)",
          r["scanned"]["maxTracks"] == max(c["tracks"] for c in r["cells"]),
          "%d vs %d" % (r["scanned"]["maxTracks"], max(c["tracks"] for c in r["cells"])))

    # ---- C. 与独立实现逐个格子对拍（metric=tracks）----
    print("\n=== C. 与独立实现对拍（metric=tracks）===")
    mine = independent_cells()
    api = api_cells(r)
    only_api, only_mine, bad = diff_report(api, mine)
    check("格子数一致", len(api) == len(mine), "API=%d independent=%d" % (len(api), len(mine)))
    check("格子集合完全相同", not only_api and not only_mine,
          "only-in-API=%d only-in-independent=%d" % (len(only_api), len(only_mine)))
    check("每格的 (点数, 轨迹数) 完全相同", not bad,
          "mismatched=%d" % len(bad) + ("" if not bad else "  e.g. %s" % (bad[0],)))
    if only_api or only_mine:
        print("  info: only-in-API=%s only-in-independent=%s" % (only_api[:5], only_mine[:5]))

    # ---- D. 两个口径都在，且 value 跟着 metric 走 ----
    print("\n=== D. 口径 ===")
    p = get("/api/analysis/density?bbox=%s&cellSize=%s&metric=points" % (BBOX, CELL))
    check("metric=points 时 value 等于 points",
          all(c["value"] == c["points"] for c in p["cells"]))
    check("切口径不改变 points/tracks 两个原始值", api_cells(p) == api)
    check("metric=points 时接口回显 metric", p["metric"] == "points", p["metric"])

    # ---- E. 时段筛选（独立实现 + 关系比较）----
    print("\n=== E. 时段筛选（北京时间 7-9 点）===")
    m = get("/api/analysis/density?bbox=%s&cellSize=%s&hourFrom=7&hourTo=9" % (BBOX, CELL))
    print("  info: morning cells=%d points=%d / all-day cells=%d points=%d" %
          (len(m["cells"]), m["scanned"]["points"], len(r["cells"]), r["scanned"]["points"]))
    check("早高峰的点数少于全天",
          m["scanned"]["points"] < r["scanned"]["points"],
          "morning=%d all-day=%d" % (m["scanned"]["points"], r["scanned"]["points"]))
    check("早高峰的格子数少于全天", len(m["cells"]) < len(r["cells"]),
          "morning=%d all-day=%d" % (len(m["cells"]), len(r["cells"])))
    check("params 回显了时段",
          m["params"]["hourFrom"] == 7 and m["params"]["hourTo"] == 9, str(m["params"]))
    # 这一条防的是"时区没真的生效"：如果 SQL 忘了 AT TIME ZONE，
    # 拿到的其实是 UTC 的 7-9 点（= 北京 15-17 点），和独立实现（+8 小时写法）就对不上。
    m_api = api_cells(m)
    m_mine = independent_cells(7, 9)
    m_only_api, m_only_mine, m_bad = diff_report(m_api, m_mine)
    check("7-9 点时段：格子集合与独立实现相同",
          not m_only_api and not m_only_mine,
          "only-in-API=%d only-in-independent=%d" % (len(m_only_api), len(m_only_mine)))
    check("7-9 点时段：每格数值与独立实现相同", not m_bad,
          "mismatched=%d" % len(m_bad) + ("" if not m_bad else "  e.g. %s" % (m_bad[0],)))

    # ---- F. 边界与上限 ----
    print("\n=== F. 边界与上限 ===")
    empty = get("/api/analysis/density?bbox=0,0,0.1,0.1&cellSize=0.002")
    check("没数据的视野 → 200 + 空数组", empty["cells"] == [], str(empty["cells"]))

    for name, url in [
        ("全球 bbox + 最细格 → 400", "/api/analysis/density?bbox=-180,-90,180,90&cellSize=0.0001"),
        ("非法格边长 → 400", "/api/analysis/density?bbox=%s&cellSize=0.003" % BBOX),
        ("bbox 西南>=东北 → 400", "/api/analysis/density?bbox=116.4,40,116.2,39.9&cellSize=0.002"),
        ("时段倒过来 → 400",
         "/api/analysis/density?bbox=%s&cellSize=%s&hourFrom=9&hourTo=7" % (BBOX, CELL)),
        ("metric 非法 → 400",
         "/api/analysis/density?bbox=%s&cellSize=%s&metric=count" % (BBOX, CELL)),
    ]:
        try:
            get(url)
            check(name, False, "returned 200 unexpectedly")
        except urllib.error.HTTPError as ex:
            check(name, ex.code == 400, "HTTP %d" % ex.code)

    # ---- G. 估算值是上界（所以接口不需要 LIMIT/truncated 字段）----
    # 防的是：将来有人把 estimateCells 从 ceil 改成 floor/round，上界性质被破坏，
    # 于是"超大视野"能绕过 max-cells 检查打死数据库。
    print("\n=== G. 估算值确实是上界 ===")
    est = math.ceil((E - W) / CELL) * math.ceil((N - S) / CELL)
    check("实际格子数 <= 估算上界", len(r["cells"]) <= est,
          "actual=%d upper-bound=%d" % (len(r["cells"]), est))

    print("\nchecks run: %d, failed: %d" % (STAT["n"], len(fails)))
    if fails:
        print("FAILED: " + "; ".join(fails))
        sys.exit(1)
    print("全部通过")


main()
