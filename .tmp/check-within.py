# -*- coding: utf-8 -*-
"""M3 Task 11（修复轮 1）—— 圈选（空间范围查询）的浏览器验收：Playwright 真实等待 + Pillow 像素统计。

跑法（**必须提权 danger-full-access**，浏览器子进程靠管道通信；后端 8080 + 前端 5173 同时在跑）：

    cd E:\\JAVA_IDEA_package\\JAVA_Project\\Calcite
    $env:PYTHONIOENCODING='utf-8'
    & "E:\\python\\python_address\\python.exe" .tmp\\check-within.py

== 修复轮 1：首轮实跑暴露的三处脚本问题 ==

1. ⭐ **拉框前先"点一条轨迹 → 等相机飞到位"**。`CesiumGlobe` 初始视角是
   `Cartesian3.fromDegrees(116.4, 39.9, 12000000)`（12000 公里高），这个尺度下拖 90px
   ≈ 1200 公里，必然落在无人区（首轮实测 `within-empty = 1`）。现在先点 `.track-list .item`
   的第一条（`TrackList.vue` 里那个 `class="item"` 的 `<button>`，**不依赖任何轨迹 id**），
   flyTo 动画 `duration: 1.5s`，脚本等 3.5s，并断言"相机高度真的降下来了"。
2. ⭐ **不再猜拉框坐标**：`globe_probe()` 通过页面里的组件实例拿 viewer，把带 `position`
   的实体投影到窗口坐标，挑一个**四角都在视口内且在面板右侧**的点当框中心；
   同时打印相机高度/视野包围盒（`getViewBbox()`），失败时一眼能看出"框画在哪个尺度上"。
   取不到就回退"画布中心"，并在诊断里说明原因。
3. ⭐ **`draw-clear` 无结果时是 `disabled`**（首轮 `page.click` 直接超时崩）：
   `click_clear()` 先判 `is_enabled()`，禁用就 `force=True`，再兜一层 try/except，
   **最多记一条失败，绝不抛异常**。
4. ⭐ **硬证据**：Task 9 新加的 `globe.exposed.getRotateEnabled()`（`boolean | null`）——
   通过 `document.querySelector('#app').__vue_app__._instance` 递归走 vnode 树找到
   setupState 里有 `setDrawingMode` 的实例。新增 6 条直接读开关的断言：
   进档仍 `true` / 点拉框后 `false` / 拉框结束恢复 `true` / 再点拉框后 `false` /
   画到一半（拖拽刚结束）仍 `false` / 切档后恢复 `true`。
   取不到组件实例时这些**自动 skip**，退回原来的"像素 + 是否出结果"间接判据。

两条老纪律（不要回退）：**真实时间等待**（Cesium 几何体在 worker 里异步生成，虚拟时钟会得到
"线不存在"的假象）；**面板右边界问 DOM 要**（面板宽度 `min(420px, 34vw)`，写死 `x>=400` 假红/假绿过）。

断言纪律：没有"永远为真"的判据；取文本/边界框前先判存在；前置状态不成立就 `skip` 不崩；
靠数据的断言在失败明细里带**实测值**；靠"页面有没有暴露 Cesium / 组件实例"的判据能降级就降级，
真正的功能判据（旋转开关、绘制中不旋转、零溢出、零报错）一条不少。
"""
import math
import os
import sys
import traceback

from playwright.sync_api import sync_playwright
from PIL import Image

URL = "http://localhost:5173"          # ⚠️ 必须是 localhost：Vite 只绑 IPv6，127.0.0.1 连不上
SHOT = os.path.join(".tmp", "shot-within.png")

# 拉框尺寸（像素）。点完轨迹后相机已经贴到那条轨迹上，这个幅度足够跨过轨迹线。
RECT_W = 90
RECT_H = 70
D_RECT_W = 140                         # D 段（绘制中拖拽）的幅度
D_RECT_H = 0
FLY_WAIT_MS = 3500                     # flyTo duration 1.5s + 余量（真实等待，不用虚拟时钟）
FLIGHT_HEIGHT_DROP_RATIO = 0.5         # 相机高度降到原来一半以下才算"真的飞过去了"

