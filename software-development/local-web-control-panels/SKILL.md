---
name: local-web-control-panels
description: Build localhost settings/control-panel web UIs for tools.
version: 1.0.0
---

# Local web control panels for agent tools

Build a browser-based settings editor / control center for a CLI-ish agent toolchain,
without any framework: a Python stdlib `http.server` on 127.0.0.1 + one HTML/JS page
that auto-renders a form from a JSON schema and shows LIVE data from the tool's
real artifacts. Verified pattern: RFQ Control Center (`C:/Projects/RFQ_Pipeline/editor`,
port 8791) — see `references/rfq-control-center.md` for the concrete instance.

## When to use
- User wants to change tool settings (emails, paths, thresholds, cron) WITHOUT editing code.
- User wants a dashboard over the tool's real state (projects, offers, prices, mail, cron).
- Any "make an editor/settings page for our agent" request.

## Architecture (proven shape)

1. **Config module is the single source of truth** (e.g. `rfq_settings.py`):
   - `SCHEMA`: dict group → field → {label, type: str|email|int|float|bool|select|textarea|path|map, options, default, hint, readonly}. Flat field keys.
   - `DEFAULTS` = current real values. `load()` merges file over DEFAULTS. `save()` validates types/email/select/map and writes file.
   - Tool scripts import `load()` instead of hardcoding addresses/paths/thresholds — no code edits needed by user afterwards.
   - Never store credentials in settings: only himalaya account NAMES + emails; passwords stay in himalaya config / `.env`.
2. **Server** (`editor_server.py`): `ThreadingHTTPServer` bound to `127.0.0.1` only.
   - `GET /api/config` → {groups, fields, values}; `PUT /api/config` → validate+save, return 422 with per-field `errors`.
   - Side-effect actions as separate POST endpoints (`/api/mail/check`, `/api/cron/run`, `/api/lark/test`, `/api/matcher/test`).
   - Apply side effects (cron edit/pause/resume via `hermes cron …`) ONLY when the relevant fields actually changed — compare `old = load()` BEFORE `save()`, not after.
   - Aggregate endpoints (`/api/dashboard`, `/api/projects`) read real project artifacts (rfq_state.json, sent_log, offer_*.json, fill_report.json) — never fake numbers.
   - CORS headers (`Access-Control-Allow-Origin: *` + methods incl. OPTIONS) are REQUIRED when the page may open inside the Hermes desktop preview pane (different origin than 127.0.0.1). Handle `do_OPTIONS`.
3. **Frontend** (single `index.html`): dark card UI, tab nav, form inputs generated from schema fields, "map" fields (direction→emails) as editable rows with comma-split values, live preview (template placeholders), per-action result `<pre class=out>` blocks.

## UX requirement (user standard — hard lesson)
A "settings editor" that shows ONLY editable fields and no real data is rejected as
«корявый, неполный, кастрированный, нефункциональный». The panel MUST include:
- Overview tab with live counters read from real artifacts (projects, rows, classified,
  sent, offers, priced) and mode/schedule badges.
- Per-project drill-down (stage progress bar s1–s6, sent log, offers, fill report, files) as expandable `<details>`.
- Working actions with visible output: check mailboxes (IMAP counts), run cron now,
  test Lark, live matcher test (real engine call), path-exists check.

## First paint must NEVER wait on slow external I/O (hard lesson)
User check (verbatim): «От этапа открытия веб интерфейса до этапа загрузки интерфейса
проходит не меньше 20 секунд!!!». Root cause was ONE line in the init chain:

```js
await Promise.all([loadConfig(), loadProjects()]);
await refreshMail(false);   // ← POST /api/mail/check → himalaya per mailbox → 22–44 s on Gmail
… render();                 //   first paint waited for IMAP
```

Every endpoint measured fast in isolation (4–30 ms by `curl`), which sends the first
diagnosis astray: the delay is the init ORDER, not any single handler. Same mailbox measured
**22.4 s / 44.0 s / 1.2 s** across runs — slow ≠ broken, benchmark before concluding.
Fix, all five parts:
1. **Paint first, probe later.** `await` only local sub-100 ms reads, then `render()` +
   `setConn('connected',true)`; fire the slow probe WITHOUT await
   (`refreshMail(false).catch(()=>{})`) and let it repaint when it lands.
