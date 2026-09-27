# -*- coding: utf-8 -*-
r"""网格密度（M2 第三阶段）的浏览器像素验收。

用法（需要提权 danger-full-access，Playwright 的浏览器子进程要管道通信）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp/check-density.py

前置条件：后端 8080 + 前端 5173 都在跑。

与实施计划 Task 9 原文的两处**必要偏离**（主控会话实测过，按原文写会假红）：

① 入口用 `http://localhost:5173/?track=5`，不是裸 URL。
   裸 URL 进页面时没有选中任何轨迹 → 相机停在全球视野 → 密度按视野挑到最粗的
   5° 档 → 整个地球只有 3 个格子（实测暖色像素 ≈2718，就是原文那条 >3000 的
   判据假红的原因）。用 `?track=5` 后 App 会 selectTrack(5)，相机飞到北京那条
   轨迹（908 点 / 经度 116.285~116.325），视野落在有数据的地方：
   0.002° 网格下实测 500+ 个格子、预计暖色像素 20 万+。

② 缩放的滚轮必须【朝着有数据的地方】滚，而且只滚 2~3 档。
   Cesium 的滚轮是朝鼠标位置缩的。主控在 (1100, 400) 滚 6 档滚到了海面上 ——
   那个视野确实没数据，格边长自动变成最细的 0.0001°、0 个格子，看起来像功能坏了。
   本脚本改成：先从后端取 track 5 的真实点，在**经纬度**上找最密的一小簇，再用
   运行时捕获的密度请求 bbox（就是 Cesium 当前视野）把它换算成像素，把鼠标放在
   那一簇上；滚 3 档。万一还是滚到了没数据的地方（响应里 0 个格子），会自动往回
   滚并重测，不会靠放松阈值蒙过去。

判据尽量写成**关系型**（对比两次的响应/像素，不写死"应该有多少格"）：
  - 「缩放后重新计算」→ 先看有没有发出**新的**密度请求、bbox 是否变了，
    再看响应里的格边长/格子数是否变了，最后看像素分布是否变了
  - 「时段切换生效」→ 比较切换前后的格子数/最深值 + 像素分布
  - 「口径切换生效」→ 比较「最深 = N」这个绝对刻度（轨迹数 152 ↔ 点数 14186）
  - 「切走密度档」→ 暖色像素归零
"""
import asyncio
import json
import re
import sys
import urllib.parse
import urllib.request

from PIL import Image
from playwright.async_api import async_playwright

# ⚠️ 必须带 ?track=5：见文件头 ①。没有它相机停在全球视野，密度只剩 3 个格子。
URL = "http://localhost:5173/?track=5"
TRACK_ID = 5
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/density-shot.png"
API = "http://localhost:8080"

# 「暖色系」判据：覆盖色带的黄→橙→深红，同时排除地球底色的绿/蓝。
# 用真实截图校准过：城市尺度下 500+ 个格子里约一半落在这个区间。
WARM = lambda r, g, b: r > 170 and b < 150 and r - g > 45

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def note(text):
    print("    · " + text)


def warm_px(path, x_from, y_from=60, y_to=820):
    """数暖色像素。左上角面板（x < x_from）要排除 —— 图例色条/橙色文字都在那儿。"""
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    n = 0
    for y in range(y_from, min(y_to, h)):
        for x in range(x_from, w):
            if WARM(*px[x, y][:3]):
                n += 1
    return n


def _first_int(text, pattern):
    m = re.search(pattern, text)
    return int(m.group(1).replace(",", "")) if m else None


def _first_float(text, pattern):
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


READ_DOM = """() => {
    const pick = (sel) => {
        const el = document.querySelector(sel);
        return el ? el.textContent.replace(/\\s+/g, ' ').trim() : '';
    };
    return {
        stat: pick('[data-testid="density-stat"]'),
        legend: pick('[data-testid="density-legend-bar"]'),
        // 还在转圈 / 加载失败时统计行和色条都不存在，把提示语一起带出来好定位
        hint: pick('[data-testid="density-legend"]'),
    };
}"""


async def read_density(page):
    """把面板上的密度响应读回来。

    用 evaluate 直接读 DOM 而不是 text_content：元素不存在时 text_content 要等满
    30 秒超时再抛异常，而这里应该**红一条判据并带上面板提示语**，不是崩掉。

    格子数/格边长/最深值都来自后端响应（App.vue 把 scanned/cellSize 原样传下来），
    所以它们变了 == 真的重新查过一次，不是前端自己重画。
    """
    dom = await page.evaluate(READ_DOM)
    stat, legend = dom.get("stat", ""), dom.get("legend", "")
    return {
        "stat": stat,
        "legend": legend,
        "hint": dom.get("hint", ""),
        "cells": _first_int(stat, r"([\d,]+)\s*个格子"),
        "cell": _first_float(stat, r"格边长\s*([\d.]+)\s*°"),
        "max": _first_int(legend, r"最深\s*=\s*([\d,]+)"),
    }


