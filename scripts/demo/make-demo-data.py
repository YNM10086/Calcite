#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcite 演示数据集生成器（M4 · Task 4）
============================================================================
用途
----
生成 `scripts/db/04-demo-data.sql`：14 条**合成** GPS 轨迹（坐标落在北京真实地标附近，
轨迹本身是编的），导入后让五个分析面板（停留点 / 热点 / 密度 / 相似 / 圈选）都有东西看。

设计依据
--------
- 规格：`docs/superpowers/specs/2026-09-25-m4-wrapup-design.md` 的「### Task 4：演示数据集」
  那 14 行表格（每条轨迹服务哪个面板、关键参数）
- 字段清单与幂等写法：`scripts/db/02-sample-track.sql`
- 表结构 / SRID 4326：`scripts/db/01-schema.sql`

口径与真实导入器**逐条对齐**（不是自己发明的公式）
------------------------------------------------
| 派生项 | 出处 | 本脚本的复刻 |
|---|---|---|
| 相邻点球面距离 | `service/GeoUtils.java:21` haversine，R=6371008.8 | `haversine_m()` |
| 逐点速度 | `TrackCleaner.java:59-62`：第 0 点 NULL；`dt>0` 才算，否则 NULL | `finalize()` 第 ② 步 |
| 总时长 | `TrackCleaner.java:83`：首末点时间差取整秒 | `duration_s` |
| GPS 漂移标记 | `TrackCleaner.java:65-78`：阈值 `max(8, 3×速度中位数)`，超阈值**两端都标** | `finalize()` 第 ③ 步 |
| 海拔缺失 | `TrackCleaner.java:114-132`：整条全同（含全 NULL）→ 全部 NULL | `normalize_elevation()` |
| 总距离 | `TrackCleaner.java`：**Haversine 求和**（不是 `ST_Length(geography)`，两者实测差约 1.9%，Java 注释已说明） | `total_distance_m` |
| 轨迹线 | `ImportService.java:378-384` `applyCleaned` → `buildLineString(cleaned.points())`：**按清洗后的点序**连成 LineString | `linestring_wkt()`（脚本里点的顺序就是 seq 顺序） |

⚠️ 坐标在生成时**先四舍五入到 6 位小数（约 0.1 米）再算派生值**。
原因：SQL 里写入的就是这 6 位小数的坐标，先算后舍会让"点几何"与"速度/距离"差出
毫米级；先舍后算则三者严格自洽（误差 &lt; 1 厘米，对 50 米级阈值无影响）。

可复现性
--------
- 只用标准库；固定随机种子（`random.Random(20260925)`）
- 连跑两次输出**字节一致**（换行统一写 `\\n`，不跟随平台）
- `--self-check`：用上面那套口径**离线**跑一遍分析阈值（不是连数据库），
  打印每条轨迹的点数 / 距离 / 时长 / 停留段数 / 漂移点数 / 是否有海拔

用法
----
    python scripts/demo/make-demo-data.py                # 生成 SQL
    python scripts/demo/make-demo-data.py --self-check    # 生成 + 自检 + 打印报告
    python scripts/demo/make-demo-data.py --out 其它路径.sql

导入
----
    psql -U postgres -d calcite -f scripts/db/04-demo-data.sql
（首行 `\\encoding UTF8` + 开头 `DELETE FROM track WHERE external_id LIKE 'DEMO-%'`，
  可重复执行；与 02-sample-track.sql 的 SAMPLE-001 互不干扰）
