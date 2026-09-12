"""detect_template.py — Авто-детекция шаблона PDF-спецификации.

Скрипт анализирует координаты слов на странице, определяет
границы колонок и y-окно таблицы. Выдаёт JSON шаблона, который
человек подтверждает или корректирует одной фразой.

Использование:
    python detect_template.py <pdf> [--page N] [--tolerance FLOAT]

Вывод:
    JSON с колонками, y-окном и содержимым — готовый шаблон.
    Принимается пользователем → сохраняется в templates/.
    python ... --confirm сразу пишет файл.

Алгоритм:
  1. get_text("words") → слова с координатами
  2. Гистограмма x-пробелов → границы колонок
  3. Анализ содержимого колонок → тип
  4. Кластеризация y → строки, y-window
"""

import argparse, json, os, re, sys
from collections import Counter
import pymupdf

X_GAP = 12.0        # pt — мин. промежуток между колонками
LINE_GAP = 2.0      # pt — макс. разброс y внутри одной строки
TOP_CROP_RATIO = 0.08  # доля верхней части страницы (скип заголовков)
BOTTOM_CROP_RATIO = 0.05  # доля нижней (скип штампа)

# Признаки колонок
def _is_number(t):
    return bool(re.match(r'^[0-9.,\s]+$', t.strip()))

def _is_poz(t):
    return bool(re.match(r'^\d+$', t.strip()))

def _has_unit(t):
    return t.strip() in ('шт', 'м', 'м²', 'м³', 'кг', 'т', 'л', 'компл.', 'компл', 'км')

def _has_row_marker(wx):
    """Слова в левой части страницы (потенциальный poz)"""
    return wx < 120

def _has_code(t):
    """Похоже на код или марку (латиница/цифры без кириллицы)"""
    return bool(re.match(r'^[A-Z0-9/\\-]+$', t.strip())) and len(t.strip()) > 2

def detect(pdf_path, page_no=0, tolerance=None):
    """Авто-детекция шаблона. Возвращает dict с template-полями."""
    doc = pymupdf.open(pdf_path)
    if page_no >= len(doc):
        print(f"Страница {page_no} вне диапазона (всего {len(doc)})")
        sys.exit(1)
    page = doc[page_no]
    words = page.get_text("words")

    if not words:
        print("⛔ На странице нет слов. Страница может быть повёрнута (ОВ?) или сканирована.")
        print("   Для повёрнутых страниц используйте find_tables() — extract_spec.py")
        sys.exit(1)

    # --- Шаг 1: гистограмма x-границ ---
    cols = _detect_columns(words)
    # --- Шаг 2: y-окно ---
    y_win = _detect_y_window(words)
    # --- Шаг 3: содержимое колонок ---
    col_map = _classify_columns(words, cols, y_win)
    # --- Шаг 4: выборка значений ---
    samples = _get_samples(words, col_map, y_win)
    # --- Шаг 5: header_keywords ---
    hdr_kw = _get_header_keywords(words, cols, y_win)

    result = {
        "columns": {k: dict(zip(["x0","x1"], v)) for k,v in col_map.items()},
        "y_windows": {str(page_no+1): y_win},
        "header_keywords": hdr_kw,
        "line_tolerance": tolerance or 4.0
    }
    result["_diagnostic"] = {
        "samples": {k: v for k,v in samples.items() if v},
        "x_histogram": [round(x) for x in _x_histogram(words)],
    }
    return result

def _x_histogram(words, bins=list(range(0,842,20))):  # bin size 20pt
    h = Counter()
    for w in words:
        mid = (w[0]+w[2])/2
        for i,b in enumerate(bins):
            if mid < b:
                h[i] += 1
                break
    return h

def _px():
    """Слова с координатами"""
    pass

def _detect_columns(words):
    """
    Найти границы колонок по x-координатам слов.
    Возвращает список [(x0, x1, примеры_слов), ...].
    """
    # Все x-диапазоны
    ranges = [(w[0], w[2]) for w in words]
    ranges.sort()
    # Слияние соседних/частично перекрывающихся
    merged = []
    cur_x0, cur_x1 = ranges[0]
    for x0, x1 in ranges[1:]:
        if x0 - cur_x1 < X_GAP:
            cur_x1 = max(cur_x1, x1)
        else:
            merged.append((cur_x0, cur_x1))
            cur_x0, cur_x1 = x0, x1
    merged.append((cur_x0, cur_x1))

    # Отбросить очень узкие (артефакты)
    merged = [m for m in merged if m[1]-m[0] > 15]

    return merged

