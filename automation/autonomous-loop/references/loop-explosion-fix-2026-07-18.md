# Loop Explosion Incident — FIX6/FIX7/FIX8 (2026-07-18)

**Severity:** 🔴 CRITICAL  
**Status:** ✅ Fixed + verified  

---

## What Happened

After FIX2 (SSE structured emit) made the middleware v4 injection WORK, a catastrophic bug surfaced: **every normal agent turn created a false-positive loop journal**. The detection threshold was too low.

### Root Cause — Detection Logic (loop_tool.py L2419-2420)

```python
# BROKEN — TOO AGGRESSIVE:
_iterative_markers = frozenset({
    "search_files", "read_file", "patch", "write_file",
    "execute_code", "browser_navigate", "terminal",
})
_is_iterative = len(tool_names & _iterative_markers) >= 2   # ← TRIGGERS TOO EASY
_needs_loop = not _has_loop and (len(tool_names) >= 3 or _is_iterative)

# Example normal turn: read_file + execute_code + patch (3 tools, 3 markers)
# → len(tool_names)=3 ≥ 3? YES → LOOP CREATED ← FALSE POSITIVE!
```

**Why it broke NOW:** Middleware v4 injection made loop_handler actually WORK. Previously LLM ignored text hints — loop was never called. After injection fix, every detected "iterative task" spawned a real loop with journal file and SSE notifications to UI.

### Impact

| Metric | Value |
|---|---|
| Journals in `~/.hermes/loops/` | 180 active + 166 archives = 346 total |
| Running state (false positives) | 68 simultaneously "active" |
| UI notifications per turn | 14+ `[🔄 Loop active · ...]` lines |
| Age of oldest journal | 3.9 days |
| New false-positive rate before fix | ~104 new journals in 30 min |

---

## Applied Fixes

### FIX6 — Detection Threshold (CRITICAL)

**File:** `loop_tool.py` L2419-2424

```diff
- _is_iterative = len(tool_names & _iterative_markers) >= 2
- _needs_loop = not _has_loop and (len(tool_names) >= 3 or _is_iterative)

+ # FIX: Raised thresholds to prevent false-positive loop creation.
+ _is_iterative = len(tool_names & _iterative_markers) >= 3
+ _needs_loop = not _has_loop and (len(tool_names) >= 5 and _is_iterative)
```

**Rationale:** Normal turns use 2-4 tools. Genuine iterative work has ≥5 tool calls AND ≥3 iterative markers. New logic requires BOTH conditions (AND, not OR).

### FIX7 — Stale Loop Guard

**File:** `loop_tool.py` L2455

Detection scan now checks `_jd.get("iteration", 0) > 0` before considering a running loop for resume. Dead loops stuck at iteration=0 are skipped.

### FIX8 — Snapshot Emission Flood Fix

**Files:** `conversation_loop.py` L4879, 5324-5331, 5349-5357

| Before | After |
|---|---|
| Level 1 emitted ALL running loops as UI lines | Picks best loop (highest iteration) → ONE line |
| Sweep read all states (running/completed/stopped/timeout/stuck) | Sweep only reads `state=="running"` |
| SSE emission flooded with N events | Single structured event per turn |

---

## Verification — Load Test Results

### Threshold Simulation (6 scenarios)

| Scenario | Tools | Markers Hit | Result |
|---|---|---|---|
| Normal: read + execute + patch | 3 | 3/3 | ✅ No loop |
| Heavy normal: 4 tools, 3 markers | 4 | 4/3 | ✅ No loop |
| 5 tools, 3 iterative | 5 | 3/3 | 🔴 Loop created (correct) |
| Borderline: 5+5 markers | 5 | 5/3 | 🔴 Loop created (correct) |
| Heavy: 7 tools, 5 markers | 7 | 7/3 | 🔴 Loop created (correct) |
| 2 tools only | 2 | 2/3 | ✅ No loop |

### Post-Fix Metrics

- **New journals since fix:** 0 ✅
- **Active running loops after cleanup:** 14 (all legitimate, iteration>0, from Jul 16-17 sessions)
- **UI shows:** 1 status line per turn (not 14+)

---

## Lessons Learned

1. **OR vs AND logic matters catastrophically** — `≥3 OR ≥2` was mathematically guaranteed to trigger on most turns. Always use AND for multi-condition gates in safety-critical detection.
2. **Test thresholds against real traffic patterns** — normal agent turns average 3-4 tool calls. A threshold of 3 tools is NOT "unusual activity."
3. **SSE notifications need flood protection** — emitting N events where N = all running loops is not scalable. Always pick the best/representative one.
4. **Cleanup must handle ALL states, not just stopped** — `state="stopped"` journals still count as active files in sweep and waste I/O every turn.

---

## Related Files

- `loop_tool.py` L2415-2424 (detection thresholds)
- `conversation_loop.py` L4879, 5324-5369 (sweep + emission)
- `loop_tool_FIX_REPORT.md` — user-applied fixes FIX1-FIX5
- `loop_tool_STATE_HANDBOOK.md` — comprehensive state documentation
