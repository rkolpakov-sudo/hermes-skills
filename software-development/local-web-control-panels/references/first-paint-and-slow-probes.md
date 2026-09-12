# First paint vs slow external probes (IMAP / network / subprocess)

Concrete instance: RFQ Control Center, port 8791. All numbers below are measured, not estimated.

## Symptom
User: «От этапа открытия веб интерфейса до этапа загрузки интерфейса проходит не меньше
20 секунд!!!». The page sat on «обновление…» with only static chrome; `#view` (tabs, counters)
appeared after a long wait. `curl` of every endpoint answered in 4–30 ms, so the delay lived in
the JS **init order**, not in any single handler.

## Root cause
```js
// index.html — BEFORE
async function reloadAll(){
  setConn('обновление…',false);
  try{
    await Promise.all([loadConfig(),loadProjects()]);
    await refreshMail(false);        // POST /api/mail/check → himalaya per mailbox
    … render();                      // first paint waited on IMAP
```
```python
# editor_server.py — BEFORE: sequential, one slow account dominates
for field, role in roles:
    r = subprocess.run(["himalaya","envelope","list","--account",acc,"--output","json"],
                       capture_output=True, timeout=45)
```
Measured `POST /api/mail/check`: **66 s** (45 s timeout hit on one mailbox), **43.6 s** with the
force path. Direct `himalaya envelope list --account gmail` on the SAME mailbox: **22.4 s**,
**44.0 s**, and **1.2 s** in a warm/parallel run. Gmail IMAP is intermittently slow — slow is not
broken, and the fix is architectural (async + cache), never “the mailbox is broken”.

## Fix
```js
// JS — paint first, probe after
async function reloadAll(){
  setConn('обновление…',false);
  try{
    await Promise.all([loadConfig(),loadProjects()]);
    const h=new URLSearchParams(location.hash.slice(1)).get('tab');
    if(h&&TABS.some(x=>x[0]===h)) TAB=h;
    setConn('connected',true); render();
    refreshMail(false).catch(()=>{});        // fire-and-forget
  }catch(e){ setConn('нет соединения',false); toast('Не удалось загрузить: '+e,'err'); }
}

async function refreshMail(force){
  if(!force&&MAIL_CACHE){ render(); return; }               // JS-side cache
  const r=await api('/api/mail/check'+(force?'?force=1':''),{method:'POST'});
  MAIL_CACHE=r.body.accounts||[];
  if(TAB==='mail') rMail(); else toast('Ящики проверены','ok');
}
```
```python
# SERVER — TTL cache + parallel probes + timeout above worst latency
MAIL_CACHE = {"data": None, "at": 0.0}
MAIL_TTL = 120

def mail_check(force: bool = False) -> list[dict]:
    import time as _time
    from concurrent.futures import ThreadPoolExecutor
    now = _time.time()
    if not force and MAIL_CACHE["data"] is not None and now - MAIL_CACHE["at"] < MAIL_TTL:
        return MAIL_CACHE["data"]
    …
    def check_one(task):
        acc, email, role = task
        r = subprocess.run(["himalaya","envelope","list","--account",acc,"--output","json"],
                           capture_output=True, timeout=60)   # > measured worst (44 s)
        …
    out = list(ThreadPoolExecutor(max_workers=max(1,len(tasks))).map(check_one, tasks)) if tasks else []
    MAIL_CACHE["data"], MAIL_CACHE["at"] = out, now
    return out

# do_POST
elif path == "/api/mail/check":
    self._json(200, {"accounts": mail_check(force="force=1" in self.path)})
```

## Result
| probe | before | after |
|---|---|---|
| first paint (`#view` populated) | > 20 s (blocked on IMAP) | **< 700 ms** (painted at 600 ms budget) |
| `POST /api/mail/check` cold | 43.6–66 s | 43.6 s — but OFF the critical path (background) |
| `POST /api/mail/check` cached | n/a | **19 ms** |
| `/` , `/api/config` | 4 ms, as before | 4 ms, 28 ms |
| `/api/projects`, `/api/dashboard` | 27 ms, 16 ms | unchanged (lazy per tab) |
| `/api/sites`, `/api/directions` | 248 ms, 228 ms (DB+YAML read) | unchanged — keep lazy, never in init |

## Verification commands
```bash
# endpoint timings
for ep in "" api/config api/projects api/dashboard api/sites; do \
  printf '%-18s ' "/$ep"; curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' "http://127.0.0.1:8791/$ep"; done

# cold vs cached probe
curl -s -X POST -o /dev/null -w '%{time_total}s\n' 'http://127.0.0.1:8791/api/mail/check?force=1'
curl -s -X POST -o /dev/null -w '%{time_total}s\n'  http://127.0.0.1:8791/api/mail/check

# first paint budget ladder (must paint at the LOW budget)
msedge --headless=new --disable-gpu --no-first-run \
  --user-data-dir="$LOCALAPPDATA/Temp/edge_probe" \
  --virtual-time-budget=700 --dump-dom http://127.0.0.1:8791/ | grep -c 'Сводка по контуру'
```
Preferred: `scripts/panel_latency_probe.sh <port> <marker>`.

## Rules distilled
- Init awaits ONLY local, sub-100 ms reads (config file, small artifact JSON).
- Every external probe (IMAP, SMTP, HTTP, subprocess, big scan) is: background-fired from the UI,
  TTL-cached server-side, parallel across accounts, with a `?force=1` path for explicit user action.
- Never shrink the subprocess timeout below the worst measured latency to make things “faster” —
  that only turns a slow success into an error row. Cache + async is the fix; the timeout is a guard.
- Server cache is per-process: a restart re-probes once. Acceptable; do not persist it to disk.
