# -*- coding: utf-8 -*-
r"""修两处遗留的过时数字（Task 11 的子代理发现的）。

① `DensityResponse.java` 的类注释还写着「736 个格子 / 68921 个点」——
   那是**另一组查询条件**（窄 bbox + 按来源过滤）测出来的，接口实际是 1335 / 227945。

② density 设计文档附录 A 写着「快 3.5 倍」—— 用 psql 自带计时重测是**约 2 倍**
   （93ms vs 188ms）。3.5 倍那个数被 psql 进程启动开销污染了。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-stale-numbers.py
"""
import io
import sys

DTO = "backend/src/main/java/com/calcite/web/dto/DensityResponse.java"
DESIGN = "docs/superpowers/specs/2026-09-17-m2-density-design.md"

EDITS = [
    (DTO,
     ' * <p>{@code scanned} 让前端能显示"736 个格子 / 68921 个点"，',
     ' * <p>{@code scanned} 让前端能显示"1335 个格子 / 227945 个点"（参照视野的实测值），'),

    (DESIGN,
     "| 第 128 行「热点区域分析：按固定边长网格统计轨迹点密度（`ST_SnapToGrid`）」 | "
     "**落地**。但实现上用 `round(ST_X/cell)` 等价替代（快 3.5 倍），用测试钉住等价性 |",
     "| 第 128 行「热点区域分析：按固定边长网格统计轨迹点密度（`ST_SnapToGrid`）」 | "
     "**落地**。但实现上用 `round(ST_X/cell)` 替代（快约 **2 倍**：93ms vs 188ms，psql 自带计时），"
     "**并用四条断言钉住「除格子边界点外等价」**（不是笼统的「完全相同」） |"),
]


def main():
    ok = True
    for path, old, new in EDITS:
        with io.open(path, encoding="utf-8") as fh:
            t = fh.read()
        n = t.count(old)
        if n != 1:
            print(f"  [XX] {path} 期望命中 1 次，实得 {n}：{old[:60]}…")
            ok = False
            continue
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(t.replace(old, new))
        print(f"  [OK] {path.split('/')[-1]}  {old[:50]}…")
    print()
    print("全部替换成功" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
