#!/usr/env python3
"""Recalculate a workbook's formulas headlessly with `formulas` (pure Python).

openpyxl never computes formulas. This script uses the `formulas` library
(a pure-Python Excel calculation engine, no LibreOffice / Excel / JVM) to
load the workbook, build the dependency graph, evaluate every cell, and
write the cached results back into the file so that
`xlsx_read.py --data-only` and `--formulas` show real numbers.

Why `formulas` instead of LibreOffice:
  * Zero external binaries — `pip install formulas` only.
  * Works headless on any OS including this Windows host.
  * Deterministic recalculation of the full dependency graph.

Behavior:
  * Success: writes cached values into --out (or replaces input) and prints
    {"ok": true, "recalculated": true, "formula_cells": N,
     "evaluated": M, "output": "..."}. Exit 0.
  * The engine raises on an unsupported function: prints
    {"ok": true, "recalculated": false, "reason": ..., "unsupported": [...]}
    and exits 0 (callers branch on the JSON, as before).

Usage:
  xlsx_recalc.py book.xlsx
  xlsx_recalc.py book.xlsx --out recalced.xlsx
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def count_formula_cells(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False)
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Recalculate .xlsx formulas headlessly via `formulas`.")
    ap.add_argument("file", help="path to .xlsx file")
    ap.add_argument("--out", help="output path (default: replace input)")
    args = ap.parse_args(argv)

    src = Path(args.file).resolve()
    if not src.exists():
        print(json.dumps({"ok": False, "error": f"no such file: {src}"},
                         file=sys.stderr))
        return 1

    dest = Path(args.out).resolve() if args.out else src

    try:
        import formulas
    except ImportError:
        print(json.dumps({
            "ok": True, "recalculated": False,
            "reason": "`formulas` not installed",
            "guidance": "pip install formulas",
        }, ensure_ascii=False))
        return 0

    formula_cells = count_formula_cells(src)
    try:
        # Load + build the graph + evaluate everything in one pass.
        xl_model = formulas.ExcelModel().loads(str(src)).finish()
        solution = xl_model.calculate()
        # Write the recalculated workbook (cached values embedded) into dirpath;
        # `formulas` reuses the original base filename automatically.
        xl_model.write(dirpath=str(dest.parent), solution=solution)
    except Exception as exc:  # noqa: BLE001 - report, don't crash callers
        # Surface the first unsupported token if present in the message.
        unsupported = []
        msg = str(exc)
        if "not supported" in msg:
            unsupported = [m for m in msg.split() if "(" in m and ")" in m][:10]
        print(json.dumps({
            "ok": True, "recalculated": False,
            "reason": f"calculation engine error: {msg[:400]}",
            "unsupported": unsupported,
        }, ensure_ascii=False))
        return 0

    # `formulas` writes "<stem>.xlsx" into dirpath; rename to exact dest name.
    produced = dest.parent / (src.stem + ".xlsx")
    if produced != dest and produced.exists():
        shutil.move(str(produced), str(dest))

    evaluated = count_formula_cells(dest)
    print(json.dumps({
        "ok": True, "recalculated": True, "output": str(dest),
        "formula_cells": formula_cells, "evaluated": evaluated,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
