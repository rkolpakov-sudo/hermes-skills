# Pricer_Vision — project map (C:\Projects\Pricer_Vision)

Studied 2026-08-21; **refreshed 2026-09-03** (delta + verified test run below). ~23K LOC of project code (plus nested venv: `venv/` — exclude from any find/wc).

## Purpose
PySide6 desktop app for automatic price collection from websites by spec line (сметное дело). LLM agent "studies" sites, finds prices, saves reusable recipes ("подходы"/approaches) into a knowledge graph.

## Core (`src/`) — размеры/состав на 2026-09-09 (ниже по тексту дельты)
- `agent_loop.py` (2799 lines) — heart: autonomous browser-agent loop over MCP tools; монолитный `async process_row()` (~477-1729) с вложенными хелперами; stuck_detector, resilience (retries/backoff), rate_limiter, human_behavior, captcha_detector, semantic_cache, learning_loop, ductwork-контекст.
- `graph_engine.py` (932) — knowledge graph on SQLite (`data/pricer.db`): product types, sites, approaches (browser step recipes with success/failure counters + deprecation flag), confirmed prices, hints for LLM, concept edges (SOLD_AT). YAML seed from `config/categories_and_sites.yaml`, caching, rebuild.
- `memory_manager.py` — CRUD layer: save_price, add_hint, save_approach, product↔site priorities (primary/secondary/all), cascade delete.
- `llm_client.py` + `resilience.py` — OpenAI-compatible API client with retries.
- `mcp_bridge.py` — bridge to external MCP servers, exposing their tools to the agent.
- `study_runner.py` (701) — forced site study: LLM agent by URL+spec+product type; Qt signals (log_signal, question_signal — agent asks user questions, approaches_signal, done_signal).
- `approach_relevance.py` — name matching: stopwords, structural words, params, abbreviations, context rules; configurable via `config/matching_rules.yaml` and GUI.
- Supporting: excel_writer, task_scheduler, session_cache, column_classifier, site_analyzer, adaptive_limits, validator, tool_parser, audit_logger, theme.py (dark/light).

## MCP servers (`mcp_servers/`)
- `browser_server.py` (1208) — Playwright tools: navigate, click, type, query_selector, text extraction/screenshots.
- `pricer_server.py` — **УДАЛЁН** (commit `b45aae4`, dead-code removal); в mcp_servers остался только browser_server.py. AGENTS.md и эта секция до 21.08 его упоминали — не искать.

## GUI (`gui/` + `main.py`, 2739 lines на 2026-09-09; было 1001 на 21.08)
- `graph_assistant.py` (2018) — "Assistant" panel, 11 pages: graph context, approach search, sites, approaches, prices, product types, hints, price correction, Study (Q&A + checkboxes to approve proposed approaches/hints/concepts), stats, help. Global product-type filter syncs all pages.
- `graph_explorer.py` (1013) — interactive graph visualization: custom numpy force-directed physics in a separate thread (PhysicsWorker, alpha decay, ~150-iteration stabilization), OpenGL viewport, LOD (>500 nodes → labels/physics off), radial layout around root (products R=220, sites R=350, prices R=480), type filters, JSON export, info overlay.
- `rules_editor.py` — matching-rules dialog with "Check" tab; agent_monitor, metrics_panel.

## Data/config
`data/pricer.db` (SQLite), `config/settings.yaml` (LLM, browser headless), `config/categories_and_sites.yaml` (product/site seed), `config/matching_rules.yaml`.

## Delta 2026-09-03 → 2026-09-09 (2nd refresh — study again after "серьёзные изменения")

