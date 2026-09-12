# Pricer Vision: движки классификации/детекции и их внешний reuse (2026-09-09)

Разобрано при постройке RFQ-классификатора поверх pricer (задача «классифицировать товары
спецификации как pricer»). Pricer решает ДВЕ разные задачи, не путать:

## 1. «Воздуховод/фасонка vs сантехника» — `src/ductwork_calculator.py`

- `is_ductwork_row(spec_text, product_type=None, spec_context=None) -> bool` — слоёный детектор:
  - Уровень 0 (жёсткие стопы, перекрывают ВСЁ): `_FINISHED_DEVICE_RE` (воздухораспределител|диффузор|решётк|клапан|заслонк|воздухоотводчик — готовые УСТРОЙСТВА, pricer их не считает листовым duct, цена рыночная) и `_PLUMBING_OVERRIDE_RE` (канализаци|полипропилен|ППР|ПВХ|ПНД|PPR|из ПП|чугун|водопровод|отоплен|пластик|переходник|латунн|медн|резьбов|под пайку|приварн|НР|ВР|ВН|«дюйм-кавычка»|сгон|футорк|американк|VTr./VT.|балансировочн|ду N|DN N|G1/|G3/).
  - Уровень 1: детектор 20 типов элементов (`detect_element_type`, иначе 'other' → False).
  - Уровень 2: `_DUCT_CONTEXT_RE` (воздуховод|вентиляц|приточн|вытяжн|круглого|прямоугольн|кругл|`°\s*\d.*R\d`).
  - Уровень 3: `spec_context == "ventilation"` для типов из `_SPEC_CONTEXT_TYPES`.
  - Уровень 4: `transition_mix` (круглое→прямоугольное = только вент).
- Контекст спецификации: `mcp_agent_runner._resolve_spec_context()` (явный → имя файла «вент» → `infer_spec_context(specs)` majority), но ПРИМЕНЯЕТСЯ построчно через вент-СЕГМЕНТЫ (`_spec_context_for_row`), иначе сантех-блок смешанной спеки уходит в duct.
- Внутри применяются `fix_circle_notation()`/`apply_ocr_fixes()` (p125→Ø125 и т.п.) — нормализация ДО regex.
- **Важный нюанс для категоризации (RFQ)**: `_FINISHED_DEVICE_RE` → False у duct-детектора, НО товар всё равно ВЕНТИЛЯЦИОННЫЙ (решётки/диффузоры/клапаны вент). Для категории «Вентиляция» это отдельное правило, не путать с «не duct».

## 2. «Что за товар» — граф: `src/graph_engine.py` `GraphEngine.classify_product_type(spec_text)`

- `spec_lower = text.lower()` (БЕЗ ё→е — если keywords с «е», текст с «ё» не совпадёт).
- Поиск по `keywords` каждой product_type (word-boundary regex), возвращает id типа или 'unknown'.
- Таблица `product_types` в `data/pricer.db`: колонки `id, name, category, keywords, created_at, source`.
  - `category` — верхний уровень: cables | plumbing_heating | electrical | ventilation_climate | instruments_automation | fire_safety | tools_general | **insulation** (отдельная!) | None (пользовательские кастом-типы: ups, terminal_block_dkc…).
  - keywords богатые: ventilation_climate_ventilation ~1174 симв. — но состав марко-ориентирован; ОВ-специфику (конвекторы, K-Flex, SAN-M, WHR/VRF, дымолюки) НЕ покрывает → 'unknown'.
- Пользовательские переклассификации: `set_product_type_override(spec_text, product_type_id)` → таблица оверрайдов, `_get_type_override` срабатывает ПЕРВЫМ (exact по нормализованному spec_text).

## 3. Внешний запуск (вне pricer, для RFQ-скиллов)

```python
import sys; sys.path.insert(0, "C:/Projects/Pricer_Vision")
from src.graph_engine import GraphEngine
from src.ductwork_calculator import is_ductwork_row, _PLUMBING_OVERRIDE_RE  # приватные импортируемы
eng = GraphEngine("C:/Projects/Pricer_Vision/data/pricer.db"); eng.build()
cat = (eng._all_products.get(pt) or {}).get("category")
```
Запускать ИНТЕРПРЕТАТОРОМ venv pricer (`C:/Projects/Pricer_Vision/venv/Scripts/python.exe`).

### ⚠️ ИЗОЛЯЦИЯ: `build()` ПИШЕТ в pricer.db — работать ТОЛЬКО с копией (2026-09-09, требование пользователя «агент не влияет на pricer vision»)

