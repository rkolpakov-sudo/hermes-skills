#!/usr/bin/env python3
"""
spec_engine.py — универсальный движок PDF-спецификаций.
Механика. Все решения структуры — LLM на основе выхлопа.

Подкоманды:
  probe   <pdf>                  — диагностика: есть ли спецификация
  dump    <pdf> --pages N[,M]    — сырые данные с координатами
  tables  <pdf> --pages N[,M]    — find_tables экстракция
  render  <pdf> --pages N[,M]    — рендер в PNG (без текста)
  build   <rows.json> <out.xlsx> — XLSX из rows

Зависимости: pymupdf, openpyxl
"""
import argparse, csv, json, os, re, sys, math
from collections import Counter
from pathlib import Path

try: import pymupdf
except ImportError: pymupdf = None
try: import openpyxl
except ImportError: openpyxl = None
try: from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
except: pass


# ── Хелперы ──────────────────────────────────────────────────────────

def _page_list(s: str):
    """--pages '1-3,5,7-9' → [0,1,2,4,6,7,8]"""
    result = set()
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            for i in range(int(a.strip()), int(b.strip())+1):
                result.add(i-1)
        else:
            result.add(int(part)-1)
    return sorted(result)


def _get_page(doc, pno):
    if pno < 0 or pno >= len(doc):
        return None
    return doc[pno]


def _line_center_y(line):
    if not line: return 0
    return sum((w[1] + w[3]) / 2 for w in line) / len(line)


# ── PROBE ────────────────────────────────────────────────────────────

def cmd_probe(args):
    if not pymupdf: sys.exit("pymupdf not installed")
    doc = pymupdf.open(args.pdf)
    out = []
    for pno in range(len(doc)):
        page = doc[pno]
        words = page.get_text("words")
        txt = page.get_text().strip()[:200]
        has_text = len(words) > 0
        # признаки спецификации
        full_lower = page.get_text().lower()
        has_spec_header = ('позиция' in full_lower and 'наименование' in full_lower)
        # колоночный ряд цифр
        digits = [w for w in words if re.fullmatch(r'\d', w[4])]
        col_clusters = {}
        for w in digits:
            yk = round(w[1]/6)*6
            col_clusters.setdefault(yk, []).append(w)
        has_colrow = any(len(v) >= 5 for v in col_clusters.values())
        out.append({
            "page": pno+1,
            "words": len(words),
            "has_text": has_text,
            "has_spec_header": has_spec_header,
            "has_colrow": has_colrow,
            "width": round(page.rect.width),
            "height": round(page.rect.height),
            "rotation": page.rotation,
            "preview": txt[:160] if has_text else "(no text layer)"
        })
    doc.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    # Резюме
    total_words = sum(p["words"] for p in out)
    spec_pages = [p["page"] for p in out if p["has_spec_header"] or p["has_colrow"]]
    if spec_pages:
        print(f"=== SPEC_PAGES: {spec_pages} (pages with spec признаки)", file=sys.stderr)
    else:
        print(f"=== SPEC_PAGES: none — спецификация не обнаружена", file=sys.stderr)
        no_text = [p["page"] for p in out if not p["has_text"]]
        if no_text:
            print(f"=== NO_TEXT_PAGES: {no_text} (страницы без текстового слоя)", file=sys.stderr)
    print(f"=== TOTAL_WORDS: {total_words}", file=sys.stderr)


# ── DUMP (слова с координатами, по строкам) ────────────────────────

def cmd_dump(args):
    if not pymupdf: sys.exit("pymupdf not installed")
    doc = pymupdf.open(args.pdf)
    pages_out = []
    for pno in _page_list(args.pages):
        page = _get_page(doc, pno)
        if page is None: continue
        words = page.get_text("words")
        if not words:
            pages_out.append({"page": pno+1, "lines": [], "words": 0})
            continue
        # кластеризация в строки
        words.sort(key=lambda w: (w[1], w[0]))
        lines = []
        cur = [words[0]]
        for w in words[1:]:
            if abs(w[1] - cur[-1][1]) <= 4.0:
                cur.append(w)
            else:
                cur.sort(key=lambda x: x[0])
                lines.append(cur)
                cur = [w]
        cur.sort(key=lambda x: x[0])
        lines.append(cur)
        lines_out = []
        for l in lines:
            line_text = ' '.join(w[4] for w in l)
            words_out = [{"x0":round(w[0],1),"y0":round(w[1],1),"x1":round(w[2],1),"y1":round(w[3],1),"text":w[4]} for w in l]
            lines_out.append({"y_center": round(_line_center_y(l),1), "y_range": (round(l[0][1],1), round(l[-1][3],1)), "text": line_text, "words": words_out})
        pages_out.append({"page": pno+1, "words": len(words), "lines": lines_out})
    doc.close()
    print(json.dumps(pages_out, ensure_ascii=False, indent=1))


# ── TABLES (find_tables) ────────────────────────────────────────────

