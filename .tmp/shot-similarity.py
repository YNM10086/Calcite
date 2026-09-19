# -*- coding: utf-8 -*-
r"""抓几张相似档的截图，肉眼确认 Task 7+8 真的接起来了。

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\shot-similarity.py
"""
import asyncio
import json

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1600, "height": 900})
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))

        # ① 没选轨迹时进相似档 → 应该给提示
        await pg.goto("http://localhost:5173", wait_until="load")
        await pg.wait_for_selector('[data-testid="mode-similar"]', timeout=30000)
        await pg.wait_for_timeout(3000)
        await pg.click('[data-testid="mode-similar"]')
        await pg.wait_for_timeout(2000)
        need = await pg.query_selector('[data-testid="similarity-need-track"]')
        print("没选轨迹时的提示:", "有 OK" if need else "没有 !!")
        await pg.screenshot(path=".tmp/sim-need-track.png")

        # ② 选中 track 20 → 进相似档
        await pg.goto("http://localhost:5173/?track=20", wait_until="load")
        await pg.wait_for_selector('[data-testid="mode-similar"]', timeout=30000)
        await pg.wait_for_timeout(4000)
        await pg.click('[data-testid="mode-similar"]')
        await pg.wait_for_selector('[data-testid="similarity-list"]', timeout=30000)
        await pg.wait_for_timeout(9000)

        info = await pg.evaluate(
            """() => {
                const panel = document.querySelector('.panel');
                const pr = panel.getBoundingClientRect();
                const kids = [...panel.children];
                const last = kids[kids.length - 1].getBoundingClientRect();
                const ms = document.querySelector('.mode-switch');
                return {
                    panelRight: Math.round(pr.right),
                    overflow: panel.scrollHeight - panel.clientHeight,
                    spill: Math.round(last.bottom - pr.bottom),
                    baseline: (document.querySelector('[data-testid="similarity-baseline"]')||{}).textContent,
                    compared: (document.querySelector('[data-testid="similarity-compared"]')||{}).textContent,
                    items: document.querySelectorAll('[data-testid="similarity-item"]').length,
                    first: (document.querySelector('[data-testid="similarity-item"]')||{}).textContent,
                    modeSwitchOverflow: ms ? ms.scrollWidth - ms.clientWidth : null,
                    modeButtons: document.querySelectorAll('.mode-switch button').length,
                };
            }"""
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        await pg.screenshot(path=".tmp/sim-list.png")

        # ③ 筛选到 >=90%
        await pg.select_option('[data-testid="similarity-filter"]', "90")
        await pg.wait_for_timeout(1500)
        n90 = await pg.eval_on_selector_all('[data-testid="similarity-item"]', "els => els.length")
        print("筛到 >=90% 后条数:", n90)
        await pg.screenshot(path=".tmp/sim-filter90.png")

        print("控制台错误:", errs[:3] if errs else "无")
        await b.close()


asyncio.run(main())