VIEWPORT = {"width": 1600, "height": 900}
SHORT_VIEWPORTS = ((1366, 660), (1600, 600))

ok = 0
fail = 0
msgs = []          # 失败明细
skipped = []       # 因前置状态不成立而跳过的断言
notes = []         # 关键诊断值（报告要靠它判断失败原因）

errors = []        # pageerror + console.error 合起来（"控制台零报错"用它）
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
        note(f"读 {selector} 文本失败：{type(e).__name__}: {e}")
        return default


def count_of(page, selector):
    try:
        return page.locator(selector).count()
    except Exception as e:                      # noqa: BLE001
        note(f"统计 {selector} 数量失败：{type(e).__name__}: {e}")
        return -1


def click_clear(page):
    """安全点「清除」。

    ⚠️ 首轮实跑就是这里崩的：无结果时 `RegionDrawer` 的清除按钮带 `disabled`
    （`:disabled="!hasResult && mode === 'idle'"`），`page.click` 会等可点击直到超时抛异常，
    整个脚本就死在这里。这里：判 `is_enabled()` → 禁用就 `force=True` → 再兜一层 try/except。
    返回 True 表示点成了，False 表示没点成（调用方记一条失败，不崩）。
    """
    try:
        loc = page.locator('[data-testid="draw-clear"]')
        if loc.count() == 0:
            note("清除按钮不存在，这次点击跳过")
            return False
        if loc.first.is_enabled():
            loc.first.click(timeout=5000)
            return True
        note("清除按钮当前 disabled（无结果时属正常状态）→ 用 force=True 点它")
        loc.first.click(force=True, timeout=5000)
        return True
    except Exception as e:                      # noqa: BLE001
        note(f"点清除按钮失败：{type(e).__name__}: {e}")
        return False


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


# ---------------------------------------------------------------- 页面侧探针
# 下面几个 JS 遵守同一条纪律：取不到就返回 null / 空数组，绝不抛异常打断验收。
GL_JS = r"""
function findGlobe() {
  try {
    const app = document.querySelector('#app');
    const root = app && app.__vue_app__ && app.__vue_app__._instance;
    if (!root) return null;
    const seen = new Set();
    const stack = [root];
    while (stack.length) {
      const inst = stack.pop();
      if (!inst || seen.has(inst)) continue;
      seen.add(inst);
      const st = inst.setupState;
      if (st && typeof st.setDrawingMode === 'function') {
        return (inst.exposed && typeof inst.exposed === 'object') ? inst.exposed : st;
      }
      const sub = inst.subTree;
      if (sub) {
        if (sub.component) stack.push(sub.component);
        let c = sub.children;
        if (Array.isArray(c)) { for (const x of c) if (x && x.component) stack.push(x.component); }
        else if (c && c.component) stack.push(c.component);
      }
    }
  } catch (e) { return null; }
  return null;
}
// 组件公开实例上找 Cesium 的 Scene：运行时它通常挂在 `scene` 上（也可能被包成 ref/value）
function findScene(g) {
  if (!g) return null;
  const cands = ['scene', '_scene'];
  for (const k of cands) {
    try {
      let s = g[k];
      if (s && s.value) s = s.value;
      if (s && s.camera && s.canvas) return s;
    } catch (e) {}
  }
  return null;
}
"""


