#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_spec_prices.py — заполнение колонки цен спецификации из справочного файла.

Команды:
  fill    заполнить цены и сохранить НОВЫЙ файл (оригинал не трогается)
  verify  проверить заполненный файл против справочника и оригинала

Примеры:
  python fill_spec_prices.py fill "spec.xlsx" "ref.xlsx"
  python fill_spec_prices.py fill "spec.xlsx" "ref.xlsx" --out "out.xlsx"
  python fill_spec_prices.py verify "out.xlsx" "ref.xlsx" --orig "spec.xlsx"

Параметры по умолчанию — структура типового ВОР:
  спецификация:  тип строки в A, наименование в C, цена в G (в ЖК2) / H (в ЖК1) —
                 всегда указывать --price-col;
                 заполняются только типы из --row-types (по умолчанию материал,материалы)
  справочник:    наименование в B, цена в H

Стратегии сопоставления (по порядку, пока не найдено):
  1. direct   — точное совпадение нормализованного имени (пробелы/регистр/ё->е)
  2. manual   — ручная карта цен --manual-map (CSV 'наименование;цена')
  3. strip    — снятие ведущего префикса --strip-prefix (напр. 'Монтаж ')
  4. group    — фрагмент (имя начинается с ⌀/Ø/∅/ø) + имя родителя-группы ':' (--group-prefix)
  5. nospace  — fallback без пробелов (--nospace)

Правила:
  - строки «работа» и прочие типы НЕ заполняются;
  - цена '-'/'—'/'–' в справочнике -> ячейка пустая, строка заливается --dash-color;
  - строки без позиции -> пустые, без заливки;
  - цены копируются как числа без округлений;
  - формулы и объединения сохраняются (data_only=False), fullCalcOnLoad=True.
"""
import argparse
import os
import sys

import openpyxl
from openpyxl.styles import PatternFill

DASH = {"-", "—", "–"}
DIAM = ("⌀", "Ø", "∅", "ø")


def norm(s):
    if s is None:
        return ""
    return " ".join(str(s).split()).lower().replace("ё", "е")


def norm_ns(s):
    if s is None:
        return ""
    return str(s).replace(" ", "").lower().replace("ё", "е")


def parse_price(s):
    return float(str(s).replace(" ", "").replace("\u00a0", "").replace(",", ""))


def parse_col(arg):
    arg = str(arg).strip()
    if arg.isdigit():
        return int(arg)
    n = 0
    for ch in arg.upper():
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def read_manual(path):
    """CSV 'наименование;цена' (utf-8), строки с # игнорируются."""
    manual = {}
    if not path:
        return manual
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, sep, price = line.partition(";")
            if not sep:
                continue
            manual[norm(name)] = parse_price(price)
    return manual