`GraphEngine.build()` при каждом вызове выполняет на переданной БД: `SCHEMA_SQL` (CREATE TABLE IF NOT EXISTS ×11), миграции `ALTER TABLE ADD COLUMN` (consecutive_failures / expires_at / source) и `PRAGMA journal_mode=WAL` + commit — это **реальная запись в файл** (меняет mtime, создаёт -wal/-shm). Передавать оригинал `C:/Projects/Pricer_Vision/data/pricer.db` нельзя: идемпотентность миграций не означает «файл не тронут».

Проверенный шаблон изоляции (rfq_classify_pricer.py): свежая копия БД на каждый запуск в рабочую папку RFQ, движок — на копии:
```python
import shutil
_WORK_DB = Path.home() / ".hermes" / "rfq" / "work" / "pricer_rfq.db"
_WORK_DB.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2("C:/Projects/Pricer_Vision/data/pricer.db", _WORK_DB)  # свежая копия на запуск
eng = GraphEngine(str(_WORK_DB)); eng.build()
```
Прочие чтения pricer: sqlite открывать read-only URI `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`; YAML-таксономию читать из снимка `~/.hermes/rfq/taxonomy/` (не из репозитория pricer). Верификация изоляции — хэши 8 ключевых файлов pricer до/после прогона (`dev/isolation_check.py`: pricer.db, config/*.yaml×3, src/{graph_engine,approach_relevance,ductwork_calculator,config_loader}.py; PASS = ни один не изменён). Важно: модули pricer при ИМПОРТЕ не пишут (approach_relevance module-level только дефолты, config_loader._write_run — только явные save_*), единственный скрытый писатель — `build()`.

## 4. Проверенный порядок слоёв для категоризации товаров спеки (RFQ P1, 87%→95% на «Одинцово вент17.07», 446 строк)

1. `is_ductwork_row(text)` → ventilation_climate/duct;
2. `_PLUMBING_OVERRIDE_RE` → plumbing_heating (ДО duct-формы! «Переход/Тройник стальной Ду…» — сантех, хотя слово-форма общая); подкатегория: graph classify если дал plumbing, иначе pipes_fittings;
3. duct-ФОРМА + размер → ventilation_climate: `_DUCT_PART_RE` (отвод|переход|тройник|заглушк|врезк|воздуховод|адаптер|вставк|зонт|конфузор|колено|муфт|крестовин) И `_DUCT_DIM_RE` (`(пр)|(кр)|кругл|прямоуг|\d+[xх]\d+|p\d{2,3}|°|R\d+|Ø\d+`);
4. вент-устройства (`_VENT_FINISHED_RE`: воздухораспределител|диффузор|решётк|решетк|заслонк|шибер|анемостат) → ventilation_climate/air_distribution;
5. `classify_product_type` → категория из БД;
6. unknown → ручная классификация.

Правило товарности строк: товар = qty непусто ИЛИ role=='component'; строки-описания/матери без qty и заголовки разделов — НЕ товары (остаются в полном отчёте-спецификации).

## 5. Схема rows json (extract_spec.py / pdf2spec)

Поля: `poz, name, type, code, supplier, unit, qty, mass, note, role, page`; роли: item | component | header.
`extract_spec.py` (скилл spec-pdf-csv) пишет `spec_<base>.csv + spec_<base>_rows.json + spec_<base>_log.json` — **XLSX НЕ создаёт** (сборка отдельным шагом, колонки шапки — как в документе). В `_log.json['extract']` — per-page статусы: EMPTY_SKIPPED | NO_SPEC (rejected_scores) | FRAME_SKIPPED | NO_TABLES | успешные (без status) — так видно, на каких листах проекта живёт спецификация (напр. 249-стр. PDF → спека на стр. 37–51, ~20 таблиц с нумерацией 1..N по системам).

## 6. Pitfalls

- НЕ строить keyword-классификатор с нуля по categories_and_sites.yaml — pricer-движки (слои ductwork + граф + оверрайды БД) уже отлажены; reuse > reimplement (требование пользователя).
- Дети строк без имени матери («1177 мм», «16х2,2/15» — pdf2spec v2 местами не наследует) не классифицируются; вход шага 1 должен быть с ПОЛНЫМИ наименованиями (финальный выход extract_spec.py, мать-дети).
- Артефакт склейки колонок: «…(оц. ст. 0.8/R20)огнезащита EI30 5 мм» — суффикс соседней колонки уводит keyword-классификацию в tools_general/«защитные покрытия»; лечится правилом duct-формы ДО keywords.
- «Огнезащита …: мастика/базальт…» без qty = component (материал, расход на м²) — товар в tools_general, но в закупочный файл без количества не идёт.
- Дубли-омонимы: «Клапан обратный» без контекста pricer относит к plumbing valves — приемлемо, контекст системы решает при наличии маркеров.

Рабочие скрипты RFQ-прототипа: `C:\Projects\RFQ_Pipeline\dev\rfq_classify_pricer.py`, `split_by_category.py`, `rows_to_xlsx.py` (до формализации в скиллы пула rfq/*).