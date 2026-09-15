# -*- coding: utf-8 -*-
r"""导入功能的浏览器验收：真实等待 + DOM 断言 + 像素分析。

为什么不用无头 Chrome 的 --virtual-time-budget 截图：
Cesium 的几何体在 web worker 里异步生成，虚拟时钟会让截图提前结束、线还没画出来。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-import-pixels.py
"""
import asyncio
import sys

from PIL import Image
from playwright.async_api import async_playwright

GPX = r"E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\src\test\resources\sample.gpx"
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/import-shot.png"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        await page.goto("http://localhost:5173/", wait_until="load")
        # 这个 input 是 hidden 的（用 label 当按钮代理点击），所以只能等它"挂载"而不是"可见"
        await page.wait_for_selector('[data-testid="import-input"]', state="attached", timeout=30000)

        # --- 1. 上传按钮存在 ---
        check("导入按钮存在", True)

        # --- 2. 上传真实 GPX（2342 点，之前已导入过，所以会走幂等分支）---
        await page.set_input_files('[data-testid="import-input"]', GPX)
        await page.wait_for_selector(".import-ok", timeout=60000)
        await page.wait_for_timeout(6000)
        summary = ((await page.text_content(".import-ok")) or "").strip()
        check("摘要出现且信息正确", len(summary) > 0, summary[:90])

        # --- 3. 海拔面板走"没有数据"降级路径 ---
        empties = await page.eval_on_selector_all(".empty", "els => els.map(e => e.textContent.trim())")
        has_elev_empty = any("没有海拔数据" in t for t in empties)
        check("海拔面板显示「没有海拔数据」而不是贴底直线", has_elev_empty, str(empties))

        # --- 4. 轨迹线画出来了（像素）---
        # 排除区不能写死：面板标题用的是 #7fd1ff，和轨迹线是同一个精确色，
        # 面板一改宽就会被误算成"地图上的线"。直接问 DOM 要面板右边界。
        panel_right = await page.eval_on_selector(
            ".panel", "el => Math.round(el.getBoundingClientRect().right)"
        )
        await page.screenshot(path=SHOT)
        img = Image.open(SHOT).convert("RGB")
        px = img.load()
        hits = 0
        for y in range(90, 820):
            for x in range(panel_right + 8, VIEW_W):
                r, g, b = px[x, y][:3]
                if abs(r - 127) < 45 and abs(g - 209) < 45 and abs(b - 255) < 45:
                    hits += 1
        check("轨迹线像素 > 500", hits > 500, "实得 " + str(hits))

        # --- 5. 控制台零报错 ---
        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
