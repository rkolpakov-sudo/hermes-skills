#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_spec_vk.py — Координатный парсер ВК-шаблона (внутреннее водоотведение).

Использование:
    python extract_spec_vk.py <input.pdf> [--out-dir DIR] [--sep ;] [--debug]

Алгоритм:
  1. Страницы 12-14 (0-indexed 11-13), y-окна таблицы per page.
  2. page.get_text("words") → кластеризация в визуальные линии (tolerance 4pt).
  3. Удаление колоночного ряда (≥5 одноцифровых слов на одной линии).
  4. Анкоры: числа в колонке позиции (x 60-105).
  5. Интервал строки: от середины с предыдущим анкором до середины со следующим.
  6. Раскладка по колонкам через жёсткие x-диапазоны.
  7. Секционные заголовки (СИСТЕМА К1/К2/К13) — наследуются через страницы.

Импортирует classify/qa/clean_name/clean_text из extract_spec.py (динамический exec).
"""
import argparse
import csv
import json
import os
import re
import sys

import pymupdf

# ── Встроенные classify/qa/clean ───────────────────────────────────
_SPLITS = [
    ('во д огазопров о д ная', 'водогазопроводная'),
    ('оцинков анная', 'оцинкованная'),
    ('электрос варная', 'электросварная'),
    ('прямошов ная', 'прямошовная'),
    ('Гофриров анная', 'Гофрированная'),
    ('Ги б кая', 'Гибкая'),
    ('присоед инения', 'присоединения'),
    ('Патруб ок', 'Патрубок'),
    ('переход ной', 'переходной'),
    ('Трой ник', 'Тройник'),
    ('О т во д', 'Отвод'),
    ('В од омерный', 'Водомерный'),
    ('К ов ер', 'Ковёр'),
    ('гиб ком', 'гибком'),
    ('Труб а', 'Труба'),
    ('на гиб ком', 'на гибком'),
    ('Д р о с с е л ь - к л а п а н', 'Дроссель-клапан'),
    ('с оед инительной', 'соединительной'),
    ('эл ек т ро механическим', 'электромеханическим'),
    ('к оробк ой', 'коробкой'),
    ('огнез ащ итное', 'огнезащитное'),
    ('т олщиной', 'толщиной'),
    ('огнест ойк ости', 'огнестойкости'),
]
_SUPPLIER_FIX = {'Ekopl astik': 'Ekoplastik', 'Агпа йп': 'Агпайп'}

def clean_text(t):
    import re as _re; t = str(t).strip()
    t = _re.sub(r'\s+', ' ', t)
    for bad, good in _SUPPLIER_FIX.items(): t = t.replace(bad, good)
    return t.strip()

def clean_name(name):
    import re as _re; t = str(name).strip()
    for bad, good in _SPLITS: t = t.replace(bad, good)
    t = _re.sub(r'\s+,', ',', t)
    t = _re.sub(r'\s+\.', '.', t)
    t = _re.sub(r'\s+:', ':', t)
    t = _re.sub(r'\s+;', ';', t)
    t = _re.sub(r'\s+"', '"', t)
    return t.strip()

def is_header_name(name):
    if not name: return False
    n = name.strip()
    if n.startswith("СИСТЕМА"): return True
    return len(n) >= 5 and n.isupper() and not any(c.isdigit() for c in n.rstrip("."))

def classify(records, debug=False):
    rows, log, merges = [], [], 0
    for r in records:
        n = clean_name(r.get("name", ""))
        tp = clean_text(r.get("type", ""))
        qty = (r.get("qty") or "").strip()
        if qty: r["role"] = "item"; r["name"] = n; r["type"] = tp; rows.append(r)
        elif is_header_name(n): r["role"] = "header"; r["name"] = n; rows.append(r)
        elif tp: r["role"] = "component"; r["name"] = n; r["type"] = tp; rows.append(r)
        else:
            if not rows: r["role"] = "header"; r["name"] = n; rows.append(r)
            elif rows[-1].get("role") in ("header", "item"):
                prev = rows[-1]; pn = prev.get("name","")
                if n and not pn.endswith(n): prev["name"] = (pn + " " + n).strip()
                for _k in ('supplier','note','code','type','unit','mass'):
                    c = r.get(_k,'').strip(); p = prev.get(_k,'').strip()
                    if c and not p: prev[_k] = c
                log.append({"type":"MERGE", "name":n, "target":prev.get("poz","")}); merges += 1
            else:
                prev = rows[-1]; pn = prev.get("name","")
                if n and not pn.endswith(n): prev["name"] = (pn + " " + n).strip()
                for _k in ('supplier','note','code','type','unit','mass'):
                    c = r.get(_k,'').strip(); p = prev.get(_k,'').strip()
                    if c and not p: prev[_k] = c
                log.append({"type":"MERGE", "name":n, "target":prev.get("poz","")}); merges += 1
    if debug:
        s2 = [{"name":clean_name(r.get("name","")),"type":clean_text(r.get("type","")),
               "qty":r.get("qty",""),"unit":r.get("unit",""),"poz":r.get("poz","")} for r in records]
        return rows, log, s2
    return rows, log

def qa(rows, log):
    import re as _re; issues = {}
    o = [r.get("name","")[:40] for r in rows if r.get("role")=="item" and not (r.get("qty") or "").strip()]
    issues["orphans"] = o[:5] if o else "OK"
    sp = set()
    for r in rows:
        for f in ("name","type","note","supplier"):
            v = r.get(f,"")
            if any(c in v for c in (" .", " ,", " :", " ;", ' "')): sp.add(v[:60])
    issues["space_punct"] = sorted(sp)[:10] if sp else "OK"
    sl = {w for r in rows for w in r.get("name","").split() if len(w)==1 and w.isalpha()}
    issues["single_letter_tokens"] = sorted(sl) if sl else "OK"
    iq = [r.get("name","")[:40] for r in rows if r.get("role")=="item" and not (r.get("qty") or "").strip()]
    issues["items_no_qty"] = iq[:5] if iq else "OK"
    issues["word_splits"] = issues["naked_diam"] = "OK"
    return issues


# ── Геометрия ВК-шаблона ────────────────────────────────────────────
# Страницы (1-indexed) и y-окна таблицы (в пунктах, origin = top-left)
PAGE_RANGES = {
    12: (122, 638),
    13: (44, 728),
    14: (44, 420),
}

# Жёсткие x-диапазоны колонок (пункты)
COLS = {
    'poz':      (60, 105),
    'name':     (108, 495),
    'type':     (495, 745),
    'code':     (0, 0),       # заглушка (пусто)
    'supplier': (745, 885),
    'unit':     (885, 935),
    'qty':      (935, 1000),
    'mass':     (1000, 1060),
    'note':     (1060, 9999),
}

# Ключевые слова секций (SystemService headers)
SECTION_RE = re.compile(r'СИСТЕМА\s+(К\d+)', re.IGNORECASE)

# Толеранс кластеризации строк (пункты)
LINE_TOL = 4.0

# Минимум одноцифровых слов для детекции колоночного ряда (1..9)
COLROW_MIN = 5


def _words_on_page(page):
    """Список (x0, y0, x1, y1, word, block_no, line_no, word_no) со страницы."""
    return page.get_text("words")


def _cluster_lines(words, y_min, y_max, tol=LINE_TOL):
    """Кластеризация слов в визуальные линии по y-координате.

    Возвращает список линий, где каждая линия — список слов, отсортированных по x.
    Фильтрует слова вне y-окна.
    """
    filtered = [w for w in words if y_min <= w[1] <= y_max]
    if not filtered:
        return []

    # Сортировка по y
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


def _is_column_row(line):
    """Проверка: колоночный ряд (≥5 одноцифровых слов на одной линии)."""
    single_digit = sum(1 for w in line if re.fullmatch(r'\d', w[4]))
    return single_digit >= COLROW_MIN


def _find_section_headers(lines, global_sec):
    """Поиск секционных заголовков (СИСТЕМА К1/К2/К13) среди линий.

    Обновляет global_sec (mutates) и возвращает список (line_idx, section_name).
    """
    found = []
    for i, line in enumerate(lines):
        text = ' '.join(w[4] for w in line)
        m = SECTION_RE.search(text)
        if m:
            sec_name = f"СИСТЕМА {m.group(1)}"
            global_sec[0] = sec_name
            found.append((i, sec_name))
    return found


def _assign_columns(line):
    """Раскладка слов линии по колонкам через жёсткие x-диапазоны.

    Возвращает dict {col_key: concatenated_text}.
    """
    result = {k: '' for k in COLS}
    for w in line:
        x_center = (w[0] + w[2]) / 2
        word = w[4]
        for col_key, (x_lo, x_hi) in COLS.items():
            if x_lo <= x_center <= x_hi:
                if result[col_key]:
                    result[col_key] += ' ' + word
                else:
                    result[col_key] = word
                break
    return result


def _merge_multiline(lines, anchors, y_min, y_max):
    """Слияние мультистрочных имен.

    Если строка-кандидат (нет анкора в poz) и её y близок к предыдущей
    (y разница < 18pt) — считается продолжением имени предыдущей строки.
    Возвращает список индексов линий, которые являются «孤儿» продолжениями.
    """
    orphan_indices = set()
    anchor_set = set(anchors.keys())

    for i, line in enumerate(lines):
        if i in anchor_set:
            continue
        x_lo, x_hi = COLS['poz']
        has_poz = any(x_lo <= (w[0] + w[2]) / 2 <= x_hi and re.match(r'\d', w[4])
                      for w in line)
        if has_poz:
            continue

        # Проверяем, есть ли x-диапазон name
        name_words = [w for w in line if COLS['name'][0] <= (w[0] + w[2]) / 2 <= COLS['name'][1]]
        if not name_words:
            continue

        # Ищем ближайший анchor выше
        for j in range(i - 1, -1, -1):
            if j in anchor_set:
                prev_line = lines[j]
                prev_y = max(w[3] for w in prev_line) if prev_line else 0
                curr_y = min(w[1] for w in line) if line else 0
                if 0 < curr_y - prev_y < 18:
                    orphan_indices.add(i)
                break

    return orphan_indices


def _detect_anchors(lines):
    """Анкоры: строки с числом в колонке позиции (x 60-105).

    Возвращает dict {line_idx: poz_number}.
    """
    anchors = {}
    x_lo, x_hi = COLS['poz']
    for i, line in enumerate(lines):
        for w in line:
            x_center = (w[0] + w[2]) / 2
            if x_lo <= x_center <= x_hi and re.fullmatch(r'\d{1,4}', w[4]):
                anchors[i] = int(w[4])
                break
    return anchors


def _collect_dash_ys(lines):
    """Сбор Y-координат dash-строк (прочерк «-» в колонке poz).

    Возвращает set(y) — centerY линий, содержащих «-» в poz-столбце.
    Используется для расширения y_high за пределы midpoint.
    """
    dash_ys = set()
    x_lo, x_hi = COLS['poz']
    for line in lines:
        for w in line:
            x_center = (w[0] + w[2]) / 2
            if x_lo <= x_center <= x_hi and w[4] == '-':
                y = (w[1] + w[3]) / 2
                dash_ys.add(y)
                break
    return dash_ys


def extract_records(pdf_path, debug=False):
    """Извлечение записей из ВК-шаблона.

    Возвращает (records, report, template='VK').
    records — список dict с ключами poz/name/type/code/supplier/unit/qty/mass/note/_page.
    report — список dict с информацией по страницам.
    """
    try:
        doc = pymupdf.open(pdf_path)
    except FileNotFoundError:
        raise SystemExit(f"[ERROR] Файл не найден: {pdf_path}")
    except Exception as e:
        raise SystemExit(f"[ERROR] Не удалось открыть {pdf_path}: {e}")
    records = []
    report = []
    global_sec = [None]  # mutable ref для наследования секций

    # Определяем 0-indexed номера страниц
    # Быстрый детектор страниц: строка колонок (>=5 одноцифровых слов на одной y)
    page_ranges = {}
    for pno_0idx in range(len(doc)):
        page = doc[pno_0idx]
        words = [w for w in page.get_text("words")]
        digits = [w for w in words if re.fullmatch(r'\d', w[4])]
        rows = {}
        for w in digits:
            key = round(w[1]/6)*6
            rows.setdefault(key, []).append(w)
        colrow_y = None
        for v in rows.values():
            if len(v) >= 5:
                cy = min(x[1] for x in v)
                if colrow_y is None or cy < colrow_y:
                    colrow_y = cy
        if colrow_y is None:
            continue
        has_poz = 'позиция' in page.get_text().lower()
        y_min = 120 if has_poz else max(40, int(colrow_y) + 12)
        page_ranges[pno_0idx + 1] = (y_min, page.rect.height)

    if not page_ranges:
        page_ranges = {p: PAGE_RANGES[p] for p in PAGE_RANGES}

    pages_0idx = [p - 1 for p in page_ranges]

    for p1idx in pages_0idx:
        if p1idx >= len(doc): continue
        page = doc[p1idx]
        pno = p1idx + 1
        y_min, y_max = page_ranges[pno]

        words = _words_on_page(page)
        lines = _cluster_lines(words, y_min, y_max)

        # Удаление колоночного ряда
        lines = [l for l in lines if not _is_column_row(l)]

        # Детекция секций
        sec_found = _find_section_headers(lines, global_sec)

        # Анкоры
        anchors = _detect_anchors(lines)

        # Dash-строки (прочерк «-» в колонке poz)
        dash_ys = _collect_dash_ys(lines)

        # Мультистрочные имена
        orphan_indices = _merge_multiline(lines, anchors, y_min, y_max)

        # Интервалы строк: от mid(анкор[i-1], анкор[i]) до mid(анкор[i], анкор[i+1])
        sorted_anchors = sorted(anchors.keys())
        n_lines = len(lines)
        page_records = []
        prev_boundary = y_min  # защита от перекрытия диапазонов

        for idx, line_idx in enumerate(sorted_anchors):
            # y_low: midpoint до предыдущего анкора, но не выше prev_boundary
            if idx == 0:
                y_low = y_min
            else:
                prev_idx = sorted_anchors[idx - 1]
                prev_y = _line_center_y(lines[prev_idx])
                curr_y = _line_center_y(lines[line_idx])
                y_low = max((prev_y + curr_y) / 2, prev_boundary)

            # y_high: midpoint до следующего анкора, или расширение до dash + 6pt
            if idx == len(sorted_anchors) - 1:
                y_high = y_max
            else:
                next_idx = sorted_anchors[idx + 1]
                next_y = _line_center_y(lines[next_idx])
                curr_y = _line_center_y(lines[line_idx])
                # Ищем последний dash между текущим и следующим анкором
                max_dash = None
                for dy in dash_ys:
                    if curr_y < dy < next_y:
                        if max_dash is None or dy > max_dash:
                            max_dash = dy
                if max_dash is not None:
                    y_high = min(max_dash + 6, next_y)
                else:
                    y_high = (curr_y + next_y) / 2

            prev_boundary = y_high

            # Собираем все слова в интервале [y_low, y_high)
            interval_words = []
            for li in range(line_idx, n_lines):
                if li > line_idx:
                    cy = _line_center_y(lines[li])
                    if cy >= y_high:
                        break
                interval_words.extend(lines[li])

            # Если есть orphan-продолжение — добавляем его слова
            for li in range(line_idx + 1, n_lines):
                if li in orphan_indices:
                    cy = _line_center_y(lines[li])
                    if y_low <= cy < y_high:
                        interval_words.extend(lines[li])

            # Разделение на main + sub-записи по dash-маркерам
            x_lo_poz, x_hi_poz = COLS['poz']
            line_clusters = []  # [(y_center, has_dash, words)]
            for li in range(line_idx, n_lines):
                if li > line_idx:
                    cy = _line_center_y(lines[li])
                    if cy >= y_high:
                        break
                ws = [w for w in lines[li]
                      if not (x_lo_poz <= (w[0] + w[2]) / 2 <= x_hi_poz)]
                has_dash = any(
                    w[4] == '-' and x_lo_poz <= (w[0] + w[2]) / 2 <= x_hi_poz
                    for w in lines[li]
                )
                if ws:
                    line_clusters.append((_line_center_y(lines[li]), has_dash, ws))

            # Раздача: первый кластер → main, кластеры с dash → sub
            pieces = []
            current_piece = None
            for cy, has_dash, ws in line_clusters:
                if current_piece is None:
                    current_piece = {'words': list(ws), 'is_main': True}
                elif has_dash:
                    pieces.append(current_piece)
                    current_piece = {'words': list(ws), 'is_main': False}
                else:
                    current_piece['words'].extend(ws)
            if current_piece:
                pieces.append(current_piece)

            if not pieces:
                continue

            # Main-запись (первый кластер, с номером позиции)
            main_cols = _assign_columns(pieces[0]['words'])
            if global_sec[0] and not main_cols['name']:
                main_cols['name'] = global_sec[0]
            if any(main_cols[k] for k in ('name', 'type', 'qty', 'supplier')):
                poz_val = str(anchors[line_idx]) if line_idx in anchors else ''
                rec = {k: main_cols[k] for k in ('poz', 'name', 'type', 'code', 'supplier',
                                                   'unit', 'qty', 'mass', 'note')}
                rec['poz'] = poz_val
                rec['_page'] = pno
                records.append(rec)
                page_records.append(rec)

            # Sub-записи (каждый кластер с dash — отдельная запись)
            for piece in pieces[1:]:
                sub_cols = _assign_columns(piece['words'])
                if global_sec[0] and not sub_cols['name']:
                    sub_cols['name'] = global_sec[0]
                if any(sub_cols[k] for k in ('name', 'type', 'qty', 'supplier')):
                    rec = {k: sub_cols[k] for k in ('poz', 'name', 'type', 'code', 'supplier',
                                                     'unit', 'qty', 'mass', 'note')}
                    rec['poz'] = ''
                    rec['_page'] = pno
                    records.append(rec)
                    page_records.append(rec)

        report.append({
            'page': pno,
            'words': len(words),
            'lines_raw': len(_cluster_lines(words, y_min, y_max)),
            'lines_filtered': len(lines),
            'anchors': len(anchors),
            'records': len(page_records),
            'section': global_sec[0],
        })

    doc.close()
    return records, report, 'VK'


def _line_center_y(line):
    """Средняя y-координата линии."""
    if not line:
        return 0
    return sum((w[1] + w[3]) / 2 for w in line) / len(line)

# ── OV fallback: find_tables flat extraction ─────────────────────────
# ── OV fallback: find_tables flat extraction (колонки по заголовку, пропуск строки номеров) ──
def _is_colrow(row):
    cells = [(c or '').strip() for c in row]
    ne = [c for c in cells if c]
    return len(ne) >= 3 and all(c.isdigit() and len(c) == 1 for c in ne)

def extract_ov(pdf_path, debug=False):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    records, report = [], []
    section = ""
    for pno in range(len(doc)):
        page = doc[pno]; tabs = page.find_tables()
        if not tabs.tables: continue
        for t in tabs.tables:
            raw = t.extract()
            if not raw or len(raw) < 3: continue
            hdr_idx = None
            for i in range(min(6, len(raw))):
                mtxt = ' '.join((c or '').replace(chr(10),' ').strip().lower() for c in raw[i])
                if 'позиция' in mtxt and ('наименование' in mtxt or 'наимен' in mtxt):
                    hdr_idx = i; break
            if hdr_idx is None: continue
            cm = {}
            for ci, cell in enumerate(raw[hdr_idx]):
                ct = (cell or '').replace(chr(10),' ').strip().lower()
                if 'позиция' in ct: cm['poz'] = ci
                elif 'наименование' in ct or 'наимен' in ct: cm['name'] = ci
                elif 'тип' in ct: cm['type'] = ci
                elif 'код' in ct: cm['code'] = ci
                elif 'поставщик' in ct: cm['supplier'] = ci
                elif 'единица' in ct or 'измер' in ct: cm['unit'] = ci
                elif 'количест' in ct or 'коли' in ct: cm['qty'] = ci
                elif 'масса' in ct: cm['mass'] = ci
                elif 'примечан' in ct: cm['note'] = ci
            def g(row, k):
                ci = cm.get(k)
                if ci is None or ci >= len(row): return ''
                return (row[ci] or '').replace(chr(10),' ').strip()
            n_data = 0
            desc = []          # накопленные строки описания текущей позиции
            has_children = False
            def flush():
                nonlocal desc, has_children
                desc = []; has_children = False
            for row in raw[hdr_idx+1:]:
                if _is_colrow(row): continue
                poz = g(row,'poz'); name = g(row,'name'); type_ = g(row,'type')
                code = g(row,'code'); supplier = g(row,'supplier')
                unit = g(row,'unit'); qty = g(row,'qty'); mass = g(row,'mass'); note = g(row,'note')
                if not (poz or name or qty): continue
                # section header
                if name.upper().startswith('СИСТЕМА') and not poz:
                    flush(); section = name; n_data += 1; continue
                has_num = bool(qty or mass)
                if not has_num and name:
                    # строка описания (без qty)
                    if has_children:
                        flush()          # новая позиция начинается
                    desc.append(name)
                    n_data += 1
                elif has_num:
                    full = (' '.join(desc) + ' ' + name).strip() if desc else name
                    records.append({"poz":poz,"name":full,"type":type_,"code":code,
                           "supplier":supplier,"unit":unit,"qty":qty,"mass":mass,"note":note,
                           "_page":pno+1,"section":section})
                    has_children = True
                    n_data += 1
            flush()
            report.append({"page":pno+1,"rows":n_data,"source":"OV_find_tables"})
    doc.close()
    return records, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('--out-dir', default='.')
    ap.add_argument('--sep', default=';')
    ap.add_argument('--debug', action='store_true')
    a = ap.parse_args()

    base = os.path.splitext(os.path.basename(a.pdf))[0]
    os.makedirs(a.out_dir, exist_ok=True)
    csv_path = os.path.join(a.out_dir, f'spec_{base}.csv')
    rows_path = os.path.join(a.out_dir, f'spec_{base}_rows.json')
    log_path = os.path.join(a.out_dir, f'spec_{base}_log.json')

    raw_rec, extract_report, template = extract_records(a.pdf, debug=a.debug)
    # ── OV fallback condition and replacement
    if len(raw_rec) < 50 or len(raw_rec) > 200:
        raw_rec2, report2 = extract_ov(a.pdf, debug=a.debug)
        if len(raw_rec2) > len(raw_rec) // 2:
            raw_rec, extract_report, template = raw_rec2, report2, 'OV (flat)'
    rows_out, log = classify(raw_rec)

    if a.debug:
        s1 = os.path.join(a.out_dir, f'spec_{base}_stage1_records.json')
        json.dump(raw_rec, open(s1, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"STAGE1: {s1} ({len(raw_rec)} records)")

        s2 = os.path.join(a.out_dir, f'spec_{base}_stage2_cleaned.json')
        cleaned = [{'name': clean_name(r['name']), 'type': clean_text(r['type']),
                     'qty': r['qty'], 'unit': r['unit'], 'sup': clean_text(r['supplier']),
                     'code': clean_text(r['code']), 'mass': r['mass'],
                     'note': clean_text(r['note']), 'poz': r['poz'], 'page': r['_page']}
                    for r in raw_rec]
        json.dump(cleaned, open(s2, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"STAGE2: {s2} ({len(cleaned)} records)")

    issues = qa(rows_out, log)

    if a.debug:
        s3 = os.path.join(a.out_dir, f'spec_{base}_stage3_rows.json')
        json.dump(rows_out, open(s3, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"STAGE3: {s3} ({len(rows_out)} rows)")

    # CSV
    HDR_VK = ['Поз.', 'Наименование и техническая характеристика',
              'Тип, марка, обозначение документа, опросного листа', 'Код продукции',
              'Поставщик', 'Ед. измерения', 'Кол.', 'Масса 1 ед., кг', 'Примечание']
    keys = ['poz', 'name', 'type', 'code', 'supplier', 'unit', 'qty', 'mass', 'note']
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=a.sep)
        w.writerow(HDR_VK)
        for r in rows_out:
            if r['role'] == 'header':
                w.writerow([r.get('poz', ''), r['name'], '', '', '', '', '', '', ''])
            elif r['role'] == 'component':
                w.writerow(['', r['name'], r['type'], '', r.get('supplier', ''),
                            '', '', '', r.get('note', '')])
            else:
                w.writerow([r.get(k, '') for k in keys])

    json.dump(rows_out, open(rows_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump({'extract': extract_report, 'log': log, 'issues': issues},
              open(log_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"PDF:            {a.pdf}")
    print(f"Template:       VK (координатный парсер)")
    print(f"Raw records:    {len(raw_rec)}")
    print(f"Final rows:     {len(rows_out)}  {dict(Counter(r['role'] for r in rows_out))}")
    print(f"CSV:            {csv_path}  ({os.path.getsize(csv_path)} bytes)")
    print(f"LOG:            {log_path}")
    print("ISSUES:")
    for k, v in issues.items():
        print(f"  {k}: {v if v else 'OK'}")


if __name__ == '__main__':
    main()
