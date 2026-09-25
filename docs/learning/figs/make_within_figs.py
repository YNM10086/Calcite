# -*- coding: utf-8 -*-
"""生成 M3「圈选（空间范围查询）」报告里用的三张图（PNG）。

为什么不画 mermaid：officecli 在本机写不进 docx（见 global-knowledge），
Pillow 画成图片再用 python-docx 插进去最稳 —— 和 M1/M2 各阶段的配图同一套做法。

输出（都在本目录）：
  fig-within-1-shapes.png   三种画法 → 一条判定路径
  fig-within-2-perf.png     实测耗时对比（缓冲区写法 / 绑定变量换计划）
  fig-within-3-singleton.png ⭐ Cesium 事件对象是单例 —— "三角形"缺陷的原理图
"""
import os

from make_figs import (Fig, f, INK, GRAY, BLUE, BLUE_F, GREEN, GREEN_F, ORANGE,
                       ORANGE_F, RED, RED_F, PURPLE, PURPLE_F, CYAN, CYAN_F)

OUT = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- 图 1
def fig_shapes():
    fig = Fig(660)
    fig.title("图 1 · 三种画法，在后端合成同一条判定",
              "拉框 / 自由多边形 / 缓冲区 —— 为什么缓冲区不是「距离判断」")
    y = 150
    fig.box(60, y, 300, 130, "拉框", ("前端算 4 个角 → Rectangle", "后端：Polygon"), border=BLUE, fill=BLUE_F)
    fig.box(60, y + 150, 300, 130, "自由多边形", ("用户逐点点出 N 个顶点", "后端：Polygon"),
            border=ORANGE, fill=ORANGE_F)
    fig.box(60, y + 300, 300, 130, "缓冲区", ("前端只发「中心点 + 半径(米)」",
                                              "后端：ST_Buffer(点::geography, r)"), border=PURPLE, fill=PURPLE_F)
    # 中间：统一成一个多边形
    fig.arrow(365, y + 65, 455, 320, label="矩形")
    fig.arrow(365, y + 215, 455, 330, label="多边形")
    fig.arrow(365, y + 365, 455, 340, label="33 边形")
    fig.box(460, 250, 330, 190, "统一成一个多边形",
            ("三种形状到这里已经没区别了", "「圆」是后端用 PostGIS 算出来的",
             "所以它照样能命中空间索引"), border=CYAN, fill=CYAN_F, ts=26)
    fig.arrow(795, 345, 885, 345)
    fig.box(890, 235, 450, 220, "ST_Intersects(track.geom, 区域)",
            ("GiST 空间索引：先用外接矩形粗筛",
             "再逐条精确判断「线与多边形是否相交」",
             "→ 命中列表 + 区域统计"), border=GREEN, fill=GREEN_F, ts=26)
    fig.text(60, 600, "会话里一句话：前端只负责「画出区域」，判定与统计的真相全在后端（同一段 SQL）。",
             size=19, color=GRAY)
    fig.save("fig-within-1-shapes.png")


