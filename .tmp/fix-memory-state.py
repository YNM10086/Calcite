# -*- coding: utf-8 -*-
r"""修正会话记忆里已经过时的状态（数据管理其实已经合并 + 推送了）。

背景：Task 9 的文档子代理写这段时，数据管理还没合并；之后主控合并了（3a3cbe2）
并推送了两次（3a3cbe2、44369c0），但这段记忆没跟着更新。
不修的话，下个会话会以为还要"合并 + 推送"，重复劳动。

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-memory-state.py
"""
import io
import sys

P = "_session_context.md"

EDITS = [
    ("  - ✅ **「数据管理」也已完成**（2026-09-21，分支 `feat/data-management`，**尚未合并、尚未推送**）——\n"
     "    添加 / 替换 / 改名 / **删除** 全通，并兑现了 M2 留下的两处缓存欠账（详见上一节）\n"
     "  - **下一步 = 合并 + 推送**：把 `feat/data-management` 合并回 `main` 再推\n"
     "    （按约定\"攒到一块做完再推\"；⚠️ 沙箱内 git 的 SSH 操作必崩，推送要提权 `danger-full-access`）\n"
     "  - **推送之后 = M3**：",

     "  - ✅ **「数据管理」已完成并已推送**（2026-09-21）——\n"
     "    添加 / 替换 / 改名 / **删除** 全通，并兑现了 M2 留下的两处缓存欠账（详见上一节）。\n"
     "    分支 `feat/data-management` 已**快进合并回 main 并删除**；\n"
     "    `3a3cbe2`（功能）+ `44369c0`（Word 报告）两次推送，**本地 = origin/main**。\n"
     "  - **下一步 = M3**："),
]

# 交付物那条：Word 报告已经交了
OLD_DELIV = "  - 📌 **用户点名要的交付物（现在到期）**："
NEW_DELIV = ("  - ✅ **用户点名的 Word 交付物已交**（2026-09-21）——\n"
             "    `D:\\Calcite-note\\2026-09-21-数据管理改动报告.docx`（40 KB / 61 段落 / 5 表格）；\n"
             "    仓库里也有一份：`docs/learning/2026-09-21-数据管理改动报告.{md,docx}`。\n"
             "    更早那份 `2026-09-17-M2-全景笔记.docx`（四阶段全景）也在同一目录。\n"
             "\n"
             "  - 📌 **（历史记录，已完成）以下是当初点名的交付物**：")


def main():
    with io.open(P, encoding="utf-8") as fh:
        t = fh.read()
    ok = True
    for old, new in EDITS + [(OLD_DELIV, NEW_DELIV)]:
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
    print("修正完成" if ok else "有替换失败")
    if not ok:
        sys.exit(1)


main()
