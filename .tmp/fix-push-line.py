# -*- coding: utf-8 -*-
r"""修会话记忆里被 PowerShell 转义吃掉字符的那一行。

问题：在 PowerShell 的双引号 here-string 里，反引号是转义符，
`e62b1c8...` 里的 `e 被当成了 ESC，结果写成 `62b1c8`。
这个脚本直接改文件，不经过 shell 转义。
"""
import io
import re

P = "_session_context.md"
BT = chr(96)

with io.open(P, encoding="utf-8") as fh:
    t = fh.read()

# 把损坏的那一行整行替换掉
bad_pat = re.compile(r"^.*62b1c8\.\.7e6fe23\s+main -> main.*$", re.M)
m = bad_pat.search(t)
if not m:
    print("  [--] 没找到损坏的行，可能已经是对的")
else:
    indent = "  " if m.group(0).startswith("  ") else ""
    good = (indent + "- ✅ **已推送到 GitHub（2026-09-17）** —— "
            + BT + "e62b1c8..7e6fe23  main -> main" + BT + "，")
    t = t[:m.start()] + good + t[m.end():]
    print("  [OK] 修好了损坏的行")

with io.open(P, "w", encoding="utf-8", newline="") as fh:
    fh.write(t)

# 复查
for i, ln in enumerate(t.splitlines(), 1):
    if "已推送到 GitHub" in ln or "M2 至此正式交付" in ln:
        print(f"  行{i}: {ln.strip()}")
