# -*- coding: utf-8 -*-
r"""停留热点功能的浏览器像素验收（共 16 项）。

基础 8 项来自 docs/superpowers/plans/2026-09-15-m2-hotspot.md 的 Task 9 原文；
其余合并了主控会话集成验收（原 .tmp/check-integration.py）在实测中抓到的回归点：

  增量 A（2 项）两个红热点的像素包围盒必须被撑开 > 600px
      —— 防的是「Cesium 的 flyTo(Rectangle) 铺满整个画布，而左侧 432px 被面板盖着」
         这个 bug：西边那个热点整好落在面板底下，屏幕上两个红热点只占 53x37px 一个团块，
         肉眼看着像"只画出了一个热点"；修好后实测宽 1028px。
         颜色判据必须只匹配热点红 #ff375f，不能把停留点橙 Color.ORANGE(255,165,0) 算进来。
  增量 B（4 项）四个视口下面板都不许溢出
      —— 防的是「热点模式比停留点模式多占 切换开关 + 提示语 + 排序工具栏 约 17px」，
         --list-min: 72px 时 1600x600 面板溢出 17px、列表被顶出下边界。
  增量 C（2 项）模式互斥用结构性判据（DOM 节点数），不用像素
      —— 像素判据会被停留点圆干扰，节点有无是硬事实。

约定：库里 25 条轨迹 → 10 个停留点 → 默认参数下正好 3 个热点
      （2 个 trackCount=3 的红热点 + 1 个黄/橙热点；默认排序第一条是 visitCount=4）。

用法（需要提权 danger-full-access，Playwright 靠命名管道通信）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-hotspots.py
"""
import asyncio
import sys

from PIL import Image
from playwright.async_api import async_playwright

# 中文 Windows 控制台默认 GBK，直接 print 中文会 UnicodeEncodeError；
# 这里强行把 stdout 切到 UTF-8，免得验收脚本自己先崩在输出上。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/hotspot-shot.png"             # 1600x900 热点模式截图（原文命名）
SHOT_STAY = ".tmp/hotspot-shot.stay.png"   # 切回停留点后的截图（原文命名）
SHOT_1366 = ".tmp/hotspot-1366x660.png"    # 矮窗口视口截图（1366x660 是上阶段抓到布局 bug 的视口）

# 判据一：宽松「橙色系」，即任务原文的判据。
# 它会同时命中停留点圆 Color.ORANGE(255,165,0)；但热点模式下两种圈互斥，
# 所以这里数到的是热点色板 #ffd60a / #ff9f0a / #ff375f。
LOOSE = lambda r, g, b: r > 190 and b < 140 and g < 220
# 判据二：严格「热点红」，只命中 #ff375f(255,55,95)。
# 停留点橙 (255,165,0)：g=165 被 g<130 排除、b=0 被 b>50 排除。
# 于是切回停留点模式下这一路数到的，只可能是没清干净的热点残留。
TIGHT_RED = lambda r, g, b: r > 200 and g < 130 and 50 < b < 170

