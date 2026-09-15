# -*- coding: utf-8 -*-
r"""停留点功能的浏览器验收。

约定：轨迹 id=5 是 GeoLife 的 20081023025304，默认参数下正好 1 段停留
（306 秒 / 活动半径 24.2 米）。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-stay-points.py
"""
import asyncio
import sys

from PIL import Image
from playwright.async_api import async_playwright

VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/stay-shot.png"
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

        await page.goto("http://localhost:5173/?track=5", wait_until="load")
        await page.wait_for_selector('[data-testid="stay-list"]', timeout=30000)
        await page.wait_for_timeout(6000)

        # --- 1. 列表里有 1 条 ---
        items = await page.eval_on_selector_all('[data-testid="stay-item"]', "els => els.length")
        check("停留点列表正好 1 条", items == 1, "实得 " + str(items))

        # --- 2. 内容含时长与半径 ---
        txt = ((await page.text_content('[data-testid="stay-item"]')) or "").strip()
        check("显示时长与活动半径", "分钟" in txt and "半径" in txt, txt[:70])

        # --- 3. 面板标题含「停留点（1 处）」 ---
        heads = await page.eval_on_selector_all("h2", "els => els.map(e => e.textContent.trim())")
        check("面板有停留点标题", any("停留点" in h for h in heads), str(heads))

        # --- 4. 橙色半透明圆画出来了（像素）---
        await page.screenshot(path=SHOT)
        img = Image.open(SHOT).convert("RGB")
        px = img.load()
        hits = 0
        for y in range(60, 820):
            for x in range(400, VIEW_W):
                r, g, b = px[x, y][:3]
                # Cesium 的 ORANGE(255,165,0) 带透明度叠在绿色底图上
                if r > 140 and 80 < g < 215 and b < 130:
                    hits += 1
        check("橙色停留圆像素 > 300", hits > 300, "实得 " + str(hits))

        # --- 5. 点一条不报错（会触发相机飞行）---
        await page.click('[data-testid="stay-item"]')
        await page.wait_for_timeout(2500)
        check("点击停留点未报错", True)

        # --- 6. 窗口拉矮后，停留点列表仍在视口内（布局 A 的核心验收）---
        await page.set_viewport_size({"width": VIEW_W, "height": 600})
        await page.wait_for_timeout(800)
        box = await page.eval_on_selector(
            '[data-testid="stay-list"]',
            "el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom} }",
        )
        check(
            "窗口拉矮到 600px 后停留点列表没被切掉",
            box["bottom"] <= 600 and box["top"] >= 0,
            f"top={box['top']:.0f} bottom={box['bottom']:.0f}",
        )

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