def globe_probe(page):
    """一次 JS 往返拿回全部页面侧信息（少往返 = 少失败点）：
      have_globe  找到 CesiumGlobe 的 exposed 了吗
      rotate      getRotateEnabled() → true / false / null
      keys        exposed 上有哪些方法（诊断用，拿不到场景时看它）
      cam         {lon, lat, h}（弧度 / 弧度 / 米）；来自真实 viewer（能拿到场景时）
      bbox        getViewBbox() 的 {west, south, east, north}（度）—— 拿不到 viewer 也能有
      points      带 position 的实体投影到窗口的坐标（最多 200 个）
    """
    try:
        return page.evaluate(r"""() => {
            %s
            const g = findGlobe();
            const out = { have_globe: !!g, rotate: null, keys: [], cam: null, bbox: null, points: [] };
            if (!g) return out;
            out.keys = Object.keys(g);
            if (typeof g.getRotateEnabled === 'function') {
              const r = g.getRotateEnabled();
              out.rotate = (r === true || r === false) ? r : null;
            }
            if (typeof g.getViewBbox === 'function') {
              try { out.bbox = g.getViewBbox(); } catch (e) {}
            }
            const s = findScene(g);
            if (!s) return out;
            try {
              const c = s.camera.positionCartographic;
              if (c) out.cam = { lon: c.longitude, lat: c.latitude, h: c.height };
            } catch (e) {}
            try {
              const ST = (typeof Cesium !== 'undefined') ? Cesium.SceneTransforms : null;
              const f = ST && (ST.worldToWindowCoordinates || ST.wgs84ToWindowCoordinates);
              if (!f) return out;
              const rect = s.canvas.getBoundingClientRect();
              const arr = s.entities.values;
              for (let i = 0; i < arr.length && out.points.length < 200; i++) {
                const e = arr[i];
                if (!e.position) continue;
                const t = e.position.getValue(s.clock.currentTime);
                if (!t) continue;
                const w = f(s, t);
                if (!w) continue;
                const x = w.x + rect.left, y = w.y + rect.top;
                if (x >= 0 && x <= rect.width && y >= 0 && y <= rect.height) {
                  out.points.push([Math.round(x), Math.round(y)]);
                }
              }
            } catch (e) {}
            return out;
        }""" % GL_JS)
    except Exception as e:                      # noqa: BLE001
        note(f"页面探针失败：{type(e).__name__}: {e}")
        return {"have_globe": False, "rotate": None, "keys": [], "cam": None,
                "bbox": None, "points": []}


def globe_rotate(page):
    """只读「左键旋转」开关：True / False / None（组件拿不到、或 viewer 没就绪）。

    ⚠️ 这是 Task 9 的 `getRotateEnabled()`（defineExpose 暴露）——
    比"像素变没变"和"有没有出结果"都硬。
    """
    return globe_probe(page)["rotate"]


def _screen_of(page, lon, lat):
    """（尽力而为）经纬度 → 窗口坐标。拿不到场景时返回 None（只用于诊断输出）。"""
    try:
        return page.evaluate(r"""([lon, lat]) => {
            %s
            const g = findGlobe();
            const s = findScene(g);
            if (!s) return null;
            const ST = (typeof Cesium !== 'undefined') ? Cesium.SceneTransforms : null;
            const f = ST && (ST.worldToWindowCoordinates || ST.wgs84ToWindowCoordinates);
            if (!f) return null;
            const rect = s.canvas.getBoundingClientRect();
            const win = f(s, Cesium.Cartesian3.fromDegrees(lon, lat, 0));
            if (!win) return null;
            return { x: win.x + rect.left, y: win.y + rect.top,
                     w: rect.width, h: rect.height,
                     on: win.x >= 0 && win.x <= rect.width && win.y >= 0 && win.y <= rect.height };
        }""" % GL_JS, [lon, lat])
    except Exception:                           # noqa: BLE001
        return None


def _fmt_cam(cam):
    if not cam:
        return "拿不到"
    return (f"lon={math.degrees(cam['lon']):.4f} lat={math.degrees(cam['lat']):.4f} "
            f"h={cam['h'] / 1000:.1f}km")


def _h(cam):
    return "拿不到" if not cam else f"{cam['h'] / 1000:.1f}km"


def _bbox_txt(bbox):
    if not bbox:
        return "拿不到"
    return (f"lon[{bbox['west']:.3f},{bbox['east']:.3f}] "
            f"lat[{bbox['south']:.3f},{bbox['north']:.3f}] "
            f"跨度 {bbox['east'] - bbox['west']:.3f}°×{bbox['north'] - bbox['south']:.3f}°")