2. **Server-side TTL cache** for every expensive probe (IMAP, network, subprocess):
   `CACHE = {"data": None, "at": 0.0}` + `TTL = 120`; return cached payload when fresh.
   Measured: 43.6 s cold → **19 ms** cached.
3. **Explicit force path** so the «проверить сейчас» button still gets fresh data:
   JS appends `?force=1`; server does `mail_check(force="force=1" in self.path)` and skips the
   cache. The silent background call stays on the cached path.
4. **Probe external accounts in PARALLEL** (`ThreadPoolExecutor`) and set the subprocess timeout
   ABOVE the worst measured latency (60 s here) — sequential probing summed the per-account
   timeouts. A hanging probe must degrade to an error row in the UI, never block the page.
5. **JS-side cache** (`if(!force && CACHE){ render(); return; }`) so tab switches don't re-probe.

Verify by measurement, not by eye: `msedge --headless=new --disable-gpu
--virtual-time-budget=700 --dump-dom http://127.0.0.1:<port>/` then grep a known content marker
(«Сводка по контуру»); present ⇒ the UI paints inside the budget. Ladder the budget (600 → 1500 ms)
to bound it, and re-time the endpoints with `%{time_total}`.
Detail + code + numbers: `references/first-paint-and-slow-probes.md`.
Re-runnable probe: `scripts/panel_latency_probe.sh`.

## Per-entity config fields belong INLINE on every visible entity, same tab
When the panel manages a list of entities (sites per category, suppliers, mailboxes)
and each entity carries its own config (email, priority, enabled), the config input must
sit ON EACH tile of the list the user is looking at — NOT only on a secondary
"assigned/your items" column after some drag-drop. User check (verbatim): «Почему нет
настроек email в той же вкладке как я приказал?» — email fields existed only on
*dragged-to-pool* tiles; the base catalog tiles (the ones actually visible) had none.
Fix pattern: every tile = `[⠿ site-name] [email input] [✕]`; typing a value on a base
tile UPSERTS the entity into the user overlay (pool) automatically; clearing it removes
it. One canonical place per entity for the value, never two (edit-in-both-columns confuses).

## Chip/tile list layout — three rejected attempts, one working pattern
User iterated three times on domain-name chips:
1. `white-space:nowrap; text-overflow:ellipsis; max-width:210px` → «Наименования
   сайтов обрезаются» — truncation rejected.
2. `overflow-wrap:anywhere` (wrap) → «Длинные домены переносятся на другую строку и
   увеличивают вертикальный размер плиток» — wrapping rejected.
3. Shrinking font to 10.5px to force fit → «Откатить! Вернуть размеры шрифта!» — font
   shrink rejected.
WORKING: keep the original font size; name = `white-space:nowrap; overflow:visible;
flex:0 0 auto` (chip `flex-wrap:nowrap`) so the chip grows HORIZONTALLY to the domain
length; widen the column enough for the longest name + controls (~370px for
name+email+priority+✕ at 12.5px). Constant vertical size, nothing truncated, nothing
wrapped. Names were ≤17 chars ≈ 105px — measure the longest before fixing widths.

## Donor catalog lists: merge ALL donor sources, not just the first found
Building a "base/catalog" list (sites per category, etc.) from a donor project: the
taxonomy YAML is NOT complete by itself. Categories `fire_safety`/`tools_general` exist
in the YAML but carry NO `sites:` section; `insulation` is absent from the YAML entirely
— their sites live ONLY in the donor DB (`product_types→product_sites→sites`). Symptom:
«Категория не имеет доменов, хотя в pricer vision БД есть!». Fix: union YAML +
DB-join, dedupe by entity keeping the BEST (lowest-rank) priority. Priority mapping is
in the donor code, not assumed: `{primary:0, secondary:1}.get(p, 2)` (0=primary,
1=secondary, anything else=all). DB rows are dirty: strip protocol/paths/annotations
with a domain regex (`https://proconsim.ru`→`proconsim.ru`, `вентиляция-топ
(ventilyacia-top.ru)`→`ventilyacia-top.ru`). Detail: `references/sites-data-merge.md`.

