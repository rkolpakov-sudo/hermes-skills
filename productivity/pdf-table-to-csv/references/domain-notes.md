# Domain notes: Cyrillic engineering spec tables

Condensed, task-specific knowledge for converting a Cyrillic technical specification
("спецификация оборудования, изделий и материалов") from PDF to clean CSV. Proven on a real
23-page sheet. Read this when working the pipeline in SKILL.md.

## Row classification heuristic (the core of the task)

For each extracted table row, compute `name` (after cleaning) and whether it has a
quantity. Then:

```
has_qty (Кол./unit filled)?
  YES -> ITEM (a real record)
  NO:
    name is a known section phrase?      -> HEADER (keep separate)
    name has its own standard (Тип cell  -> COMPONENT (kit part, keep separate)
      holds ГОСТ/ТУ/марка)?
    else                                  -> CONTINUATION (merge into previous ITEM)
```

- **CONTINUATION** examples: `Ø150х4,5`, `6125х4,5`, `эксцентрический, DN160х110`,
  `с раструбным соединением`, `с фланцевым соединением`, `на гибком шланге`,
  `унитаза Ø110х400мм`.
- **HEADER** examples: `Трубы и изоляция`, `Трубопроводы и изоляция`,
  `Оборудование, фитинги, арматура`, `Сантехническое оборудование (жилье)`,
  `Водопровод`, `Канализация`, and system lines like `Хозяйственно питьевой
  водопровод В1.3`, `Горячее водоснабжение Т3.4`, `Ливневая канализация напорная К2Н`.
  Header test: startswith a section keyword OR matches
  `(водопровод|водоснабжение|канализация)\s*[ВТК]\d` and short (<~75 chars).
- **COMPONENT** examples: `а) Сифон пластмассовый СБУв`, `б) Рукав П (VII)-…`,
  `в) Головка рукавная Ø25 мм`. These belong to a `… компл:` parent but each carries its
  own ГОСТ/ТУ in the Тип column, so they are **their own rows**, not merged text.

The discriminator that separates COMPONENT from CONTINUATION is the presence of a standard
value (ГОСТ/ТУ/марка) in the Тип cell. A bare size/attribute with no standard is a
continuation.

## Ø / diameter symbol corruption (do NOT blind-replace)

The PDF *renders* Ø (or φ), but the **text layer** often carries `6`, `ф`, or `∅` in its
place. Confirmed by codepoints: a cell that looks like `6150х4,5` is actually
`0x36 0x31 0x35 0x30 х 0x34 , 0x35` — an ASCII "6", not Ø. The same doc elsewhere uses a
correct `∅` (`∅100мм`) and real sizes `Ду=65`, `DN50`, `65х15`, proving the "6" prefix is
the mis-mapped Ø, not a digit.

Rule: convert a `6` or `ф` to Ø **only** when it is a leading symbol immediately followed
by a real pipe diameter. Whitelist of diameters (mm): `15 20 25 32 40 50 65 80 100 110
125 150 160 200 219 250 300 400 500 1000`.

Work on **tokens**, not a global regex, so you never corrupt `Ду=65` / `DN160` / `65х15`:

```python
DIAM = {15,20,25,32,40,50,65,80,100,110,125,150,160,200,219,250,300,400,500,1000}
def is_diam(tok):
    m = re.match(r'^(\d+)', tok); return bool(m) and int(m.group(1)) in DIAM

def fix_diam(s):
    toks = s.split(); out = []; i = 0
    while i < len(toks):
        t = toks[i]
        if t == '6' and i+1 < len(toks) and is_diam(toks[i+1]):      # "6 150" -> Ø150
            out.append('Ø' + re.sub(r'\s','',toks[i+1])); i += 2; continue
        if re.match(r'^6\d', t) and is_diam(t[1:]):                 # "6150х4,5" -> Ø150х4,5
            out.append('Ø' + t[1:]); i += 1; continue
        if t.startswith('ф') and re.match(r'ф\d', t) and is_diam(t[1:]):  # "ф110х400мм"
            out.append('Ø' + t[1:]); i += 1; continue
        out.append(t); i += 1
    s2 = ' '.join(out)
    s2 = re.sub(r'Ø\s+(\d)', r'Ø\1', s2)   # "Ø 50" -> "Ø50"
    return s2.replace('∅', 'Ø')            # normalize the correctly-mapped ones too
```

Self-check after running: no output may contain `ØØ`, `Ду=Ø`, `DN1Ø`, `Д=Ø`. Any hit means
a real digit was eaten.

## Word-split artifacts

Extraction inserts spaces inside Cyrillic words. Enumerate the **distinct** name list first,
build the repair pairs from what you actually see, then apply. Common ones observed:

`Труб а→Труба`, `электрос варная→электросварная`, `прямошов ная→прямошовная`,
`оцинков анная→оцинкованная`, `во д огазопров о д ная→водогазопроводная`,
`Гофриров анная→Гофрированная`, `Ги б кая→Гибкая`, `присоед инения→присоединения`,
`Патруб ок→Патрубок`, `переход ной→переходной`, `Трой ник→Тройник`, `О т во д→Отвод`,
`В од омерный→Водомерный`, `К ов ер→Ковёр`, `гиб ком→гибком`, `наружнего→наружного`.

Then a general pass: collapse ` ,`→`,`, `(\d),\s+(\d)`→`\1,\2` (i.e. `6, 0`→`6,0`),
`х\s+(\d)`→`х\1` **only when the х follows a digit** (so `грувлоках 650` keeps its space),
`Д =`→`Д=`, `= (\d)`→`=\1`, `м .`→`м.`, collapse multi-spaces.

**Pitfall**: define the repair list AND make sure the final cleaner actually calls it.
Re-scan the finished CSV for each bad fragment — the leftover count must be zero.

## Rotated landscape sheets

`page.rotation` can be 90 on A2/A3 engineering sheets.
- Data: `page.find_tables().tables[0].extract()` is rotation-aware — use it, not raw words.
- Raw `page.get_text("words")` coordinates are meaningless on rotated pages; don't use them
  to assign cells.
- Vision crops: render `page.get_pixmap(matrix=pymupdf.Matrix(3,3))`, then
  `PIL.Image.rotate(-90, expand=True)`, then crop the band you need.
- The header row tells you the real column order; map columns from header **text**, not by
  fixed index (blank/merged columns shift indices).

## Stray quantities on section headers

On rotated pages, a header row can pick up a qty that belongs to a neighbor
(observed: `Хозяйственно бытовая канализация К1.1 | шт. 9`, `Трубопроводы и изоляция | 61`).
When a row is classified as HEADER but has a qty, **log** it (`HEADER_STRAY_QTY`) and do
NOT emit it as a record. Do not try to "fix" it into the previous item — that qty belongs to
the header's own (mis-bled) cell, not to the data.

## Verification

Run `scripts/qa_scan_csv.py` on the output. It flags double spaces, space-before-punctuation,
naked `Ø` (no digit after), dangling trailing `х`/`=`, and rows with an empty name or (for
items) an empty qty. Expect zero findings on a clean file. Then read the first ~15 rows, one
header-heavy region, and one `компл:` kit region by eye.
