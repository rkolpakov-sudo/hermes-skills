#!/usr/bin/env python3
# MIT License. Part of the Hermes docx skill.
"""Create a .docx document from a JSON spec.

Usage: docx_create.py spec.json output.docx
Run with --help for the spec format summary.

Spec (JSON object):
{
  "preset": "russian_contract",     # optional named typography preset (sets
                                    # page + styles for TNR/Justified/красная
                                    # строка; see PRESETS below). Overridable
                                    # by explicit page/styles blocks below.
  "page": {"width_mm": 210, "height_mm": 297,
           "margins_mm": {"top": 25, "bottom": 25, "left": 20, "right": 20}},
  "header": "text shown in page header",
  "footer": "text shown in page footer",
  "styles": [{"name": "MyStyle", "base": "Normal", "font": "Arial",
              "size_pt": 12, "bold": true, "color": "1F4E79",
              "align": "center",            # left|center|right|justify
              "first_line_indent_dxa": 709, # "красная строка" ~1.25cm
              "left_indent_dxa": 0,
              "space_after_dxa": 160, "space_before_dxa": 0}],
  "blocks": [
    {"type": "heading", "text": "Title", "level": 1},
    {"type": "paragraph", "style": "MyStyle", "runs": [
        {"text": "plain "}, {"text": "bold", "bold": true},
        {"text": " italic", "italic": true},
        {"text": " under", "underline": true}]},
    {"type": "paragraph", "text": "shortcut: single plain run",
     "first_line_indent_dxa": 709, "align": "justify", "space_after_dxa": 160},
    {"type": "bullet_list", "items": ["a", "b"]},
    {"type": "numbered_list", "items": ["one", "two"]},
    {"type": "table", "header": ["Col1", "Col2"],
     "rows": [["1", "2"]], "style": "Table Grid",
     "header_bold": true, "font_size_pt": 9,
     "header_fill": "D9E2F3",            # light-blue header fill (ShadingType.CLEAR)
     "width_dxa": 9360,                  # total table width in DXA
     "column_widths": [4680, 4680],      # MUST sum to width_dxa
     "cell_margins": {"top": 40, "bottom": 40, "left": 60, "right": 60}},
    {"type": "image", "path": "pic.png", "width_mm": 60},
    {"type": "page_break"},
    {"type": "toc"}
  ]
}

Named typography presets (set "preset" at the top level):
  - "russian_contract": A4, left margin 20 mm, Times New Roman everywhere,
    RC Title (14pt bold center), RC Heading (12pt bold center), RC Body
    (12pt justified + 709 DXA first-line indent + 160 DXA after),
    RC Note (8pt italic). Use these style names in your blocks.

Extras: `footer_page_numbers": true` at the top level adds a
"Page X of Y" footer built from PAGE/NUMPAGES fields, and a `toc` block
inserts a Table of Contents field. Field results are computed by
Word/LibreOffice when the file is opened, not by python-docx.
"""
from __future__ import annotations

import argparse
import json
import sys

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor, Twips


def apply_page(doc, page: dict) -> None:
    section = doc.sections[0]
    if "width_mm" in page:
        section.page_width = Mm(page["width_mm"])
    if "height_mm" in page:
        section.page_height = Mm(page["height_mm"])
    m = page.get("margins_mm", {})
    for side in ("top", "bottom", "left", "right"):
        if side in m:
            setattr(section, f"{side}_margin", Mm(m[side]))


# --- Typography presets (Document Engine spec §3.2 / §3.4) ------------
# "russian_contract": Times New Roman, justified body with a 1.25 cm
# (709 DXA) first-line indent ("красная строка"), classic left margin
# >= 20 mm. Sizes are full points; indents/spacing are DXA (twips).
RUSSIAN_CONTRACT = {
    "page": {"width_mm": 210, "height_mm": 297,
             "margins_mm": {"top": 15, "bottom": 15, "left": 20, "right": 15}},
    "styles": [
        {"name": "RC Title", "base": "Normal", "font": "Times New Roman",
         "size_pt": 14, "bold": True, "align": "center",
         "space_after_dxa": 200},
        {"name": "RC Heading", "base": "Normal", "font": "Times New Roman",
         "size_pt": 12, "bold": True, "align": "center",
         "space_after_dxa": 200},
        {"name": "RC Body", "base": "Normal", "font": "Times New Roman",
         "size_pt": 12, "align": "justify", "first_line_indent_dxa": 709,
         "space_after_dxa": 160},
        {"name": "RC Note", "base": "Normal", "font": "Times New Roman",
         "size_pt": 8, "italic": True, "align": "left"},
    ],
}

