#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Заполнение цен ВОР из справочника цен (xlsx -> xlsx), ТОЛЬКО строки
"материал"/"материалы" (строки "работа" не трогаются).

Проверено на шаблоне ВОР_ВК (см. references/vor-template-structure.md).
Оригиналы не изменяются; формулы сохраняются (data_only=False);
wb.calculation.fullCalcOnLoad=True для пересчёта в Excel при открытии.
Цены '-' в справочнике -> H пустая + строка залита красным FFC7CE.

Использование:
    python fill_vor_prices.py <ВОР.xlsx> <справочник.xlsx> <выход.xlsx>
    python fill_vor_prices.py <ВОР.xlsx> <справочник.xlsx> <выход.xlsx> --verify-only

Если структура файла отличается от типового шаблона, поправить константы ниже.
"""
import sys
import openpyxl
from openpyxl.styles import PatternFill

# --- КОНФИГ (под типовой шаблон ВОР) ---
COL_TYPE = 1        # A: тип строки ("материал"/"материалы"/"работа"/заголовки)
COL_NAME = 3        # C: наименование
COL_PRICE = 8       # H: "Цена за ед., руб. с НДС" (заполняется)
ROW_DATA_START = 9  # первая строка данных после шапки
ROW_DATA_END = None # None = до конца; при наличии хвоста (ИТОГО/Детализация) задать число
MAX_FILL_COL = 25   # Y: до какой колонки заливать строку красным
REF_NAME_COL = 2    # справочник: наименование
REF_PRICE_COL = 8   # справочник: цена
REF_HEADER_ROWS = 1 # справочник: сколько строк шапки пропустить

DASH = {"-", "—", "–"}
RED_FILL = PatternFill(start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid")


def norm(s):
    if s is None:
        return ""
    return " ".join(str(s).split()).lower().replace("ё", "е")


def load_reference(ref_path):
    wb_r = openpyxl.load_workbook(ref_path, data_only=True)
    ws_r = wb_r.active
    ref = {}
    for r in range(REF_HEADER_ROWS + 1, ws_r.max_row + 1):
        name = ws_r.cell(row=r, column=REF_NAME_COL).value
        if name is None or str(name).strip() == "":
            continue
        key = norm(name)
        if key not in ref:  # дубликаты имён: берём первое вхождение
            ref[key] = ws_r.cell(row=r, column=REF_PRICE_COL).value
    return ref


def fill(vor_path, ref, out_path, row_data_end):
    wb = openpyxl.load_workbook(vor_path, data_only=False)  # ВАЖНО: формулы!
    ws = wb.active
    anchors = {(m.min_row, m.min_col) for m in ws.merged_cells.ranges}
    stats = {"numeric": 0, "dash": 0, "no_ref": 0, "work_skipped": 0}
    dash_rows, no_ref_rows = [], []

    last = row_data_end if row_data_end else ws.max_row
    for r in range(ROW_DATA_START, last + 1):
        a = ws.cell(row=r, column=COL_TYPE).value
        c = ws.cell(row=r, column=COL_NAME).value
        if c is None or str(c).strip() == "":
            continue
        if a not in ("материал", "материалы"):
            if a == "работа":
                stats["work_skipped"] += 1
            continue
        key = norm(c)
        if key not in ref:
            stats["no_ref"] += 1
            no_ref_rows.append((r, str(c).strip()))
            continue
        price = ref[key]
        if isinstance(price, str) and price.strip() in DASH:
            stats["dash"] += 1
            dash_rows.append(r)
            for col in range(1, MAX_FILL_COL + 1):
                if (r, col) in anchors:  # не-якорная ячейка объединения
                    continue
                ws.cell(row=r, column=col).fill = RED_FILL
            continue
        try:
            ws.cell(row=r, column=COL_PRICE).value = float(price)
            stats["numeric"] += 1
        except (TypeError, ValueError):
            stats["no_ref"] += 1
            no_ref_rows.append((r, str(c).strip()))

    wb.calculation.fullCalcOnLoad = True
    wb.save(out_path)
    print("Saved:", out_path)
    print("STATS:", stats)
    print("DASH_ROWS:", dash_rows)
    print("NO_REF:", len(no_ref_rows))
    for r, name in no_ref_rows:
        print(f"  R{r}: {name[:80]}")
    return stats, dash_rows


def verify(vor_path, ref_path, out_path, expected_numeric=None, row_data_end=None):
    """Перечитать результат и сверить с оригиналом и справочником."""
    ref = load_reference(ref_path)
    wb = openpyxl.load_workbook(vor_path, data_only=False)
    ws_o = wb.active
    wb2 = openpyxl.load_workbook(out_path, data_only=False)
    ws = wb2.active
    errs, numeric_count, dash_rows, no_ref_rows, work_filled = 0, 0, [], [], []
    last = row_data_end if row_data_end else ws.max_row
    for r in range(ROW_DATA_START, last + 1):
        a = ws.cell(row=r, column=COL_TYPE).value
        c = ws.cell(row=r, column=COL_NAME).value
        if c is None or str(c).strip() == "":
            continue
        key = norm(c)
        h = ws.cell(row=r, column=COL_PRICE).value
        if a in ("материал", "материалы"):
            if isinstance(h, (int, float)):
                numeric_count += 1
                rp = ref.get(key)
                if rp is None or isinstance(rp, str) or abs(float(rp) - float(h)) > 1e-9:
                    errs += 1
                    print(f"  ОШИБКА R{r}: {h} != справочник {rp!r}")
            elif key in ref and not isinstance(ref[key], str):
                errs += 1
                print(f"  ОШИБКА R{r}: цена не проставлена, в справочнике {ref[key]!r}")
            elif key in ref and isinstance(ref[key], str):
                dash_rows.append(r)
            else:
                no_ref_rows.append(r)
        elif a == "работа" and h is not None and str(h).strip() != "":
            work_filled.append((r, str(c).strip()))
    # структура: объединения
    m_o = sorted(str(m) for m in ws_o.merged_cells.ranges)
    m_n = sorted(str(m) for m in ws.merged_cells.ranges)
    print(f"numeric={numeric_count} dash={len(dash_rows)} no_ref={len(no_ref_rows)} "
          f"work_filled={len(work_filled)} errors={errs}")
    print("merges orig==new:", m_o == m_n, f"({len(m_o)} vs {len(m_n)})")
    print("fullCalcOnLoad:", wb2.calculation.fullCalcOnLoad)
    if expected_numeric is not None:
        print("expected_numeric match:", numeric_count == expected_numeric)
    return errs == 0 and not work_filled


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) < 3:
        print(__doc__)
        sys.exit(1)
    vor, refp, outp = args[0], args[1], args[2]
    verify_only = "--verify-only" in args
    if verify_only:
        verify(vor, refp, outp, row_data_end=ROW_DATA_END)
    else:
        refmap = load_reference(refp)
        st, _ = fill(vor, refmap, outp, ROW_DATA_END)
        verify(vor, refp, outp, expected_numeric=st["numeric"], row_data_end=ROW_DATA_END)
