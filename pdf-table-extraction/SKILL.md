---
name: pdf-table-extraction
description: Convert complex PDF tables to Excel.
---

# pdf-table-extraction

Use when converting PDF tables to structured formats (Excel, CSV). Handles complex layouts like multi-line text and hierarchical (parent-child) row structures.

## Capabilities
- Extract tables from PDF using `pdfplumber`.
- Reconstruct multi-line text into single cells.
- Preserve hierarchical row structures.
- Export to `.xlsx` or `.csv`.

## Workflows
- [Complex Table Extraction (Hierarchical/Multi-line)](references/complex_table_extraction.md)

## References
- `references/complex_table_extraction.md`: Specific logic for handling engineering/specification PDFs.
