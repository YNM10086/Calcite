# -*- coding: utf-8 -*-
r"""把真实网格数据用【三种色阶】各画一遍，并排对比。

为什么必须对比：数据极度偏斜（轨迹数中位数 2、最大 152，差 76 倍）。
线性色阶下除了一两个最热的格子，其余全是浅色 —— 整张图等于空白。

输入的 .tmp/density-grid.json 由 psql 导出（北京范围 0.002° 网格，1294 个非空格子）。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\render-density-scales.py
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "docs", "learning", "figs"))
from make_figs import Fig, INK, GRAY, RED, GREEN, ORANGE, BLUE  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

SRC = ".tmp/density-grid.json"
OUT = os.path.join("docs", "learning", "figs", "fig-density-scales.png")

# 北京裁剪范围（纬度 40° 处：1° 经度 ≈ 85.3 km，1° 纬度 ≈ 110.6 km）
LON0, LON1 = 116.27, 116.41
LAT0, LAT1 = 39.96, 40.03
CELL = 0.002

METRIC = "trks"        # 先用「轨迹条数」——它是场景 3 的主口径
LABEL = "轨迹条数"


def ramp(t):
    """t ∈ [0,1] → 颜色。浅米黄 → 深红。"""
    t = max(0.0, min(1.0, t))
    stops = [(0.00, (0xFF, 0xF7, 0xE8)), (0.25, (0xFF, 0xD6, 0x8A)),
             (0.50, (0xFF, 0x9F, 0x0A)), (0.75, (0xE8, 0x50, 0x1E)),
             (1.00, (0x9E, 0x00, 0x1B))]
    for i in range(len(stops) - 1):
        a, ca = stops[i]
        b, cb = stops[i + 1]
        if t <= b:
            k = (t - a) / (b - a)
            return tuple(int(ca[j] + (cb[j] - ca[j]) * k) for j in range(3))
    return stops[-1][1]


def main():
    with open(SRC, encoding="utf-8") as fh:
        cells = json.load(fh)
    vals = [c[METRIC] for c in cells]
    vmax, vmin = max(vals), min(vals)
    srt = sorted(vals)

    def quantile(p):
        return srt[min(len(srt) - 1, int(p * len(srt)))]

    # 三张图的归一化函数
    def lin(v):
        return v / vmax

    def log(v):
        return math.log1p(v) / math.log1p(vmax)

    buckets = [quantile(q) for q in (0.2, 0.4, 0.6, 0.8, 0.95)]

    def quant(v):
        for i, b in enumerate(buckets):
            if v <= b:
                return (i + 1) / (len(buckets) + 1)
        return 1.0

    variants = [
        ("A · 线性色阶", lin,
         f"深浅 ∝ 数值 / 最大值（{vmax}）",
         "只有最热的极少数格子有颜色，其余几乎全白 —— 看不出结构"),
        ("B · 对数色阶（推荐）", log,
         f"深浅 ∝ log(数值) / log(最大值)",
         "中低值也被拉开，整条路网都看得见；高值仍然最深"),
        ("C · 分位分档", quant,
         f"按分位切成 5 档：{buckets}",
         "各档格子数量固定，对比最均衡；但档位随数据变，跨查询不可比"),
    ]

    # 画布尺寸：按真实米数等比（纬度 40° 处经度要乘 cos）
    m_per_deg_lon = 111320 * math.cos(math.radians(40))
    m_per_deg_lat = 110574
    w_m = (LON1 - LON0) * m_per_deg_lon
    h_m = (LAT1 - LAT0) * m_per_deg_lat
    PW = 330
    PH = int(PW * h_m / w_m)
    GAP = 46
    TOP = 150
    total_w = 60 + 3 * PW + 2 * GAP + 60
    total_h = TOP + PH + 190

    im = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    from make_figs import f as font

    d.text((60, 36), "图 · 三种色阶画同一份真实数据（北京 0.002° 网格，1294 个非空格子）",
           font=font(30, True), fill=INK)
    d.text((60, 78),
           f"指标 = {LABEL}：中位数 {quantile(0.5)}，最大 {vmax} —— 相差 {vmax / max(1, quantile(0.5)):.0f} 倍",
           font=font(18), fill=GRAY)
    d.text((60, 108), "格子越小越冷、越红越热。三张图用的是同一份数据，只有色阶不同。",
           font=font(17), fill=GRAY)

    for i, (title, fn, formula, note) in enumerate(variants):
        ox = 60 + i * (PW + GAP)
        oy = TOP
        d.rectangle([ox, oy, ox + PW, oy + PH], fill=(0xF4, 0xF6, 0xF8),
                    outline=(0xCE, 0xD5, 0xDD))
        for c in cells:
            lon, lat = c["x"], c["y"]
            if not (LON0 <= lon <= LON1 and LAT0 <= lat <= LAT1):
                continue
            # 格子中心 → 像素
            px0 = ox + (lon - CELL / 2 - LON0) / (LON1 - LON0) * PW
            px1 = ox + (lon + CELL / 2 - LON0) / (LON1 - LON0) * PW
            py0 = oy + PH - (lat + CELL / 2 - LAT0) / (LAT1 - LAT0) * PH
            py1 = oy + PH - (lat - CELL / 2 - LAT0) / (LAT1 - LAT0) * PH
            d.rectangle([px0, py0, max(px1, px0 + 1), max(py1, py0 + 1)],
                        fill=ramp(fn(c[METRIC])))
        d.text((ox, oy - 34), title, font=font(20, True), fill=INK)
        d.text((ox, oy + PH + 14), formula, font=font(15), fill=GRAY)
        # 说明折行
        line, y = "", oy + PH + 40
        for ch in note:
            if d.textlength(line + ch, font=font(15)) > PW:
                d.text((ox, y), line, font=font(15), fill=(0x4E, 0x59, 0x69))
                y += 22
                line = ""
            line += ch
        d.text((ox, y), line, font=font(15), fill=(0x4E, 0x59, 0x69))

    im.save(OUT)
    print("已生成", OUT, im.size)
    print(f"  轨迹数分位：p20={quantile(0.2)} p40={quantile(0.4)} "
          f"p60={quantile(0.6)} p80={quantile(0.8)} p95={quantile(0.95)} max={vmax}")
    # 统计三种色阶下"值最小的那一半格子"的平均深浅，用来量化差别
    half = [c[METRIC] for c in cells if c[METRIC] <= quantile(0.5)]
    print(f"  下半数格子的平均归一化深浅："
          f"线性 {sum(lin(v) for v in half)/len(half):.3f} / "
          f"对数 {sum(log(v) for v in half)/len(half):.3f} / "
          f"分位 {sum(quant(v) for v in half)/len(half):.3f}")


main()
