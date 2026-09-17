# -*- coding: utf-8 -*-
r"""生成 M2 第二阶段热点文档用的两张图。

图 1：为什么你看不到自己的数据 —— 你的 GPX（福建）vs GeoLife（北京），相距 1665 公里
图 2：前端怎么用 —— 用真实截图标注三步

复用 docs/learning/figs/make_figs.py 里的 Fig 类（同一套配色）。

用法（在仓库根目录跑）：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" docs\learning\figs\make_hotspot_figs.py
"""
import json
import math
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_figs import (  # noqa: E402
    Fig, INK, GRAY, BLUE, BLUE_F, GREEN, GREEN_F, ORANGE, ORANGE_F,
    PURPLE, PURPLE_F, RED, RED_F, CYAN_F, CYAN,
)
from PIL import Image, ImageDraw  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
BASE = "http://localhost:8080"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch():
    """取用户 GPX 的轨迹点和 GeoLife 的热点"""
    gpx_pts, geolife_stays = [], []
    for t in get("/api/tracks?limit=500")["items"]:
        detail = get(f"/api/tracks/{t['id']}")
        pts = detail.get("points") or []
        if t.get("source") == "gpx" and pts:
            step = max(1, len(pts) // 260)
            gpx_pts.append([(p["lon"], p["lat"]) for p in pts[::step]])
        if t.get("source") == "geolife":
            for s in get(f"/api/tracks/{t['id']}/stay-points").get("stays", []):
                geolife_stays.append((s["lon"], s["lat"]))
    return gpx_pts, geolife_stays


def draw_track(g, pts, ox, oy, scale, color):
    """把一串经纬度画进 (ox,oy) 为原点的框里"""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    prev = None
    for lon, lat in pts:
        x = ox + (lon - cx) * scale * math.cos(math.radians(cy))
        y = oy - (lat - cy) * scale
        if prev:
            g.d.line([prev, (x, y)], fill=color, width=2)
        prev = (x, y)


def fig_why():
    g = Fig(700)
    g.title("图 1 · 为什么你在热点里看不到自己的数据",
            "不是没显示 —— 是热点全部来自 GeoLife（北京），而你的数据在福建，两地相距 1665 公里。")

    # ---- 左：你的 GPX ----
    g.d.rounded_rectangle([60, 170, 590, 600], radius=14, fill=GREEN_F, outline=GREEN, width=3)
    g.text(90, 192, "你的数据（福建龙岩一带）", size=23, bold=True, color=INK)
    g.text(90, 228, "经纬度约 25.03°N, 117.02°E", size=16, color=GRAY)

    g.d.rectangle([90, 262, 560, 470], fill=(0xFA, 0xFC, 0xFA), outline=(0xCE, 0xD5, 0xDD))
    for pts in GPX_TRACKS:
        draw_track(g, pts, 325, 366, 30000, GREEN)

    g.text(325, 496, "3 条轨迹 · 1821 个点", size=18, color=INK, anchor="ma")
    g.text(325, 528, "停留点 0 个", size=22, bold=True, color=RED, anchor="ma")
    g.text(325, 562, "→ 对热点没有任何贡献", size=16, color=RED, anchor="ma")

    # ---- 中：距离 ----
    g.text(700, 300, "相距", size=20, color=INK, anchor="ma")
    g.text(700, 340, "1665", size=40, bold=True, color=RED, anchor="ma")
    g.text(700, 388, "公里", size=20, color=INK, anchor="ma")
    g.arrow(610, 420, 800, 420, color=RED, width=3)
    g.arrow(800, 420, 610, 420, color=RED, width=3)
    g.text(700, 452, "切到热点模式时\n相机飞到北京", size=15, color=GRAY, anchor="ma")

    # ---- 右：GeoLife ----
    g.d.rounded_rectangle([810, 170, 1340, 600], radius=14, fill=ORANGE_F, outline=ORANGE, width=3)
    g.text(840, 192, "GeoLife（北京五道口一带）", size=23, bold=True, color=INK)
    g.text(840, 228, "经纬度约 40.00°N, 116.32°E", size=16, color=GRAY)

    g.d.rectangle([840, 262, 1310, 470], fill=(0xFA, 0xFC, 0xFA), outline=(0xCE, 0xD5, 0xDD))
    # 三个热点（按真实相对位置摆）
    sx, sy = 840, 262
    span_lon, span_lat = 0.030, 0.0085
    for lon, lat, n, col in HOTSPOTS:
        x = sx + 40 + (lon - 116.2935) / span_lon * 430
        y = sy + 195 - (lat - 40.0060) / span_lat * 180
        r = 10 + 6 * (n - 2)
        light = tuple(int(c * 0.30 + 255 * 0.70) for c in col)   # 手动调浅，Pillow 不会自动混合 alpha
        g.d.ellipse([x - r, y - r, x + r, y + r], fill=light, outline=col, width=3)
        g.text(x, y - r - 16, f"{n} 次", size=13, bold=True, color=col, anchor="ma")

    g.text(1075, 496, "21 条轨迹 · 11899 个点", size=18, color=INK, anchor="ma")
    g.text(1075, 528, "停留点 10 个 → 3 个热点", size=22, bold=True, color=GREEN, anchor="ma")
    g.text(1075, 562, "→ 热点全部来自这里", size=16, color=GREEN, anchor="ma")
    g.save("fig-hot-1-why.png")


def fig_howto():
    src = os.path.abspath(os.path.join(OUT, "..", "..", "..", ".tmp", "hotspot-ui.png"))
    rect_f = os.path.abspath(os.path.join(OUT, "..", "..", "..", ".tmp", "hotspot-ui-rects.json"))
    if not os.path.exists(src) or not os.path.exists(rect_f):
        print("  ⚠ 缺少截图或元素位置文件，跳过图 2")
        return
    with open(rect_f, encoding="utf-8") as fh:
        rects = json.load(fh)

    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.resize((1400, int(h * 1400 / w)), Image.LANCZOS)
    W, SH = im.size
    TOP = 90
    BOTTOM = 74
    canvas = Image.new("RGB", (W, SH + TOP + BOTTOM), (255, 255, 255))
    canvas.paste(im, (0, TOP))
    d = ImageDraw.Draw(canvas)
    from make_figs import f as font

    d.text((40, 24), "图 2 · 前端怎么用：点一下「热点」就够了", font=font(34, True), fill=INK)
    d.text((40, 64),
           "面板上的切换开关 → 地球自动飞到能装下所有热点的位置 → 点列表任一条可单独飞过去",
           font=font(17), fill=GRAY)

    # 标注位置全部【实测】：DOM 给的元素位置 + 像素扫描出的热点圆心。
    # 第一版是肉眼估的，结果标注 2 飘在空白处。
    vw, vh = rects["viewport"]
    k = 1400 / vw            # 缩放系数

    def to_canvas(pt):
        return (int(pt[0] * k), int(pt[1] * k * (SH / vh)) + TOP)

    marks = []
    ms = rects["modeSwitch"]
    if ms:
        marks.append(("1", (ms["x"] + ms["w"] + 26, ms["cy"])))
    hl = rects["hotspotList"]
    if hl:
        marks.append(("3", (hl["x"] + hl["w"] + 26, hl["cy"])))
    if CIRCLES:
        cx, cy = CIRCLES[0]
        marks.append(("2", (cx / vw * 1400 + 34, cy / vh * SH + TOP)))

    for label, pt in marks:
        x, y = to_canvas(pt)
        d.ellipse([x - 23, y - 23, x + 23, y + 23], fill=(0xFF, 0x3B, 0x30),
                  outline=(255, 255, 255), width=3)
        d.text((x, y), label, font=font(26, True), fill=(255, 255, 255), anchor="mm")

    # 图例：没有它，图上的 ①②③ 就是三个孤零零的红点
    ly = SH + TOP + 22
    d.ellipse([42, ly - 15, 72, ly + 15], fill=(0xFF, 0x3B, 0x30))
    d.text((57, ly), "1", font=font(19, True), fill=(255, 255, 255), anchor="mm")
    d.text((82, ly), "点「热点」档", font=font(18), fill=INK, anchor="lm")
    d.ellipse([232, ly - 15, 262, ly + 15], fill=(0xFF, 0x3B, 0x30))
    d.text((247, ly), "2", font=font(19, True), fill=(255, 255, 255), anchor="mm")
    d.text((272, ly), "地球上的热点（大小=次数，颜色=来过的轨迹条数）", font=font(18), fill=INK, anchor="lm")
    d.ellipse([760, ly - 15, 790, ly + 15], fill=(0xFF, 0x3B, 0x30))
    d.text((775, ly), "3", font=font(19, True), fill=(255, 255, 255), anchor="mm")
    d.text((800, ly), "面板逐条列出，点一条单独飞过去", font=font(18), fill=INK, anchor="lm")

    canvas.save(os.path.join(OUT, "fig-hot-2-howto.png"))
    print("  fig-hot-2-howto.png", canvas.size, "标注数", len(marks))


def find_hotspot_circles(path):
    """像素扫描找出热点圆的圆心（红/黄都算），用来把标注 2 放在真的圆上。"""
    img = Image.open(path).convert("RGB")
    px = img.load()
    w, h = img.size
    pts = []
    for y in range(80, h - 120):
        for x in range(460, w):
            r, g, b = px[x, y][:3]
            if r > 200 and g < 130 and 50 < b < 170:      # 热点红 #ff375f
                pts.append((x, y))
    if not pts:
        return []
    # 取最右边那一簇的中心（东边那个热点，不会被面板挡）
    pts.sort()
    group = [p for p in pts if p[0] > pts[-1][0] - 60]
    return [(sum(p[0] for p in group) / len(group),
             sum(p[1] for p in group) / len(group))]


GPX_TRACKS = []
HOTSPOTS = []
CIRCLES = []

if __name__ == "__main__":
    GPX_TRACKS, stays = fetch()
    # 按次数给三个热点上色（和前端一致：3 条轨迹=红，1 条=黄）
    HOTSPOTS = [
        (116.296853, 40.011572, 4, (0xFF, 0x37, 0x5F)),
        (116.321793, 40.008948, 3, (0xFF, 0x9F, 0x0A)),
        (116.296562, 40.006719, 2, (0xFF, 0xD6, 0x0A)),
    ]
    shot = os.path.abspath(os.path.join(OUT, "..", "..", "..", ".tmp", "hotspot-ui.png"))
    if os.path.exists(shot):
        CIRCLES = find_hotspot_circles(shot)
    print("生成图片：")
    fig_why()
    fig_howto()
    print("完成")
