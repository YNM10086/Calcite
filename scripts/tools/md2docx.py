#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Markdown 转成排版好的 Word 文档。

支持子集：
  标题        # .. ######
  段落        普通行
  无序列表    - / * / +（两空格缩进一级）
  有序列表    1. / 2.
  代码块      ```lang ... ```
  表格        GFM 管道表格
  引用        > 开头
  分隔线      --- / ***
  行内        **粗体**  *斜体*  `代码`

用法：
  python md2docx.py 输入.md 输出.docx
"""

import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

ASCII_FONT = "Calibri"
EA_FONT = "微软雅黑"          # 中文字体
MONO_ASCII = "Consolas"
MONO_EA = "微软雅黑"
CODE_BG = "F2F3F5"            # 代码块底色
QUOTE_BG = "FFF8E1"           # 引用底色
HEADER_BG = "E8EEF7"          # 表头底色


# --------------------------------------------------------------------------
# 底层工具
# --------------------------------------------------------------------------
def set_style_font(style, ascii_name, ea_name, size=None, bold=None, color=None):
    """给一个样式设置字体，中英文分别指定（中文必须设 w:eastAsia，否则会回退成宋体）。"""
    style.font.name = ascii_name
    if size is not None:
        style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color is not None:
        style.font.color.rgb = color

    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), ascii_name)
    rfonts.set(qn("w:hAnsi"), ascii_name)
    rfonts.set(qn("w:eastAsia"), ea_name)


def set_run_font(run, ascii_name=None, ea_name=None, size=None, bold=None,
                 italic=None, color=None):
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color
    if ascii_name or ea_name:
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        if ascii_name:
            rfonts.set(qn("w:ascii"), ascii_name)
            rfonts.set(qn("w:hAnsi"), ascii_name)
        if ea_name:
            rfonts.set(qn("w:eastAsia"), ea_name)


def shade(element, fill):
    """给段落或单元格加底色。"""
    pr = element._element.get_or_add_pPr() if hasattr(element, "paragraph_format") \
        else element._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def bottom_border(paragraph):
    """给段落加下边框，用作分隔线。"""
    ppr = paragraph._element.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "CCCCCC")
    borders.append(bottom)
    ppr.append(borders)


INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+\*)")


def add_inline(paragraph, text, base_size=None):
    """解析 **粗体** / *斜体* / `代码`，写入段落。"""
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            run = paragraph.add_run(part[2:-2])
            set_run_font(run, bold=True, size=base_size)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, MONO_ASCII, MONO_EA, size=(base_size or 10.5) - 1.5,
                         color=RGBColor(0xC0, 0x39, 0x2B))
            shade_run(run, CODE_BG)
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            run = paragraph.add_run(part[1:-1])
            set_run_font(run, italic=True, size=base_size)
        else:
            run = paragraph.add_run(part)
            set_run_font(run, size=base_size)


def shade_run(run, fill):
    """给一小段文字（run）加底色。"""
    rpr = run._element.get_or_add_rPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    rpr.append(shd)


# --------------------------------------------------------------------------
# 文档初始化
# --------------------------------------------------------------------------
def build_document():
    doc = Document()

    # 正文
    set_style_font(doc.styles["Normal"], ASCII_FONT, EA_FONT, size=10.5)
    doc.styles["Normal"].paragraph_format.space_after = Pt(6)
    doc.styles["Normal"].paragraph_format.line_spacing = 1.25

    # 标题
    sizes = {"Title": 22, "Heading 1": 17, "Heading 2": 14, "Heading 3": 12,
             "Heading 4": 11}
    for name, size in sizes.items():
        if name in [s.name for s in doc.styles]:
            set_style_font(doc.styles[name], ASCII_FONT, EA_FONT, size=size,
                           bold=True, color=RGBColor(0x1F, 0x38, 0x64))

    for name in ("List Bullet", "List Number"):
        if name in [s.name for s in doc.styles]:
            set_style_font(doc.styles[name], ASCII_FONT, EA_FONT, size=10.5)

    if "Quote" in [s.name for s in doc.styles]:
        set_style_font(doc.styles["Quote"], ASCII_FONT, EA_FONT, size=10.5,
                       color=RGBColor(0x55, 0x55, 0x55))

    # 页边距
    for section in doc.sections:
        section.left_margin = section.right_margin = None or section.left_margin
    return doc


# --------------------------------------------------------------------------
# 块级渲染
# --------------------------------------------------------------------------
def add_code_block(doc, lines, lang=""):
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(4)
    para.paragraph_format.space_after = Pt(8)
    para.paragraph_format.line_spacing = 1.0
    shade(para, CODE_BG)
    for i, line in enumerate(lines):
        run = para.add_run(line)
        set_run_font(run, MONO_ASCII, MONO_EA, size=9,
                     color=RGBColor(0x24, 0x29, 0x2E))
        if i < len(lines) - 1:
            run.add_break()


def add_quote(doc, lines):
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Pt(18)
    para.paragraph_format.space_before = Pt(4)
    para.paragraph_format.space_after = Pt(8)
    shade(para, QUOTE_BG)
    for i, line in enumerate(lines):
        if i:
            para.add_run().add_break()
        add_inline(para, line, base_size=10)


def add_table(doc, rows):
    header, *body = rows
    table = doc.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, cell_text in enumerate(header):
        cell = table.rows[0].cells[i]
        cell.text = ""
        para = cell.paragraphs[0]
        para.paragraph_format.space_after = Pt(2)
        add_inline(para, cell_text, base_size=10)
        for run in para.runs:
            run.font.bold = True
        shade(cell, HEADER_BG)

    for row in body:
        cells = table.add_row().cells
        for i in range(len(header)):
            text = row[i] if i < len(row) else ""
            cells[i].text = ""
            para = cells[i].paragraphs[0]
            para.paragraph_format.space_after = Pt(2)
            add_inline(para, text, base_size=10)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def split_table_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_table_sep(line):
    return bool(re.match(r"^\s*\|?[\s:\-|]+\|[\s:\-|]+$", line)) and "-" in line


def render(md_text, doc):
    lines = md_text.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            add_code_block(doc, buf, lang)
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            rows = [split_table_row(stripped)]
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            add_table(doc, rows)
            continue

        # 分隔线
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            para = doc.add_paragraph()
            para.paragraph_format.space_before = Pt(2)
            para.paragraph_format.space_after = Pt(8)
            bottom_border(para)
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            add_quote(doc, buf)
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            para = doc.add_heading(level=min(level, 4))
            add_inline(para, text)
            i += 1
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 无序列表
        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            indent = len(m.group(1)) // 2
            para = doc.add_paragraph(style="List Bullet")
            para.paragraph_format.left_indent = Pt(18 + indent * 18)
            para.paragraph_format.space_after = Pt(3)
            add_inline(para, m.group(2))
            i += 1
            continue

        # 有序列表
        m = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if m:
            indent = len(m.group(1)) // 2
            para = doc.add_paragraph(style="List Number")
            para.paragraph_format.left_indent = Pt(18 + indent * 18)
            para.paragraph_format.space_after = Pt(3)
            add_inline(para, m.group(2))
            i += 1
            continue

        # 普通段落
        para = doc.add_paragraph()
        add_inline(para, stripped)
        i += 1


def main():
    if len(sys.argv) != 3:
        print("用法: python md2docx.py 输入.md 输出.docx")
        return 1

    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = build_document()
    render(md_text, doc)
    doc.save(dst)
    print("生成成功:", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
