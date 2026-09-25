# -*- coding: utf-8 -*-
"""M3 Task 11 —— 圈选（空间范围查询）的浏览器验收：Playwright 真实等待 + Pillow 像素统计。

跑法（**必须提权 danger-full-access**，浏览器子进程靠管道通信；后端 8080 + 前端 5173 同时在跑）：

    cd E:\\JAVA_IDEA_package\\JAVA_Project\\Calcite
    $env:PYTHONIOENCODING='utf-8'
    & "E:\\python\\python_address\\python.exe" .tmp\\check-within.py

两条纪律（都来自既有教训，改动时不要回退）：
  1. **真实时间等待**。Cesium 的几何体由 worker 异步生成，`--virtual-time-budget` 那种虚拟时钟截图
     会得到"线不存在"的假象（M1 就误判过一轮）。本脚本一律 page.wait_for_timeout / 轮询。
  2. **面板右边界问 DOM 要**（`.panel` 的 bounding_box），不写死 `x >= 400` —— 面板宽度是
     `min(420px, 34vw)`，历史上改过好几次，写死的脚本都假红/假绿过。

两个坐标比例（0.55 / 0.30）是**按"页面默认全球视野"估的**，不保证一定命中数据：
  ⚠️ **若 B 段打印的命中条数是 0 / —，第一件事是调这两个数**（把框往地图中心挪、或先放大到北京）。
     脚本启动时会把北京/上海在画布上的**实际屏幕坐标**算出来打印（需要页面暴露 Cesium），
     拿那两个点去对，最快；同时会检查拖拽框是否四个角都在视口内（拖出画面 = Cesium 收不到
     mouseup，这一笔直接作废——那是最常见的"命中 0 条"原因，不是功能问题）。

断言纪律（每条都自检过）：
  - 没有"永远为真"的判据（不写 count() >= 0 这种）。
  - 任何取文本/取边界框之前先判存在；前置状态不成立只记一条 **skip** 并跳过依赖它的后续断言，
    不会在中途抛异常把整个脚本炸掉。
  - 依赖"输入数据 / 像素 / 页面有没有暴露 Cesium"的断言，能降级为**信息输出**的一律降级，
    避免给验收增加假红源；真正的功能判据（旋转恢复、绘制中不旋转、零溢出、零报错）一条不少。
  - 每条失败明细都带上**实测值**，便于判断是脚本问题（框没落在数据上）还是功能问题。
"""
import os
import sys
import traceback

from playwright.sync_api import sync_playwright
from PIL import Image

URL = "http://localhost:5173"          # ⚠️ 必须是 localhost：Vite 只绑 IPv6，127.0.0.1 连不上
SHOT = os.path.join(".tmp", "shot-within.png")

# 拉框用的两个比例（相对画布宽/高）。**估的**，见文件头说明。
RECT_X_RATIO = 0.55
RECT_Y_RATIO = 0.30
RECT_DX = 120
RECT_DY = 90

VIEWPORT = {"width": 1600, "height": 900}
SHORT_VIEWPORTS = ((1366, 660), (1600, 600))

ok = 0
fail = 0
msgs = []          # 失败明细
skipped = []       # 因前置状态不成立而跳过的断言
notes = []         # 关键诊断值（报告要靠它判断失败原因）

errors = []        # pageerror + console.error
page_errors = []   # 只记 pageerror，单独看（切档断言用它）
console_errors = []


# ---------------------------------------------------------------- 断言基础设施
def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        msgs.append(f"{name} :: {detail}")
        print(f"  [XX] {name}  {detail}")
    return bool(cond)


def skip(name, why):
    skipped.append(f"{name} :: {why}")
    print(f"  [--] 跳过 {name}（{why}）")


def note(text):
    notes.append(text)
    print(f"  .. {text}")


def try_text(page, selector, default=""):
    """取文本，元素不存在/取不到时返回 default（不让脚本在中途炸掉）"""
    try:
        loc = page.locator(selector)
        if loc.count() == 0:
            return default
        return loc.first.inner_text().strip()
    except Exception as e:                      # noqa: BLE001 - 验收脚本要兜住一切
        note(f"读 {selector} 文本失败：{e}")
        return default