# 量面板布局：overflowPx = 内容溢出，spillPx = 最后一个子元素越过面板下边界（视觉上被裁）
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
        spillPx: Math.round(last.bottom - pr.bottom),
        modeSwitch: rect('[data-testid="mode-switch"]'),
        hotspotList: rect('[data-testid="hotspot-list"]'),
        stayList: rect('[data-testid="stay-list"]'),
        hotspotItems: document.querySelectorAll('[data-testid="hotspot-item"]').length,
        modeOn: (el('[data-testid="mode-hotspot"]') || {}).className || '',
    };
}"""

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("  \u2713 " if ok else "  \u2717 ") + name + ("  " + detail if detail else ""))


def count_px(path, x_from, pred):
    """在 x >= x_from 的地球区域里数满足 pred 的像素数（左上角 60px 与底部 80px 排除，避开工具栏/版权）。"""
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    n = 0
    for y in range(60, h - 80):
        for x in range(x_from, w):
            if pred(*px[x, y][:3]):
                n += 1
    return n


def red_bbox(path, x_from):
    """热点红像素的 x 包围盒。用来判断两个红热点在屏幕上有没有被撑开。"""
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    xs = []
    for y in range(60, h - 80):
        for x in range(x_from, w):
            if TIGHT_RED(*px[x, y][:3]):
                xs.append(x)
    return (min(xs), max(xs), len(xs)) if xs else (0, 0, 0)


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
        await page.wait_for_selector('[data-testid="mode-hotspot"]', timeout=30000)
        await page.wait_for_timeout(4000)

        # ---- 切到热点模式，等相机 fitBounds 飞完 ----
        await page.click('[data-testid="mode-hotspot"]')
        await page.wait_for_selector('[data-testid="hotspot-item"]', timeout=30000)
        await page.wait_for_timeout(6000)

        # === 原文 1：列表正好 3 条 ===
        info = await page.evaluate(MEASURE)
        items = info["hotspotItems"]
        check("1. 热点列表正好 3 条", items == 3, "实得 " + str(items))
        print(f"      [参考] 切换开关 className = {info['modeOn']!r}")

        # === 原文 2：三个口径都在 ===
        txt = ((await page.text_content('[data-testid="hotspot-item"]')) or "").strip()
        check("2. 显示次数/轨迹数/时长三个口径",
              "次" in txt and "条轨迹" in txt and "分钟" in txt, txt[:80])

        # === 原文 3：默认按轨迹数排序，第一条应是 visitCount=4 / trackCount=3 ===
        check("3. 默认排序第一条是 4 次 3 条轨迹",
              "4 次" in txt and "3 条轨迹" in txt, txt[:60])

        # ---- 截图 1（必须趁相机还在 fitBounds 后的全景位置，点过列表就飞走了）----
        panel_right = await page.eval_on_selector(
            ".panel", "el => Math.round(el.getBoundingClientRect().right)")
        await page.screenshot(path=SHOT)
        loose_hot = count_px(SHOT, panel_right + 8, LOOSE)
        red_hot = count_px(SHOT, panel_right + 8, TIGHT_RED)

        # === 原文 4：地球上确实有热点像素（宽松橙色系，原文判据）===
        check("4. 地球上热点像素 > 200（宽松橙色系）", loose_hot > 200, "实得 " + str(loose_hot))

        # === 增量 A-1：严格只数热点红，证明 #ff375f 那两个真的画出来了 ===
        check("5. [增量A] 热点红像素 > 100（只匹配 #ff375f）", red_hot > 100, "实得 " + str(red_hot))

        # === 增量 A-2：fitBounds 遮挡回归防线（本任务最重要的一条）===
        # 两个红热点真实相距 2.12 公里。fitBounds 生效且西边那个没被面板盖住时，
        # 它们在屏幕上应被撑到 ~1000px 宽（实测修好后 1028px）；
        # bug 复现时只剩 53x37px 的单团块，这条会立刻红。
        x0, x1, n = red_bbox(SHOT, panel_right + 8)
        check("6. [增量A] 两个红热点被撑开 > 600px（fitBounds 未被面板遮挡）",
              (x1 - x0) > 600,
              f"包围盒 x[{x0}..{x1}] 宽 {x1 - x0}px，共 {n} 个红像素")

        # === 原文 5：按时长排序，第一条应该还是这条（totalDurationS 最大）===
        await page.select_option('[data-testid="hotspot-sort"]', "totalDurationS")
        await page.wait_for_timeout(800)
        txt2 = ((await page.text_content('[data-testid="hotspot-item"]')) or "").strip()
        check("7. 按时长排序后第一条仍是 29 分钟", "29 分钟" in txt2, txt2[:60])

        # === 原文 6：点一条触发相机飞行，不许报错 ===
        await page.click('[data-testid="hotspot-item"]')
        await page.wait_for_timeout(2500)
        check("8. 点击热点未报错", True)

        # === 增量 B：四个视口下面板都不许溢出 ===
        # 热点模式比停留点模式多占「切换开关 + 提示语 + 排序工具栏」约 17px，
        # 1600x600 / --list-min:72px 时列表被顶出面板下边界（实测溢出 17px）。
        print("\n--- [增量B] 各视口下面板是否溢出（数字都打出来，方便看趋势）---")
        for i, (w, h) in enumerate(((1600, 900), (1600, 600), (1366, 660), (1280, 720))):
            await page.set_viewport_size({"width": w, "height": h})
            await page.wait_for_timeout(1000)
            m = await page.evaluate(MEASURE)
            ok = m["overflowPx"] <= 0 and m["spillPx"] <= 0
            hs = m["hotspotList"]["h"] if m["hotspotList"] else "-"
            print(f"      {w}x{h}: 面板 top={m['panel']['top']} bottom={m['panel']['bottom']} "
                  f"h={m['panel']['h']} | 内容溢出={m['overflowPx']}px "
                  f"末元素越界={m['spillPx']}px | 热点列表 h={hs} "
                  f"| {'OK' if ok else '<<< 溢出'}")
            check(f"{9 + i}. [增量B] {w}x{h} 热点模式面板不溢出",
                  ok, f'overflow={m["overflowPx"]} spill={m["spillPx"]}')
            if (w, h) == (1366, 660):
                await page.screenshot(path=SHOT_1366)

        # ---- 回到 1600x900，切回停留点模式 ----
        # （像素扫描用的 panel_right / 视图宽都是 1600 下的量，必须先还原视口）
        await page.set_viewport_size({"width": VIEW_W, "height": VIEW_H})
        await page.wait_for_timeout(800)
        await page.click('[data-testid="mode-stay"]')
        await page.wait_for_timeout(2500)

        # === 增量 C：模式互斥用结构性判据，比像素硬 ===
        has_hotspot_list = await page.eval_on_selector_all(
            '[data-testid="hotspot-list"]', "els => els.length")
        has_stay_list = await page.eval_on_selector_all(
            '[data-testid="stay-list"]', "els => els.length")
        check("13. [增量C] 切回停留点后 hotspot-list 节点数为 0",
              has_hotspot_list == 0, "实得 " + str(has_hotspot_list))
        check("14. [增量C] 同时 stay-list 节点数为 1",
              has_stay_list == 1, "实得 " + str(has_stay_list))

        # === 原文 7：热点像素该消失 ===
        # 注意阈值：任务原文写 <60 太松，实测修好后残留只有 1~2px，这里收紧到 <40。
        # 只数「热点红」：停留点圆是 Color.ORANGE(g=165,b=0)，被 TIGHT_RED 排除掉了，
        # 所以这条不数停留点圆 —— 停留点数字用宽松判据单独打印做对照。
        await page.screenshot(path=SHOT_STAY)
        red_stay = count_px(SHOT_STAY, panel_right + 8, TIGHT_RED)
        loose_stay = count_px(SHOT_STAY, panel_right + 8, LOOSE)
        print(f"      [参考] 停留点模式下：宽松橙系 {loose_stay}px（这是停留点圆本身，"
              f"约 126~172px，不是残留）、热点红 {red_stay}px（这才是残留）")
        check("15. 切回停留点后热点红像素 < 40（残留归零）", red_stay < 40, "实得 " + str(red_stay))

        # === 原文 8：控制台零报错 ===
        check("16. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败（共 {len(results)} 项）")
    if failed:
        print("失败项：" + "; ".join(r[0] for r in failed))
        sys.exit(1)


asyncio.run(main())
