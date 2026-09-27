# -*- coding: utf-8 -*-
"""探针：多边形到底能画几个顶点？（用户报告「多边形选框只能是三角形」）

判据（不依赖任何 UI 文本，直接读 **POST /api/analysis/within 的请求体**）：

    1. 点第 1/2/3 个顶点 → 必须**一个请求都不发**（还没闭合）；
    2. 点第 4 个顶点（离第 1 个顶点 120 px，远大于 CLOSE_PX=12）→
         · 正确实现：仍然**不发请求**（多边形继续长），draw-cancel 还在；
         · 「只剩三角形」缺陷：**立刻发一个请求**，且 geometry 外环只有 4 个坐标
           （3 个顶点 + 闭合点）= 一个三角形 —— 第 4 次点击被误当成「点回起点」。

只读用户看到的东西，不改任何代码。跑法（需提权）：

    cd E:\\JAVA_IDEA_package\\JAVA_Project\\Calcite
    $env:PYTHONIOENCODING='utf-8'
    & "E:\\python\\python_address\\python.exe" .tmp\\probe-polygon-triangle.py
"""
import json
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:5173"
VIEWPORT = {"width": 1600, "height": 900}

posts = []          # 每次 POST /api/analysis/within 的请求体（JSON 文本）
steps = []          # 每个动作之后：请求数 / 绘制态


def inner_ring(body):
    """从请求体里取 geometry 外环坐标数；取不到返回 None（并原样打印，便于看结构）"""
    try:
        g = json.loads(body)["geometry"]
    except Exception:
        return None
    if g.get("type") == "Polygon":
        return len(g["coordinates"][0])
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)

        def on_request(req):
            if req.method == "POST" and "/api/analysis/within" in req.url:
                try:
                    body = req.post_data
                except Exception as e:      # noqa: BLE001
                    body = f"<post_data 取不到：{e}>"
                posts.append(body)

        page.on("request", on_request)
        page.goto(URL, wait_until="load")

        for _ in range(40):                 # 最多 20 秒等轨迹列表（后端 8080 活着）
            if page.locator(".track-list .item").count() > 0:
                break
            page.wait_for_timeout(500)
        else:
            print("!! 轨迹列表 20 秒没出来 —— 先确认后端 8080 / 前端 5173 在跑")
            browser.close()
            return 2

        page.click('[data-testid="mode-within"]')
        page.wait_for_timeout(500)

        canvas = page.locator("canvas").first.bounding_box()
        panel = page.locator(".panel").bounding_box()
        if not canvas or not panel:
            print(f"!! 取不到 canvas/panel 边界框：canvas={canvas} panel={panel}")
            browser.close()
            return 2
        panel_right = panel["x"] + panel["width"]
        canvas_right = canvas["x"] + canvas["width"]
        cx = (panel_right + canvas_right) / 2.0
        cy = canvas["y"] + canvas["height"] / 2.0
        print(f"canvas={canvas}\npanel={panel}\n多边形中心点 = ({cx:.0f},{cy:.0f})")

        # 正方形四角，边长 120 px（≫ CLOSE_PX=12，绝不可能被当成「点回起点」）
        half = 60
        quad = [(cx - half, cy - half), (cx + half, cy - half),
                (cx + half, cy + half), (cx - half, cy + half)]

        page.click('[data-testid="draw-polygon"]')
        page.wait_for_timeout(300)
        print(f"\n进多边形绘制态：draw-cancel="
              f"{page.locator('[data-testid=\"draw-cancel\"]').count()}（期望 1）")

        for i, (px, py) in enumerate(quad):
            page.mouse.click(px, py)
            page.wait_for_timeout(200)
            cancel = page.locator('[data-testid="draw-cancel"]').count()
            rings = [inner_ring(b) for b in posts]
            line = (f"第 {i + 1} 次点击 ({px:.0f},{py:.0f}) → "
                    f"请求数={len(posts)}（外环坐标数={rings}）绘制态={cancel}")
            print("  " + line)
            steps.append(line)

        # 第 4 次点击之后的状态：这才是判据所在
        ring_after4 = inner_ring(posts[-1]) if posts else None
        print("\n===== 结论 =====")
        if len(posts) >= 1 and ring_after4 == 4:
            print("★ 复现「只能是三角形」：第 4 次点击（离起点 120 px，>`CLOSE_PX`）就被当成"
                  "「点回起点」闭合，请求体外环只有 4 个坐标 = 3 个顶点 + 闭合点。")
            print(f"   请求体 = {posts[-1]}")
        elif len(posts) == 0:
            print("没复现：点了 4 个顶点仍然一个请求没发（多边形还在长）。")
            page.mouse.dblclick(quad[3][0], quad[3][1])
            page.wait_for_timeout(800)
            if posts:
                print(f"   双击闭合后：请求数={len(posts)}，"
                      f"外环坐标数={inner_ring(posts[-1])}（四边形 + 双击重复点 → 期望 6）")
                print(f"   请求体 = {posts[-1]}")
            else:
                print("   双击闭合后仍然没有请求（另有问题）")
        else:
            print(f"复现了别的形态：请求数={len(posts)}，"
                  f"每次的外环坐标数={[inner_ring(b) for b in posts]}")
            for b in posts:
                print(f"   {b}")

        print(f"\n全部请求体：{posts}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
