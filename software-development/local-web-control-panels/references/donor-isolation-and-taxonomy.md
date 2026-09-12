# Donor isolation + taxonomy sourcing (RFQ Control Center instance)

Concrete instance behind the SKILL.md rules. Project: RFQ Pipeline reuses engines from
Pricer Vision (`C:/Projects/Pricer_Vision`). User demand: tool changes must never affect
the donor; and panel taxonomy must come from the donor's authoritative mapping.

## Donor layout (Pricer Vision)

- Categories live in a SQLite DB: `data/pricer.db`, table `categories`
  (id, name, priority, focus) — priority 0..7 (cables 0 … insulation 7).
  `config/categories_and_sites.yaml` has `category_map` with `subcategories.*.name`
  (Russian names) and per-subcategory `sites: [{site, priority}]`. Some DB categories
  (insulation) are absent from the YAML — read BOTH sources and union.
- Engine import path: `sys.path.insert(0, "C:/Projects/Pricer_Vision")` then
  `from src.graph_engine import GraphEngine`, `from src.approach_relevance import …`.

## Taxonomy/directions endpoint recipe (`/api/directions`)

1. Read categories from the donor DB **read-only**:
   `sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)`.
2. Merge subcategory Russian names from the taxonomy YAML snapshot.
3. Overlay the tool's own user-facing direction names from its settings
   (`direction_names`: category_id → «Вентиляция», «Сантехника и отопление (ВК)» …).
4. Compute `classified` counts per category by scanning registered projects' own
   classified json — so «in_projects» is real data, not a guess.
5. Renaming a direction from the UI must (a) update settings `direction_names` and
   (b) migrate the matching supplier-pool key (pool is keyed by the Russian name).

Return shape per category: {id, priority, focus, direction_name, subcategories[],
classified, in_projects, has_suppliers}. List user-defined (non-donor) directions as extras.

## Site assignment overlay (`/api/sites`)

- `base`: per-category sites extracted from the donor taxonomy YAML (read-only display).
- `overlay`: user assignments stored in the TOOL's own file
  (`~/.hermes/rfq/site_overlay.json`) via `save_site_overlay()` — never in the donor.
- Overlay shape: `{category_id: [{site, priority: primary|secondary|all}]}`.
  Server validates domain shape (must contain a dot) and priority enum; UI edits rows
  per category then POSTs the whole overlay; read-back + cleanup verified.

## Isolation evidence (what actually broke and the fix)

1. `rfq_classify_pricer.py` originally did `eng = GraphEngine("…Pricer_Vision/data/pricer.db")`
   then `eng.build()`. `GraphEngine.build()` → `_init_db()` executes `SCHEMA_SQL`
   (CREATE TABLE IF NOT EXISTS) + three guarded `ALTER TABLE ADD COLUMN` migrations +
   `PRAGMA journal_mode=WAL`, then `commit()`. Result: EVERY tool run mutated the donor
   DB file (journal mode rewrite + WAL side files), even though rows were untouched.
   Fix: `shutil.copy2(donor_db, ~/.hermes/rfq/work/pricer_rfq.db)` before constructing
   the engine; all engine-side writes land in the copy.
2. `config/settings.yaml` is only written via explicit `save_run_flags()/_write_run()`
   calls (GUI actions) — module import reads only; verified nobody calls them from tool code.
3. `approach_relevance` import is read-only (loads defaults/rules at module level;
   `save_rules()` is an explicit call never invoked by the tool).
4. Verification script `dev/isolation_check.py`: sha256 of 8 donor files (pricer.db,
   categories_and_sites.yaml, matching_rules.yaml, settings.yaml, src/*.py) BEFORE →
   runs classify (446 rows → 425/21), selfcheck 25/25, settings show → hash AFTER →
   PASS only if identical; also confirm no `pricer.db-wal/-shm` appear next to the donor.

## UI traps hit while building the panel (RFQ Control Center)

- Nav rendered empty on first paint: central `render()` must call `renderNav()` itself,
  not only the tab-click handler (or click handlers on freshly re-rendered nav go stale —
  in the preview pane, re-clicking by ref after re-render can hit the wrong element;
  prefer CSS selector clicks: `#nav button[data-t='projects']`).
- Async render functions that `await loadDirections()/loadSites()` BEFORE setting
  innerHTML leave the previous tab visible on error — surface JS errors in a visible
  `.out` block + `window.addEventListener('error')` toast, then re-check.
- Full element re-inventory after each navigation (`drive_preview` refs rebind).
- After backend patches: kill + relaunch the background server, then hard-reload the page.