"""

from __future__ import annotations

import argparse
import hashlib
import math
import random
from pathlib import Path

# ============================================================ 阈值常量
# 全部来自 backend/src/main/resources/application.yml，改 yml 就要改这里
STAY_RADIUS_M = 50.0          # calcite.stay-point.radius-m
STAY_MIN_DURATION_S = 300     # calcite.stay-point.min-duration-s
STAY_MAX_GAP_S = 300          # calcite.stay-point.max-gap-s
HOTSPOT_RADIUS_M = 200.0      # calcite.hotspot.radius-m
HOTSPOT_MIN_VISITS = 2        # calcite.hotspot.min-visits
SIM_TOLERANCE_M = 50.0        # calcite.similarity.default-tolerance-m
MAX_SPEED_MPS = 8.0           # calcite.import.max-speed-mps
SPEED_MEDIAN_FACTOR = 3.0     # calcite.import.speed-median-factor
EARTH_RADIUS_M = 6371008.8    # GeoUtils.java 用的地球平均半径

# 停留点的合成参数：最坏情况离中心 √2×10 ≈ 14.1 m < 25 m（半径阈值的一半），
# 保证"合成出来的停留段一定被判得出来"，且不会被窗口扩窗规则吃掉。
STAY_JITTER_M = 10.0

SEED = 20260925
TZ = "+08"
# 时间原点：所有轨迹的秒数都是"相对于这个时刻的偏移"。
# 取 09-02 12:00 是为了让每条轨迹的秒数都是正数（最早那条 08:xx 也不会变成负数），
# 同时保证整批数据落在 09-01 ~ 09-07 这个窗口内（main 里有断言）。
BASE_DATETIME = "2026-09-02 12:00:00"
BASE_SEC = 36 * 3600     # 原点相对 2026-09-01 00:00 的秒数
WINDOW_S = 7 * 86400     # 窗口宽度：2026-09-01 ~ 2026-09-07

# 哪些轨迹带海拔、哪些**故意全 NULL**（模拟"传感器没记录海拔"这种真实情况，
# 让前端的"这条轨迹没有海拔数据"降级提示有东西可展示）。
#   • #3 环湖跑步：规格里明确要求"无海拔"（诚实显示 0 个停留点那条）
#   • #4 骑行 / #5 跨城长途 / #12 咖啡店 / #13 CBD：合成时就没给海拔，凑够几种"缺海拔"的形态
WITH_ELEVATION = {1, 2, 6, 7, 8, 9, 10, 11, 14}
NO_ELEVATION = {3, 4, 5, 12, 13}

# ============================================================ 基础几何


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（米）—— 与 GeoUtils.haversineMeters 同一个公式、同一个半径"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def bezier(points, t: float):
    """de Casteljau：二次/三次贝塞尔取点。用来把折线拐角磨圆、把环路磨成圆形"""
    pts = list(points)
    while len(pts) > 1:
        pts = [(lerp(pts[i][0], pts[i + 1][0], t), lerp(pts[i][1], pts[i + 1][1], t))
               for i in range(len(pts) - 1)]
    return pts[0]


def quadratic(p0, p1, p2, samples: int = 12):
    return [bezier((p0, p1, p2), i / samples) for i in range(samples + 1)]


def densify(waypoints, spacing_m: float):
    """把折线按固定弧长（米）重新采样，返回等间距点列（含首尾）"""
    pts = list(waypoints)
    if len(pts) < 2 or spacing_m <= 0:
        return pts

    def dist(a, b):
        return haversine_m(a[1], a[0], b[1], b[0])

    out = [pts[0]]
    s = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = dist(a, b)
        if seg <= 0:
            continue
        t = spacing_m - (s % spacing_m)
        while t <= seg + 1e-9:
            f = t / seg
            out.append((lerp(a[0], b[0], f), lerp(a[1], b[1], f)))
            t += spacing_m
        s += seg
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def round_corners(waypoints, radius_m: float, samples: int = 8):
    """把折线的每个拐角用二次贝塞尔磨圆（不然合成轨迹的直角看起来像假的）"""
    pts = list(waypoints)
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev, cur, nxt = pts[i - 1], pts[i], pts[i + 1]
        d_in = haversine_m(cur[1], cur[0], prev[1], prev[0])
        d_out = haversine_m(cur[1], cur[0], nxt[1], nxt[0])
        r = min(radius_m, d_in / 2, d_out / 2)
        if r < 1.0:
            out.append(cur)
            continue
        a = (lerp(cur[0], prev[0], r / d_in), lerp(cur[1], prev[1], r / d_in))
        b = (lerp(cur[0], nxt[0], r / d_out), lerp(cur[1], nxt[1], r / d_out))
        out.extend(quadratic(a, cur, b, samples)[1:-1])
    out.append(pts[-1])
    return out


def offset_path(coords, offset_m: float):
    """把整条路径沿**垂直方向**平移（用来做"回程略有偏移"：路线重合但差一条街）"""
    out = []
    n = len(coords)
    for i, (lon, lat) in enumerate(coords):
        j = min(i + 1, n - 1)
        k = max(i - 1, 0)
        dx = coords[j][0] - coords[k][0]
        dy = coords[j][1] - coords[k][1]
        norm = math.hypot(dx, dy)
        if norm < 1e-12:
            nx, ny = 0.0, 0.0
        else:
            nx, ny = -dy / norm, dx / norm
        m_lon = 111320.0 * math.cos(math.radians(lat))
        out.append((lon + nx * offset_m / m_lon, lat + ny * offset_m / 110574.0))
    return out


# ============================================================ 轨迹组装


class TrackBuilder:
    """一条轨迹：依次追加"移动段 / 停留段"，最后按导入器口径算派生列

    ⚠️ **时间模型是显式的，不做隐式串接**。第一版这里踩过一个坑：
    用"上一段末尾 + 本段间隔"去推时间，结果 `stay()` 从 `_gap()`（两点之差）起步，
    在"上一个点是整段最后一个点"时算出 0 或 2 秒，导致时间戳**重复且非单调** ——
    `finalize` 一排序，轨迹就在两个地标之间来回跳，距离被放大 25 倍、还凭空多出几十个"漂移点"。
    现在的规矩：**每个段自己声明时间**（move 用 start_s，stay 从 last_sec 起），
    `finalize` 再断言时间戳严格递增 —— 不满足就直接报错，绝不静默产出一条乱跳的轨迹。
    """

    def __init__(self, index: int, name: str, landmarks: tuple):
        self.index = index
        self.name = name
        self.landmarks = landmarks
        self.points: list[dict] = []

    # ---- 追加点 ----

    @property
    def last_sec(self) -> int:
        return self.points[-1]["sec"] if self.points else 0

    def _at(self, sec: int, lon: float, lat: float, ele):
        """坐标在这里就四舍五入到 6 位小数 —— 之后所有派生值都基于这个坐标算"""
        self.points.append({
            "sec": int(sec),
            "lon": round(float(lon), 6),
            "lat": round(float(lat), 6),
            "ele": None if ele is None else round(float(ele), 2),
        })

    def walk(self, sec: int, lon: float, lat: float, ele=None):
        self._at(sec, lon, lat, ele)
        return self

    def next_sec(self) -> int:
        """接在已有轨迹后面的下一段起点秒数（留 1 秒不重合 —— 同秒两点会让速度除零）"""
        return self.last_sec + 1

    def move(self, path_lonlat, start_s: int, speed_mps: float, elev_fn=None):
        """沿等间距点列按固定速度走。`start_s` 是第一点的秒数（时间起点由调用方定）

        ⚠️ 时间用**累计里程**算：`t_i = start_s + round(累计距离 / 速度)`，
        不是"每步 round(步长/速度) 再累加"。后者在步长略有抖动时会把 3.0 m 的步子
        四舍五入成 1 秒（真实应该 0.6 秒），凭空造出一个 25 m/s 的假速度尖刺
        —— 第一版就是这么给 DEMO-002 标出 4 个假漂移点的。累计写法没有这个问题。

        `path_lonlat` 是 (经度, 纬度) 的列表（与地标常量一致，注意别跟 hav 的参数顺序搞混）。
        """
        if speed_mps <= 0:
            raise ValueError("速度必须为正")
        path = list(path_lonlat)
        if not path:
            return
        # 起步时间不能贴着上一段的最后一个点：段与段之间常有几十米的几何跳变
        # （比如回程相对去程偏移了 20 m），若只隔 1 秒，真实导入器会把它算成
        # 一个 20 m/s 的"漂移尖刺"（阈值只有 13~15）。留 20 秒，让这一步的
        # 速度落在正常量级（约 1 m/s），不制造假漂移。
        s = max(int(start_s), self.last_sec + 20) if self.points else int(start_s)
        # 常规步长（秒）：相邻采样点之间应有的时间差，用来识别"塌陷"的尾巴
        normal_step = max(2.0, (haversine_m(path[0][1], path[0][0], path[1][1], path[1][0])
                                / speed_mps)) if len(path) > 1 else 2.0
        # ---- 先算完整段时间，再一次性追加 ----
        # 累计里程 ⇒ t_i = start + round(累计距离 / 速度)，天然单调；
        # 但 `densify` 会把终点原样补上，尾巴那截往往不足一个采样间距，
        # 四舍五入后就跟上一个点挤在同一秒、甚至反超 —— 这里做一次"从后往前"的
        # 顺延（gap 不够就把它之后的所有点一起往后推），保证**每一步间隔都不小于常规步长**。
        # ⚠️ 不做这件事的后果不是"时间难看一点"：距离是按上一个真实点算的，
        #    1 秒走 25 米就是一个 25 m/s 的假速度尖刺，会被清洗器标成 GPS 漂移
        #    （第一版就是这么给 DEMO-002 标出 4 个假漂移点、还给 DEMO-013 换算出
        #     10.08 m/s 的假阈值的）。
        times = []
        travel = 0.0
        for i, (lon, lat) in enumerate(path):
            if i > 0:
                travel += haversine_m(path[i - 1][1], path[i - 1][0], lat, lon)
            times.append(s + int(round(travel / speed_mps)))
        # 用 round 而不是 ceil：采样间距是 12.0003 m 这种带零头的值，ceil(3.0001) = 4
        # 会把每一格的间隔都拉长 1 秒（691 个点就白白多走 690 秒、速度掉到 2.99 m/s，
        # 阈值也跟着变成 8.98 —— 第二版踩过这个坑）。
        step = max(2, int(round(normal_step)))
        for i in range(len(times) - 2, -1, -1):
            if times[i + 1] - times[i] < step:
                # 只补"差的那些秒"（need），**不能**直接把 times[i] 顶到 times[i+1]-step
                # ——那样会把整条尾巴一路往后推几百秒（第一版就这么把 DEMO-006 的
                #   中位速度拉到 2.99 m/s、阈值莫名降到 8.98 的）。
                need = step - (times[i + 1] - times[i])
                for j in range(i + 1, len(times)):
                    times[j] += need
        for (lon, lat), t in zip(path, times):
            ele = None if elev_fn is None else elev_fn(t)
            self.walk(t, lon, lat, ele)

    def stay(self, center, duration_s: int, offset_s: float, rng: random.Random, ele=None):
        """在 center 附近抖动地"停着不动"，每 offset_s 秒一个点，时长约 duration_s。

        起点时间取**上一个点的时间 + 1 秒**，之后按 i×offset_s 均匀推进 ——
        所以相邻间隔恒等于 offset_s，不会出现"2 秒 / 45 秒交替"的假速度尖刺；
        +1 秒是为了不跟上一段的最后一个点撞在同一秒（同秒两点会让速度除零）。

        抖动半径 ≤ 10 m ⇒ 窗口重心在真实中心 10 m 内、点到重心 ≤ 20 m，
        「到重心最大距离」必然 < 25 m（= 半径阈值的一半），所以这段一定被识别成停留。
        """
        n = max(2, int(round(duration_s / offset_s)))
        base = self.last_sec + 20       # +20：段间常有几十米几何跳变，太近会被算成漂移
        m_lon = 111320.0 * math.cos(math.radians(center[1]))
        for i in range(n + 1):
            a = rng.uniform(-math.pi, math.pi)
            r = rng.uniform(0.0, STAY_JITTER_M)
            lon = center[0] + r * math.cos(a) / m_lon
            lat = center[1] + r * math.sin(a) / 110574.0
            self.walk(base + int(round(i * offset_s)), lon, lat, ele)

    def spike(self, sec_gap: int, lon: float, lat: float, ele=None):
        """插入一个 GPS 漂移点（时间只走了 sec_gap 秒）—— 速度尖刺就是这么做出来的"""
        self._at(self.last_sec + int(sec_gap), lon, lat, ele)

    # ---- 派生列（严格复刻 TrackCleaner + GeoUtils）----

    def finalize(self) -> dict:
        pts = sorted(self.points, key=lambda p: p["sec"])          # ① 排序
        n = len(pts)
        if n < 2:
            raise ValueError(f"{self.name}: 至少需要 2 个点，实际 {n}")
        for i in range(1, n):
            if pts[i]["sec"] <= pts[i - 1]["sec"]:
                raise ValueError(
                    f"{self.name}: 时间戳非严格递增（seq {i - 1}→{i}："
                    f"{pts[i - 1]['sec']} → {pts[i]['sec']}）——"
                    "同秒两个点会让速度变成除零，轨迹也会在两点间来回跳")

        speeds: list = [None] * n                                   # ② 逐点速度
        total = 0.0
        for i in range(1, n):
            a, b = pts[i - 1], pts[i]
            d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            total += d
            dt = b["sec"] - a["sec"]
            speeds[i] = (d / dt) if dt > 0 else None

        threshold = self._threshold(speeds)                         # ③ 漂移
        outliers = [False] * n
        for i in range(1, n):
            v = speeds[i]
            if v is not None and v > threshold:
                outliers[i - 1] = True
                outliers[i] = True

        pts = self._normalize_elevation(pts)                        # ④ 海拔

        return {
            "index": self.index,
            "name": self.name,
            "landmarks": self.landmarks,
            "points": pts,
            "speeds": speeds,
            "outliers": outliers,
            "distance_m": total,
            "duration_s": pts[-1]["sec"] - pts[0]["sec"],
            "threshold_mps": threshold,
            "has_elevation": any(p["ele"] is not None for p in pts),
            "has_outliers": any(outliers),
        }

    @staticmethod
    def _threshold(speeds) -> float:
        """阈值 = max(绝对下限 8 m/s, 3 × 正速度中位数)（TrackCleaner.thresholdFor）"""
        valid = sorted(v for v in speeds if v is not None and v > 0)
        if not valid:
            return MAX_SPEED_MPS
        m = len(valid)
        median = valid[m // 2] if m % 2 == 1 else (valid[m // 2 - 1] + valid[m // 2]) / 2.0
        return max(MAX_SPEED_MPS, SPEED_MEDIAN_FACTOR * median)

    @staticmethod
    def _normalize_elevation(pts):
        """海拔整条全同（含全 NULL）→ 全部 NULL（TrackCleaner.normalizeElevation）"""
        first = pts[0]["ele"]
        same = all((p["ele"] is None) if first is None else (p["ele"] == first) for p in pts)
        if not same:
            return pts
        return [dict(p, ele=None) for p in pts]


# ============================================================ 分析口径复刻（自检用）


def detect_stays(points) -> list:
    """逐行复刻 StayPointService.detect（滑动窗口 + 半径/时长/断档三条规则）"""
    out = []
    if len(points) < 2:
        return out
    n = len(points)
    i = 0
    while i < n:
        j = i
        while j + 1 < n:
            if points[j + 1]["sec"] - points[j]["sec"] > STAY_MAX_GAP_S:
                break
            if _window_radius(points, i, j + 1) * 2 > STAY_RADIUS_M:
                break
            j += 1
        span = points[j]["sec"] - points[i]["sec"]
        if j > i and span >= STAY_MIN_DURATION_S:
            out.append({
                "from": i, "to": j,
                "duration_s": span,
                "radius_m": _window_radius(points, i, j),
                "center": _centroid(points, i, j),
            })
            i = j + 1
        else:
            i += 1
    return out


def _centroid(points, a: int, b: int):
    k = b - a + 1
    return (sum(p["lon"] for p in points[a:b + 1]) / k,
            sum(p["lat"] for p in points[a:b + 1]) / k)


def _window_radius(points, a: int, b: int) -> float:
    c_lon, c_lat = _centroid(points, a, b)
    return max(haversine_m(c_lat, c_lon, p["lat"], p["lon"]) for p in points[a:b + 1])


def cluster_hotspots(stays: list) -> list:
    """逐行复刻 HotspotService.cluster（并查集单链聚类，距离 ≤ 200 m 连边）"""
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
            if haversine_m(a["center"][1], a["center"][0],
                           b["center"][1], b["center"][0]) <= HOTSPOT_RADIUS_M:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb

    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    out = []
    for members in groups.values():
        if len(members) >= HOTSPOT_MIN_VISITS:
            ids = sorted({stays[m]["track"] for m in members})
            out.append({
                "visits": len(members),
                "trackCount": len(ids),
                "tracks": ids,
                "duration_s": sum(stays[m]["duration_s"] for m in members),
                "center": (sum(stays[m]["center"][0] for m in members) / len(members),
                           sum(stays[m]["center"][1] for m in members) / len(members)),
            })
    out.sort(key=lambda h: (-h["trackCount"], -h["visits"], -h["duration_s"],
                            h["center"][1], h["center"][0]))
    return out


def similarity_pct(a_points, b_points, tol_m: float = SIM_TOLERANCE_M):
    """复刻 SimilarityMath.pct + TrackPointRepository.findSimilarityScores 的取小口径"""
    def hits(src, dst):
        return sum(1 for p in src
                   if any(haversine_m(p["lat"], p["lon"], q["lat"], q["lon"]) <= tol_m
                          for q in dst))

    fwd = 100.0 * hits(a_points, b_points) / len(a_points)
    rev = 100.0 * hits(b_points, a_points) / len(b_points)
    return min(fwd, rev)


# ============================================================ 地标（经纬度取自公开地图，轨迹是合成的）

LM = {
    "wudaokou":   (116.3378, 39.9928),   # 五道口
    "zhongguancun": (116.3160, 39.9836),  # 中关村（与五道口 2.4 km）
    "tiantan":    (116.3974, 39.9093),   # 天安门广场
    "coffee":     (116.4035, 39.9135),   # 广场东北角咖啡店（离广场 400 m 左右）
    "olympic":    (116.3880, 39.9930),   # 奥林匹克公园
    "summer":     (116.2750, 39.9990),   # 颐和园
    "wangjing":   (116.4720, 40.0020),   # 望京（商业区，早/午/晚三条共用路口）
    "cbd":        (116.4620, 39.9130),   # 国贸（CBD 走廊）
    "shichahai":  (116.3860, 39.9400),   # 什刹海（环湖）
    "daxing":     (116.3410, 39.7290),   # 南六环起点（跨城长途起点）
}


# ============================================================ 14 条轨迹

def build_tracks(rng: random.Random) -> list:
    tracks = []

    # ---------- #1 / #2 通勤（五道口 ↔ 中关村），互为相似度第一名 ----------
    commute_way = [LM["wudaokou"], (116.3300, 39.9905), (116.3230, 39.9870),
                   LM["zhongguancun"]]
    commute_raw = densify(round_corners(commute_way, 80.0), 10.0)   # 约 2.4 km / 10 m 一个点

    t1 = TrackBuilder(1, "演示·通勤去程 五道口→中关村", ("DEMO-001",))
    t1.stay(LM["wudaokou"], 480, 45, rng, ele=45.0)                  # 起点停留 8 分钟
    t1.move(commute_raw, t1.next_sec(), 5.0,
            elev_fn=lambda s: 45 + 4 * math.sin(s / 240.0))
    t1.stay(LM["zhongguancun"], 600, 45, rng, ele=45.0)              # 终点停留 10 分钟
    tracks.append(t1.finalize())

    back_raw = offset_path(list(reversed(commute_raw)), 20.0)        # 回程：重合但偏移 20 m
    t2 = TrackBuilder(2, "演示·通勤回程 中关村→五道口", ("DEMO-002",))
    t2.stay(LM["zhongguancun"], 480, 45, rng, ele=45.0)
    t2.move(back_raw, t2.next_sec(), 5.0,
            elev_fn=lambda s: 45 + 4 * math.sin(s / 240.0))
    t2.stay(LM["wudaokou"], 600, 45, rng, ele=45.0)
    tracks.append(t2.finalize())

    # ---------- #3 环湖跑步：闭合环、**无海拔**、无停留点 ----------
    # 采样 12 m + 相邻点抖 1.5 m：任何 300 秒窗口至少走 900 m（≈3 m/s × 300 s），
    # 跨度必然 >> 50 m 的直径阈值 ⇒ 诚实地产出 0 个停留点。
    ring = []
    center = LM["shichahai"]
    radius_m = 500.0
    segs = 8
    ctrl = []
    for k in range(segs):
        ang = 2 * math.pi * k / segs
        ctrl.append((center[0] + radius_m * math.sin(ang) / (111320.0 * math.cos(math.radians(center[1]))),
                     center[1] + radius_m * math.cos(ang) / 110574.0))
    loop_way = []
    for k in range(segs):
        p0 = ctrl[k]
        p2 = ctrl[(k + 1) % segs]
        mid = ((p0[0] + p2[0]) / 2, (p0[1] + p2[1]) / 2)
        k_ctrl = (center[0] + (mid[0] - center[0]) * 1.28, center[1] + (mid[1] - center[1]) * 1.28)
        loop_way.extend(quadratic(p0, k_ctrl, p2, 10))
    loop_way.append(loop_way[0])
    loop_pts = densify(loop_way, 12.0)
    t3 = TrackBuilder(3, "演示·环湖跑步（无海拔）", ("DEMO-003",))
    sec = 0
    t3.walk(0, loop_pts[0][0], loop_pts[0][1], None)
    for i in range(1, len(loop_pts)):
        sec += 45                                                   # 12 m / 45 s ≈ 0.96 m/s 的慢跑
        jl = rng.uniform(-1.5, 1.5) / (111320.0 * math.cos(math.radians(loop_pts[i][1])))
        ja = rng.uniform(-1.5, 1.5) / 110574.0
        t3.walk(sec, loop_pts[i][0] + jl, loop_pts[i][1] + ja, None)
    tracks.append(t3.finalize())

    # ---------- #4 含 GPS 漂移的骑行（3 个速度尖刺）----------
    # 做法：先正常骑行一遍（4.5 m/s、约 48 m 一个采样点），然后在三个位置**插入偏出去的点**：
    # 偏 35 m 只花 6 秒、偏 70 m 再花 6 秒 ⇒ 5.8 m/s 与 11.7 m/s。
    # 中位数仍是 4.4 ⇒ 阈值 = max(8, 3×4.4) = 13.2 ⇒ 后一段超阈值 ⇒ **两端都被标记**（宁可多标不可漏标）。
    # ⚠️ 插点必须发生在 `move()` **之后**：`move()` 内部会丢掉"与上一点同秒"的点，
    #    边插边算时间的话，插进去的点会被当成"同秒"直接丢掉（第一版就是这么让尖刺消失的）。
    ride_raw = densify(round_corners([LM["wudaokou"], (116.3300, 39.9950),
                                      (116.3250, 40.0000), LM["olympic"]], 60.0), 12.0)
    t4 = TrackBuilder(4, "演示·含 GPS 漂移的骑行", ("DEMO-004",))
    ride_pts = [ride_raw[i] for i in range(0, len(ride_raw), 4)]      # 每 4 点取一个 ≈ 48 m
    if ride_pts[-1] != ride_raw[-1]:
        ride_pts.append(ride_raw[-1])
    t4.move(ride_pts, 0, 4.5, elev_fn=lambda s: 44.0)
    for pos, k in ((0.30, int(len(ride_pts) * 0.30)),
                   (0.50, int(len(ride_pts) * 0.50)),
                   (0.70, int(len(ride_pts) * 0.70))):
        anchor_sec = t4.points[k]["sec"]
        c_lon, c_lat = ride_pts[k]
        m_lon = 111320.0 * math.cos(math.radians(c_lat))
        t4.walk(anchor_sec + 2, c_lon + 35.0 / m_lon, c_lat, 44.0)
        t4.walk(anchor_sec + 4, c_lon + 70.0 / m_lon, c_lat, 44.0)
    tracks.append(t4.finalize())

    # ---------- #5 跨城长途（北京 → 天津 ≈ 120 km，稀疏采样）----------
    long_way = [LM["daxing"], (116.5000, 39.6000), (116.8000, 39.4500),
                (117.0500, 39.2500), (117.2000, 39.1300)]
    long_pts = densify(long_way, 500.0)
    t5 = TrackBuilder(5, "演示·跨城长途 北京→天津", ("DEMO-005",))
    sec = 0
    t5.walk(0, long_pts[0][0], long_pts[0][1], 35.0)
    for i in range(1, len(long_pts)):
        step = haversine_m(long_pts[i - 1][1], long_pts[i - 1][0],
                           long_pts[i][1], long_pts[i][0])
        sec += max(1, int(round(step / 30.0)))                      # 高速 30 m/s
        t5.walk(sec, long_pts[i][0], long_pts[i][1], 35.0)
    tracks.append(t5.finalize())

    # ---------- #6 / #7 / #8 同一商圈早 / 午 / 晚三条（都经过望京同一路口）----------
    # 三条走**同一条走廊**、只是出发时刻不同 ⇒ 走廊上的格子每格 ≥3 条轨迹
    # （密度档 0.002° ≈ 170 m × 220 m，单元格大小就够装下三条线）。
    # 这三条的用途是"密度昼夜对比"，不承担停留点，所以不安排停留段。
    junction = (116.4720, 39.9980)          # 三条共用的"同一路口"
    mall_defs = [
        (6, "演示·望京早高峰 08:xx", (116.4600, 39.9930), "08:10:00"),
        (7, "演示·望京午间 12:xx", (116.4830, 40.0050), "12:30:00"),
        (8, "演示·望京晚间 18:xx", (116.4620, 40.0080), "18:05:00"),
    ]
    for index, name, start_lm, clock in mall_defs:
        b = TrackBuilder(index, name, (f"DEMO-{index:03d}",))
        path = densify(round_corners([start_lm, junction, LM["olympic"]], 80.0), 12.0)
        # 让"经过路口"这一刻落在标签写的钟点上。
        # ⚠️ 采样点是等弧长插值出来的，路口**本身通常不在点列里** ——
        # 所以取"离路口最近的那个采样点"，不能用 `path[i] == junction` 比坐标（永远不相等）。
        best_i, best_d = 0, float("inf")
        for i, (plon, plat) in enumerate(path):
            d = haversine_m(junction[1], junction[0], plat, plon)
            if d < best_d:
                best_i, best_d = i, d
        travel_to_junction = sum(
            haversine_m(path[i - 1][1], path[i - 1][0], path[i][1], path[i][0])
            for i in range(1, best_i + 1))
        base = hms(clock) - int(round(travel_to_junction / 4.0))
        b.move(path, base, 4.0, elev_fn=lambda s: 38 + 3 * math.cos(s / 300.0))
        tracks.append(b.finalize())

    # ---------- #9 / #10 / #11 三次到访天安门广场（人为造热点）----------
    square_defs = [
        (9, "演示·到访广场 第一次（晨）", "07:20:00", 390),
        (10, "演示·到访广场 第二次（午）", "12:15:00", 480),
        (11, "演示·到访广场 第三次（昏）", "18:40:00", 330),
    ]
    for index, name, clock, stay_s in square_defs:
        b = TrackBuilder(index, name, (f"DEMO-{index:03d}",))
        start = hms(clock)
        path = densify([(116.3900, 39.9000), (116.3948, 39.9050), LM["tiantan"]], 10.0)
        b.move(path, start, 4.5, elev_fn=lambda s: 44 + 2 * math.sin(s / 200.0))
        b.stay(LM["tiantan"], stay_s, 45, rng, ele=44.0)            # 在广场停留 5.5~8 分钟
        if index == 10:
            # #10 顺路进一趟咖啡店 —— 与广场相距约 400 m（> 热点半径 200 m），
            # 所以它是**独立**的第二次到访，与广场热点形成"大小对比"
            # （从广场走到咖啡店约 400 m，10 m 采样、4 m/s，约 100 秒）
            b.move(densify([LM["tiantan"], LM["coffee"]], 10.0), b.next_sec(), 4.0,
                   elev_fn=lambda s: 44.0)
            b.stay(LM["coffee"], 330, 45, rng, ele=44.0)
        tracks.append(b.finalize())

    # ---------- #12 两次到访同一咖啡店（与广场热点形成大小对比）----------
    t12 = TrackBuilder(12, "演示·两次到访咖啡店", ("DEMO-012",))
    t12.move(densify([(116.4090, 39.9160), LM["coffee"]], 15.0), 0, 4.0,
             elev_fn=lambda s: 43.0)
    t12.stay(LM["coffee"], 360, 60, rng, ele=43.0)
    t12.move(densify([LM["coffee"], (116.3920, 39.9060), (116.4000, 39.9020),
                      (116.4090, 39.9160)], 15.0), t12.next_sec(), 4.0,
             elev_fn=lambda s: 43.0)
    t12.stay((116.4090, 39.9160), 300, 60, rng, ele=43.0)
    tracks.append(t12.finalize())

    # ---------- #13 穿越 CBD 的一条（径直穿过一个便于拉框的走廊）----------
    cbd_way = [(116.4350, 39.9060), (116.4620, 39.9080), (116.4830, 39.9190),
               (116.4720, 39.9290)]
    cbd_pts = densify(round_corners(cbd_way, 70.0), 10.0)
    t13 = TrackBuilder(13, "演示·穿越 CBD 走廊", ("DEMO-013",))
    t13.move(cbd_pts, 0, 4.0, elev_fn=lambda s: 40.0)
    tracks.append(t13.finalize())

    # ---------- #14 极短轨迹（5 个点，边界情况）----------
    t14 = TrackBuilder(14, "演示·极短轨迹（5 个点）", ("DEMO-014",))
    short = [(116.3975, 39.9090), (116.3978, 39.9092), (116.3980, 39.9095),
             (116.3977, 39.9097), (116.3975, 39.9099)]
    sec = 0
    t14.walk(0, short[0][0], short[0][1], 41.0)
    for i in range(1, len(short)):
        sec += 30
        t14.walk(sec, short[i][0], short[i][1], 41.0 + i * 0.1)
    tracks.append(t14.finalize())

    return tracks


# ============================================================ SQL 输出


def lstr(ss: str) -> str:
    return "'" + str(ss).replace("'", "''") + "'"


def hms(clock: str) -> int:
    """'HH:MM:SS' → 当天秒数"""
    hh, mm, ss = (int(x) for x in clock.split(":"))
    return hh * 3600 + mm * 60 + ss


def fmt(value, digits: int) -> str:
    if value is None:
        return "NULL"
    return f"{value:.{digits}f}"


def linestring_wkt(points) -> str:
    return "LINESTRING(" + ",".join(f"{p['lon']:.6f} {p['lat']:.6f}" for p in points) + ")"


def check_sql_shape(sql: str) -> None:
    """生成后立刻做一次**结构自检**：外层 SELECT 的列名与 VALUES 的 `AS v(...)` 别名必须逐列一致。

    ⚠️ 这条检查是有来历的：第一版把 `v.is_outlier` 写死在 SELECT 里，而别名只在"这条轨迹
    真有漂移点"时才带上该列 ⇒ 13 条轨迹全部报「字段 v.is_outlier 不存在」，
    整份脚本在第一条 INSERT 就中止（`psql -v ON_ERROR_STOP=1` 退出码 1）。
    教训：**模板化的 SQL 必须校验「列名/列数对齐」，光看"生成成功"不算数**。
    """
    import re

    # 三份列清单必须逐列一致：① `INSERT INTO track_point (...)` 的表列名
    #   ② 外层 SELECT 里 `v.*` 的引用 ③ VALUES 的 `AS v(...)` 别名
    # 表列名与别名只有 `recorded_at` ←→ `ts` 一处不同，其余同名。
    required = {"seq", "ts", "elevation_m", "speed_mps", "lon", "lat"}
    alias_to_table = {"seq": "seq", "ts": "recorded_at", "elevation_m": "elevation_m",
                      "speed_mps": "speed_mps", "is_outlier": "is_outlier",
                      "lon": "lon", "lat": "lat"}
    blocks = re.split(r"\) AS v\(", sql)[:-1]
    aliases = [[c.strip() for c in m.group(1).split(",")]
               for m in re.finditer(r"AS v\(([^)]*)\);", sql)]
    if len(aliases) != 14 or len(blocks) != 14:
        raise ValueError(f"期望 14 条 INSERT，实际 别名 {len(aliases)} / 块 {len(blocks)}")
    for n, (block, declared) in enumerate(zip(blocks, aliases), 1):
        head = block.split("FROM ins")[0]
        insert_cols = [c.strip() for c in
                       re.search(r"INSERT INTO track_point \(([^)]*)\)", head).group(1).split(",")]
        select_line = re.search(r"SELECT ins\.id, ([^\n]+)", head).group(1)
        select_cols = re.findall(r"\bv\.([a-z_]+)", select_line)
        # ⚠️ lon / lat 只用来拼 POINT(...)，**绝不能作为独立列出现在 SELECT 里** ——
        #    出现了就会「表达式比目标字段多」。2026-09-27 就是这条断言缺失导致带病通过
        #    （旧版检查只把它们从 expect_table 里过滤掉，等于把错误一起"过滤"了）。
        if any(c in ("lon", "lat") for c in select_cols):
            raise ValueError(
                f"第 {n} 条：SELECT 把 lon/lat 当成独立列选了出来（{select_cols}）—— "
                f"它们只应出现在 ST_GeomFromText 里，否则表达式比目标字段多")
        # SELECT 必须引用【除 lon/lat 之外的全部别名】，且顺序一致
        expect_select = [c for c in declared if c not in ("lon", "lat")]
        if select_cols != expect_select:
            raise ValueError(
                f"第 {n} 条：SELECT 引用 {select_cols}，期望 {expect_select}"
                f"（别名 {declared}）—— 导入会报「字段不存在」或「字段数不匹配」")
        expect_table = (["track_id"]
                        + [alias_to_table[c] for c in select_cols]
                        + ["geom"])
        if insert_cols != expect_table:
            raise ValueError(
                f"第 {n} 条：INSERT 表列 {insert_cols} 与 SELECT {select_cols} 不一致"
                f"（期望 {expect_table}）")
        unknown = [c for c in declared if c not in alias_to_table]
        if unknown:
            raise ValueError(f"第 {n} 条别名里有未登记映射的列 {unknown}")
        not_required = required - set(declared)
        if not_required:
            raise ValueError(f"第 {n} 条别名缺少必需列 {sorted(not_required)}")
        first_row = re.search(r"FROM ins, \(VALUES\n  \((.*?)\),\n", block + "\n", re.S)
        if first_row:
            n_vals = len(first_row.group(1).split(", "))
            if n_vals != len(declared):
                raise ValueError(
                    f"第 {n} 条：VALUES 有 {n_vals} 列，别名声明了 {len(declared)} 列：{declared}")

    # ⚠️ 裸 NULL 的坑（2026-09-27 实测）：VALUES 里某一列**全是 NULL** 时，PostgreSQL 会把
    #    该列推断成 text，插进 double precision 直接报「表达式的类型为 text」。
    #    所以生成物里不允许出现裸 NULL —— 必须写成 `NULL::double precision`。
    bare = re.search(r"[(,]\s*NULL\s*[,)]", sql)
    if bare:
        raise ValueError(
            f"生成的 SQL 里有裸 NULL（偏移 {bare.start()}）—— 全 NULL 的列会被推断成 text，"
            "插进 double precision 会报「表达式的类型为 text」；请改成 NULL::double precision")


def demo_box(tracks, index: int = 13):
    """给 #13 算一个"用户拉框"示例矩形（包围盒外扩 10%），供「圈选」档演示用"""
    pts = tracks[index - 1]["points"]
    west, east = min(p["lon"] for p in pts), max(p["lon"] for p in pts)
    south, north = min(p["lat"] for p in pts), max(p["lat"] for p in pts)
    pad_lon = (east - west) * 0.1
    pad_lat = (north - south) * 0.1
    return west - pad_lon, east + pad_lon, south - pad_lat, north + pad_lat