PRESETS = {"russian_contract": RUSSIAN_CONTRACT}


def apply_preset(doc, name: str) -> None:
    """Apply a named typography preset (page setup + style set)."""
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError(f"unknown preset: {name}")
    if preset.get("page"):
        apply_page(doc, preset["page"])
    if preset.get("styles"):
        add_styles(doc, preset["styles"])


ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "justified": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def _apply_paragraph_format(pfmt, spec: dict) -> None:
    """Apply align / indent / spacing from a spec dict onto a ParagraphFormat."""
    if spec.get("align"):
        pfmt.alignment = ALIGN_MAP.get(spec["align"], WD_ALIGN_PARAGRAPH.LEFT)
    if spec.get("first_line_indent_dxa") is not None:
        pfmt.first_line_indent = Twips(int(spec["first_line_indent_dxa"]))
    if spec.get("left_indent_dxa") is not None:
        pfmt.left_indent = Twips(int(spec["left_indent_dxa"]))
    if spec.get("space_after_dxa") is not None:
        pfmt.space_after = Twips(int(spec["space_after_dxa"]))
    if spec.get("space_before_dxa") is not None:
        pfmt.space_before = Twips(int(spec["space_before_dxa"]))


def _set_table_widths(table, total_dxa, column_widths) -> None:
    """Dual width definition (spec §3.2): tblW total + per-cell tcW.

    column_widths MUST sum to total_dxa for correct layout.
    """
    tblPr = table._tbl.tblPr
    tblW = tblPr.find(qn('w:tblW'))
    if tblW is None:
        tblW = OxmlElement('w:tblW')
        tblPr.append(tblW)
    tblW.set(qn('w:w'), str(total_dxa))
    tblW.set(qn('w:type'), 'dxa')
    if column_widths:
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                if i >= len(column_widths):
                    break
                tcPr = cell._tc.get_or_add_tcPr()
                tcW = tcPr.find(qn('w:tcW'))
                if tcW is None:
                    tcW = OxmlElement('w:tcW')
                    tcPr.append(tcW)
                tcW.set(qn('w:w'), str(column_widths[i]))
                tcW.set(qn('w:type'), 'dxa')


