# Always-on localhost panel on Windows: detached daemon + watchdog

Session evidence (RFQ Control Center, port 8791, Sep 2026). Everything below was verified
by real tool output, not assumed.

## Symptom chain seen by the user
1. «Веб-интерфейс не загружается. Только футер» — actually TWO servers bound to the same port
   (see the split-brain pitfall in SKILL.md).
2. «Проблема не ушла! В браузере не открывается!!!» — the server process had been killed with the
   turn (`termination_source: process.kill`), so the browser got connection-refused; and the tab
   opened inside an already-MINIMIZED browser window, so nothing visibly happened.
3. «Сервер не запускается по умолчанию, для этого нужно произвести какие-то действия» — the
   first watchdog was registered with `schtasks /create /sc minute /mo 1`, which stops repeating
   after 10 minutes; overnight nothing restarted it.

## Part 1 — detached start (survives the agent turn)
```python
import subprocess, sys
p = subprocess.Popen(
    [sys.executable, "editor_server.py", "--port", "8791"],
    cwd=r"C:\path\to\server",
    creationflags=0x8 | 0x200,          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    stdout=open(r"C:\...\tmp\panel.log", "ab"),
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
)
print("DAEMON_PID=", p.pid)
```
`terminal(background=true)` is NOT a substitute: such processes are Hermes-tracked and reaped
(`exit_code: -15`, `termination_source: process.kill`) when the turn/session cleans up.

## Part 2 — watchdog registered from XML (indefinite repetition)
`schtasks /create /sc minute /mo 1` produces `<Repetition><Interval>PT1M</Interval><Duration>PT10M</Duration></Repetition>`:
repeats for ten minutes, then the trigger is spent. Query evidence from the broken task:
`Time next run: 10.09.2026 9:42:00` (created 09.09 21:35) and a watchdog log with a single line.

Fix = register the XML from `templates/windows-watchdog-task.xml` (UTF-16 + BOM):
```python
with open(task_xml, "w", encoding="utf-16") as f:
    f.write(xml)
```
```bash
schtasks /create /tn MyPanel_Watchdog /xml "C:\...\task.xml" /f
schtasks /query /tn MyPanel_Watchdog /xml | grep -iE "Repetition|Interval|Duration|Trigger"
```
Expected: `<LogonTrigger>`, `<TimeTrigger>` with `<Repetition><Interval>PT1M</Interval></Repetition>`
and **no** `<Duration>` inside the repetition (the `PT10M` in a healthy task belongs to
`<IdleSettings>`, not to the repetition).

`<Command>`: absolute interpreter path, `pythonw.exe` — the task fires every minute and
`python.exe` flashes a black console window on each run. Pick an interpreter that actually has the
panel's dependencies (the session's server needs PyYAML; a bare `python` may resolve elsewhere).

## Part 3 — manual start for the user
`.bat` (double-click friendly, idempotent, leaves no console holding the server):
```bat
@echo off
chcp 65001 >nul
title Control Panel
cd /d C:\path\to\server
"C:\path\to\venv\Scripts\pythonw.exe" "C:\path\to\port_watchdog.py" --server-dir "C:\path\to\server" --port 8791
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8791
exit
```
Also tell the user the two other ways: `schtasks /run /tn MyPanel_Watchdog`, or Task Scheduler →
the task → Run.

## Verification transcript (do this, don't claim it)
```bash
PID=$(netstat -ano | grep ":8791" | grep LISTENING | awk '{print $5}' | tr -d '\r' | head -1)
taskkill -F -PID $PID                      # NOTE: //F //PID fails in git-bash; single dash/slash works
curl -s -o /dev/null -w "%{http_code}\n" --max-time 3 http://127.0.0.1:8791/   # expect 000
sleep 75                                                                        # let the task fire
netstat -ano | grep ":8791" | grep LISTENING                                    # a NEW pid
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8791/                 # expect 200
tail -3 ~/.hermes/tmp/panel_watchdog.log                                        # new "port dead - starting" line
```
A sleeping or powered-off machine does not run the task (`WakeToRun=false`); on wake,
`StartWhenAvailable=true` fires it and the panel is back within a minute — say this to the user
instead of pretending it is instantaneous.

## Also observed
- `Cache-Control: no-cache, no-store, must-revalidate` on HTML/JSON: without it a browser keeps
  serving the previous broken page and the user reports «проблема не ушла» after a real fix.
- The user's browser is not necessarily the one you test with (Yandex vs Edge). Launching the URL in
  a Chromium browser already running minimized opens a tab the user cannot see — bring the window
  forward, or state which window to look at.
- `taskkill /F /PID` on a PID that `tasklist`/`wmic` cannot see (process from another session) still
  kills it, as long as the PID comes from `netstat -ano`.
