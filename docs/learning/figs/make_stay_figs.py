# -*- coding: utf-8 -*-
"""生成《M2 第一阶段：停留点算法》学习笔记里用的图（PNG）。

复用 make_figs.py 里的 Fig 类（同一套配色和排版），只加本阶段的新图。

图 5 用的是**真实数据**：直接读 backend/src/test/resources/sample-real.plt，
在 Python 里把同一套算法再实现一遍，画出真实的 71 个点和真实的窗口扩张曲线。
这样图上每个数字都能跟后端 API 对上，不是"示意图"。

输出：docs/learning/figs/fig-s*.png
运行：python docs/learning/figs/make_stay_figs.py   （在仓库根目录跑）
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_figs import (  # noqa: E402
    Fig, BG, INK, GRAY, BLUE, BLUE_F, GREEN, GREEN_F, ORANGE, ORANGE_F,
    PURPLE, PURPLE_F, RED, RED_F, CYAN, CYAN_F, f,
)
from PIL import ImageDraw  # noqa: E402

D, T, G = 50.0, 300.0, 300.0          # 默认参数：直径 50 米 / 最短 300 秒 / 间隔 300 秒
PLT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "..", "..", "backend", "src", "test", "resources", "sample-real.plt")


# ------------------------------------------------------------------ 真实数据 + 算法
def haversine(lat1, lon1, lat2, lon2):
    R = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_plt(path):
    pts = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) != 7:
                continue
            try:
                lat, lon, alt = float(parts[0]), float(parts[1]), float(parts[3])
                hh, mm, ss = (int(x) for x in parts[6].split(":"))
            except ValueError:
                continue
            pts.append((lat, lon, alt, hh * 3600 + mm * 60 + ss))
    return pts


def radius_of(pts, a, b):
    n = b - a + 1
    clat = sum(p[0] for p in pts[a:b + 1]) / n
    clon = sum(p[1] for p in pts[a:b + 1]) / n
    return max(haversine(clat, clon, p[0], p[1]) for p in pts[a:b + 1])


def detect(pts):
    """后端 StayPointService.detect 的 1:1 复刻，用来核对图上数字。"""
    out, n, i = [], len(pts), 0
    while i < n:
        j = i
        grow = []                      # 记录窗口每次长大的半径，供图 5 画曲线
        while j + 1 < n:
            if pts[j + 1][3] - pts[j][3] > G:
                break
            r = radius_of(pts, i, j + 1)
            if r * 2 > D:
                break
            j += 1
            grow.append((j - i + 1, r))
        span = pts[j][3] - pts[i][3]
        if j > i and span >= T:
            out.append((i, j, span, radius_of(pts, i, j), j - i + 1, grow))
            i = j + 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------- 图 1 三个拦路虎
def fig_s1():
    g = Fig(880)
    g.title("图 1 · 停留点是什么，以及为什么它比想象的难",
            "停留点 = 「这个人在这块地方待了一会儿没走」。难点全在：GPS 不是尺子。")

    # 左：飘移散点
    cx, cy, R = 340, 500, 200          # R 像素 = 25 米（即 D/2）
    g.d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(0xFF, 0xF3, 0xE0))
    g.d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=ORANGE, width=3)
    rnd = random.Random(20081023)
    for _ in range(46):
        a, rr = rnd.uniform(0, 2 * math.pi), R * math.sqrt(rnd.random()) * 0.92
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        g.d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(0x16, 0x5D, 0xFF),
                    outline=(0xFF, 0xFF, 0xFF), width=2)
    g.d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=RED)
    g.text(cx, cy + R + 26, "虚线圈 = 允许的活动范围（直径 50 米）", size=18,
           color=ORANGE, anchor="ma")
    g.text(cx, cy + R + 56, "红点 = 人真正站的位置", size=18, color=RED, anchor="ma")
    g.text(cx, cy + R + 86, "蓝点 = GPS 报出来的位置（46 个点全在飘）", size=18,
           color=BLUE, anchor="ma")

    # 右：三个拦路虎
    cards = [
        ("① GPS 会飘，所以「没动」不等于「坐标不变」",
         ("站着不动时，每秒钟报的坐标能差出十几米。",
          "实测：即使站着不动，逐点速度的第 5 百分位仍有 0.3~0.65 米/秒 ——",
          "比走路慢，但绝不是 0。所以「速度小于某值就是停留」这条路直接废掉。"),
         ORANGE, ORANGE_F),
        ("② 信号会断，所以「时间差大」不等于「待得久」",
         ("进地铁、没电、GPS 丢星，都会让中间几百秒没有点。",
          "真实数据里有一条轨迹断了 8217 秒（2.3 小时），前后还在同一个位置。",
          "不防这一手，它就会被判成「在这里停了 2.3 小时」。"),
         RED, RED_F),
        ("③ 半径给大了，走路也会被算成停留",
         ("半径 100 米时，「60 秒走 84 米」也落在圈里 → 被判成停留。",
          "半径 30 米时，真实的停留又几乎全被漏掉。",
          "所以半径这个参数必须小（50 米）且要配合「时长」一起用。"),
         PURPLE, PURPLE_F),
    ]
    y = 160
    for title, subs, border, fill in cards:
        g.d.rounded_rectangle([620, y, 1340, y + 190], radius=14, fill=fill,
                              outline=border, width=3)
        for k, ln in enumerate(title.split("\n")):
            g.text(648, y + 22 + k * 28, ln, size=20, bold=True, color=INK)
        for k, ln in enumerate(subs):
            g.text(648, y + 62 + k * 26, ln, size=16, color=(0x4E, 0x59, 0x69))
        y += 214
    g.save("fig-s1-what.png")


# ------------------------------------------------------------------ 图 2 主流程
def fig_s2():
    g = Fig(1080)
    g.title("图 2 · 算法主流程：一个只会往右滑的窗口",
            "思路一句话：从每个点出发，尽量往右圈进更多的点；圈不动了就看看圈住的这段够不够「久」。")

    L, LW = 90, 470           # 左列（把窗口撑大）
    R, RW = 780, 520          # 右列（结算一段）

    g.box(L, 150, LW, 76, "i = 0（从第一个点开始试）", (), border=PURPLE, fill=PURPLE_F)
    g.box(L, 270, LW, 86, "窗口 = [ i .. j ]，先让 j = i",
          ("窗口里目前只有 1 个点",), border=BLUE, fill=BLUE_F)

    g.box(L, 400, LW, 96, "j + 1 这个点，能并进来吗？",
          ("两个条件都要满足 ↓",), border=CYAN, fill=CYAN_F)
    g.box(L, 530, LW, 100, "规则 3 · 断档：时间间隔 ≤ 300 秒？",
          ("断了就说明中间没数据，窗口到此为止",), border=RED, fill=RED_F)
    g.box(L, 665, LW, 100, "规则 1 · 空间：并进来后仍 ≤ 25 米？",
          ("25 米 = 直径 50 米的一半",), border=ORANGE, fill=ORANGE_F)
    g.box(L, 800, LW, 84, "j = j + 1（窗口长大一格）",
          ("然后回到上面继续问下一个点",), border=GREEN, fill=GREEN_F)

    g.box(R, 400, RW, 96, "结算窗口 [ i .. j ]",
          ("不能再长大了，看看这一段算不算停留",), border=CYAN, fill=CYAN_F)
    g.box(R, 530, RW, 100, "规则 2 · 时长：跨度 ≥ 300 秒？",
          ("用首尾两点的时刻相减，不是点数 × 间隔",), border=ORANGE, fill=ORANGE_F)
    g.box(R, 665, RW, 112, "记下一个停留点（最终输出）",
          ("中心 = 窗口重心 · 半径 = 最远那个点到重心的距离",
           "规则 4 · 跳过整段：i = j + 1"), border=GREEN, fill=GREEN_F)
    g.box(R, 845, RW, 96, "不够久 → 放弃第一个点",
          ("i = i + 1，从下一个点重新开始试",), border=GRAY, fill=(0xF2, 0xF4, 0xF7))

    g.d.rounded_rectangle([90, 950, 1310, 1020], radius=12, fill=(0xEC, 0xEF, 0xF1),
                          outline=INK, width=2)
    g.text(700, 985, "右边两种情况做完，i 都会往右走，然后回到最上面重新开始 —— 直到 i 走到最后一个点",
           size=18, bold=True, color=INK, anchor="mm")

    # 主干箭头
    g.arrow(L + LW / 2, 226, L + LW / 2, 270)
    g.arrow(L + LW / 2, 356, L + LW / 2, 400)
    g.arrow(L + LW / 2, 496, L + LW / 2, 530)
    g.arrow(L + LW / 2, 630, L + LW / 2, 665, label="是", label_dx=-40)
    g.arrow(L + LW / 2, 765, L + LW / 2, 800, label="是", label_dx=-40)
    # 回到"窗口"的环
    g.arrow(L - 6, 842, L - 46, 842, color=GREEN)
    g.d.line([L - 46, 842, L - 46, 313], fill=GREEN, width=3)
    g.arrow(L - 46, 313, L - 6, 313, color=GREEN)
    g.text(L - 38, 590, "继续", size=15, color=GREEN, anchor="lm")

    # 到右列
    g.arrow(L + LW, 448, R, 448, label="否", label_dy=-20)
    g.arrow(L + LW, 580, R, 580, label="否（断了）", label_dy=-20)
    g.arrow(L + LW, 715, R, 715, label="否（超了）", label_dy=-20)
    g.arrow(R + RW / 2, 496, R + RW / 2, 530)
    g.arrow(R + RW / 2, 630, R + RW / 2, 665, label="是", label_dx=-34, label_dy=0)
    g.arrow(R + RW, 580, R + RW + 44, 580, color=GRAY, label="否", label_dx=40, label_dy=-14)
    g.d.line([R + RW + 44, 580, R + RW + 44, 893], fill=GRAY, width=3)
    g.arrow(R + RW + 44, 893, R + RW, 893, color=GRAY)
    g.save("fig-s2-flow.png")


# ------------------------------------------------------------------ 图 3 四条规则
def fig_s3():
    g = Fig(1010)
    g.title("图 3 · 四条规则，每条都在挡一种错误",
            "少任何一条都会出错 —— 这不是「加保险」，是算法成立的必要条件。")

    rows = [
        ("规则 1", "空间：窗口内所有点到重心的距离 ≤ 25 米", "半径 = 直径 ÷ 2",
         "挡住「其实在走路」。去掉它 → 整条轨迹会被当成一个巨大的停留点。",
         "StayPointService.java 第 73 行：radiusOf(...) * 2 > radiusM", ORANGE, ORANGE_F),
        ("规则 2", "时长：窗口首尾时刻相差 ≥ 300 秒", "用时刻相减，不是数点数",
         "挡住「路过」。去掉它 → 在路口等个红灯（20 秒）也会报一个停留点。",
         "StayPointService.java 第 79-81 行：span >= minDurationS", BLUE, BLUE_F),
        ("规则 3", "断档：窗口内相邻两点间隔 ≤ 300 秒", "这一条最容易被漏掉",
         "挡住「信号中断」。去掉它 → 2.3 小时的空白被算成 2.3 小时的停留（见图 4）。",
         "StayPointService.java 第 67-71 行：gap > maxGapS", RED, RED_F),
        ("规则 4", "跳段：找到一个停留点后，i 直接跳到 j + 1", "不是 i = i + 1",
         "挡住「同一段停留被报好几次」。去掉它 → 一次停留会输出几十个重叠结果。",
         "StayPointService.java 第 83 行：i = j + 1", PURPLE, PURPLE_F),
    ]
    y = 165
    for tag, rule, sub, why, code, border, fill in rows:
        g.d.rounded_rectangle([60, y, 1340, y + 180], radius=14, fill=fill,
                              outline=border, width=3)
        g.d.rounded_rectangle([84, y + 26, 214, y + 74], radius=10, fill=border)
        g.text(149, y + 50, tag, size=22, bold=True, color=(0xFF, 0xFF, 0xFF), anchor="mm")
        g.text(238, y + 28, rule, size=23, bold=True, color=INK)
        g.text(238, y + 68, sub, size=17, color=border)
        g.text(238, y + 100, why, size=17, color=(0x4E, 0x59, 0x69))
        g.text(238, y + 136, code, size=15, color=GRAY, mono=True)
        y += 200
    g.save("fig-s3-rules.png")


# ------------------------------------------------------------------ 图 4 断档事故
def fig_s4():
    g = Fig(820)
    g.title("图 4 · 规则 3 的来历：真实数据里的一次 2.3 小时断档",
            "这条规则不是拍脑袋定的，是被一条真实轨迹「教」出来的。")

    y0 = 300
    g.d.line([110, y0, 1310, y0], fill=(0xCE, 0xD5, 0xDD), width=2)
    g.text(110, y0 + 34, "时间 →", size=17, color=GRAY)

    for k in range(11):                       # 断档前：同一点附近的 11 个点
        x = 130 + k * 24
        g.d.ellipse([x - 7, y0 - 7, x + 7, y0 + 7], fill=BLUE,
                    outline=(0xFF, 0xFF, 0xFF), width=2)
    for k in range(11):                       # 断档后：同一位置又来 11 个点
        x = 850 + k * 24
        g.d.ellipse([x - 7, y0 - 7, x + 7, y0 + 7], fill=BLUE,
                    outline=(0xFF, 0xFF, 0xFF), width=2)

    g.d.rounded_rectangle([400, y0 - 46, 830, y0 - 12], radius=8,
                          fill=RED_F, outline=RED, width=2)
    g.text(615, y0 - 29, "8217 秒（2.3 小时）一个点都没有", size=18, bold=True,
           color=RED, anchor="mm")
    g.arrow(400, y0 - 8, 380, y0 - 8, color=RED)
    g.arrow(830, y0 - 8, 850, y0 - 8, color=RED)
    g.text(184, y0 + 74, "轨迹 20081115010133 中断前的最后几个点", size=16,
           color=BLUE, anchor="ma")
    g.text(985, y0 + 74, "恢复后又出现在同一个位置", size=16, color=BLUE, anchor="ma")

    # 两种判定的对照
    g.d.rounded_rectangle([110, 420, 690, 560], radius=14, fill=RED_F, outline=RED, width=3)
    g.text(140, 442, "不加规则 3，算法看到的是：", size=21, bold=True, color=RED)
    g.text(140, 484, "首尾时刻差了 8217 秒 ≥ 300 秒 →「时长够了」", size=17, color=INK)
    g.text(140, 514, "空间上前后都在同一处 →「半径也没超」", size=17, color=INK)
    g.text(140, 544 - 6, "结论：这个人在这里停留了 2.3 小时", size=17, bold=True, color=RED)

    g.d.rounded_rectangle([720, 420, 1310, 560], radius=14, fill=GREEN_F, outline=GREEN, width=3)
    g.text(750, 442, "加了规则 3，算法看到的是：", size=21, bold=True, color=GREEN)
    g.text(750, 484, "这 8217 秒里有「断档」，窗口在这里就断了", size=17, color=INK)
    g.text(750, 514, "断成两段后，每一段都不到 300 秒", size=17, color=INK)
    g.text(750, 538, "结论：什么也不报（这条轨迹的正确答案是 0 个停留点）",
           size=17, bold=True, color=GREEN)

    g.d.rounded_rectangle([110, 600, 1310, 740], radius=14, fill=ORANGE_F, outline=ORANGE, width=3)
    g.text(140, 622, "这条规则对整个数据集的影响有多大", size=21, bold=True, color=ORANGE)
    g.text(140, 668, "21 条真实轨迹的停留段数：", size=19, color=INK)
    g.text(420, 668, "漏掉规则 3 → 23 段（虚高 2.3 倍）", size=19, bold=True, color=RED)
    g.text(420, 706, "加上规则 3 → 10 段（正确答案）", size=19, bold=True, color=GREEN)
    g.text(850, 668, "注意：我是先写了探索脚本、", size=17, color=GRAY)
    g.text(850, 700, "漏了这条才发现数字对不上，", size=17, color=GRAY)
    g.text(850, 732, "回头补进设计和代码里的。", size=17, color=GRAY)
    g.save("fig-s4-gap.png")


# ------------------------------------------------------------------ 图 5 真实数据
def fig_s5():
    raw = load_plt(os.path.abspath(PLT))
    found = detect(raw)
    assert len(found) == 1, f"预期 sample-real.plt 正好 1 个停留点，实得 {len(found)}"
    a, b, span, radius, count, grow = found[0]

    g = Fig(960)
    g.title("图 5 · 真实数据跑一遍（sample-real.plt，908 个点）",
            f"算法输出：第 {a}~{b} 号点 · 时长 {span} 秒 · 半径 {radius:.1f} 米 · 共 {count} 个点")

    # 左：把这段停留的点画成散点（换成以重心为原点的米）
    cx, cy, SCALE = 360, 520, 4.6        # 4.6 像素 / 米
    clat = sum(p[0] for p in raw[a:b + 1]) / count
    clon = sum(p[1] for p in raw[a:b + 1]) / count
    R2 = radius * SCALE
    R25 = 25.0 * SCALE

    for r, col, dash in ((R25, ORANGE, True), (R2, GREEN, False)):
        box = [cx - r, cy - r, cx + r, cy + r]
        if dash:
            for k in range(72):
                if k % 2:
                    continue
                g.d.arc(box, k * 5, k * 5 + 5, fill=col, width=3)
        else:
            g.d.ellipse(box, outline=col, width=3)

    for k in range(a, b + 1):
        lat, lon = raw[k][0], raw[k][1]
        x = cx + haversine(clat, clon, clat, lon) * (1 if lon >= clon else -1) * SCALE
        y = cy - haversine(clat, clon, lat, clon) * (1 if lat >= clat else -1) * SCALE
        order = k - a
        t = order / max(1, count - 1)
        col = (int(0x16 + 0x90 * t), int(0x5D + 0x30 * t), int(0xFF - 0x60 * t))
        g.d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=col)
    g.d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=RED)
    g.text(cx, cy + R25 + 30, "虚线圈 25 米 = 规则 1 的上限", size=17, color=ORANGE, anchor="ma")
    g.text(cx, cy + R25 + 58, f"实线圈 {radius:.1f} 米 = 实际算出来的活动半径", size=17,
           color=GREEN, anchor="ma")
    g.text(cx, cy + R25 + 86, "点从深蓝渐变到浅色 = 时间由早到晚", size=17,
           color=GRAY, anchor="ma")

    # 右：窗口扩张曲线（真实数字）
    ox, oy, ow, oh = 800, 250, 500, 460
    g.d.rectangle([ox, oy, ox + ow, oy + oh], fill=(0xFA, 0xFB, 0xFC),
                  outline=(0xCE, 0xD5, 0xDD), width=2)
    g.text(ox, oy - 34, "窗口从第 0 个点开始往右撑，半径怎么变", size=19, bold=True, color=INK)
    g.text(ox, oy - 6, "纵轴 = 窗口内最远的点到重心的距离（米）", size=15, color=GRAY)

    maxr = 30.0
    ythr = oy + oh - (25.0 / maxr) * oh
    g.d.line([ox, ythr, ox + ow, ythr], fill=RED, width=2)
    for k in range(0, int(ow), 12):
        if k % 24:
            continue
        g.d.line([ox + k, ythr, ox + k + 12, ythr], fill=RED, width=2)
    g.text(ox + ow - 10, ythr - 26, "25 米上限（规则 1）", size=15, color=RED, anchor="ra")

    n = len(grow)
    pts = [(ox + (idx / max(1, n - 1)) * ow,
            oy + oh - min(r, maxr) / maxr * oh) for idx, (c, r) in enumerate(grow)]
    for p, q in zip(pts, pts[1:]):
        g.d.line([p, q], fill=BLUE, width=3)
    for p in pts:
        g.d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=BLUE)
    if pts:
        g.d.line([pts[-1][0], pts[-1][1], pts[-1][0], oy + oh], fill=GRAY, width=2)
    g.text(ox + ow / 2, oy + oh + 34,
           f"这条曲线一共爬了 {n} 格，就是窗口长大的过程", size=17, color=GRAY, anchor="ma")

    g.d.rounded_rectangle([110, 800, 1310, 930], radius=14, fill=BLUE_F, outline=BLUE, width=3)
    g.text(140, 820, "这段停留为什么特别适合当「指纹测试」", size=20, bold=True, color=BLUE)
    g.text(140, 858, f"• 时长 {span} 秒，离 300 秒的门槛只差 {int(span - 300)} 秒", size=17, color=INK)
    g.text(140, 888, f"• 半径 {radius:.1f} 米，离 25 米的上限只差 {25 - radius:.1f} 米", size=17, color=INK)
    g.text(760, 858, "两个阈值都离得这么近，算法但凡改错一点，", size=17, color=GRAY)
    g.text(760, 888, "这个测试立刻变红 —— 等于给算法钉了个钉子。", size=17, color=GRAY)
    g.save("fig-s5-real.png")


# ------------------------------------------------------------------ 图 6 数据流
def fig_s6():
    g = Fig(820)
    g.title("图 6 · 一个停留点从数据库走到屏幕上，经过哪些地方",
            "沿着这条线走一遍，就知道每个文件为什么存在、要改东西该动哪个。")

    steps = [
        ("① 你点了一条轨迹\nApp.vue", "发出请求\nGET /api/tracks/5/stay-points", BLUE, BLUE_F),
        ("② TrackController\nweb/", "去数据库捞这条轨迹的所有点\n拆成 (lat, lon, 时刻)", CYAN, CYAN_F),
        ("③ StayPointService\nservice/", "核心算法：滑动窗口 + 四条规则\n★ 这一阶段真正新写的东西", ORANGE, ORANGE_F),
        ("④ StayPointDto\nweb/dto/", "把结果转成前端看得懂的 JSON\n时刻 / 时长 / 中心点 / 半径 / 点数", PURPLE, PURPLE_F),
        ("⑤ App.vue 收到", "存进 stays 变量\n顺手给列表和地球各递一份", GREEN, GREEN_F),
        ("⑥ 屏幕上出现", "StayPointList：面板里逐条列出\nCesiumGlobe：地球上画半透明橙圈", RED, RED_F),
    ]
    y = 170
    for title, sub, border, fill in steps:
        g.d.rounded_rectangle([80, y, 1320, y + 84], radius=12, fill=fill,
                              outline=border, width=2)
        for k, ln in enumerate(title.split("\n")):
            g.text(108, y + 14 + k * 26, ln, size=18, bold=True, color=INK)
        for k, ln in enumerate(sub.split("\n")):
            g.text(560, y + 22 + k * 26, ln, size=17, color=(0x4E, 0x59, 0x69))
        y += 100
    g.text(700, 790, "⑥ 里那两个组件都是**纯展示**：props 进来就画，不自己发请求",
           size=17, color=GRAY, anchor="ma")
    g.save("fig-s6-dataflow.png")


# ------------------------------------------------------------------ 图 7 往哪加
def fig_s7():
    g = Fig(900)
    g.title("图 7 · 以后想改这个功能，分别动哪里",
            "这份笔记最实用的一张表 —— 左边是「我想……」，右边是「动这个文件」。")

    items = [
        ("我想调参数\n（50 米 / 300 秒）", "backend/src/main/resources/application.yml",
         "calcite.stay-point.* 三行，改完重启后端即可，代码一行不用动", BLUE, BLUE_F),
        ("我想加一条新规则\n（比如限制最高速度）", "StayPointService.java 的 detect()",
         "在扩窗口的判断里加一个 if break；新参数照抄 @Value 的写法", ORANGE, ORANGE_F),
        ("我想换一套算法\n（比如 DBSCAN 聚类）", "只换 StayPointService 的内部实现",
         "detect(List<RawPoint>) 的签名不变，Controller / 前端 / 测试全都不用动", PURPLE, PURPLE_F),
        ("我想把结果存进数据库", "新加 SQL + StayPointRepository + 改 Controller",
         "stay_point 表已经建好了、一直空着；等 M3 要跨轨迹查询时再做才划算", CYAN, CYAN_F),
        ("我想做「热点区域」\n（哪些地方总被停留）", "新建一个 HotspotService",
         "拿所有轨迹的停留点当输入做空间聚类；复用现成的 GeoUtils 距离函数", GREEN, GREEN_F),
        ("我想在曲线上标出\n停留时段（色带）", "frontend/src/lib/chart.js + SpeedChart.vue",
         "这阶段你选了不做（布局 A）；要做时给图加一层矩形即可", RED, RED_F),
    ]
    y = 160
    for want, where, how, border, fill in items:
        g.d.rounded_rectangle([60, y, 1340, y + 108], radius=12, fill=fill,
                              outline=border, width=2)
        for k, ln in enumerate(want.split("\n")):
            g.text(84, y + 26 + k * 26, ln, size=18, bold=True, color=INK)
        g.text(400, y + 26, "→", size=24, bold=True, color=border)
        g.text(440, y + 24, where, size=17, bold=True, color=border, mono=True)
        g.text(440, y + 60, how, size=16, color=(0x4E, 0x59, 0x69))
        y += 120
    g.save("fig-s7-extend.png")


if __name__ == "__main__":
    os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
    print("生成图片：")
    fig_s1()
    fig_s2()
    fig_s3()
    fig_s4()
    fig_s5()
    fig_s6()
    fig_s7()
    print("完成")
