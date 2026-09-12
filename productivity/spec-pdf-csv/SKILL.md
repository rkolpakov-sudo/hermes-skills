---
name: spec-pdf-csv
description: Convert PDF спецификация to CSV/XLSX (ВК/СО/ОВ). PyMuPDF pipeline.
---

# PDF-спецификация → CSV/XLSX

## Правило исполнения (единственное)

**extract_spec_vk.py OK → сразу XLSX. Перед отправкой — обязательный анализ (п.24-32).**

```bash
# Единственная команда:
python scripts/extract_spec_vk.py <pdf> --out-dir <dir>
# CSV есть → openpyxl → XLSX → доставка
```

⚠ extract_spec.py удалён. Не используется.
validate.py, references/, log-анализ — ТОЛЬКО когда:
- скрипт упал с ошибкой
- records=0
- пользователь явно сказал «проверь»

## Железное правило: обязательный анализ перед выдачей

Перед тем как уведомить пользователя о готовности, провести обязательный анализ:
1. Проверить, что все секции из PDF представлены в XLSX
2. Проверить структуру мать-ребенок: ВК — anchor-группировка (дети с poz='—'), ОВ — flat (без '—' heuristic)
3. Проверить, что нет пустых строк, дублей заголовков, артефактов find_tables
4. Проверить, что поставщик, тип, количество не потеряны
5. Проверить общее количество строк против raw_records: разница должна объясняться MERGE
6. Только после всех проверок — Lark-уведомление

## Iron Law (единственное правило)

**Запрещено** изменять что-либо без обязательного предварительного анализа текущего состояния. Перед любой выдачей результата — анализ всех 6 пунктов выше.

**Запрещено** трогать RFQ_Pipeline. extract_spec.py удалён (не используется).
Любая правка скилла — только с явного подтверждения пользователя.

## Диагностика (читать ТОЛЬКО при проблемах)

| Если проблема | Читать |
|---------------|--------|
| validate не OK (orphans >0) | `references/classification_rules.md` |
| validate не OK (single_letter_tokens >0) | `references/cleaning_rules.md` |
| 0 записей в rows.json (find_tables не сработал) | `references/template_format.md` + detect_template.py |
| validate не OK (необычные ошибки) | `references/pitfalls.md` |
| Повторный прогон того же PDF | `read_file('state.json')` — если там `delivered`, спросить пользователя через clarify |
| Суб-строки комплекта разрезаны (qty/mass размазаны по двум записям) | `references/vk_dash_subitems.md` — постраничная Y-диагностика |

**Не читать все references/ сразу — только один, под проблему.**

## После компактизации

```bash
skill_view(name='spec-pdf-csv')
read_file('state.json')
# продолжить с шага, на котором остановились
```

## Структура директории

```
spec-pdf-csv/
├── SKILL.md                    # этот файл
├── state.json                  # прогресс (создаётся моделью)
├── scripts/
│   ├── extract_spec_vk.py      # основной: координатный (VK) + find_tables fallback (OV)
│   ├── extract_spec_custom.py  # парсер по шаблону (get_text words)
│   ├── detect_template.py      # авто-детект колонок (стадия 0)
│   └── validate.py             # валидатор выхлопа
├── references/
│   ├── cleaning_rules.md       # SPLITS, Ø-артефакт, ГОСТ-ТУ склейка
│   ├── classification_rules.md # MOTHER_ABSORBED, подзаголовки
│   ├── pitfalls.md             # все известные грабли
│   └── template_format.md      # формат шаблона + процедура
└── templates/                  # сохранённые шаблоны
```