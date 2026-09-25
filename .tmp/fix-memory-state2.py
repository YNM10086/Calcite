# -*- coding: utf-8 -*-
r"""按【关键词整行替换】修正会话记忆里过时的状态（比精确匹配整段稳）。

要改的两处：
  ① 「数据管理」那条写着"尚未合并、尚未推送"，实际已合并（3a3cbe2）并推送（44369c0）
  ② 「用户点名要的交付物（现在到期）」—— Word 报告已经交了

用法：
    $env:PYTHONIOENCODING='utf-8'
    & "E:\python\python_address\python.exe" .tmp\fix-memory-state2.py
"""
import io
import sys

P = "_session_context.md"

with io.open(P, encoding="utf-8") as fh:
    lines = fh.read().splitlines(keepends=True)

out = []
done = {"data": False, "next": False, "deliv": False}

for ln in lines:
    stripped = ln.strip()

    # ① 「数据管理」那条：把"尚未合并、尚未推送"改成已完成
    if (not done["data"]) and "「数据管理」也已完成" in ln:
        indent = ln[:len(ln) - len(ln.lstrip())]
        out.append(indent + "- ✅ **「数据管理」已完成、已合并、已推送**（2026-09-21）——\n")
        out.append(indent + "  添加 / 替换 / 改名 / **删除** 全通，并兑现了 M2 留下的两处缓存欠账（详见上一节）。\n")
        out.append(indent + "  分支 `feat/data-management` 已快进合并回 main 并删除；\n")
        out.append(indent + "  `3a3cbe2`（功能）+ `44369c0`（Word 报告）两次推送，**本地 = origin/main**。\n")
        done["data"] = True
        continue

    # ② 「下一步 = 合并 + 推送」这条已经没有意义了 —— 整条删掉
    if "下一步 = 合并 + 推送" in ln:
        done["next"] = True
        continue

    # ③ 「推送之后 = M3」改成「下一步 = M3」
    if "推送之后 = M3" in ln:
        out.append(ln.replace("**推送之后 = M3**", "**下一步 = M3**"))
        done["next"] = True
        continue

    # ④ 交付物那条
    if (not done["deliv"]) and "用户点名要的交付物（现在到期）" in ln:
        indent = ln[:len(ln) - len(ln.lstrip())]
        out.append(indent + "- ✅ **用户点名的 Word 交付物已交**（2026-09-21）——\n")
        out.append(indent + "  `D:\\Calcite-note\\2026-09-21-数据管理改动报告.docx`（40 KB / 61 段落 / 5 表格），\n")
        out.append(indent + "  仓库里也有：`docs/learning/2026-09-21-数据管理改动报告.{md,docx}`；\n")
        out.append(indent + "  更早那份四阶段全景 `2026-09-17-M2-全景笔记.docx` 也在同一目录。\n")
        out.append(indent + "\n")
        out.append(indent + "- 📌 **（以下为历史记录，已完成）** 当初点名的交付物：\n")
        done["deliv"] = True
        continue

    out.append(ln)

with io.open(P, "w", encoding="utf-8", newline="") as fh:
    fh.write("".join(out))

print("  命中情况：", done)
if not all(done.values()):
    print("  [XX] 有没命中的，请看上面")
    sys.exit(1)
print("  修正完成")
