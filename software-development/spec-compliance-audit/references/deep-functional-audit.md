---
title: Deep Functional Audit — Presence ≠ Functionality
date: 2026-07-23
project: dxf-mep-analyzer (v1.0.0)
session_context: User demanded "глубокий критический анализ" after previous audit claimed 100% compliance while features were non-functional
---

# Deep Functional Audit Technique

## Core Lesson

**Signature-based compliance ≠ working software.** A function existing in source code does not mean the feature works. This was validated when an audit script reported 83/83 checks (100%), yet four critical modules were completely non-functional:

| Module | Signature Check | Reality | Gap Cause |
|--------|----------------|---------|-----------|
| §8 Vision Analysis | ✅ `analyze_all_tiles()` exists | ❌ Returns empty lists, API calls commented as TODO | Stub implementation |
| §14 MCP Server | ✅ 8 tools registered in `register_tools()` | ❌ JSON-RPC handler incomplete — code cut off mid-function | Incomplete code path |
| §15 Error Handling | ✅ `FallbackMatrix.execute_fallbacks()` exists | ⚠️ Method never called by any other module | Disconnected safety net |
| §17 Security | ✅ `MAX_DXF_SIZE = 200*1024**2` defined | ❌ Constant unused in `validate_dxf()` — dead code | Dead config |

**Real functional coverage: ~65%** (not the reported 100%).

## The Deep Audit Checklist

When user demands "глубокий критический анализ" (deep critical analysis), go beyond grep/regex and actually READ source files:

### 1. Read Critical Modules Fully
```python
# Don't just grep for function names — read the actual implementation
read_file("src/modules/module_4_vision.py")  # Full file, not search results
```
Look for inside every critical function:
- `# TODO:` or commented-out code blocks (real work behind comments)
- Unconditional `return []`, `return {}`, `return None` (stub responses)
- Functions that build payloads but never send them (`build_vision_request()` → no actual HTTP call)

### 2. Verify Cross-Module Wiring
```bash
# Check if a function defined in one file is actually called from others
grep -rn "execute_fallbacks" src/   # Returns only the definition? → dead code
grep -rn "sanitize_cypher" src/     # Only in security.py + mcp_server.py? → partially wired
```

**Disconnected patterns:**
- Error handler exists but no module imports it
- Fallback matrix defined but `try/except` blocks raise instead of calling fallbacks
- Security validation function never invoked from CLI entry point

### 3. Check for Dead Code
```bash
# Constants that exist but nothing references them
grep -rn "MAX_DXF_SIZE" src/   # Only definition? → dead code, not enforced
grep -rn "DEFAULT_THRESHOLDS" src/logging_config.py  # Used internally? Yes. Exported? No.

# Functions registered in schemas but never routed
grep -rn "initialize_analysis" src/mcp_server.py  # Defined + listed in register_tools()... 
# But is there code to actually invoke it from incoming JSON-RPC requests? Read the stdin loop!
```

### 4. Look for Hardcoded Defaults That Contradict Spec Claims
**Pattern:** `config_value = cfg.get("key") or "hardcoded_default"`

**Why it matters:** The spec says "everything is configurable, no hardcoded models." But when config is missing, the system falls back to a specific model — effectively making it the default. If that model isn't available to the user, the feature fails silently.

**Scan for:**
```bash
grep -rn 'or\s*["'"'"']' src/  # Finds all hardcoded fallbacks behind optional config
```

### 5. Global State Without Cleanup (Memory Leaks)
```python
# Pattern: global mutable state that persists between runs
STATE = AnalysisState()  # mcp_server.py line 38
```

If the process handles multiple analyses sequentially (MCP server, long-running daemon), this state accumulates without reset. Check for:
- `reset()` method on the state object? → No
- Cleanup at end of analysis cycle? → No
- New instance created per request? → No

### 6. Thread Safety Gaps
```python
# In logging_config.py line 113:
avg = sum(self.histograms[name]) / len(self.histograms[name])
```
No locks around shared dictionaries (`counters`, `histograms`, `gauges`). If multiple threads call `observe()` and `check_thresholds()` simultaneously → race conditions.

## Deliverable Format for Deep Audits

When producing a deep audit report, structure it by **actual impact**, not by spec section:

```markdown
# Deep Audit Report — Project X

## 🔴 CRITICAL (blocks production)
1. [Module] Feature non-functional — stub returns empty values
2. [Server] Incomplete code path — handler never reaches tool routing

## 🟠 SERIOUS (degrades in production)  
3. [Security] Validation exists but unused — dead code
4. [State] Memory leak in long-running process — no cleanup between runs
5. [Concurrency] Race condition on shared metrics — no thread safety
6. [Config] Hardcoded defaults contradict "zero hardcoded" spec claim

## 🟡 MODERATE (quality issues)
7. Duplicated code across modules (scale detection, polyline length)
8. Missing dependency in pyproject.toml (structlog)
9. Incomplete test coverage for critical paths

## Summary
- Signature-based compliance: 100%
- **Functional compliance: ~65%** ← THIS is the real number
- Critical blockers to production: 4
```

## When to Trigger Deep Audit vs Signature Check

| Signal | Action |
|--------|--------|
| "Сверься с ТЗ" / "проверь соответствие" | Standard signature audit (regex + file existence) |
| "Глубокий критический анализ" / "реальный аудит" | **Deep functional audit** — read actual files, verify wiring, find stubs/dead code |
| User calls out hallucinated coverage ("Ты галлюцинируешЬ!") | Immediately switch to deep audit + expand section coverage |