def build_ref(ref_path, ref_name_col, ref_price_col, nospace=False):
    wb = openpyxl.load_workbook(ref_path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    ref, ref_ns = {}, {}
    for r in range(2, ws.max_row + 1):
        name = ws.cell(row=r, column=ref_name_col).value
        if name is None or str(name).strip() == "":
            continue
        key = norm(name)
        if key not in ref:
            ref[key] = ws.cell(row=r, column=ref_price_col).value
        if nospace:
            k2 = norm_ns(name)
            if k2 not in ref_ns:
                ref_ns[k2] = ws.cell(row=r, column=ref_price_col).value
    return ref, ref_ns


def collect_rows(ws, start_row, type_col, name_col):
    """(r, type_key, name, parent_prefix) — parent = ближайшая строка-материал с ':'."""
    out, parent = [], None
    row_types_known = None  # заполняется позже; здесь ловим все строки с именем
    for r in range(start_row, ws.max_row + 1):
        a = ws.cell(row=r, column=type_col).value
        c = ws.cell(row=r, column=name_col).value
        if c is None or str(c).strip() == "":
            continue
        tk = norm(a)
        name = str(c).strip()
        if tk and name.rstrip().endswith(":"):
            parent = name.rstrip()[:-1].strip()
        out.append((r, tk, name, parent if tk else None))
    return out


def resolve(ref, ref_ns, manual, args, name, parent):
    """Возвращает (цена, способ) или (None, None)."""
    key = norm(name)
    if key in ref:
        return ref[key], "direct"
    if key in manual:
        return manual[key], "manual"
    for pfx in args.strip_prefix:
        if name.lower().startswith(pfx.lower()):
            k2 = norm(name[len(pfx):])
            if k2 in ref:
                return ref[k2], "strip:" + pfx
    if args.group_prefix and parent and name.startswith(DIAM):
        full = norm(parent + " " + name)
        if full in ref:
            return ref[full], "group"
    if args.nospace:
        k3 = norm_ns(name)
        if k3 in ref_ns:
            return ref_ns[k3], "nospace"
    return None, None


def default_out(spec_path):
    base, ext = os.path.splitext(spec_path)
    return base + "_с_ценами" + (ext or ".xlsx")


def cmd_fill(args):
    ref, ref_ns = build_ref(args.ref, args.ref_name_col, args.ref_price_col, args.nospace)
    manual = read_manual(args.manual_map)
    row_types = {t.strip().lower() for t in args.row_types.split(",") if t.strip()}

    wb = openpyxl.load_workbook(args.spec, data_only=False)
    ws = wb[wb.sheetnames[0]]
    red_fill = PatternFill(
        start_color="FF" + args.dash_color.upper(),
        end_color="FF" + args.dash_color.upper(),
        fill_type="solid",
    )
    non_anchor = set()
    for m in ws.merged_cells.ranges:
        for row in range(m.min_row, m.max_row + 1):
            for col in range(m.min_col, m.max_col + 1):
                if (row, col) != (m.min_row, m.min_col):
                    non_anchor.add((row, col))

    stats = {"numeric": 0, "dash": 0, "no_ref": 0, "other_skipped": 0, "by": {}}
    dash_rows, no_ref_rows = [], []
    rows = collect_rows(ws, args.start_row, args.type_col, args.name_col)

    for r, tk, name, parent in rows:
        if tk not in row_types:
            stats["other_skipped"] += 1
            continue
        price, how = resolve(ref, ref_ns, manual, args, name, parent)
        if price is None:
            stats["no_ref"] += 1
            no_ref_rows.append(r)
            continue
        if isinstance(price, str) and price.strip() in DASH:
            stats["dash"] += 1
            dash_rows.append(r)
            for col in range(1, 26):
                if (r, col) in non_anchor:
                    continue
                ws.cell(row=r, column=col).fill = red_fill
            continue
        ws.cell(row=r, column=args.price_col).value = parse_price(price)
        stats["numeric"] += 1
        stats["by"][how] = stats["by"].get(how, 0) + 1

    out = args.out or default_out(args.spec)
    wb.calculation.fullCalcOnLoad = True
    wb.save(out)
    print(f"Saved: {out}")
    print(f"STATS: numeric={stats['numeric']} dash={stats['dash']} "
          f"no_ref={stats['no_ref']} other={stats['other_skipped']}")
    print(f"BY_STRATEGY: {stats['by']}")
    print(f"DASH_ROWS ({len(dash_rows)}): {dash_rows}")
    print(f"NO_REF_ROWS ({len(no_ref_rows)}): {no_ref_rows}")


def cmd_verify(args):
    ref, ref_ns = build_ref(args.ref, args.ref_name_col, args.ref_price_col, args.nospace)
    manual = read_manual(args.manual_map)
    row_types = {t.strip().lower() for t in args.row_types.split(",") if t.strip()}

    wb = openpyxl.load_workbook(args.out, data_only=False)
    ws = wb[wb.sheetnames[0]]

    errors, other_filled = [], []
    numeric = dash = no_ref = 0
    dash_red_ok = 0
    rows = collect_rows(ws, args.start_row, args.type_col, args.name_col)

    for r, tk, name, parent in rows:
        h = ws.cell(row=r, column=args.price_col).value
        if tk in row_types:
            price, how = resolve(ref, ref_ns, manual, args, name, parent)
            if isinstance(h, (int, float)):
                numeric += 1
                if price is None or isinstance(price, str):
                    errors.append(f"R{r}: цена {h} но позиции нет в справочнике/карте")
                elif abs(parse_price(price) - float(h)) > 1e-9:
                    errors.append(f"R{r}: цена {h} != ожидаемая {price!r}")
            elif price is not None and isinstance(price, str) and price.strip() in DASH:
                dash += 1
                fill = ws.cell(row=r, column=args.name_col).fill
                if fill is not None and fill.fill_type == "solid" and \
                        str(fill.start_color.rgb).endswith(args.dash_color.upper()):
                    dash_red_ok += 1
                else:
                    errors.append(f"R{r}: цена '-' но строка не залита {args.dash_color}")
            elif price is not None and not isinstance(price, str):
                errors.append(f"R{r}: {name[:50]} цена не проставлена, ожидается {price!r}")
            else:
                no_ref += 1
        else:
            if isinstance(h, (int, float)) and not str(tk).replace(".", "").isdigit():
                other_filled.append((r, name, h))

    print(f"Материал-строк с ценой: {numeric}")
    print(f"С ценой '-' (красных {dash_red_ok}/{dash}): {dash}")
    print(f"Без позиции: {no_ref}")
    print(f"Прочих строк с заполненной ценой: {len(other_filled)}")
    for r, name, h in other_filled[:10]:
        print(f"   R{r}: {name[:60]!r} цена={h!r}")
    print(f"Ошибок сверки: {len(errors)}")
    for e in errors[:40]:
        print("   ", e)

    if args.orig:
        wb_o = openpyxl.load_workbook(args.orig, data_only=False)
        ws_o = wb_o[wb_o.sheetnames[0]]
        m_o = sorted(str(m) for m in ws_o.merged_cells.ranges)
        m_n = sorted(str(m) for m in ws.merged_cells.ranges)
        dim_ok = ws.dimensions == ws_o.dimensions
        merges_ok = m_o == m_n
        print(f"Структура: размер {'OK' if dim_ok else 'ОТЛИЧИЕ ' + ws.dimensions + ' vs ' + ws_o.dimensions}, "
              f"объединения {'OK' if merges_ok else 'ОТЛИЧИЕ ' + str(len(m_o)) + ' vs ' + str(len(m_n))}")
        if not merges_ok:
            print("  только в оригинале:", [x for x in m_o if x not in m_n][:10])
            print("  только в новом:", [x for x in m_n if x not in m_o][:10])
    print(f"fullCalcOnLoad: {wb.calculation.fullCalcOnLoad}")

    if errors or other_filled:
        sys.exit(1)


def add_common(parser):
    parser.add_argument("--type-col", default="A", type=parse_col, help="колонка типа строки (default A)")
    parser.add_argument("--name-col", default="C", type=parse_col, help="колонка наименования (default C)")
    parser.add_argument("--price-col", default="H", type=parse_col, help="колонка цены в спецификации (default H)")
    parser.add_argument("--row-types", default="материал,материалы",
                        help="типы строк, которые заполняются (default 'материал,материалы')")
    parser.add_argument("--ref-name-col", default="B", type=parse_col, help="колонка наименования в справочнике (default B)")
    parser.add_argument("--ref-price-col", default="H", type=parse_col, help="колонка цены в справочнике (default H)")
    parser.add_argument("--dash-color", default="FFC7CE", help="заливка строк с ценой '-' (default FFC7CE)")
    parser.add_argument("--start-row", type=int, default=2, help="первая строка данных (default 2)")
    parser.add_argument("--group-prefix", action="store_true", default=True,
                        help="восстановление фрагментов ⌀/Ø под родителем ':' (default on)")
    parser.add_argument("--no-group-prefix", dest="group_prefix", action="store_false")
    parser.add_argument("--strip-prefix", action="append", default=[],
                        help="ведущий префикс для снятия перед поиском (напр. 'Монтаж '), можно несколько")
    parser.add_argument("--nospace", action="store_true", help="fallback: совпадение без пробелов")
    parser.add_argument("--manual-map", default="", help="CSV 'наименование;цена' для ручных цен")


def main():
    p = argparse.ArgumentParser(description="Заполнение цен спецификации из справочника")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fill", help="заполнить цены и сохранить новый файл")
    pf.add_argument("spec", help="спецификация (ВОР)")
    pf.add_argument("ref", help="справочник с ценами")
    pf.add_argument("--out", help="имя нового файла (по умолчанию <spec>_с_ценами.xlsx)")
    add_common(pf)
    pf.set_defaults(func=cmd_fill)

    pv = sub.add_parser("verify", help="проверить заполненный файл")
    pv.add_argument("out", help="заполненный файл")
    pv.add_argument("ref", help="справочник с ценами")
    pv.add_argument("--orig", help="оригинал спецификации (для сравнения структуры)")
    add_common(pv)
    pv.set_defaults(func=cmd_verify)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
