# -*- coding: utf-8 -*-
r"""轨迹相似度的独立对拍。

Java 单测只覆盖数学与参数校验，覆盖不到 SQL。这个脚本用独立实现核对，
并做三条只有对拍能做的专项验证：
  ① 对称性 —— similarity(A,B) 必须等于 similarity(B,A)
  ② 「被包含」不能被误判（设计文档 2.3 节实测到的坑）
  ③ 点对点近似 vs 点到折线 —— 把设计取舍【量化】成具体数字

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\verify-similarity-api.py
"""
import json
import math
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8080"
PSQL = r"E:\PostgreSQL\bin\psql.exe"
fails = []


def check(name, ok, detail=""):
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def psql_json(sql):
    """跑 SQL 并把结果当 JSON 拿回来（用 json_agg 包裹）。"""
    out = subprocess.run(
        [PSQL, "-U", "postgres", "-h", "localhost", "-p", "5432",
         "-d", "calcite", "-t", "-A", "-c", sql],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError("psql 失败: " + (out.stderr or "")[:300])
    txt = (out.stdout or "").strip()
    return json.loads(txt) if txt else []


def hav(lat1, lon1, lat2, lon2):
    """和项目里 GeoUtils 一致的 haversine（米）。"""
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def points_of(track_id):
    """取一条轨迹的全部点（lat, lon），按 seq 排序。"""
    rows = psql_json(
        "SELECT json_agg(row_to_json(t)) FROM ("
        "  SELECT seq, ST_Y(geom) AS lat, ST_X(geom) AS lon "
        f"  FROM track_point WHERE track_id = {track_id} ORDER BY seq) t;")
    return [(r["lat"], r["lon"]) for r in (rows or [])]


def overlap_pct(pts_a, pts_b, tol):
    """独立实现：pts_a 里有多少个点落在 pts_b 的某个点 tol 米内（百分比）。"""
    if not pts_a:
        return 0.0
    hit = 0
    for la, lo in pts_a:
        for lb, lob in pts_b:
            if hav(la, lo, lb, lob) <= tol:
                hit += 1
                break
    return 100.0 * hit / len(pts_a)


def main():
    TOL = 50.0

    # ================= A. 对称性（Review Focus 第 4 条）=================
    print("=== A. 对称性 ===")
    for a, b in [(20, 39), (6, 18), (20, 35)]:
        ra = get(f"/api/analysis/similarity?trackId={a}&limit=500")
        rb = get(f"/api/analysis/similarity?trackId={b}&limit=500")
        sa = next((m["similarity"] for m in ra["matches"] if m["trackId"] == b), None)
        sb = next((m["similarity"] for m in rb["matches"] if m["trackId"] == a), None)
        check(f"similarity({a},{b}) == similarity({b},{a})", sa == sb,
              f"{sa} vs {sb}")
        if sa is not None:
            fa = next(m["forwardPct"] for m in ra["matches"] if m["trackId"] == b)
            rbv = next(m["reversePct"] for m in rb["matches"] if m["trackId"] == a)
            check(f"fwd({a},{b}) == rev({b},{a})", fa == rbv, f"{fa} vs {rbv}")

    # ================= B. 「被包含」不能被误判 =================
    print("\n=== B. 被包含的一小段（设计文档 2.3 节的坑）===")
    r6 = get("/api/analysis/similarity?trackId=6&limit=500")
    m18 = next((m for m in r6["matches"] if m["trackId"] == 18), None)
    if m18 is None:
        print("  info: track 18 没出现在 track 6 的结果里（说明被正确过滤了）")
    else:
        check("track 6 vs 18 的单向重合度接近 100%", m18["forwardPct"] >= 99.0,
              f"fwd={m18['forwardPct']}")
        check("track 6 vs 18 的双向相似度必须 < 50%（取小生效）",
              m18["similarity"] < 50.0, f"similarity={m18['similarity']}")
    # 长度对比：证明这一对确实是"被包含"而不是"同一条路"
    lens = psql_json(
        "SELECT json_agg(row_to_json(t)) FROM ("
        "  SELECT id, round(ST_Length(geom::geography)::numeric) AS len_m "
        "  FROM track WHERE id IN (6,18)) t;")
    d = {r["id"]: r["len_m"] for r in lens}
    check("track 6 确实远短于 track 18（这才是被包含）",
          d.get(6, 0) * 3 < d.get(18, 1), f"6={d.get(6)}米 18={d.get(18)}米")

    # ================= C. 点对点近似 vs 点到折线（量化取舍）=================
    print("\n=== C. 相似度【取小】对近似是否稳健 ===")
    # ⚠️ 这里必须比【相似度】，不能比 forwardPct！
    #
    # 实测（设计文档 2.6/2.7 节）：track 6 的点对 track 18
    #   到【折线】：244/244 = 100%   到【采样点】：105/244 = 43%
    # 因为 track 18 的采样间距是 42 米，点对点会严重低估 fwd。
    #
    # 但相似度取的是 min(fwd, rev)，而被低估的方向【恰好是本来更大的那个】——
    # 所以相似度几乎不受影响（六组实测差 ≤ 0.6 个百分点）。
    # 断言必须打在这个性质上，不能打在 forwardPct 上（后者本来就对不上）。
    for a, b in [(20, 39), (6, 18), (20, 35), (6, 16), (6, 24)]:
        truth = psql_json(f"""
            SELECT json_agg(row_to_json(t)) FROM (
              SELECT least(
                (SELECT 100.0 * count(*) FILTER (
                          WHERE ST_DWithin(p.geom::geography, t2.geom::geography, {TOL}))
                        / count(*)
                 FROM track_point p JOIN track t2 ON t2.id = {b} WHERE p.track_id = {a}),
                (SELECT 100.0 * count(*) FILTER (
                          WHERE ST_DWithin(p.geom::geography, t1.geom::geography, {TOL}))
                        / count(*)
                 FROM track_point p JOIN track t1 ON t1.id = {a} WHERE p.track_id = {b})
              ) AS sim) t;""")[0]["sim"]
        api = get(f"/api/analysis/similarity?trackId={a}&limit=500")
        got = next((m["similarity"] for m in api["matches"] if m["trackId"] == b), 0.0)
        diff = abs(truth - got)
        check(f"({a},{b}) 相似度对近似稳健（取小救了我们）", diff <= 2.0,
              f"真值(点到折线)={round(truth,1)}% 接口(点对点)={got}% 差 {round(diff,1)} 个百分点")

    # 顺手把"近似确实很差"这件事也钉住 —— 免得将来有人以为点对点=点到折线
    fwd_line = psql_json(f"""
        SELECT json_agg(row_to_json(t)) FROM (
          SELECT round(100.0 * count(*) FILTER (
                   WHERE ST_DWithin(p.geom::geography, t2.geom::geography, {TOL}))
                 / count(*), 1) AS pct
          FROM track_point p JOIN track t2 ON t2.id = 18
          WHERE p.track_id = 6) t;""")[0]["pct"]
    api6 = get("/api/analysis/similarity?trackId=6&limit=500")
    m18 = next((m for m in api6["matches"] if m["trackId"] == 18), None)
    if m18 is not None:
        check("（已知限制）点对点的 forwardPct 确实远低于真值",
              fwd_line - m18["forwardPct"] > 20,
              f"真值 {fwd_line}% vs 点对点 {m18['forwardPct']}% —— 差异是预期的，不是 bug")

    # ================= D. 与独立实现对拍（逐条）=================
    print("\n=== D. 与独立实现对拍（trackId=20）===")
    r = get("/api/analysis/similarity?trackId=20&limit=500")
    bas = points_of(20)
    check("主线点数与接口一致", r["pointCount"] == len(bas),
          f"接口 {r['pointCount']} / 独立 {len(bas)}")
    mismatched = 0
    for m in r["matches"][:15]:
        other = points_of(m["trackId"])
        fwd = overlap_pct(bas, other, TOL)
        rev = overlap_pct(other, bas, TOL)
        sym = min(fwd, rev)
        if abs(round(fwd, 1) - m["forwardPct"]) > 0.6 or abs(round(sym, 1) - m["similarity"]) > 0.6:
            mismatched += 1
            print(f"    info: track {m['trackId']} 接口 fwd={m['forwardPct']} sym={m['similarity']}"
                  f" / 独立 fwd={round(fwd,1)} sym={round(sym,1)}")
    check("前 15 名逐条与独立实现一致（容差 0.6 个百分点）", mismatched == 0,
          f"不一致 {mismatched} 条")

    # ================= E. compared / limit / 排序 =================
    print("\n=== E. compared / limit / 排序 ===")
    check("compared 是分母，不受 limit 影响", r["compared"] > 50,
          f"compared={r['compared']}")
    small = get("/api/analysis/similarity?trackId=20&limit=3")
    check("limit=3 只截返回条数", len(small["matches"]) == 3 and small["compared"] == r["compared"],
          f"matches={len(small['matches'])} compared={small['compared']}")
    sims = [m["similarity"] for m in r["matches"]]
    check("matches 严格按相似度降序", sims == sorted(sims, reverse=True),
          f"前 5: {sims[:5]}")
    check("similarity == min(fwd, rev)", all(
        abs(m["similarity"] - min(m["forwardPct"], m["reversePct"])) < 1e-9
        for m in r["matches"]))

    # ================= F. 容差真的生效 =================
    print("\n=== F. 容差参数 ===")
    wide = get("/api/analysis/similarity?trackId=20&toleranceM=200&limit=500")
    check("容差 200 米时 compared 不少于 50 米的",
          wide["compared"] >= r["compared"], f"200m={wide['compared']} 50m={r['compared']}")
    top50 = next((m["similarity"] for m in r["matches"] if m["trackId"] == 39), 0)
    top200 = next((m["similarity"] for m in wide["matches"] if m["trackId"] == 39), 0)
    check("容差变大后第一名相似度不会下降", top200 >= top50, f"50m={top50} 200m={top200}")

    # ================= G. 边界与错误 =================
    print("\n=== G. 边界与错误 ===")
    for name, url, want in [
        ("容差 0 → 400", "/api/analysis/similarity?trackId=20&toleranceM=0", 400),
        ("容差 100000 → 400", "/api/analysis/similarity?trackId=20&toleranceM=100000", 400),
        ("limit 0 → 400", "/api/analysis/similarity?trackId=20&limit=0", 400),
        ("不存在的轨迹 → 404", "/api/analysis/similarity?trackId=999999", 404),
        ("缺 trackId → 400", "/api/analysis/similarity", 400),
    ]:
        try:
            get(url)
            check(name, False, "居然返回了 200")
        except urllib.error.HTTPError as ex:
            check(name, ex.code == want, f"HTTP {ex.code}（期望 {want}）")

    # 主线孤立无邻居 → 200 + 空数组（Review Focus 第 1 条）
    gpx = get("/api/tracks?limit=1&source=gpx")
    if gpx.get("tracks"):
        gid = gpx["tracks"][0]["id"]
        g = get(f"/api/analysis/similarity?trackId={gid}")
        check("福建的 GPX 轨迹 → 200 + 空匹配（不是错误）",
              g["matches"] == [], f"compared={g['compared']} matches={len(g['matches'])}")
    else:
        print("  info: 没找到 gpx 轨迹，跳过这一条")

    # ================= H. daysAway =================
    print("\n=== H. daysAway ===")
    m39 = next((m for m in r["matches"] if m["trackId"] == 39), None)
    if m39:
        check("track 20 vs 39 相差 19 天", m39["daysAway"] == 19, str(m39["daysAway"]))
        check("startTime 是 ISO-8601 UTC", m39["startTime"].endswith("Z"), m39["startTime"])

    print(f"\n{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


main()