# ---------------------------------------------------------------- 图 2
def fig_perf():
    fig = Fig(700)
    fig.title("图 2 · 实测耗时：同一个查询，写法不同差 38 倍",
              "PostgreSQL 18.3 + PostGIS 3.6，`EXPLAIN ANALYZE` 实测（北京 228 条候选轨迹）")

    def bar(y, label, ms, maxms, color, note):
        x0, wmax = 470, 700
        fig.text(60, y + 8, label, size=20)
        fig.d.rectangle([x0, y, x0 + wmax * ms / maxms, y + 34], fill=color)
        fig.text(x0 + wmax * ms / maxms + 12, y + 8, f"{ms} ms", size=20, bold=True, color=color)
        fig.text(60, y + 36, note, size=16, color=GRAY)

    bar(120, "缓冲区：ST_DWithin(点::geography, r)", 303, 303, RED,
        "顺序扫描（Seq Scan）：对每条候选轨迹的每个顶点算一遍椭球距离，索引帮不上忙")
    bar(215, "缓冲区：ST_Intersects(track, ST_Buffer(…))", 7.9, 303, GREEN,
        "Index Scan：先把圆算成多边形，之后与拉框/手画多边形走完全相同的谓词 → 约 38 倍")
    bar(310, "上海那一组：292 ms → 8.2 ms", 8.2, 303, GREEN,
        "候选只剩 1 条也照样差距巨大 —— 说明瓶颈不是「扫了多少行」，而是「每个顶点算什么」")
    bar(405, "区域点数统计：字面量 180 ms / 绑定参数 456 ms", 456, 456, ORANGE,
        "同一个 SQL：绑定参数会走通用计划，优化器改选空间索引 + 多付一次外部排序落盘（2.1 MB）")
    bar(535, "接口总耗时（含统计）203 ~ 628 ms", 628, 628, BLUE,
        "远低于 1000 ms 红线；本轮不做进一步优化，只把区间与原因记在文档里")

    fig.text(60, 640, "结论：能走索引的前提是「把圆变成多边形」；能变慢的原因是「优化器换了计划」。",
             size=19, color=INK, bold=True)
    fig.save("fig-within-2-perf.png")


# ---------------------------------------------------------------- 图 3（⭐ 重点节）
def fig_singleton():
    fig = Fig(680)
    fig.title("图 3 · 「多边形只能是三角形」的原理：事件对象是同一个",
              "Cesium 的鼠标事件对象是模块级单例 —— 存引用，等于存了「最后一次点击」")

    # 左：你以为的
    fig.box(60, 140, 560, 360, "你以为的（也是 .d.ts 给人的印象）",
            ("每次点击 → 一个新的 Cartesian2", "数组里 4 格 = 4 个不同的点",
             "距离(第 4 点, 第 1 点) = 566px", "→ 不该闭合，继续加点"),
            border=BLUE, fill=BLUE_F, ts=25)
    for i, x in enumerate((110, 220, 330, 440)):
        fig.box(x, 330, 80, 76, f"点{i + 1}", (), border=BLUE, fill=(255, 255, 255),
                ts=21, radius=8)
    fig.text(340, 440, "四个独立对象 → 距离算得出", size=18, color=GRAY, anchor="ma")

    # 右：实际发生的
    fig.box(700, 140, 640, 360, "实际发生的（Cesium 源码 237297-237320）",
            ("mouseClickEvent.position 是模块级的一个对象",
             "每次点击：Cartesian2.clone(新位置, 同一个对象)",
             "→ 写进同一个对象，再交给 handler"),
            border=RED, fill=RED_F, ts=25)
    fig.box(730, 300, 150, 110, "1 个对象", ("x/y 被改写 4 次",),
            border=RED, fill=(255, 255, 255), ts=21)
    for i, y in enumerate((300, 348, 396, 444)):
        fig.box(950, y, 115, 40, f"数组[{i}]", (), border=RED, fill=(255, 255, 255),
                ts=19, radius=8)
        fig.arrow(886, 355, 944, y + 20, color=RED, width=2)
    fig.text(1090, 330, "数组 4 格", size=19, color=RED, bold=True)
    fig.text(1090, 360, "全是同一个引用", size=19, color=RED, bold=True)

    fig.box(60, 520, 1280, 60,
            "距离(本次点击, 数组[0]) ≡ 0  →  第 4 次点击被当成「点回起点」",
            (), border=RED, fill=RED_F, ts=22)
    fig.box(60, 600, 1280, 60,
            "修法：screenCopy(p) = new Cartesian2(p.x, p.y) —— 存副本，绝不存事件对象本身",
            (), border=GREEN, fill=GREEN_F, ts=22)
    fig.save("fig-within-3-singleton.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    fig_shapes()
    fig_perf()
    fig_singleton()
    print("完成：fig-within-1-shapes / fig-within-2-perf / fig-within-3-singleton")
