#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_spec_custom.py — Парсер спецификации по пользовательскому шаблону.

Использование:
    python extract_spec_custom.py <input.pdf> <template.json> [--out-dir DIR] [--sep ;] [--debug]

Алгоритм:
  1. Загрузка шаблона (страницы, y-окна, колонки).
  2. page.get_text("words") → кластеризация в линии.
  3. Удаление колоночного ряда и футера.
  4. Анкоры по poz-колонке.
  5. Раскладка по колонкам.
  6. Классификация через extract_spec.classify.
"""
import argparse
import csv
import json
import os
import re
import sys

import pymupdf

# ── Импорт общих функций ────────────────────────────────────────────
_extract_spec_dir = os.path.dirname(os.path.abspath(__file__))
_spec_code = open(os.path.join(_extract_spec_dir, 'extract_spec.py'), encoding='utf-8').read()
_ns = {}
exec(compile(_spec_code, 'extract_spec.py', 'exec'), _ns)
classify = _ns['classify']
qa = _ns['qa']
clean_name = _ns['clean_name']
clean_text = _ns['clean_text']

LINE_TOL_DEFAULT = 4.0
COLROW_MIN_DEFAULT = 5


def _cluster_lines(words, y_min, y_max, tol=LINE_TOL_DEFAULT):
    """Кластеризация слов в визуальные линии по y-координате."""
    filtered = [w for w in words if y_min <= w[1] <= y_max]
    if not filtered:
        return []
    filtered.sort(key=lambda w: w[1])
    lines = []
    current_line = [filtered[0]]
    current_y = filtered[0][1]
    for w in filtered[1:]:
        if abs(w[1] - current_y) <= tol:
            current_line.append(w)
        else:
            current_line.sort(key=lambda w: w[0])
            lines.append(current_line)
            current_line = [w]
            current_y = w[1]
    current_line.sort(key=lambda w: w[0])
    lines.append(current_line)
    return lines


def _is_column_row(line, min_count=COLROW_MIN_DEFAULT):
    """Колоночный ряд: ≥min_count одноцифровых слов."""
    single_digit = sum(1 for w in line if re.fullmatch(r'\d', w[4]))
    return single_digit >= min_count


def _is_footer_line(line, footer_keywords):
    """Строка футера (штамп листа)."""
    text = ' '.join(w[4] for w in line).lower()
    return any(kw.lower() in text for kw in footer_keywords)


def _assign_columns(line, columns):
    """Раскладка слов линии по колонкам через x-диапазоны."""
    result = {k: '' for k in columns}
    for w in line:
        x_center = (w[0] + w[2]) / 2
        word = w[4]
        for col_key, (x_lo, x_hi) in columns.items():
            if x_lo <= x_center <= x_hi:
                if result[col_key]:
                    result[col_key] += ' ' + word
                else:
                    result[col_key] = word
                break
    return result


def _detect_anchors(lines, columns):
    """Анкоры: строки с числом в poz-колонке."""
    anchors = {}
    if 'poz' not in columns:
        return anchors
    x_lo, x_hi = columns['poz']
    for i, line in enumerate(lines):
        for w in line:
            x_center = (w[0] + w[2]) / 2
            if x_lo <= x_center <= x_hi and re.match(r'\d{1,4}', w[4]):
                anchors[i] = int(w[4])
                break
    return anchors


def _line_center_y(line):
    if not line:
        return 0
    return sum((w[1] + w[3]) / 2 for w in line) / len(line)


def extract_records(pdf_path, template, debug=False):
    """Извлечение записей по шаблону.

    template — dict с ключами pages, y_windows, columns, line_tolerance,
    column_row_min, footer_keywords.
    Возвращает (records, report, template_name).
    """
    doc = pymupdf.open(pdf_path)
    records = []
    report = []

    pages = template.get("pages", [])
    y_windows = template.get("y_windows", {})
    columns = template.get("columns", {})
    tol = template.get("line_tolerance", LINE_TOL_DEFAULT)
    colrow_min = template.get("column_row_min", COLROW_MIN_DEFAULT)
    footer_kw = template.get("footer_keywords", ["Лист", "Изм.", "Подп.", "Дата"])

    for pno in pages:
        if pno >= len(doc):
            continue
        page = doc[pno]
        words = page.get_text("words")

        # y-окно для страницы
        yw = y_windows.get(str(pno), y_windows.get(pno, None))
        if yw:
            y_min, y_max = yw
        else:
            # Авто: по всем словам
            if not words:
                report.append({"page": pno + 1, "status": "NO_WORDS"})
                continue
            y_min = min(w[1] for w in words)
            y_max = max(w[3] for w in words)

        lines = _cluster_lines(words, y_min, y_max, tol)

        # Удаление колоночного ряда и футера
        lines = [l for l in lines
                 if not _is_column_row(l, colrow_min)
                 and not _is_footer_line(l, footer_kw)]

        # Анкоры
        anchors = _detect_anchors(lines, columns)
        sorted_anchors = sorted(anchors.keys())
        n_lines = len(lines)
        page_records = []

        for idx, line_idx in enumerate(sorted_anchors):
            # Границы интервала
            if idx == 0:
                y_top = y_min
            else:
                prev_y = _line_center_y(lines[sorted_anchors[idx - 1]])
                curr_y = _line_center_y(lines[line_idx])
                y_top = (prev_y + curr_y) / 2

            if idx == len(sorted_anchors) - 1:
                y_bot = y_max
            else:
                next_y = _line_center_y(lines[sorted_anchors[idx + 1]])
                curr_y = _line_center_y(lines[line_idx])
                y_bot = (curr_y + next_y) / 2

            # Собираем слова в интервале
            interval_words = []
            for li in range(line_idx, n_lines):
                if li > line_idx:
                    cy = _line_center_y(lines[li])
                    if cy > y_bot:
                        break
                interval_words.extend(lines[li])

            cols = _assign_columns(interval_words, columns)

            # Фильтрация пустых
            if not any(cols[k] for k in ('name', 'type', 'qty', 'supplier')):
                continue

            rec = {k: cols.get(k, '') for k in ('poz', 'name', 'type', 'code',
                                                   'supplier', 'unit', 'qty', 'mass', 'note')}
            rec['_page'] = pno + 1
            records.append(rec)
            page_records.append(rec)

        report.append({
            "page": pno + 1,
            "words": len(words),
            "lines_filtered": len(lines),
            "anchors": len(anchors),
            "records": len(page_records),
        })

    doc.close()
    return records, report, template.get("name", "custom")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("template")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--sep", default=";")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    # Загрузка шаблона
    tmpl_path = a.template
    if not os.path.exists(tmpl_path):
        # Попытка найти в templates/
        from pathlib import Path
        alt = Path(__file__).resolve().parent.parent / "templates" / tmpl_path
        if not alt.suffix:
            alt = alt.with_suffix(".json")
        if alt.exists():
            tmpl_path = str(alt)
        else:
            print(f"ОШИБКА: шаблон не найден: {a.template}", file=sys.stderr)
            sys.exit(1)

    template = json.loads(open(tmpl_path, encoding="utf-8").read())

    base = os.path.splitext(os.path.basename(a.pdf))[0]
    os.makedirs(a.out_dir, exist_ok=True)
    csv_path = os.path.join(a.out_dir, f"spec_{base}.csv")
    rows_path = os.path.join(a.out_dir, f"spec_{base}_rows.json")
    log_path = os.path.join(a.out_dir, f"spec_{base}_log.json")

    raw_rec, extract_report, tpl_name = extract_records(a.pdf, template, debug=a.debug)
    rows_out, log = classify(raw_rec)

    if a.debug:
        s1 = os.path.join(a.out_dir, f"spec_{base}_stage1_records.json")
        json.dump(raw_rec, open(s1, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"STAGE1: {s1} ({len(raw_rec)} records)")

    issues = qa(rows_out, log)

    # CSV
    HDR_CUSTOM = ["Поз.", "Наименование и техническая характеристика",
                  "Тип, марка, обозначение документа, опросного листа", "Код продукции",
                  "Поставщик", "Ед. измерения", "Кол.", "Масса 1 ед., кг", "Примечание"]
    keys = ["poz", "name", "type", "code", "supplier", "unit", "qty", "mass", "note"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=a.sep)
        w.writerow(HDR_CUSTOM)
        for r in rows_out:
            if r["role"] == "header":
                w.writerow([r.get("poz", ""), r["name"], "", "", "", "", "", "", ""])
            elif r["role"] == "component":
                w.writerow(["", r["name"], r["type"], "", r.get("supplier", ""),
                            "", "", "", r.get("note", "")])
            else:
                w.writerow([r.get(k, "") for k in keys])

    json.dump(rows_out, open(rows_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"extract": extract_report, "log": log, "issues": issues,
               "template": tpl_name},
              open(log_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"PDF:            {a.pdf}")
    print(f"Template:       {tpl_name} (кастомный)")
    print(f"Raw records:    {len(raw_rec)}")
    print(f"Final rows:     {len(rows_out)}  {dict(Counter(r['role'] for r in rows_out))}")
    print(f"CSV:            {csv_path}  ({os.path.getsize(csv_path)} bytes)")
    print(f"LOG:            {log_path}")
    print("ISSUES:")
    for k, v in issues.items():
        print(f"  {k}: {v if v else 'OK'}")


if __name__ == "__main__":
    main()