def build_sql(tracks: list, total_points: int) -> str:
    stamp = "2026-09-01 ~ 2026-09-07"
    banner = [
        r"\encoding UTF8",
        "-- ============================================================================",
        "-- Calcite 演示数据集（M4 · Task 4）—— 14 条**合成**轨迹",
        "--",
        "-- ⚠️ 本文件由 `scripts/demo/make-demo-data.py` 生成，请勿手改；",
        "--    要改内容请改脚本后重新生成（固定随机种子，两次输出字节一致）。",
        "--",
        "-- 用途：导入后让五个分析面板都有东西看",
        "--   （停留点 / 热点 / 密度 / 相似 / 圈选）。唯一 KPI 就是这个，不是数据的真实性。",
        "-- 数据：坐标落在北京真实地标附近（五道口 / 中关村 / 天安门 / 望京 / CBD / 什刹海 / 奥林匹克公园），",
        "--       但轨迹是**合成的**，时间戳固定在 " + stamp + "（过去时间，可重复）。",
        "-- 幂等：开头 DELETE 掉全部 DEMO-* 再重插 —— 连跑两次结果一致；",
        "--       与 02-sample-track.sql 的 SAMPLE-001 互不干扰。",
        "--",
        "-- 导入：psql -U postgres -d calcite -f scripts/db/04-demo-data.sql",
        "--",
        "-- 派生列口径与真实导入器完全一致（见脚本头部对照表）：",
        "--   速度 = 到前一点的 Haversine 距离 ÷ 时间差（第 0 点为 NULL）",
        "--   漂移 = 速度 > max(8 m/s, 3 × 该轨迹速度中位数) 的段**两端**",
        "--   海拔 = 整条全同（含全 NULL）时全部置 NULL",
        "--   总距离 = Haversine 逐段求和（与 TrackCleaner 一致，不是 ST_Length）",
        "-- ============================================================================",
        "",
        r"\echo ''",
        r"\echo '########## 0) 清理旧的演示数据（DEMO-*）##########'",
        "DELETE FROM track WHERE external_id LIKE 'DEMO-%';",
        "",
        r"\echo ''",
        r"\echo '########## 1) 轨迹元数据 ##########'",
        "",
    ]

    chunks = list(banner)
    for t in tracks:
        pts = t["points"]
        coords = ",".join(f"({p['lon']:.6f} {p['lat']:.6f})" for p in pts)
        chunks.append(f"-- #{t['index']:02d} {t['name']}")
        chunks.append(f"--      external_id = {t['landmarks'][0]} / "
                      f"{len(pts)} 点 / {t['distance_m']:.1f} m / {t['duration_s']} s")
        chunks.append("WITH ins AS (")
        chunks.append("  INSERT INTO track (name, source, external_id, start_time, end_time,")
        chunks.append("                     distance_m, duration_s, point_count, geom)")
        chunks.append("  VALUES (")
        chunks.append(f"    {lstr(t['name'])}, 'demo', {lstr(t['landmarks'][0])},")
        chunks.append(f"    TIMESTAMPTZ '{BASE_DATETIME}{TZ}' + INTERVAL '{pts[0]['sec']} seconds',")
        chunks.append(f"    TIMESTAMPTZ '{BASE_DATETIME}{TZ}' + INTERVAL '{pts[-1]['sec']} seconds',")
        chunks.append(f"    {fmt(t['distance_m'], 2)}, {t['duration_s']}, {len(pts)},")
        chunks.append(f"    ST_GeomFromText('{linestring_wkt(pts)}', 4326)")
        chunks.append("  ) RETURNING id")
        chunks.append(")")
        keep_ele = t["has_elevation"]
        keep_out = t["has_outliers"]
        # ⚠️ INSERT 的列清单、外层 SELECT 的列、下面的 `AS v(...)` 别名 —— **三者必须逐列对齐**。
        # 这里连着踩了三次同一个坑（每次都是"只改了一处"）：
        #   ① 第一版把 `v.is_outlier` 写死在 SELECT 里，而别名只在"真有漂移点"时才带该列
        #      ⇒ 13 条轨迹报「字段 v.is_outlier 不存在」；
        #   ② 补上①之后，INSERT 的列清单仍写死 7 列、别名只有 6 列
        #      ⇒ 报「INSERT 的指定字段数多于表达式」；
        #   ③ ②之后 INSERT 的列清单直接复用了别名（`ts` 是别名，表里叫 `recorded_at`）
        #      ⇒ 报「关系 track_point 的 ts 字段不存在」。
        # 所以现在**只写一份** `vcols`（别名），表列名从它映射出来；生成后还有
        # check_sql_shape() 兜底，三处任何一处不同步都会在写文件前就报错。
        vcols = ["seq", "ts", "elevation_m", "speed_mps"]
        if keep_out:
            vcols.append("is_outlier")
        vcols += ["lon", "lat"]
        table_cols = ["seq", "recorded_at", "elevation_m", "speed_mps"]
        if keep_out:
            table_cols.append("is_outlier")
        chunks.append("INSERT INTO track_point (track_id, " + ", ".join(table_cols) + ", geom)")
        # ⚠️ 只选【真的是 track_point 列】的那些 vcol：`lon`/`lat` 只用来拼下面的 POINT(...)，
        #    绝不能当成独立列选出来 —— 否则表达式比目标字段多，psql 直接报
        #    「INSERT 的表达式多于指定的字段数」（2026-09-27 实测踩到）。
        sel_cols = [c for c in vcols if c not in ("lon", "lat")]
        chunks.append("SELECT ins.id, " + ", ".join("v." + c for c in sel_cols) + ",")
        chunks.append("       ST_GeomFromText('POINT(' || v.lon || ' ' || v.lat || ')', 4326)")
        chunks.append("FROM ins, (VALUES")

        rows = []
        for i, p in enumerate(pts):
            # ⚠️ 裸 NULL 会让 PostgreSQL 把**整列**推断成 text（VALUES 里该列全是 NULL 时），
            #    插进 double precision 列直接报「表达式的类型为 text」。
            #    所以一律写成带类型转换的 NULL::double precision（2026-09-27 实测踩到）。
            parts = [str(i),
                     f"TIMESTAMPTZ '{BASE_DATETIME}{TZ}' + INTERVAL '{p['sec']} seconds'",
                     fmt(p["ele"], 2) if keep_ele else "NULL::double precision",
                     fmt(t["speeds"][i], 3) if t["speeds"][i] is not None else "NULL::double precision"]
            if keep_out:
                parts.append("true" if t["outliers"][i] else "false")
            parts.append(f"{p['lon']:.6f}")
            parts.append(f"{p['lat']:.6f}")
            rows.append("  (" + ", ".join(parts) + ")")
        chunks.append(",\n".join(rows))
        chunks.append(") AS v(" + ", ".join(vcols) + ");")
        chunks.append("")

    chunks.extend([
        r"\echo ''",
        r"\echo '########## 2) 验收：演示轨迹概览 ##########'",
        "SELECT external_id, name, point_count,",
        "       round(distance_m::numeric, 1) AS 距离米,",
        "       duration_s                    AS 时长秒,",
        "       count(*) FILTER (WHERE p.is_outlier) AS 漂移点,",
        "       count(p.elevation_m)          AS 有海拔点数",
        "FROM track t JOIN track_point p ON p.track_id = t.id",
        "WHERE t.external_id LIKE 'DEMO-%'",
        "GROUP BY external_id, name, point_count, distance_m, duration_s",
        "ORDER BY external_id;",
        "",
        r"\echo ''",
        r"\echo '########## 3) 验收：五档各自应当非空 ##########'",
        "-- 停留点：至少 #1、#9~#12 有段，环湖跑（#3）诚实地是 0 段",
        "SELECT count(*) AS 演示轨迹数,",
        "       sum(point_count) AS 演示点数",
        "FROM track WHERE external_id LIKE 'DEMO-%';",
        "",
        "-- 圈选示例（#13 的包围盒外扩 10%）：",
        "--     lon {:.4f} ~ {:.4f} / lat {:.4f} ~ {:.4f}".format(*demo_box(tracks)),
        "--     在前端「圈选」档拉这个框即可命中 #13（穿越 CBD 走廊）。",
        r"\echo '圈选示例：#13 的包围盒外扩 10%（见文件末尾注释）'",
        r"\echo ''",
    ])
    return "\n".join(chunks) + "\n"


