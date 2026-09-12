#!/usr/bin/env python3
"""Hermes Desktop -> Feishu/Lark outbound bridge daemon (persistent).

Watches state.db for NEW FINAL assistant messages in the CURRENTLY ACTIVE
desktop session (resolved dynamically each cycle) and forwards them to the
Feishu home channel via the IM API.

- Dynamic session resolution: most recent live (ended_at IS NULL)
  source='desktop' session by last_activity_at. Survives chat switches and
  compaction chains.
- Only final responses are forwarded: role='assistant' with non-empty content
  and finish_reason != 'tool_calls' (intermediate thinking/tool-call frames
  are skipped).
- Dedup: per-session cursor (max forwarded message id) persisted in state
  file. First run for a NEW session pins the cursor to the last qualifying id
  and sends NOTHING -> never floods Lark with history.
- Gateway auto-delivery dedup: turns whose user message appears in
  gateway.log as `platform=feishu ... msg=...` are skipped (the gateway
  delivers those replies to Lark itself).

Run:  pythonw bridge_daemon.py            (persistent, logs to logs/bridge.log)
      python bridge_daemon.py --once      (one cycle, print to stdout)
      python bridge_daemon.py --test-outbound "text"
Autostart: Hermes_Bridge.vbs in the Windows Startup folder, mirroring
Hermes_Gateway.vbs. Keep this script in a STABLE dir
(C:/Users/Ruslan/.hermes/bridge/), not tmp/.
"""
import os, re, json, time, sys, sqlite3, urllib.request

BASE   = 'C:/Users/Ruslan/.hermes'
DB     = BASE + '/state.db'
STATE  = BASE + '/tmp/bridge_state.json'
LOG    = BASE + '/logs/bridge.log'
FEISHU_HOST = 'open.feishu.cn'          # open.larksuite.com DNS is blocked here

def log(*a):
    msg = time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + ' '.join(str(x) for x in a)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except Exception:
        pass
    print(msg, flush=True)

# ---------- .env ----------
ENV = {}
try:
    for line in open(BASE + '/.env', encoding='utf-8', errors='ignore'):
        m = re.match(r'\s*(\w+)\s*=\s*(.*)', line)
        if m:
            ENV[m.group(1)] = m.group(2).strip().strip('"').strip("'")
except Exception as e:
    log('env load err', repr(e))
APP_ID, APP_SECRET = ENV.get('FEISHU_APP_ID',''), ENV.get('FEISHU_APP_SECRET','')
HOME_CH = ENV.get('FEISHU_HOME_CHANNEL','')

# ---------- Feishu IM ----------
_tok = {'v':'','exp':0}
def _http(method, url, payload=None, headers=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {'Content-Type':'application/json'}
    if headers: h.update(headers)
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read().decode() or '{}')
    except Exception as e:
        d = ''
        if hasattr(e,'read'):
            try: d = e.read().decode()[:300]
            except Exception: pass
        return {'_err': str(getattr(e,'code',e)), 'detail': d}

def token():
    if _tok['v'] and time.time() < _tok['exp']: return _tok['v']
    r = _http('POST', 'https://%s/open-apis/auth/v3/tenant_access_token/internal' % FEISHU_HOST,
              {'app_id': APP_ID, 'app_secret': APP_SECRET})
    if r.get('_err'): return ''
    _tok['v'] = r.get('tenant_access_token','')
    _tok['exp'] = time.time() + int(r.get('expire', 3600)) - 120
    return _tok['v']

def send_text(text):
    tok = token()
    if not tok: return False, 'no-token'
    r = _http('POST', 'https://%s/open-apis/im/v1/messages?receive_id_type=chat_id' % FEISHU_HOST,
              {'receive_id': HOME_CH, 'msg_type':'text',
               'content': json.dumps({'text': text}, ensure_ascii=False)},
              headers={'Authorization':'Bearer '+tok})
    if r.get('_err'): return False, str(r)
    if r.get('code') == 0:
        return True, (r.get('data') or {}).get('message_id','')
    return False, 'code=%s msg=%s' % (r.get('code'), r.get('msg'))

