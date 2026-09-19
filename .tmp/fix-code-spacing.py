# -*- coding: utf-8 -*-
r"""把【真实代码里】残留的「采样间距 3~15 米」更正为实测值。

这三处是 Task 1 / Task 3 的子代理照抄计划原文写进去的 —— 而计划那句话
已被实测推翻（真实间距 5~42 米）。代码注释里写着错的前提，比文档里写错更危险：
后来的人会照着注释去推理。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-code-spacing.py
"""
import io
import sys

PROPS = "backend/src/main/java/com/calcite/config/SimilarityProperties.java"
YML = "backend/src/main/resources/application.yml"
REPO = "backend/src/main/java/com/calcite/repository/TrackPointRepository.java"
PLAN = "docs/superpowers/plans/2026-09-17-m2-similarity.md"

EDITS = [
    (PROPS,
     "     * <p>为什么是 50：GeoLife 采样间隔 1~5 秒，城市骑行速度下相邻采样点只隔 3~15 米，\n"
     "     * <b>远密于 50 米</b>（这是\"用采样点代表折线\"这个近似能成立的前提）；\n"
     "     * 50 米又能容纳城市 GPS 漂移（常见 10~30 米），且远小于\"走错一条街\"的 100 米以上偏差。",
     "     * <p>为什么是 50：<b>实测采样间距是 5~42 米</b>（不是设计时以为的 3~15 米 —— 见设计文档 2.6 节）。\n"
     "     * 对密采样的轨迹（5~21 米）50 米是合适的；对稀疏轨迹（42 米）会低估单向百分比，\n"
     "     * 但<b>相似度取两个方向的最小值，不受影响</b>（被低估的方向恰好是本来更大的那个，见 2.7 节）。\n"
     "     * 50 米又能容纳城市 GPS 漂移（常见 10~30 米），且远小于\"走错一条街\"的 100 米以上偏差。"),

    (YML,
     "    # 默认容差（米）。GeoLife 采样间隔 3~15 米，城市 GPS 漂移 10~30 米",
     "    # 默认容差（米）。实测采样间距 5~42 米、城市 GPS 漂移 10~30 米（见设计文档 2.6 节）"),

    (REPO,
     "     * 代价是\"用采样点代表折线\"这个近似 —— GeoLife 采样间隔 3~15 米，\n"
     "     * 远密于 50 米容差，所以近似成立。这个代价写进了设计文档的已知限制。",
     "     * 代价是\"用采样点代表折线\"这个近似。实测采样间距是 5~42 米（见设计文档 2.6 节），\n"
     "     * 所以<b>对稀疏轨迹会严重低估单向百分比</b>（实测 100% 被算成 43%）。\n"
     "     * 但<b>相似度取两个方向的最小值，几乎不受影响</b> —— 被低估的方向恰好是本来更大的那个\n"
     "     * （六组实测与真值差 ≤ 0.6 个百分点，见 2.7 节）。这个取舍写进了设计文档的已知限制。"),

    (PLAN,
     " * <p>为什么是 50：GeoLife 采样间隔 1~5 秒，城市骑行速度下相邻采样点只隔 3~15 米，\n"
     " * <b>远密于 50 米</b>（这是\"用采样点代表折线\"这个近似能成立的前提）；",
     " * <p>为什么是 50：<b>实测采样间距是 5~42 米</b>（不是设计时以为的 3~15 米 —— 见设计文档 2.6 节）。"),
]


def apply(path, old, new):
    with io.open(path, encoding="utf-8") as fh:
        t = fh.read()
    n = t.count(old)
    if n != 1:
        print(f"  [XX] {path.split('/')[-1]} 期望命中 1 次，实得 {n}：{old[:56]}…")
        return False
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(t.replace(old, new))
    print(f"  [OK] {path.split('/')[-1]}  {old[:50]}…")
    return True


def main():
    ok = True
    for path, old, new in EDITS:
        ok = apply(path, old, new) and ok
    print()
    print("全部替换成功" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