def _detect_y_window(words):
    """Найти y-окно: от первой строки данных до последней."""
    y0_vals = sorted([w[1] for w in words])
    y1_vals = sorted([w[3] for w in words])
    dy = y1_vals[-1] - y0_vals[0]
    top_crop = y0_vals[0] + dy * TOP_CROP_RATIO
    bot_crop = y1_vals[-1] - dy * BOTTOM_CROP_RATIO

    # Ищем первую строку данных (после заголовка) — ищем первую y, где есть цифры?
    # Проще: skip верхние TOP_CROP_RATIO%
    data_y0 = y0_vals[0] + dy * TOP_CROP_RATIO
    data_y1 = y1_vals[-1] - dy * BOTTOM_CROP_RATIO
    return [round(data_y0, 1), round(data_y1, 1)]

def _classify_columns(words, col_ranges, y_win):
    """
    Для каждой найденной колонки определить, на какую маппится:
    poz / name / type / code / supplier / unit / qty / mass / note

    По содержимому слов внутри y-окна.
    """
    y0, y1 = y_win
    labels = {}

    for i, (cx0, cx1) in enumerate(col_ranges):
        # Слова в этой колонке внутри y-окна
        col_words = [w for w in words if w[0] >= cx0 and w[2] <= cx1 and w[1] >= y0 and w[3] <= y1]

        if not col_words:
            labels[str(i)] = (cx0, cx1)
            continue

        # Анализ содержимого
        texts = [w[4] for w in col_words]

        # Числа?
        nums = [t for t in texts if _is_number(t)]
        pozs = [t for t in texts if _is_poz(t)]
        units = [t for t in texts if _has_unit(t)]
        codes = [t for t in texts if _has_code(t)]

        # Если колонка левая (до 120pt) и содержит числа → poz
        if cx0 < 120 and pozs and len(pozs) > len(texts) * 0.5:
            key = "poz"
        elif len(units) > 1 and len(units) > len(texts) * 0.3:
            key = "unit"
        elif len(nums) > len(texts) * 0.6 and not codes:
            key = "qty"
        elif len(codes) > len(texts) * 0.3:
            key = "type"  # коды/марки
        elif sum(len(t) for t in texts) / max(len(texts),1) > 15:
            key = "name"
        else:
            key = f"col_{i}"

        labels[key] = (cx0, cx1)

    return labels

def _get_samples(words, col_map, y_win):
    """Вернуть по 2-3 примера слов из каждой колонки для диагностики."""
    y0, y1 = y_win
    samples = {}
    for key, (cx0, cx1) in col_map.items():
        cw = [w[4] for w in words if w[0] >= cx0 and w[2] <= cx1 and w[1] >= y0 and w[3] <= y1]
        samples[key] = cw[:3]
    return samples

def _get_header_keywords(words, col_ranges, y_win):
    """Извлечь ключевые слова из заголовочной строки."""
    y0, y1 = y_win
    hdr_words = []
    # Слова выше y_win (заголовок)
    top_y = max(y0 - 30, 0)
    for w in words:
        if w[3] <= y0 and w[1] >= top_y:
            hdr_words.append(w[4])

    return hdr_words[:8]  # первые 8 слов

def _confirm_template(tmpl):
    """Вывести на экран готовый шаблон и спросить подтверждение."""
    print("=== ПРЕДЛОЖЕННЫЙ ШАБЛОН ===")
    print(f"Колонки ({len(tmpl['columns'])}):")
    for k, v in tmpl["columns"].items():
        print(f"  {k:12s}: x=[{v['x0']:.0f}..{v['x1']:.0f}]")
    print(f"Y-окно: {tmpl['y_windows']}")
    print(f"Header keywords: {tmpl['header_keywords']}")
    print()
    print("Образцы:")
    for k, v in tmpl["_diagnostic"]["samples"].items():
        print(f"  {k:12s}: {', '.join(v)}")
    print()
    resp = input("Сохранить шаблон? (Y/n): ").strip().lower()
    return resp in ('', 'y', 'yes')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Путь к PDF")
    ap.add_argument("--page", type=int, default=0, help="Страница для анализа (0-indexed)")
    ap.add_argument("--tolerance", type=float, default=4.0, help="Допуск строк (pt)")
    ap.add_argument("--out", default=None, help="Куда сохранить шаблон (если указан, подтверждение не нужно)")
    ap.add_argument("--confirm", action="store_true", help="Спросить подтверждение перед сохранением")
    a = ap.parse_args()

    tmpl = detect(a.pdf, page_no=a.page, tolerance=a.tolerance)

    if a.out:
        dir = os.path.dirname(a.out) or "."
        os.makedirs(dir, exist_ok=True)
        json.dump(tmpl, open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"✅ Шаблон сохранён: {a.out}")
        sys.exit(0)

    if a.confirm:
        ok = _confirm_template(tmpl)
        if not ok:
            print("❌ Отменено пользователем")
            sys.exit(1)
        name = a.pdf.replace(".pdf", "").replace("\\", "_").replace("/", "_")
        out = os.path.join("templates", f"{name}_page{a.page+1}.json")
        os.makedirs("templates", exist_ok=True)
        json.dump(tmpl, open(out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"✅ Шаблон сохранён: {out}")
    else:
        print(json.dumps(tmpl, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()