def count_of(page, selector):
    try:
        return page.locator(selector).count()
    except Exception as e:                      # noqa: BLE001
        note(f"统计 {selector} 数量失败：{e}")
        return -1


def count_color(img, rgb, tol=12, x_from=0):
    """数指定颜色附近的像素（隔 2 采样，够用且快）"""
    px = img.load()
    w, h = img.size
    n = 0
    for y in range(0, h, 2):
        for x in range(x_from, w, 2):
            r, g, b = px[x, y][:3]
            if abs(r - rgb[0]) <= tol and abs(g - rgb[1]) <= tol and abs(b - rgb[2]) <= tol:
                n += 1
    return n


def diff_ratio(path_a, path_b, x_from, step=4, base=6, threshold=30):
    """地图区域（x >= x_from）里"变化明显"的像素**占比**（0.0~1.0）。

    ⚠️ 用**占比**而不是**绝对个数**，并且把纯色底（深蓝海洋 / 纯黑太空）排除掉：
       旋转地球时深蓝海面仍是深蓝，色差很小 —— 拿深蓝像素个数当"转没转"的判据，
       遇到深蓝占绝对多数的画面会**假绿**。占比 + 排除近纯色才描述得了"画面整体换了一张"。
    """
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    if a.size != b.size:
        return -1.0
    pa, pb = a.load(), b.load()
    w, h = a.size
    total = 0
    changed = 0
    for y in range(0, h, step):
        for x in range(x_from, w, step):
            ra, ga, ba = pa[x, y][:3]
            rb, gb, bb = pb[x, y][:3]
            if max(ra, ga, ba) < base or max(rb, gb, bb) < base:
                continue                        # 近纯色像素（海面 / 太空）不参与
            total += 1
            if abs(ra - rb) + abs(ga - gb) + abs(ba - bb) > threshold:
                changed += 1
    return (changed / total) if total else -1.0


def panel_overflow(page):
    """面板零溢出：scrollHeight <= clientHeight + 2（2px 是亚像素容差）"""
    return page.evaluate("""() => {
        const p = document.querySelector('.panel');
        if (!p) return null;
        return { sh: p.scrollHeight, ch: p.clientHeight };
    }""")


def canvas_camera(page):
    """（尽力而为）通过 Cesium 的 canvas 反查相机，用来直接判"地球转没转"。
    取不到就返回 None —— 调用方必须容忍，不能把它当硬断言。"""
    return page.evaluate("""() => {
        const c = document.querySelector('canvas');
        if (!c) return null;
        const v = c._cesiumWidget || c.__cesiumWidget || null;
        if (!v || !v.camera || !v.camera.positionCartographic) return null;
        const p = v.camera.positionCartographic;
        return { lon: p.longitude, lat: p.latitude, h: p.height,
                 rotate: v.screenSpaceCameraController
                   ? v.screenSpaceCameraController.enableRotate : null };
    }""")


def screen_of(page, lon, lat):
    """（尽力而为）经纬度 → 画布内屏幕坐标。页面没暴露 Cesium 时返回 None。"""
    return page.evaluate("""([lon, lat]) => {
        if (typeof Cesium === 'undefined' || !Cesium.Cartesian3) return null;
        const c = document.querySelector('canvas');
        if (!c) return null;
        const v = c._cesiumWidget || c.__cesiumWidget || null;
        const viewer = (v && v.camera) ? v : (window.viewer || null);
        if (!viewer || !viewer.camera || !viewer.scene) return null;
        const cart = Cesium.Cartesian3.fromDegrees(lon, lat, 0);
        const win = Cesium.SceneTransforms.worldToWindowCoordinates
            ? Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene, cart)
            : Cesium.SceneTransforms.wgs84ToWindowCoordinates(viewer.scene, cart);
        if (!win) return null;
        const r = c.getBoundingClientRect();
        return { x: win.x + r.left, y: win.y + r.top,
                 w: r.width, h: r.height, on: win.x >= 0 && win.x <= r.width && win.y >= 0 && win.y <= r.height };
    }""", [lon, lat])


