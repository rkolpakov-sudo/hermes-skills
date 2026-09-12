# Loop Enforcement v4 — Load Test Report (2026-07-19)

## Verdict: Heuristic Middleware, NOT Mandatory Blocker

Loop enforcement auto-injects `loop(mode="run")` into tool calls when thresholds are met, but is **non-fatal** and **configurable**. It does not block sessions.

## Architecture (conversation_loop.py L5012-5080)

| Phase | Location | Action |
|---|---|---|
| Phase 1: Detection | L5016 | `_detect_iterative_task()` scans tool names vs config markers |
| Phase 2: Injection | L5023-5044 | Appends synthetic `loop(mode="run")` to `assistant_message.tool_calls` |
| Phase 3: Snapshot | L5048-5078 | Builds running-loop snapshots for UI (Level 1/2/3 SSE emit) |

## Trigger Logic (loop_tool.py L1469-1470)

```python
_is_iterative = marker_count >= 3 OR (marker_count >= 2 AND tool_count >= 4)
_needs_loop   = NOT has_loop AND tool_count >= 5 AND _is_iterative
```

## Decision Matrix

| Tools | Markers=0 | Markers=1 | Markers=2 | Markers=3+ |
|---|---|---|---|---|
| 1-4 | . | . | . | . (NEVER triggers, tools < 5) |
| 5 | . | . | **Y** | **Y** |
| 6+ | . | . | **Y** | **Y** |

**Y** = loop auto-injected · **.** = bypassed

## Bypass Conditions

1. Agent explicitly calls `loop` → `_has_loop=True`, enforcement skipped entirely
2. `< 5 unique tools` in the turn → never triggers, regardless of markers
3. Previous enforced loop still running (`_already_enforced=True`) → reuses existing loop (resume mode)
4. Injection failure → logged as debug (L5043-5044), original tool calls execute normally

## Configuration (config.yaml L653-667)

```yaml
loop_tool:
  iterative_markers: [search_files, read_file, patch, write_file, execute_code, browser_navigate, terminal, delegate_task, web_scrape]
  min_tool_count: 5
  min_iterative_markers: 3
```

## Test Scenarios (13 total)

| # | Scenario | Tools | Markers | Iterative? | Triggered | Result |
|---|---|---|---|---|---|---|
| 1 | Single tool call | 1 | 1 | No | No | ✅ PASS |
| 2 | Two simple tools | 2 | 2 | No | No | ✅ PASS |
| 3 | Three markers (boundary, <5 tools) | 3 | 3 | Yes | **No** | ✅ Correct (tools < 5) |
| 4 | Five tools, 4 markers | 5 | 4 | Yes | Yes | ✅ PASS |
| 5 | Six tools, 3 markers | 6 | 3 | Yes | Yes | ✅ PASS |
| 6 | All 9 markers | 9 | 9 | Yes | Yes | ✅ PASS |
| 7 | Four tools, 2 markers | 4 | 2 | Yes | **No** | ✅ Correct (tools < 5) |
| 8 | Five tools, 1 marker | 5 | 1 | No | No | ✅ PASS |
| 9 | Agent called loop explicitly | 4 | 3 | Yes | **No** | ✅ Bypassed (has_loop=True) |
| 10 | Minimal tools, no markers | 2 | 0 | No | No | ✅ PASS |
| 11 | Code review workflow | 5 | 5 | Yes | Yes | ✅ PASS |
| 12 | Research + docs | 5 | 5 | Yes | Yes | ✅ PASS |
| 13 | Data analysis pipeline | 5 | 4 | Yes | Yes | ✅ PASS |

**Result: 6/13 triggered loop injection. 0 false positives.**
