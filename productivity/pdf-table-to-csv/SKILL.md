---
name: pdf-table-to-csv
description: "PDF table → clean CSV: merge split rows, fix symbols."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [PDF, Tables, CSV, Data-Extraction, Engineering, BOM, Spec, Cyrillic]
    related_skills: [ocr-and-documents, pdf, xlsx]
---

# PDF Table → Clean CSV

Turn a **structured PDF table** (specification / "спецификация", BOM, technical schedule) into a clean CSV where **each logical record is exactly one row**. This is *interpretation* of the table, not raw text extraction: you merge split names, separate section headers and kit components, and fix symbol/font corruption before writing.

Use when the user uploads a PDF containing a repeating-column table and wants CSV/spreadsheet output, especially engineering/construction specs where a name wraps across several physical rows and symbols like Ø get mangled by the PDF font layer.

## When to use vs. not
- **Use this**: table → clean CSV with domain-aware cleanup (multi-line names, symbol fixes, row classification).
- **Only need raw text/markdown**: use the `ocr-and-documents` skill instead.
- **Creating/editing the spreadsheet or document itself**: `xlsx` / `docx` / `powerpoint`.

## Pipeline (5 steps)

1. **Probe** — page count, `page.rotation`, and whether `page.find_tables()` returns a table. (Rotated sheets are common in A2/A3 landscape engineering sheets.)
2. **Extract rows** with `page.find_tables().tables[0].extract()`. This is **rotation-aware** — do NOT use raw `get_text("words")` coordinates on a rotated page (they come out meaningless). Map columns from the header text, not from fixed indices.
3. **Classify every row** (see "Pitfall 1" + `references/domain-notes.md`): item / section-header / kit-component / continuation.
4. **Clean each field** (word-splits, symbol corruption, number spacing). See `references/domain-notes.md`.
5. **Write CSV + verify** (QA scan below). Never ship an unverified CSV.

Write the CSV with `utf-8-sig` so Cyrillic opens cleanly in Excel. Preserve the source column names.

## The 5 pitfalls that decide success

### 1. Multi-line names are ONE record — but not every continuation merges
A physical row whose name cell is filled but quantity is empty is one of three things:
- **continuation** — a size/attribute (`Ø150х4,5`, `с раструбным соединением`, `на гибком шланге`, `унитаза Ø110х400мм`) → **merge** into the previous item.
- **section header** (`Трубы и изоляция`, `Канализация`, `Хоз. питьевой водопровод В1.3`) → keep as a **separate** header row.
- **kit component** (`а) Сифон пластмассовый СБУв` carrying its own `ГОСТ 23289-94`) → **keep separate**, do not merge.

**Discriminator**: does the name-only row carry its own standard / Тип value (ГОСТ, ТУ, марка)? → component (separate). Known section phrase → header. Otherwise → continuation (merge). Full heuristic in `references/domain-notes.md`.

**Mother-child (hierarchical) specs** — specs where a full description row (no quantity) is followed by many short child rows (DN15, 400 мм, 20/20): the mother is ABSORBED and its name propagated to every child (name := mother, designation → «Тип, марка», mother's марка prepended). This needs lookahead classification, ALL-CAPS header detection, and careful handling of Ø/d-prefixed children (they are children, NOT continuations). Full verified rules: `references/hierarchical-parent-child-rows.md`.

### 2. Ø / diameter symbol is frequently corrupted in the text layer
Cyrillic technical PDFs often map the diameter glyph to `6`, `ф`, or `∅` in the *text layer* while **rendering** Ø/φ. So `6150х4,5` really means `Ø150х4,5`, but real digits like `Ду=65`, `DN50`, `65х15` are genuine and must survive. **Never do a blind replace.** Convert only a *leading* `6`/`ф` that is immediately followed by a real pipe diameter (15,20,25,32,40,50,65,80,100,110,125,150,160,219,…). Exact rule + codepoint proof: `references/domain-notes.md`.

**Verification path when vision times out:** don't loop on the vision tool — read glyph codepoints with `page.get_text("rawdict")` and inspect `ord()` of the leading char (`0x36`=ASCII "6" vs `0xD8`=Ø). Combine that with one successful vision pass to confirm which glyph the font *renders*.

### 3. Word-split artifacts
Extraction splits Cyrillic words: `Труб а`, `электрос варная`, `во д огазопров о д ная`, `К ов ер`, `Трой ник`. Enumerate the **distinct** name list, build a repair dict from it, apply, then **re-scan the output for leftovers — must be zero**. (A classic bug: defining the repair list but forgetting to actually apply it in the final cleaner.)

### 4. Rotated landscape sheets
`page.rotation` may be 90. Use `find_tables().extract()` for data (handles rotation) and PIL `img.rotate(-90, expand=True)` for vision crops. High-res render: `page.get_pixmap(matrix=pymupdf.Matrix(3,3))`.

### 5. Stray quantities on section headers
A header row can carry a qty that actually belongs to an adjacent cell (extraction bleed on rotated pages). Detect header-with-qty, **log it**, and do NOT emit it as a record.

## Verify (do not skip)
After writing, run the QA scan for: double spaces, space-before-punctuation, a naked symbol with no digit (default `Ø`), a dangling trailing separator (`х`/`=` with no value), and empty required columns. Then eyeball: the first ~15 rows, one header-heavy region, one kit/component region. Confirm the split/merge counts against your log.

## Files
- `references/domain-notes.md` — Ø-corruption rule + codepoint proof, row-classification heuristic, word-split approach, rotated-page handling, stray-qty handling.
- `references/hierarchical-parent-child-rows.md` — mother-child (мать-дети) row absorption rules: lookahead mother-vs-header, child name/type propagation, Ø/d children vs continuations, dash-prefixed standalone items, subheader-bleed strip, ALL-CAPS headers, name/type column splice, lost code column on poz-less sheets.
- `scripts/qa_scan_csv.py` — reusable QA scanner for a produced CSV (run it, don't hand-check).

## Related
- Raw text/markdown extraction → `ocr-and-documents`.
- Producing the Excel/Word artifact → `xlsx`, `docx`, `powerpoint`.