def cmd_tables(args):
    if not pymupdf: sys.exit("pymupdf not installed")
    doc = pymupdf.open(args.pdf)
    pages_out = []
    for pno in _page_list(args.pages):
        page = _get_page(doc, pno)
        if page is None: continue
        tabs = page.find_tables()
        tables_out = []
        for t in tabs.tables:
            raw = t.extract()
            headers = raw[0] if raw else []
            data = raw[1:] if raw else []
            clean = [[(c or '').replace(chr(10),' ').strip() for c in row] for row in raw]
            tables_out.append({"header": headers, "cols": len(headers), "rows": len(data), "data": clean})
        pages_out.append({"page": pno+1, "tables": tables_out})
    doc.close()
    print(json.dumps(pages_out, ensure_ascii=False, indent=1))


# ── RENDER ────────────────────────────────────────────────────────────

def cmd_render(args):
    if not pymupdf: sys.exit("pymupdf not installed")
    doc = pymupdf.open(args.pdf)
    out_dir = args.out or os.path.dirname(args.pdf)
    os.makedirs(out_dir, exist_ok=True)
    rendered = []
    for pno in _page_list(args.pages):
        page = _get_page(doc, pno)
        if page is None: continue
        pix = page.get_pixmap(matrix=pymupdf.Matrix(args.dpi/72, args.dpi/72))
        fname = os.path.join(out_dir, f"p{pno+1}.png")
        pix.save(fname)
        rendered.append({"page": pno+1, "path": os.path.abspath(fname), "w": pix.width, "h": pix.height})
    doc.close()
    print(json.dumps(rendered, ensure_ascii=False, indent=1))


# ── BUILD XLSX ───────────────────────────────────────────────────────

HDR_NAMES = ['Поз.', 'Наименование и техническая характеристика',
             'Тип, марка, обозначение документа, опросного листа',
             'Код продукции', 'Поставщик', 'Ед. измерения', 'Кол.',
             'Масса 1 ед., кг', 'Примечание']
HDR_KEYS  = ['poz','name','type','code','supplier','unit','qty','mass','note']
HDR_COL_WIDTHS = [8, 48, 28, 12, 14, 10, 10, 14, 18]

HDR_FILL = PatternFill('solid', fgColor='4472C4')
HDR_FONT = Font(bold=True, color='FFFFFF', size=9)
SECTION_FILL = PatternFill('solid', fgColor='D9E2F3')
SECTION_FONT = Font(bold=True, size=9)
CELL_FONT = Font(size=9)
CELL_ALIGN = Alignment(wrap_text=True, vertical='center')
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)