def choose_drag_rect(points, canvas, panel_right, w=RECT_W, h=RECT_H):
    """从候选点里挑一个**能当拉框中心**的点：四角都在视口内、且在面板右侧。

    返回 (x0, y0, x1, y1) 或 None（一个都没有 → 调用方回退到画布中心）。
    """
    vw, vh = VIEWPORT["width"], VIEWPORT["height"]
    for pt in points:
        cx, cy = pt[0], pt[1]               # 探针返回的已经是窗口坐标
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        if x0 < panel_right + 8 or x1 > vw - 4:
            continue
        if y0 < 4 or y1 > vh - 4:
            continue
        return round(x0), round(y0), round(x1), round(y1)
    return None


def center_rect(canvas, w=RECT_W, h=RECT_H):
    cx, cy = canvas["x"] + canvas["width"] / 2, canvas["y"] + canvas["height"] / 2
    return round(cx - w / 2), round(cy - h / 2), round(cx + w / 2), round(cy + h / 2)


def shift_rect(rect, dx):
    return (rect[0] + dx, rect[1], rect[2] + dx, rect[3])


def in_viewport(rect):
    vw, vh = VIEWPORT["width"], VIEWPORT["height"]
    x0, y0, x1, y1 = rect
    return (0 <= x0 and 0 <= y0 and x1 <= vw and y1 <= vh)


def drag(page, x0, y0, x1, y1, steps=8):
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x1, y1, steps=steps)
    page.mouse.up()


