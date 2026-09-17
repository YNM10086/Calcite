# -*- coding: utf-8 -*-
r"""验证热点模式集成后的两个风险点：

1. 面板在热点模式下会不会溢出（多了切换开关 + tip + 排序工具栏）
2. 地球上的热点圈是否真的画出来了、两种圈是否互斥

量四个视口：1600x900 / 1600x600 / 1366x660 / 1280x720。
1366x660 是上一阶段抓到布局 bug 的那个视口。

用法（需要提权 danger-full-access）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-integration.py
"""
import asyncio
import sys

from PIL import Image
from playwright.async_api import async_playwright

MEASURE = """() => {
    const panel = document.querySelector('.panel');
    const pr = panel.getBoundingClientRect();
    const kids = [...panel.children];
    const last = kids[kids.length - 1].getBoundingClientRect();
    const el = (sel) => document.querySelector(sel);
    const rect = (sel) => {
        const e = el(sel);
        if (!e) return null;
        const r = e.getBoundingClientRect();
        return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) };
    };
    return {
        viewport: [innerWidth, innerHeight],
        panel: { top: Math.round(pr.top), bottom: Math.round(pr.bottom), h: Math.round(pr.height) },
        overflowPx: panel.scrollHeight - panel.clientHeight,
        // 最后一个子元素有没有越过面板下边界（越过 = 视觉上被裁）
        spillPx: Math.round(last.bottom - pr.bottom),
        modeSwitch: rect('[data-testid="mode-switch"]'),
        hotspotList: rect('[data-testid="hotspot-list"]'),
        stayList: rect('[data-testid="stay-list"]'),
        hotspotItems: document.querySelectorAll('[data-testid="hotspot-item"]').length,
        modeOn: (el('[data-testid="mode-hotspot"]') || {}).className || '',
    };
}"""

fails = []


def check(name, ok, detail=""):
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))
    if not ok:
        fails.append(name)


def count_px(path, x_from, pred):
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    n = 0
    for y in range(60, h - 80):
        for x in range(x_from, w):
            r, g, b = px[x, y][:3]
            if pred(r, g, b):
                n += 1
    return n


def red_bbox(path, x_from):
    """热点红像素（#ff375f）的包围盒。用来判断两个红热点有没有在屏幕上被撑开。"""
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    xs = []
    for y in range(60, h - 80):
        for x in range(x_from, w):
            if TIGHT_RED(*px[x, y][:3]):
                xs.append(x)
    return (min(xs), max(xs), len(xs)) if xs else (0, 0, 0)


# 宽松「橙色系」：会同时命中停留点圆 Color.ORANGE(255,165,0)
LOOSE = lambda r, g, b: r > 190 and b < 140 and g < 220
# 只命中热点红 #ff375f(255,55,95)：g 明显低、b 不为 0。
# 停留点橙的 g=165、b=0，被这两条排除掉。
TIGHT_RED = lambda r, g, b: r > 200 and g < 130 and 50 < b < 170


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        await page.goto("http://localhost:5173/?track=5", wait_until="load")
        await page.wait_for_selector('[data-testid="mode-hotspot"]', timeout=30000)
        await page.wait_for_timeout(4000)

        # ---- 切到热点模式 ----
        await page.click('[data-testid="mode-hotspot"]')
        await page.wait_for_selector('[data-testid="hotspot-item"]', timeout=30000)
        await page.wait_for_timeout(6000)

        info = await page.evaluate(MEASURE)
        check("热点列表渲染出 3 条", info["hotspotItems"] == 3, f'实得 {info["hotspotItems"]}')
        check("切换开关处于热点档", "on" in info["modeOn"], info["modeOn"])

        panel_right = await page.eval_on_selector(
            ".panel", "el => Math.round(el.getBoundingClientRect().right)")
        await page.screenshot(path=".tmp/integ-900.png")
        loose_hot = count_px(".tmp/integ-900.png", panel_right + 8, LOOSE)
        red_hot = count_px(".tmp/integ-900.png", panel_right + 8, TIGHT_RED)
        check("热点模式下地球有热点像素（宽松橙色系）", loose_hot > 200, f"实得 {loose_hot}")
        check("热点模式下有热点红像素（#ff375f）", red_hot > 100, f"实得 {red_hot}")

        # 两个红热点（trackCount=3 那两个）真实相距 2.12 公里。
        # 如果 fitBounds 生效且没被面板遮住，它们在屏幕上应该被撑开到 ~1088px。
        # 这条是"西边热点被面板挡住"那个 bug 的回归防线。
        x0, x1, n = red_bbox(".tmp/integ-900.png", panel_right + 8)
        check("两个红热点在屏幕上被撑开（fitBounds 生效且未被面板遮挡）",
              (x1 - x0) > 600, f"包围盒 x[{x0}..{x1}] 宽 {x1 - x0}px，共 {n} 个红像素")

        print("\n--- 各视口下面板是否溢出 ---")
        for w, h in ((1600, 900), (1600, 600), (1366, 660), (1280, 720)):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(1000)
            m = await page.evaluate(MEASURE)
            ok = m["overflowPx"] <= 0 and m["spillPx"] <= 0
            print(f"  {w}x{h}: 面板 {m['panel']['top']}~{m['panel']['bottom']} "
                  f"内容溢出 {m['overflowPx']}px 末元素越界 {m['spillPx']}px "
                  f"热点列表 h={m['hotspotList']['h'] if m['hotspotList'] else '-'} "
                  f"{'OK' if ok else '<<< 溢出'}")
            check(f"{w}x{h} 热点模式面板不溢出", ok,
                  f'overflow={m["overflowPx"]} spill={m["spillPx"]}')
            if (w, h) == (1366, 660):
                await page.screenshot(path=".tmp/integ-1366.png")

        # ---- 互斥：切回停留点，热点应该彻底消失 ----
        await page.set_viewport_size({"width": 1600, "height": 900})
        await page.wait_for_timeout(800)
        await page.click('[data-testid="mode-stay"]')
        await page.wait_for_timeout(2500)

        # 判据 1（最明确）：结构性 —— 热点列表组件应该从 DOM 里消失
        has_hotspot_list = await page.eval_on_selector_all(
            '[data-testid="hotspot-list"]', "els => els.length")
        has_stay_list = await page.eval_on_selector_all(
            '[data-testid="stay-list"]', "els => els.length")
        check("切回停留点后热点列表组件已移除", has_hotspot_list == 0, f"实得 {has_hotspot_list}")
        check("切回停留点后停留点列表存在", has_stay_list == 1, f"实得 {has_stay_list}")

        # 判据 2（像素）：只看【热点红】。停留点圆是 Color.ORANGE(g=165,b=0)，
        # 被 TIGHT_RED 的 g<130 和 b>50 排除，所以这里剩下的只能是残留热点。
        await page.screenshot(path=".tmp/integ-stay.png")
        red_stay = count_px(".tmp/integ-stay.png", panel_right + 8, TIGHT_RED)
        loose_stay = count_px(".tmp/integ-stay.png", panel_right + 8, LOOSE)
        print(f"  [参考] 停留点模式下：浅橙系(含停留点圆) {loose_stay} px，"
              f"热点红 {red_stay} px")
        check("切回停留点后热点红像素基本归零", red_stay < 40, f"实得 {red_stay}")

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))
        await browser.close()

    print("")
    print(f"{'全部通过' if not fails else str(len(fails)) + ' 项失败: ' + ', '.join(fails)}")
    if fails:
        sys.exit(1)


asyncio.run(main())
