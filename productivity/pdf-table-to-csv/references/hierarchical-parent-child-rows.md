# Hierarchical parent-child rows (мать-дети) in engineering specs

Worked out on an ОВ (отопление и вентиляция) specification, 9 rotated landscape sheets,
with ~30 mother groups (конвекторы 16-18 children each, фитинги 7-13, арматура, коллекторы, трубы).

## The mother-child pattern

A **mother row** = full description with EMPTY quantity (e.g. «Конвектор отопительный «Универсал» МКСК…»),
followed by **child rows** = each with a quantity and a short designation (DN15, 400 мм, 20/20, Ø20, 32/25/32).
The mother's name is written ONCE for the whole group and must be propagated to every child.

Rules (verified on real data):
- **Mother with no qty is ABSORBED** — never emitted as its own row.
- **Child with short name + own type** (e.g. «400 мм» + «МКСК20-400К»): `name := mother.name + ' ' + child.name`, `type := child.type` (short name completes the mother's sentence, e.g. «…длиной кожуха: 400 мм»).
- **Child with short name + empty type** (DN15, Ø20, 40 [4]): `name := mother.name`, `type := (mother.type + ' ') + child.name` — the designation goes into «Тип, марка», mother's марка/ГОСТ is prepended so it isn't lost («ГОСТ 3262-75 Ø20», «SAN DPV-30 DN15»).
- **Child with EMPTY name + type + qty** (20/20, 25/15…): `name := mother.name`, `type := own type` (GROUP_INHERIT).
- **Mother WITH quantity** («DN32 Шаровый кран…» qty=3) stays a position AND opens a group — following short rows inherit its name.
- **Continuation rows** (start lowercase: «замкнутым кожухом…», «выполнен из DZR-латуни…») merge into the current mother/position. `mother['name'] += ' ' + name`.
- **Ø/∅/d-prefixed rows (Ø20, d25 (16-18)) are CHILDREN, not continuations** — do NOT include Ø/∅/d in the continuation-prefix list, or sizes accumulate in the mother's name («…труб Ø20 Ø25»).
- **Dash-prefixed rows («- КТР-20», «- дюбель-втулка ДВ-М8»)** are standalone items — capture `was_dash` BEFORE clean (which strips the dash), then treat as plain items, never merge.
- **Structural subheaders ending ':'** («Крепление трубопроводов:») are rows, NOT mothers; their dash-children are standalone items.
- Check the lowercase-continuation branch BEFORE the subheader-with-colon branch — a continuation can legitimately end with ':' («…креплением, с модулем подключения А 22, длиной кожуха:»).

## Lookahead to decide mother vs header

A name-only row with no type and no qty is ambiguous (mother vs group header like «Кран шаровый PN16»).
Look ahead to the FIRST row WITH quantity (skipping continuations without qty and empty-name rows):
- next row short designation → this row is a MOTHER;
- next row starts lowercase → mother (its continuation carries the qty, «мать с количеством»);
- next row is a full named position → this row is a GROUP HEADER (emit as header row, no qty).
Also: the mother can continue ACROSS page boundaries (same name repeated at top of next page — re-register it as the current mother).

## Subheader «1 2 3 4 5 6 7 8 9» bleed
find_tables may fuse the «1 2 3 …» subheader row into the FIRST data row:
- p2: poz='1', name='2 Конвектор…', type='3', qty='7' → strip leading digit from name, zero type/code/qty/supplier;
- p4: name empty, type='2 3', qty='7' → drop the whole row.

## ALL-CAPS section headers
Section titles in caps («СИСТЕМА ОТОПЛЕНИЯ», «АРМАТУРА», «ФИТИНГИ», «СТОЯКИ И МАГИСТРАЛЬНЫЕ ТРУБОПРОВОДЫ», «ТЕПЛОСНАБЖЕНИЕ ПРИТОЧНОЙ УСТАНОВКИ») are not in any prefix list — catch with `name == name.upper()` (Cyrillic, len>4). «ФИТИНГИ» may sit in the TYPE column with empty name → header built from type. «Антикорозионное/Антикоррозионное покрытие…» is a section header too (its children are dash-prefixed standalone items).

## Name/type column splice (merged header page)
On pages with a merged header («Наименование и т…» | «Тип, марка, обозначение ехническая харак»), find_tables splits one logical name cell across name and type columns: «Муфта или муфта редукционная, резь» + «ба внутренняя дюймовая». Rule: if type does NOT match a марка/standard prefix (ГОСТ|ТУ|DN|Dу|Ду|Ø|SAN|K-FLEX|серия|МКСК|…) and has no '='/° — it is a name continuation → splice into name, then fix splice words («резь ба»→«резьба», «авто матический»→«автоматический», «M труб ono»→«Mono»).
Leading size in type of a qty-row («DN20 ono CU, монтаж…») → extract `DN20` as type, rest goes to name.

## Code column lost on pages 2+ (OV)
Two traps when the header says «Код оборудо- вания» (hyphenated):
1. `find('Код оборудования')` misses the line-broken header → search by prefix 'Код'.
2. The skill's `_is_real_row` requires a non-empty poz; on sheets 2+ the poz column is EMPTY → the column-shift heuristic (code in [5] while header says [4]) never fires → codes lost. Fix: local extract_records whose row filter requires only a non-empty name (not a bare digit), then the shift heuristic works.

## QA proof for mother-child runs
Report per-group counts: MOTHER / FULL_NAME_CHILD / GROUP_INHERIT / MOTHER_W_QTY / MERGE / HEADER, plus `items_no_qty = 0` and orphans = 0. Row count sanity: final = items + headers; absorbed mothers legitimately leave «gaps» in позиция numbering.
