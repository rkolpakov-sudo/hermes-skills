# Audit v2 → v2.1 (2026-07-14)

**Scope:** Deep technical audit of StateGraph implementation in `tools/loop_tool.py`.  
**Method:** Static analysis + dynamic verification script (22 tests, all passing).

## Methodology (Reusable for Future Audits)

1. **Full source read** — load entire file before any static analysis
2. **Write standalone `.py` test script** → avoid bash quoting issues with inline `python -c` on Windows/MSYS
3. **Test each fix independently** — unit-level checks before integration tests
4. **Verify via handler path too** — direct function calls AND registry dispatch (`loop_handler`)
5. **Import smoke test** — `del sys.modules[...]` + fresh import confirms no registration breakage

## 9 Issues Found and Fixed

### 🔴 Critical (block production use)

| ID | Location | Problem | Fix |
|----|----------|---------|-----|
| BUG-1 | `_check_success_condition()` line 312 | Checked `data.get("evidence")` — field never written by `loop_run()`. Self-judge always returned confidence=0.4 even with real artifacts | Now checks `result_summary` (which ACT nodes actually write) + `decision` as fallback. Confidence=0.85 when evidence exists |
| BUG-2 | `loop_run()` lines 457-460 | `_rollback_to()` modified `graph["active_node_id"]` IN PLACE before `transition_reason` was constructed. Journal recorded wrong origin node (target instead of previous active) | `_rollback_to()` now returns `prev_active` BEFORE mutation. Caller uses returned value for transition_reason logging |

### 🟡 Logic (breaks on complex scenarios)

| ID | Location | Problem | Fix |
|----|----------|---------|-----|
| LOGIC-9 | `_add_branch()` line 140 | Branch inherited ALL ancestor parent_ids from source node. At depth N, branch had O(N) parents → inflated ancestors sets, wrong path calculations, false positives in self-judge | Branch stores `[source]` only (one parent). Ancestry is implicit through edge traversal, not duplicated in parent_ids |
| LOGIC-4 | `_graph_topology()` lines 257-270 | `current_path` used BFS on parent_ids — collected siblings as ancestors. In DAG with branching, path included nodes that were never executed | Now follows reverse edge index backward from active→root. Gives actual execution chain even in branched graphs |

### 🟢 Performance

| ID | Location | Problem | Fix |
|----|----------|---------|-----|
| PERF-3 | `_get_children()` line 175 | Scanned all edges O(\|E\|) per call. `_detect_repeated_patterns()` called it in a loop → overall O(\|V\|×\|E\|). Slow at 200+ nodes | Adjacency index (`_ci`) built lazily, cached on graph dict. Invalidation on node/edge addition. `_get_children()` is now O(1) |

### 🔵 Conceptual (wrong mental model for consumers)

| ID | Location | Problem | Fix |
|----|----------|---------|-----|
| CONCEPT-5 | Function name + docstring | Named `_detect_cycles()` but in a DAG, real cycles are impossible by definition. Function actually finds repeated text patterns across nodes | Renamed to `_detect_repeated_patterns()`. Docstring clarifies it detects semantic repetition, not graph cycles |

### ⚫ Dead Code / Robustness

| ID | Fix |
|----|-----|
| DEAD-8 | Removed unused `max_depth` parameter from `_detect_repeated_patterns()` signature |
| ROBUST | `_save_journal()`: replaced `Path(None) or ...` (TypeError on Windows pathlib) with explicit `if p else _journal_path(...)` |

### ℹ️ Known / Deferred to v3

| ID | Status |
|----|--------|
| DEAD-7 | `strategy` parameter stored at init but never checked during run(). Requires LLM-agent policy changes (adaptive/backtracking strategies) — architectural decision, not a bug |
| API-6 | Two return types: `loop_init()` → dict vs `loop_handler()` → str (JSON). Documented, kept for registry compatibility |

## Verification Results

```
[BUG-1]    2/2 passed   — self-judge confidence correct with result_summary evidence
[BUG-2]    2/2 passed   — rollback returns previous node ID before mutation
[LOGIC-9]  3/3 passed   — branch parent_ids = [source] only, no inflation
[PERF-3]   3/3 passed   — adjacency index built, O(1) children lookup, correct results
[LOGIC-4]  1/1 passed   — current_path follows edges backward (length=3 for branched DAG)
[CONCEPT-5] 3/3 passed  — old name removed, new function exists without max_depth
[Integration] 9/9 passed — full init→run→branch→status→rollback→stop cycle via handler

Total: 22/22 tests passed ✓
```

## Lessons for Future Audits

- **Inline `python -c` on Windows/MSYS bash fails** with multiline scripts containing single quotes. Always write to `.py` file instead.
- **Test both direct calls AND handler path** — registry dispatch can mask or expose different bugs (e.g., `_save_journal` TypeError only appeared via handler in cleanup).
- **Check field names between writer and reader**: ACT writes `result_summary`, CHECK reads `evidence`. This mismatch is the #1 class of bug in producer-consumer patterns.
