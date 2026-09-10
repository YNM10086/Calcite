# -*- coding: utf-8 -*-
"""生成《Calcite 项目结构地图》里用的流程图（PNG）。

为什么自己画：Word 里用文字画箭头很难看，officecli 的 mermaid 又写不进文件
（见 global-knowledge：officecli 在 DSH 沙箱写不进 docx）。
Pillow 直接画成图片再用 python-docx 插进去最稳。

输出：.tmp/figs/fig*.png
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
FONT = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"
MONO = "C:/Windows/Fonts/consola.ttf"

W = 1400
BG = (255, 255, 255)
INK = (0x1D, 0x21, 0x26)
GRAY = (0x86, 0x90, 0x9C)

BLUE, BLUE_F = (0x16, 0x5D, 0xFF), (0xE8, 0xF3, 0xFF)
GREEN, GREEN_F = (0x00, 0xB4, 0x2A), (0xE8, 0xFF, 0xEA)
ORANGE, ORANGE_F = (0xFF, 0x7D, 0x00), (0xFF, 0xF7, 0xE8)
PURPLE, PURPLE_F = (0x72, 0x2E, 0xD1), (0xF5, 0xE8, 0xFF)
RED, RED_F = (0xF5, 0x3F, 0x3F), (0xFF, 0xEC, 0xEC)
CYAN, CYAN_F = (0x0F, 0xC0, 0xC0), (0xE6, 0xFF, 0xFF)

_cache = {}


def f(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _cache:
        path = MONO if mono else (FONT_B if bold else FONT)
        _cache[key] = ImageFont.truetype(path, size)
    return _cache[key]


class Fig:
    def __init__(self, height, width=W):
        self.w, self.h = width, height
        self.im = Image.new("RGB", (width, height), BG)
        self.d = ImageDraw.Draw(self.im)

    def title(self, text, sub=None):
        self.d.text((60, 40), text, font=f(34, True), fill=INK, anchor="la")
        if sub:
            self.d.text((60, 88), sub, font=f(19), fill=GRAY, anchor="la")

    def box(self, x, y, w, h, title, subs=(), border=BLUE, fill=BLUE_F,
            ts=24, ss=17, radius=14, dash=False, align="center"):
        # 防御：写成 ("只有一行") 时它其实是字符串不是元组，
        # 直接 for 会逐字符画成竖排。这里兜一下。
        if isinstance(subs, str):
            subs = (subs,)
        if dash:
            self._dashed_round_rect(x, y, w, h, radius, border)
            self.d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill)
            self._dashed_round_rect(x, y, w, h, radius, border)
        else:
            self.d.rounded_rectangle([x, y, x + w, y + h], radius=radius,
                                     fill=fill, outline=border, width=3)
        cx = x + w / 2
        ty = y + 26
        if align == "center":
            self.d.text((cx, ty), title, font=f(ts, True), fill=INK, anchor="ma")
            sy = ty + ts + 12
            for s in subs:
                self.d.text((cx, sy), s, font=f(ss), fill=GRAY, anchor="ma")
                sy += ss + 8
        else:
            self.d.text((x + 20, ty), title, font=f(ts, True), fill=INK, anchor="la")
            sy = ty + ts + 10
            for s in subs:
                self.d.text((x + 20, sy), s, font=f(ss), fill=GRAY, anchor="la")
                sy += ss + 8
        return (x, y, w, h)

    def text(self, x, y, s, size=18, bold=False, color=INK, anchor="la", mono=False):
        self.d.text((x, y), s, font=f(size, bold, mono), fill=color, anchor=anchor)

    def _dashed_round_rect(self, x, y, w, h, r, color, width=3, seg=12, gap=8):
        pts = []
        pts += [(x + r + i, y) for i in range(0, int(w - 2 * r), 4)]
        pts += [(x + w, y + r + i) for i in range(0, int(h - 2 * r), 4)]
        pts += [(x + w - r - i, y + h) for i in range(0, int(w - 2 * r), 4)]
        pts += [(x, y + h - r - i) for i in range(0, int(h - 2 * r), 4)]
        i = 0
        while i < len(pts) - 1:
            j = min(i + seg, len(pts) - 1)
            self.d.line([pts[i], pts[j]], fill=color, width=width)
            i = j + gap

    def arrow(self, x1, y1, x2, y2, label=None, color=GRAY, width=3,
              label_dx=0, label_dy=-16, dashed=False):
        if dashed:
            n = int(math.hypot(x2 - x1, y2 - y1) / 12)
            for k in range(n):
                t0, t1 = k / n, (k + 0.55) / n
                self.d.line([x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0,
                             x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1],
                            fill=color, width=width)
        else:
            self.d.line([x1, y1, x2, y2], fill=color, width=width)
        ang = math.atan2(y2 - y1, x2 - x1)
        L = 16
        for da in (math.radians(152), math.radians(-152)):
            self.d.line([x2, y2, x2 + L * math.cos(ang + da),
                         y2 + L * math.sin(ang + da)], fill=color, width=width)
        if label:
            mx, my = (x1 + x2) / 2 + label_dx, (y1 + y2) / 2 + label_dy
            bb = self.d.textbbox((mx, my), label, font=f(17), anchor="mm")
            self.d.rectangle([bb[0] - 6, bb[1] - 3, bb[2] + 6, bb[3] + 3], fill=BG)
            self.d.text((mx, my), label, font=f(17), fill=color, anchor="mm")

    def save(self, name):
        path = os.path.join(OUT, name)
        # 自动溢出检查：把非白像素的包围盒求出来，贴边就说明内容被裁掉了。
        # 这是给自己兜底的——不能全靠肉眼看图。
        mask = self.im.convert("L").point(lambda p: 255 if p < 250 else 0)
        bbox = mask.getbbox()
        warn = []
        if bbox:
            if bbox[0] <= 2:
                warn.append("左边贴边")
            if bbox[1] <= 2:
                warn.append("上边贴边")
            if bbox[2] >= self.w - 2:
                warn.append("右边贴边")
            if bbox[3] >= self.h - 2:
                warn.append("下边贴边(内容被裁)")
        self.im.save(path)
        flag = ("  ⚠ " + "、".join(warn)) if warn else ""
        print("  " + name, self.im.size, "内容范围", bbox, flag)


# ---------------------------------------------------------------- 图 1 总体架构
def fig1():
    g = Fig(960)
    g.title("图 1 · Calcite 总体架构",
            "四层结构。每一层只跟相邻层说话，跨层是不可能的——这是理解整个项目的第一把钥匙。")

    # 用户
    g.box(470, 150, 460, 90, "你（浏览器）", ("Chrome 窗口里的那个页面",),
          border=PURPLE, fill=PURPLE_F)
    # 前端
    g.box(150, 300, 1100, 190, "前端 · Vue 3（开发时跑在 Vite 上，端口 5173）",
          ("App.vue 负责状态（选中了哪条轨迹、播到第几秒）",
           "CesiumGlobe 画地球和轨迹 · TrackList 画列表 · TrackPlayer 画播放条 · SpeedChart 画曲线",
           "lib/ 里是纯计算函数（playback.js 算倍速、chart.js 算刻度），不碰浏览器"), border=BLUE, fill=BLUE_F, align="left")
    # 后端
    g.box(150, 570, 1100, 160, "后端 · Spring Boot（端口 8080）",
          ("web/TrackController 收 HTTP 请求、决定返回什么",
           "repository/TrackRepository 负责查数据库（方法名就是 SQL）",
           "domain/Track 是数据库表的 Java 影子 · web/dto/ 是要发出去的精简版"), border=GREEN, fill=GREEN_F, align="left")
    # 数据库
    g.box(470, 790, 460, 80, "数据库 · PostgreSQL + PostGIS（端口 5432）",
          (), border=ORANGE, fill=ORANGE_F)

    g.arrow(700, 240, 700, 296, "打开网页 / 点击操作", color=PURPLE, label_dy=-14)
    g.arrow(700, 490, 700, 566, "HTTP 请求  GET /api/tracks/1", color=BLUE, label_dy=-14)
    g.arrow(700, 730, 700, 786, "SQL 查询", color=GREEN, label_dy=-14)
    g.arrow(1010, 786, 1010, 730, "查询结果（一行行数据）", color=ORANGE, label_dy=-14)
    g.arrow(1010, 566, 1010, 490, "JSON 响应", color=GREEN, label_dy=-14)
    g.arrow(390, 296, 390, 240, "渲染画面", color=BLUE, label_dy=-14)

    g.text(60, 895, "注：前端 dev server 会把 /api 开头的请求转发给 8080，这个机制叫「代理」，用来避开浏览器的跨域限制。",
           size=16, color=GRAY)
    g.save("fig1-arch.png")


# ------------------------------------------------------------ 图 2 目录结构
def fig2():
    g = Fig(1120)
    g.title("图 2 · 目录结构地图",
            "每个格子里写的是「这个目录负责什么」。打星号的是你以后最常改的。")

    rows = [
        ("backend/", "后端 Java 代码，一个独立进程", GREEN, GREEN_F, 0),
        ("    pom.xml", "★ 后端依赖清单（加 Java 库改这里）", GREEN_F, GREEN_F, 1),
        ("    src/main/java/com/calcite/", "★ Java 代码，按职责分包", GREEN_F, GREEN_F, 1),
        ("        web/", "★ 接口层：Controller + dto/", GREEN_F, GREEN_F, 2),
        ("        repository/", "★ 查数据库的接口（方法名即 SQL）", GREEN_F, GREEN_F, 2),
        ("        domain/", "★ 实体类：数据库表的 Java 影子", GREEN_F, GREEN_F, 2),
        ("    src/main/resources/", "★ 配置文件（application.yml 等）", GREEN_F, GREEN_F, 1),
        ("frontend/", "前端 Vue 代码，另一个独立进程", BLUE, BLUE_F, 0),
        ("    package.json", "★ 前端依赖清单（加 npm 包改这里）", BLUE_F, BLUE_F, 1),
        ("    vite.config.js", "★ 构建配置：端口、代理、Cesium 资源拷贝", BLUE_F, BLUE_F, 1),
        ("    index.html", "页面骨架，只有一个空的 #app", BLUE_F, BLUE_F, 1),
        ("    src/App.vue", "★ 总指挥：所有状态都放这里", BLUE_F, BLUE_F, 1),
        ("    src/components/", "★ 界面组件（地球 / 列表 / 播放条 / 曲线）", BLUE_F, BLUE_F, 2),
        ("    src/lib/", "★ 纯计算代码（有测试保护，改起来最安全）", BLUE_F, BLUE_F, 2),
        ("    scripts/", "回归检查脚本（node 直接跑）", BLUE_F, BLUE_F, 2),
        ("scripts/db/", "★ 数据库建表 / 灌数据 / 查看结果的 SQL", ORANGE, ORANGE_F, 0),
        ("scripts/tools/", "辅助工具（比如把 Markdown 转成 Word）", ORANGE_F, ORANGE_F, 0),
        ("docs/", "设计文档与实施计划（写代码之前先写这里）", PURPLE, PURPLE_F, 0),
        ("_session_context.md", "会话记忆：每次开工先读它，收工更新它", PURPLE_F, PURPLE_F, 0),
    ]
    y = 150
    for name, desc, border, fill, indent in rows:
        x = 90 + indent * 34
        g.d.rounded_rectangle([x, y, 1310, y + 42], radius=8, fill=fill,
                              outline=border, width=2)
        g.text(x + 18, y + 11, name, size=19, bold=True, color=INK, mono=True)
        g.text(660, y + 12, desc, size=18, color=(0x4E, 0x59, 0x69))
        y += 49
    g.save("fig2-tree.png")


# ------------------------------------------------------- 图 3 点轨迹的旅程
def fig3():
    g = Fig(1330)
    g.title("图 3 · 点一条轨迹，数据经历了什么",
            "这是全项目最重要的一张图。看懂它，你就知道任何功能该改哪一层。")

    lane_x = {"浏览器": (90, PURPLE, PURPLE_F),
              "前端": (390, BLUE, BLUE_F),
              "后端": (700, GREEN, GREEN_F),
              "数据库": (1010, ORANGE, ORANGE_F)}

    for name, (x, c, _f) in lane_x.items():
        g.d.rounded_rectangle([x, 140, x + 264, 1310], radius=16,
                              fill=(0xFA, 0xFA, 0xFA), outline=c, width=2)
        g.text(x + 132, 158, name, size=22, bold=True, color=c, anchor="ma")

    steps = [
        ("浏览器", 210, "① 你点击列表里的\n「北京城区骑行」", PURPLE, PURPLE_F),
        ("前端", 330, "② TrackList 发出 select 事件\nApp.vue 收到 → selectTrack(1)", BLUE, BLUE_F),
        ("前端", 462, "③ fetch('/api/tracks/1')\n（注意：请求发给自己 5173）", BLUE, BLUE_F),
        ("前端", 594, "④ Vite dev server 把 /api\n转发到 8080（代理，避开跨域）", CYAN, CYAN_F),
        ("后端", 594, "⑤ TrackController.detail(1)", GREEN, GREEN_F),
        ("后端", 714, "⑥ TrackRepository.findById(1)\n→ 拿到 1 条 Track 实体", GREEN, GREEN_F),
        ("后端", 834, "⑦ TrackPointRepository\n.findByTrackIdOrderBySeqAsc(1)\n→ 拿到 121 条点", GREEN, GREEN_F),
        ("数据库", 834, "⑧ PostgreSQL 用索引\n( track_id, seq ) 取出这 121 行", ORANGE, ORANGE_F),
        ("后端", 980, "⑨ 实体 → DTO\n（只挑前端要用的字段）", GREEN, GREEN_F),
        ("前端", 980, "⑩ 收到 JSON\n存进 detail.value", BLUE, BLUE_F),
        ("前端", 1100, "⑪ 三个组件同时收到 points：\nCesiumGlobe 画线\nSpeedChart 画曲线\nTrackPlayer 算总时长", BLUE, BLUE_F),
    ]
    boxes = []
    for lane, y, label, border, fill in steps:
        x = lane_x[lane][0] + 12
        lines = label.split("\n")
        h = 34 + len(lines) * 26
        g.d.rounded_rectangle([x, y, x + 240, y + h], radius=10, fill=fill,
                              outline=border, width=2)
        for k, ln in enumerate(lines):
            g.text(x + 120, y + 16 + k * 26, ln, size=16, color=INK, anchor="ma")
        boxes.append((x, y, h))

    # 竖向箭头串起来
    for i in range(len(boxes) - 1):
        x1, y1, h1 = boxes[i]
        x2, y2, _ = boxes[i + 1]
        if x1 == x2:
            g.arrow(x1 + 120, y1 + h1 + 4, x2 + 120, y2 - 6, color=GRAY, width=2)
        else:
            g.arrow(x1 + 120, y1 + h1 + 4, x2 + 120, y2 - 6, color=GRAY, width=2)
    g.save("fig3-journey.png")


# --------------------------------------------------------- 图 4 后端分层
def fig4():
    g = Fig(760)
    g.title("图 4 · 后端为什么要分四层",
            "每一层只干一件事。分层不是为了好看，是为了「改一处不用动别处」。")

    g.box(60, 150, 300, 120, "web/Controller", ("收 HTTP 请求", "决定返回什么、什么时候抛 404"),
          border=GREEN, fill=GREEN_F, ts=23, ss=16)
    g.box(400, 150, 300, 120, "repository/", ("拿数据", "方法名 = SQL（findByTrackId…）"),
          border=GREEN, fill=GREEN_F, ts=23, ss=16)
    g.box(740, 150, 300, 120, "domain/Entity", ("数据库表的 Java 影子", "一个对象 = 一行数据"),
          border=GREEN, fill=GREEN_F, ts=23, ss=16)
    g.box(1080, 150, 260, 120, "数据库", ("真正存数据的地方",),
          border=ORANGE, fill=ORANGE_F, ts=23, ss=16)

    g.box(60, 330, 300, 120, "web/dto/", ("要发出去的精简版", "只留前端用得上的字段"),
          border=CYAN, fill=CYAN_F, ts=23, ss=16)

    g.arrow(360, 210, 396, 210, "调用", color=GREEN, label_dy=-16)
    g.arrow(700, 210, 736, 210, "调用", color=GREEN, label_dy=-16)
    g.arrow(1040, 210, 1076, 210, "SQL", color=ORANGE, label_dy=-16)
    g.arrow(1210, 274, 1210, 470, "", color=ORANGE)
    g.arrow(1210, 470, 210, 470, "", color=ORANGE)
    g.arrow(210, 470, 210, 454, "数据往回走", color=ORANGE, label_dx=120, label_dy=0)

    g.text(400, 500, "为什么要 DTO 这一层？", size=23, bold=True, color=INK)
    for i, s in enumerate([
        "① 实体里可能有多余字段（比如内部用的 id、数据库时间戳），不该发给前端",
        "② 前端要的格式和数据库不一样（比如要数组、要重命名的字段），转换放在 DTO 的 from() 里",
        "③ 以后数据库改字段，只要 DTO 不变，前端就完全不用动",
    ]):
        g.text(400, 545 + i * 34, s, size=18, color=(0x4E, 0x59, 0x69))

    g.text(60, 660, "记住一句：Controller 不写 SQL，Repository 不碰 HTTP，Entity 不认识前端。",
           size=19, bold=True, color=RED)
    g.save("fig4-backend.png")


# --------------------------------------------------------- 图 5 前端组件树
def fig5():
    g = Fig(820)
    g.title("图 5 · 前端组件树与数据流向",
            "数据从上往下流（props），事件从下往上跑（emit）。App.vue 是唯一的状态中心。")

    g.box(500, 150, 400, 110, "App.vue",
          ("状态中心：选中了哪条轨迹、播到第几秒、循环开不开",),
          border=RED, fill=RED_F, ts=26, ss=16)

    kids = [
        (60, "TrackList.vue", ("轨迹列表", "emit: select")),
        (380, "CesiumGlobe.vue", ("地球 + 轨迹 + 移动点", "defineExpose: play/pause/seekTo")),
        (700, "TrackPlayer.vue", ("播放条", "emit: toggle/seek/loop")),
        (1020, "SpeedChart.vue", ("速度/海拔曲线", "emit: seek")),
    ]
    # 树的画法：App.vue 下来一根竖线，接一条横线（总线），再从总线各自往下分叉
    BUS_Y = 320
    g.d.line([700, 260, 700, BUS_Y], fill=BLUE, width=3)
    g.d.line([210, BUS_Y, 1170, BUS_Y], fill=BLUE, width=3)
    for x, name, subs in kids:
        cx = x + 150
        g.arrow(cx, BUS_Y, cx, 396, "", color=BLUE, width=3)
        g.box(x, 400, 300, 130, name, subs, border=BLUE, fill=BLUE_F, ts=21, ss=16)
        g.arrow(cx + 90, 396, cx + 90, BUS_Y + 6, "", color=GRAY, width=2, dashed=True)

    g.text(636, BUS_Y - 26, "props 往下传（数据）→", size=17, color=BLUE, anchor="ra")
    g.text(760, BUS_Y - 26, "← 虚线：emit 往上报（事件）", size=17, color=GRAY)

    g.box(60, 600, 610, 170, "lib/ · 纯计算，没有界面", (
        "playback.js —— 算倍速（总秒数 ÷ 60）、算时间范围、判断能不能播",
        "chart.js —— 算刻度、算坐标映射、算游标处的精确值",
        "特点：不 import Vue、不 import Cesium，所以能用 node 直接跑断言"), border=PURPLE, fill=PURPLE_F, ts=23, ss=17, align="left")

    g.box(730, 600, 610, 170, "为什么状态只放 App.vue？", (
        "如果每个组件各存一份「播到第几秒」，就会出现",
        "播放条显示在播、地球却停着这种不一致。",
        "所以约定：状态只放父组件，子组件负责显示 + 上报意图。"), border=GREEN, fill=GREEN_F, ts=23, ss=17, align="left")
    g.save("fig5-frontend.png")


# --------------------------------------------------------- 图 6 数据库表
def fig6():
    g = Fig(880)
    g.title("图 6 · 数据库三张表的关系",
            "一对多：一条轨迹有很多点、很多次停留。删掉轨迹，它的点和停留会自动跟着删。")

    g.box(60, 160, 380, 300, "track（一条轨迹 = 一次出行）", (), border=ORANGE, fill=ORANGE_F, ts=21, align="left")
    for i, s in enumerate(["id 主键", "name 名字", "source 来源（geolife/gpx/csv/sample）",
                            "external_id 原始编号（判重用）", "start_time / end_time 起止时刻",
                            "distance_m 总距离（派生）", "duration_s 总时长（派生）",
                            "point_count 点数（派生）", "geom 轨迹线 LineString"]):
        g.text(80, 218 + i * 26, s, size=16, color=(0x4E, 0x59, 0x69), mono=True)

    g.box(540, 160, 400, 300, "track_point（一个 GPS 点 = 原始真相）", (), border=ORANGE, fill=ORANGE_F, ts=21, align="left")
    for i, s in enumerate(["id 主键", "track_id → track.id（外键）", "seq 在轨迹里的顺序",
                            "recorded_at 这一点的时刻", "elevation_m 海拔",
                            "speed_mps 速度（由坐标算出来再回填）",
                            "geom 一个点 Point"]):
        g.text(560, 218 + i * 26, s, size=16, color=(0x4E, 0x59, 0x69), mono=True)

    g.box(540, 540, 400, 200, "stay_point（一次停留 · M2 才用）", (), border=GRAY, fill=(0xF7, 0xF8, 0xFA), ts=21, align="left", dash=True)
    for i, s in enumerate(["track_id → track.id（外键）", "start_time / end_time",
                            "duration_s 停了多久", "radius_m 活动半径", "geom 停留中心点"]):
        g.text(560, 598 + i * 26, s, size=16, color=(0x4E, 0x59, 0x69), mono=True)

    g.arrow(444, 310, 536, 310, "1 条轨迹 → 121 个点", color=ORANGE, label_dy=-18)
    g.arrow(444, 640, 536, 640, "1 条轨迹 → 多次停留", color=GRAY, label_dy=-18, dashed=True)

    g.text(60, 500, "派生数据是什么意思：", size=20, bold=True, color=INK)
    for i, s in enumerate(["distance_m / duration_s / point_count / geom（线）",
                            "这些都能由 track_point 算出来，存一份只是为了让列表页不用现算。" ]):
        g.text(60, 540 + i * 30, s, size=17, color=(0x4E, 0x59, 0x69))
    g.text(60, 620, "真相只有一个：track_point 表。别的都是它的推论。",
           size=19, bold=True, color=RED)
    g.save("fig6-db.png")


# --------------------------------------------------- 图 7 加东西放哪里
def fig7():
    g = Fig(920)
    g.title("图 7 · 以后要加东西，放哪里",
            "先问「这东西属于哪一层」，答案就出来了。这张图以后你会反复回来看。")

    items = [
        ("想加一个新的接口\n（比如导入轨迹）", "backend/src/main/java/com/calcite/web/", "新建 XxxController.java", GREEN, GREEN_F),
        ("想加一张新表", "scripts/db/", "新建 04-xxx.sql，同时在 domain/ 加实体类", ORANGE, ORANGE_F),
        ("想加一个复杂查询", "backend/.../repository/", "在 Repository 接口里加一个方法", GREEN, GREEN_F),
        ("想加一个新页面 / 新面板", "frontend/src/components/", "新建 Xxx.vue，在 App.vue 里挂上去", BLUE, BLUE_F),
        ("想加一段计算逻辑\n（不涉及界面）", "frontend/src/lib/", "新建 xxx.js + 在 scripts/ 加检查脚本", PURPLE, PURPLE_F),
        ("想加一个 Java 库", "backend/pom.xml", "<dependency> 写在 <dependencies> 里", GREEN, GREEN_F),
        ("想加一个 npm 包", "frontend/package.json", "用 npm install xxx 自动写入", BLUE, BLUE_F),
        ("想加一张图片 / 静态资源", "frontend/public/", "这个目录还没建，需要自己新建一个，用 /文件名 访问", BLUE, BLUE_F),
    ]
    y = 160
    for want, where, how, border, fill in items:
        g.d.rounded_rectangle([60, y, 1340, y + 82], radius=12, fill=fill,
                              outline=border, width=2)
        for k, ln in enumerate(want.split("\n")):
            g.text(84, y + 18 + k * 26, ln, size=18, bold=True, color=INK)
        g.text(470, y + 30, "→", size=24, bold=True, color=border)
        g.text(510, y + 14, where, size=18, bold=True, color=border, mono=True)
        g.text(510, y + 46, how, size=16, color=(0x4E, 0x59, 0x69))
        y += 92
    g.save("fig7-where.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    print("生成图片：")
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
    fig7()
    print("完成")
