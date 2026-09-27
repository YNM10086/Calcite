# -*- coding: utf-8 -*-
"""给 M3 报告拍两张**真实截图**（写进 docs/learning/figs/，供 .md 引用后转 Word）。

两处要点：
  1. 先点列表里一条轨迹把相机飞近 —— 不然 12000 公里的初始视野下，北京 235 条轨迹只是一个小点；
  2. ⭐ 多边形这张同时是**修复轮 7 的证据**：点 5 个顶点围成五边形，
     请求体里必须是 **5 个去重顶点**（修复前第 4 次点击就会闭合，永远只能拿到三角形）。

跑法（需提权 danger-full-access，浏览器子进程靠管道通信）：

    cd E:\\JAVA_IDEA_package\\JAVA_Project\\Calcite
    $env:PYTHONIOENCODING='utf-8'
    & "E:\\python\\python_address\\python.exe" .tmp\\shot-within-report.py
"""
import json
import math
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
VIEWPORT = {"width": 1600, "height": 900}
OUT_POLY = "docs/learning/figs/fig-within-shot-polygon.png"
OUT_BUF = "docs/learning/figs/fig-within-shot-buffer.png"

posts = []

# 页面内探针：找到 CesiumGlobe 组件实例 → Viewer → 把**当前这条轨迹**的首点/中点投影成屏幕坐标。
# （页面里没有全局 Cesium，所以投影走 scene.cartesianToCanvasCoordinates；实体走 viewer.entities）
PROJ_JS = r"""
() => {
  try {
    const app = document.querySelector('#app');
    const root = app && app.__vue_app__ && app.__vue_app__._instance;
    if (!root) return { why: 'no vue root' };
    const seen = new Set(); const stack = [root]; let inst = null;
    while (stack.length) {
      const i = stack.pop();
      if (!i || seen.has(i)) continue;
      seen.add(i);
      const st = i.setupState;
      if (st && typeof st.setDrawingMode === 'function') { inst = i; break; }
      const sub = i.subTree;
      if (sub) {
        if (sub.component) stack.push(sub.component);
        const c = sub.children;
        if (Array.isArray(c)) { for (const x of c) if (x && x.component) stack.push(x.component); }
        else if (c && c.component) stack.push(c.component);
      }
    }
    if (!inst) return { why: 'no globe instance' };
    let v = inst.setupState && inst.setupState.viewer;
    if (v && v.value) v = v.value;
    if (!v || !v.scene) return { why: 'no viewer' };
    const s = v.scene;
    if (typeof s.cartesianToCanvasCoordinates !== 'function') return { why: 'no projector' };
    const bad = (id) => String(id).startsWith('within-') || String(id).startsWith('draw-preview');
    for (const e of v.entities.values) {
      const pl = e.polyline;
      if (!pl || bad(e.id)) continue;
      const arr = pl.positions && pl.positions.getValue ? pl.positions.getValue(v.clock.currentTime) : null;
      if (!arr || arr.length < 2) continue;
      const a = s.cartesianToCanvasCoordinates(arr[0]);
      const b = s.cartesianToCanvasCoordinates(arr[Math.floor(arr.length / 2)]);
      if (!a || !b) continue;
      return { ok: true, id: String(e.id), a: { x: a.x, y: a.y }, b: { x: b.x, y: b.y },
               n: arr.length };
    }
    return { why: 'no polyline entity with positions' };
  } catch (e) { return { why: 'throw: ' + e }; }
}
"""


def ring_distinct(body):
    try:
        g = json.loads(body)["geometry"]
    except Exception:                       # noqa: BLE001
        return None
    if g.get("type") == "Polygon":
        ring = g["coordinates"][0]
        return len({(round(x, 9), round(y, 9)) for x, y in ring})
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)
        page.on("request", lambda r: posts.append(r.post_data)
                if r.method == "POST" and "/api/analysis/within" in r.url else None)
        page.goto(URL, wait_until="load")

        for _ in range(40):
            if page.locator(".track-list .item").count() > 0:
                break
            page.wait_for_timeout(500)
        else:
            print("!! 轨迹列表没出来 —— 后端 8080 / 前端 5173 在跑吗")
            browser.close()
            return 2

        # 相机飞近一条轨迹（点列表第一条）
        page.locator(".track-list .item").first.click()
        page.wait_for_timeout(3500)

        canvas = page.locator("canvas").first.bounding_box()
        panel = page.locator(".panel").bounding_box()
        cx = (panel["x"] + panel["width"] + canvas["x"] + canvas["width"]) / 2
        cy = canvas["y"] + canvas["height"] / 2
        proj = page.evaluate(PROJ_JS)
        print(f"画布中心 = ({cx:.0f},{cy:.0f})；轨迹投影 = {proj}")
        # 以"轨迹首点 + 中点"的中心当锚点：这样圈出来的区域一定盖住这条轨迹
        if proj and proj.get("ok"):
            cx = (proj["a"]["x"] + proj["b"]["x"]) / 2
            cy = (proj["a"]["y"] + proj["b"]["y"]) / 2
            print(f"改用轨迹锚点 = ({cx:.0f},{cy:.0f})")

        # ---------- 截图 1：多边形选区 ----------
        page.click('[data-testid="mode-within"]')
        page.wait_for_timeout(400)
        page.click('[data-testid="draw-polygon"]')
        page.wait_for_timeout(300)
        R = 210
        # 顺时针五边形（每个点之间 ~250px，远大于 CLOSE_PX=12）
        pts = [(cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a)))
               for a in (-90, -18, 54, 126, 198)]
        for (x, y) in pts:
            page.mouse.click(x, y)
            page.wait_for_timeout(220)
        page.mouse.dblclick(pts[-1][0], pts[-1][1])     # 双击闭合（第 5 点再补两个重复点）
        page.wait_for_timeout(2500)
        poly_distinct = ring_distinct(posts[-1]) if posts else None
        stat = page.locator('[data-testid="stat-tracks"]').count()
        empty = page.locator('[data-testid="within-empty"]').count()
        print(f"多边形：请求数={len(posts)}、去重顶点数={poly_distinct}（期望 5）、"
              f"stat-tracks={stat}、within-empty={empty}、"
              f"列表条数={page.locator('[data-testid^=\"within-item-\"]').count()}")
        page.screenshot(path=OUT_POLY)
        print(f"已保存 {OUT_POLY}")

        # ---------- 截图 2：缓冲区（先清掉上一次结果）----------
        try:
            page.locator('[data-testid="draw-clear"]').first.click(timeout=3000)
        except Exception:                       # noqa: BLE001
            pass
        page.wait_for_timeout(500)
        page.click('[data-testid="mode-within"]')
        page.wait_for_timeout(300)
        for preset in ("buffer-preset-5000", "buffer-preset-1000"):
            if page.locator(f'[data-testid="{preset}"]').count() == 1:
                page.click(f'[data-testid="{preset}"]')
                break
        page.wait_for_timeout(200)
        page.click('[data-testid="draw-buffer"]')
        page.wait_for_timeout(300)
        page.mouse.click(cx, cy)                # 单击中心即以当前半径查询
        page.wait_for_timeout(2500)
        print(f"缓冲区：请求数={len(posts)}、"
              f"stat-tracks={page.locator('[data-testid=\"stat-tracks\"]').count()}、"
              f"within-empty={page.locator('[data-testid=\"within-empty\"]').count()}、"
              f"列表条数={page.locator('[data-testid^=\"within-item-\"]').count()}")
        page.screenshot(path=OUT_BUF)
        print(f"已保存 {OUT_BUF}")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
