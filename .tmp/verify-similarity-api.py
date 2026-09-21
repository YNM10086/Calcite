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
from datetime import date

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
    # ⚠️ 配对**当场从接口取**，不写死 trackId。
    # 旧版写死了 track 39，而 39 后来被"数据编辑"功能删掉了 —— 于是 `sa` 和 `sb`
    # 双双是 None、`None == None` 为真，**对称性这一项直接假绿**；
    # 紧接着的 `if sa is not None` 又让第二项整段静默跳过。
    # 写死具体轨迹 id 和写死条数是同一类错误：把"某一次的数据"当判据。
    # 现在改成：从主线自己的结果里取前两名当对拍对象（必然存在、必然非零），
    # 而且加"取不到就判红"的护栏 —— 不是取不到就跳过。
    for a in (20, 6):
        ra = get(f"/api/analysis/similarity?trackId={a}&limit=500")
        pairs = [m["trackId"] for m in ra["matches"][:2]]
        check(f"主线 {a} 至少有 2 个非零匹配（对称性才有对象可比）",
              len(pairs) == 2, f"matches={len(ra['matches'])} 前两名={pairs}")
        for b in pairs:
            ma = next(m for m in ra["matches"] if m["trackId"] == b)
            rb = get(f"/api/analysis/similarity?trackId={b}&limit=500")
            mb = next((m for m in rb["matches"] if m["trackId"] == a), None)
            check(f"similarity({a},{b}) == similarity({b},{a})",
                  mb is not None and ma["similarity"] == mb["similarity"],
                  f"{ma['similarity']} vs {None if mb is None else mb['similarity']}")
            check(f"fwd({a},{b}) == rev({b},{a})",
                  mb is not None and ma["forwardPct"] == mb["reversePct"],
                  f"{ma['forwardPct']} vs {None if mb is None else mb['reversePct']}")

    # ================= B. 「被包含」不能被误判 =================
    print("\n=== B. 被包含的一小段（设计文档 2.3 节的坑）===")
    r6 = get("/api/analysis/similarity?trackId=6&limit=500")
    m18 = next((m for m in r6["matches"] if m["trackId"] == 18), None)
    # 先独立算【点到折线】的真值 —— "被包含"这件事要用真值来证明
    line_truth = psql_json(f"""
        SELECT json_agg(row_to_json(t)) FROM (
          SELECT round(100.0 * count(*) FILTER (
                   WHERE ST_DWithin(p.geom::geography, t18.geom::geography, {TOL}))
                 / count(*), 1) AS pct
          FROM track_point p, track t18
          WHERE p.track_id = 6 AND t18.id = 18) t;""")[0]["pct"]
    check("track 6 的点【全部】落在 track 18 的折线上（所以它确实是被包含）",
          line_truth >= 99.0, f"点到折线真值={line_truth}%")
    if m18 is None:
        print("  info: track 18 没出现在 track 6 的结果里（说明被正确过滤了）")
    else:
        # ⚠️ 这里【不能】断言 m18["forwardPct"] >= 99 ——
        # 接口用的是【点对点】，track 18 采样间距 42 米，会把它低估成 43%。
        # 那是已知且刻意的取舍（见设计文档 2.6/2.7 节），不是 bug。
        # 要断言的是：**双向相似度**被压到 50% 以下（"取小"生效）。
        check("track 6 vs 18 的双向相似度必须 < 50%（取小把'被包含'压下去了）",
              m18["similarity"] < 50.0, f"similarity={m18['similarity']}")
        check("（已知限制）接口的 forwardPct 被点对点低估",
              m18["forwardPct"] < line_truth - 20,
              f"真值 {line_truth}% vs 接口 {m18['forwardPct']}% —— 差异是预期的")
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
    #
    # ⚠️ 这里【必须】用一组真实存在的轨迹对 —— 曾经写死成 (20,39)，而 39 后来被
    #    "数据编辑"功能删掉了（它的数据现在是 249），于是 SQL 里 count(*) 为 0 → **除以零**。
    #    改成 PairsRef：既保留"跨采样密度"这个设计意图，又不会因为 id 变动而炸。
    PAIRS = [(20, 249), (6, 18), (20, 35), (6, 16), (6, 24)]
    # 逐个确认两端都还有点 —— 少了谁就明说，不要静默跳过（静默跳过 = 覆盖归零）
    for a, b in PAIRS:
        na = psql_json(f"SELECT json_agg(row_to_json(t)) FROM ("
                       f"SELECT count(*) AS n FROM track_point WHERE track_id = {a}) t;")[0]["n"]
        nb = psql_json(f"SELECT json_agg(row_to_json(t)) FROM ("
                       f"SELECT count(*) AS n FROM track_point WHERE track_id = {b}) t;")[0]["n"]
        check(f"对拍用的一对 ({a},{b}) 两端都还有点", na > 0 and nb > 0,
              f"track {a} 有 {na} 点、track {b} 有 {nb} 点")
    for a, b in PAIRS:
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
    # ⚠️ 原来写死的是「compared 必须大于一个人为挑的地板值」（当时有近 200 条候选，
    # 就随手拿 50 当了地板）。那种判据既说明不了问题，数据一变又照样红。
    # 换成**同样强、而且与数据量无关**的三条：
    #   ① compared 就是"全量候选数" —— 完整 matches 的条数必须等于它（limit 没参与它的计算）
    #   ② 它不可能超过"除主线以外的轨迹总数"（物理上界）
    #   ③ 换 limit=3 时它一个字都不许变，而 matches 恰好被截到 3 条（下一项）
    total_tracks = get("/api/tracks?limit=1")["total"]
    check("compared 是分母（= 全量候选数），且不超过「其它轨迹」的总数",
          len(r["matches"]) == min(r["compared"], 500)
          and 1 <= r["compared"] <= total_tracks - 1,
          f'compared={r["compared"]} / 返回 matches={len(r["matches"])}（查询上限 500）'
          f' / 库内轨迹总数={total_tracks}')
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
    top50 = r["matches"][0]                     # 50 米下的第一名（接口已按相似度降序）
    top200 = next((m for m in wide["matches"] if m["trackId"] == top50["trackId"]), None)
    # ⚠️ 这里原来写死了 track 39，而 39 已被删除 → 两个 `next(..., 0)` 都拿到 0 →
    # `0 >= 0` 恒真，这条判据**形同虚设**。现在拿"50 米下的第一名"去 200 米的结果里找它，
    # **找不到就判红**（容差变大反而丢掉一个相似轨迹，那才是真的回归）。
    check("容差变大后原先的第一名相似度不会下降",
          top200 is not None and top200["similarity"] >= top50["similarity"],
          f'track {top50["trackId"]}：50m={top50["similarity"]} '
          f'200m={None if top200 is None else top200["similarity"]}')

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

    # 没有邻居 → 200 + 空数组（Review Focus 第 1 条）
    # ⚠️ 三个坑都踩过：
    #   ① /api/tracks 返回的是 {total, items}，不是 {tracks} —— 键名写错会让这一项
    #      **静默跳过**（输出看着像无害的 info，实际覆盖为 0）。
    #   ② 不能断言"GPX 轨迹必然孤立" —— 3 条 GPX 是同一场地跑的，它们**互相之间是相似的**。
    #   ③ 实测容差 50 米下**每一条都至少有 1 个邻居**，把容差压到 1 米才有个别孤立的。
    #      所以断言要写成"扫描几条、至少有一条返回空数组"，而不是指定某一条。
    # ⚠️ 顺带把 limit 也改成从总数算：旧版写死 `limit=200`，而库里有近 250 条时
    #    它只会看到前 200 条 —— **静默**少看，正是上面第 ① 条警告的那类坑。
    listing = get(f"/api/tracks?limit={min(total_tracks, 500)}")
    items = listing.get("items", [])
    check("能取到轨迹列表（键名必须是 items），且看到的就是全库",
          len(items) > 0 and len(items) == min(total_tracks, 500),
          f"拿到 {len(items)} 条（total={listing.get('total')}）")
    probe = items[:6]
    empty_n, ok_n = 0, 0
    for t in probe:
        try:
            g = get(f"/api/analysis/similarity?trackId={t['id']}&toleranceM=1")
        except urllib.error.HTTPError as ex:
            print(f"    info: trackId={t['id']} 返回 HTTP {ex.code}")
            continue
        ok_n += 1
        if g["matches"] == []:
            empty_n += 1
    check("苛刻容差下没有一条报错（不是 500）", ok_n == len(probe),
          f"{ok_n}/{len(probe)} 条正常返回")
    check("至少有一条返回空数组（'没有邻居'是正常结果，不是错误）", empty_n >= 1,
          f"{empty_n}/{ok_n} 条为空")
    # 防"假绿"：同一个接口在正常容差下必须能给出结果 ——
    # 否则上面那个"空数组"断言可能被一个永远返回空的 bug 骗过
    if items:
        g2 = get(f"/api/analysis/similarity?trackId={items[0]['id']}&toleranceM=50")
        check("同一接口在正常容差下不是永远返回空", g2["compared"] > 0,
              f"trackId={items[0]['id']} compared={g2['compared']}")
    # ================= H. daysAway =================
    print("\n=== H. daysAway ===")
    # ⚠️ 原来写死"track 20 vs 39 相差 19 天"，而 track 39 已被删除 →
    # `next(..., None)` 拿到 None → **整个 H 段被静默跳过**（正是 G 段警告过的那类坑：
    # 输出看着像没事，其实这一段一个判据都没跑）。
    # 现在改成**独立重算**：daysAway 的定义就是"两条轨迹的 startTime 按 UTC 日期相差几天"
    # （`SimilarityMath.daysBetween` = `|DAYS.between(a.toLocalDate(), b.toLocalDate())|`），
    # 于是对返回的**每一条**匹配都重算一遍再比对 —— 比原来那一条数据指纹强得多，且与数据无关。
    base = next((it for it in items if it["id"] == 20), None)
    check("能从列表接口取到主线 20 的 startTime（独立重算的前提）",
          base is not None and bool(base.get("startTime")),
          f'startTime={None if base is None else base.get("startTime")}')
    bad_days, bad_iso = 0, 0
    for m in r["matches"]:
        if not (m["startTime"] or "").endswith("Z"):
            bad_iso += 1
            continue
        if base is not None and base.get("startTime"):
            want = abs((date.fromisoformat(m["startTime"][:10])
                        - date.fromisoformat(base["startTime"][:10])).days)
            if m["daysAway"] != want:
                bad_days += 1
                print(f"    info: track {m['trackId']} daysAway={m['daysAway']} 重算={want}"
                      f'（{base["startTime"][:10]} vs {m["startTime"][:10]}）')
    check("每条匹配的 daysAway 都等于独立重算的 UTC 日期差",
          base is not None and len(r["matches"]) > 0 and bad_days == 0,
          f"{len(r['matches'])} 条里 {bad_days} 条对不上")
    check("所有 startTime 都是 ISO-8601 UTC（以 Z 结尾）",
          len(r["matches"]) > 0 and bad_iso == 0, f"{bad_iso} 条格式不对")

    print(f"\n{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


main()