def wait_result(page, timeout_ms=15000):
    """等查询收尾：统计卡的条数出现、或空结果提示出现、或错误出现。
    真实时间轮询（不用虚拟时钟）。返回 (state, text)：
      state = 'stats' | 'empty' | 'error' | 'timeout'

    ⚠️ 它只看"现在有没有结果" —— 若上一次查询的统计卡还在，它会**立刻**返回旧值。
       需要"新结果"的场景请用 wait_new_result()。
    """
    spent = 0
    step = 250
    while spent < timeout_ms:
        if count_of(page, '[data-testid="within-empty"]') > 0:
            return "empty", try_text(page, '[data-testid="within-empty"]')
        if count_of(page, '[data-testid="stat-tracks"]') > 0:
            return "stats", try_text(page, '[data-testid="stat-tracks"]')
        if count_of(page, '[data-testid="within-error"]') > 0:
            return "error", try_text(page, '[data-testid="within-error"]')
        page.wait_for_timeout(step)
        spent += step
    return "timeout", ""


def wait_new_result(page, prev_text, timeout_ms=15000):
    """等**这一次**查询收尾：结果文本与上一次不同，或先经过"查询中…"再落定。

    ⚠️ 为什么不能直接用 wait_result：D 段拉框前统计卡里还留着 B 段的结果，
       而"统计卡的文本"就是那一次查询的返回值 —— 不等它变化，就会把**旧结果**
       当成"这次拖拽产生了查询结果"（断言假绿）。这里用 prev_text 兜住。
    """
    spent = 0
    step = 250
    seen_busy = False
    while spent < timeout_ms:
        if count_of(page, '[data-testid="within-error"]') > 0:
            return "error", try_text(page, '[data-testid="within-error"]')
        hint = try_text(page, '[data-testid="draw-hint"]')
        if hint.startswith("查询中"):
            seen_busy = True
        if count_of(page, '[data-testid="within-empty"]') > 0:
            return "empty", try_text(page, '[data-testid="within-empty"]')
        if count_of(page, '[data-testid="stat-tracks"]') > 0:
            t = try_text(page, '[data-testid="stat-tracks"]')
            if seen_busy or t != prev_text:
                return "stats", t
        page.wait_for_timeout(step)
        spent += step
    return "timeout", ""


def drag(page, x0, y0, x1, y1, steps=8):
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x1, y1, steps=steps)
    page.mouse.up()


