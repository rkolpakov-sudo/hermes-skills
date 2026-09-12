#!/usr/bin/env python3
"""Inbound poll bridge: Feishu IM API → state.db (bypasses stalled WS).

Polls the Feishu IM API for new DM messages and writes them directly to
state.db as user messages in the active feishu session. Bypasses the
gateway's WebSocket when it's stalled (unclean kill without WS CLOSE frame).

Dedup: checks platform_message_id column to avoid writing the same message
twice across poll cycles.

Run via pythonw from a stable dir (C:/Users/Ruslan/.hermes/bridge/):
  pythonw bridge_inbound_poll.py

Autostart option: add to Hermes_Bridge.vbs alongside bridge_daemon.py.
"""
import sys, os, json, time, sqlite3, re, urllib.request

BASE = 'C:/Users/Ruslan/.hermes'
DB = BASE + '/state.db'
FEISHU_HOST = 'open.feishu.cn'  # NOT open.larksuite.com (DNS blocked)
POLL_LOG = BASE + '/logs/bridge_inbound.log'

def log(msg):
    l = time.strftime('%Y-%m-%d %H:%M:%S') + ' bridge-inbound: ' + str(msg)
    print(l, flush=True)
    try:
        with open(POLL_LOG, 'a', encoding='utf-8') as f:
            f.write(l + '\n')
    except Exception:
        pass

# ---------- .env ----------
ENV = {}
for line in open(BASE + '/.env', encoding='utf-8', errors='ignore'):
    m = re.match(r'\s*(\w+)\s*=\s*(.*)', line)
    if m:
        ENV[m.group(1)] = m.group(2).strip().strip('"').strip("'")
APP_ID, APP_SECRET = ENV.get('FEISHU_APP_ID',''), ENV.get('FEISHU_APP_SECRET','')
HOME_CH = ENV.get('FEISHU_HOME_CHANNEL','')

# ---------- Feishu IM API ----------
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
            except: pass
        return {'_err': str(getattr(e,'code',e)), 'detail': d}

def token():
    if _tok['v'] and time.time() < _tok['exp']: return _tok['v']
    r = _http('POST', 'https://%s/open-apis/auth/v3/tenant_access_token/internal' % FEISHU_HOST,
              {'app_id': APP_ID, 'app_secret': APP_SECRET})
    if r.get('_err'): return ''
    _tok['v'] = r.get('tenant_access_token','')
    _tok['exp'] = time.time() + int(r.get('expire', 3600)) - 120
    return _tok['v']

def get_recent_messages():
    """Get last 10 messages from the home DM chat."""
    tok = token()
    if not tok: return []
    url = 'https://%s/open-apis/im/v1/messages?container_id_type=chat&container_id=%s&sort_type=ByCreateTimeDesc&page_size=10' % (FEISHU_HOST, HOME_CH)
    r = _http('GET', url, headers={'Authorization':'Bearer '+tok})
    if r.get('_err'): return []
    items = r.get('data',{}).get('items',[])
    results = []
    for i in items:
        if i.get('msg_type') != 'text':
            continue
        sender = i.get('sender',{})
        sid = sender.get('id','')
        if not sid or sid.startswith('cli_'):  # skip bot's own messages
            continue
        try:
            content = json.loads(i.get('body',{}).get('content','{}'))
            text = content.get('text','')
        except:
            text = str(i.get('body',{}).get('content',''))
        # Skip "recalled" messages (Feishu sends placeholder text)
        if text.strip() in ('This message was recalled', 'This message has been recalled'):
            continue
        results.append({
            'message_id': i.get('message_id',''),
            'text': text.strip(),
        })
    return results

def write_to_session(feishu_msg_id, text):
    """Write a user message into the active feishu session in state.db."""
    con = sqlite3.connect(DB, timeout=15)
    cur = con.cursor()
    try:
        row = cur.execute(
            "SELECT id FROM sessions WHERE ended_at IS NULL "
            "AND source='feishu' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            log("no active feishu session")
            return False
        sess_id = row[0]
        dup = cur.execute(
            "SELECT id FROM messages WHERE session_id=? AND platform_message_id=? LIMIT 1",
            (sess_id, feishu_msg_id)).fetchone()
        if dup:
            return False
        max_id = cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM messages").fetchone()[0]
        now = time.time()
        cur.execute(
            "INSERT INTO messages (id, session_id, role, content, timestamp, "
            "platform_message_id, finish_reason) VALUES (?, ?, 'user', ?, ?, ?, NULL)",
            (max_id, sess_id, text, now, feishu_msg_id))
        cur.execute(
            "UPDATE sessions SET message_count=COALESCE(message_count,0)+1 WHERE id=?", (sess_id,))
        con.commit()
        log(f"WROTE id={max_id} '{text[:40]}' -> {sess_id[:22]}")
        return True
    except Exception as e:
        log(f"write err: {e}")
        return False
    finally:
        con.close()

def main():
    log("started (poll=10s)")
    last_poll = 0
    while True:
        try:
            if time.time() - last_poll >= 10:
                msgs = get_recent_messages()
                written = 0
                for m in msgs:
                    if write_to_session(m['message_id'], m['text']):
                        written += 1
                if msgs:
                    log(f"poll: {len(msgs)} msgs, {written} new, {len(msgs)-written} dup/skip")
                last_poll = time.time()
        except Exception as e:
            log(f"err: {e}")
        time.sleep(5)

if __name__ == '__main__':
    main()