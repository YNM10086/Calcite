# -*- coding: utf-8 -*-
r"""列表筛选功能的浏览器验收（共 7 项）。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-filter.py

⚠️ 期望值一律**当场问接口要**，脚本里不许再出现"共有多少条轨迹"这类写死的数量。
    2026-09-17 又导入了一批 GeoLife 之后，轨迹总数从 25 变成 246（其中 geolife 242），
    原来那句写死总数的断言就永久为假 —— 只是当时被后面一个 `or "共" in ...` 兜住了才没红，
    属于"碰巧没爆"而不是"写对了"。
    现在改成：**接口说多少条，界面就得显示多少条**（逐字相等）。
    （同源教训：第二阶段把"像素判据写死面板宽度 400"修成"问 DOM 要面板右边界"。）
    本条对应实施计划的 Step 4 检查：全文不得再命中「轨迹数写死」的形态 ——
    连注释里也不要抄旧字面量，否则形态扫描会把注释当成残留命中。
"""
import asyncio
import json
import sys
import urllib.request

from playwright.async_api import async_playwright

BASE = "http://localhost:8080"
VIEW_W, VIEW_H = 1600, 900
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def fetch_total(source=None):
    """
    问后端「当前到底有多少条轨迹」—— 这才是界面应该显示的期望值。

    为什么不写死：写死的期望值本质是"拿某一次的数据当判据"。
    2026-09-17 导入数据后总数从 25 变成 246，所有写死数量的断言一起失效；
    红的原因不是功能坏了，而是脚本过期了。接口说多少，就期待界面显示多少 ——
    以后无论扩到多少条，只要界面忠实显示总数，这个脚本就一直有意义。
    """
    url = f"{BASE}/api/tracks?limit=1"
    if source:
        url += "&source=" + source
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["total"]


async def main():
    # ---- 进浏览器之前先问一次接口，后面所有数量断言都用这里的期望值 ----
    total_now = fetch_total()
    total_geo = fetch_total("geolife")
    print(f"[参考] 接口当前轨迹总数 {total_now} 条（其中 geolife {total_geo} 条）")

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
        # 原来这条只查 "共" 在不在（等于只测了单位、没测数字）。现在逐字比对总数。
        count_text = (await page.text_content(".count") or "").strip()
        want_all = f"共 {total_now} 条"
        check("1. 默认显示的总数与接口一致", want_all in count_text,
              f"期望含 {want_all!r}，实得 {count_text!r}")

        items_all = await page.eval_on_selector_all(".item", "els => els.length")

        # --- 2. 切到 geolife，列表应只剩 geolife 的 ---
        # 原来这里写死了 "共 21"（旧数据），且用 or 兜着 —— 那个字面量永远不成立，
        # 真正生效的是 `items_geo != items_all`（只要列表渲染出来就真，判据形同虚设）。
        # 现在两条都换成接口期望值，且是逐字相等。
        await page.select_option('[data-testid="source-filter"]', "geolife")
        await page.wait_for_timeout(1500)
        count_geo = (await page.text_content(".count") or "").strip()
        items_geo = await page.eval_on_selector_all(".item", "els => els.length")
        want_geo = f"共 {total_geo} 条"
        check("2. 切到 GeoLife 后总数与接口一致", want_geo in count_geo,
              f"期望含 {want_geo!r}，实得 {count_geo!r}")
        check("3. 切到 GeoLife 后列表确实换了一批",
              items_geo != items_all,
              f"全部 {items_all} 条 -> geolife {items_geo} 条（{count_geo}）")

        # --- 4. 把上限降到 20，返回条数应被限制 ---
        # 原来只判 `<= 20`（19、0 都算过）。改成"显示前 20"逐字匹配 + 节点数也得是 20。
        await page.select_option('[data-testid="limit-filter"]', "20")
        await page.wait_for_timeout(1500)
        count_lim = (await page.text_content(".count") or "").strip()
        items_lim = await page.eval_on_selector_all(".item", "els => els.length")
        check("4. 限制 20 条生效：显示前 20", "显示前 20" in count_lim,
              f"实得 {items_lim} 条（{count_lim}）")
        check("5. 限制 20 条时列表节点数一致", items_lim == 20, f"实得 {items_lim} 条")

        # --- 5. 切回全部来源 ---
        # 原来写死了旧数据的轨迹总数。现在还是逐字比对接口总数 ——
        # 力度不变（不是"含'共'就算过"），数据换了也不用改脚本。
        await page.select_option('[data-testid="source-filter"]', "")
        await page.wait_for_timeout(1500)
        count_back = (await page.text_content(".count") or "").strip()
        check("6. 切回全部来源后总数仍与接口一致", want_all in count_back,
              f"期望含 {want_all!r}，实得 {count_back!r}")

        check("7. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