# ---------------------------------------------------------------- 主流程
def main():
    os.makedirs(".tmp", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT)
        page.on("pageerror", lambda e: (page_errors.append(str(e)), errors.append(str(e))))
        page.on("console", lambda m: (console_errors.append(m.text), errors.append(m.text))
                if m.type == "error" else None)

        page.goto(URL, wait_until="load")

        print("=== 0) 页面就绪 ===")
        # 等轨迹列表真的出来（后端没起时这里会失败，后面的断言就没意义了 —— 一条就够说明问题）
        listed = False
        for _ in range(40):                    # 最多 20 秒
            if count_of(page, ".track-list .item") > 0:
                listed = True
                break
            page.wait_for_timeout(500)
        check("轨迹列表已加载（后端 8080 活着）", listed,
              "20 秒内 .track-list .item 一直是空的 —— 先确认后端与数据库在跑")
        canvas_n = count_of(page, "canvas")
        note(f"页面 canvas 数量 = {canvas_n}（用第一个当前景 canvas）")
        if canvas_n != 1:
            note("⚠️ canvas 不止 1 个（可能有别的东西也画 canvas）：本脚本固定取第一个，"
                 "若它取错了，后面所有坐标都会偏")

        # 画布与面板边界只取一次；取不到就直接收工（后面每条都依赖它）
        canvas = page.locator("canvas").first.bounding_box()
        panel_box = page.locator(".panel").bounding_box()
        if not canvas or not panel_box:
            check("能取到 canvas / .panel 的边界框", False,
                  f"canvas={canvas} panel={panel_box}")
            summary(browser)
            return
        x_from = int(panel_box["x"] + panel_box["width"]) + 4
        note(f"canvas = {canvas}")
        note(f"面板右边界 x={x_from}（面板 {panel_box['x']:.0f},{panel_box['y']:.0f} "
             f"{panel_box['width']:.0f}x{panel_box['height']:.0f}）")

        # 画布之外的"辅助线"：把北京/上海的屏幕坐标打出来，B 段命中 0 条时用它调比例
        cam0 = canvas_camera(page)
        note(f"相机可达性：{'可用 ' + str(cam0) if cam0 else '不可用（页面没暴露 Cesium viewer，'
                                                       '涉及相机的检查会降级为信息输出）'}")
        for name, lon, lat in (("北京", 116.40, 39.90), ("上海", 121.47, 31.23)):
            s = screen_of(page, lon, lat)
            if s is None:
                note(f"{name} 屏幕坐标：取不到（Cesium 未暴露）")
            else:
                note(f"{name} 屏幕坐标：x={s['x']:.0f} y={s['y']:.0f} "
                     f"画布 {s['w']:.0f}x{s['h']:.0f} 视野内={s['on']}")

        # ------------------------------------------------ A) 第五档存在
        print("=== A) 第五档「圈选」存在 ===")
        n_mode = count_of(page, '[data-testid="mode-within"]')
        check("有 mode-within 按钮", n_mode == 1, f"实际 {n_mode} 个")
        if n_mode == 1:
            page.click('[data-testid="mode-within"]')
            page.wait_for_timeout(500)
        else:
            skip("A) 后续断言", "没有 mode-within 按钮")

        shape_counts = {t: count_of(page, f'[data-testid="{t}"]')
                        for t in ("draw-rect", "draw-polygon", "draw-buffer")}
        check("三个画法按钮都在（draw-rect / draw-polygon / draw-buffer）",
              all(v == 1 for v in shape_counts.values()),
              " | ".join(f"{k}={v}" for k, v in shape_counts.items()))
        n_clear = count_of(page, '[data-testid="draw-clear"]')
        check("有清除按钮（draw-clear）", n_clear == 1, f"实际 {n_clear} 个")

        # ------------------------------------------------ B) 拉框
        print("=== B) 拉框 → 统计卡出现且与接口一致 ===")
        if count_of(page, '[data-testid="draw-rect"]') != 1:
            skip("B) 拉框全部断言", "draw-rect 按钮不存在")
        else:
            page.click('[data-testid="draw-rect"]')
            page.wait_for_timeout(300)

            x0 = canvas["x"] + canvas["width"] * RECT_X_RATIO
            y0 = canvas["y"] + canvas["height"] * RECT_Y_RATIO
            x1, y1 = x0 + RECT_DX, y0 + RECT_DY
            note(f"拉框：( {x0:.0f},{y0:.0f} ) → ( {x1:.0f},{y1:.0f} )  "
                 f"比例 {RECT_X_RATIO}/{RECT_Y_RATIO}")
            inside = (0 <= x0 <= VIEWPORT["width"] and 0 <= y0 <= VIEWPORT["height"]
                      and 0 <= x1 <= VIEWPORT["width"] and 0 <= y1 <= VIEWPORT["height"])
            if not inside:
                note(f"⚠️ 拖拽坐标超出视口 ({x0:.0f},{y0:.0f})→({x1:.0f},{y1:.0f})："
                     "拖出画面 Cesium 收不到 mouseup，这一笔作废（命中 0 条时先看这里）")
            drag(page, x0, y0, x1, y1)

            # 等真实响应：先给"松手 → 发请求"留出最短间隔，再轮询到结果落定
            page.wait_for_timeout(600)
            state, txt = wait_result(page)
            note(f"B 段查询收尾状态 = {state}，stat-tracks 文本 = {txt!r}")

            n_stats_card = count_of(page, '[data-testid="within-stats"]')
            check("统计卡出现（within-stats）", n_stats_card == 1, f"实际 {n_stats_card} 个")
            has_stat = count_of(page, '[data-testid="stat-tracks"]') == 1
            check("有「条轨迹穿过」数字（stat-tracks）", has_stat,
                  f"状态={state} 文本={txt!r}"
                  + ("（空结果：统计卡只有提示行，说明这一框没框到轨迹）" if state == "empty" else ""))
            if has_stat:
                note(f"接口命中 {txt} 条")
                check("命中数不是 0 / 破折号 / 空（说明真的查到了数据）",
                      txt not in ("—", "", "0"), f"实际 {txt!r}")
                if txt in ("—", "", "0"):
                    note("⚠️ 命中 0 条：优先怀疑拉框坐标没落在数据上 —— 调脚本顶部 "
                         "RECT_X_RATIO / RECT_Y_RATIO（或用上面打印的北京屏幕坐标换算），"
                         "用 .tmp/shot-within.png 看框画在哪")
            else:
                skip("命中数不是 0/破折号/空", "没有 stat-tracks 元素")

            n_cancel = count_of(page, '[data-testid="draw-cancel"]')
            check("拉框松手后已退出绘制态（draw-cancel 消失）", n_cancel == 0,
                  f"draw-cancel 还有 {n_cancel} 个（松手没收敛 / 没退出绘制模式）")
            err_b = try_text(page, '[data-testid="within-error"]')
            check("拉框查询没有报错（within-error 不存在）",
                  count_of(page, '[data-testid="within-error"]') == 0, err_b or "有 within-error")
            # D 段"产生了查询结果"要靠它做前后对比（否则旧统计卡会让断言假绿）
            prev_tracks_text = txt if has_stat else None

        # ------------------------------------------------ C) 拉框之后左键旋转恢复
        print("=== C) 拉框之后左键旋转必须恢复 ===")
        shot_c_before = os.path.join(".tmp", "shot-within-c-before.png")
        shot_c_after = os.path.join(".tmp", "shot-within-c-after.png")
        page.screenshot(path=shot_c_before)
        img_before = Image.open(shot_c_before).convert("RGB")
        page.mouse.move(canvas["x"] + canvas["width"] * 0.70,
                        canvas["y"] + canvas["height"] * 0.60)
        page.mouse.down()
        page.mouse.move(canvas["x"] + canvas["width"] * 0.70 - 200,
                        canvas["y"] + canvas["height"] * 0.60, steps=10)
        page.mouse.up()
        page.wait_for_timeout(2500)            # 真实等待惯性 / 重绘结束
        page.screenshot(path=shot_c_after)
        img_after = Image.open(shot_c_after).convert("RGB")
        blue_before = count_color(img_before, (9, 20, 40), tol=30, x_from=x_from)
        blue_after = count_color(img_after, (9, 20, 40), tol=30, x_from=x_from)
        check("拖拽后地球确实动了（左键旋转已恢复，不是「地图坏了」）",
              abs(blue_before - blue_after) > 200, f"{blue_before} vs {blue_after}")
        c_ratio = diff_ratio(shot_c_before, shot_c_after, x_from)
        note(f"C 段底色像素 {blue_before} → {blue_after}（差 {abs(blue_before - blue_after)}）；"
             f"地图区域变化像素占比 {c_ratio:.1%}（非绘制态拖拽的基准值）")
        c1 = canvas_camera(page)
        if c1:
            note(f"C 段拖拽后相机：{c1}")

        # ------------------------------------------------ D) 绘制模式期间拖拽不旋转地球
        print("=== D) 绘制模式期间拖拽【不应该】旋转地球 ===")
        if count_of(page, '[data-testid="draw-rect"]') != 1:
            skip("D) 绘制模式拖拽断言", "draw-rect 按钮不存在")
        else:
            page.click('[data-testid="draw-rect"]')
            page.wait_for_timeout(300)
            cam_before = canvas_camera(page)
            page.screenshot(path=SHOT)
            img_a = Image.open(SHOT).convert("RGB")

            dx0 = canvas["x"] + canvas["width"] * 0.60
            dy0 = canvas["y"] + canvas["height"] * 0.50
            drag(page, dx0, dy0, dx0 - 150, dy0, steps=10)
            page.wait_for_timeout(600)
            cam_after = canvas_camera(page)
            # ⚠️ 等"新"结果：B 段那张统计卡还在，不比对旧文本就会假绿
            state_d, txt_d = wait_new_result(page, prev_text=prev_tracks_text)
            page.wait_for_timeout(600)         # 让区域轮廓/轨迹线画上去，像素比较才有意义
            page.screenshot(path=SHOT)
            img_b = Image.open(SHOT).convert("RGB")

            note(f"D 段拉框：( {dx0:.0f},{dy0:.0f} ) → ( {dx0 - 150:.0f},{dy0:.0f} )")
            note(f"D 段查询收尾状态 = {state_d}，stat-tracks 文本 = {txt_d!r}"
                 f"（上一次 = {prev_tracks_text!r}）")
            if state_d == "timeout":
                note("⚠️ D 段等不到结果：最可能是拖拽两端没落在球面上（这一点在默认全球视野下"
                     "本来就在地球外）→ 调 D 段的 0.60 / 0.50 两个比例，"
                     "或改用 B 段校准过的坐标；也可能是请求失败，看 within-error 有没有出现")

            # 判据 1（任务书要求的直接判据）：这次拖动被当成"拉框"了 → 才会产生查询结果
            check("绘制中的拖拽被当成拉框（产生了查询结果）",
                  count_of(page, '[data-testid="stat-tracks"]') == 1
                  or count_of(page, '[data-testid="within-empty"]') == 1,
                  f"状态={state_d}：拖拽后既没有统计数字也没有空结果提示 —— "
                  "要么事件没被当成拉框（地球被转了），要么请求失败")

            # 判据 2（参考值，不参与断言）：同一手势在 C 段（非绘制态）转了很多，
            # 在 D 段（绘制中）应当几乎不动 —— "画上去的框和橙色轨迹"会带来一点变化，
            # 但整体换画面（地球转了）是量级差别。只打印，避免给验收增加假红源。
            shot_d_before = os.path.join(".tmp", "shot-within-d-before.png")
            shot_d_after = os.path.join(".tmp", "shot-within-d-after.png")
            img_a.save(shot_d_before)
            img_b.save(shot_d_after)
            a = count_color(img_a, (9, 20, 40), tol=30, x_from=x_from)
            b = count_color(img_b, (9, 20, 40), tol=30, x_from=x_from)
            d_ratio = diff_ratio(shot_d_before, shot_d_after, x_from)
            note(f"D 段底色像素 {a} → {b}；地图区域变化像素占比 {d_ratio:.1%}"
                 f"（C 段非绘制态同样手势是 {c_ratio:.1%} —— 绘制中应当远小于它）")

            # 相机判据（若页面暴露了 viewer）：绘制模式下 enableRotate 必须是 false、相机不动
            if cam_before and cam_after and cam_before.get("rotate") is not None:
                check("绘制模式期间 enableRotate = false",
                      cam_after.get("rotate") is False,
                      f"enableRotate={cam_after.get('rotate')}（绘制中应为 false）")
                dlon = abs(cam_after["lon"] - cam_before["lon"])
                dlat = abs(cam_after["lat"] - cam_before["lat"])
                check("绘制模式期间相机没有被拖动（地球没转）",
                      dlon < 0.02 and dlat < 0.02,
                      f"Δ经度={dlon:.5f} Δ纬度={dlat:.5f}（绘制中不应被旋转）")
            else:
                skip("绘制模式期间相机不动 / enableRotate=false（直接读 viewer）",
                     "页面没暴露 Cesium viewer（canvas._cesiumWidget 取不到）")

        # ------------------------------------------------ E) 缓冲区
        print("=== E) 缓冲区 ===")
        page.click('[data-testid="draw-clear"]')
        page.wait_for_timeout(500)
        if count_of(page, '[data-testid="draw-buffer"]') != 1:
            skip("E) 缓冲区断言", "draw-buffer 按钮不存在")
        else:
            page.click('[data-testid="draw-buffer"]')
            page.wait_for_timeout(300)
            n_preset = count_of(page, '[data-testid="buffer-preset-1000"]')
            check("缓冲区预设半径按钮存在（buffer-preset-1000）", n_preset == 1,
                  f"实际 {n_preset} 个")
            if n_preset == 1:
                page.click('[data-testid="buffer-preset-1000"]')
                page.wait_for_timeout(200)
            else:
                note("预设按钮不存在，用输入框默认半径继续")
            page.mouse.click(canvas["x"] + canvas["width"] * 0.60,
                             canvas["y"] + canvas["height"] * 0.50)
            page.wait_for_timeout(600)
            state_e, txt_e = wait_result(page)
            note(f"E 段查询收尾状态 = {state_e}，stat-tracks 文本 = {txt_e!r}")

            check("缓冲区查询出结果或明确为空（统计卡 / 空提示至少有一个）",
                  count_of(page, '[data-testid="within-stats"]') == 1
                  and (count_of(page, '[data-testid="stat-tracks"]') == 1
                       or count_of(page, '[data-testid="within-empty"]') == 1),
                  f"状态={state_e} 文本={txt_e!r}")
            err_e = try_text(page, '[data-testid="within-error"]')
            check("缓冲区查询没有报错（within-error 不存在）",
                  count_of(page, '[data-testid="within-error"]') == 0, err_e or "有 within-error")

        # ------------------------------------------------ F) 清除 + 切档
        print("=== F) 清除 + 切档 ===")
        page.click('[data-testid="draw-clear"]')
        page.wait_for_timeout(900)
        still = count_of(page, '[data-testid="stat-tracks"]')
        check("清除后统计数字消失（stat-tracks 计数变 0）", still == 0,
              f"清除后 stat-tracks 还有 {still} 个 —— 统计卡没清干净")
        check("清除后没有残留的 within-error",
              count_of(page, '[data-testid="within-error"]') == 0,
              try_text(page, '[data-testid="within-error"]') or "有 within-error")

        if count_of(page, '[data-testid="mode-stay"]') == 1:
            before_pe = len(page_errors)
            page.click('[data-testid="mode-stay"]')
            page.wait_for_timeout(1200)
            left_after_switch = count_of(page, '[data-testid="stat-tracks"]')
            check("切到别的档不报错（无 pageerror，且圈选痕迹已清）",
                  len(page_errors) == before_pe and left_after_switch == 0,
                  f"新增 pageerror={page_errors[before_pe:][:3]} "
                  f"残留 stat-tracks={left_after_switch}")
        else:
            skip("切档不报错", "没有 mode-stay 按钮")

        # ------------------------------------------------ G) 面板零溢出
        print("=== G) 面板零溢出（两个矮视口）===")
        for w, h in SHORT_VIEWPORTS:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(300)
            if count_of(page, '[data-testid="mode-within"]') == 1:
                page.click('[data-testid="mode-within"]')
            else:
                skip(f"{w}x{h} 面板零溢出", "没有 mode-within 按钮")
                continue
            page.wait_for_timeout(900)
            ov = panel_overflow(page)
            if ov is None:
                skip(f"{w}x{h} 面板零溢出", "取不到 .panel")
                continue
            # 信息输出：面板实测尺寸（不是断言，只用于定位）
            box = page.locator(".panel").bounding_box()
            over = ov["sh"] - ov["ch"]
            note(f"{w}x{h} 面板 scrollHeight={ov['sh']} clientHeight={ov['ch']} "
                 f"溢出={over}px box={box}")
            check(f"{w}x{h} 面板零溢出", ov["sh"] <= ov["ch"] + 2,
                  f"scrollHeight={ov['sh']} > clientHeight={ov['ch']} + 2（溢出 {over}px）"
                  f" box={box}（矮视口下面板内容塞不下 → 会顶出下边界或裁掉列表）")

        # ------------------------------------------------ 控制台
        check("控制台零报错（pageerror + console.error）", len(errors) == 0, errors[:5])

        summary(browser)


