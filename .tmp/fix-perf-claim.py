# -*- coding: utf-8 -*-
r"""修设计文档 2.5 节里一处【跨口径】的性能对比。

问题：2.5 节写「点到整条折线 119 秒 vs 点对点 0.79 秒 = 60 倍」，
但这两个数**不是一个口径**：
  - 119 秒 = 244 点 × 208 条轨迹的【点到折线】，
    而且那个测量里每条候选都算了一次 ST_SimplifyPreserveTopology（污染了结果）
  - 0.79 秒 = 点对点，而且只是【单向】

同一套口径下的正确对比（都是"全部 241 条候选、单向"）：
  - 点到折线：单对 61.5 ms × 208 ≈ 12.8 秒
  - 点对点：0.79 秒
  → 约 16 倍

（另有 11 倍那处说的是"点对点换个写法"：让主线的点驱动 vs 让候选驱动，8.5s vs 0.75s，
  那是另一组对比，不改。）

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-perf-claim.py
"""
import io
import sys

P = "docs/superpowers/specs/2026-09-17-m2-similarity-design.md"

EDITS = [
    ("### 2.5 ⭐ 性能：写法决定 60 倍差距",
     "### 2.5 ⭐ 性能：写法决定十几倍差距"),

    ("""| 写法 | 耗时 |
|---|---|
| 点到整条折线 | **119 秒** ❌ |
| ⭐ **点对点 + 空间索引** | **0.79 秒** |""",
     """| 写法 | 耗时（全部 241 条候选、单向） |
|---|---|
| 点到整条折线 | **约 12.8 秒** ❌（单对实测 61.5 ms × 208 条） |
| ⭐ **点对点 + 空间索引** | **0.79 秒** |"""),

    ("""**60 倍差距，原因只有一句话**：`track_point` 上有一个 `gist(geom, recorded_at)` 索引，""",
     """**约 16 倍差距，原因只有一句话**：`track_point` 上有一个 `gist(geom, recorded_at)` 索引，"""),
]

# 补一段"为什么这里不用 119 秒那个数"的说明
NOTE_ANCHOR = "而不是手动遍历折线。\n"
NOTE = """
> ⚠️ **口径说明（这处踩过一次）**：早先这里写的是「点到折线 **119 秒** vs 0.79 秒 = 60 倍」，
> 但**那两个数不是一个口径** ——
> 119 秒算的是「244 个点 × 208 条轨迹」的点到折线，**而且那个测量里每条候选都额外算了一次
> `ST_SimplifyPreserveTopology`（1000 点级别的折线 × 208 次），把结果污染了**；
> 而 0.79 秒只是**单向**的点对点。
> 同一套口径（全部候选、单向）下，单对点到折线实测只要 **61.5 毫秒**，× 208 条 ≈ **12.8 秒**。
> **教训和 4.4 节那条一样：数字必须和它的测量口径一起看。**
"""


def main():
    with io.open(P, encoding="utf-8") as fh:
        t = fh.read()
    ok = True
    for old, new in EDITS:
        n = t.count(old)
        if n != 1:
            print(f"  [XX] 期望命中 1 次，实得 {n}：{old[:60]!r}")
            ok = False
            continue
        t = t.replace(old, new)
        print(f"  [OK] {old[:52]}")
    if t.count(NOTE_ANCHOR) == 1:
        t = t.replace(NOTE_ANCHOR, NOTE_ANCHOR + NOTE, 1)
        print("  [OK] 补上口径说明")
    else:
        print(f"  [--] 口径说明的锚点命中 {t.count(NOTE_ANCHOR)} 次，跳过")
    if ok:
        with io.open(P, "w", encoding="utf-8", newline="") as fh:
            fh.write(t)
    print()
    print("全部替换成功" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
