# Cyrillic / legacy-encoding PDF pitfalls (MinerU case study, Aug 2026)

Verified findings from a controlled repro against MinerU 3.4 on Windows
(Pricer_Vision project). Class-level lesson: **a PDF can have a perfect text
layer that extractors still mangle** if fonts lack ToUnicode CMaps.

## The encoding trap

- Many Russian CAD/Word→PDF converters embed Type1/CID fonts with cp1251
  byte codes and NO /ToUnicode table. The rendered page looks fine; the text
  layer is garbage-in-garbage-out for any extractor.
- Symptom signature in extracted output:
  - txt-mode extraction: `Труба ПВХ` → `ÒðóÆà ˇ´Õ` (cp1251 bytes read as
    Western/Latin) — mojibake, deterministic, NOT random OCR noise.
  - OCR-mode extraction of a rendered text page: transliteration-like junk
    (`óa aCay a1óaiiay`) — the east_slavic OCR-rec model misreading clean print.
- Distinguish mojibake vs OCR noise by pattern: mojibake preserves length and
  punctuation positions exactly; OCR noise does not.

## Diagnostic recipe (tight loop)

1. Generate a minimal one-page PDF with known Cyrillic text. A dependency-free
   generator works in ~30 lines of Python: hand-built PDF 1.4 with a content
   stream of cp1251-encoded `(text) Tj` operators, Courier base font, no
   ToUnicode — write bytes directly, no external libraries.
2. Run BOTH extractor modes on it (`-m auto`, `-m txt` for MinerU).
3. Compare output against the known input strings.
4. Inspect raw bytes: extract the content stream (`stream\n...\nendstream`)
   and decode candidate encodings (cp1251) to confirm what the layer holds.

If the minimal repro reproduces the corruption → extractor/font-encoding
problem. If not → document-specific issue (scans, layout, tables).

## MinerU-specific operational findings

- CLI startup cost dominates: each invocation spawns a temporary
  FastAPI/Uvicorn service and re-initializes DocAnalysis models (~2s init,
  ~25s total overhead for a 1-page 900-byte PDF; ~7s actual processing).
  Per-document subprocess calls never amortize this. For batches, prefer a
  long-lived service or batch API over repeated CLI runs.
- `-m auto` routes text pages through OCR when the extracted layer decodes to
  junk — silently choosing the worse path. Pin `-m txt` / `-m ocr` when you
  know the document class.
- Re-running the whole pipeline because extracted text < N chars (length
  heuristic) doubles cost and rarely helps; classify the PDF type BEFORE parsing.
- Silent truncation hazard: downstream consumers that cap input chars
  (e.g. LLM structuring at 24K) drop specification rows without surfacing it
  to the user. Always log/warn visibly on truncation.

## Alternatives for this document class

- **pdf-inspector (Firecrawl)** — Rust, PyO3 bindings (`pip install
  pdf-inspector`). Classifies TextBased/Scanned/Mixed in ~20ms with
  confidence + per-page OCR routing; extracts position-aware text and clean
  Markdown (best-in-class table TEDS 0.814 on opendataloader-bench, ~36x
  faster than pymupdf4llm). Handles CID fonts via bcmap/fallback CMaps —
  designed for exactly the no-ToUnicode problem above. Does NOT do OCR itself
  for scanned pages (routes to PP-OCRv6 or hosted fallback).
- Hybrid architecture that works: classify first → text-based path via
  pdf-inspector/pymupdf → scanned pages to heavy OCR (MinerU/marker).
