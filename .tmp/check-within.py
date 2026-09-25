# -*- coding: utf-8 -*-
"""M3 Task 11（修复轮 5）—— 圈选（空间范围查询）的浏览器验收：Playwright 真实等待 + Pillow 像素统计。

跑法（**必须提权 danger-full-access**，浏览器子进程靠管道通信；后端 8080 + 前端 5173 同时在跑）：

    cd E:\\JAVA_IDEA_package\\JAVA_Project\\Calcite
    $env:PYTHONIOENCODING='utf-8'
    & "E:\\python\\python_address\\python.exe" .tmp\\check-within.py

五轮修复的净结果（历史细节见各段注释）：
  轮 1：拉框前先点一条轨迹飞相机 / `draw-clear` 禁用兜底 / 用 `getRotateEnabled()` 拿硬证据
  轮 2：C 段旋转判据从"像素差"换成"视野包围盒位移" / `findViewer` 改走 `setupState.viewer`
  轮 3：5 个包围盒测量点先 `wait_view_stable()` 等相机停稳（消惯性余摆污染）
  轮 4：⭐ D 段"绘制中包围盒不动"**降级为信息输出**（理由见下）
  轮 5：⭐ 补多边形交互 + ESC 出口；D/E 段的"有没有出结果"改成**数网络请求**（理由见下）
  轮 6：⭐ 补「区域轮廓 + 命中轨迹画在地球上」与「列表↔地图联动」的**实体**证据；
        造出「命中 > DRAW_LIMIT」的真实场景；零溢出改成有结果 / 无结果都量 + CSS 契约

== 修复轮 6：实体证据（规格 9.5）+ 零溢出只在空面板量过 + 一条恒真断言 ==

最终审查的 4 条 finding 逐条：

1) ⭐ **规格 9.5 的「区域轮廓与命中轨迹像素存在」从来没验过** —— 全文只数了底色 (9,20,40)，
   从没检查 `within-region` / `within-track-*` 实体，也从没点过 `within-item-*`。
   这条路**真的断过一次**（提交 `0af523b`：点列表一条 → 地图上什么都不画），
   靠人读代码才发现，测试没抓住。修法（新增 A2 / A2b / B2 段）：
   · 新增 `within_entities()`：数 id 以 `within-region` / `within-track-` 开头的实体
     （`v.entities.values`，`String(e.id)`）—— 实体在 ⇔ CesiumGlobe 真把两个 prop 画上了地球；
   · **B2 段**（B 段拉框成功之后）断言 `within-region*` ≥ 1（轮廓真的画了）、
     `within-track-*` ≥ 1（命中轨迹真的画了）；
   · 还加了一条与命中条数无关的**列表↔地图高亮**证据：`within_track_style()` 读那条线的
     线宽/颜色，点列表里**已画**的条目后必须从「宽 2 / 橙 #ff9f45」变成「宽 3 / 亮蓝 #7fd1ff」
     （`drawWithinTracks` 的 selected 分支）——这条在 3 条命中时也能验。
2) ⭐ **「点一个没画出来的条目 → 补画」原来只能 skip**：B 段把相机飞到福建那条轨迹，
   附近一共只有 3 条，而地图默认画前 20 条（DRAW_LIMIT）→ **没有可点的条目**。
   修法：**A2 段**在初始相机（12000 公里、正对北京上空，画布中心就是 116.4,39.9）上用
   50 公里缓冲区（`calcite.within.max-buffer-m`）一次罩住北京全部轨迹 → 命中数远超 DRAW_LIMIT，
   列表被截断、地图只画 20 条 → **A2b 段**点一个 `within-item-*`（先算出"列表有、地球上没有"的集合），
   断言 `within-track-*` 实体数**增加**（`onWithinSelect → loadWithinDetail` 的行为证据）。
   ⚠️ 放在 B 段**之前**是刻意的：B/C/D 段的判据都建立在"相机贴在某条轨迹上"这个尺度上，
      在它们之后挪相机会污染 C 段那条"拖拽后地球确实动了 ≥8% 视野跨度"。
   ⚠️ 若 A2 的命中数 ≤ DRAW_LIMIT（数据变了 / 相机尺度不对），A2b **记 skip 并打印
      「列表 N 条全部已画」，不写成恒真**。
3) **零溢出只在"面板已被清空"时量过**（旧脚本先 F 段清除、再 G 段量）→ 量的是空面板，
   而 Task 8 评审警告的"命中多条时列表被裁"那个场景**没有任何布局验证**。修法（G 段重写）：
   · **有结果**（当前视口下重新查一次最大半径缓冲区、列表里真的有条目）与
     **无结果**（清除后）**两个状态都量** `scrollHeight <= clientHeight + 2`；
   · 再加一条**与条数无关的 CSS 契约**：`getComputedStyle('.within-stats').flexShrink === '1'`。
     为什么是它：`.panel > div:not(...)` 那条规则给"非白名单"的 div 设 `flex: 0 0 auto`
     （flex-shrink 0 = 不可收缩），把 `.within-stats` 加进 `:not(...)` 链之后它拿回默认的
     `flex-shrink: 1`（可收缩、能滚动）。这条在 0 / 3 / 232 条命中下都成立，
     正好补上"232 条时列表被裁"用真实数据不好构造的缺口。实测不是 '1' 就**如实红**。
4) **一条恒真断言**（旧 B 段 `统计卡出现（within-stats）`）：`WithinStats` 根 div 没有 v-if、
   `App.vue` 里无条件渲染 → 无论这次拉框有没有生效它都在。删掉，换成与 D/E/E2 段同款的
   **请求计数**判据：`POST /api/analysis/within` 计数增加 ≥1（并顺手修了 B 段读结果时
   会被"上一段留在 DOM 里的旧统计卡"骗到的时序问题：先等新请求、再等 `draw-hint` 离开"查询中…"）。

== 修复轮 5：多边形交互补验 + ESC 出口 + "用请求计数代替看 DOM 文本" ==

评审给的 4 条开放 finding，逐条：

1) **多边形交互整条没验** —— 旧脚本只数了 `draw-polygon` 按钮存在（`count == 1`），
   从没点过、没画过点、没双击过。于是 `RegionDrawer → App.onDrawPolygon → polygonGeometry
   → queryWithin` 这条链**整条坏掉也全绿**。新增 **E2 段**：点「多边形」→ 在轨迹锚点位置
   点 4 个点（围成边长 ~44px 的小四边形）→ 在最后一点 `dblclick` 闭合 → 断言
   「`stat-tracks` 有数字 或 `within-empty` 有文字（至少一个有内容，不止元素存在）」
   → 再断言 `draw-cancel` 消失。失败时打印 4 个坐标、闭合方式、GET/POST 计数。
   ⚠️ Cesium 会把一次 `dblclick` 拆成**两次 LEFT_CLICK + 一次 LEFT_DOUBLE_CLICK**
   （Build/CesiumUnminified/index.js 的 `handleMouseUp` 里 LEFT_CLICK 是 mouseup 时发的，
   `handleDblClick` 另外发 LEFT_DOUBLE_CLICK），所以末尾会多一个**与第 4 点重合的顶点**。
   实测确认无害：`SELECT ST_IsValid('POLYGON((…,第4点,第4点,第1点))')` → `t | Valid Geometry`
   （PostGIS 3.6 / GEOS 容忍重复顶点）。

2) **`:963-965` 是恒真断言**（本轮最要紧）—— 因果链：`draw-rect` 只 `emit('start')` →
   `App.startDraw` **只改 `drawingMode`、不清 `withinStats`**；`WithinStats.vue` 的根 div
   **没有 `v-if`**、`App.vue` 里也**无条件渲染**它。⇒ B 段查出来的 `stat-tracks`
   **一直留在 DOM 里**，所以 D 段哪怕完全没被当成拉框（地球被转了），
   `count('[data-testid="stat-tracks"]') == 1` 也照样成立 —— 这条 check 信息量为 0。
   修法：**数网络请求**。新增 `http_log` + `req_count(method, url片段)`，
   D 段拖拽前后各读一次 `POST /api/analysis/within` 的计数，断言**增加 ≥1**：
   这既证明"这个手势被当成画区域并真的发了请求"，也顺带证明请求确实发出去了，
   而且**完全不依赖 DOM 的新旧文本**（`wait_new_result` 的两个弱点就此不再影响判据：
   空结果分支会看到**旧的** `within-empty` 就立即返回、`seen_busy` 靠 250ms 轮询
   可能错过 ≈200–560ms 的"查询中"窗口 —— 它现在只用来取诊断文本）。
   E2（多边形）与 E（缓冲区）段也做了同样的前后对比：**E 段原来那条
   `within-stats==1 && (stat-tracks==1 || within-empty==1)` 在"E 段前的清除没点成、
   D 段结果还留在 DOM 里"时会变成恒真**，所以把"新增请求 ≥1"折进同一条 check。
   缓冲区单击若落在球外则不发请求 → 一眼能看出是哪一种。

3) **实体投影探针是死代码 + 诊断误导** —— 旧代码写 `typeof Cesium !== 'undefined'`，
   而页面里**没有全局 `Cesium`**（`index.html` 只加载 `main.js`，组件用具名 import，
   vite 只 `define` 了 `CESIUM_BASE_URL`）→ 恒为 false；即便有，下一句
   `s.entities.values` 也不成立（`entities` 是 **Viewer** 的属性，**Scene 没有**）。
   于是投影点恒为空 → 拉框锚点永远回退画布中心，却打印"北京/上海 屏幕坐标：取不到
   （**Viewer 未就绪**）"—— Viewer 其实是好的，这句把人带偏。修法：
   · 实体取 `v.entities.values`（`findViewer()` 返回的 Viewer，本来就已经能拿到）；
   · 投影用 **`scene.cartesianToCanvasCoordinates(position)`**（Cesium 1.145 的
     `Scene` 自带方法，见 `node_modules/cesium/Source/Cesium.d.ts:45150`），
     不再需要全局 `Cesium`；经纬度 → Cartesian3 走
     `scene.globe.ellipsoid.cartographicToCartesian({longitude, latitude, height})`
     （Ellipsoid 这个方法是**鸭子类型**的，普通对象即可，已核 `CesiumUnminified/index.js:23890`）；
   · 实在取不到就**明确降级**：打印「实体投影不可用（原因：…），拉框锚点使用画布中心
     （设计如此）」，**不再留一条"永远为 0 却看起来像环境没就绪"的诊断**。
   探针新增 `proj_how`（投影走的是哪条能力），拿不到 Viewer / 投影函数 / 转换函数
   会分别给出**具体原因**。

4) **ESC 取消**（规格 9.5 明列的出口，旧脚本从不按 ESC）：新增 **E3 段**：
   进入拉框模式（此时 `draw-cancel` 应在、`getRotateEnabled()===false`）→ 按 `Escape`
   → 断言 `draw-cancel` 消失 **且** `getRotateEnabled()` 回到 `true`。
   （`App.vue` 的 `onKeydown` 挂在 `window` 上，`Escape` 时把 `drawingMode` 收回 `idle`，
   地球的 watcher 随之 `rotateEnabled(true)`。）

== 修复轮 4：为什么 D 段那条不再是断言 ==

主控三轮探针实测（2026-09-25）证明这条**代理判据在合成拖拽下不成立**：

    | 实验                                            | 相机位移                    |
    | 非绘制态快速拖拽（steps=8）                       | −0.0116°（正常旋转 ✓）      |
    | 绘制态快速拖拽 #1 / #2（enableRotate 全程 false）  | −0.0077° / −0.0089°（！）   |
    | 绘制态慢速分步拖拽（每步 200ms ≈ 人类速度）        | **精确 0.0**（✓ 不动）      |
    | 绘制态快速拖拽 + 同时关 enableInputs               | 减半（−0.0038），**没消除** |

⇒ Playwright 的合成拖拽**速度极高**（8 步在几十毫秒内跑完），会激发 Cesium **输入聚合器**，
让相机在 `enableRotate=false` 时也动一点点；而**人类速度的拖拽位移精确为 0**。
所以"视野包围盒位移"只能当**信息**看，**不计入通过/失败**（C 段那条不同：它是**正向**证据，
非绘制态拖拽实测 46%，仍然有效且保留）。
「绘制中左键不旋转」现在由两条可靠证据承担：
  ① `进入绘制模式后 getRotateEnabled() === false`（**直接**证据）
  ② `绘制中的拖拽被当成拉框（发出了新的 within 请求）`（**行为**证据）
     —— ⚠️ 修复轮 5 把 ② 从"看 DOM 里有没有 stat-tracks"换成**数网络请求**：
     旧写法是**恒真**的（`App.startDraw` 不清 `withinStats`、`WithinStats` 根 div 没有 v-if），
     详见本文件顶部"修复轮 5"一节。
⚠️ 以后若看到"绘制中包围盒动了"，**不要去改 CesiumGlobe** —— 先读 D 段那段注释。
   📌 这条已经被**正式记为已知限制**：设计文档 `docs/superpowers/specs/2026-09-25-m3-within-design.md`
   第 10 节「已知限制」里的 **"极快甩动绘制后地球会轻微跳一下"**（含同一批实测数据与"不修"的理由）。

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
   setupState 里有 `setDrawingMode` 的实例。6 条直接读开关的断言：
   进档仍 `true` / 点拉框后 `false` / 拉框结束恢复 `true` / 再点拉框后 `false` / 切档后恢复 `true`。
   取不到组件实例时这些**自动 skip**，退回原来的间接判据。

两条老纪律（不要回退）：**真实时间等待**（Cesium 几何体在 worker 里异步生成，虚拟时钟会得到
"线不存在"的假象）；**面板右边界问 DOM 要**（面板宽度 `min(420px, 34vw)`，写死 `x>=400` 假红/假绿过）。

断言纪律：没有"永远为真"的判据；取文本/边界框前先判存在；前置状态不成立就 `skip` 不崩；
靠数据的断言在失败明细里带**实测值**；靠"页面有没有暴露 Cesium / 组件实例"的判据能降级就降级，
真正的功能判据（旋转开关、绘制中不旋转、零溢出、零报错）一条不少。
"""
import math
import os
import sys
import time
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

