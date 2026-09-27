# -*- coding: utf-8 -*-
"""文档链接自检：README / DEPLOY / 技术要点自检 里的相对链接与图片是否都存在。

为什么需要它：文档最常见的腐烂方式不是写错内容，而是**链接和图片路径失效**
（文件改名、目录搬家、图没提交）。M4 之后 `scripts/acceptance/` 刚搬过家、
`docs/images/arch-overview.png` 是新图，正是最容易出这种问题的时候。

另外顺手扫一遍**过时表述**（README 曾长期停在 M1 时代：写着"M2 进行中""41 项测试""GeoLife 尚未导入"）。

跑法（从仓库根目录）：
    & "E:\\python\\python_address\\python.exe" scripts\\acceptance\\check-doc-links.py
退出码：0 = 全绿；1 = 有失效项或过时表述。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = [
    "README.md",
    "docs/DEPLOY.md",
    "docs/learning/技术要点自检.md",
]
# 过时表述：出现即视为需要人工确认（左为要搜的字符串，右为为什么）
STALE = [
    ("M2 进行中", "M2 早已完成"),
    ("M3 计划中", "M3 早已完成"),
    ("尚未导入", "GeoLIFE 已导入（246 条）"),
    ("41 项", "后端测试基线早已是 162 项"),
    ("134 项", "前端 node 基线早已是 157 项"),
]

LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def check_links(rel_path):
    path = os.path.join(ROOT, rel_path)
    if not os.path.exists(path):
        return [f"{rel_path}: 文件不存在"]
    text = open(path, encoding="utf-8").read()
    bad = []
    total = 0
    for raw in LINK.findall(text):
        target = raw.split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        total += 1
        # 文档里的路径统一按【仓库根目录】为基准（md2docx 也是这么解析的）
        if not os.path.exists(os.path.join(ROOT, target.replace("/", os.sep))):
            bad.append(f"{rel_path}: 链接失效 -> {target}")
    return bad, total


def check_stale(rel_path):
    path = os.path.join(ROOT, rel_path)
    if not os.path.exists(path):
        return []
    text = open(path, encoding="utf-8").read()
    out = []
    for needle, why in STALE:
        if needle in text:
            for i, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    out.append(f"{rel_path}:{i}: 出现过时表述「{needle}」（{why}）-> {line.strip()[:80]}")
    return out


def main():
    problems = []
    for rel in DOCS:
        res = check_links(rel)
        if isinstance(res, list) and res and res[0].endswith("文件不存在"):
            problems += res
            continue
        bad, total = res
        print(f"[链接] {rel}: 检查 {total} 个相对链接/图片，失效 {len(bad)} 个")
        problems += bad
        problems += check_stale(rel)

    print()
    if problems:
        print("发现问题：")
        for p in problems:
            print("  ✗ " + p)
        print(f"\n结果：{len(problems)} 个问题")
        return 1
    print("结果：全部通过（链接与图片都存在，无过时表述）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