## Reference sections: source from the donor's AUTHORITATIVE mapping, not generated sets
User check (verbatim): «Раздел „Направления, встречающиеся в проектах“ не доработан!
Не извлечены направления из маппинга pricer vision, а сгенерирован базовый набор!»
When the panel shows taxonomy/directions/categories/sites that conceptually belong to a
donor project the tool borrows engines from:
- Read the donor's real sources: DB tables (categories) + taxonomy YAML (subcategory names)
  + user-facing naming overlay — NOT file names derived from project artifacts.
- Merge into one endpoint (`/api/directions`) with priority, id, direction name, subcategories,
  and per-project classified counts so «есть в проектах» is computed, not assumed.
- Show base (donor) data read-only + a separate user overlay; label both with their file paths.
  Persist user edits in the overlay file only — never into the donor.

## Donor isolation (hard requirement for engine-reuse tools)
If the tool imports engines from another project (Pricer Vision etc.), the user demands
proof that tool changes «не влияют и не могут повлиять» on the donor. Two traps found:
1. **Engine constructors/build() can WRITE to the donor DB.** `GraphEngine(path).build()`
   ran `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` migrations + `PRAGMA journal_mode=WAL`
   on the ORIGINAL donor db on every classifier run (mtime moved, file mutated even though
   migrations were idempotent). Fix: copy the donor DB fresh into the tool's own work dir
   (`~/.hermes/rfq/work/pricer_rfq.db`, `shutil.copy2` per run) and point the engine there.