# ⭐ 修复轮 3：测"视野包围盒"之前必须先等相机稳定。
#    原因是 Cesium 拖拽松手后有**惯性余摆（inertiaSpin）**还会衰减几百毫秒，
#    在余摆中读到的"拖拽前包围盒"是假的 —— 修复轮 2 就是这样让 D 段读到 16.11% 的假位移
#    （同一时刻相机自身只动了 0.000097 弧度 ≈ 10 米，恰好证明旋转确实被关掉了）。
#    所以：**每个测量点都先用 wait_view_stable() 等停稳，再读那个基准值。**
STABLE_TIMEOUT_MS = 5000               # 等稳定的上限；超时就记一条诊断并继续（不判失败）
STABLE_POLL_MS = 200
STABLE_REL_EPS = 0.001                 # 连续两次读数位移 ÷ 视野跨度 < 0.1% 算"没动"
STABLE_NEED = 3                        # 连续 3 次稳定才算停稳（过滤单次抖动）

VIEWPORT = {"width": 1600, "height": 900}
SHORT_VIEWPORTS = ((1366, 660), (1600, 600))

# ⭐ 修复轮 6 新增：地图上最多叠画多少条命中轨迹（与 frontend/src/lib/region.js 的 DRAW_LIMIT 一致）。
#    "列表里有、地图上没画"的条目只有在命中数 > 它时才存在 —— 这是"点列表补画"那条链的前提。
DRAW_LIMIT = 20
# 缓冲区半径上限（backend application.yml 的 calcite.within.max-buffer-m）。
# 用它把北京全部轨迹一次罩住，从而**真实地**造出"命中 > DRAW_LIMIT"的场景。
BIG_BUFFER_M = 50000
# 等实体数增加的上限（点列表一条 → GET /api/tracks/{id} → 画线）
ENTITY_WAIT_MS = 10000

ok = 0
fail = 0
msgs = []          # 失败明细
skipped = []       # 因前置状态不成立而跳过的断言
notes = []         # 关键诊断值（报告要靠它判断失败原因）

errors = []        # pageerror + console.error 合起来（"控制台零报错"用它）
page_errors = []   # 只记 pageerror，单独看（切档断言用它）
console_errors = []
http_log = []      # 页面发出的每个请求 [(method, url)]（修复轮 5：数圈选请求，见 req_count）


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


# ---------------------------------------------------------------- 请求计数（修复轮 5）
# ⭐ 为什么不看 DOM 文本：`App.startDraw()` 只改 `drawingMode`、**不清 `withinStats`**，
#    而 `WithinStats.vue` 的根 div **没有 v-if**、`App.vue` 里也**无条件渲染**它 ——
#    于是"上一次查询的 stat-tracks"会一直留在 DOM 里。
#    后果：D 段拖拽**哪怕完全没被当成拉框**（地球被转了），
#    `count('[data-testid="stat-tracks"]') == 1` 也照样成立 → 那条 check 信息量为 0（恒真）。
#    所以改用**网络请求计数**：`POST /api/analysis/within` 的次数增加 ≥1，
#    既证明"这个手势被当成画区域、并真的发出了请求"，也不依赖任何 DOM 的新旧文本。
def on_request(req):
    """`page.on("request")` 的回调：只记账，**绝不抛异常**（事件回调里抛异常会打断验收）"""
    try:
        http_log.append((req.method, req.url))
    except Exception:                           # noqa: BLE001
        pass


def req_count(method=None, contains=None):
    """页面发出过多少个请求，可按方法（GET/POST）和 URL 片段过滤。

    `req_count("POST", "/api/analysis/within")` = 圈选查询一共发出去几次。
    """
    n = 0
    for m, u in http_log:
        if method is not None and m != method:
            continue
        if contains is not None and contains not in u:
            continue
        n += 1
    return n


def within_post_count():
    """圈选查询（`POST /api/analysis/within`）的累计次数 —— 判据用的就是它"""
    return req_count("POST", "/api/analysis/within")


def req_summary():
    """诊断一行：GET / POST 各多少次（多边形/缓冲区段失败时先看它）"""
    return (f"GET×{req_count('GET')} POST×{req_count('POST')}"
            f"（其中圈选 POST×{within_post_count()}）")


def wait_new_within_request(page, before, timeout_ms=10000, step=200):
    """等页面又发出了一次 `POST /api/analysis/within`。返回 (是否等到, 等了毫秒数)。

    这是"这一次手势真的被当成画区域了"的**直接证据**，比读 DOM 文本可靠：
    DOM 里的统计卡是上一次查询留下的，新旧文本又可能一模一样（命中数相同）。
    """
    t0 = time.time()
    while (time.time() - t0) * 1000 < timeout_ms:
        if within_post_count() > before:
            return True, int((time.time() - t0) * 1000)
        page.wait_for_timeout(step)
    return False, int((time.time() - t0) * 1000)


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


def within_stats_flex_shrink(page):
    """`.within-stats` 的 flex-shrink（**CSS 契约**，与命中条数无关）。

    ⭐ 为什么断这一条（修复轮 6）：Task 8 评审那个修法是把 `.within-stats` 加进
    `App.vue` 的 `.panel > div:not(...)` 白名单链 —— 那条规则给面板里**非白名单**的 div 设
    `flex: 0 0 auto`（即 `flex-shrink: 0`，不可收缩），加进白名单后它拿回默认的
    `flex-shrink: 1`（可收缩，内部 `.items` 才能滚动而不是把面板撑高）。
    这条契约在 0 条 / 3 条 / 232 条命中下**都成立**，正好补上
    "232 条时列表被裁"那个场景用真实数据不好构造的缺口。
    返回 '1' / '0'（字符串）或 None（元素不在 / 取不到）。

    ⚠️ 修复轮 7 的实测结论：白名单**早就生效**了 —— 两个矮视口 ×（有结果 / 无结果）
    四种组合实测 flex-shrink 都是 `'1'`。所以修复轮 6 挖出来的那两条
    "有结果溢出 99px / 159px"**与白名单无关**，不要再往那个方向修；
    真正的原因是 `.within-stats` 内部不可收缩的内容 + 圈选档的固定块
    超过了矮视口的面板可用高度 —— 分块数字由 `panel_breakdown()` 打印。
    """
    try:
        return page.evaluate("""() => {
            const el = document.querySelector('.within-stats');
            if (!el) return null;
            return getComputedStyle(el).flexShrink;
        }""")
    except Exception as e:                      # noqa: BLE001
        note(f"读 .within-stats 的 flex-shrink 失败：{type(e).__name__}: {e}")
        return None


def panel_breakdown(page):
    """把「面板为什么溢出」拆成可读的分块数字（**诊断用，不判通过/失败**）。

    ⭐ 修复轮 7 新增：只报一句"溢出 99px"没法定位，必须知道它花在哪几个块上。
    返回 {panel:{sh,ch,padTop,padBottom}, stats:{minHeight,height,flexBasis,flexShrink,
    offsetHeight,scrollHeight}, children:[{tag,cls,h,flex,minH}, ...]}；取不到返回 None。
    """
    try:
        return page.evaluate("""() => {
            const p = document.querySelector('.panel');
            if (!p) return null;
            const cs = getComputedStyle(p);
            const out = {
              panel: { sh: p.scrollHeight, ch: p.clientHeight,
                       padTop: cs.paddingTop, padBottom: cs.paddingBottom },
              stats: null, children: [],
            };
            const st = document.querySelector('.within-stats');
            if (st) {
              const s = getComputedStyle(st);
              out.stats = { minHeight: s.minHeight, height: s.height, flexBasis: s.flexBasis,
                            flexShrink: s.flexShrink, offsetHeight: st.offsetHeight,
                            scrollHeight: st.scrollHeight };
            }
            for (const c of p.children) {
              const s = getComputedStyle(c);
              out.children.push({
                tag: c.tagName.toLowerCase(),
                cls: (c.className && typeof c.className === 'string') ? c.className : '',
                h: c.offsetHeight, flex: s.flex, minH: s.minHeight,
              });
            }
            return out;
        }""")
    except Exception as e:                      # noqa: BLE001
        note(f"读面板分块高度失败：{type(e).__name__}: {e}")
        return None


def _fmt_breakdown(bd):
    """把 panel_breakdown() 压成一两行诊断文本（报告与失败明细直接抄它）。"""
    if not bd:
        return "面板分块：取不到（.panel 不在？）"
    parts = [f"{c['tag']}.{c['cls'] or '-'}={c['h']}px(flex:{c['flex']},minH:{c['minH']})"
             for c in bd["children"]]
    st = bd.get("stats")
    st_txt = ("取不到 .within-stats" if not st else
              f".within-stats offsetHeight={st['offsetHeight']} height={st['height']} "
              f"flexBasis={st['flexBasis']} flexShrink={st['flexShrink']} "
              f"minHeight={st['minHeight']} scrollHeight={st['scrollHeight']}")
    return (f"面板 scrollHeight={bd['panel']['sh']} clientHeight={bd['panel']['ch']} "
            f"(padding {bd['panel']['padTop']}/{bd['panel']['padBottom']})；{st_txt}；"
            f"直接子块：{' | '.join(parts)}")


def list_item_track_ids(page):
    """列表里当前有哪些条目（`[data-testid="within-item-<trackId>"]` 的后缀，int 列表）。

    用**界面上实际渲染出来的**条目，而不是"接口返回的前 N 条"：
    "列表里有、地球上没有"这件事必须按界面事实判定。
    """
    try:
        raw = page.eval_on_selector_all(
            '[data-testid^="within-item-"]',
            'els => els.map(e => (e.getAttribute("data-testid") || "").replace("within-item-", ""))')
        return [int(x) for x in raw if str(x).lstrip("-").isdigit()]
    except Exception as e:                      # noqa: BLE001
        note(f"读列表条目失败：{type(e).__name__}: {e}")
        return []