- **pdf2spec v2 IMPLEMENTED (e5325ea 2026-09-03 11:13) — весь PDF2XLSX_REFACTOR_PLAN выполнен в тот же день** (P0-P4, частично P5): `src/pdf2spec/` — clean.py, spec_detect.py, extract.py (PyMuPDF find_tables), row_classify.py, fullname.py (mother-child), qa.py, export_xlsx.py, orchestrator.py (LLM-цикл, runtime_rules в `data/pdf2spec/rules/runtime_rules.json`), runner_v2.py (QThread, сигналы = PdfParserRunner; OCR-маршрут: `_needs_ocr` → MinerU → legacy SpecStructurer → v2 rows). `pymupdf>=1.28.0` добавлен в requirements. На эталоне 3924-2-МСП-РД-ОВ: 161 строка vs Hermes XLSX, 3 матери поглощены.
- **Переключатель**: `config/settings.yaml → pdf_parser.pipeline: v2` (default) | `legacy`; GUI Settings → «Парсер: v2/legacy»; `main.py _load_pdf` → Pdf2SpecRunner | PdfParserRunner. Legacy `src/pdf_parser/` НЕ удалён (бэкап-решение). P6 (чистка) не делалась.
- **Замечание-расхождение (для будущей работы)**: runner_v2 сохраняет Hermes-xlsx (`data/output/spec_<name>.xlsx`) и шлёт items, но main.py `_on_pdf_items_ready` затем всё равно открывает legacy ReviewDialog и пересохраняет через 7-колоночный шим `_save_pdf_items_to_excel` → load_spec. Колонки оригинала (Поставщик/Масса/Примечание) на финальном шаге снова теряются — пункт P2 плана («продукт v2 → штатный load_spec») фактически НЕ выполнен до конца.
- **main.py 1719→2739 строк**: retry single row (ПКМ/кнопка), start-from-row (контекстное меню), пометка «невалидна» (invalid) + «⟳ Перезапустить отмеченные» (очередь retry), upsert по excel_row, сортировка по excel_row везде, dashboard tiles, Material Symbols иконки, компактный monitor, full URL в таблице, `_HAS_V2` guard.
- **gui/**: `reclassify_dialog.py` (редактируемые категории/группы товаров, сплит типов), graph_assistant.py 95→119KB.
- **Агент/ядро (Sep 3-8)**: блокировка маркетплейсов (ozon/wb) как источников цен; только верифицированные цены в reuse/context; price reuse threshold 0.7 descriptive-only; click fast-fail + JS-fallback; cooldown-retry очередь; spec_text в RowFacts; единый captcha-детект + strike-блокировка сайта; антибот: `persistent_profile:true`+`pinned_fingerprint:true`, stealth.js инъекция убрана, disable_coop, camoufox>=0.5.6; max_rounds 25/10; автосохранение кандидата при лимите раундов; нормализация ⌀/p→Ø и p-переходов (ductwork для OCR-спецификаций); ductwork: исключены сантехника/готовые изделия, сегментация смешанных спецификаций по spec_context; исправления сессий (gap-fill, сортировка, corrupted recovery отменён); run.reuse_price вернулся в true.
- **Тесты**: AGENTS.md заявляет 1323 passed 10 skipped; state.md Sep 4: 1274+10; pdf2spec: ~90 unit (8 файлов tests/test_pdf2spec_*.py).
- **Файлы**: PDF2XLSX_REFACTOR_PLAN.md и REFACTORING_PLAN.md — оба в корне, оба закоммичены.
- **state.md 5663→7075 строк; гибридный порядок** — новые записи ПРЕПЕНДЯТСЯ сверху, но блок Sep 3 pdf2spec записан в самом низу файла (6738+) — при чтении «последнего состояния» искать и в начале, и в конце.
- **Мелочи**: в AGENTS.md стр.54 вкраплён мусор «吸收» (китайский символ в описании pdf2spec).

## Coverage note (2026-08-21)
Read line-by-line: all docs (readme 31K, AGENTS.md), configs, git log, entry point, entire `src/`, both MCP servers, entire GUI. NOT read line-by-line: `dependency_manager/` (~1050 lines — npm/pypi/venv managers with worker threads), `pdf_parser/` (~1060 lines — MinerU OCR backend, structurer, review), `tests/` (~2900 lines, ~30 pytest files + integration test_agent_flow.py) — known from imports/structure only.

## Delta 2026-08-21 → 2026-09-03 (refresh: docs/git/hotspot code, NOT full re-read)

- **Branch:** work happens on `fix/revert-to-baseline` (NOT main). HEAD 2026-09-03: `cdfe8fe`. v3 refactor branches (`refactor/v3-phase1/2/3`) abandoned after catastrophic degradation → revert to baseline (state.md 2026-08-30). 88 commits since 2026-08-21, mostly session-restore reliability + agent bug fixes.
- **Size changes:** `agent_loop.py` 1594→2799 (monolithic `async def process_row()` spans ~477-1729 with nested helpers), `main.py` 1001→1719, `graph_assistant.py`→2034, `browser_server.py` 827→1208, `graph_engine.py`→976, `study_runner.py` 701→725.
- **New modules:** `src/mcp_agent_runner.py` (561 — MCPAgentRunner QThread, `run()`→`_run_async()`, row loop with restore/skip/caches, audit_session_id), `session_facts.py` (405 — RowFacts/SessionFacts/StrategyTracker, extended to_prompt_block ~600 tok), `session_manager.py` (Qt-free session save/load JSON `data/sessions/`), `skip_registry.py`, `ductwork_calculator.py` (603 — offline duct pricing, `ductwork.enabled` flag), `llm_providers.py` (450 — provider registry: opencode/routerai/local, factory `create_llm_client`, `/models` fetch), `radiator_section_pricer.py`, `config_loader.py`.
- **Deleted:** `mcp_servers/pricer_server.py` (commit `b45aae4` dead-code removal) — only `browser_server.py` remains. AGENTS.md line about pricer_server is stale.
- **GUI:** new `gui/session_dialog.py` (session picker on startup); `_merge_session_results()` in main.py iterates `_original_restored_results` (immutable snapshot), exact + normalized fallback, used by `_on_all_done` AND `_on_runner_error` (crash-safe merge); runner restores rows by `excel_row` first then spec_text.
- **Key recent fixes:** REFACTORING_PLAN.md all 5 P0-P2 resolved (2026-09-02, commit 31b6f2a); 7 agent bugs B1-B7 (17d5dbc, _last_shown_approach_id → mutable list); session results destroyed on start/stop/crash (4 commits Sep 2-3); poisoned matching_equivalences cleaned (290→0, Sep 1); approach penalty no-op fix; vseinstrumenti type-timeout fix (bracket strip, placeholder, cooldown 900→300).
- **Config now:** `browser.backend: camoufox`, `failover: false` (only primary backend starts), headless:false, reuse_price (цены): user preference toggle in UI; `row_max_seconds: 300`, `row_idle_timeout: 180`, `llm.timeout: 90`. Model chosen in GUI Settings (llm_providers). ductwork.enabled:false default.
- **state.md convention:** entries PREPENDED at top (newest first) — read lines 1-190 for current state, not the tail. 5663 lines.
- **Test baseline (VERIFIED by run 2026-09-03):** `venv/Scripts/python.exe -m pytest -q` → **1146 passed, 2 skipped** in ~114s. Must use venv interpreter (system python lacks pdf-inspector/camoufox). ~50 test files + `tests/integration/test_agent_flow.py`.
- **Open items / context for next work:** success rate 4.88% on 41-row run (2026-09-02) drove REFACTORING_PLAN; cleanups of poisoned prices done (confirmed_prices 348→305 Aug 19, more later); `refactor/v2.0`+ phases tags awaiting user confirmation per commit discipline.

## Классификационные движки (разобрано 2026-09-09; их переиспользует RFQ-пул)

Урок пользователя: НЕ строить наивный keyword-классификатор для товаров спецификации — в pricer уже есть отлаженная детекция «что за товар / воздуховод или сантехника». Внешние потребители подключают pricer как движок (venv + sys.path на репозиторий, read-only `data/pricer.db`), а не копируют логику.

- **`src/ductwork_calculator.py` — `is_ductwork_row(spec_text, product_type, spec_context)`** — многоуровневый вент-детектор: Ур.0 жёсткие стопы `_FINISHED_DEVICE_RE` (воздухораспределител|диффузор|решётк|клапан|заслонк|воздухоотводчик — готовые устройства, НЕ duct-расчёт, но категория вентиляция) и `_PLUMBING_OVERRIDE_RE` (канализаци|полипропилен|ППР|ПВХ|ПНД|PPR|из ПП|чугун|водопровод|отоплен|пластик|переходник|латунн|медн|резьбов|под пайку|приварн|НР|ВР|ВН|дюйм-кавычка|сгон|футорк|американк|разъемн|VTr.|VT.|балансировочн|ду N|DN N|G1/|G3/); Ур.1 детектор 20 типов элементов; Ур.2 исключение сантех-омонимов; Ур.3 `_DUCT_CONTEXT_RE` (воздуховод|вентиляц|приточн|вытяжн|круглого|прямоугольн|кругл|°\d.*R\d) + `product_type`/`spec_context`. Нормализация внутри: `fix_circle_notation`/`apply_ocr_fixes` (p→Ø). `_resolve_spec_context()`/`_spec_context_for_row()` (mcp_agent_runner) — вент-контекст ПОСТРОЧНО по сегментам, не для файла целиком.
- **`graph_engine.py:1014 classify_product_type(spec_text)`** — keyword-матчинг по product_types БД (граница слова `(?<!\w)kw(?!\w)`, keywords через `,;`), сначала пользовательский override (type_overrides в БД). Возвращает id типа; категория — колонка `category` таблицы product_types (ventilation_climate/plumbing_heating/insulation(отдельная!)/cables/electrical/instruments_automation/tools_general/fire_safety + категория NULL у пользовательских). Вернуть категорию: `eng._all_products[pt]['category']`. ВАЖНО: НЕ нормализует ё→е и НЕ знает системный контекст (вент-фасонку «Отвод 300x500» может отдать в plumbing) — поэтому композит: duct-детектор → plumbing-override → duct-форма+размер → graph.
- **Проверенный композит (dev/rfq_classify_pricer.py, 95% на вент-проекте 446 строк):** (1) `is_ductwork_row` → ventilation; (2) `_PLUMBING_OVERRIDE_RE` → plumbing_heating (Ду-стальные переходы/тройники не уходят в tools_general); (3) duct-ФОРМА + размерный маркер (`(пр)|(кр)|кругл|прямоуг|\d+x\d+|p\d{2,3}|°|R\d+`) → ventilation даже при вклеенном суффиксе «…огнезащита EI30» (артефакт склейки колонок pdf); (4) вент-устройства (решётк|диффузор|заслонк|шибер|анемостат) → ventilation; (5) graph classify → категория из БД; (6) unknown → ручная классификация (ask).
- **Вход шага «классифицировать» должен быть rows С полными наименованиями** (final Hermes/pdf2spec-rows с mother-child), иначе дети «400 мм»/«16х2,2/15» без словаря матери неклассифицируемы.
- **RFQ-пул (внешний потребитель):** план `C:\Projects\RFQ_Pipeline\RFQ_PIPELINE_PLAN.md`; dev-скрипты `C:\Projects\RFQ_Pipeline\dev\` (rows_to_xlsx.py, rfq_classify_pricer.py, split_by_category.py, send_rfq_test.py, classify_v0.py — v0 наивный, заменён pricer-движками); тестовый проект `C:\Users\Ruslan\Downloads\projects\Одинцово_вент17.07\` (P1-P2 done 2026-09-09: 95% классификация, 4 письма-запроса отправлены). Таксономия-снапшот: `~/.hermes/rfq/taxonomy/` (categories_and_sites.yaml + user_overlay.yaml).