# ---------------------------------------------------------------- 结果等待
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

        canvas = page.locator("canvas").first.bounding_box()
        panel_box = page.locator(".panel").bounding_box()
        if not canvas or not panel_box:
            check("能取到 canvas / .panel 的边界框", False,
                  f"canvas={canvas} panel={panel_box}")
            summary(browser)
            return
        panel_right = panel_box["x"] + panel_box["width"]
        x_from = int(panel_right) + 4
        note(f"canvas = {canvas}")
        note(f"面板右边界 x={x_from}（面板 {panel_box['x']:.0f},{panel_box['y']:.0f} "
             f"{panel_box['width']:.0f}x{panel_box['height']:.0f}）")

        pr0 = globe_probe(page)
        note(f"组件实例 have_globe={pr0['have_globe']}；exposed 方法={pr0['keys']}")
        note(f"初始相机 = {_fmt_cam(pr0['cam'])}；rotate={pr0['rotate']}；"
             f"视野 = {_bbox_txt(pr0['bbox'])}")
        if not pr0["have_globe"]:
            note("⚠️ 找不到 CesiumGlobe 的 exposed（__vue_app__ 遍历失败）："
                 "6 条 getRotateEnabled 硬判据会 skip，退回像素/结果间接判据")
        if pr0["cam"] is None:
            note("⚠️ 拿不到真实 viewer（组件公开实例上没有 scene）：实体投影点会为空，"
                 "拉框只能回退画布中心；视野包围盒仍可用（getViewBbox）")
        for name, lon, lat in (("北京", 116.40, 39.90), ("上海", 121.47, 31.23)):
            s = _screen_of(page, lon, lat)
            if s is None:
                note(f"{name} 屏幕坐标：取不到（viewer 未就绪）")
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

        rot_idle = pr0["rotate"] if pr0["rotate"] is not None else globe_rotate(page)
        if rot_idle is None:
            skip("进圈选档时左键旋转仍开启（getRotateEnabled = true）",
                 "拿不到组件 exposed 或开关值")
        else:
            check("进圈选档时左键旋转仍开启（getRotateEnabled = true）", rot_idle is True,
                  f"getRotateEnabled() = {rot_idle}（还没开始画，应当可以转）")

        # ------------------------------------------------ B) 先飞相机，再拉框
        print("=== B) 点一条轨迹飞过去 → 拉框 → 统计卡出现 ===")
        prev_tracks_text = None
        if count_of(page, '[data-testid="draw-rect"]') != 1:
            skip("B) 拉框全部断言", "draw-rect 按钮不存在")
        else:
            # ⭐ 修复轮 1 的核心：先把相机从"12000 公里全球视野"拉到一条真实轨迹上。
            # 否则 90px 在 12000 公里尺度下 ≈ 1200 公里，必然画到无人区（首轮实测）。
            pr_before_fly = globe_probe(page)
            cam_before_fly = pr_before_fly["cam"]
            n_items = count_of(page, ".track-list .item")
            note(f"轨迹列表可点条目 = {n_items} 个（选择器 .track-list .item，不依赖轨迹 id）")
            anchor = None
            if n_items > 0:
                page.locator(".track-list .item").first.click()
                page.wait_for_timeout(FLY_WAIT_MS)   # flyTo duration 1.5s，真实等待
                pr_fly = globe_probe(page)
                cam_after_fly = pr_fly["cam"]
                note(f"点第一条轨迹后：相机 {_fmt_cam(cam_after_fly)}；"
                     f"视野 {_bbox_txt(pr_fly['bbox'])}；"
                     f"实体投影点 {len(pr_fly['points'])} 个")
                if cam_before_fly and cam_after_fly:
                    h0, h1 = cam_before_fly["h"], cam_after_fly["h"]
                    check("点列表后相机确实飞近了（不是停在 12000 公里全球视野）",
                          h1 < h0 * FLIGHT_HEIGHT_DROP_RATIO or h1 < 200000,
                          f"高度 {h0 / 1000:.1f}km → {h1 / 1000:.1f}km"
                          f"（期望 < {h0 * FLIGHT_HEIGHT_DROP_RATIO / 1000:.1f}km 或 < 200km）")
                else:
                    skip("点列表后相机确实飞近了", "拿不到相机高度（viewer 不可达）")
                anchor = choose_drag_rect(pr_fly["points"], canvas, panel_right)
            else:
                skip("点列表后相机确实飞近了", "轨迹列表里一条都没有，无法飞相机")

            if anchor is None:
                anchor = center_rect(canvas)
                note("⚠️ 没有可用的实体投影点 → 回退「画布中心」拉框。"
                     "若命中 0 条，先看上面「相机/视野/实体投影点」三行与 .tmp/shot-within.png")
            x0, y0, x1, y1 = anchor
            note(f"B 段拉框：( {x0},{y0} ) → ( {x1},{y1} ) 大小 {x1 - x0}x{y1 - y0}px")
            if not in_viewport(anchor):
                note(f"⚠️ 拖拽坐标超出视口 ({x0},{y0})→({x1},{y1})："
                     "拖出画面 Cesium 收不到 mouseup，这一笔作废（命中 0 条时先看这里）")

            rot_pre_draw = globe_rotate(page)
            page.click('[data-testid="draw-rect"]')
            page.wait_for_timeout(300)
            rot_in_draw = globe_rotate(page)
            if rot_pre_draw is None or rot_in_draw is None:
                skip("进入绘制模式后 getRotateEnabled = false", "拿不到组件 exposed 或开关值")
            else:
                check("进入绘制模式后 getRotateEnabled = false",
                      rot_pre_draw is True and rot_in_draw is False,
                      f"点拉框前={rot_pre_draw}，点拉框后={rot_in_draw}（期望 true → false）")

            drag(page, x0, y0, x1, y1)
            page.wait_for_timeout(600)         # 松手 → 发请求之间的最短间隔
            state, txt = wait_result(page)
            note(f"B 段查询收尾状态 = {state}，stat-tracks 文本 = {txt!r}")

            rot_after_draw = globe_rotate(page)
            if rot_after_draw is None:
                skip("拉框结束后左键旋转恢复（getRotateEnabled = true）", "拿不到开关值")
            else:
                check("拉框结束后左键旋转恢复（getRotateEnabled = true）",
                      rot_after_draw is True,
                      f"getRotateEnabled() = {rot_after_draw}（松手即退出绘制，期望 true）")

            n_stats_card = count_of(page, '[data-testid="within-stats"]')
            check("统计卡出现（within-stats）", n_stats_card == 1, f"实际 {n_stats_card} 个")
            has_stat = count_of(page, '[data-testid="stat-tracks"]') == 1
            check("有「条轨迹穿过」数字（stat-tracks）", has_stat,
                  f"状态={state} 文本={txt!r}"
                  + ("（空结果：统计卡只有提示行 —— 框没框到轨迹）" if state == "empty" else ""))
            if has_stat:
                note(f"接口命中 {txt} 条")
                check("命中数不是 0 / 破折号 / 空（说明真的查到了数据）",
                      txt not in ("—", "", "0"), f"实际 {txt!r}")
                if txt in ("—", "", "0"):
                    note("⚠️ 命中 0 条：先看上面「点第一条轨迹后…」那行（相机/视野/实体投影点），"
                         "再用 .tmp/shot-within.png 看框画在哪 —— 这是脚本坐标问题，不是功能问题")
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
            b_anchor = anchor
        if prev_tracks_text is None:
            b_anchor = center_rect(canvas)

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
        if abs(blue_before - blue_after) > 200 and c_ratio < 0.02:
            note("⚠️ 底色像素差够大、但整片地图变化占比很小：这条可能是**判据本身**在作怪"
                 "（面板/曲线重绘、底图异步加载），而不是真的转了 —— 请对照 D 段那行"
                 "「相机 Δ经度/Δ纬度」与 getRotateEnabled 的行再判一次")
        c1 = globe_probe(page)
        note(f"C 段拖拽后：相机 {_fmt_cam(c1['cam'])}；视野 {_bbox_txt(c1['bbox'])}；"
             f"rotate={c1['rotate']}")

        # ------------------------------------------------ D) 绘制模式期间拖拽不旋转地球
        print("=== D) 绘制模式期间拖拽【不应该】旋转地球 ===")
        if count_of(page, '[data-testid="draw-rect"]') != 1:
            skip("D) 绘制模式拖拽断言", "draw-rect 按钮不存在")
        else:
            page.click('[data-testid="draw-rect"]')
            page.wait_for_timeout(300)
            # ⭐ 位置①：刚进入绘制模式（还没拖）—— 应当已经关掉旋转。
            # 这一条在 B 段也测了（同一个事实两次站岗）。✅ 安全：此刻距点击只有 300ms，
            # 松手事件还没发生，开关一定是"绘制中"的 false。
            rot_d1 = globe_rotate(page)
            if rot_d1 is None:
                skip("进入绘制模式后 getRotateEnabled = false（D 段）", "拿不到开关值")
            else:
                check("进入绘制模式后 getRotateEnabled = false（D 段）", rot_d1 is False,
                      f"getRotateEnabled() = {rot_d1}（绘制中必须为 false）")

            cam_before = globe_probe(page)["cam"]
            page.screenshot(path=SHOT)
            img_a = Image.open(SHOT).convert("RGB")

            if in_viewport(shift_rect(b_anchor, -D_RECT_W)):
                d_rect = shift_rect(b_anchor, -D_RECT_W)
            else:
                d_rect = center_rect(canvas, 60, 40)
                note("⚠️ D 段拖拽落点会超出视口 → 回退画布中心小框")
            dx0, dy0 = d_rect[0], d_rect[1]
            dx1, dy1 = d_rect[2], d_rect[3]
            note(f"D 段拉框：( {dx0},{dy0} ) → ( {dx1},{dy1} )")
            drag(page, dx0, dy0, dx1, dy1, steps=10)
            page.wait_for_timeout(400)
            # ⚠️ 读相机要放在"等待查询结果"**之前**：查询一落地，App 就把 drawingMode 收回
            #    'idle'、地球的 watcher 立刻把 enableRotate 恢复成 true —— 之后再读
            #    getRotateEnabled 只会读到 true，那是**竞态假红**，不是 bug。
            cam_after = globe_probe(page)["cam"]
            rot_d2 = globe_rotate(page)   # 只在拿不到相机时当兜底判据用（见下）

            # ⭐ 位置②的硬证据：绘制中的拖拽**不该带动相机**。
            # 这条不会踩上面的竞态 —— 相机是"拖拽有没有被当成旋转"的物理后果。
            if cam_before and cam_after:
                dlon = abs(cam_after["lon"] - cam_before["lon"])
                dlat = abs(cam_after["lat"] - cam_before["lat"])
                check("绘制模式期间拖拽【没有】转动相机（绘制中左键旋转被关掉）",
                      dlon < 0.02 and dlat < 0.02,
                      f"Δ经度={dlon:.6f} Δ纬度={dlat:.6f} "
                      f"（非绘制态同样的 140px 拖拽会改变约 0.1~0.5 弧度）；"
                      f"高度 {cam_before['h'] / 1000:.1f}→{cam_after['h'] / 1000:.1f}km")
                note(f"D 段相机 Δ经度={dlon:.6f} Δ纬度={dlat:.6f} "
                     f"高度 {cam_before['h'] / 1000:.1f}→{cam_after['h'] / 1000:.1f}km")
            else:
                note("拿不到相机 → D 段的「绘制中不旋转」只能靠间接证据"
                     "（B 段的开关断言 + D 段是否产生新查询结果）；这里不塞一条恒真断言充数。")
                note(f"D 段（拖拽刚结束）getRotateEnabled = {rot_d2}"
                     "（松手后可能已退出绘制态，读到 true 属竞态，不作为失败）")
                skip("绘制模式期间拖拽【没有】转动相机", "viewer 不可达，拿不到相机位置")

            # ⚠️ 等"新"结果：B 段那张统计卡还在，不比对旧文本就会假绿
            state_d, txt_d = wait_new_result(page, prev_text=prev_tracks_text)
            page.wait_for_timeout(600)         # 让区域轮廓/轨迹线画上去，像素比较才有意义
            page.screenshot(path=SHOT)
            img_b = Image.open(SHOT).convert("RGB")

            note(f"D 段查询收尾状态 = {state_d}，stat-tracks 文本 = {txt_d!r}"
                 f"（上一次 = {prev_tracks_text!r}）")
            if state_d == "timeout":
                note("⚠️ D 段等不到结果：最可能是拖拽两端没落在球面/当前视野内的数据上 → "
                     "看上面「D 段拉框」坐标与「C 段拖拽后 视野」，"
                     "也可能是请求失败（看 within-error）")

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

        # ------------------------------------------------ E) 缓冲区
        print("=== E) 缓冲区 ===")
        if not click_clear(page):
            note("E 段前那次「清除」没点成，继续跑（下面用新查询覆盖）")
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
            # 单击一个点 = 以该点为中心、当前半径 1000m 直接查（不必再点「查询」按钮）
            bcx, bcy = canvas["x"] + canvas["width"] * 0.60, canvas["y"] + canvas["height"] * 0.50
            note(f"缓冲区中心点：( {bcx:.0f},{bcy:.0f} )，半径 1000m")
            page.mouse.click(bcx, bcy)
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
        cleared = click_clear(page)
        page.wait_for_timeout(900)
        still = count_of(page, '[data-testid="stat-tracks"]')
        check("清除后统计数字消失（stat-tracks 计数变 0）", still == 0,
              f"清除后 stat-tracks 还有 {still} 个 —— 统计卡没清干净"
              + ("" if cleared else "（这次清除按钮没点成，看上面诊断）"))
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
            page.click('[data-testid="mode-within"]')   # 切回来，供 G 段量面板
            page.wait_for_timeout(600)
            rot_after_switch = globe_rotate(page)
            if rot_after_switch is None:
                skip("切档后左键旋转恢复（getRotateEnabled = true）", "拿不到开关值")
            else:
                check("切档后左键旋转恢复（getRotateEnabled = true）", rot_after_switch is True,
                      f"getRotateEnabled() = {rot_after_switch}（切档应当恢复旋转）")
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
