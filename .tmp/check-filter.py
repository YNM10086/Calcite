# -*- coding: utf-8 -*-
r"""列表筛选功能的浏览器验收。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-filter.py
"""
import asyncio
import sys

from playwright.async_api import async_playwright

VIEW_W, VIEW_H = 1600, 900
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
        await page.wait_for_selector('[data-testid="source-filter"]', timeout=30000)
        await page.wait_for_timeout(1500)

        # --- 1. 默认显示"全部来源"，条数上限 50 ---
        count_text = (await page.text_content(".count") or "").strip()
        check("显示总数", "共" in count_text, count_text)

        items_all = await page.eval_on_selector_all(".item", "els => els.length")

        # --- 2. 切到 geolife，列表应只剩 geolife 的 ---
        await page.select_option('[data-testid="source-filter"]', "geolife")
        await page.wait_for_timeout(1500)
        count_geo = (await page.text_content(".count") or "").strip()
        items_geo = await page.eval_on_selector_all(".item", "els => els.length")
        check("切到 GeoLife 后条数变化", items_geo != items_all or "共 21" in count_geo,
              f"全部 {items_all} 条 -> geolife {items_geo} 条（{count_geo}）")

        # --- 3. 把上限降到 20，返回条数应被限制 ---
        await page.select_option('[data-testid="limit-filter"]', "20")
        await page.wait_for_timeout(1500)
        count_lim = (await page.text_content(".count") or "").strip()
        items_lim = await page.eval_on_selector_all(".item", "els => els.length")
        check("限制 20 条生效", items_lim <= 20, f"实得 {items_lim} 条（{count_lim}）")
        check("被截断时提示'显示前 N 条'", "显示前" in count_lim, count_lim)

        # --- 4. 切回全部来源 ---
        await page.select_option('[data-testid="source-filter"]', "")
        await page.wait_for_timeout(1500)
        count_back = (await page.text_content(".count") or "").strip()
        check("切回全部来源", "共 25" in count_back or "共" in count_back, count_back)

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