# ============================================================ 自检 + 主流程


def crosstab(rows, cell_deg: float):
    """把 (lon, lat) 落到网格里，返回 ASCII 密度图（确认"有格子 ≥3 条轨迹"）"""
    if not rows:
        return []
    grid: dict = {}
    for lon, lat in rows:
        k = (int(math.floor(lon / cell_deg)), int(math.floor(lat / cell_deg)))
        grid[k] = grid.get(k, 0) + 1
    xs = sorted(x for x, _ in grid)
    ys = sorted(y for _, y in grid)
    out = []
    for y in reversed(ys):
        out.append("".join(str(min(grid.get((x, y), 0), 9)) if grid.get((x, y)) else "."
                           for x in range(xs[0], xs[-1] + 1)))
    return out


def self_check(tracks: list) -> str:
    lines = []
    total_points = sum(len(t["points"]) for t in tracks)
    lo = min(p["sec"] for t in tracks for p in t["points"])
    hi = max(p["sec"] for t in tracks for p in t["points"])
    lines.append("=" * 96)
    lines.append("演示数据集自检（离线复刻 StayPointService / HotspotService / SimilarityMath）")
    lines.append("=" * 96)
    lines.append(f"{'#':>3} {'external_id':<10} {'点数':>6} {'距离m':>9} {'时长s':>6} "
                 f"{'停留':>4} {'漂移':>4} {'海拔':>4}  说明")
    lines.append("-" * 96)

    all_stays = []
    failures = []
    for t in tracks:
        stays = detect_stays(t["points"])
        for s in stays:
            all_stays.append({"track": t["index"], "center": s["center"],
                              "duration_s": s["duration_s"]})
        n_out = sum(1 for b in t["outliers"] if b)
        lines.append(f"{t['index']:>3} {t['landmarks'][0]:<10} {len(t['points']):>6} "
                     f"{t['distance_m']:>9.1f} {t['duration_s']:>6} {len(stays):>4} "
                     f"{n_out:>4} {'有' if t['has_elevation'] else 'NULL':>4}  "
                     f"{t['name']}（阈值 {t['threshold_mps']:.2f} m/s）")
        if t["index"] in (1, 9, 10, 11, 12) and not stays:
            failures.append(f"#{t['index']} 期望有停留点，实际 0")
        if t["index"] == 3 and stays:
            failures.append(f"#3 期望 0 个停留点（诚实为 0 是验收项），实际 {len(stays)}")
        if t["index"] == 4 and n_out < 4:
            failures.append(f"#4 期望 ≥4 个漂移点（3 处尖刺各自标两端），实际 {n_out}")
        if t["index"] not in (4,) and n_out:
            failures.append(f"#{t['index']} 不该有漂移点（清洗器把假速度尖刺标出来了），实际 {n_out}")
        if t["index"] in WITH_ELEVATION and not t["has_elevation"]:
            failures.append(f"#{t['index']} 期望有海拔，实际全 NULL")
        if t["index"] in NO_ELEVATION and t["has_elevation"]:
            failures.append(f"#{t['index']} 期望「无海拔」（模拟传感器不记录海拔），实际有海拔")

    lines.append("-" * 96)
    lines.append(f"轨迹 {len(tracks)} 条 / 总点数 {total_points} / 停留段 {len(all_stays)}")
    lines.append("")

    hotspots = cluster_hotspots(all_stays)
    lines.append(f"热点（半径 {HOTSPOT_RADIUS_M:.0f} m / min-visits {HOTSPOT_MIN_VISITS}）：{len(hotspots)} 个")
    for i, h in enumerate(hotspots, 1):
        lines.append(f"  #{i} 中心 {h['center'][1]:.6f},{h['center'][0]:.6f}  "
                     f"访问 {h['visits']} 次 / 轨迹 {h['trackCount']} 条 / "
                     f"累计 {h['duration_s']} s / 来自 {h['tracks']}")
    if len(hotspots) < 2:
        failures.append(f"期望 ≥2 个热点，实际 {len(hotspots)}")
    if not any(h["trackCount"] >= 3 for h in hotspots):
        failures.append("期望有 trackCount ≥ 3 的热点")

    sim = similarity_pct(tracks[0]["points"], tracks[1]["points"])
    lines.append("")
    lines.append(f"相似度：DEMO-001 ↔ DEMO-002 = {sim:.1f}%（容差 {SIM_TOLERANCE_M:.0f} m，"
                 f"取 min(正向, 反向)）")
    if sim < 60.0:
        failures.append(f"期望 #1↔#2 ≥60%，实际 {sim:.1f}%")
    worst = max(similarity_pct(tracks[0]["points"], t["points"])
                for t in tracks[2:])
    lines.append(f"        对照：DEMO-001 与其它轨迹的最好成绩 = {worst:.1f}%"
                 f"（其它轨迹理应明显更不相似）")

    cells = []
    for t in tracks:
        cells.extend((p["lon"], p["lat"]) for p in t["points"])
    lines.append("")
    lines.append("密度自检：每格有多少个点（格边长 0.01° ≈ 1.1 km；"
                 "前端默认档 0.002° 更细，这里只为了用 ASCII 看轮廓）")
    for row in crosstab(cells, 0.01):
        lines.append("  " + row)
    dens = None
    # 密度档口径复刻：后端用 round(ST_X/cell) 分桶、count(DISTINCT track_id) 数轨迹条数。
    # 这里按前端默认档 0.002°（阶梯里的一档）逐条轨迹数一遍，确认"真有格子 ≥3 条"。
    for cell in (0.002, 0.01):
        buckets: dict = {}
        for t in tracks:
            for lon, lat in {(p["lon"], p["lat"]) for p in t["points"]}:
                k = (int(math.floor(lon / cell)), int(math.floor(lat / cell)))
                buckets.setdefault(k, set()).add(t["index"])
        richest = max((len(v) for v in buckets.values()), default=0)
        lines.append(f"          {cell:g}° 档：{len(buckets)} 个格子，最热闹的一格 "
                     f"{richest} 条轨迹")
        if cell == 0.002:
            if not buckets:
                failures.append("0.002° 密度档没有任何格子")
            if richest < 3:
                failures.append(f"0.002° 档最热闹的格子只有 {richest} 条轨迹，期望 ≥3")

    # 圈选档：用 #13 的包围盒外扩 10% 当作"用户拉的框"，数一下有几条轨迹落在里面
    west, east, south, north = demo_box(tracks, 13)
    in_box = 0
    inside_pts = 0
    for t in tracks:
        hit = [p for p in t["points"]
               if west <= p["lon"] <= east and south <= p["lat"] <= north]
        if hit:
            in_box += 1
            inside_pts += len(hit)
    lines.append("")
    lines.append(f"圈选示例框：lon {west:.4f} ~ {east:.4f} / lat {south:.4f} ~ {north:.4f}"
                 f"（#13 的包围盒外扩 10%，脚本已写进 SQL 注释）")
    lines.append(f"          命中 {in_box} 条轨迹 / 区域内 {inside_pts} 个点")
    if in_box < 1 or inside_pts < 1:
        failures.append(f"圈选示例框内应当有轨迹与点，实际 {in_box} 条 / {inside_pts} 点")
    lines.append("")
    lines.append(f"⏱ 演示时长：整批数据落在 2026-09-01 之后 {(BASE_SEC + lo) / 86400:.2f} ~ "
                 f"{(BASE_SEC + hi) / 86400:.2f} 天"
                 f"（第 {BASE_SEC + lo} ~ {BASE_SEC + hi} 秒，即 2026-09-01 起算的秒偏移）")
    if failures:
        lines.append("❌ 自检未通过：")
        for f in failures:
            lines.append("   - " + f)
    else:
        lines.append("✅ 自检通过：五档所需的关键条件全部满足")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Calcite 演示数据集 SQL")
    parser.add_argument("--out", default=None, help="输出 SQL 路径（默认 scripts/db/04-demo-data.sql）")
    parser.add_argument("--self-check", action="store_true", help="生成后离线自检并打印报告")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    out = Path(args.out) if args.out else (root / "scripts" / "db" / "04-demo-data.sql")

    rng = random.Random(SEED)
    tracks = build_tracks(rng)

    seen = set()
    for t in tracks:
        for lm in t["landmarks"]:
            if lm in seen:
                raise ValueError(f"external_id 重复：{lm}")
            seen.add(lm)
    if len(tracks) != 14:
        raise ValueError(f"期望 14 条轨迹，实际 {len(tracks)}")

    lo = min(p["sec"] for t in tracks for p in t["points"]) + BASE_SEC
    hi = max(p["sec"] for t in tracks for p in t["points"]) + BASE_SEC
    if lo < 0 or hi >= WINDOW_S:
        raise ValueError(f"时间戳超出 2026-09-01 ~ 2026-09-07 窗口：[{lo}, {hi}]")

    sql = build_sql(tracks, sum(len(t["points"]) for t in tracks))
    check_sql_shape(sql)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sql)

    buf = sql.encode("utf-8")
    print(f"已写出 {out}")
    print(f"字节数 {len(buf)}  SHA-256 {hashlib.sha256(buf).hexdigest()}")
    print(f"轨迹 {len(tracks)} 条 / 总点数 {sum(len(t['points']) for t in tracks)} / "
          f"时间跨度 2026-09-01+{lo}s ~ 2026-09-01+{hi}s（即 {lo / 86400:.3f} ~ {hi / 86400:.3f} 天）")

    if args.self_check:
        print()
        print(self_check(tracks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
