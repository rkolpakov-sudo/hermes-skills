# Hermes Agent Skills

Коллекция skills для [Hermes Agent](https://hermes-agent.nousresearch.com).  
Каждый skill — автономный модуль знаний: workflow, команды, правила, ссылки для выполнения определённого класса задач (парсинг PDF, код-ревью, генерация отчётов и т.д.).

## Структура

```
skills/
├── <category>/
│   ├── <skill-name>/
│   │   ├── SKILL.md          # описание, шаги, правила
│   │   ├── scripts/           # скрипты для skill
│   │   ├── references/        # справочные файлы
│   │   └── templates/         # шаблоны
│   └── ...
├── .bundled_manifest
├── .curator_ledger.jsonl
└── README.md
```

## Как добавить skill

```bash
mkdir -p skills/<category>/<name>
# создать SKILL.md с YAML frontmatter + markdown телом
# опционально: scripts/, references/, templates/
cd skills && git add -A && git commit -m "feat: add <name> skill"
git push
```

## Использование в других агентах

Любой AI-агент (Claude Code, Codex, OpenCode, Cursor) может загрузить репозиторий и использовать SKILL.md файлы как контекст:

```bash
git clone https://github.com/rkolpakov-sudo/hermes-skills.git
# Далее указать агенту прочитать конкретный SKILL.md:
# - spec-pdf-csv:   PDF спецификация → XLSX
# - github-*:       работа с GitHub
# - email-*:        работа с почтой
# и т.д.
```

## Принципы

- **self-contained** — skill содержит ВСЁ необходимое: процедуры, команды, ссылки, скрипты
- **deterministic** — никаких «подумай сам»; каждый шаг — конкретное действие
- **cost-aware** — перед дорогими операциями (рендер PNG → vision) оценивается ROI
- **flag don't stall** — неразрешимая неоднозначность → флаг в отчёт, не бесконечная верификация