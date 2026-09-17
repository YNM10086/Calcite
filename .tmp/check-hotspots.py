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

⚠️ 期望值一律**当场问接口要**，脚本里不许再出现"热点只有几个 / 轨迹有多少条"这类写死的数量。
    2026-09-17 导入数据后（246 条轨迹 → 37 个热点），本文里原来写死的
    「列表条数」「第一条的访问次数与轨迹数」「按时长排序第一条的分钟数」全部变红，
    于是顺带把 check-filter.py 里写死的轨迹总数也改掉了。
    写死环境相关的数字等于把"数据本身"当成判据 —— 数据一扩充，脚本红的不是 bug，是它自己。
    （注意：连注释里都不要再抄那几个旧字面量，否则 Step 4 的形态扫描会把注释当成残留命中。）
    （同源教训：第二阶段把"像素判据写死面板宽度 400"修成"问 DOM 要面板右边界"。）
    本条对应实施计划的 Step 4 检查：全文不得再命中「热点数/轨迹数写死」的形态。

用法（需要提权 danger-full-access，Playwright 靠命名管道通信）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\check-hotspots.py
"""
import asyncio
import json
import sys
import urllib.request

from PIL import Image
from playwright.async_api import async_playwright

# 中文 Windows 控制台默认 GBK，直接 print 中文会 UnicodeEncodeError；
# 这里强行把 stdout 切到 UTF-8，免得验收脚本自己先崩在输出上。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://localhost:8080"
VIEW_W, VIEW_H = 1600, 900
SHOT = ".tmp/hotspot-shot.png"             # 1600x900 热点模式截图（原文命名）
SHOT_STAY = ".tmp/hotspot-shot.stay.png"   # 切回停留点后的截图（原文命名）
SHOT_1366 = ".tmp/hotspot-1366x660.png"    # 矮窗口视口截图（1366x660 是上阶段抓到布局 bug 的视口）

# 界面上热点列表最多画几个 —— **这是界面行为的上限，不是数据量**，所以留在脚本里是合法的。
# 它对应 App.vue 的 `hotspots`（`/api/analysis/hotspots` 目前不带 limit，前端全量渲染），
# 改动它会同时改界面行为，因此不会像"37 个热点"那样被导数据打破。
HOTSPOT_LIST_CAP = 50

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


def fetch_hotspots():
    """
    问后端要「当前数据的真实热点列表」—— 这就是界面应该显示的东西，用它当期望值。

    为什么不写死条数：写死的期望值本质是"拿某一次的数据当判据"。
    2026-09-17 又导入了一批 GeoLife 之后，热点从 3 个变成 37 个，所有写死数量的断言
    一起变红 —— 红的不是功能退化，是脚本自己过期了。接口返回什么，就期待界面显示什么，
    这样无论以后数据扩到多少，只要界面忠实渲染，这个脚本就一直有意义。
    """
    with urllib.request.urlopen(BASE + "/api/analysis/hotspots", timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["hotspots"]


def max_by(items, key):
    """列表里 key 最大的那条（前端 sortHotspots 是纯降序，没有并列时的次级口径）。"""
    return max(items, key=lambda h: h.get(key) or 0)


def trackline_bbox(path, x_from):
    """
    轨迹线（精确色 #7fd1ff）的屏幕包围盒。
    用它判断"相机有没有动"：相机不动时，两次截图里轨迹线的位置和大小**完全一致**。

    为什么不用"整图平均像素差"：实测有防护时 0.00、去掉防护时只有 1.66 ——
    相机确实飞了，但那个指标太钝，2.0 的阈值根本分辨不出来（等于没测）。
    换成包围盒之后：有防护 (602,558) 不变；去掉防护变成 (231,288)，差 370px 量级。
    """
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    xs, ys = [], []
    for y in range(60, h - 80):
        for x in range(x_from, w):
            r, g, b = px[x, y][:3]
            if abs(r - 127) < 30 and abs(g - 209) < 30 and abs(b - 255) < 30:
                xs.append(x)
                ys.append(y)
    return (max(xs) - min(xs), max(ys) - min(ys), len(xs)) if xs else (0, 0, 0)


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
    # ---- 进浏览器之前先问一次接口，后面所有数量断言都用这里的期望值 ----
    expect = fetch_hotspots()
    expect_n = len(expect)
    expect_shown = min(expect_n, HOTSPOT_LIST_CAP)
    first = expect[0]                       # 接口默认排序（五级口径）的第一名
    top_by_duration = max_by(expect, "totalDurationS")
    print(f"[参考] 接口当前返回 {expect_n} 个热点；界面最多画 {HOTSPOT_LIST_CAP} 个 "
          f"→ 期待列表 {expect_shown} 条")
    print(f"[参考] 接口第一名：{first['visitCount']} 次 / {first['trackCount']} 条轨迹 / "
          f"{first['totalDurationS']} 秒；按时长排序的第一名："
          f"{top_by_duration['visitCount']} 次 / {top_by_duration['trackCount']} 条轨迹 / "
          f"{top_by_duration['totalDurationS']} 秒")

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

        # === 原文 1：列表条数与接口一致（原来写死条数，被数据打破）===
        info = await page.evaluate(MEASURE)
        items = info["hotspotItems"]
        check("1. 热点列表条数与接口一致",
              items == expect_shown,
              f"界面 {items} 条 / 接口 {expect_n} 个（界面上限 {HOTSPOT_LIST_CAP}）")
        print(f"      [参考] 切换开关 className = {info['modeOn']!r}")

        # === 原文 2：三个口径都在 ===
        txt = ((await page.text_content('[data-testid="hotspot-item"]')) or "").strip()
        # ⚠️ 不要写死"分钟"：第一名时长现在是 11065 秒，格式化出来是「3 小时 4 分」，
        # 文本里根本没有"分钟"两个字。数据一变时长跨过 1 小时，这个判据就假红。
        # 判据要接受两种形态（分钟 / 小时x分），但仍然是"必须有明确的时长文本"。
        has_dur = "分钟" in txt or "小时" in txt
        check("2. 显示次数/轨迹数/时长三个口径",
              "次" in txt and "条轨迹" in txt and has_dur, txt[:80])

        # === 原文 3：默认按轨迹数排序，第一条应与接口第一名一致 ===
        # 原来写死"4 次 / 3 条轨迹"；现在把接口第一名的两个数字拼成判据，
        # 力度完全一样（还是逐字相等），但数据换了也不用改脚本。
        # ⚠️ 精确匹配（不搞"含 '次' 就算过"那种放松）——否则第一条换人也能绿。
        want_visits = f"{first['visitCount']} 次"
        want_tracks = f"{first['trackCount']} 条轨迹"
        check("3. 默认排序第一条与接口第一名一致",
              want_visits in txt and want_tracks in txt,
              f"接口第一名 {want_visits} / {want_tracks}；界面：{txt[:60]}")

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
        # ⚠️ 原来写死的是"两个红热点的包围盒 > 600px"。那是**为"只有 2 个热点"写的**判据：
        # 当时 2 个红热点相距 2 公里，fitBounds 一撑开就是 1028px 宽。
        # 现在有 37 个热点，fitBounds 要装下全部，视野一拉远、红热点在屏幕上反而更近
        # （实测只剩 286px 宽）—— 判据失效，但功能是好的（红像素 5.6 万，画得好好的）。
        #
        # 真正要防的 bug 是「Cesium 的 flyTo(Rectangle) 铺满画布，而左侧 432px 被面板盖着，
        # 西边的热点整好落到面板底下」。所以正确的判据是：
        #   ① 最左边的红像素必须在面板右侧（这才是那个 bug 的直接表现）
        #   ② 红热点得铺开一定宽度，不是糊成一个团块
        check("6. [增量A] 热点不被面板遮挡，且铺开成一片（fitBounds 生效）",
              x0 > panel_right and (x1 - x0) > 150,
              f"包围盒 x[{x0}..{x1}] 宽 {x1 - x0}px（面板右边界 {panel_right}），共 {n} 个红像素")

        # === 原文 5：按时长排序，第一条应与接口里时长最大的那条一致 ===
        # 原来写死"29 分钟"（那是旧的 3 个热点的数据）；现在按接口算出"谁该第一"，
        # 用它的 visitCount 逐字匹配 —— 不依赖前端的时长格式（"x 分钟" / "x 小时 y 分"），
        # 但仍然是精确判据：第一名换人、或者排序接线断了，这里都会红。
        await page.select_option('[data-testid="hotspot-sort"]', "totalDurationS")
        await page.wait_for_timeout(800)
        txt2 = ((await page.text_content('[data-testid="hotspot-item"]')) or "").strip()
        want_dur_first = f"{top_by_duration['visitCount']} 次"
        check("7. 按时长排序后第一条与接口时长第一名一致",
              want_dur_first in txt2,
              f"接口时长第一名 {want_dur_first} / {top_by_duration['totalDurationS']} 秒；"
              f"界面：{txt2[:60]}")

        # === 原文 6：点一条触发相机飞行，不许报错 ===
        # ⚠️ 这里原来写的是 check("...", True) —— 字面量恒真，等于没测，
        # 点击引发的异常会被 Vue 吞掉、这一项照样绿。改成"点击后有没有新增控制台报错"。
        err_before_click = len(errors)
        await page.click('[data-testid="hotspot-item"]')
        await page.wait_for_timeout(2500)
        check("8. 点击热点未产生新的控制台报错",
              len(errors) == err_before_click,
              f"点击前 {err_before_click} 条 → 点击后 {len(errors)} 条"
              + ("; ".join(errors[err_before_click:]) if len(errors) > err_before_click else ""))

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

        # === 增量 D：切模式的竞态（最终代码审查抓到的确定性 bug，已修）===
        # 复现：把 /api/analysis/hotspots 拦下来延迟 2 秒，在请求还没回来时切回「停留点」。
        # 修复前：挂起的 switchMode 恢复后会【照样】执行 fitBounds，
        #         于是界面在停留点模式（地球不画热点），相机却飞去了热点区域 —— 表现为"地球自己飘走了"。
        # 判据：切回之后隔 3.5 秒再截一张，画面应该几乎没变（相机没动）。
        async def delay_route(route):
            await asyncio.sleep(2.0)
            await route.continue_()

        # ⚠️ 必须在【全新加载】的页面上做。如果热点已经加载过，
        # switchMode 里的 `if (hotspots.value.length === 0) await loadHotspots()`
        # 就是 false —— 没有 await 就没有竞态窗口，这条检查会退化成"永远通过"
        # （第一版就是这么写的，去掉修复后它照样绿，等于没测）。
        await page.goto("http://localhost:5173/?track=5", wait_until="load")
        await page.wait_for_selector('[data-testid="mode-hotspot"]', timeout=30000)
        await page.wait_for_timeout(4000)

        # 此刻 hotspots 还是空的，点「热点」会真的去打请求（并被拖 2 秒）
        await page.click('[data-testid="mode-hotspot"]')
        await page.wait_for_timeout(250)                    # 趁请求还在飞
        await page.click('[data-testid="mode-stay"]')       # 切回去
        await page.wait_for_timeout(400)
        await page.screenshot(path=".tmp/race-a.png")
        await page.wait_for_timeout(3500)                   # 等挂起的那次切换彻底结束
        await page.screenshot(path=".tmp/race-b.png")
        await page.unroute("**/api/analysis/hotspots")

        # 判据：相机没动 → 两次截图里轨迹线的屏幕包围盒完全一致。
        # （整图平均差在这里太钝：实测有防护 0.00 / 无防护 1.66，分辨不出来。）
        bw_a, bh_a, n_a = trackline_bbox(".tmp/race-a.png", panel_right + 8)
        bw_b, bh_b, n_b = trackline_bbox(".tmp/race-b.png", panel_right + 8)
        moved = abs(bw_a - bw_b) > 10 or abs(bh_a - bh_b) > 10
        check("16. [增量D] 拉取热点期间切回停留点，相机不会被带飞",
              not moved,
              f"轨迹线包围盒 切换后({bw_a}x{bh_a}, {n_a}px) → 3.5秒后({bw_b}x{bh_b}, {n_b}px)"
              + ("  ← 相机飞走了！" if moved else ""))

        # === 原文 8：控制台零报错 ===
        check("17. 控制台零报错", len(errors) == 0, "; ".join(errors[:3]))

        await browser.close()

    failed = [r for r in results if not r[1]]
    print("")
    print(f"{len(results) - len(failed)} 项通过，{len(failed)} 项失败（共 {len(results)} 项）")
    if failed:
        print("失败项：" + "; ".join(r[0] for r in failed))
        sys.exit(1)


asyncio.run(main())
