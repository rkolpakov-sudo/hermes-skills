# GAP Remediation: Wave-Based Batch Bug Fixing

Discovered: Session 2026-07-24 (dxf-mep-analyzer project)
Verified against: Spec v1.0.0 (§§1-29)

## Context

When a spec compliance audit reveals 20+ bugs across multiple modules, sequential fixing is slow and error-prone. Wave-based parallel remediation achieved 24/24 fixes in 4 waves with full per-patch verification against the spec.

## The Problem With Broad-Spectrum Scanners

A generic pattern scanner (e.g., `grep "mkdir"` across all Python files) hit **3681 files** — including venv dependencies, causing false positives and wasted effort. This is NOT how to do a GAP audit after the initial compliance check.

## Correct Approach: Targeted GAP Audit Script

```python
# scripts/gap_audit_v3.py
# Check SPECIFIC bugs against SPECIFIC modules
checks = []

m0 = rf("modules/module_0_preprocessing.py")
m3 = rf("modules/module_3_rendering.py")
m4 = rf("modules/module_4_vision.py")
m6 = rf("modules/module_6_graphrag.py")
sec = rf("security.py")
cfg = rf("config.py")

# BUG-001: Silent exceptions in rendering → check for logger.error presence
if m3 and "logger" in m3 and "# BUG-001 FIX" in m3:
    checks.append({"id": "BUG-001", "status": "FIXED"})
else:
    checks.append({"id": "BUG-001", "status": "OPEN"})

# ... repeat for each specific bug, reading actual function bodies
```

**Rules:**
- Scan ONLY `src/` — exclude `venv/`, `tests/`, `benchmarks/`
- Check 20-50 SPECIFIC items, not thousands of files
- A GAP audit reports FIXED/OPEN per bug ID, not a match count

## Wave Strategy for Parallel Remediation

### Wave Composition Principles

1. **Read ALL affected files FIRST** (batch reads are parallel and free)
2. **Group by module independence**: Modules that don't import each other → same wave; dependent modules → sequential
3. **After EACH patch**: Verify against the relevant spec § before moving on

### Session 2026-07-24: 4 Waves, 24 Bugs Fixed

| Wave | Files Modified | Bugs Fixed | Spec Sections Verified |
|------|---------------|------------|----------------------|
| Wave 1 | `module_3_rendering.py` | BUG-001, 002, 006 | §7 (Rendering & Tiling) |
| Wave 2 | `mcp_server.py` | BUG-003, 004 + regex fix | §14, §17.2 (Security) |
| Wave 3 | `module_6_graphrag.py` | BUG-008, 009 | §10.4, §17.2 (GraphRAG + Security) |
| Wave 4 | `module_4_vision.py`, `llm/client.py` | BUG-005, 015 | §8.3, §15.2 (Vision + Error Handling) |

## Bug Fix Patterns Discovered This Session

### Pattern A: Vision Retry with Exponential Backoff
```python
# Before: single call, no retry
response = requests.post(url, json=payload, timeout=timeout)

# After: 3 retries with exponential backoff + circuit breaker
for attempt in range(max_retries):
    try:
        response = session.post(url, json=payload, timeout=timeout)
        break
    except Exception as e:
        if attempt < max_retries - 1:
            time.sleep(min(2 ** attempt * backoff_sec, max_backoff))
```

### Pattern B: Cypher Self-Correction Loop
```python
# Before: generate once, fail silently on syntax error
cypher = llm.generate(prompt)
if not validate_cypher(cypher):
    return None  # Lost opportunity for self-correction

# After: feed syntax errors back to LLM for correction (max 3 retries)
for attempt in range(max_retries):
    if validate_cypher(cypher):
        break
    cypher = llm.generate(correction_prompt + f"\nError: {syntax_error}")
```

### Pattern C: Scale-Aware Tile Coordinates
```python
# Before (BUG-006): tile steps in pixel units, ignoring DXF scale/units
step = tile_size - overlap  # pixels — WRONG for large drawings

# After (§7.2.2): convert to DXF coordinate space
dpi = fig.dpi  # e.g., 300 DPI
scale_mm_per_unit = doc.header.get('$INSUNITS', 'mm')
step_dxf_x = (tile_size - overlap) / dpi * scale_mm_per_unit
```

### Pattern D: Unicode Injection Bypass Prevention (§17.2)
```python
# Before: regex scans the raw query, allowing unicode escape sequences to bypass validation
if re.search(r'\bDELETE\b', cypher):  # \u0044\u0045\u004C\u0045\u0054\u0045 = "DELETE"

# After: normalize unicode BEFORE scanning
normalized = unicodedata.normalize('NFKC', cypher)
if re.search(r'\bDELETE\b', normalized):  # Now catches escaped DELETE
```

## Verification Protocol (Per-Patch Spec Check)

After EACH patch, verify:
1. Does the fix satisfy the spec requirement? (re-read relevant §)
2. No regressions introduced? (lint passes, module imports cleanly)
3. Bug registry entry marked resolved with evidence (diff output + line numbers)

## Final Commit Strategy

Batch all verified patches into ONE commit per wave:
```bash
git add -A && git commit -m "fix: Resolve remaining bugs BUG-005→BUG-024, verified against spec v1.0.0"
```

Verify clean working tree after commit: `git status` should show nothing to commit.

## Lessons Learned

| Lesson | Context | Application |
|--------|---------|-------------|
| Targeted GAP audit beats broad spectrum scanner | Scanner hit 3681 files; targeted script checked 24 specific bugs → all correct | Always use SPECIFIC bug checks, not generic pattern matches |
| Wave-based parallel remediation is fast | 4 waves × ~5 min each = 20 min for 24 bugs vs sequential hours | Group by module independence, read all files first |
| Per-patch spec verification prevents wrong fixes | User directive: "After EACH patch, verify against the spec" | Re-read relevant § after every patch before moving on |
| `patch` can corrupt regex backslashes in Python strings | `\\b` vs `\b` escaping issue when using `patch()` | Use `write_file` for complex regex rewrites where escaping is fragile |
