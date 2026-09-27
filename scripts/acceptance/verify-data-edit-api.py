# -*- coding: utf-8 -*-
r"""数据管理的对拍：改名 / 删除 / 新增导入 + 【缓存真的失效了没有】。

四条关键测试（只有这里能做，Java 单测覆盖不到）：

  ① 删掉相似度第一名后，主线 20 的 compared 必须少 1     → 证明 SimilarityCache 被清了
  ② 改名后，别的主线的匹配列表里必须显示新名字          → 证明"改名也要清缓存"
  ③ 删除前必须真的落盘了回收站文件                      → 证明 fail-safe 生效
  ④ 新增导入后，相似度必须反映新轨迹                    → 证明"新增也清了缓存"

⚠️ 这个脚本会**真的改动数据库**。每一步都做了现场恢复（改回原名 / 删掉自己刚导入的那条）。
   跑之前请确认 D:\Calcite-note\backups\ 里有当天的快照。

⚠️⚠️ 跑之前**必须**确认后端跑的是最新代码：JVM 的启动时间要**晚于**
   最后一次改动 `ImportService` / `TrackEditService` 的时间。
     Get-Process -Id (netstat -ano | Select-String ":8080\s.*LISTENING" | ...) | Select StartTime
     (Get-Item backend\target\classes\com\calcite\service\ImportService.class).LastWriteTime
   第一次跑对拍时踩到的坑：JVM 20:28:18 启动，而那句「新增也清相似度缓存」是
   20:31:05 才编译的 —— 于是 ④ 全红，看起来像"缓存没清"的**重大发现**，
   实际上是**在测旧代码**。这种假信号比不测还危险。

用法：
    $env:PYTHONIOENCODING='utf-8'; $env:LC_MESSAGES='C'
    & "E:\python\python_address\python.exe" .tmp\verify-data-edit-api.py

    # 回收站目录默认取 application.yml 里的 calcite.data.recycle-dir。
    # 如果后端是用 [--calcite.data.recycle-dir=...] 覆盖过的（沙箱里必须这么干，
    # 因为 DSH 起的进程一律写不了 D:\），就把同一个路径用环境变量告诉本脚本：
    $env:CALCITE_RECYCLE_DIR = "E:\...\Calcite\.tmp\recycle"

----------------------------------------------------------------------------
与计划原文（docs/superpowers/plans/2026-09-21-data-management.md Task 4）的差异，
以及每一处改动的理由 —— 都是为了让断言**真的会红**，不是放松断言：

1) 原文 ② 把改名对象写死成 track 3（「资料一」，在福建）。
   但主线 20 在**北京**，而相似度 SQL 用的是「点对点距离 ≤ 容差」的 INNER JOIN
   （见 TrackPointRepository.findSimilarityScores）—— 一条福建轨迹**根本进不了**
   主线 20 的候选名单。于是原文那段会走 `info: ... 跳过这条` 分支，
   **② 等于从没被测过**（绿的，但是假绿）。
   改法：**从主线 20 的匹配列表里挑一个**（第一名）当改名对象 —— 它按定义一定在名单里。
   改名后用同一个列表验证名字，这条检查就一定会红/绿分明。

2) ③ 的判据全部保留（文件数 +1 / 点数一致 / 带名字 / 带每个点的时间 / 文件名带名字和点数），
   只额外加了一条「times 里每一项都非空」——原文只数了长度，长度对但内容全是空串照样绿。

3) ④ 是新增的（原文只有三条）。新增轨迹必须有**至少一个点在主线 20 的 50 米容差内**，
   否则它连候选名单都进不去，`compared` 不会变 —— 那就分不清
   「缓存没清」和「新轨迹本来就无关」。
   所以**不能**拿 D:\Calcite-note\GPX-Data\ 下的 .gpx 样本（资料一~四在福建，
   离北京 1665 km）。改法：**复制 track 20 自己的原始 GeoLife .plt 文件**、
   改掉一个坐标数字（内容变 → SHA256 变 → 不会被当成重复），再上传。
   这样新轨迹的几何与 track 20 几乎完全相同，**必然**进候选名单。

4) 轨迹总数的判据从写死「某一次数据的 total - 1」改成「开工前实测的 total - 1」，
   并额外用「被删的两条 GET 详情都 404」交叉验证。
   这不是放松 —— 写死那个数字只是把数据量再抄一遍，换台库就假红/假绿。
"""
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://localhost:8080"
# 回收站目录 = backend/src/main/resources/application.yml 的 calcite.data.recycle-dir。
# 允许用环境变量覆盖，是为了适配"后端被 --calcite.data.recycle-dir=... 改过路径"的情形
# （DSH 沙箱里后端写不了 D:\，只能把回收站改到工作区内）。
RECYCLE = Path(os.environ.get("CALCITE_RECYCLE_DIR", r"D:\Calcite-note\backups\deleted"))
BACKUPS = Path(r"D:\Calcite-note\backups")
# GeoLife 原始数据（只读，绝不修改原文件）
GEOLIFE = Path(r"D:\Calcite-note\GPX-Data\Geolife Trajectories 1.3\Data")
TMP = Path(__file__).resolve().parent
# 主线：拿它当"别人"，验证删 / 改名 / 新增之后它看到的名单有没有跟着变
BASE_TRACK = 20
fails = []
notes = []


