#!/usr/bin/env bash
# Panel latency probe: endpoint timings + first-paint budget ladder.
# Faults it catches: init awaiting slow external I/O; a second (stale) listener on the port.
#
# Usage:  bash panel_latency_probe.sh [PORT] [CONTENT_MARKER]
#   PORT            default 8791
#   CONTENT_MARKER  string that only exists after JS render (default: 'Сводка')
set -u
PORT="${1:-8791}"
MARKER="${2:-Сводка}"
BASE="http://127.0.0.1:$PORT"
TMP="${LOCALAPPDATA:-$HOME/AppData/Local}/Temp"
mkdir -p "$TMP"

EDGE=""
for c in \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  "/c/Program Files/Microsoft/Edge/Application/msedge.exe" \
  "/c/Program Files/Google/Chrome/Application/chrome.exe"; do
  [ -f "$c" ] && EDGE="$c" && break
done

echo "== listeners on :$PORT (must be exactly ONE) =="
netstat -ano | grep ":$PORT" | grep LISTENING || echo "  (none — server is DOWN)"

echo
echo "== endpoint timings =="
for ep in "" api/config api/projects api/dashboard api/sites api/directions; do
  printf '%-18s ' "/$ep"
  curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' --max-time 30 "$BASE/$ep"
done

echo
echo "== expensive probes: cold (?force=1) vs cached =="
printf 'cold   '; curl -s -X POST -o /dev/null -w '%{http_code} %{time_total}s\n' --max-time 180 "$BASE/api/mail/check?force=1"
printf 'cached '; curl -s -X POST -o /dev/null -w '%{http_code} %{time_total}s\n' --max-time 60  "$BASE/api/mail/check"

echo
echo "== first paint: headless budget ladder (want PAINTED at the LOW budget) =="
if [ -z "$EDGE" ]; then
  echo "  no Chromium binary found — install Edge/Chrome or pass one manually"
  exit 0
fi
for b in 600 1500; do
  out="$TMP/panel_dom_${b}.html"
  "$EDGE" --headless=new --disable-gpu --no-first-run --user-data-dir="$TMP/edge_panel_probe" \
      --virtual-time-budget="$b" --dump-dom "$BASE/" > "$out" 2>/dev/null
  if grep -q "$MARKER" "$out" 2>/dev/null; then
    echo "  ${b}ms: PAINTED"
  else
    echo "  ${b}ms: not yet"
  fi
done
echo
echo "Reading: 'not yet' at 600ms but PAINTED at 1500ms => init awaits slow external I/O."
echo "         Two LISTENING PIDs above => split-brain, requests hit stale code — kill all, relaunch once."