def cmd_build(args):
    if not openpyxl: sys.exit("openpyxl not installed")
    with open(args.rows, 'r', encoding='utf-8') as f:
        rows = json.load(f)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Спецификация'
    # заголовки
    for ci, h in enumerate(HDR_NAMES, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.fill = HDR_FILL
        c.font = HDR_FONT
        c.alignment = CELL_ALIGN
        c.border = THIN_BORDER
    # данные
    for ri, r in enumerate(rows, 2):
        role = r.get('role', 'item')
        vals = [r.get(k, '') for k in HDR_KEYS]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = CELL_FONT
            c.alignment = CELL_ALIGN
            c.border = THIN_BORDER
            if role == 'header':
                c.fill = SECTION_FILL
                c.font = SECTION_FONT
    # ширины
    for ci, w in enumerate(HDR_COL_WIDTHS, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = w
    # заморозка заголовка
    ws.freeze_panes = 'A2'
    wb.save(args.out)
    # CSV тоже
    csv_path = args.out.rsplit('.', 1)[0] + '.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(HDR_NAMES)
        for r in rows:
            vals = [r.get(k, '') for k in HDR_KEYS]
            if r.get('role') == 'header':
                w.writerow([r.get('poz',''), r.get('name',''), '', '', '', '', '', '', ''])
            else:
                w.writerow(vals)
    role_counts = dict(Counter(r.get('role','item') for r in rows))
    print(f"XLSX: {os.path.abspath(args.out)}")
    print(f"CSV:  {os.path.abspath(csv_path)}")
    print(f"Rows: {len(rows)}  {role_counts}")


# ── SPREAD (flat rows from find_tables JSON) ────────────────────────

STAMP_TEXTS = ['Взам. инв.N', 'Подпись и дата', 'Инв.N подл.', 'Изм. Ко', 'Изм. Кол',
               'Спецификация', 'Разработ', 'Провери', 'Н.контр', 'ГИП', 'Формат',
               'Листов', 'Стадия', 'РД', 'Корпус', 'Многоэтажный', 'Лист', 'Копировал']

def cmd_spread(args):
    if not args.tables and not (args.pdf and args.pages):
        sys.exit("Укажите --tables JSON ИЛИ pdf + --pages")
    if args.tables:
        with open(args.tables, 'r', encoding='utf-8') as f:
            raw = f.read()
        # skip pymupdf warning if present
        data = json.loads(raw[raw.find('['):])
    else:
        # run tables inline
        doc = pymupdf.open(args.pdf)
        pages_list = _page_list(args.pages)
        data = []
        for pno in pages_list:
            page = doc[pno]
            tabs = page.find_tables()
            tables_out = []
            for t in tabs.tables:
                raw = t.extract()
                clean = [[(c or '').replace(chr(10),' ').strip() for c in row] for row in raw]
                tables_out.append({"page": pno+1, "data": clean, "cols": max(len(r) for r in clean) if clean else 0})
            if tables_out:
                data.append({"page": pno+1, "tables": tables_out})
        doc.close()
    
    flat = []
    for p in data:
        for t in p.get('tables', []):
            rows_raw = t.get('data', [])
            if not rows_raw:
                continue
            # find header row
            hdr_idx = None
            for i, r in enumerate(rows_raw):
                txt = ' '.join((c or '').lower() for c in r)
                if 'позиция' in txt and 'наименование' in txt:
                    hdr_idx = i; break
            if hdr_idx is None:
                continue
            hdr = rows_raw[hdr_idx]
            col_map = {}  # {col_index: field_name}
            for ci, cell in enumerate(hdr):
                ct = (cell or '').lower()
                if 'позиция' in ct: col_map[ci] = 'poz'
                if 'наименование' in ct or 'наимен' in ct: col_map[ci] = 'name'
                if 'тип' in ct and 'марка' in ct: col_map[ci] = 'type'
                elif 'тип' in ct: col_map[ci] = 'type'
                if 'код' in ct: col_map[ci] = 'code'
                if 'поставщик' in ct or 'завод' in ct: col_map[ci] = 'supplier'
                if 'единица' in ct or 'измер' in ct: col_map[ci] = 'unit'
                if 'количест' in ct or 'коли' in ct: col_map[ci] = 'qty'
                if 'масса' in ct: col_map[ci] = 'mass'
                if 'примечан' in ct: col_map[ci] = 'note'
            # extract data rows
            for ri in range(hdr_idx + 2, len(rows_raw)):  # +2 skips colrow
                cells = rows_raw[ri]
                if not any(c for c in cells): continue
                # skip stamp rows
                if any(c for c in cells if c and any(c.startswith(s) for s in STAMP_TEXTS)): continue
                # skip page number rows (only digits)
                non_empty = [c for c in cells if c and c.strip()]
                if len(non_empty) == 1 and non_empty[0].strip().isdigit(): continue
                rec = {'_page': p.get('page', '?'), '_ri': ri}
                for ci, fname in col_map.items():
                    v = (cells[ci] or '').strip() if ci < len(cells) else ''
                    rec[fname] = v
                flat.append(rec)
    
    out_path = args.out or '-'
    out_text = json.dumps(flat, ensure_ascii=False, indent=1)
    if out_path == '-':
        print(out_text)
    else:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(out_text)
    print(f"Flat records: {len(flat)}", file=sys.stderr)
    # show header keys detected
    keys = set()
    for r in flat: keys.update(k for k in r if k != '_page' and k != '_ri')
    print(f"Columns: {sorted(keys)}", file=sys.stderr)


# ── MAIN ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(prog='spec_engine.py')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_probe = sub.add_parser('probe', help='Диагностика PDF')
    p_probe.add_argument('pdf', help='Путь к PDF')

    p_dump = sub.add_parser('dump', help='Сырые данные с координатами')
    p_dump.add_argument('pdf')
    p_dump.add_argument('--pages', required=True, help='Страницы: 1-3,5,7-9')

    p_tabs = sub.add_parser('tables', help='find_tables экстракция')
    p_tabs.add_argument('pdf')
    p_tabs.add_argument('--pages', required=True)

    p_render = sub.add_parser('render', help='Рендер PNG')
    p_render.add_argument('pdf')
    p_render.add_argument('--pages', required=True)
    p_render.add_argument('--dpi', type=float, default=300)
    p_render.add_argument('--out', '-o', help='Выходная директория')

    p_spread = sub.add_parser('spread', help='Flat rows из find_tables (без эвристик)')
    p_spread.add_argument('--tables', help='JSON из tables команды')
    p_spread.add_argument('pdf', nargs='?', help='PDF (если без --tables)')
    p_spread.add_argument('--pages', help='Страницы для PDF')
    p_spread.add_argument('--out', '-o', help='Выходной JSON (по умолчанию stdout)')

    p_build = sub.add_parser('build', help='XLSX из rows.json')
    p_build.add_argument('rows', help='rows.json')
    p_build.add_argument('out', help='Выходной .xlsx')

    args = ap.parse_args()
    {
        'probe': cmd_probe,
        'dump': cmd_dump,
        'tables': cmd_tables,
        'render': cmd_render,
        'spread': cmd_spread,
        'build': cmd_build,
    }[args.cmd](args)

if __name__ == '__main__':
    main()