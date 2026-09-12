# Complex Table Extraction (Hierarchical/Multi-line)

When extracting tables from engineering/specification PDFs (like MEP drawings, HVAC, or structural specs), standard table extraction often fails due to:
1.  **Multi-line text**: A single cell's content spans multiple physical lines in the PDF.
2.  **Hierarchical Rows**: Parent rows (e.g., Section Titles) are followed by child rows (items) without explicit identifiers in every row.

## Extraction Workflow

### 1. Detection & Identification
- Use `pdfplumber` to find table objects.
- **Identify the Header**: Search for key anchor terms (e.g., "Позиция", "№", "Наименование") to determine the column alignment and start of the data.

### 2. Text Reconstruction (The "Multi-line" Fix)
- **The Problem**: `pdfplumber` might return `NaN` or separate rows for text that was visually one cell in the PDF.
- **The Fix**:
    - Iterate through rows.
    - If a row has a null value in a primary text column but contains text in a "sub-row" below it, merge the text into the previous non-null row's text cell.
    - Strip extra whitespace and `\n` from the combined string.

### 3. Hierarchy Preservation
- **The Problem**: Parent rows act as headers but lack the data columns of the items.
- **The Fix**:
    - Identify parent rows by their visual/content properties (e.g., spanning multiple columns, bold text, or specific naming patterns).
    - For each child row, ensure the "Parent" context is accessible (either by duplicating the parent name in a hidden/auxiliary column or by ensuring the hierarchy is logically navigable in the final Excel/CSV).

### 4. Validation
- Check the final row count against the number of distinct items found in the PDF.
- Ensure no "empty" rows exist that are actually just fragments of multi-line cells.

## Python Implementation Pattern

```python
import pdfplumber
import pandas as pd

def extract_complex_table(pdf_path, output_xlsx):
    data = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                # 1. Find header index
                # 2. Process rows with multi-line merging logic
                # 3. Append to data list
                pass
    
    df = pd.DataFrame(data)
    df.to_excel(output_xlsx, index=False)
```
