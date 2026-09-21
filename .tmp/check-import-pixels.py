# -*- coding: utf-8 -*-
r"""导入功能的浏览器验收：真实等待 + DOM 断言 + 像素分析。

为什么不用无头 Chrome 的 --virtual-time-budget 截图：
Cesium 的几何体在 web worker 里异步生成，虚拟时钟会让截图提前结束、线还没画出来。

⚠️ 数据管理改版后本脚本相应调整（2026-09-21），**断言一条没减**，只是换了入口和读取位置：
  1. 上传入口搬进了「数据编辑」视图 —— 先点 data-testid="open-data-manager" 进管理视图，
     再看管理视图里那个 `<input type="file">`（它自己的 testid 没变，见下面的选择器）；
  2. 导入结果不再是列表下方那一行文字（承载它的旧 class 已经删掉了），
     改成 ConfirmDialog 弹窗（data-testid="confirm-dialog"，正文在 `.line` 里）；
  3. 导入成功后 App 只重拉列表（@changed → resetAnalysisState），**不再自动选中**那条轨迹。
     所以这里要显式去管理视图里点一下刚导入的那一行 —— 否则后面两条断言
     （海拔面板降级文案 / 地球上的轨迹线像素）会因为"没有选中轨迹"而必然失败，
     那是假红，不是真的回归。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-import-pixels.py
"""
import asyncio
import os
import sys

from PIL import Image
from playwright.async_api import async_playwright

GPX = r"E:\JAVA_IDEA_package\JAVA_Project\Calcite\backend\src\test\resources\sample.gpx"
# 这份 GPX 里没有 <name> 元素，后端按"文件名去掉扩展名"兜底 —— 轨迹名就是 sample。
# 从路径算出来而不是写死：换个 GPX 就不会对不上。
TRACK_NAME = os.path.splitext(os.path.basename(GPX))[0]
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

        # --- 1. 上传入口存在（先经「数据编辑」进管理视图）---
        await page.wait_for_selector('[data-testid="open-data-manager"]', timeout=30000)
        await page.click('[data-testid="open-data-manager"]')
        # 这个 input 是 hidden 的（用 label 当按钮代理点击），所以只能等它"挂载"而不是"可见"
        await page.wait_for_selector('[data-testid="import-input"]', state="attached", timeout=30000)
        check("数据编辑入口 + 上传按钮存在", True)

        # --- 2. 上传真实 GPX（2342 点，之前已导入过，所以会走幂等分支）---
        await page.set_input_files('[data-testid="import-input"]', GPX)
        # 导入结果的正文以前是列表下方那一行文字，现在改在弹窗的 .line 里
        await page.wait_for_selector('[data-testid="confirm-dialog"] .line', timeout=60000)
        lines = await page.eval_on_selector_all(
            '[data-testid="confirm-dialog"] .line', "els => els.map(e => e.textContent.trim())"
        )
        summary = " ".join([t for t in lines if t]).strip()
        # 原来只断言"摘要非空"；这里连"摘要里确实是这条轨迹"一起断言（更强，不是更弱）
        check("导入结果弹窗出现且信息正确", len(summary) > 0 and TRACK_NAME in summary, summary[:90])

        # 关掉「导入完成」弹窗（唯一的按钮就是「知道了」）
        await page.click('[data-testid="confirm-ok"]')
        await page.wait_for_selector('[data-testid="confirm-dialog"]', state="detached", timeout=10000)

        # --- 3. 显式选中刚导入的那条轨迹（导入不再自动选中，见文件头第 3 条）---
        # 先筛到「我的 GPX」（只有几条），再按名字点那一行 —— 不写死行号，
        # 以后列表顺序 / 总条数变了也不会点到别的轨迹上。
        # 改筛选会触发一次异步重拉列表，所以这里是"轮询等那一行出现"而不是固定睡一下：
        # 固定睡会在机器慢时假红（列表还没回来就去数行）。
        await page.select_option('[data-testid="source-filter"]', "gpx")
        target_row = None
        for _ in range(20):
            rows = page.locator('[data-testid="dm-row"]')
            for i in range(await rows.count()):
                row = rows.nth(i)
                name = ((await row.locator(".name").text_content()) or "").strip()
                if name == TRACK_NAME:
                    target_row = row
                    break
            if target_row is not None:
                break
            await page.wait_for_timeout(500)
        if target_row is not None:
            # 点 .name 而不是行的几何中心：行右侧还有 ✎ / 🗑 两个按钮（它们带 @click.stop），
            # 点中心有概率正好落在按钮上（那就不发 focus、也不选中轨迹）。点名字一定会冒泡到行上。
            await target_row.locator(".name").click()
        check("在管理视图里选中刚导入的轨迹", target_row is not None, TRACK_NAME)
        # Cesium 的线是 worker 异步生成的，必须真实等待（虚拟时钟会截到"线还没出来"）
        await page.wait_for_timeout(10000)

        # --- 4. 海拔面板走"没有数据"降级路径 ---
        empties = await page.eval_on_selector_all(".empty", "els => els.map(e => e.textContent.trim())")
        has_elev_empty = any("没有海拔数据" in t for t in empties)
        check("海拔面板显示「没有海拔数据」而不是贴底直线", has_elev_empty, str(empties))

        # --- 5. 轨迹线画出来了（像素）---
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

        # --- 6. 控制台零报错 ---
        check("控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败")
    if failed:
        sys.exit(1)


asyncio.run(main())