def within_entities(page):
    """数地球上的圈选实体：区域轮廓（id 以 `within-region` 开头）与命中轨迹（`within-track-` 开头）。

    ⭐ 为什么要有它（修复轮 6）：规格 9.5 要求「区域轮廓与命中轨迹**像素存在**」，
    而本脚本原来全文只数了底色 `(9,20,40)` 的像素、从没检查过这两类实体。
    后果是实打实的：提交 `0af523b`（点列表一条 → 地图上什么都不画，画线整条没写进去）
    **测试没抓住**，靠人读代码才发现。像素判据在 B 段那个尺度（相机贴到 5 公里级、
    离线底图是一片纯色）上极不敏感，所以这里取更硬的证据 —— **实体**：
    实体在 ⇔ CesiumGlobe 真的把 `region` / `withinTracks` 两个 prop 画进了地球。

    返回 {region, tracks, track_ids, why}；拿不到 Viewer 时 region/tracks = -1 并给出具体原因
    （`why` 非空时调用方一律 skip，不假红）。
    """
    try:
        return page.evaluate(r"""() => {
            %s
            const out = { region: 0, tracks: 0, track_ids: [], why: null };
            const inst = findGlobeInst();
            if (!inst) { out.why = '找不到 CesiumGlobe 组件实例（__vue_app__ 遍历失败）'; return out; }
            const found = findViewer(inst);
            const v = found && found.viewer;
            if (!v) { out.why = '拿不到 Viewer（试过 ' + JSON.stringify((found && found.tried) || [])
                                + '）'; return out; }
            let arr = [];
            try { arr = (v.entities && v.entities.values) ? Array.from(v.entities.values) : []; }
            catch (e) { out.why = '读 v.entities.values 失败：' + e; return out; }
            for (const e of arr) {
              let id = '';
              try { id = String(e && e.id); } catch (err) { continue; }
              if (id.indexOf('within-region') === 0) out.region += 1;
              else if (id.indexOf('within-track-') === 0) {
                out.tracks += 1;
                out.track_ids.push(id.slice('within-track-'.length));
              }
            }
            return out;
        }""" % GL_JS)
    except Exception as e:                      # noqa: BLE001
        note(f"圈选实体探针失败：{type(e).__name__}: {e}")
        return {"region": -1, "tracks": -1, "track_ids": [],
                "why": f"探针整体失败：{type(e).__name__}: {e}"}


def within_track_style(page, track_id):
    """读某条命中轨迹实体在地球上的**线宽**与**颜色** —— 列表点选 → 地球高亮的证据。

    选中样式由 `CesiumGlobe.drawWithinTracks` 决定：选中 = 宽 3 + `#7fd1ff`（亮蓝），
    未选中 = 宽 2 + `#ff9f45`（橙）。所以"点列表里的一条 → 地图上那条变亮"是可读的。
    读不到（实体不存在 / 属性取不出来）时 `ok=False`，调用方 skip 而不是假红。
    """
    try:
        return page.evaluate(r"""([trackId]) => {
            %s
            const out = { ok: false, why: null, width: null, rgb: null, found: false };
            const inst = findGlobeInst();
            if (!inst) { out.why = '找不到 CesiumGlobe 组件实例'; return out; }
            const found = findViewer(inst);
            const v = found && found.viewer;
            if (!v) { out.why = '拿不到 Viewer'; return out; }
            let e = null;
            try { e = v.entities.getById('within-track-' + trackId); } catch (err) {}
            if (!e) { out.why = '地球上没有 id=within-track-' + trackId + ' 的实体'; return out; }
            out.found = true;
            const t = v.clock.currentTime;
            const read = function (prop) {
              try {
                if (prop === undefined || prop === null) return null;
                if (typeof prop.getValue === 'function') return prop.getValue(t);
                return prop;
              } catch (err) { return null; }
            };
            const w = read(e.polyline && e.polyline.width);
            if (typeof w === 'number' && isFinite(w)) out.width = w;
            const mat = e.polyline && e.polyline.material;
            const c = read(mat && mat.color);
            if (c && typeof c.red === 'number') out.rgb = [c.red, c.green, c.blue];
            out.ok = true;
            return out;
        }""" % GL_JS, [str(track_id)])
    except Exception as e:                      # noqa: BLE001
        note(f"读 within-track-{track_id} 的样式失败：{type(e).__name__}: {e}")
        return {"ok": False, "why": f"探针失败：{type(e).__name__}: {e}", "width": None, "rgb": None}


def _is_selected_style(st):
    """这条线是不是"选中样式"：宽 3 或 颜色 = #7fd1ff（≈ [0.498, 0.820, 1.0]）。"""
    if st.get("width") == 3:
        return True
    rgb = st.get("rgb")
    return bool(rgb) and rgb[2] > 0.9 and rgb[1] > 0.7 and rgb[0] < 0.7


def draw_big_buffer(page):
    """在**当前视口**下用最大半径缓冲区查一次（"有结果且列表里真的有条目"的场景制造器）。

    用途一（A2 段）：初始相机正对北京上空时，50 公里缓冲区罩住北京全部轨迹 →
    命中数远超 DRAW_LIMIT(20) → 列表里存在"地图上没画出来"的条目，`onWithinSelect`
    的补画分支才有东西可点。
    用途二（G 段）：在矮视口下量"有结果时面板零溢出"，而不是只量空面板。

    ⚠️ 画布与面板的几何**每个视口都要重新取**（面板宽度 `min(420px, 34vw)`、画布尺寸都会变），
    并且中心点要避开底部的速度曲线与播放条 —— 它们是 DOM 浮层，盖在画布上，事件到不了地球。
    返回 (state, 列表条目数, 诊断文本)；段内异常返回 (None, 0, 原因)，绝不抛。
    """
    try:
        if count_of(page, '[data-testid="draw-buffer"]') != 1:
            return None, 0, "draw-buffer 按钮不存在"
        cb = page.locator("canvas").first.bounding_box()
        pb = page.locator(".panel").bounding_box()
        if not cb or not pb:
            return None, 0, "取不到 canvas / .panel 的边界框"
        pr = pb["x"] + pb["width"]
        cx = max(cb["x"] + cb["width"] / 2, pr + 40)
        cy = cb["y"] + min(cb["height"] * 0.45, max(60.0, cb["height"] - 220))
        page.click('[data-testid="draw-buffer"]')
        page.wait_for_timeout(300)
        page.fill('[data-testid="buffer-m"]', str(BIG_BUFFER_M))
        page.wait_for_timeout(200)
        req_before = within_post_count()
        page.mouse.click(cx, cy)
        page.wait_for_timeout(600)
        got, waited = wait_new_within_request(page, req_before, timeout_ms=15000)
        state, txt = wait_result(page, timeout_ms=20000)
        items = len(list_item_track_ids(page))
        return state, items, (f"中心 ( {cx:.0f},{cy:.0f} ) / 画布 {cb['width']:.0f}x{cb['height']:.0f} / "
                              f"面板右 {pr:.0f}；半径 {BIG_BUFFER_M}m；"
                              f"圈选请求 {req_before} → {within_post_count()}"
                              f"（等新请求 {waited}ms/{got}）；状态={state} 文本={txt!r}")
    except Exception as e:                      # noqa: BLE001
        return None, 0, f"段内异常：{type(e).__name__}: {e}"


# ---------------------------------------------------------------- 页面侧探针
# 下面几个 JS 遵守同一条纪律：取不到就返回 null / 空数组，绝不抛异常打断验收。
#
# ⚠️ 取 viewer 的两条路径（修复轮 2 才找对）：
#   ① `inst.exposed`  —— 只有 defineExpose 里列出的方法（getRotateEnabled / getViewBbox / …）
#      **没有 viewer**；② `inst.setupState.viewer` —— `<script setup>` 的顶层绑定，
#      dev 模式下就挂在 setupState 上，**这才是 Viewer**（主控探针实测 hasScene: true、
#      viewerType "Viewer"）。所以这里把**组件实例本身**交给后面用，两条路径都留着。
#   ⚠️ ② 依赖 Vue 的 dev 内部态：生产构建（压缩后）可能取不到 —— 取不到一律 skip，不假红。
GL_JS = r"""
function findGlobeInst() {
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
      if (st && typeof st.setDrawingMode === 'function') return inst;
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
// 组件公开实例（defineExpose 的对象）—— getRotateEnabled / getViewBbox 在这里
function globeApi(inst) {
  try {
    const st = inst && inst.setupState;
    if (inst && inst.exposed && typeof inst.exposed === 'object') return inst.exposed;
    return st || null;
  } catch (e) { return null; }
}
// Viewer：按 setupState.viewer → setupState._viewer → exposed.viewer → exposed.scene
// 依次试（ref 要解包 .value），命中要求同时有 scene / camera / canvas。
function findViewer(inst) {
  if (!inst) return null;
  const tried = [];
  const paths = [
    ['setupState.viewer', function () { return inst.setupState && inst.setupState.viewer; }],
    ['setupState._viewer', function () { return inst.setupState && inst.setupState._viewer; }],
    ['exposed.viewer', function () { return inst.exposed && inst.exposed.viewer; }],
    ['ctx.viewer', function () { return inst.ctx && inst.ctx.viewer; }],
  ];
  for (const [name, get] of paths) {
    try {
      let v = get();
      if (v && v.value) v = v.value;
      if (v && v.scene && v.camera) return { viewer: v, path: name };
      tried.push(name + '=' + (v === undefined ? 'undefined' : (v === null ? 'null' : typeof v)));
    } catch (e) { tried.push(name + '=throw'); }
  }
  return { viewer: null, path: null, tried: tried };
}
// ⭐ 修复轮 5：投影**不能**再依赖全局 `Cesium` —— 页面里根本没有它
//   （index.html 只加载 main.js，组件用具名 import，vite 只 define 了 CESIUM_BASE_URL），
//   旧写法 `typeof Cesium !== 'undefined'` 恒为 false，于是"实体投影点"永远是 0、
//   拉框锚点永远回退画布中心，却打印"Viewer 未就绪"（误导：Viewer 是好的）。
//   改用 Cesium 1.145 里**确实存在**的两件事：
//     ① `viewer.entities.values` —— `entities` 是 **Viewer** 的属性（Scene 没有！）
//     ② `scene.cartesianToCanvasCoordinates(position)` —— **Scene 自带**的投影方法
//        （node_modules/cesium/Source/Cesium.d.ts:45150，class Scene 的成员；
//         不需要 Cesium.SceneTransforms 这个静态命名空间）
function sceneProjector(v) {
  try {
    const s = v && v.scene;
    if (!s) return null;
    if (typeof s.cartesianToCanvasCoordinates === 'function') {
      return { how: 'scene.cartesianToCanvasCoordinates',
               f: function (p) { return s.cartesianToCanvasCoordinates(p); } };
    }
  } catch (e) {}
  return null;
}
// 经纬度（度）→ Cartesian3：同样不依赖全局 Cesium —— Ellipsoid 实例上的
// cartographicToCartesian 接受**普通对象** {longitude, latitude, height}（弧度，鸭子类型，
// 见 Build/CesiumUnminified/index.js:23890 的 geodeticSurfaceNormalCartographic）。
function lonLatToCartesian(v, lon, lat) {
  try {
    const ell = v && v.scene && v.scene.globe && v.scene.globe.ellipsoid;
    if (!ell || typeof ell.cartographicToCartesian !== 'function') return null;
    const R = Math.PI / 180;
    return ell.cartographicToCartesian({ longitude: lon * R, latitude: lat * R, height: 0 });
  } catch (e) { return null; }
}
"""