2. **Panel readers can open the donor DB writable.** Fix: sqlite connect with read-only URI
   `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
Audit method: grep tool code for donor paths AND write verbs (`write|open(.*[wa]|save|insert|
update|delete|PRAGMA|commit`) — the only allowed hits are `sys.path.insert` and reads.
Prove it: hash donor files (db, config yaml, src) BEFORE → run the real operations
(classify, matcher, selfcheck, settings save) → hash AFTER → all must match; also check no
WAL/SHM files appeared next to the donor db. This session's checker: `C:/Projects/RFQ_Pipeline/dev/isolation_check.py` (PASS = donor untouched).
Detail: `references/donor-isolation-and-taxonomy.md`.

## Always-on panel: it must SURVIVE the agent session (detached daemon + Windows watchdog)
A localhost panel the user relies on is worthless if it dies with the turn. Hard lesson:
`terminal(background=true)` server processes are tracked by Hermes and killed when the
session/turn cleans up (`exit_code: -15`, `termination_source: process.kill`). Symptom from the
user: «Сервер не запускается по умолчанию» / «Браузер ничего не показывает, почини порт!» —
while YOUR `curl` from the shell returns 200. Three-part fix (all verified in production):

1. **Start the server DETACHED** — never `background=true` for a panel the user needs:
   ```python
   subprocess.Popen([sys.executable, "editor_server.py", "--port", "8791"],
                    cwd=SERVER_DIR, creationflags=0x8 | 0x200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                    stdout=open(LOG, "ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
   ```
   It then outlives the shell/turn and is invisible to `process_manage`.
2. **Watchdog keeps the port alive** — `scripts/port_watchdog.py` (quiet: silent if the port
   answers, else relaunches the server detached + one log line) registered via
   `templates/windows-watchdog-task.xml`.
3. **Idempotent `.bat` for manual start** — call the watchdog (starts the server only if dead),
   `timeout /t 2 /nobreak >nul`, `start "" http://127.0.0.1:<port>`, `exit`. The launcher must
   NEVER leave a console window holding the server.

### schtasks trap that silently kills the watchdog
`schtasks /create /sc minute /mo 1 /tr "python wd.py"` looks right and ISN'T: it creates a
ONE-TIME TimeTrigger whose `<Repetition>` carries a **limited `<Duration>PT10M</Duration>`** —
the task repeats for ~10 minutes then stops (query then shows the next run *the next day*, e.g.
`10.09.2026 9:42:00`), and the watchdog log holds exactly one entry forever. Register from XML:
```xml
<Triggers>
  <LogonTrigger><Enabled>true</Enabled><UserId>S-1-5-21-…</UserId><Delay>PT15S</Delay></LogonTrigger>
  <TimeTrigger><StartBoundary>2026-09-09T21:35:00</StartBoundary><Enabled>true</Enabled>
    <Repetition><Interval>PT1M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
  </TimeTrigger>
</Triggers>
```
- **No `<Duration>` inside `<Repetition>` = indefinite repeats** (this is the whole fix).
  LogonTrigger ⇒ the panel returns after every reboot/login (15 s delay lets the desktop settle).
- `<Command>` must be an **absolute interpreter path**: a bare `python` resolves via the user PATH
  to whatever it finds (possibly an interpreter missing the panel's deps, e.g. PyYAML), and prefer
  **`pythonw.exe`** — the task fires every minute, `python.exe` flashes a console window each time.
- The task XML must be written **UTF-16 with BOM** (`open(p, "w", encoding="utf-16")`) or
  `schtasks /create /xml` refuses it.
- Plus `IgnoreNew` multiple-instances policy, `StartWhenAvailable=true`, battery flags off.
- **Verify for real:** kill the listener by netstat PID, wait ~75 s, assert a NEW watchdog log line
  AND `curl` 200 — no manual `schtasks /run`. A sleeping/off machine doesn't run the task: the panel
  comes back within a minute of wake (expected, tell the user).

### Also do this
- Send `Cache-Control: no-cache, no-store, must-revalidate` (+`Pragma`, `Expires: 0`) on panel
  HTML/JSON — otherwise the browser cheerfully serves the previous, broken version and the user
  says «проблема не ушла» after your fix.
- **"Fixed" is not a message, it's a state:** exactly ONE listener on the port + auto-restart in
  place + the page actually opened on the URL. Open it yourself:
  `cmd /c start "" "C:\Program Files\Yandex\YandexBrowser\Application\browser.exe" http://127.0.0.1:8791/`
  (a Chromium browser often opens the tab inside an existing MINIMIZED window — the user sees
  "nothing happened"; bring the window forward or say which window to look at).
- The user's browser may not be the one you test with (they used Yandex while tests ran on Edge).
  Render-check headlessly AND look at the user's actual window (windows-mcp Snapshot/Screenshot).
  Detail + full recipe: `references/windows-alwayson-server.md`.

## Pitfalls (all hit in production)
- **Stale server answers after a restart — kill by PORT, not by PID bookkeeping.**
  After patching editor_server.py, relaunching can leave TWO processes LISTENING on the
  same port (old one still bound); requests hit the OLD code, so "fix applied but curl
  still shows old data" (dirty domains persisted past the fix). Verify with
  `netstat -ano | grep :8791`, `taskkill /F /PID <each>`, relaunch ONCE, then re-curl
  and assert the NEW behavior (not just HTTP 200). On git-bash use `taskkill /F /PID`
  (single slash); `taskkill //F //PID` fails with "неверный параметр" — MSYS mangles
  double-slashes here.
- **TWO listeners on one port = request split-brain: "only footer renders" even with
  clean JS.** Worse symptom than stale data: each browser fetch (/api/config, /api/sites,
  /api/dashboard…) is routed to a RANDOM one of the two listeners, and the old process
  hangs (e.g. IMAP call blocking on a dead connection — server log shows
  `ConnectionAbortedError` mid-handler). Some fetches never resolve → the JS init
  `await` chain stalls → only the static header/footer paint, tabs/`#view` stay empty.
  Diagnostic order when a page shows only chrome and everything else looks fine:
  (1) `node --check` on the extracted <script> — syntax OK doesn't rule this out;
  (2) `netstat -ano | grep :<port> | grep LISTENING` — TWO PIDs = the cause, regardless
  of code correctness; (3) kill EVERY listener PID (old ones may be invisible to
  `tasklist`/`wmic` from another session — `taskkill /F /PID` by the netstat PID still
  works), relaunch ONCE, re-curl all endpoints and assert fast responses
  (`%{time_total}`), then reload the page. Prevention: before every relaunch, check the
  port is free — never stack a second server on purpose.
- **Headless-browser error probe for "blank page" debugging.** When the in-app preview
  can't surface JS console errors: temporarily inject
  `<script>window.addEventListener('error',e=>{try{document.title='JSERR: '+(e.message||e.error)+' @'+e.lineno+':'+e.colno}catch(_){}});window.addEventListener('unhandledrejection',e=>{try{document.title='JSPROM: '+String(e.reason)}catch(_){}})</script>`
  before `</head>`, then `msedge --headless --disable-gpu --virtual-time-budget=6000
  --dump-dom http://127.0.0.1:8791/` and read the `<title>`: `JSERR:`/`JSPROM:` names the
  failure; unchanged title = no JS error (suspect server/network, see split-brain above).
  Remove the probe afterwards. Caveat: locating `#view` content by a strict
  `</div></main>` regex can false-negative "empty view" on valid nested HTML — search for
  a known content marker string (e.g. a stat label) instead. `--enable-logging=stderr`
  console output is drowned in Edge oneauth noise — the title-probe is the clean channel.
- **JS init order kills the whole page silently.** Calling `buildGroups()`/`Object.keys(SCHEMA)`
  before `await load()` finished → `Object.keys(null)` TypeError → script dies → ONLY the static
  header/footer render. Symptom looks like a network/CORS problem but is a JS runtime error.
  Fix: `buildGroups()` inside `load()` after schema arrives; init = `try { await load() } catch(e){…}`.
  Also: the central `render()` must call `renderNav()` itself — nav was empty on first paint
  because only the tab-click handler did.
- **Schema-rendered toggle/switch fields overlap their label text** («переключатели
  налезают на другой текст»). Root cause is CSS specificity, not layout intent: the
  generic input rule `.field label{display:block}` (0,1,1) outranks
  `.toggle{display:inline-flex}` (0,1,0), so the toggle `<label>` is forced block — and
  the knob `<span>` was inline so its 42×23px width/height were IGNORED entirely.
  Fix: render bool fields as a DEDICATED flex row, not the generic text-input wrapper:
  `<div class="field sw"><label>Подпись</label><label class="toggle"><input…><span class="knob"></span></label>…</div>`
  with `.field.sw{display:flex;align-items:center;gap:14px;flex-wrap:wrap}`,
  `.field.sw>label{flex:1 1 60%;margin:0}`,
  `.field.sw label.toggle{display:inline-flex;flex:0 0 auto}` (0,2,1 now wins),
  `.field.sw .hint{flex-basis:100%}`, and `.knob{display:inline-block}` so its fixed
  size actually applies. A `border-top` separator + `:first-of-type{border-top:none}`
  makes consecutive switches read as clean rows. One fix in mkField + CSS covers every
  bool field on every tab.
- **Python `set` is not JSON-serializable.** Matcher/classifier internals return sets in
  result dicts → wrap responses in a `_conv()` that converts set→sorted list before `json.dumps`.
- **git-bash curl sends Cyrillic bodies as cp1251/cp866, not UTF-8** → `UnicodeDecodeError` on
  the server. Parse `_body()` with fallback chain utf-8 → cp1251 → cp866.
- **tomllib for himalaya config**: accounts live in NESTED `[accounts.<name>]` sections —
  read `data.get("accounts", {})`, not top-level keys.
- **Verify HTML served fully**: `curl -o file` then `wc -c`/grep (native curl cannot write to
  MSYS `/tmp` — use a Windows path); `-o /dev/null -w size_download` misreports 0 bytes.
- Extract the `<script>` block and run `node --check` on it — cheap syntax gate before
  opening the browser.
- `.bat` launcher must `chcp 65001` and start the page AFTER the server (or the first
  browser load 404s; reload fixes).

## Verification
- `curl /api/config`, PUT valid + PUT invalid (expect 422 with field errors).
- Hit every POST action endpoint via Python `urllib` (UTF-8 body) — curl body encoding is unreliable for Cyrillic.
- Render check in the Hermes desktop preview pane (desktop_preview open + drive_preview
  elements/read) — it exercises CORS + real DOM. Nav tabs present = init OK.
- **Checkboxes inside toggles are `display:none`, so they NEVER appear in the AX
  elements dump** — absence of the checkbox in the inventory is not proof the toggle is
  missing. Verify bool fields by the surrounding `<label>` text (visible in read/elements)
  plus the `.field.sw`/`.knob` DOM, and keep `node --check` on the extracted <script> as
  the syntax gate.
- After any backend change: kill EVERY listener on the port (netstat PID) and relaunch the server
  DETACHED (`background=true` processes get killed with the turn — see «Always-on panel»), then
  re-curl and assert the NEW behavior, not just HTTP 200.
- **Page-load latency gate:** run the headless budget ladder + content marker
  (`scripts/panel_latency_probe.sh`) — the panel must paint under ~1 s. If it paints only at the
  high budget, some init step is awaiting slow external I/O (see «First paint must NEVER wait…»).
