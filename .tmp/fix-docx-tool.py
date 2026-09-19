# -*- coding: utf-8 -*-
r"""把 Word 生成工具的指引从 officecli 改回 python-docx。

背景：会话记忆 2026-09-08 就定稿了「Word 一律走 python-docx」，
因为 officecli 在本机写不进 docx（add/save 报成功但文件是空的）。
而我给 Task 11 写的指引是「用 officecli 技能」，之前写进会话记忆的那条也是错的。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-docx-tool.py
"""
import io
import sys

BT = chr(96)          # 反引号 —— 不直接写在源码里，免得被 shell 的 here-string 吃掉

SESSION = "_session_context.md"
PLAN = "docs/superpowers/plans/2026-09-17-m2-similarity.md"

OLD_SESSION = f"生成工具：{BT}officecli{BT} 技能（做 .docx）"
NEW_SESSION = (
    "生成工具：**" + BT + "python-docx" + BT + "** —— 先写 .md，再在**仓库根目录**跑\n"
    "  `python scripts/tools/md2docx.py <md> <docx>`（图路径是相对的，必须在根目录跑）。\n"
    "  ⚠️ **不要用 officecli 写 docx** —— 它在本机写不进（add/save 报成功但文件是空的，\n"
    "  validate 对空文档还假报通过）。这条决策 2026-09-08 就定稿了（见本文件前面的「文档工具决策」）。"
)

OLD_PLAN_1 = (
    f"- [ ] **Step 1: 加载 {BT}officecli{BT} 技能**\n\n"
    f"用 {BT}skill{BT} 工具加载 {BT}officecli{BT}，按它的指引做 {BT}.docx{BT}。"
)
NEW_PLAN_1 = f"""- [ ] **Step 1: 用 {BT}python-docx{BT}，不要用 officecli**

⚠️ **这是本任务最容易踩的坑**：项目在 **2026-09-08 就定稿**了文档工具决策 ——
**Word 一律走 {BT}python-docx{BT}**（{BT}scripts/tools/md2docx.py{BT}，已支持表格/图片/字体）。
{BT}officecli{BT} 在本机**写不进 docx**（{BT}add{BT}/{BT}save{BT} 报成功但文件是空的，
{BT}validate{BT} 对空文档还假报通过）——**不要用它写 docx**。

正确流程（和前三份学习笔记完全一致）：
1. **先写一份 {BT}.md{BT}**（markdown，表格照常用）
2. 在**仓库根目录**跑：{BT}python scripts/tools/md2docx.py <md路径> <docx路径>{BT}
   （**必须在根目录** —— 图路径是相对的）
3. 用 {BT}officecli raw{BT} **只做验证**（验真），或直接检查文件大小 / 能否打开

输出位置参考已有的三份笔记：和 {BT}D:\\\\Calcite-note\\\\Calcite-M2停留热点笔记.docx{BT} 同目录。"""

OLD_PLAN_2 = (
    f"用 {BT}officecli{BT} 生成 {BT}.docx{BT}，然后：\n"
    f"- **用 officecli 读回来检查**（标题层级、表格、图片是否正常）"
)
NEW_PLAN_2 = (
    f"用 {BT}md2docx.py{BT} 生成 {BT}.docx{BT}（见 Step 1），然后：\n"
    "- **检查生成结果**：文件大小合理（不是空文件）、能用 python-docx 读回来、"
    "标题层级与表格正常"
)

EDITS = [
    (SESSION, OLD_SESSION, NEW_SESSION),
    (PLAN, OLD_PLAN_1, NEW_PLAN_1),
    (PLAN, OLD_PLAN_2, NEW_PLAN_2),
]


def main():
    ok = True
    for path, old, new in EDITS:
        with io.open(path, encoding="utf-8") as fh:
            t = fh.read()
        n = t.count(old)
        if n != 1:
            print(f"  [XX] {path} 期望命中 1 次，实得 {n}：{old[:60]!r}")
            ok = False
            continue
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(t.replace(old, new))
        print(f"  [OK] {path}  {old[:52]}")
    print()
    print("全部替换成功" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
