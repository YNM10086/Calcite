# -*- coding: utf-8 -*-
r"""抓一张「热点模式」下的前端截图，给学习文档当操作示意图用。

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\shot-hotspot-ui.py
"""
import asyncio
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1600, "height": 900})
        await pg.goto("http://localhost:5173/?track=5", wait_until="load")
        await pg.wait_for_selector('[data-testid="mode-hotspot"]', timeout=30000)
        await pg.wait_for_timeout(4000)
        await pg.click('[data-testid="mode-hotspot"]')
        await pg.wait_for_selector('[data-testid="hotspot-item"]', timeout=30000)
        await pg.wait_for_timeout(6000)
        await pg.screenshot(path=".tmp/hotspot-ui.png")

        # 顺便把要标注的元素【实测】位置存下来 —— 不要靠肉眼估，
        # 第一版就是估的，结果标注 2 飘在空白处。
        rects = await pg.evaluate(
            """() => {
                const r = (sel) => {
                    const e = document.querySelector(sel);
                    if (!e) return null;
                    const b = e.getBoundingClientRect();
                    return { x: b.x, y: b.y, w: b.width, h: b.height,
                             cx: b.x + b.width/2, cy: b.y + b.height/2 };
                };
                return {
                    viewport: [innerWidth, innerHeight],
                    modeSwitch: r('[data-testid="mode-switch"]'),
                    hotspotList: r('[data-testid="hotspot-list"]'),
                    firstItem: r('[data-testid="hotspot-item"]'),
                };
            }"""
        )
        with open(".tmp/hotspot-ui-rects.json", "w", encoding="utf-8") as fh:
            json.dump(rects, fh, ensure_ascii=False, indent=2)
        print("已保存 .tmp/hotspot-ui.png 与 .tmp/hotspot-ui-rects.json")
        print(json.dumps(rects, ensure_ascii=False))
        await b.close()


asyncio.run(main())

