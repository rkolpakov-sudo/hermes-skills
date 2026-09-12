# Pricer_Vision — Architecture Map (studied 2026-08-21)

Location: `C:\Projects\Pricer_Vision`. PySide6 desktop app for automatic price collection from websites by specification rows (ОВ/ВК/ЭОМ). Core idea: a self-learning LLM browser agent researches a site, finds the price, saves an "approach" (browser-step recipe) into a knowledge graph; recipes are reused on repeat tasks.

## Module map (~23k lines project code, excl. venv/mineru_venv)

### Core (`src/`)
- `agent_loop.py` (~1600 L) — heart: autonomous browser-agent loop over MCP tools. 7 graph tools (get_approaches, save_approach, get_confirmed_prices, save_confirmed_price, search_sites, save_discovered_site, get_hints). Stuck-detector, resilience/backoff, rate-limiter v2 (jitter + per-site overrides + post-block cooldown), human_behavior delays, captcha detection, semantic LLM cache, learning loop on failures. Phase temperatures: exploration/navigation/extraction/recovery.
- `graph_engine.py` (~930 L) — SQLite knowledge graph (`data/pricer.db`): tables approaches, confirmed_prices, hints, product_sites, product_types, sites, matching_equivalences. Approaches carry success/fail counters + deprecation flag; YAML seed from config/categories_and_sites.yaml; caching + rebuild.
- `memory_manager.py` — CRUD layer: save_price, add_hint, save_approach, site priorities (primary/secondary/all), cascade delete.
- `llm_client.py` + `resilience.py` — OpenAI-compatible client with retries.
- `mcp_bridge.py` — bridge exposing external MCP server tools to the agent.
- `study_runner.py` (~700 L) — forced site learning: LLM agent over URL+specification+product type; Qt signals (log, question — agent asks user, approaches, done).
- `approach_relevance.py` — name matching: stopwords, structural words, param words, abbreviations, context rules; configurable via config/matching_rules.yaml + GUI.
- Helpers: excel_writer, task_scheduler, session_cache, column_classifier, site_analyzer, adaptive_limits, validator, tool_parser, audit_logger, theme (dark/light), toast, widget_base, _labels, mcp_agent_runner, config_loader, skip_registry, learning_loop, semantic_cache, rate_limiter, human_behavior, captcha_detector.

### Browser backends
Multi-backend chain: camoufox (default) → playwright (@playwright/mcp via npx) → nodriver (system Chrome). Config `browser.backends` in settings.yaml.

### MCP servers (`mcp_servers/`)
- `browser_server.py` (~830 L) — Playwright tools: navigate, click, type, query_selector, text extraction, screenshots.
- `pricer_server.py` (~340 L) — pricing-domain tools (price extraction, spec matching).

### GUI (`gui/`, `main.py`)
- `graph_assistant.py` (~2000 L) — "Assistant" panel, 11 pages: graph context, approach search, sites, approaches, prices, product types, hints, price correction, Learning (Q&A + checkboxes to confirm proposed approaches/hints/concepts), statistics, help. Global product-type filter syncs all pages.
- `graph_explorer.py` (~1000 L) — interactive graph visualization: custom force-directed physics on numpy in a separate thread (PhysicsWorker, alpha decay, ~150 iterations to stabilize), OpenGL viewport, LOD (>500 nodes → labels/physics off), radial layout around root (products R=220, sites R=350, prices R=480), type filters, JSON export.
- `rules_editor.py` — matching-rules dialog with "Check" tab; `agent_monitor`, `metrics_panel`, `spinner_widget`.

### PDF pipeline (`src/pdf_parser/`)
MinerU (separate `mineru_venv`, CLI `-l east_slavic`) via async subprocess with process-tree kill (`taskkill /T /F` — Windows-deadlock workaround for subprocess timeout); progress parsed from stderr tqdm. OCR fallback = same MinerU (no PaddleOCR). `SpecStructurer`: LLM structuring per GOST 9-column spec + regex fallback (right-to-left scan of qty/unit/weight, ШТ→шт normalization, Latin lookalike normalization). `SmartReview` confidence: name .4 + qty .2 + unit .1 + code/mfg .2 + specs .1, threshold 0.8. `FeedbackCollector`: table pdf_corrections — repeat corrections auto-applied. `ReviewDialog`: low-confidence highlighting, Excel export.

### Dependency manager (`src/dependency_manager/`)
Qt dialog for pip + @playwright/mcp updates: venv discovery (venv/, mineru_venv/), PyPI/npm registry clients, PEP440+semver sorting, browser revision checks (playwright-core browsers.json vs installed chromium-<rev> folders in %LOCALAPPDATA%\ms-playwright; camoufox fetch bundle; nodriver system Chrome). requirements.txt rewrite preserves comments/ordering byte-for-byte; backup `.depsbak.<ts>` + rollback. QThread workers keep UI responsive.

### Configs
`config/settings.yaml` (LLM, browser backends/headless), `config/categories_and_sites.yaml` (~1040 L: schema v2.2, category_map with 7 top categories — cables, plumbing_heating, electrical, ventilation_climate, instruments_automation, fire_safety, tools_general; subcategories → keywords + sites with priority; excluded_sites; hints), `config/matching_rules.yaml` (abbreviations ВГП/ВЧШГ/оц/фл/эс, context-insignificant phrases, param_words pn/kvs/бар…, stopwords, structural words).

### Tests
34 pytest files (~5600 L) covering every core module; conftest fixtures: tmp SQLite DB + built GraphEngine, sample categories YAML (cables→power_cables→tinko.ru primary / keaz.ru secondary), sample approach dict, mock LLM response helpers.

## Known anomalies (as of 2026-08-21)
1. **Dead import:** `src/site_order_dialog.py` imports missing module `src.category_router` (`load_categories_cached`, `save_site_order`) — file absent from disk AND never in git history; nothing imports site_order_dialog itself → unreachable, but crashes if imported.
2. **Uncommitted WIP** (git status): dependency_manager/ (dialog, manager, models, worker), matching_rules.yaml, state.md, tests/test_dependency_manager.py — multi-backend browser feature on top of HEAD `88fecc6` ("LLM token counters in Monitoring tab").

## Git history highlights
Recent commits: LLM token counters; poisoned-price blocking (homepage/search URLs + low-confidence overrides); anti-ban rate limiter v2; ⌀/Ø cache reuse + portable locators across backends; multi-backend browser fixes + GUI backend selector; matching rules config + GUI editor + equivalence learning.
