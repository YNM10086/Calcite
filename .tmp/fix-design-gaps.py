# -*- coding: utf-8 -*-
r"""设计文档自查发现的两处补充。

① 【边界漏洞】替换时如果新内容的 SHA256 已经属于另一条轨迹，会撞 external_id 唯一约束。
   场景：先导入「资料一」（hash A）→ 再拿同一个文件去"替换"「资料二」
        → 新的 external_id = A，但 A 已经是「资料一」的 → 约束冲突（500）
   正确行为：这等于"这份内容已经在库里了"，应该**再返回一次 409** 说清楚。

② 澄清：用户选"替换"时前端不需要重新选文件（File 对象还在内存里）。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-design-gaps.py
"""
import io
import sys

P = "docs/superpowers/specs/2026-09-21-data-management-design.md"

# ① 在 2.2 的流程后面补 external_id 冲突的说明
ANCHOR_1 = """**为什么用 409 + 让用户决定，而不是系统按名字自动替换**："""

NEW_1 = """**⚠️ 还有第二个冲突要处理（自查时发现的边界）**：

替换时，新文件的 `external_id`（= 内容 SHA256）**可能已经属于另一条轨迹**：

```
先导入「资料一」→ 它的 external_id = A
再拿【同一个文件】去"替换"「资料二」
  → 新的 external_id 也是 A，但 A 已经是「资料一」的
  → 撞唯一约束 → 500
```

**正确行为**：这不是错误，是「**这份内容已经在库里了**」——
应该**再返回一次 409**，说清楚"这个文件的内容已经是『资料一』了，你是想替换『资料二』还是算了？"。

**不要让它变成 500** —— 用户会以为系统坏了，而实际上是他自己传了一份已经在库里的文件。

**为什么用 409 + 让用户决定，而不是系统按名字自动替换**："""

# ② 在 2.3 里补一句前端不用重传文件
ANCHOR_2 = """替换是**原地更新**（geom、点数、时长、external_id、时间范围），**不删不插**。"""
NEW_2 = """替换是**原地更新**（geom、点数、时长、external_id、时间范围），**不删不插**。

> 界面上用户选"替换"时，**不需要重新选文件** —— 浏览器里 `File` 对象还在内存里，
> 直接用同一个对象再提交一次即可（不会真的重传一遍磁盘读取）。"""

EDITS = [(P, ANCHOR_1, NEW_1), (P, ANCHOR_2, NEW_2)]


def main():
    with io.open(P, encoding="utf-8") as fh:
        t = fh.read()
    ok = True
    for path, old, new in EDITS:
        n = t.count(old)
        if n != 1:
            print(f"  [XX] 期望命中 1 次，实得 {n}：{old[:56]!r}")
            ok = False
            continue
        t = t.replace(old, new)
        print(f"  [OK] {old[:52]}…")
    if ok:
        with io.open(P, "w", encoding="utf-8", newline="") as fh:
            fh.write(t)
    print()
    print("补充完成" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
