r"""曲线功能的真实浏览器验收：DOM 断言 + 像素分析。

为什么不用无头 Chrome 的 --virtual-time-budget 截图：
Cesium 的几何体在 web worker 里异步生成，虚拟时间会让截图提前结束、线还没画出来。
所以这里用 Playwright 真实等待。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-chart-pixels.py
"""
import asyncio
import re
import sys

from PIL import Image
from playwright.async_api import async_playwright

URL = "http://localhost:5173/?track=1"
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/chart-shot.png"

# 曲线所在像素带（视口高 - 186 到 视口高 - 46），避免抓到地球上的白色移动点
BAND_TOP = VIEW_H - 186
BAND_BOTTOM = VIEW_H - 46

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def count_pixels(img, predicate):
    px = img.load()
    n = 0
    for y in range(BAND_TOP, BAND_BOTTOM):
        for x in range(0, VIEW_W):
            r, g, b = px[x, y][:3]
            if predicate(r, g, b):
                n += 1
    return n


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome", headless=True, args=["--no-sandbox"]
        )
        page = await browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H})

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        await page.goto(URL, wait_until="load")
        await page.wait_for_selector('[data-testid="speed-chart"]', timeout=30000)
        await page.wait_for_timeout(3000)

        # --- 1. 两条线都画了 ---
        d_speed = await page.eval_on_selector(
            '[data-testid="chart-speed"] path.line', "el => el.getAttribute('d')"
        )
        d_elev = await page.eval_on_selector(
            '[data-testid="chart-elevation"] path.line', "el => el.getAttribute('d')"
        )
        check("速度折线路径非空", d_speed and len(d_speed) > 100, "长度 " + str(len(d_speed or "")))
        check("海拔折线路径非空", d_elev and len(d_elev) > 100, "长度 " + str(len(d_elev or "")))

        # --- 2. 时间轴有刻度 ---
        axis_labels = await page.eval_on_selector_all(
            '[data-testid="chart-axis"] text', "els => els.map(e => e.textContent.trim())"
        )
        check("时间轴有 HH:MM 刻度", len(axis_labels) >= 3, str(axis_labels))

        # --- 3. 像素判据 ---
        await page.screenshot(path=SHOT)
        img = Image.open(SHOT).convert("RGB")
        green = count_pixels(img, lambda r, g, b: g >= 180 and r <= 150 and b <= 180)
        orange = count_pixels(img, lambda r, g, b: r >= 200 and 100 <= g <= 200 and b <= 130)
        check("绿色速度线像素 > 50", green > 50, "实得 " + str(green))
        check("橙色海拔线像素 > 50", orange > 50, "实得 " + str(orange))

        # --- 4. 游标会动 ---
        x1 = await page.eval_on_selector(
            '[data-testid="chart-playhead"]', "el => Number(el.getAttribute('x1'))"
        )
        await page.click('[data-testid="play-toggle"]')
        await page.wait_for_timeout(4000)
        x2 = await page.eval_on_selector(
            '[data-testid="chart-playhead"]', "el => Number(el.getAttribute('x1'))"
        )
        check("播放 4 秒后游标移动 > 20px", abs(x2 - x1) > 20, f"{x1:.0f} → {x2:.0f}")
        await page.click('[data-testid="play-toggle"]')

        # --- 5. 点击跳转 ---
        box = await page.eval_on_selector(
            '[data-testid="chart-speed"]',
            "el => { const r = el.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height} }",
        )
        plot_w = box["w"] - 46 - 12
        click_x = box["x"] + 46 + plot_w * 0.8
        click_y = box["y"] + box["h"] / 2
        await page.mouse.click(click_x, click_y)
        await page.wait_for_timeout(500)
        clock = await page.text_content('[data-testid="clock"]')
        # 时钟文本形如 "08:09:58 / 08:20:00"（当前 / 总时长），只比前半段。
        # 点击坐标会被浏览器取整到整数像素，1542px 跨 3000 秒 → 1px ≈ 2 秒，
        # 所以留 ±3 秒容差；这不是实现精度问题，是鼠标本身没有亚像素。
        cur_text = (clock or "").split("/")[0].strip()
        hh, mm, ss = (int(v) for v in cur_text.split(":"))
        cur_sec = hh * 3600 + mm * 60 + ss
        want_sec = 8 * 3600 + 10 * 60
        check(
            "点 80% 处时钟落在 08:10:00 ±3 秒",
            abs(cur_sec - want_sec) <= 3,
            "实得 " + repr(clock),
        )

        # --- 6. 悬停读数 ---
        await page.mouse.move(click_x, click_y)
        await page.wait_for_timeout(300)
        tip = await page.text_content('[data-testid="chart-tooltip"]')
        check(
            "悬停提示含时刻/速度/海拔",
            bool(re.search(r"\d{2}:\d{2}:\d{2}", tip or ""))
            and "速度" in (tip or "")
            and "海拔" in (tip or ""),
            repr((tip or "").replace("\n", " ")),
        )

        # --- 7. 游标 + 交点不遮挡数据线 ---
        # 做法：先把游标和交点藏起来拍一张，再显示出来拍一张，比较数据线像素总数。
        # 若游标压在数据线上，藏起来之后数据线像素会明显变多。
        # 这个判据比「在游标那一列找颜色」稳健得多：后者会因为游标落在数据线很平
        # 的位置、交点又被白点盖住，而只剩几个像素，容易假通过。
        def count_data_pixels(path):
            im = Image.open(path).convert("RGB")
            return count_pixels(
                im,
                lambda r, g, b: (g >= 180 and r <= 150 and b <= 180)
                or (r >= 200 and 100 <= g <= 200 and b <= 130),
            )

        style = await page.add_style_tag(
            content=".playhead{display:none !important} .dot{display:none !important}"
        )
        await page.screenshot(path=SHOT + ".hidden.png")
        n0 = count_data_pixels(SHOT + ".hidden.png")
        await page.evaluate("el => el.remove()", style)
        await page.screenshot(path=SHOT)
        n1 = count_data_pixels(SHOT)
        ratio = (n1 / n0) if n0 else 0
        check(
            "游标+交点遮住的数据线像素 < 5%",
            n0 > 0 and ratio >= 0.95,
            f"藏起 {n0} → 显示 {n1}（保留 {ratio:.1%}）",
        )

        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