# ---------- gateway.log dedup ----------
def _gateway_delivered(user_text):
    if not user_text or len(user_text.strip()) < 3: return False
    try:
        lines = open(BASE+'/logs/gateway.log', encoding='utf-8', errors='ignore').readlines()[-600:]
    except Exception:
        return False
    needle = re.escape(user_text.strip()[:40])
    pat = re.compile(r'platform=feishu.*msg=' + needle)
    return any(pat.search(ln) for ln in lines)

# ---------- state ----------
def load_state():
    try: return json.load(open(STATE, encoding='utf-8'))
    except Exception: return {'cursors': {}}

def save_state(st):
    try:
        json.dump(st, open(STATE,'w',encoding='utf-8'), ensure_ascii=False)
    except Exception as e:
        log('state save err', repr(e))

# ---------- resolution ----------
def active_desktop_sid():
    """Most recent live desktop session by last_activity_at."""
    con = sqlite3.connect(DB, timeout=15); cur = con.cursor()
    try:
        cols = [d[1] for d in cur.execute('PRAGMA table_info(sessions)').fetchall()]
        if 'id' not in cols or 'source' not in cols: return ''
        row = cur.execute(
            "SELECT id FROM sessions WHERE source='desktop' AND ended_at IS NULL "
            "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT 1").fetchone()
        return row[0] if row else ''
    except Exception as e:
        log('resolve err', repr(e)); return ''
    finally:
        con.close()

# ---------- main cycle ----------
def once(sid):
    st = load_state()
    cursors = st.setdefault('cursors', {})
    con = sqlite3.connect(DB, timeout=15); cur = con.cursor()
    try:
        rows = cur.execute(
            "SELECT id, content, finish_reason FROM messages "
            "WHERE session_id=? AND role='assistant' AND content IS NOT NULL "
            "AND length(content) > 0 AND id > ? AND COALESCE(finish_reason,'') <> 'tool_calls' "
            "ORDER BY id", (sid, cursors.get(sid, 0))).fetchall()
    except Exception as e:
        log('query err', repr(e)); rows = []
    con.close()

    sent = 0
    # First-run safety: for a session we've never seen, pin cursor to the last
    # qualifying id and send NOTHING — never flood Lark with history.
    if sid not in cursors:
        if rows:
            cursors[sid] = rows[-1][0]
            log('new session %s: cursor pinned to %s (history not sent)' % (sid, rows[-1][0]))
        else:
            cursors[sid] = 0
        save_state(st)
        return 0

    for mid, content, fr in rows:
        # gateway auto-delivery dedup
        try:
            con2 = sqlite3.connect(DB, timeout=15); cur2 = con2.cursor()
            urow = cur2.execute(
                "SELECT content FROM messages WHERE session_id=? AND role='user' AND id<? "
                "ORDER BY id DESC LIMIT 1", (sid, mid)).fetchone()
            con2.close()
        except Exception:
            urow = None
        if urow and _gateway_delivered(str(urow[0] or '')):
            log('skip msg_id=%s (gateway delivered)' % mid)
            cursors[sid] = mid
            continue
        text = str(content).strip()
        if not text:
            cursors[sid] = mid
            continue
        ok, info = send_text(text[:2000])
        log('send msg_id=%s -> %s %s' % (mid, 'OK' if ok else 'FAIL', str(info)[:80]))
        cursors[sid] = mid
        sent += 1
        time.sleep(1)
    save_state(st)
    return sent

def main():
    mode = 'loop'
    if '--once' in sys.argv: mode = 'once'
    if '--test-outbound' in sys.argv:
        idx = sys.argv.index('--test-outbound')
        text = sys.argv[idx+1] if len(sys.argv) > idx+1 else 'test'
        ok, info = send_text(text)
        log('TEST-OUTBOUND', 'OK '+info if ok else 'FAIL '+str(info))
        return 0 if ok else 1

    log('bridge daemon start (mode=%s)' % mode)
    while True:
        try:
            sid = active_desktop_sid()
            if sid:
                n = once(sid)
                if n: log('cycle: sent %d from %s' % (n, sid))
            else:
                log('no active desktop session found')
        except Exception as e:
            log('cycle err', repr(e))
        if mode == 'once': break
        time.sleep(5)

if __name__ == '__main__':
    main()