def check(name, ok, detail=""):
    print(("  [OK] " if ok else "  [XX] ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)
    return ok


def note(msg):
    print("  info: " + msg)
    notes.append(msg)


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))


def send(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode("utf-8", "replace")
        try:
            return ex.code, json.loads(raw)
        except Exception:
            return ex.code, {"raw": raw}


def upload(file_path, filename=None):
    r"""手工构造 multipart 上传。

    ⚠️ 不用 Invoke-RestMethod -Form：沙箱里它去开 D:\ 会被拒；
       而且这里要传的是已复制进 .tmp/ 的文件，本来就不该碰 D:\。
    """
    boundary = "----CalciteVerify" + "%08x" % random.getrandbits(32)
    name = filename or file_path.name
    parts = []
    parts.append(("--" + boundary + "\r\n").encode())
    parts.append(('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % name).encode("utf-8"))
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(file_path.read_bytes())
    parts.append(("\r\n--" + boundary + "\r\n").encode())
    parts.append(b'Content-Disposition: form-data; name="mode"\r\n\r\nappend\r\n')
    parts.append(("--" + boundary + "--\r\n").encode())
    body = b"".join(parts)
    req = urllib.request.Request(BASE + "/api/tracks/import", data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode("utf-8", "replace")
        try:
            return ex.code, json.loads(raw)
        except Exception:
            return ex.code, {"raw": raw}


def similarity(track_id, limit=500):
    return get(f"/api/analysis/similarity?trackId={track_id}&limit={limit}")


def sim_map(resp):
    return {m["trackId"]: m for m in resp["matches"]}


def track_ids(limit=500):
    return [t["id"] for t in get(f"/api/tracks?limit={limit}")["items"]]


def recycle_files():
    return sorted(RECYCLE.glob("*.geojson")) if RECYCLE.exists() else []


def geo_life_point_line(line):
    """判断一行是不是**真的轨迹点**（返回字段数组，否则 None）。

    判据与 GeoLifeImporter 完全一致：≥7 个字段 + 经纬度是数 + 第 6/7 字段能拼成时间戳。
    ⚠️ 只判"前两个字段是数"是不够的 —— 文件里那行头
    `0,2,255,My Track,0,0,2,8421376` 前两个字段正好是 0 和 2，会被当成坐标行。
    （第一次跑就踩了这个坑：改到了文件头，日志里打出"第 5 行纬度 0 → 0.000001"。）
    """
    f = line.split(",")
    if len(f) < 7:
        return None
    try:
        float(f[0]); float(f[1])
        datetime.strptime(f[5].strip() + "T" + f[6].strip(), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return f


def main():
    # ================= 0. 前置检查 =================
    print("=== 0. 前置检查 ===")
    health = get("/api/health")
    check("后端 UP", health.get("status") == "UP", str(health.get("status")))
    snaps = sorted(BACKUPS.glob("calcite-*.dump")) if BACKUPS.exists() else []
    check("全库快照在（最后的退路）", len(snaps) > 0,
          ", ".join(p.name for p in snaps) if snaps else "没找到 *.dump！")

    total_before = get("/api/tracks?limit=1")["total"]
    print(f"  回收站目录（本脚本读的）：{RECYCLE}")
    print(f"  开工前：轨迹总数 total={total_before}，回收站已有 {len(recycle_files())} 个 geojson")
    base_detail = get(f"/api/tracks/{BASE_TRACK}")
    print(f"  主线 {BASE_TRACK}「{base_detail['name']}」{base_detail['pointCount']} 点"
          f" source={base_detail['source']}")

    # ================= A. 改名的边界 =================
    print("\n=== A. 改名 + 边界 ===")
    vid = 3
    orig_name = get(f"/api/tracks/{vid}")["name"]
    stamp = "改名测试-唯一标记"

    st, _ = send("PATCH", f"/api/tracks/{vid}", {"name": stamp})
    check("改名返回 200", st == 200, f"HTTP {st}")
    check("改完详情里是新名字", get(f"/api/tracks/{vid}")["name"] == stamp)

    st, _ = send("PATCH", f"/api/tracks/{vid}", {"name": "   "})
    check("空名字 → 400", st == 400, f"HTTP {st}")
    st, _ = send("PATCH", f"/api/tracks/{vid}", {"name": "x" * 201})
    check("超长名字 → 400", st == 400, f"HTTP {st}")
    st, _ = send("PATCH", "/api/tracks/999999", {"name": "x"})
    check("改不存在的轨迹 → 404", st == 404, f"HTTP {st}")

    send("PATCH", f"/api/tracks/{vid}", {"name": orig_name})
    check("已改回原名（清理现场）", get(f"/api/tracks/{vid}")["name"] == orig_name)

    # ================= B. ⭐ 改名后相似度列表必须显示新名字 =================
    # 在防什么：SimilarityMatch 里带了 name。改名如果只更新 track 表、不清
    # SimilarityCache，别的主线的匹配列表会永远显示旧名字 —— 界面上看起来
    # "改名没生效"，但刷新一下又对了，最难查的那种 bug。
    print("\n=== B. ⭐ 改名也要清相似度缓存 ===")
    sim_b_before = similarity(BASE_TRACK)
    if not sim_b_before["matches"]:
        check("主线有匹配可测", False, f"主线 {BASE_TRACK} 的 matches 是空的，② 无法验证")
    else:
        # 从名单里挑，而不是写死 id —— 保证被改名的那条**确实在主线的候选名单里**
        target = sim_b_before["matches"][0]
        rid = target["trackId"]
        r_orig = target["name"]
        r_new = "改名对拍-" + "%06x" % random.getrandbits(24)
        print(f"  改名对象：主线 {BASE_TRACK} 的匹配第 1 名 track {rid}「{r_orig}」"
              f" sim={target['similarity']}（改名后它必须显示为「{r_new}」）")

        st, _ = send("PATCH", f"/api/tracks/{rid}", {"name": r_new})
        check(f"改名 track {rid} 返回 200", st == 200, f"HTTP {st}")

        sim_b_after = similarity(BASE_TRACK)
        got = sim_map(sim_b_after).get(rid, {}).get("name")
        check("改名后，别的主线的匹配列表里显示新名字", got == r_new,
              f"期望 {r_new!r}，实得 {got!r}")
        check("改名不改变比对条数（compared）",
              sim_b_after["compared"] == sim_b_before["compared"],
              f"{sim_b_before['compared']} → {sim_b_after['compared']}")

        # 现场恢复：改回原名，并确认列表里也回退（同样是清缓存的效果）
        send("PATCH", f"/api/tracks/{rid}", {"name": r_orig})
        back = sim_map(similarity(BASE_TRACK)).get(rid, {}).get("name")
        check("已改回原名（清理现场）", back == r_orig, f"实得 {back!r}")

    # ================= C. ⭐⭐ 删除后相似度必须变 =================
    # 在防什么：删了一条轨迹，别的主线的相似度结果里还留着它（缓存没清）——
    # 就是这次数据管理功能要兑现的那笔"欠账"。
    print("\n=== C. ⭐⭐ 删除后相似度必须变（证明缓存被清了）===")
    sim0 = similarity(BASE_TRACK)
    compared0 = sim0["compared"]
    if not sim0["matches"]:
        print("\n主线没有匹配，后续无法验证 —— 直接结束")
        sys.exit(2)
    first = sim0["matches"][0]
    victim = first["trackId"]
    victim_name = first["name"]
    victim_points = first["pointCount"]
    print(f"  主线 {BASE_TRACK}: compared={compared0}，第一名 track {victim}「{victim_name}」"
          f" sim={first['similarity']} 点数={victim_points}")

    files_before = len(recycle_files())

    st, del_body = send("DELETE", f"/api/tracks/{victim}")
    check("删除返回 200", st == 200, f"HTTP {st}")
    check("响应里带了回收站路径", bool(del_body.get("recyclePath")), str(del_body)[:120])
    check("响应里的点数是删除前的点数",
          del_body.get("deletedPointCount") == victim_points,
          f"{del_body.get('deletedPointCount')} vs {victim_points}")

    # ③ 回收站文件真的落盘了
    files_after = recycle_files()
    check("回收站文件数 +1", len(files_after) == files_before + 1,
          f"{files_before} → {len(files_after)}")

    newest = max(files_after, key=lambda p: p.stat().st_mtime) if files_after else None
    if newest:
        gj = json.loads(newest.read_text(encoding="utf-8"))
        coords = gj["features"][0]["geometry"]["coordinates"]
        props = gj["features"][0]["properties"]
        times = props.get("times", [])
        check("回收站文件里的点数与删除前接口报的一致", len(coords) == victim_points,
              f"文件 {len(coords)} vs 接口报的 {victim_points}")
        check("回收站文件带了名字", props.get("name") == victim_name,
              f"{props.get('name')!r}")
        check("回收站文件带了每个点的时间", len(times) == len(coords),
              f"times={len(times)} coords={len(coords)}")
        check("回收站文件里的时间每一项都非空（长度对但内容是空串不算数）",
              len(times) > 0 and all(isinstance(t, str) and t.strip() for t in times),
              f"首 {times[0] if times else None!r} 末 {times[-1] if times else None!r}")
        check("回收站文件名里带轨迹名和点数",
              victim_name.replace(" ", "_") in newest.name or "unnamed" in newest.name,
              newest.name)
    else:
        check("回收站里有刚写出的文件", False, "目录里一个 geojson 都没有")

    # ① 相似度必须变
    sim1 = similarity(BASE_TRACK)
    check("主线 20 的 compared 少了 1", sim1["compared"] == compared0 - 1,
          f"{compared0} → {sim1['compared']}")
    check("被删的那条不再出现在名单里",
          all(m["trackId"] != victim for m in sim1["matches"]))
    check("被删的那条详情 → 404",
          send("GET", f"/api/tracks/{victim}")[0] == 404)

    # ================= D. 删除的边界 =================
    print("\n=== D. 删除的边界 ===")
    st, _ = send("DELETE", f"/api/tracks/{victim}")
    check("再删同一条 → 404", st == 404, f"HTTP {st}")
    st, _ = send("DELETE", "/api/tracks/999999")
    check("删不存在的 → 404", st == 404, f"HTTP {st}")

    # ================= E. 删除后热点也要重算 =================
    print("\n=== E. 删除后热点反映新数据 ===")
    h = get("/api/analysis/hotspots")
    check("热点接口仍能正常返回", "hotspots" in h, f"热点 {len(h.get('hotspots', []))} 个")
    check("热点扫描的轨迹数已减少", h.get("scannedTracks", 10 ** 9) < total_before,
          f"scannedTracks={h.get('scannedTracks')}（开工前 total={total_before}）")

    # ================= F. 🆕 新增导入后，相似度必须反映新轨迹 =================
    # 在防什么：ImportService.persist 里那句 similarityCache.invalidateAll()。
    # 新增一条轨迹后，如果没清缓存，别的主线点开还是旧名单 —— 新导入的轨迹
    # "看不见"。这条只有真的导入一条**几何上会进候选名单**的轨迹才测得出来。
    print("\n=== F. 🆕 新增导入后相似度必须反映新轨迹（证明缓存被清了）===")
    sim_f_before = similarity(BASE_TRACK)
    compared_before_import = sim_f_before["compared"]
    print(f"  导入前：主线 {BASE_TRACK} 的 compared={compared_before_import}")

    # 先定位 track 20 的原始文件 —— 用 SHA256 前 32 位对上 external_id，绝不靠文件名猜
    src = None
    src_err = ""
    if not GEOLIFE.exists():
        src_err = f"GeoLife 目录不存在：{GEOLIFE}"
    else:
        hits = list(GEOLIFE.glob(f"*/Trajectory/{base_detail['name']}.plt"))
        if not hits:
            src_err = f"没有找到 {base_detail['name']}.plt"
        else:
            want = base_detail["externalId"]
            for p in hits:
                if hashlib.sha256(p.read_bytes()).hexdigest()[:32] == want:
                    src = p
                    break
            if src is None:
                src_err = f"{len(hits)} 个同名文件，但 SHA256 都对不上 externalId={want}"

    new_file = None
    new_id = None
    if src is None:
        check("找到主线 20 的原始 GeoLife 文件（④ 的前提）", False, src_err)
        note("④ 无法执行 —— 见上面的 [XX]")
    else:
        check("找到主线 20 的原始 GeoLife 文件（SHA256 对上 external_id）", True, str(src))
        # 复制到工作区再改：原文件只读、绝不修改；而且沙箱里直接拿 D:\ 上传会被拒
        lines = src.read_text(encoding="utf-8").splitlines()
        idx = None
        for i, line in enumerate(lines):
            if geo_life_point_line(line) is not None:
                idx = i
                break
        if idx is None:
            check("改坐标：源文件里能找到真的坐标行", False, "没找到形如 lat,lon,...,date,time 的行")
        else:
            f = lines[idx].split(",")
            old_lat, old_lon = f[0], f[1]
            # 只动第 6 位小数（≈0.11 米）：内容变了 → SHA256 变了 → 不会被当重复，
            # 几何几乎不变 → 新轨迹仍然落在主线 20 的 50 米容差里
            f[0] = "%.6f" % (float(f[0]) + 0.000001)
            lines[idx] = ",".join(f)
            new_name = "verify-new-" + "%06x" % random.getrandbits(24)
            new_file = TMP / (new_name + ".plt")
            new_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"  造了个新文件：{new_file.name}")
            print(f"    改的是第 {idx + 1} 行（真正的轨迹点）纬度 {old_lat} → {f[0]}"
                  f"（内容变、几何基本不变）")
            print(f"    新文件 SHA256[:32] = "
                  f"{hashlib.sha256(new_file.read_bytes()).hexdigest()[:32]}"
                  f"（原文件 {base_detail['externalId']}）")

            st, imp = upload(new_file)
            check("上传返回 200", st == 200, f"HTTP {st} {str(imp)[:160]}")
            check("不是被当成重复跳过", imp.get("skippedDuplicate") is False,
                  f"skippedDuplicate={imp.get('skippedDuplicate')}")
            new_id = imp.get("id")
            check("新轨迹拿到了新 id", isinstance(new_id, int), f"id={new_id}")
            check("新轨迹名字不撞（用文件名兜底）", imp.get("name") == new_name,
                  f"{imp.get('name')!r}")

            if isinstance(new_id, int):
                # ⭐ 先做一次**判别性**检查：把新轨迹自己当主线。
                # 它和主线 20 的点几乎重合，所以 SQL 一定 join 得上。
                # 有了这一条，后面 compared 没变时才能分清是哪种原因：
                #   · 这里 OK、主线 20 的名单里却没有新轨迹  → 缓存没清（真 bug）
                #   · 这里也看不到主线                       → SQL 没匹配上（新轨迹其实无关）
                # 第一次跑对拍时正是靠这条把"看着像缓存没清"钉成了"在测旧代码"。
                sim_new = similarity(new_id, limit=5)
                hit_base = next((m for m in sim_new["matches"] if m["trackId"] == BASE_TRACK), None)
                check("新轨迹自己当主线时能看到主线 20（说明 SQL 能 join 上，排除'新轨迹无关'）",
                      hit_base is not None,
                      f"新轨迹的 compared={sim_new['compared']}，与主线 20 的相似度="
                      f"{hit_base['similarity'] if hit_base else None}")

                sim_f_after = similarity(BASE_TRACK)
                print(f"  导入后：主线 {BASE_TRACK} 的 compared={sim_f_after['compared']}")
                check("导入后 compared +1（证明新增也清了缓存）",
                      sim_f_after["compared"] == compared_before_import + 1,
                      f"{compared_before_import} → {sim_f_after['compared']}")
                check("新轨迹出现在主线 20 的候选名单里",
                      any(m["trackId"] == new_id for m in sim_f_after["matches"]),
                      f"新 id={new_id}")

                # 清理现场：删掉刚导入的那条（这次也会走回收站，正常）
                n_before = len(recycle_files())
                st, del2 = send("DELETE", f"/api/tracks/{new_id}")
                check("清理：删掉刚导入的轨迹返回 200", st == 200, f"HTTP {st}")
                check("清理：回收站又多了一个文件",
                      len(recycle_files()) == n_before + 1,
                      f"{n_before} → {len(recycle_files())}")
                sim_f_final = similarity(BASE_TRACK)
                check("清理后 compared 回到导入前",
                      sim_f_final["compared"] == compared_before_import,
                      f"{sim_f_after['compared']} → {sim_f_final['compared']}")

    # ================= G. 总数与收尾 =================
    print("\n=== G. 轨迹总数 ===")
    listing = get("/api/tracks?limit=1")
    total_after = listing["total"]
    print(f"  开工前 total={total_before}，现在 total={total_after}")
    check("轨迹总数比开工前少 1（净删一条：删了第一名，新增的那条已清理）",
          total_after == total_before - 1, f"{total_before} → {total_after}")
    ids = track_ids()
    check("列表实际条数与 total 一致", len(ids) == total_after, f"{len(ids)} vs {total_after}")
    check("被删的相似度第一名确实不在库里了", victim not in ids, f"victim={victim}")
    if new_id is not None:
        check("临时导入的那条也确实不在库里了", new_id not in ids, f"new_id={new_id}")

    print("\n" + "=" * 68)
    print(f"⚠️ 本次删掉了 track {victim}「{victim_name}」（{victim_points} 个点）。")
    print(f"   回收站文件：{newest}")
    if new_id is not None:
        rest = recycle_files()
        newest2 = max(rest, key=lambda p: p.stat().st_mtime) if rest else None
        print(f"   另外还删掉了本次临时导入的 track {new_id}"
              f"（上传用的源文件：{new_file}）。")
        print(f"   它的回收站文件：{newest2}")
    print("   要恢复的话：从原始文件重新导入，或用当天的数据库快照：")
    for p in (sorted(BACKUPS.glob("calcite-*.dump")) if BACKUPS.exists() else []):
        print(f"     {p}  ({p.stat().st_size / 1024 / 1024:.1f} MB)")
    print("=" * 68)

    print(f"\n{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


main()