def _set_cell_margins(cell, dxa: dict) -> None:
    """Set w:tcMar on a cell (default 40 DXA on every edge, per spec §3.2)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.find(qn('w:tcMar'))
    if tcMar is None:
        tcMar = OxmlElement('w:tcMar')
        tcPr.append(tcMar)
    for edge in ('top', 'bottom', 'left', 'right'):
        val = dxa.get(edge, 40)
        el = tcMar.find(qn(f'w:{edge}'))
        if el is None:
            el = OxmlElement(f'w:{edge}')
            tcMar.append(el)
        el.set(qn('w:w'), str(val))
        el.set(qn('w:type'), 'dxa')


def _shade(cell, fill_hex: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tcPr.append(shd)
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)


def add_table(doc, block: dict):
    """Build a table with dual widths, cell margins and optional header fill."""
    header = block.get("header", [])
    rows = block.get("rows", [])
    ncols = len(header) if header else (len(rows[0]) if rows else 1)
    table = doc.add_table(rows=0, cols=ncols)
    table.style = block.get("style", "Table Grid")
    font_size_pt = block.get("font_size_pt", 9)
    header_fill = block.get("header_fill")
    cell_margins = block.get("cell_margins", {})
    header_align = block.get("header_align", "center")

    def _put(cells, texts, header_row):
        for i, text in enumerate(texts):
            cell = cells[i]
            cell.text = ""
            para = cell.paragraphs[0]
            if header_row:
                para.alignment = ALIGN_MAP.get(header_align, WD_ALIGN_PARAGRAPH.CENTER)
            run = para.add_run(str(text))
            run.font.name = "Times New Roman"
            run.font.size = Pt(font_size_pt)
            if header_row and block.get("header_bold", True):
                run.bold = True
            _set_cell_margins(cell, cell_margins)
            if header_row and header_fill:
                _shade(cell, header_fill)

    if header:
        _put(table.add_row().cells, header, True)
    for row in rows:
        _put(table.add_row().cells, row, False)
    total_dxa = block.get("width_dxa") or (sum(block["column_widths"])
                                           if block.get("column_widths") else None)
    if total_dxa:
        _set_table_widths(table, total_dxa, block.get("column_widths"))
    return table


def add_styles(doc, styles: list) -> None:
    for s in styles:
        style = doc.styles.add_style(s["name"], WD_STYLE_TYPE.PARAGRAPH)
        if s.get("base"):
            style.base_style = doc.styles[s["base"]]
        font = style.font
        if s.get("font"):
            font.name = s["font"]
        if s.get("size_pt"):
            font.size = Pt(s["size_pt"])
        if s.get("bold") is not None:
            font.bold = s["bold"]
        if s.get("italic") is not None:
            font.italic = s["italic"]
        if s.get("color"):
            font.color.rgb = RGBColor.from_string(s["color"])
        _apply_paragraph_format(style.paragraph_format, s)


def add_runs(para, block: dict) -> None:
    runs = block.get("runs")
    if runs is None:
        runs = [{"text": block.get("text", "")}]
    for r in runs:
        run = para.add_run(r.get("text", ""))
        if r.get("bold"):
            run.bold = True
        if r.get("italic"):
            run.italic = True
        if r.get("underline"):
            run.underline = True


def add_block(doc, block: dict) -> None:
    btype = block["type"]
    if btype == "heading":
        doc.add_heading(block.get("text", ""), level=block.get("level", 1))
    elif btype == "paragraph":
        para = doc.add_paragraph(style=block.get("style"))
        _apply_paragraph_format(para.paragraph_format, block)
        add_runs(para, block)
    elif btype == "bullet_list":
        for item in block.get("items", []):
            doc.add_paragraph(item, style="List Bullet")
    elif btype == "numbered_list":
        for item in block.get("items", []):
            doc.add_paragraph(item, style="List Number")
    elif btype == "table":
        add_table(doc, block)
    elif btype == "image":
        width = Mm(block["width_mm"]) if block.get("width_mm") else None
        doc.add_picture(block["path"], width=width)
    elif btype == "page_break":
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    elif btype == "toc":
        from docx_edit import _add_field
        para = doc.add_paragraph()
        _add_field(para, r' TOC \o "1-3" \h \z \u ',
                   "Table of contents - open in Word/LibreOffice and "
                   "update fields to populate.")
    else:
        raise ValueError(f"unknown block type: {btype}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Create a .docx from a JSON spec.",
        epilog="See the module docstring (top of this file) for the spec format.")
    ap.add_argument("spec", help="path to JSON spec file")
    ap.add_argument("output", help="path of .docx to write")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)

    doc = Document()
    if spec.get("preset"):
        apply_preset(doc, spec["preset"])
    if spec.get("page"):
        apply_page(doc, spec["page"])
    if spec.get("styles"):
        add_styles(doc, spec["styles"])
    if spec.get("header"):
        doc.sections[0].header.paragraphs[0].text = spec["header"]
    if spec.get("footer"):
        doc.sections[0].footer.paragraphs[0].text = spec["footer"]
    for block in spec.get("blocks", []):
        add_block(doc, block)
    if spec.get("footer_page_numbers"):
        from docx_edit import _add_field
        para = doc.sections[0].footer.paragraphs[0]
        para.add_run("Page ")
        _add_field(para, " PAGE ", "1")
        para.add_run(" of ")
        _add_field(para, " NUMPAGES ", "1")
    doc.save(args.output)
    print(json.dumps({"ok": True, "output": args.output,
                      "blocks": len(spec.get("blocks", []))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
