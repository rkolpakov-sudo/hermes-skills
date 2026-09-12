---
name: smeta-pdf-generator
description: "Generate professional PDF documents for construction estimates (сметы), acts, specifications using fpdf2/reportlab with Cyrillic support. Creates formatted сметные документы in Russian."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [pdf, smeta, construction, russian, reports]

---

# Smeta PDF Generator

Generates professional Russian-language PDF documents for construction estimating (сметное дело) using fpdf2 with Windows Cyrillic fonts.

## Prerequisites

- `fpdf2` installed (`pip install fpdf2`)
- Windows system fonts: `C:\Windows\Fonts\arial.ttf`, `calibri.ttf`, etc.
- On Linux: install `fonts-dejavu` or any TTF font with Cyrillic support

## Quick Usage

```python
from hermes_tools import execute_code

execute_code(code='''
import sys
sys.path.insert(0, "~/.hermes/skills/smeta-pdf-generator/scripts")
from smeta_pdf import create_smeta_report

create_smeta_report(
    title="Смета на строительство",
    project_name="Объект: ЖК Северный",
    output_path="/tmp/smeta.pdf"
)
''')
```

## Document Types

### 1. Сметная ведомость (Estimate Statement)
- Table with ГЭСН/ФЕР codes, descriptions, quantities, rates, totals
- Summary section with subtotal, НДС, total cost

### 2. Акт выполненных работ (Work Completion Certificate)
- Header with contract number and date
- Completed work table
- Signatures block

### 3. Спецификация материалов (Material Specification)
- Material list with codes, descriptions, units, quantities, prices
- Supplier information section

## Font Configuration

```python
# Windows Cyrillic font paths
CYRILLIC_FONTS = {
    "regular": r"C:\Windows\Fonts\arial.ttf",
    "bold": r"C:\Windows\Fonts\arialbd.ttf",
    "italic": r"C:\Windows\Fonts\ariali.ttf",
}

# Linux fallback
if not os.path.exists(CYRILLIC_FONTS["regular"]):
    CYRILLIC_FONTS = {k: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" for k in CYRILLIC_FONTS}
```

## Template Examples

See `templates/` directory for:
- `smeta_template.py` — сметная ведомость with ГЭСН tables
- `akt_template.py` — акт выполненных работ
- `specification_template.py` — спецификация материалов

## Workflow

1. Load template from `templates/` or create inline
2. Populate with data (from Excel, SQLite, or manual input)
3. Generate PDF via fpdf2
4. Save to output path or return as bytes for email attachment

## Integration

- **Excel**: Read сметные данные через `mcp_excel_*` tools, then generate PDF
- **SQLite**: Query нормативы from database, format into PDF report
- **Email**: Attach generated PDF via Himalaya CLI

## Troubleshooting

### fpdf2 + Cyrillic: Critical pitfalls

1. **Register font BEFORE `add_page()`** — `header()` fires automatically on page creation. If you call `add_font()` after `add_page()`, the header crashes with "Undefined font". Solution: register in subclass `__init__()`, not after instantiation.

2. **Use a custom family name** — registering as `"Arial"` conflicts with fpdf2's built-in Helvetica alias, causing silent failures. Use `"Cyrillic"` or another unique name instead:
   ```python
   self.add_font("Cyrillic", "", font_path, uni=True)  # not "Arial"
   ```

3. **Italic requires a separate `.ttf` file** (`ariali.ttf`) that may not exist on the system. If italic is needed, register `add_font(FAMILY, "I", italic_font_path)`. Workaround: use regular style in footer/header when italic font is unavailable.

4. **No `multi_cell` for column headers** — `.cell()` does NOT support `multi_cell=True`. Wrap long text manually or use single-line headers.