def globe_probe(page):
    """一次 JS 往返拿回全部页面侧信息（少往返 = 少失败点）：
      have_globe  找到 CesiumGlobe 组件实例了吗
      keys        exposed 上有哪些方法（诊断用，拿不到 viewer 时看它）
      viewer_path 拿到 Viewer 走的是哪条路径（或试过哪些路径都失败）
      rotate      getRotateEnabled() → true / false / null
      cam         {lon, lat, h}（弧度 / 弧度 / 米）
      bbox        getViewBbox() 的 {west, south, east, north}（度）—— 不依赖 viewer
      points      带 position 的实体投影到窗口的坐标（最多 200 个）
    """
    try:
        return page.evaluate(r"""() => {
            %s
            const inst = findGlobeInst();
            const g = globeApi(inst);
            const out = { have_globe: !!inst, has_api: !!g, rotate: null, keys: [],
                          viewer_path: null, viewer_tried: [], cam: null, bbox: null,
                          proj_how: null, points: [] };
            if (!inst) return out;
            if (g) {
              out.keys = Object.keys(g);
              if (typeof g.getRotateEnabled === 'function') {
                const r = g.getRotateEnabled();
                out.rotate = (r === true || r === false) ? r : null;
              }
              if (typeof g.getViewBbox === 'function') {
                try { out.bbox = g.getViewBbox(); } catch (e) {}
              }
            }
            const found = findViewer(inst);
            out.viewer_path = found ? (found.path || null) : null;
            out.viewer_tried = found && found.tried ? found.tried : [];
            const v = found && found.viewer;
            if (!v) return out;
            const s = v.scene;
            try {
              const c = v.camera.positionCartographic;
              if (c && isFinite(c.height)) out.cam = { lon: c.longitude, lat: c.latitude, h: c.height };
            } catch (e) {}
            // ⭐ 修复轮 5：实体从 **Viewer** 上取（v.entities），投影用 **Scene 自带方法**。
            //    旧代码用全局 Cesium.SceneTransforms + s.entities.values（Scene 没有 entities）
            //    → 恒为死代码，投影点永远 0。拿不到就返回 proj_how=null，由调用方明确降级。
            const proj = sceneProjector(v);
            out.proj_how = proj ? proj.how : null;
            if (!proj) return out;
            try {
              const rect = s.canvas.getBoundingClientRect();
              const arr = (v.entities && v.entities.values) ? v.entities.values : [];
              for (let i = 0; i < arr.length && out.points.length < 200; i++) {
                const e = arr[i];
                if (!e || !e.position || typeof e.position.getValue !== 'function') continue;
                const t = e.position.getValue(v.clock.currentTime);
                if (!t) continue;
                const w = proj.f(t);
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
        return {"have_globe": False, "has_api": False, "rotate": None, "keys": [],
                "viewer_path": None, "viewer_tried": [], "cam": None, "bbox": None,
                "proj_how": None, "points": []}


def globe_rotate(page):
    """只读「左键旋转」开关：True / False / None（组件拿不到、或 viewer 没就绪）。

    ⚠️ 这是 Task 9 的 `getRotateEnabled()`（defineExpose 暴露）——
    比"像素变没变"和"有没有出结果"都硬。
    """
    return globe_probe(page)["rotate"]


def bbox_center(bbox):
    """视图包围盒 → (中心经度, 中心纬度)；拿不到或不是有限数就返回 None"""
    if not bbox:
        return None
    try:
        w, e = float(bbox["west"]), float(bbox["east"])
        s, n = float(bbox["south"]), float(bbox["north"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in (w, e, s, n)):
        return None
    return ((w + e) / 2.0, (s + n) / 2.0)


def bbox_shift_ratio(b0, b1):
    """两次视野包围盒之间**中心位移 ÷ 视野跨度**（无量纲，与缩放无关）。

    为什么用它当"地球转没转"的硬判据：
      - **与缩放无关**：飞机飞到 5 公里级时，离线底图 NaturalEarthII 是一片纯色，
        转不转**像素几乎不变**（实测像素差 66）—— 像素判据在"已放大"场景天然失效；
        而包围盒中心一定跟着转（实测移动了视野宽度的 34%）。
      - 位移按**两个方向分别算比例再取大者**，避免经度/纬度跨度差一个数量级时被稀释。
    返回 (ratio, 经度比例, 纬度比例) 或 None。
    """
    c0, c1 = bbox_center(b0), bbox_center(b1)
    if c0 is None or c1 is None:
        return None
    span_lon = abs(float(b0["east"]) - float(b0["west"]))
    span_lat = abs(float(b0["north"]) - float(b0["south"]))
    if span_lon <= 0 or span_lat <= 0:
        return None
    r_lon = abs(c1[0] - c0[0]) / span_lon
    r_lat = abs(c1[1] - c0[1]) / span_lat
    return max(r_lon, r_lat), r_lon, r_lat


def view_bbox(page):
    """轻量地只取一次 `getViewBbox()`（轮询用；失败返回 None，绝不抛异常）"""
    try:
        return page.evaluate(r"""() => {
            %s
            const g = globeApi(findGlobeInst());
            if (!g || typeof g.getViewBbox !== 'function') return null;
            try { return g.getViewBbox(); } catch (e) { return null; }
        }""" % GL_JS)
    except Exception:                           # noqa: BLE001
        return None


def _bbox_short(bbox):
    """一行的包围盒摘要（诊断用，别把整串小数全打出来）"""
    if not bbox:
        return "null"
    try:
        return (f"[{bbox['west']:.5f},{bbox['east']:.5f}]x"
                f"[{bbox['south']:.5f},{bbox['north']:.5f}]")
    except (KeyError, TypeError):
        return "非法"


def wait_view_stable(page, label, timeout_ms=STABLE_TIMEOUT_MS):
    """等相机/视野**停稳**再测量，返回 (bbox, waited_ms, stable)。

    ⭐ 为什么必须有这一步（修复轮 3）：
      Cesium 拖拽松手后左键旋转有**惯性余摆（inertiaSpin）**，会继续衰减几百毫秒。
      若在余摆过程中读"拖拽前"的包围盒，它就是个**运动中的值** —— 等会儿再读"拖拽后"
      就会凭空多出一段位移。修复轮 2 的 D 段失败（16.11% vs 阈值 3%）就是这么来的：
      同一时刻**相机自身**只动了 0.000097 弧度（≈10 米），证明左键旋转确实被关掉了，
      动的是"上一段 C 拖拽留下的余摆"。

    判据：连续 STABLE_NEED 次读数两两之间 `位移 ÷ 视野跨度 < STABLE_REL_EPS`（0.1%）。
    超时不算失败 —— 只把"等了多少毫秒 / 是否稳定"打进诊断（调用方各自决定怎么办）。
    """
    t0 = time.time()
    last = None
    hits = 0
    readings = []
    while True:
        b = view_bbox(page)
        readings.append(b)
        if len(readings) > 8:
            readings.pop(0)
        if b and last:
            r = bbox_shift_ratio(last, b)
            if r is not None and r[0] < STABLE_REL_EPS:
                hits += 1
                if hits >= STABLE_NEED - 1:
                    waited = int((time.time() - t0) * 1000)
                    note(f"视野稳定：{label} 等了 {waited} ms，"
                         f"末次读数 {_bbox_short(b)}")
                    return b, waited, True
            else:
                hits = 0
        last = b
        if (time.time() - t0) * 1000 >= timeout_ms:
            waited = int((time.time() - t0) * 1000)
            note(f"⚠️ 视野未在 {waited} ms 内稳定：{label}；"
                 f"最后几次读数 = {[ _bbox_short(x) for x in readings[-4:] ]}"
                 f"（若后续位移断言红了，先看这里 —— 可能是惯性还没停，也可能是真被转了）")
            return last, waited, False
        page.wait_for_timeout(STABLE_POLL_MS)


def _screen_of(page, lon, lat):
    """（尽力而为）经纬度 → 窗口坐标，只用于诊断输出。

    ⭐ 修复轮 5：**不再依赖全局 `Cesium`**（页面里没有它，旧写法恒为 false → 永远"取不到"，
    却打印"Viewer 未就绪"，把人带偏：Viewer 其实是好的）。
    返回 `{'ok': True, x, y, w, h, on}` 或 `{'ok': False, 'why': '具体原因'}`；
    页面内 JS 整个失败时返回 None。
    """
    try:
        return page.evaluate(r"""([lon, lat]) => {
            %s
            const inst = findGlobeInst();
            const found = findViewer(inst);
            const v = found && found.viewer;
            if (!v) return { ok: false, why: '拿不到 Viewer（试过的路径 '
                              + JSON.stringify((found && found.tried) || []) + '）' };
            const proj = sceneProjector(v);
            if (!proj) return { ok: false,
              why: '拿不到 Scene 的投影函数 scene.cartesianToCanvasCoordinates' };
            const cart = lonLatToCartesian(v, lon, lat);
            if (!cart) return { ok: false,
              why: '拿不到 scene.globe.ellipsoid.cartographicToCartesian' };
            const rect = v.scene.canvas.getBoundingClientRect();
            const win = proj.f(cart);
            if (!win) return { ok: false, why: '这一点的投影结果为空（在地球背面 / 球心附近）' };
            return { ok: true, x: win.x + rect.left, y: win.y + rect.top,
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
        # ⭐ 修复轮 5：数圈选请求（判据用，见 req_count 的注释）
        page.on("request", on_request)

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
        note(f"Viewer 路径 viewer_path={pr0['viewer_path']}；"
             f"试过的路径={pr0['viewer_tried']}")
        note(f"初始相机 = {_fmt_cam(pr0['cam'])}；rotate={pr0['rotate']}；"
             f"视野 = {_bbox_txt(pr0['bbox'])}")
        if not pr0["have_globe"]:
            note("⚠️ 找不到 CesiumGlobe 组件实例（__vue_app__ 遍历失败）："
                 "6 条 getRotateEnabled 硬判据会 skip，退回像素/结果间接判据")
        if pr0["cam"] is None:
            note("⚠️ 拿不到 Viewer —— 已试 setupState.viewer / setupState._viewer / "
                 "exposed.viewer / ctx.viewer（见上一行 tried）。"
                 "实体投影点会为空（拉框回退画布中心）；"
                 "「点列表后相机飞近了」与「绘制中不旋转（相机位移）」两条会 skip。"
                 "视野包围盒不依赖 Viewer，仍可用（getViewBbox）")
        # ⭐ 修复轮 5：投影可用性必须**说清楚走的是哪条能力**，不能再打
        #    "取不到（Viewer 未就绪）" 这种"看起来像环境没就绪"的误导文案。
        if pr0["proj_how"]:
            note(f"实体投影可用：{pr0['proj_how']}"
                 "（页面里没有全局 Cesium → 实体取 v.entities.values、投影用 Scene 自带方法）")
        else:
            note("实体投影不可用（原因：拿不到 Scene 的投影函数 "
                 "scene.cartesianToCanvasCoordinates），拉框锚点使用画布中心（设计如此）")
        for name, lon, lat in (("北京", 116.40, 39.90), ("上海", 121.47, 31.23)):
            s = _screen_of(page, lon, lat)
            if s is None:
                note(f"{name} 屏幕坐标：探针整个失败（页面内 JS 抛异常，见上面的页面探针日志）")
            elif not s.get("ok"):
                note(f"{name} 屏幕坐标不可用（{s.get('why')}）")
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

        # ------------------------------------------------ A2) 全局视野缓冲区：造出「命中 > DRAW_LIMIT」的真实场景
        # ⭐ 修复轮 6 新增（规格 9.5 的"区域轮廓 + 命中轨迹画在地球上"与"列表↔地图联动"）。
        #
        # 为什么必须有这一段：B 段先把相机飞到列表第一条轨迹（**福建，附近一共只有 3 条**），
        # 那里拉框只能命中 3 条 —— 而地图默认把**前 20 条**（DRAW_LIMIT）全画出来，
        # 于是"点列表里没画出来的条目 → 补画到地图上"这条链**永远没有可点的条目**，
        # 只能记 skip（= 等于没验）。而"命中条数超过 DRAW_LIMIT"正是设计里
        # "列表被裁、需要点列表补画"的真实场景。
        #
        # 初始相机（CesiumGlobe onMounted 的 setView）停在 12000 公里、正对北京上空，
        # 画布中心就是 (116.4, 39.9)：一个 50 公里缓冲区（calcite.within.max-buffer-m）
        # 足以罩住北京全部轨迹，福建那 3 条在 1665 公里外、不会被算进来 ——
        # 命中数远超 DRAW_LIMIT(20)，于是列表里有条目、地球上只画了 20 条。
        #
        # ⚠️ 这一段刻意放在 B 段**之前**：B/C/D 段的判据全部建立在"相机贴在某条轨迹上"
        # 这个尺度上（C 段那条"拖拽后地球确实动了 ≥8% 视野跨度"尤其是），
        # 在它们之后挪相机会把 C 段的基准污染掉。
        print("=== A2) 全局视野缓冲区：命中 > DRAW_LIMIT 的真实场景 ===")
        a2_done = False
        a2_items = []
        a2_ent = {"region": -1, "tracks": -1, "track_ids": [], "why": "A2 段没跑"}
        a2_state, a2_txt = None, ""
        if count_of(page, '[data-testid="draw-buffer"]') != 1:
            skip("A2) 全局视野下的 50 公里缓冲区查出了结果", "draw-buffer 按钮不存在")
        else:
            try:
                page.click('[data-testid="draw-buffer"]')
                page.wait_for_timeout(300)
                page.fill('[data-testid="buffer-m"]', str(BIG_BUFFER_M))
                page.wait_for_timeout(200)
                bm_now = page.input_value('[data-testid="buffer-m"]')
                ccx = canvas["x"] + canvas["width"] / 2
                ccy = canvas["y"] + canvas["height"] / 2
                note(f"A2 段：半径输入框 = {bm_now}（期望 {BIG_BUFFER_M}，即 calcite.within.max-buffer-m）；"
                     f"缓冲区中心 = 画布中心 ( {ccx:.0f},{ccy:.0f} )"
                     "（初始相机正对北京上空 116.4,39.9）")
                req_before_a2 = within_post_count()
                page.mouse.click(ccx, ccy)
                page.wait_for_timeout(600)
                got_a2, waited_a2 = wait_new_within_request(page, req_before_a2, timeout_ms=15000)
                req_after_a2 = within_post_count()
                a2_state, a2_txt = wait_result(page, timeout_ms=20000)
                a2_items = list_item_track_ids(page)
                a2_ent = within_entities(page)
                note(f"A2 段：状态={a2_state} stat-tracks={a2_txt!r}；列表条目 {len(a2_items)} 条；"
                     f"地球上的命中轨迹实体 {a2_ent['tracks']} 条 / 区域实体 {a2_ent['region']} 个；"
                     f"圈选请求 {req_before_a2} → {req_after_a2}"
                     f"（等新请求 {waited_a2}ms/{got_a2}）；{req_summary()}")
                check("A2) 全局视野下的 50 公里缓冲区查出了结果",
                      (req_after_a2 - req_before_a2) >= 1
                      and (count_of(page, '[data-testid="stat-tracks"]') == 1
                           or count_of(page, '[data-testid="within-empty"]') == 1),
                      f"状态={a2_state} 文本={a2_txt!r}；圈选请求计数 {req_before_a2} → {req_after_a2}"
                      f"（新增 {req_after_a2 - req_before_a2}，期望 ≥1）"
                      "；新增 0 = 这一击没被当成缓冲区中心（点在球外 / 没进绘制模式）")
                a2_done = True
            except Exception as e:              # noqa: BLE001
                note(f"A2 段自身出错：{type(e).__name__}: {e}")
                skip("A2) 全局视野下的 50 公里缓冲区查出了结果",
                     f"段内异常：{type(e).__name__}: {e}")

        # ------------------------------------------------ A2b) 点列表里"没画出来"的条目 → 地图补画
        # ⭐ 这条是 `onWithinSelect` 的**行为证据**（提交 0af523b 那条链：点列表一条 → 地图补画）。
        # 判据：点之前地球上 within-track-* 实体数 N → 点之后 N+1。
        if not a2_done:
            skip("A2b) 点列表里没画出来的条目 → 地图补画一条", "A2 段没跑成（见上面那条）")
        elif a2_ent["why"]:
            skip("A2b) 点列表里没画出来的条目 → 地图补画一条",
                 f"拿不到实体（{a2_ent['why']}）—— 没有可靠的办法读'已画几条'")
        elif not a2_items:
            skip("A2b) 点列表里没画出来的条目 → 地图补画一条",
                 f"列表里一条都没有（状态={a2_state} 文本={a2_txt!r}）—— 这一击没命中任何轨迹")
        else:
            drawn_a2 = set(str(x) for x in a2_ent["track_ids"])
            undrawn_a2 = [i for i in a2_items if str(i) not in drawn_a2]
            if not undrawn_a2:
                skip("A2b) 点列表里没画出来的条目 → 地图补画一条",
                     f"命中的 {len(a2_items)} 条**全部**已经画在地球上了"
                     f"（列表 {a2_items}，已画 {sorted(drawn_a2, key=lambda s: int(s) if s.lstrip('-').isdigit() else 0)}）"
                     f"—— 命中数 ≤ DRAW_LIMIT({DRAW_LIMIT}) 时不存在「没画出来」的条目，这条只能跳过；"
                     "先看上面 A2 段那行的列表条目数（期望 > 20）与相机尺度")
            else:
                target_a2 = undrawn_a2[0]
                before_n = a2_ent["tracks"]
                click_err_a2 = ""
                try:
                    page.click(f'[data-testid="within-item-{target_a2}"]')
                except Exception as e:          # noqa: BLE001
                    # 点不动（被别的元素挡住 / 元素不在视口）是脚本/环境问题，不当功能判据
                    click_err_a2 = f"{type(e).__name__}: {e}"
                    note(f"A2b 段：点 within-item-{target_a2} 失败 —— {click_err_a2}")
                after_a2 = a2_ent
                spent_a2 = 0
                if not click_err_a2:
                    while spent_a2 < ENTITY_WAIT_MS:
                        page.wait_for_timeout(400)
                        spent_a2 += 400
                        after_a2 = within_entities(page)
                        if after_a2["tracks"] > before_n:
                            break
                note(f"A2b 段：点 within-item-{target_a2}（列表 {len(a2_items)} 条、"
                     f"点前已画 {before_n} 条 → 点后 {after_a2['tracks']} 条，等了 {spent_a2}ms）；"
                     f"点前已画 id={sorted(drawn_a2, key=lambda s: int(s) if s.lstrip('-').isdigit() else 0)}；"
                     f"点后实体探针 why={after_a2['why']}")
                if click_err_a2:
                    skip("A2b) 点列表里没画出来的条目 → 地图上补画一条（within-track-* 实体数 +1）",
                         f"点 within-item-{target_a2} 时抛异常（{click_err_a2}）—— 脚本没点到，"
                         "不是「点列表不补画」，故跳过（诊断见上一行）")
                else:
                    check("A2b) 点列表里没画出来的条目 → 地图上补画一条（within-track-* 实体数 +1）",
                          after_a2["tracks"] > before_n,
                          f"点的是 within-item-{target_a2}；点前地球上已有 {before_n} 条 "
                          f"within-track-* 实体（列表共 {len(a2_items)} 条，"
                          f"没画出来的 {len(undrawn_a2)} 条：{undrawn_a2[:5]}）→ 点后 {after_a2['tracks']} 条"
                          f"（期望 > {before_n}，等了 {spent_a2}ms）；"
                          "点后仍相等 = onWithinSelect → loadWithinDetail 那条链断了"
                          "（0af523b 就是它：`loadWithinDetail(ids)` 漏传序号时守卫恒真、直接 return）")

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
                # ⭐ 修复轮 3 采集点①：flyTo 动画结束后等停稳，再读相机高度与实体投影点
                wait_view_stable(page, "点完第一条轨迹（flyTo 后）")
                pr_fly = globe_probe(page)
                cam_after_fly = pr_fly["cam"]
                note(f"点第一条轨迹后：相机 {_fmt_cam(cam_after_fly)}；"
                     f"视野 {_bbox_txt(pr_fly['bbox'])}；"
                     f"实体投影点 {len(pr_fly['points'])} 个"
                     f"（投影方式 {pr_fly['proj_how'] or '不可用'}）")
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
                     f"（投影方式 proj_how={pr_fly['proj_how']}；"
                     "为 None 时看上面「实体投影不可用（原因…）」那行——"
                     "**不要**再怀疑 Viewer：页面里没有全局 Cesium，旧版那句"
                     "「Viewer 未就绪」是错的）。"
                     "若命中 0 条，先看上面「相机/视野/实体投影点」三行与 .tmp/shot-within.png")
            x0, y0, x1, y1 = anchor
            note(f"B 段拉框：( {x0},{y0} ) → ( {x1},{y1} ) 大小 {x1 - x0}x{y1 - y0}px")
            if not in_viewport(anchor):
                note(f"⚠️ 拖拽坐标超出视口 ({x0},{y0})→({x1},{y1})："
                     "拖出画面 Cesium 收不到 mouseup，这一笔作废（命中 0 条时先看这里）")

            # ⭐ 修复轮 6：B 段也数网络请求。
            #    原来这里那条 `统计卡出现（within-stats）` 是**恒真断言**：
            #    `WithinStats.vue` 的根 div 没有 v-if、`App.vue` 里也无条件渲染它，
            #    所以无论这次拉框有没有生效，它都在 —— 信息量为 0。
            #    换成与 D/E/E2 段同款的"POST /api/analysis/within 计数增加 ≥1"：
            #    这既证明这次手势被当成画区域，也证明请求真的发出去了，且完全不看 DOM 新旧文本。
            req_before_b = within_post_count()
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
            got_req_b, req_waited_b = wait_new_within_request(page, req_before_b, timeout_ms=10000)
            req_after_b = within_post_count()
            # ⭐ 修复轮 6：等**这一次**查询收尾再读结果。
            #    原因：A2 段在 DOM 里留了一张旧统计卡，而 `wait_result` 一看到 stat-tracks
            #    就立刻返回 —— 不等这次收尾就会把 A2 的旧文本当成 B 段的结果
            #    （B2 段要看的"命中 3 条时画在地球上的实体"也会变成 A2 那批实体）。
            #    收尾信号用 `draw-hint` 的"查询中…"（withinBusy 在 fetch 之前就置 true，
            #    所以 wait_new_within_request 返回时它一定已经亮了）。
            spent_busy_b = 0
            while spent_busy_b < 8000:
                if not try_text(page, '[data-testid="draw-hint"]').startswith("查询中"):
                    break
                page.wait_for_timeout(200)
                spent_busy_b += 200
            state, txt = wait_result(page)
            note(f"B 段查询收尾状态 = {state}，stat-tracks 文本 = {txt!r}；"
                 f"圈选请求 {req_before_b} → {req_after_b}"
                 f"（等新请求 {req_waited_b}ms/{got_req_b}，等收尾 {spent_busy_b}ms）；"
                 f"{req_summary()}")

            rot_after_draw = globe_rotate(page)
            if rot_after_draw is None:
                skip("拉框结束后左键旋转恢复（getRotateEnabled = true）", "拿不到开关值")
            else:
                check("拉框结束后左键旋转恢复（getRotateEnabled = true）",
                      rot_after_draw is True,
                      f"getRotateEnabled() = {rot_after_draw}（松手即退出绘制，期望 true）")

            check("B) 拉框手势真的发起了圈选查询（POST /api/analysis/within 计数增加 ≥1）",
                  (req_after_b - req_before_b) >= 1,
                  f"圈选请求计数 {req_before_b} → {req_after_b}"
                  f"（新增 {req_after_b - req_before_b}，期望 ≥1）"
                  "；新增 0 = 这次拖拽没被当成拉框（地球被转了 / 拖出画面）"
                  f"；{req_summary()}")
            note(f"B 段统计卡容器 within-stats × "
                 f"{count_of(page, '[data-testid=\"within-stats\"]')}"
                 "（它没有 v-if、恒在，所以不作为判据 —— 见上面那条请求计数）")
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

        # ------------------------------------------------ B2) 区域轮廓 / 命中轨迹的**实体**证据 + 列表↔地图高亮
        # ⭐ 修复轮 6 新增（规格 9.5 的「区域轮廓与命中轨迹像素存在」）。
        #    旧脚本全文只数了底色 `(9,20,40)`，**从没**检查过 `within-region` /
        #    `within-track-*` 实体，也从没点过 `within-item-*` —— 提交 0af523b
        #    （点列表一条 → 地图上什么都不画）就是这么漏过去的，靠人读代码才发现。
        #    像素判据在这里天然不灵（相机贴在 5 公里级，离线底图是一片纯色），
        #    所以判据换成**实体集合**：实体在 ⇔ CesiumGlobe 真把两个 prop 画进了地球。
        print("=== B2) 区域轮廓 / 命中轨迹的实体证据 + 列表↔地图高亮 ===")
        ent_b = within_entities(page)
        note(f"B 段结果的实体：区域 {ent_b['region']} 个（轮廓面 + 边线，正常为 2）、"
             f"命中轨迹 {ent_b['tracks']} 条 id={ent_b['track_ids']}；why={ent_b['why']}")
        if ent_b["why"]:
            skip("B2) 区域轮廓真的画在地球上（within-region* 实体 ≥1）", ent_b["why"])
            skip("B2) 命中轨迹真的画在地球上（within-track-* 实体 ≥1）", ent_b["why"])
            skip("B2) 点列表里已画的那条 → 地图上变选中样式", ent_b["why"])
        else:
            if prev_tracks_text is None:
                skip("B2) 区域轮廓真的画在地球上（within-region* 实体 ≥1）",
                     "B 段没拿到命中数（框没框到轨迹 —— 脚本坐标问题），实体本就不该出现")
                skip("B2) 命中轨迹真的画在地球上（within-track-* 实体 ≥1）",
                     "B 段没拿到命中数（框没框到轨迹）")
            else:
                check("B2) 区域轮廓真的画在地球上（within-region* 实体 ≥1）",
                      ent_b["region"] >= 1,
                      f"region 实体={ent_b['region']} 个（drawRegion 成功时应为 2：半透明面 + 边线）；"
                      f"B 段命中 {prev_tracks_text!r} 条")
                check("B2) 命中轨迹真的画在地球上（within-track-* 实体 ≥1）",
                      ent_b["tracks"] >= 1,
                      f"within-track-* 实体={ent_b['tracks']} 条（地图上该画的条数，"
                      f"最多 DRAW_LIMIT={DRAW_LIMIT}）；区域实体={ent_b['region']} 个；"
                      f"B 段命中 {prev_tracks_text!r} 条 —— 实体为 0 而 stat-tracks 有数字，"
                      "就是 0af523b 那类「统计对、地图上什么都没画」的断链")

            # 列表点选 → 地球高亮（与命中条数无关，只要地球上画了至少一条就能验）
            drawn_b = [int(x) for x in ent_b["track_ids"] if str(x).lstrip("-").isdigit()]
            if not drawn_b:
                skip("B2) 点列表里已画的那条 → 地图上变选中样式",
                     "地球上一条 within-track-* 实体都没有，没有可验的高亮对象")
            else:
                target_b = drawn_b[0]
                st0 = within_track_style(page, target_b)
                click_err_b = ""
                try:
                    page.click(f'[data-testid="within-item-{target_b}"]')
                    page.wait_for_timeout(800)
                except Exception as e:          # noqa: BLE001
                    click_err_b = f"{type(e).__name__}: {e}"
                st1 = within_track_style(page, target_b)
                note(f"B2 段：点 within-item-{target_b} 前后，within-track-{target_b} 的样式 "
                     f"width {st0.get('width')} → {st1.get('width')}；"
                     f"rgb {st0.get('rgb')} → {st1.get('rgb')}；"
                     f"ok={st0.get('ok')}/{st1.get('ok')}；点击异常={click_err_b or '无'}")
                if click_err_b:
                    skip("B2) 点列表里已画的那条 → 地图上变选中样式",
                         f"点 within-item-{target_b} 时抛异常（{click_err_b}）—— 脚本没点到，故跳过")
                elif not st0.get("ok") or not st1.get("ok"):
                    skip("B2) 点列表里已画的那条 → 地图上变选中样式",
                         f"读不到实体样式（点前 {st0.get('why')} / 点后 {st1.get('why')}）"
                         "—— Cesium 的属性读不出来时一律 skip，不假红")
                else:
                    check("B2) 点列表里已画的那条 → 地图上该条变选中样式（线宽 2→3 / 颜色变亮蓝）",
                          _is_selected_style(st1) and not _is_selected_style(st0),
                          f"within-item-{target_b} → within-track-{target_b}："
                          f"点前 width={st0.get('width')} rgb={st0.get('rgb')}"
                          "（未选中应为宽 2 / 橙 #ff9f45≈[1.0,0.624,0.271]）→ "
                          f"点后 width={st1.get('width')} rgb={st1.get('rgb')}"
                          "（选中应为宽 3 / 亮蓝 #7fd1ff≈[0.498,0.820,1.0]）"
                          "；样式没变 = 列表点选没传到地球（withinTracksForGlobe 的 selected 没生效）")

        # ------------------------------------------------ C) 拉框之后左键旋转恢复
        print("=== C) 拉框之后左键旋转必须恢复 ===")
        c_ratio_bbox = None        # C 段实测的"位移 ÷ 视野跨度"（D 段的阈值要用它）
        shot_c_before = os.path.join(".tmp", "shot-within-c-before.png")
        shot_c_after = os.path.join(".tmp", "shot-within-c-after.png")
        # ⭐ 修复轮 3 采集点②：C 段拖拽前的基准 —— 先等视野停稳再读
        bbox_c_before, _, _ = wait_view_stable(page, "C 段拖拽前")
        pr_c_before = globe_probe(page)
        page.screenshot(path=shot_c_before)
        img_before = Image.open(shot_c_before).convert("RGB")
        page.mouse.move(canvas["x"] + canvas["width"] * 0.70,
                        canvas["y"] + canvas["height"] * 0.60)
        page.mouse.down()
        page.mouse.move(canvas["x"] + canvas["width"] * 0.70 - 200,
                        canvas["y"] + canvas["height"] * 0.60, steps=10)
        page.mouse.up()
        page.wait_for_timeout(2500)            # 真实等待惯性 / 重绘结束
        # ⭐ 修复轮 3 采集点③：C 段拖拽后也要等停稳 —— 否则"拖拽后"读的是余摆中的值，
        #    会把惯性算成位移（修复轮 2 的 D 段假红就是这么来的）
        bbox_c_after, c_waited, c_stable = wait_view_stable(page, "C 段拖拽后（等余摆停）")
        page.screenshot(path=shot_c_after)
        img_after = Image.open(shot_c_after).convert("RGB")
        pr_c_after = globe_probe(page)
        note(f"C 段测量点：拖拽前 {_bbox_short(bbox_c_before)} → "
             f"拖拽后 {_bbox_short(bbox_c_after)}"
             f"（后一次等了 {c_waited} ms，稳定={c_stable}）")

        # ⭐ 修复轮 2：C 段的判据换成「视野包围盒中心是否移动」——
        #    与缩放无关，是"地球转没转"的硬证据。
        #    为什么像素判据不适用：点完第一条轨迹后相机在 **5 公里级**缩放
        #    （视野跨度 0.047°×0.024°），离线底图 NaturalEarthII 在那个尺度是一片纯色，
        #    转不转几乎不改变像素（主控实测差 66，而包围盒中心移动了视野宽度的 34%）。
        c_shift = bbox_shift_ratio(bbox_c_before, bbox_c_after)
        # 实测基准：中心位移 ≈ 视野跨度的 34%（主控代跑数据）。阈值取 8%（约 1/4 余量），
        # 既能挡住"完全没转"（≈0%），也不会被惯性/取整带来的小差异误伤。
        C_MIN_SHIFT = 0.08
        if c_shift is None:
            skip("拖拽后地球确实动了（视野包围盒移动）", "拿不到 getViewBbox() 的包围盒")
            c_ratio_bbox = None
        else:
            c_ratio_bbox = c_shift[0]
            check("拖拽后地球确实动了（视野包围盒中心位移 ≥ 8% 视野跨度）",
                  c_ratio_bbox >= C_MIN_SHIFT,
                  f"中心位移 = {c_ratio_bbox:.1%} 视野跨度"
                  f"（经度向 {c_shift[1]:.1%} / 纬度向 {c_shift[2]:.1%}），"
                  f"阈值 {C_MIN_SHIFT:.0%}；两个测量点都已等稳定（后一次 {c_waited}ms/"
                  f"{c_stable}）；{_bbox_txt(bbox_c_before)} → {_bbox_txt(bbox_c_after)}")
            note(f"C 段视野包围盒中心位移 = {c_ratio_bbox:.1%} 视野跨度"
                 f"（经度向 {c_shift[1]:.1%} / 纬度向 {c_shift[2]:.1%}）；"
                 f"{_bbox_txt(bbox_c_before)} → {_bbox_txt(bbox_c_after)}")

        # 像素差：**降级为信息输出**（在已放大的纯色底图上它天然不敏感，会假红）
        blue_before = count_color(img_before, (9, 20, 40), tol=30, x_from=x_from)
        blue_after = count_color(img_after, (9, 20, 40), tol=30, x_from=x_from)
        c_ratio = diff_ratio(shot_c_before, shot_c_after, x_from)
        note(f"C 段底色像素 {blue_before} → {blue_after}（差 {abs(blue_before - blue_after)}，"
             f"仅供参考、不参与断言）；地图区域变化像素占比 {c_ratio:.1%}")
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

            pr_d_before = globe_probe(page)
            cam_before = pr_d_before["cam"]
            # ⭐ 修复轮 3 采集点④：D 段拖拽前的基准 —— 等 C 段的余摆彻底停稳再读
            bbox_d_before, d_pre_waited, d_pre_stable = wait_view_stable(
                page, "D 段拖拽前（等 C 段余摆停）")
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
            # ⭐ 修复轮 5：这一次拖拽"有没有被当成拉框"用**请求计数**判（见下面那条 check）——
            #    所以要在拖拽**之前**先读一次基线。
            req_before_d = within_post_count()
            drag(page, dx0, dy0, dx1, dy1, steps=10)
            page.wait_for_timeout(500)
            # ⭐ 修复轮 3 采集点⑤：D 段拖拽后同样等停稳（理论上没有余摆，等一下更可比）
            bbox_d_after, d_post_waited, d_post_stable = wait_view_stable(
                page, "D 段拖拽后（等稳定）")
            # ⚠️ 读探针要放在"等待查询结果"**之前**：查询一落地，App 就把 drawingMode 收回
            #    'idle'、地球的 watcher 立刻把 enableRotate 恢复成 true —— 之后再读
            #    getRotateEnabled 只会读到 true，那是**竞态假红**，不是 bug。
            pr_d_after = globe_probe(page)
            cam_after = pr_d_after["cam"]
            rot_d2 = pr_d_after["rotate"]   # 只用诊断（松手后可能已退出绘制态）

            # ⚠️⚠️ 修复轮 4：这条**降级为信息输出**（打印实测比例，但**不计入通过/失败**）。
            #
            # 为什么降级 —— 主控三轮探针实测（2026-09-25）：
            #   | 实验                                          | 相机位移                    |
            #   | 非绘制态快速拖拽（steps=8）                     | −0.0116°（正常旋转 ✓）      |
            #   | 绘制态快速拖拽 #1 / #2（enableRotate 全程 false）| −0.0077° / −0.0089°（！）   |
            #   | 绘制态**慢速**分步拖拽（每步 200ms ≈ 人类速度）  | **精确 0.0**（✓ 不动）      |
            #   | 绘制态快速拖拽 + 同时关 enableInputs             | 减半（−0.0038），**没消除** |
            # ⇒ Playwright 的合成拖拽**速度极高**（8 步在几十毫秒内跑完），会激发 Cesium
            #   **输入聚合器**，让相机在 `enableRotate=false` 时也动一点点；而**人类速度的拖拽
            #   实测位移精确为 0**。所以"视野包围盒位移"这个**代理判据在合成快速拖拽下不成立** ——
            #   它测不出"旋转有没有被关掉"，反映的只是输入聚合器的产物。
            #
            # ⚠️ 以后若看到"绘制中包围盒动了"，**不要**去改 CesiumGlobe —— 先读这段注释。
            # 「绘制中左键不旋转」现在由两条可靠证据承担（都在下面/上面，且都通过）：
            #   ① `进入绘制模式后 getRotateEnabled() === false`（**直接**证据，开关本身）
            #   ② `绘制中的拖拽被当成拉框（发出了新的 within 请求）`（**行为**证据：
            #      这个手势被拿去画区域并**真的发了一次新请求**，而不是去转地球）
            #      —— 修复轮 5 把这条从"看 DOM 里有没有 stat-tracks"换成了数请求
            #      （旧写法恒真，理由见下面那条 check 上方的长注释）。
            d_shift = bbox_shift_ratio(bbox_d_before, bbox_d_after)
            D_MAX_SHIFT = 0.03                       # 历史参考阈值（已不参与判定）
            if d_shift is None:
                note("D 段包围盒位移（信息输出）：拿不到 getViewBbox()，跳过这项打印")
            else:
                ref_bound = D_MAX_SHIFT
                if c_ratio_bbox is not None:
                    ref_bound = min(D_MAX_SHIFT, c_ratio_bbox / 3.0)
                note(f"D 段包围盒位移（**信息输出，不判通过/失败**）= {d_shift[0]:.2%} 视野跨度；"
                     f"C 段非绘制态是 "
                     f"{('拿不到' if c_ratio_bbox is None else f'{c_ratio_bbox:.1%}')}；"
                     f"历史参考阈值 {ref_bound:.2%}（已废弃）；测量点稳定："
                     f"前 {d_pre_waited}ms/{d_pre_stable}、后 {d_post_waited}ms/{d_post_stable}；"
                     f"{_bbox_short(bbox_d_before)} → {_bbox_short(bbox_d_after)}")
                note("（这条位移在合成快速拖拽下必然非 0：Playwright 8 步几十毫秒跑完会激发 "
                     "Cesium 输入聚合器；按人类速度分步拖拽实测为 0。"
                     "绘制中不旋转由 getRotateEnabled=false 与「拖拽被当成拉框」两条证据承担）")

            # ⭐ 判据 B：相机**位置**没被带动（整段 C+D 手势后比较）。
            #    阈值 0.02 弧度是有意留宽的：实测的"输入聚合器产物"约 0.0077° ≈ 1.3e-4 弧度，
            #    比阈值小两个数量级；而真实旋转是 0.1~0.5 弧度，比阈值大 5~25 倍。
            #    所以它既能容忍合成拖拽的噪声，又能抓住"真的被转了"。
            if cam_before and cam_after:
                dlon = abs(cam_after["lon"] - cam_before["lon"])
                dlat = abs(cam_after["lat"] - cam_before["lat"])
                check("绘制模式期间相机没有被拖动（进入 D 段到 D 段拖拽结束）",
                      dlon < 0.02 and dlat < 0.02,
                      f"Δ经度={dlon:.6f} Δ纬度={dlat:.6f} "
                      f"（非绘制态同样量级的拖拽会改约 0.1~0.5 弧度）；"
                      f"高度 {cam_before['h'] / 1000:.1f}→{cam_after['h'] / 1000:.1f}km")
                note(f"D 段相机 Δ经度={dlon:.6f} Δ纬度={dlat:.6f} "
                     f"高度 {cam_before['h'] / 1000:.1f}→{cam_after['h'] / 1000:.1f}km；"
                     f"（拖拽刚结束）rotate={rot_d2}（松手后可能已退出绘制态，只作诊断）；"
                     "阈值 0.02 rad 比「输入聚合器产物」（≈1.3e-4 rad）大两个数量级、"
                     "比真实旋转（0.1~0.5 rad）小 5~25 倍")
            else:
                note("拿不到相机 → 上面那条「相机没被拖动」记 skip"
                     "（已试 setupState.viewer / exposed.viewer / ctx.viewer）")
                skip("绘制模式期间相机没有被拖动", "拿不到 viewer 的 camera.positionCartographic")

            # ⚠️ 等"新"结果：B 段那张统计卡还在，不比对旧文本就会假绿
            state_d, txt_d = wait_new_result(page, prev_text=prev_tracks_text)
            # ⭐ 修复轮 5：等这一次的请求真的发出去（在 wait_new_result 之前它多半已经发了，
            #    这里只是个兜底等待，让下面的计数读数稳定）
            got_req_d, req_waited_d = wait_new_within_request(page, req_before_d, timeout_ms=10000)
            req_after_d = within_post_count()
            page.wait_for_timeout(600)         # 让区域轮廓/轨迹线画上去，像素比较才有意义
            page.screenshot(path=SHOT)
            img_b = Image.open(SHOT).convert("RGB")

            note(f"D 段查询收尾状态 = {state_d}，stat-tracks 文本 = {txt_d!r}"
                 f"（上一次 = {prev_tracks_text!r}）")
            note(f"D 段圈选请求计数：拖拽前 {req_before_d} → 拖拽后 {req_after_d}"
                 f"（新增 {req_after_d - req_before_d}，等新请求 {req_waited_d}ms/{got_req_d}）；"
                 f"{req_summary()}")
            if state_d == "timeout":
                note("⚠️ D 段等不到结果：最可能是拖拽两端没落在球面/当前视野内的数据上 → "
                     "看上面「D 段拉框」坐标与「C 段拖拽后 视野」，"
                     "也可能是请求失败（看 within-error）")

            # ⭐ 判据 1：这次拖动被当成"拉框"了 → 才会**真的发出**一次新的圈选查询。
            #
            # ⚠️⚠️ 修复轮 5 换判据的原因（评审 finding 2，本轮最要紧的一条）：
            #   旧写法 `count('[stat-tracks]') == 1 or count('[within-empty]') == 1` 是**恒真**的：
            #   `App.startDraw()` 只改 drawingMode、**不清 withinStats**，而 `WithinStats.vue` 的
            #   根 div 没有 v-if、`App.vue` 里无条件渲染 —— B 段查出来的 stat-tracks **一直留在
            #   DOM 里**。于是 D 段哪怕完全没被当成拉框（地球被转了），这条也照样"通过"，
            #   信息量为 0（它正是上一轮用来支撑"D 段降级"的行为证据，其实不成立）。
            #   现在改成数 `POST /api/analysis/within`：**增加 ≥1** 才说明这个手势被拿去画区域
            #   并真的发了请求。它不依赖 DOM 文本的新旧，也不受 wait_new_result 两个弱点影响
            #   （"空结果分支看到旧的 within-empty 就返回"、"seen_busy 250ms 轮询可能错过
            #   ≈200–560ms 的查询中窗口"）——那两个弱点现在只影响诊断文本，不影响判据。
            n_new_req_d = req_after_d - req_before_d
            check("绘制中的拖拽被当成拉框（发出了新的 within 请求）",
                  n_new_req_d >= 1,
                  f"拖拽前后 POST /api/analysis/within 计数 {req_before_d} → {req_after_d}"
                  f"（新增 {n_new_req_d}，期望 ≥1）；DOM 收尾状态={state_d} 文本={txt_d!r}。"
                  "新增 0 = 这个手势**没有**被当成拉框（地球被转了 / 拖拽两端没落在球面上 "
                  "→ CesiumGlobe 故意不 emit），或请求失败")

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
            # ⭐ 修复轮 5：这条也补上"请求计数"（与 D 段同款判据）。
            #    原因：`within-stats==1 && (stat-tracks==1 || within-empty==1)` 在
            #    "E 段前那次清除没点成、D 段结果还留在 DOM 里"时**会变成恒真**；
            #    折进"新增请求 ≥1"之后，只有真的发了圈选查询才可能通过。
            req_before_e = within_post_count()
            page.mouse.click(bcx, bcy)
            page.wait_for_timeout(600)
            got_req_e, req_waited_e = wait_new_within_request(page, req_before_e, timeout_ms=10000)
            req_after_e = within_post_count()
            state_e, txt_e = wait_result(page)
            note(f"E 段查询收尾状态 = {state_e}，stat-tracks 文本 = {txt_e!r}")
            note(f"E 段圈选请求计数：单击前 {req_before_e} → 单击后 {req_after_e}"
                 f"（新增 {req_after_e - req_before_e}，等新请求 {req_waited_e}ms/{got_req_e}）；"
                 f"{req_summary()}")

            check("缓冲区查询出结果或明确为空（统计卡 / 空提示至少有一个）",
                  (req_after_e - req_before_e) >= 1
                  and count_of(page, '[data-testid="within-stats"]') == 1
                  and (count_of(page, '[data-testid="stat-tracks"]') == 1
                       or count_of(page, '[data-testid="within-empty"]') == 1),
                  f"状态={state_e} 文本={txt_e!r}；POST /api/analysis/within 计数 "
                  f"{req_before_e} → {req_after_e}（新增 {req_after_e - req_before_e}，期望 ≥1）"
                  "；新增 0 = 这次单击没被当成缓冲区中心（点在球外 / 没进绘制模式）")
            err_e = try_text(page, '[data-testid="within-error"]')
            check("缓冲区查询没有报错（within-error 不存在）",
                  count_of(page, '[data-testid="within-error"]') == 0, err_e or "有 within-error")

        # ------------------------------------------------ E2) 多边形：4 个点 + 双击闭合
        # ⭐ 修复轮 5 新增（规格 9.5 第 3 条，旧脚本只数了「多边形」按钮存在、从没点过）：
        #    这条链是 `RegionDrawer → App.onDrawPolygon → polygonGeometry → queryWithin`，
        #    "自交多边形必须 400"这条用户最会碰的路径就在它上面 —— 整条坏掉旧脚本也全绿。
        print("=== E2) 多边形：点 4 个点 + 双击闭合 ===")
        if count_of(page, '[data-testid="draw-polygon"]') != 1:
            skip("E2) 多边形断言", "draw-polygon 按钮不存在")
        else:
            if not click_clear(page):
                note("E2 段前那次「清除」没点成 —— 若下面那条红，先看这里"
                     "（旧结果留在 DOM 里会被当成新结果）")
            page.wait_for_timeout(500)
            pre_stat_p = count_of(page, '[data-testid="stat-tracks"]')
            pre_empty_p = count_of(page, '[data-testid="within-empty"]')
            note(f"多边形绘制前：stat-tracks={pre_stat_p}、within-empty={pre_empty_p}"
                 "（期望都是 0）")
            # 用**已有的锚点逻辑**（B 段从实体投影点挑出来的框，四角都在视口内、在面板右侧）
            # 的中心当四边形中心：这样 4 个点一定落在轨迹上、也一定在球面上。
            pcx = (b_anchor[0] + b_anchor[2]) / 2.0
            pcy = (b_anchor[1] + b_anchor[3]) / 2.0
            quad = [(pcx - 22, pcy - 22), (pcx + 22, pcy - 22),
                    (pcx + 22, pcy + 22), (pcx - 22, pcy + 22)]
            req_before_p = within_post_count()
            page.click('[data-testid="draw-polygon"]')
            page.wait_for_timeout(300)
            rot_poly_in = globe_rotate(page)
            n_cancel_p_in = count_of(page, '[data-testid="draw-cancel"]')
            note(f"进多边形绘制态：rotate={rot_poly_in}（期望 false）、"
                 f"draw-cancel={n_cancel_p_in}（期望 1）")
            for i, (qx, qy) in enumerate(quad):
                page.mouse.click(qx, qy)
                page.wait_for_timeout(120)
                note(f"多边形第 {i + 1} 个点：( {qx:.0f},{qy:.0f} )")
            # 双击闭合。⚠️ Cesium 会把一次 dblclick 拆成**两次 LEFT_CLICK + 一次
            # LEFT_DOUBLE_CLICK**（LEFT_CLICK 在 mouseup 里发、dblclick 另发），所以末尾会多一个
            # **与第 4 点重合**的顶点。实测无害：PostGIS 3.6 对重复顶点
            # `ST_IsValid` 仍返回 t/Valid Geometry（本轮已用 psql 实测确认）。
            page.mouse.dblclick(quad[3][0], quad[3][1])
            page.wait_for_timeout(600)
            got_req_p, req_waited_p = wait_new_within_request(page, req_before_p, timeout_ms=10000)
            req_after_p = within_post_count()
            state_p, txt_p = wait_result(page)
            txt_stat_p = try_text(page, '[data-testid="stat-tracks"]')
            txt_empty_p = try_text(page, '[data-testid="within-empty"]')
            txt_err_p = try_text(page, '[data-testid="within-error"]')
            has_stat_p = count_of(page, '[data-testid="stat-tracks"]') == 1 \
                and txt_stat_p not in ("", "—")
            has_empty_p = count_of(page, '[data-testid="within-empty"]') == 1 and txt_empty_p != ""
            note(f"E2 段查询收尾状态 = {state_p}；stat-tracks={txt_stat_p!r}；"
                 f"within-empty={txt_empty_p!r}；within-error={txt_err_p!r}")
            note(f"E2 段圈选请求计数：绘制前 {req_before_p} → 双击闭合后 {req_after_p}"
                 f"（新增 {req_after_p - req_before_p}，等新请求 {req_waited_p}ms/{got_req_p}）；"
                 f"{req_summary()}")
            # 断言 1：**至少一个有内容**（不是"元素存在"）——stat-tracks 是数字（0 也是数字，
            # 代表"这个区域里没有轨迹穿过"），或 within-empty 有提示文字。
            check("多边形（4 点 + 双击闭合）查出了结果（stat-tracks 数字 或 within-empty 至少一个有内容）",
                  (req_after_p - req_before_p) >= 1 and (has_stat_p or has_empty_p),
                  f"状态={state_p}；stat-tracks={txt_stat_p!r}；within-empty={txt_empty_p!r}；"
                  f"within-error={txt_err_p!r}；"
                  f"4 个点={[(round(a), round(b)) for a, b in quad]}；"
                  f"闭合方式=在第 4 点 ({quad[3][0]:.0f},{quad[3][1]:.0f}) 处 dblclick；"
                  f"请求计数 {req_before_p} → {req_after_p}"
                  f"（新增 {req_after_p - req_before_p}，期望 ≥1）；{req_summary()}")
            # 断言 2：闭合后必须已经退出绘制态
            n_cancel_p = count_of(page, '[data-testid="draw-cancel"]')
            check("多边形闭合后已退出绘制态（draw-cancel 消失）", n_cancel_p == 0,
                  f"draw-cancel 还有 {n_cancel_p} 个 —— 双击闭合后没收敛"
                  "（App.onDrawPolygon 应把 drawingMode 收回 idle）")

        # ------------------------------------------------ E3) ESC 取消绘制
        # ⭐ 修复轮 5 新增（规格 9.5 第 5 条明列的出口，旧脚本从不按 ESC）：
        #    进入绘制模式 → 按 Escape → draw-cancel 消失 + getRotateEnabled() 回到 true。
        #    （App.vue 的 onKeydown 挂在 window 上：Escape 且 drawingMode !== 'idle' 时收回 'idle'，
        #      CesiumGlobe 的 watcher 随之 clearDrawHandler() + rotateEnabled(true)。）
        print("=== E3) ESC 取消绘制 ===")
        if count_of(page, '[data-testid="draw-rect"]') != 1:
            skip("E3) ESC 取消绘制", "draw-rect 按钮不存在")
        else:
            # ⚠️ 这里**故意不点「清除」**：E2 段刚查出来的结果要留在 DOM 里，
            #    好让下面 F 段那条「清除后 stat-tracks 归 0」仍然是有内容的（否则会变成恒真）。
            page.click('[data-testid="draw-rect"]')
            page.wait_for_timeout(300)
            cancel_before_esc = count_of(page, '[data-testid="draw-cancel"]')
            rot_before_esc = globe_rotate(page)
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            cancel_after_esc = count_of(page, '[data-testid="draw-cancel"]')
            rot_after_esc = globe_rotate(page)
            note(f"ESC：按前 draw-cancel={cancel_before_esc}、rotate={rot_before_esc}；"
                 f"按后 draw-cancel={cancel_after_esc}、rotate={rot_after_esc}")
            check("ESC 取消绘制后退出绘制态（draw-cancel 消失）",
                  cancel_before_esc == 1 and cancel_after_esc == 0,
                  f"按 ESC 前 draw-cancel={cancel_before_esc}（期望 1，说明确实进了绘制态）、"
                  f"按后={cancel_after_esc}（期望 0）")
            if rot_after_esc is None:
                skip("ESC 取消绘制后左键旋转恢复（getRotateEnabled = true）", "拿不到开关值")
            else:
                check("ESC 取消绘制后左键旋转恢复（getRotateEnabled = true）",
                      rot_after_esc is True,
                      f"按 ESC 后 getRotateEnabled() = {rot_after_esc}（期望 true）；"
                      f"按前是 {rot_before_esc}（绘制中期望 false）——"
                      "若这里还是 false，说明 ESC 只收了 UI、没恢复左键旋转")

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

        # ------------------------------------------------ G) 面板零溢出（有结果 / 无结果）+ CSS 契约
        # ⭐ 修复轮 6 修两个漏洞：
        #   ① 旧脚本在 F 段「清除」**之后**才量溢出 → 量到的是**空面板**；
        #      现在两个状态都量：**有结果**（列表里真的有条目）+ **无结果**。
        #   ② 新增一条与命中条数无关的 **CSS 契约** 断言：`.within-stats` 的 `flex-shrink` 必须
        #      是 `1`（原来 Task 8 的修法就是把它加进 `.panel > div:not(...)` 白名单链，
        #      拿回"可收缩"）。
        #
        # ⭐⭐ 修复轮 7（主控代跑这次新增断言的结果）—— **这条断言抓到了一个真缺陷**：
        #      有结果时 1366×660 溢出 **99px**、1600×600 溢出 **159px**；无结果时两个都是 **0px**。
        #      而 flex-shrink 四种组合实测**都是 '1'** → 白名单早就生效了，**不是**"没加白名单"。
        #      真正的原因（CSS 推断 + 下面的分块数字可证实）：
        #        · `.within-stats` 是 `overflow: visible`，它内部**不可再收缩**的内容
        #          （统计卡 2 行 / 来源行 / 提示行 / `.items` 的 min-height: 40）超出分到的空间后，
        #          溢出部分照样算进 `.panel` 的 scrollHeight；
        #        · 而 `.panel` 是 `overflow: hidden` → 超出的那 99/159px 被**裁掉、用户点不到**。
        #      修法（已落地，产品代码）：
        #        · `.within-stats { flex: 1 1 0; min-height: 0 }`（只占剩余空间 + 真能收缩）
        #        · 矮窗口瘦身：WithinStats / RegionDrawer / App 三处 @media (max-height: 660px/620px)
        #      所以下面除了断言，还打印**面板分块高度**（panel_breakdown）——
        #      再红的话，一眼就能看出超出的 px 花在哪个块上。
        print("=== G) 面板零溢出（有结果 / 无结果 × 两个矮视口）+ flex-shrink 契约 ===")
        for w, h in SHORT_VIEWPORTS:
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(300)
            if count_of(page, '[data-testid="mode-within"]') == 1:
                page.click('[data-testid="mode-within"]')
            else:
                skip(f"{w}x{h} 面板零溢出（有结果）", "没有 mode-within 按钮")
                skip(f"{w}x{h} 面板零溢出（无结果）", "没有 mode-within 按钮")
                skip(f"{w}x{h} .within-stats 的 flex-shrink == '1'（CSS 契约）", "没有 mode-within 按钮")
                continue
            page.wait_for_timeout(900)

            # --- ① 有结果：在**这个视口**下重新查一次最大半径缓冲区，拿到"列表里真的有条目"的状态
            state_g, items_g, diag_g = draw_big_buffer(page)
            note(f"{w}x{h} 有结果状态：{diag_g}")
            ov_res = panel_overflow(page)
            if ov_res is None:
                skip(f"{w}x{h} 面板零溢出（有结果）", "取不到 .panel")
            else:
                box = page.locator(".panel").bounding_box()
                over_res = ov_res["sh"] - ov_res["ch"]
                bd_res = _fmt_breakdown(panel_breakdown(page))
                note(f"{w}x{h} 有结果：列表条目 {items_g} 条；"
                     f"面板 scrollHeight={ov_res['sh']} clientHeight={ov_res['ch']} "
                     f"溢出={over_res}px box={box}")
                note(f"{w}x{h} 有结果分块：{bd_res}")
                if items_g == 0:
                    skip(f"{w}x{h} 面板零溢出（有结果）",
                         f"这次缓冲区没查出条目（状态={state_g} 文本={diag_g}）—— 量到的还是空面板，"
                         "没有意义，故跳过（下面的无结果那条仍然会量）")
                else:
                    check(f"{w}x{h} 面板零溢出（有结果：列表 {items_g} 条）",
                          ov_res["sh"] <= ov_res["ch"] + 2,
                          f"scrollHeight={ov_res['sh']} > clientHeight={ov_res['ch']} + 2"
                          f"（溢出 {over_res}px）；列表条目 {items_g} 条 box={box}；"
                          f"分块：{bd_res}"
                          " —— ⚠️ 成因见 G 段顶部注释：**不是**白名单（flex-shrink 实测为 '1'），"
                          "是 .within-stats 内部不可收缩的内容 + 圈选档固定块超过面板可用高度，"
                          "被 .panel 的 overflow: hidden 裁掉")
            fs_res = within_stats_flex_shrink(page)
            if fs_res is None:
                skip(f"{w}x{h} .within-stats 的 flex-shrink == '1'（有结果时）",
                     "取不到 .within-stats（元素不在 / 读样式失败）")
            else:
                check(f"{w}x{h} .within-stats 的 flex-shrink == '1'（有结果时，CSS 契约）",
                      fs_res == "1",
                      f"getComputedStyle('.within-stats').flexShrink = {fs_res!r}（期望 '1'）；"
                      "为 '0' 说明它落进了 .panel > div 的 flex: 0 0 auto 规则、不可收缩"
                      "（白名单链里必须带上 .within-stats）——"
                      "⚠️ 修复轮 7 实测它一直是 '1'，所以「有结果溢出」那条的成因**不是**白名单")

            # --- ② 无结果：清除后再量一次（这一条就是旧脚本原来那条断言，保留）
            cleared_g = click_clear(page)
            page.wait_for_timeout(900)
            ov_empty = panel_overflow(page)
            if ov_empty is None:
                skip(f"{w}x{h} 面板零溢出（无结果）", "取不到 .panel")
            else:
                over_empty = ov_empty["sh"] - ov_empty["ch"]
                note(f"{w}x{h} 无结果：stat-tracks={count_of(page, '[data-testid=\"stat-tracks\"]')}；"
                     f"面板 scrollHeight={ov_empty['sh']} clientHeight={ov_empty['ch']} "
                     f"溢出={over_empty}px")
                note(f"{w}x{h} 无结果分块：{_fmt_breakdown(panel_breakdown(page))}")
                check(f"{w}x{h} 面板零溢出（无结果）", ov_empty["sh"] <= ov_empty["ch"] + 2,
                      f"scrollHeight={ov_empty['sh']} > clientHeight={ov_empty['ch']} + 2"
                      f"（溢出 {over_empty}px）"
                      + ("" if cleared_g else "（这次清除没点成，看上面诊断）"))
            fs_empty = within_stats_flex_shrink(page)
            if fs_empty is None:
                skip(f"{w}x{h} .within-stats 的 flex-shrink == '1'（无结果时）",
                     "取不到 .within-stats（元素不在 / 读样式失败）")
            else:
                check(f"{w}x{h} .within-stats 的 flex-shrink == '1'（无结果时，CSS 契约）",
                      fs_empty == "1",
                      f"getComputedStyle('.within-stats').flexShrink = {fs_empty!r}（期望 '1'）")

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
