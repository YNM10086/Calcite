# -*- coding: utf-8 -*-
r"""把「round 与 ST_SnapToGrid 语义完全相同」这句过强的话改成准确描述。

背景：Task 4 的 Python 对拍升级成「双向差集对比」后（之前只比 count，是个很弱的检查），
发现两种写法**并非严格等价** —— 差异 100% 出现在「恰好落在格子边界上」的点：

    x = 116.4095, cell = 0.001
      round 路线：116.4095 / 0.001 = 116409.49999999999（double 精度）→ 116.409
      snap  路线：x*1000 = 116409.5 精确 → 按「取偶」规则 → 116.410

影响面（实测）：
  0.002 档：格子集合严格相同（3916 = 3916、1335 = 1335），但有 14 个格子的点数因此差 1
  0.001 档：snap 比 round 多 1 个格子；0.0005 档多 2 个

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-equivalence-claim.py
"""
import io
import sys

REPO = "backend/src/main/java/com/calcite/repository/TrackPointRepository.java"
PLAN = "docs/superpowers/plans/2026-09-17-m2-density.md"
DESIGN = "docs/superpowers/specs/2026-09-17-m2-density-design.md"

ACCURATE = """两种写法在<b>非边界点</b>上完全等价 —— 实测「所有归属不同的点都恰好落在格子边界上」
 * （8 组断言全部满足 diff_points == tie_points），且 round 的格子集合是 ST_SnapToGrid 的子集。
 * <b>边界点的归属不同</b>：round 走 ST_X/cell 的浮点除法
 * （116.4095/0.001 = 116409.49999999999），ST_SnapToGrid 走乘法后按「取偶」规则，
 * 于是在恰好半格的点上会分到相邻格子。
 * 影响面：默认档 0.002 上两种写法<b>严格相同</b>（3916 = 3916、1335 = 1335，集合逐个相同），
 * 只有 14 个格子的点数因此差 1（视觉不可见）；0.001 / 0.0005 档还会多出 1~2 个格子。
 * 由 .tmp/verify-density-api.py 的四条断言钉住。"""

