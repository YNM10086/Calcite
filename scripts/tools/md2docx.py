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

import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ASCII_FONT = "Calibri"
EA_FONT = "微软雅黑"          # 中文字体
MONO_ASCII = "Consolas"
MONO_EA = "微软雅黑"
CODE_BG = "F2F3F5"            # 代码块底色
QUOTE_BG = "FFF8E1"           # 引用底色
HEADER_BG = "E8EEF7"          # 表头底色

# --------------------------------------------------------------------------
# OOXML 子元素顺序：pPr / rPr / tcPr 里的元素不是随便排的，
# 顺序错了 Word 能容忍，但严格校验器（officecli validate 等）会报
# "unexpected child element"。所以统一用 insert_element_before 而不是 append。
# --------------------------------------------------------------------------
_AFTER_SHD_IN_PPR = (
    "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
    "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
    "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
    "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
    "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl",
    "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
)
_AFTER_PBDR_IN_PPR = ("w:shd",) + _AFTER_SHD_IN_PPR
_AFTER_SHD_IN_TCPR = (
    "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign",
    "w:hideMark", "w:headers", "w:cellIns", "w:cellDel", "w:cellMerge",
    "w:tcPrChange",
)
_AFTER_RFONTS_IN_RPR = (
    "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike",
    "w:dstrike", "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof",
    "w:snapToGrid", "w:vanish", "w:webHidden", "w:color", "w:spacing", "w:w",
    "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect",
    "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em",
    "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath",
)


def insert_ordered(parent, element, successors):
    """把 element 插到 parent 里第一个「应当排在它后面」的兄弟之前。"""
    parent.insert_element_before(element, *successors)


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
        insert_ordered(rpr, rfonts, _AFTER_RFONTS_IN_RPR)
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
            insert_ordered(rpr, rfonts, _AFTER_RFONTS_IN_RPR)
        if ascii_name:
            rfonts.set(qn("w:ascii"), ascii_name)
            rfonts.set(qn("w:hAnsi"), ascii_name)
        if ea_name:
            rfonts.set(qn("w:eastAsia"), ea_name)


def shade(element, fill):
    """给段落或单元格加底色。"""
    is_par = hasattr(element, "paragraph_format")
    pr = element._element.get_or_add_pPr() if is_par \
        else element._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    insert_ordered(pr, shd, _AFTER_SHD_IN_PPR if is_par else _AFTER_SHD_IN_TCPR)


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
    insert_ordered(ppr, borders, _AFTER_PBDR_IN_PPR)


INLINE_RE = re.compile(
    r"(\*\*.+?\*\*"                                       # **粗体**
    r"|`[^`]+`"                                           # `行内代码`
    r"|\*[^*]+\*"                                         # *斜体*
    # _斜体_：按 CommonMark 规则，前后不能紧挨字母数字，
    # 否则 snake_case / file_name 这种下划线会被误判成斜体
    r"|(?<![A-Za-z0-9_])_[^_\s][^_]*?_(?![A-Za-z0-9_])"
    r")"
)


def add_inline(paragraph, text, base_size=None):
    """解析 **粗体** / *斜体* / _斜体_ / `代码`，写入段落。"""
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
        elif part.startswith("_") and part.endswith("_") and len(part) > 2:
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


def add_figure(doc, caption, src, max_width_in=6.3):
    """插入一张居中图片 + 图注（图注用灰色小字）。

    max_width_in 是正文可用宽度；图片按此宽度等比缩放。
    """
    if not os.path.exists(src):
        para = doc.add_paragraph()
        add_inline(para, f"[缺图: {src}]", base_size=10)
        return
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_before = Pt(10)
    para.paragraph_format.space_after = Pt(2)
    para.add_run().add_picture(src, width=Inches(max_width_in))
    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(14)
        run = cap.add_run(caption)
        set_run_font(run, size=9, color=RGBColor(0x70, 0x70, 0x70))


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

        # 插图：![图 1 说明](相对路径)
        m_img = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", stripped)
        if m_img:
            add_figure(doc, m_img.group(1), m_img.group(2))
            i += 1
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