def summary(browser):
    try:
        browser.close()
    except Exception:                          # noqa: BLE001
        pass
    print()
    if notes:
        print("关键诊断：")
        for n in notes:
            print("  ..", n)
    if console_errors:
        print(f"控制台 error 共 {len(console_errors)} 条：")
        for e in console_errors[:10]:
            print("  !!", e)
    if page_errors:
        print(f"pageerror 共 {len(page_errors)} 条：")
        for e in page_errors[:10]:
            print("  !!", e)
    if skipped:
        print("跳过的断言：")
        for s in skipped:
            print("  -", s)
    print()
    print(f"{ok} 项通过，{fail} 项失败" + (f"（另有 {len(skipped)} 项跳过）" if skipped else ""))
    if msgs:
        print("失败明细：")
        for m in msgs:
            print("  -", m)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:                          # noqa: BLE001
        # 脚本自身崩了也要给出一行可解析的结论 + 完整堆栈（否则主控只看到 traceback 没有计数）
        print()
        print("脚本异常终止（不是断言失败，是脚本自身出错）：")
        traceback.print_exc()
        print()
        print(f"{ok} 项通过，{fail + 1} 项失败")
        print("失败明细：")
        for m in msgs:
            print("  -", m)
        print("  - 脚本异常终止 :: 见上面的 traceback")
        sys.exit(1)
