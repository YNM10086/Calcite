# -*- coding: utf-8 -*-
"""生成 README 用的全景架构图：docs/images/arch-overview.png

为什么单独一个脚本：README 的主图尺寸/信息密度跟学习笔记里的流程图不同，
但画法完全一样 —— 直接复用 make_figs.py 的 Fig 类与配色/字体常量，
不重复造轮子，也**不改动** make_figs.py（它属于学习笔记那一套）。

--------------------------------------------------------------------
第二版（可读性改版）为什么这么画
--------------------------------------------------------------------
第一版是 1400 px 宽的竖版图，正文最小只有 14 px。GitHub README 的正文栏
大约 900 px，主图被压到 900/1400 ≈ 64% 显示 —— 14 px 的正文实际只有 9 px，
手机上基本看不清。所以这一版做了三件事：

1. **画布 1400 → 1000 px**（正文总宽 960），并按比例放大字号：
   主标题 24、分区标题 20、技术栈徽标 15、正文 15~16、注脚 15~16。
   在 900 px 宽的正文栏里缩放比是 90%，正文仍有 13.5~14.4 px，分区标题 18 px。
2. **每个框只留标题 + 2~3 行短要点**（第一版有写到 3 行长句的）。
   细节交给 README 正文讲 —— 宁可少写字，也不要把字缩小。
3. 所有 x/y 都是**按可用宽度算出来的**（cols()/chain_x()/row_h()），
   不再手写坐标；改画布宽度或列数时不会有一列跑出画布。

注意两点（沿用第一版）：

1. `Fig.save()` 默认写回 make_figs.py 所在目录，所以这里改的是
   `make_figs.OUT`（运行时变量），不是源文件。
2. `Fig.box()` 的高度是硬编码的，画错了它不会报错 —— 文字会静静地
   画到框外面去。所以这里保留了 `sbox()`：**按内容算高度**，
   并逐行校验文字宽度，超宽/超框直接打印 ⚠。

用法（必须在仓库根目录跑）：
    & "E:\\python\\python_address\\python.exe" docs\\learning\\figs\\make_readme_figs.py
输出：docs/images/arch-overview.png（1000 宽，竖版）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# make_figs.save() 在发现"贴边"时会 print 一个 ⚠（U+26A0）。
# 中文 Windows 的控制台是 GBK，直接 print 会 UnicodeEncodeError 把脚本打断。
# 这里不改 make_figs.py，只把本进程的 stdout 换成 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import make_figs as mf
from make_figs import (BLUE, BLUE_F, CYAN, CYAN_F, GRAY, GREEN, GREEN_F, INK,
                       ORANGE, ORANGE_F, PURPLE, PURPLE_F, RED, RED_F, Fig)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(ROOT, "docs", "images")
mf.OUT = OUT_DIR  # save() 会读这个模块级变量

# ---------------------------------------------------------------- 版面常量
W = 1000          # 画布宽度（GitHub 正文栏约 900，缩放比 90% → 字号只掉一成）
M = 20            # 左右页边距
CW = W - 2 * M    # 正文总宽 = 960
PAD = 20          # box() 里文字距边框的水平内边距（align="left" 用的是 x+20）
LINE = 24         # 每行文字占的行高

BAD = []          # 收集所有自动检查发现的问题，最后统一汇报


def line_w(s, size):
    return mf.f(size).getlength(s)


def cols(n, gap, x0=M, total=CW):
    """把总宽切成 n 等宽列，返回 (每列宽, [每列左边的 x])。"""
    w = (total - (n - 1) * gap) // n
    return w, [x0 + i * (w + gap) for i in range(n)]


def chain_x(n, arw, x0=M, total=CW):
    """有箭头的横向链：n 个框 + (n-1) 个宽 arw 的箭头空隙。"""
    w = (total - (n - 1) * arw) // n
    return w, [x0 + i * (w + arw) for i in range(n)], arw


def calc_h(title, subs, ts, ss, align="left"):
    """算出 Fig.box() 真正需要的高度。

    Fig.box() 的排版是固定的：标题画在 y+26，副标题从
    y+26+ts+(12 居中 / 10 左对齐) 开始，每行 ss+8。
    最后一行的**下伸部分**必须用 textbbox 量，否则中文会压到框线上
    （第一版就是按 "ss+8" 估的，第三行正好骑在边框上）。
    """
    if isinstance(subs, str):
        subs = (subs,)
    n = len(subs)
    gap = 12 if align == "center" else 10
    if n == 0:
        return 26 + ts + 6
    sy_last = 26 + ts + gap + (n - 1) * (ss + 8)
    sb = mf.f(ss).getbbox(subs[-1], anchor="la")
    return int(sy_last + sb[3] + 8)


def check_lines(lines, size, limit, what):
    for s in lines:
        if line_w(s, size) > limit:
            BAD.append("%s超宽 %.0f>%.0f: %s" % (what, line_w(s, size), limit, s))


def sbox(g, x, y, w, title, subs=(), border=BLUE, fill=BLUE_F,
         ts=20, ss=15, align="left", radius=14, dash=False):
    """按内容自动算高度的 box()，顺便校验每行文字的宽度。"""
    if isinstance(subs, str):
        subs = (subs,)
    h = calc_h(title, subs, ts, ss, align)

    inner = w - 2 * PAD
    if line_w(title, ts) > inner:
        BAD.append("标题超宽 %.0f>%.0f: %s" % (line_w(title, ts), inner, title))
    check_lines(list(subs), ss, inner, "副标题")
    # 已知 msyh 缺字形的字符（↔ 就是这么发现的：画出来是个 □）
    # ①-④、·、—、→、↓ 都实测能画，别误报。
    for ch in title + "".join(subs):
        if ch in "↔⇒⇔≤≥℃㎡≠√∞–":
            BAD.append("可疑字符（可能是豆腐块）: %r in %s" % (ch, title))

    g.box(x, y, w, h, title, subs, border=border, fill=fill,
          ts=ts, ss=ss, radius=radius, dash=dash, align=align)
    return y + h


def row_h(items, ts, ss, align="center", pad=8):
    """一行里所有框的统一高度（取最高那个），这样顶部对齐、底边平齐。"""
    return max(calc_h(t, s, ts, ss, align) for t, s in items) + pad


def head(g, y):
    """页头：主标题 + 两行事实性描述。也逐行校验宽度。"""
    tsize, ssize = 24, 16
    subs = (
        "把 GPS 轨迹存进 PostGIS，做成时空分析 + Cesium 三维时间轴回放",
        "个人项目 · 从零边做边学 · 设计文档 → 计划 → TDD → 回归 → 同步文档",
    )
    check_lines((TITLE,), tsize, CW, "主标题")
    check_lines(subs, ssize, CW, "页头副标题")
    g.text(M, y, TITLE, size=tsize, bold=True, color=INK)
    for i, s in enumerate(subs):
        g.text(M, y + 34 + i * LINE, s, size=ssize, color=GRAY)
    ty = y + 34 + (len(subs) - 1) * LINE + 24   # 副标题末行基线
    g.d.line([M, ty + 12, W - M, ty + 12], fill=(0xE5, 0xE8, 0xEE), width=2)
    return ty + 12


def badge_row(g, y):
    """技术栈徽标条：四项等宽排开。副标题拆成短行，避免缩到 13px 以下。"""
    items = [
        ("Java 25", ("后端语言", "Maven 构建")),
        ("Spring Boot 3.5", ("web / service", "repository / domain")),
        ("PostgreSQL 18", ("+ PostGIS 3.6", "geometry · GiST 索引")),
        ("Vue 3 + Cesium", ("1.145 · 三维地球", "Vite 8 构建")),
    ]
    gap = 14
    w, xs = cols(len(items), gap)
    h = row_h(items, ts=16, ss=14)
    colors = (GREEN, GREEN, ORANGE, BLUE)
    fills = (GREEN_F, GREEN_F, ORANGE_F, BLUE_F)
    for (name, subs), x, c, f in zip(items, xs, colors, fills):
        check_lines((name,), 16, w - 2 * PAD, "徽标标题")
        check_lines(subs, 14, w - 2 * PAD, "徽标副标题")
        g.box(x, y, w, h, name, subs, border=c, fill=f,
              ts=16, ss=14, radius=10, align="center")
    return y + h


def flow_chain(g, y, steps, color, fill):
    """一条横向数据流：4 个步骤 + 3 个箭头。4 列是画布压到 1000 后的上限。"""
    arw = 18
    w, xs, arw = chain_x(len(steps), arw)
    h = row_h(steps, ts=16, ss=15)
    for i, (title, subs) in enumerate(steps):
        check_lines((title,), 16, w - 2 * PAD, "流程标题")
        check_lines(subs, 15, w - 2 * PAD, "流程副标题")
        g.box(xs[i], y, w, h, title, subs, border=color, fill=fill,
              ts=16, ss=15, radius=10, align="center")
        if i < len(steps) - 1:
            g.arrow(xs[i] + w + 2, y + h // 2, xs[i + 1] - 2, y + h // 2,
                    color=color, width=3)
    return y + h


def layer_arrows(g, y_top, y_bottom, down_label, up_label, down_color, up_color):
    """两层之间的双向箭头：左边往下（请求），右边往上（响应）。

    标签不用 arrow() 的 label —— 它在竖线上会盖出一个白缺口，
    这里自己用 text() 贴在线的右侧。两条竖线相距 260 px，
    而标签从线右侧 18 px 起画，所以下行标签必须短于约 240 px，
    否则会跟上行标签连成一句（第一版就是这里糊在一起的）。
    """
    mid = (y_top + y_bottom) / 2
    check_lines((down_label,), 15, 630 - (370 + 18) - 8, "层间下行标签")
    check_lines((up_label,), 15, W - M - (630 + 18), "层间上行标签")
    g.arrow(370, y_top + 2, 370, y_bottom - 2, color=down_color, width=3)
    g.text(388, mid, down_label, size=15, color=down_color, anchor="lm")
    g.arrow(630, y_bottom - 2, 630, y_top + 2, color=up_color, width=3)
    g.text(648, mid, up_label, size=15, color=up_color, anchor="lm")


TITLE = "Calcite · GPS 轨迹时空分析平台"


def overview():
    # 先给一块足够高的画布，画完再按内容裁到实际高度：
    # 竖版图的行数是算出来的，硬写高度很容易差几十像素把最后一行裁掉。
    g = Fig(1600, width=W)

    # ------------------------------------------------- 0 页头 + 技术栈徽标
    y = head(g, 30) + 40
    y = badge_row(g, y) + 46

    # ------------------------------------------------------------ ① 浏览器层
    y = sbox(g, M, y, CW, "① 浏览器 · Vue 3 + Cesium + 手写 SVG", (
        "App.vue 是唯一状态中心 · CesiumGlobe 画地球 / 轨迹 / 停留 / 热点 / 密度格",
        "TrackPlayer 播放条 · SpeedChart 速度海拔曲线 · 列表与图例只负责展示",
        "分析面板五档：停留点 / 热点 / 密度 / 相似 / 圈选（拉框 · 多边形 · 缓冲区）",
    ), border=PURPLE, fill=PURPLE_F, ts=20, ss=15) + 44

    layer_arrows(g, y - 44, y, "代理转 8080 · HTTP 请求 /api", "JSON 响应",
                 PURPLE, BLUE)

    # -------------------------------------------------------------- ② 后端层
    top = y
    y0 = top + 42                      # 容器标题那一行下面
    n = 4
    bw, x, arw = chain_x(n, 20)        # 960 = 4×225 + 3×20
    chain = [
        ("web/", ("Controller 收 HTTP 请求", "dto/ 只留前端要用的字段", "400 / 404 带中文原因")),
        ("service/", ("算法与编排（五档分析）", "importer/ 可插拔：GPX", "TrackCleaner 清洗 · 缓存")),
        ("repository/", ("方法名即 SQL", "点驱动查询命中 GiST 索引", "只取 id，不全量水合实体")),
        ("domain/", ("实体 = 数据库表的影子", "JTS Point/LineString", "SRID 4326（WGS84）")),
    ]
    inner_h = row_h(chain, ts=20, ss=15)
    g.d.rounded_rectangle([M, top, W - M, y0 + inner_h + 16], radius=14,
                          fill=(0xFA, 0xFA, 0xFA), outline=GREEN, width=3)
    g.text(M + 16, top + 12, "② 后端 · Spring Boot 3.5（端口 8080）— 四层，每层只干一件事",
           size=20, bold=True, color=INK)

    for bx, name, subs in zip(x, [c[0] for c in chain], [c[1] for c in chain]):
        g.box(bx, y0, bw, inner_h, name, subs, border=GREEN, fill=GREEN_F,
              ts=20, ss=15, align="center")
    for bx in x[:-1]:
        # 箭尖收在下一个框左边 1 px 处：arrow() 的箭头是**往回画**的两条短线，
        # 箭尖若顶到框上，那两条短线就会扎进框里（第一版就是这样）。
        g.arrow(bx + bw + 1, y0 + inner_h // 2, bx + bw + arw - 1, y0 + inner_h // 2,
                color=GREEN, width=3)

    y = y0 + inner_h + 16 + 44
    layer_arrows(g, y - 44, y, "SQL（GiST 空间 + 时空索引）", "结果集（一行行数据）",
                 GREEN, ORANGE)

    # ------------------------------------------------------------ ③ 数据库层
    y = sbox(g, M, y, CW, "③ 数据库 · PostgreSQL 18 + PostGIS 3.6（端口 5432）", (
        "track（每条出行一行）· track_point（原始 GPS 点，唯一真相）· stay_point（停留点）",
        "索引：GiST(geom) 空间 · GiST(geom, recorded_at) 时空联合 · btree(track_id, seq)",
        "表结构统一由 scripts/db/*.sql 管理，JPA ddl-auto=none（不让 Hibernate 猜 geometry）",
    ), border=ORANGE, fill=ORANGE_F, ts=20, ss=15) + 42

    # -------------------------------------------------------------- ④ 数据流
    g.text(M, y, "④ 数据流 · 两条主链路", size=20, bold=True, color=INK)
    y += 34

    def chain_label(row_y, text, color):
        g.text(M, row_y, text, size=16, color=color)
        return row_y + LINE

    y = flow_chain(g, chain_label(y, "写：文件进库", GREEN), (
        ("上传 GPX / PLT", ("网页上传或本地批量",)),
        ("解析（按内容识别）", ("不看扩展名，按内容识别",)),
        ("清洗", ("速度尖刺 · 海拔全同",)),
        ("批量入库", ("SHA-256 前 32 位幂等",)),
    ), GREEN, GREEN_F) + 16

    y = flow_chain(g, chain_label(y, "读：查询上屏", BLUE), (
        ("面板切档 / 拖地图", ("当前视野 bbox 传给后端",)),
        ("REST 接口", ("/api/analysis/*",)),
        ("实体 → DTO → JSON", ("只序列化前端要用的字段",)),
        ("地球图层 + 列表", ("Cesium 实体重绘，先删旧",)),
    ), BLUE, BLUE_F) + 26

    # ---------------------------------------------------------- 能力清单 M1-M3
    g.text(M, y, "能力清单 · M1-M3 + 数据管理（全部已完成）", size=20, bold=True, color=INK)
    y += 36
    caps = [
        ("M1 · 导入与回放", GREEN, GREEN_F, (
            "GPX/GeoLife 导入清洗幂等",
            "时间轴回放（60 秒播完）",
            "速度/海拔曲线 · 游标插值")),
        ("M2 · 停留与相似", CYAN, CYAN_F, (
            "停留点 50 m / 300 s",
            "跨轨迹热点 · 单链聚类",
            "密度对数色阶 · 相似度取小")),
        ("M3 · 空间范围查询", PURPLE, PURPLE_F, (
            "拉框 · 自由多边形 · 缓冲区",
            "region 回显 = 查询范围",
            "非法几何 400 · 不自动修复")),
        ("数据管理", ORANGE, ORANGE_F, (
            "改名 · 删除 · 替换 · 同名 409",
            "删除前先导出回收站",
            "任何写操作都清缓存")),
    ]
    gap = 14
    cw, cxs = cols(len(caps), gap)
    ch = row_h([(c[0], c[3]) for c in caps], ts=16, ss=15)
    for cx, (name, border, fill, subs) in zip(cxs, caps):
        check_lines((name,), 16, cw - 2 * PAD, "能力标题")
        check_lines(subs, 15, cw - 2 * PAD, "能力要点")
        g.box(cx, y, cw, ch, name, subs, border=border, fill=fill,
              ts=16, ss=15, align="center")
    y += ch + 26

    # ------------------------------------------------------------ 取舍注脚
    sbox(g, M, y, CW, "取舍注脚 · 三个最硬的技术决定", (
        "① 缓冲区不用 ST_DWithin（303 ms 且顺序扫描）—— 让 PostGIS 把圆算成多边形：7.9 ms（约 38 倍）",
        "② 密度必须用对数色阶 —— 每格轨迹数中位数 2 / 最大 152（76 倍），线性色阶下整张图等于白纸",
        "③ Cesium 的鼠标事件对象是模块级单例 —— 位置只存副本，否则自由多边形只能画出三角形",
    ), border=RED, fill=RED_F, ts=20, ss=16)

    # 收尾：按内容裁掉底部空白，让 save() 的贴边检查重新变得有意义
    # （裁完底边还有 30px 余量，真被裁的话 save() 会报"下边贴边(内容被裁)"）。
    mask = g.im.convert("L").point(lambda p: 255 if p < 250 else 0)
    bbox = mask.getbbox()
    if bbox:
        g.im = g.im.crop((0, 0, g.w, min(g.h, bbox[3] + 30)))
        g.h = g.im.height
    g.save("arch-overview.png")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    print("生成 README 全景架构图：")
    overview()
    if BAD:
        print("  ⚠ 自动检查发现 %d 处问题：" % len(BAD))
        for b in BAD:
            print("    -", b)
    else:
        print("  文字宽度检查：全部在框内，无豆腐块风险字符")
    print("完成 →", os.path.join(OUT_DIR, "arch-overview.png"))