def fetch_track_points(track_id):
    """取真实轨迹点，用来挑「有数据的像素」当缩放锚点（见文件头 ②）。"""
    with urllib.request.urlopen(f"{API}/api/tracks/{track_id}", timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["points"]


def pick_anchor(view, points, k=6.0):
    """在经纬度上找最密的一小簇；窗口按「滚 k 档后视野缩小 k 倍」取，
    保证缩进去之后那一簇还在视野里。返回 (簇内点数, 点)。"""
    wl = view["east"] - view["west"]
    wlat = view["north"] - view["south"]
    hw, hh = wl / k / 2, wlat / k / 2
    inside = [
        p for p in points
        if view["west"] <= p["lon"] <= view["east"] and view["south"] <= p["lat"] <= view["north"]
    ]
    best_n, best = -1, None
    for p in inside:
        n = sum(1 for q in inside if abs(q["lon"] - p["lon"]) <= hw and abs(q["lat"] - p["lat"]) <= hh)
        if n > best_n:
            best_n, best = n, p
    return best_n, best


def to_pixel(view, lon, lat):
    """经纬度 → 画布像素。Cesium 的 computeViewRectangle() 给的就是整个画布的包围盒，
    城市尺度下这个线性映射足够准。"""
    fx = (lon - view["west"]) / (view["east"] - view["west"])
    fy = (view["north"] - lat) / (view["north"] - view["south"])
    return fx * VIEW_W, fy * VIEW_H


async def main():
    density_reqs = []   # 按顺序记录每一次密度请求的查询参数

    def on_request(req):
        if "/api/analysis/density" in req.url:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(req.url).query)
            density_reqs.append({k: (v[0] if v else "") for k, v in q.items()})

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})
        page.on("request", on_request)
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ---------- 入口：带 ?track=5，等相机飞到北京那条轨迹 ----------
        await page.goto(URL, wait_until="load")
        await page.wait_for_selector('[data-testid="mode-density"]', timeout=30000)
        await page.wait_for_timeout(4000)   # flyTo duration=1.5s + 渲染稳定

        panel_right = await page.eval_on_selector(
            ".panel", "el => Math.round(el.getBoundingClientRect().right)")
        x0 = panel_right + 8
        note(f"面板右边界 {panel_right}px，像素统计从 x={x0} 起")

        # 停留点档的基线（第 13 项要看"方格是否归零"）
        await page.screenshot(path=SHOT + ".stay-before.png")
        base_stay = warm_px(SHOT + ".stay-before.png", x0)
        note(f"停留点档基线暖色像素 {base_stay}")

        # ---------- 1. 切到密度档 ----------
        await page.click('[data-testid="mode-density"]')
        try:
            await page.wait_for_selector('[data-testid="density-legend-bar"]', timeout=30000)
        except Exception as e:
            # 不在这里崩：下面每条判据会红出来，并带上面板的提示语（转圈 / 加载失败）
            note(f"等图例色条超时（{type(e).__name__}），继续读面板看提示语")
        await page.wait_for_timeout(6000)
        await page.screenshot(path=SHOT)
        n1 = warm_px(SHOT, x0)
        d1 = await read_density(page)
        check("1. 切到密度档后地球出现方格", n1 > 3000,
              f"暖色像素 {n1}｜{d1['cells']} 个格子｜格边长 {d1['cell']}°"
              + (f"｜面板提示：{d1['hint']}" if not d1["stat"] else ""))

        # ---------- 2/3. 图例与统计 ----------
        check("2. 显示格子数/点数统计",
              "个格子" in d1["stat"] and "个点" in d1["stat"], d1["stat"][:70])
        bar = await page.eval_on_selector_all('[data-testid="density-legend-bar"]', "els => els.length")
        check("3. 图例色条已渲染", bar == 1, str(bar))

        # ---------- 4. 面板不溢出（四个视口）----------
        MEASURE = """() => {
            const panel = document.querySelector('.panel');
            const pr = panel.getBoundingClientRect();
            const kids = [...panel.children];
            const last = kids[kids.length - 1].getBoundingClientRect();
            return { overflow: panel.scrollHeight - panel.clientHeight,
                     spill: Math.round(last.bottom - pr.bottom) };
        }"""
        for w, h in ((1600, 900), (1600, 600), (1366, 660), (1280, 720)):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(1200)
            m = await page.evaluate(MEASURE)
            check(f"4.{w}x{h} 密度档面板不溢出", m["overflow"] <= 0 and m["spill"] <= 0,
                  f'overflow={m["overflow"]} spill={m["spill"]}')
        await page.set_viewport_size({"width": VIEW_W, "height": VIEW_H})
        await page.wait_for_timeout(2500)

        before = await read_density(page)
        await page.screenshot(path=SHOT + ".before-zoom.png")
        before["px"] = warm_px(SHOT + ".before-zoom.png", x0)
        bbox_before = density_reqs[-1].get("bbox") if density_reqs else None
        note(f"缩放前：{before['cells']} 格 / 格边长 {before['cell']}° / 暖色 {before['px']} px")
        note(f"缩放前视野 bbox = {bbox_before}")

        # ---------- 5. 朝有数据的地方滚 3 档 ----------
        anchor_view = None
        if bbox_before:
            nums = [float(v) for v in bbox_before.split(",")]
            anchor_view = {"west": nums[0], "south": nums[1], "east": nums[2], "north": nums[3]}
        mx, my = panel_right + (VIEW_W - panel_right) * 0.5, VIEW_H * 0.45   # 兜底：可见地图区中心
        if anchor_view:
            try:
                pts = fetch_track_points(TRACK_ID)
                n_cluster, best = pick_anchor(anchor_view, pts)
                if best:
                    ax, ay = to_pixel(anchor_view, best["lon"], best["lat"])
                    note(f"数据里最密的一簇：{n_cluster} 个点 @ ({best['lon']:.5f}, {best['lat']:.5f})"
                         f" → 像素 ({ax:.0f}, {ay:.0f})")
                    # 落在面板底下、或压到底部曲线区就退回兜底位置
                    if ax > panel_right + 40 and 40 < ay < VIEW_H - 250:
                        mx, my = ax, ay
                    else:
                        note(f"该簇像素 ({ax:.0f}, {ay:.0f}) 不可用（面板/曲线遮挡），改用兜底位置")
            except Exception as e:   # 后端拿不到就退回兜底位置，不让它变成假红
                note(f"取轨迹点失败（{e}），改用兜底位置")
        mx, my = min(max(mx, panel_right + 40), VIEW_W - 20), min(max(my, 40), VIEW_H - 250)
        note(f"滚轮锚点 ({mx:.0f}, {my:.0f})，滚 3 档（朝有数据的方向）")

        req_n0 = len(density_reqs)
        await page.mouse.move(mx, my)
        for _ in range(3):
            await page.mouse.wheel(0, -400)
            await page.wait_for_timeout(300)
        await page.wait_for_timeout(4500)   # 相机惯性停稳 + 400ms 防抖 + 请求
        await page.screenshot(path=SHOT + ".zoom.png")
        after = await read_density(page)
        after["px"] = warm_px(SHOT + ".zoom.png", x0)

        # 万一滚到了没数据的地方（响应里 0 个格子）→ 往回滚重测，不放松阈值。
        # 注意只在真的读到 0 时才回滚：读不到（None，面板坏了）说明是别的问题。
        recovered = 0
        while after["cells"] == 0 and recovered < 4:
            recovered += 1
            note(f"缩放后 0 个格子（视野没数据）→ 往回滚第 {recovered} 次，重测")
            await page.mouse.wheel(0, 400)
            await page.wait_for_timeout(3000)
            after = await read_density(page)
            await page.screenshot(path=SHOT + ".zoom.png")
            after["px"] = warm_px(SHOT + ".zoom.png", x0)

        zoom_reqs = density_reqs[req_n0:]
        bbox_after = zoom_reqs[-1].get("bbox") if zoom_reqs else None
        note(f"缩放后：{after['cells']} 格 / 格边长 {after['cell']}° / 暖色 {after['px']} px"
             + (f"（回滚 {recovered} 次）" if recovered else ""))
        note(f"缩放后视野 bbox = {bbox_after}")
        note(f"相机停稳后新增密度请求 {len(zoom_reqs)} 次")

        # ---------- 6. 缩放真的触发了按新视野重新查询 ----------
        new_req = len(zoom_reqs) > 0 and bbox_after and bbox_after != bbox_before
        detail5 = f"{bbox_before} → {bbox_after}（新增请求 {len(zoom_reqs)} 次）"
        if not density_reqs:
            detail5 += "｜⚠️ 全程没捕获到 /api/analysis/density 请求"
        check("5. 相机停稳后按新视野重新请求（bbox 变了）", new_req, detail5)

        # ---------- 7. 重新计算的结果确实换代了 ----------
        cell_changed = after["cell"] != before["cell"] or after["cells"] != before["cells"]
        px_delta = abs(after["px"] - before["px"])
        px_changed = px_delta > max(300, before["px"] * 0.10)
        check("6. 缩放后密度图按新视野重算（格边长/格子数变化）",
              bool(cell_changed and (after["cells"] or 0) > 0),
              f"格边长 {before['cell']}°→{after['cell']}°，格子 {before['cells']}→{after['cells']}")
        check("7. 缩放后像素分布变化", bool(px_changed and (after["cells"] or 0) > 0),
              f"暖色 {before['px']} → {after['px']}（Δ{px_delta}）")

        # ---------- ⚠️ 还原视野：缩放测试会缩过头，后面的检查必须换个干净视野做 ----------
        # 实测：Cesium 的滚轮在近处非常猛，3 档就把视野从约 9 公里缩到了 **2.2 米见方**。
        # 在那个视野上再切时段/口径，两边都是 0 个格子，"有没有变化"根本比不出来 ——
        # 于是第 9、10 项会假红（红得毫无信息）。
        # 所以这里【重新加载页面 + 重新进密度档】，把视野恢复到最初那个有数据的状态。
        note("缩放测试已完成（它证明了相机事件接线正确）；现在重载页面恢复视野，再测时段/口径")
        await page.goto("http://localhost:5173/?track=5", wait_until="load")
        await page.wait_for_selector('[data-testid="mode-density"]', timeout=30000)
        await page.wait_for_timeout(4000)
        await page.click('[data-testid="mode-density"]')
        await page.wait_for_selector('[data-testid="density-legend-bar"]', timeout=30000)
        await page.wait_for_timeout(6000)
        base = await read_density(page)
        base["px"] = warm_px(SHOT + ".reset.png", x0) if False else None
        await page.screenshot(path=SHOT + ".reset.png")
        base["px"] = warm_px(SHOT + ".reset.png", x0)
        note(f"视野已还原：{base['cells']} 格 / 格边长 {base['cell']}° / 暖色 {base['px']} px")
        after = base          # 后面的检查以"还原后的视野"为基准

        # ---------- 8. 时段切换（早高峰 7-9）----------
        await page.select_option('[data-testid="density-hour"]', "7-9")
        await page.wait_for_timeout(4500)
        await page.screenshot(path=SHOT + ".morning.png")
        morning = await read_density(page)
        morning["px"] = warm_px(SHOT + ".morning.png", x0)
        note(f"早高峰：{morning['cells']} 格 / 最深 {morning['max']} / 暖色 {morning['px']} px")
        check("8. 切到早高峰后重新查询（格子数/最深值变化）",
              morning["cells"] != after["cells"] or morning["max"] != after["max"],
              f"格子 {after['cells']}→{morning['cells']}，最深 {after['max']}→{morning['max']}")
        m_delta = abs(morning["px"] - after["px"])
        check("9. 切到早高峰后像素分布变化",
              m_delta > max(300, after["px"] * 0.10),
              f"暖色 {after['px']} → {morning['px']}（Δ{m_delta}）")

        # ---------- 9. 口径切换（按轨迹数 → 按点数）----------
        await page.select_option('[data-testid="density-hour"]', "")
        await page.wait_for_timeout(3500)
        all_day = await read_density(page)
        await page.select_option('[data-testid="density-metric"]', "points")
        await page.wait_for_timeout(4500)
        points = await read_density(page)
        note(f"全天/按轨迹数：最深 {all_day['max']}｜{all_day['legend'][-40:]}")
        note(f"全天/按点数：  最深 {points['max']}｜{points['legend'][-40:]}")
        check("10. 口径切到点数后图例最深值变化（关系型）",
              points["max"] != all_day["max"] and "个点" in points["legend"],
              f"最深 {all_day['max']} → {points['max']}")

        # ---------- 10. 切走密度档 ----------
        await page.screenshot(path=SHOT + ".points.png")
        px_before_leave = warm_px(SHOT + ".points.png", x0)
        await page.click('[data-testid="mode-stay"]')
        await page.wait_for_timeout(2500)
        await page.screenshot(path=SHOT + ".stay.png")
        gone = warm_px(SHOT + ".stay.png", x0)
        check("11. 切回停留点后方格消失（暖色归零）", gone < 300,
              f"残留暖色像素 {gone}（切走前 {px_before_leave}，停留点档基线 {base_stay}）")

        check("12. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))
        await browser.close()

    print("")
    print("密度请求轨迹（bbox / cellSize / metric / hour）：")
    for i, q in enumerate(density_reqs):
        print(f"  [{i}] cellSize={q.get('cellSize')} metric={q.get('metric')} "
              f"hour={q.get('hourFrom')}-{q.get('hourTo')} bbox={q.get('bbox')}")
    print("")
    print("截图：.tmp/density-shot.png / .png.zoom.png / .png.morning.png / .png.stay.png")
    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败（共 {len(results)} 项）")
    if failed:
        print("失败项：" + "; ".join(r[0] for r in failed))
        sys.exit(1)


asyncio.run(main())