EDITS = [
    # ---- TrackPointRepository 的 javadoc（后两行一起换掉）----
    (REPO,
     """ * 两者<b>语义完全相同</b>（都是"把坐标就近取整到 cell 的整数倍"），
     * 实测格子集合逐个相同（全量 3867 = 3867、北京 736 = 736），
     * 但整数写法快 <b>3.5 倍</b>（92ms vs 330ms），而且不需要排序、不会落盘临时文件。
     * 这个等价关系由 {@code .tmp/verify-density-api.py} 断言钉住。""",
     """ * """ + ACCURATE + """
     *
     * <p>整数写法比 ST_SnapToGrid 快约 <b>2 倍</b>（psql 自带计时：93ms vs 188ms），
     * 而且不需要排序、不会落盘临时文件。"""),

    # ---- 计划里的同一段 javadoc ----
    (PLAN,
     """ * 两者<b>语义完全相同</b>（都是"把坐标就近取整到 cell 的整数倍"），
     * 实测格子集合逐个相同（全量 3916 = 3916、北京 1335 = 1335），
     * 但整数写法快 <b>3.5 倍</b>（92ms vs 330ms），而且不需要排序、不会落盘临时文件。
     * 这个等价关系由 {@code .tmp/verify-density-api.py} 断言钉住。""",
     """ * """ + ACCURATE.replace("<b>", "**").replace("</b>", "**")),

    # ---- 计划头部 Architecture 那句 ----
    (PLAN,
     "**Architecture:** 计算下推到数据库（`round(ST_X/cell)` + 哈希聚合，语义等同 `ST_SnapToGrid` 但快 3.5 倍）",
     "**Architecture:** 计算下推到数据库（`round(ST_X/cell)` + 哈希聚合，比 `ST_SnapToGrid` 快约 2 倍；"
     "两者除格子边界点外等价，默认档 0.002 上严格相同）"),

    # ---- 计划 Task 4 里对等价性的描述 ----
    (PLAN,
     "> ① **等价性验证**（`round(ST_X/cell)` 与 `ST_SnapToGrid` 的格子集合必须逐个相同）；",
     "> ① **等价性验证** —— 注意**不能**断言\"格子集合逐个相同\"（那是错的，见下）；\n"
     "> 要断言的是四条**可证明**的性质：所有归属不同的点都恰好落在格子边界上、\n"
     "> `round` 的格子是 `ST_SnapToGrid` 的子集、差集 ≤ 2、**默认档 0.002 上严格相同**；"),

    # ---- 设计文档 §4.2 ----
    (DESIGN,
     "**它们语义完全相同，但快约 2 倍**（实测，psql 自带计时，不含进程启动开销）：",
     "**它们除「格子边界点」外等价，且快约 2 倍**（实测，psql 自带计时，不含进程启动开销）："),

    (DESIGN,
     "> **两种写法的格子集合逐个相同**（全量 3916 = 3916、北京 1335 = 1335）——",
     "> ⚠️ **更正**：早先这里写的是「格子集合逐个相同」，但那个结论来自只比 `count(*)` 的**弱检查**\n"
     "> （两个不同的集合只要元素个数相同就能骗过它）。升级成**双向 `EXCEPT` 差集**对比后发现：\n"
     "> **两种写法并非严格等价**，差异 100% 出现在**恰好落在格子边界上**的点\n"
     "> （`116.4095/0.001` 在 double 下是 `116409.49999999999`，而 `x*1000` 是精确的 `116409.5`，\n"
     "> 于是 `round` 与 `ST_SnapToGrid` 的「取偶」规则会把同一个点分到相邻格子）。\n"
     ">\n"
     "> **影响面**：默认档 0.002 上两种写法的**格子集合严格相同**（全量 3916 = 3916、参照 bbox 1335 = 1335），\n"
     "> 但有 14 个格子的**点数**因此差 1（视觉不可见）；0.001 / 0.0005 档还会多出 1~2 个格子。\n"
     "> **默认档 0.002 上仍然完全相同** ——"),
]

# 后面这段是原来那段话的延续，单独处理（避免上面的替换把上下文打断）
TAIL_OLD = """就是"把每个坐标就近取整到 s 的整数倍"。
>
> **这个等价关系会写成自动化测试**（第 7 节），钉住"我们用整数运算替代了 PostGIS 函数"这件事。"""
TAIL_NEW = """是"把每个坐标就近取整到 s 的整数倍"，差别只在**恰好半格时往哪边取**。
>
> **写成自动化测试的四条断言**（第 7 节）钉住了真正可证明的部分：
> 归属不同的点全是边界点、`round ⊆ snap`、差集 ≤ 2、默认档严格相同。"""


def apply(path, old, new):
    with io.open(path, encoding="utf-8") as fh:
        t = fh.read()
    n = t.count(old)
    if n != 1:
        print(f"  [XX] {path.split('/')[-1]} 期望命中 1 次，实得 {n}：{old[:50]}…")
        return False
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(t.replace(old, new))
    print(f"  [OK] {path.split('/')[-1]}  {old[:46]}…")
    return True


def main():
    ok = True
    for path, old, new in EDITS:
        ok = apply(path, old, new) and ok
    ok = apply(DESIGN, TAIL_OLD, TAIL_NEW) and ok
    # 设计文档 §9.3 与 §9.5 的措辞
    ok = apply(DESIGN, "见 4.2：语义逐个相同，但快 3.5 倍、不落盘。**并用自动化测试钉住这个等价关系。**",
               "见 4.2：**除格子边界点外等价**（默认档严格相同），但快约 2 倍、不落盘。\n"
               "**并用四条可证明的断言钉住这个关系** —— 而不是笼统地说\"完全相同\"。") and ok
    print()
    print("全部替换成功" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
