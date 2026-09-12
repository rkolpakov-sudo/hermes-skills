---
name: spec-compliance-audit
description: "Verify implementation against specification — gap analysis, signature matching, iterative test repair."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [specification, compliance, audit, verification, testing, code-review]
    related_skills: [test-driven-development, systematic-debugging, plan]
---

# Spec Compliance Audit

## Overview

Systematically verify that a codebase fully implements its specification — identify gaps, create missing tests/files, and repair signature mismatches until every test passes.

**Core principle:** Never guess source signatures. Always read actual function/class definitions before writing imports into tests or dependent code.

## When to Use

- User says "сверься с ТЗ" (check against spec)
- Building new project from specification document
- Verifying existing implementation matches requirements
- Tests fail with import errors — guessed signatures are wrong
- **User calls out hallucinated coverage** ("Ты галлюцинируешЬ! Спецификация имеет больше пунктов!") — IMMEDIATELY re-read the FULL spec and expand audit to cover ALL sections, not a subset
- **User demands deep critical analysis** ("Произвести глубокий критический анализ") — go beyond regex/signature matching; read actual source code via `read_file()` and verify FUNCTIONALITY. Look for stubs with TODO comments returning empty values, dead code paths, disconnected fallback chains, hardcoded defaults that contradict spec claims

## Critical Principle #1: Check EVERY Section

**NEVER assume you've covered all spec sections.** In session 2026-07-23, an audit script checked ~18 sections when the spec had 26+ technical sections — the user explicitly called this out. The fix was to re-read the full spec and rebuild the audit covering ALL sections (§§1-26). Always verify your check count against the actual number of sections in the TOC before declaring completion.

## Audit Process

### Phase 1: Read the Full Spec

Read ALL sections of the specification — don't skip. For large specs (>2000 lines), read in chunks but cover every section:

```python
# Read spec in overlapping windows to catch boundary details
read_file(spec_path, offset=1, limit=500)
read_file(spec_path, offset=501, limit=500)
# ... continue until end
```

### Phase 2: Build the Audit Script

**Write an audit script as a standalone Python file — never inline in terminal or execute_code.** This is critical because:

1. **execute_code runs in a sandboxed container** with no access to your project files (`/c/Projects/...`). A script that reads source files returns 0/N matches because all paths appear missing.
2. **Inline Python in terminal breaks on Windows bash** due to quote/escape conflicts — `unexpected EOF while looking for matching '...'` errors are common with multi-line scripts containing both single and double quotes.

```bash
# Write the script as a file:
write_file(path="scripts/compliance_audit.py", content=...)  # See templates/audit_template.py
```bash
# Run from project directory with venv activated:
cd /path/to/project && source .venv/Scripts/activate
python scripts/compliance_audit.py
```

**Windows path resolution (critical):** On Windows with MSYS/git-bash, hardcoding absolute paths like `/c/Projects/my-project` in audit scripts FAILS because the shell translates `C:\` to `/c/` but Python's `Path()` may not resolve cross-platform. **Fix:** Use script-relative base path:

```python
from pathlib import Path
BASE = str(Path(__file__).resolve().parent.parent)  # Works in Windows AND MSYS/bash
def rf(p):
    try:
        return (Path(BASE) / p).read_text(encoding="utf-8")
    except Exception:
        return None
```

**Run it from terminal with venv activated — never from execute_code sandbox:**
- `hf(content, func_name)` — checks if `def func_name(...)` exists in source
- `fe("path/to/file.yaml")` — checks file existence relative to project root
- String presence (`"SLA" in content`) — for constants, patterns, keywords
- Regex matches — for complex signature/format verification

See `scripts/compliance_audit.py` (template) for the complete working script.

### Phase 3: Run and Iterate

```bash
python scripts/compliance_audit.py
# Output shows per-section pass/fail with gap list
```

**Iterate:** Each gap → one targeted patch (to audit script OR implementation). Re-run after each batch of fixes. Don't accumulate — verify incrementally until 100%.

### Phase 2b: Gap Analysis — Spec vs File Structure

Cross-reference each spec section against actual files. Flag:
- Missing modules (spec requires §X but no corresponding file)
- **File name mismatch** (spec says `module_1_layer_mapping.py` but actual file is `module_1_layer_classification.py`) — adapt audit paths to reality, not spec text
- Missing config files (YAML/JSON referenced by code)
- Missing test coverage (modules without `test_*.py`)
- Missing documentation (§Docs section vs README.md)

**Always verify file names with `ls src/modules/` BEFORE writing the audit script.** Don't assume spec naming matches implementation naming.

### Phase 3: Create Missing Files

For each gap, create the file matching spec requirements. **Read the spec section for that file** — don't invent interfaces from memory.

### Phase 4: Write Tests Against REAL Signatures (CRITICAL)

**Anti-pattern:** Writing test imports based on guessed function names/signatures → tests fail with `ImportError` or `TypeError`.

**Correct approach:**

1. Extract actual public symbols from source files BEFORE writing tests:
```python
import re, json

with open("src/module.py") as f:
    content = f.read()
funcs = re.findall(r'^def\s+(\w+)', content, re.MULTILINE)
classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
# → {"functions": [...], "classes": [...]}
```

2. For function signatures (args count/types), read the actual `def` lines:
```python
sigs = re.findall(r'def\s+\w+\((.*?)\):', content, re.DOTALL)
```

3. Write test imports using ONLY verified symbols. If a symbol doesn't exist in source, either create it or adjust the test to use what does exist.

### Phase 5b: Functional Depth Audit (DEEP CRITICAL ANALYSIS)

**When user demands "глубокий критический анализ" — this phase is MANDATORY.** Signature-based compliance says "the function exists." Functional depth audit asks "does it actually DO anything?"

Read the actual source code of every critical module (`read_file()`). Look for:

| Pattern | Signal | What to check |
|---------|--------|---------------|
| `# TODO:` or commented-out API calls | **Stub, not implementation** | Real work is behind a comment — feature non-functional |
| Functions returning empty lists/dicts unconditionally | **Dead stubs** | `return []`, `return {}` with no conditional branches means nothing happens |
| Error handler defined but never imported/called elsewhere | **Disconnected safety net** | grep for the function name across all files — if only found in its own file, it's dead code |
| Constants defined but unused (`grep -r "MAX_.*SIZE"` returns 1 hit) | **Dead config** | Value exists but nothing references it — spec claim is false |
| Hardcoded defaults that contradict spec ("zero hardcoded models" → `or "qwen3-235b-a22b"`) | **Spec violation hidden as fallback** | Look for `or` expressions on config values — they encode the real default when config is missing |
| Global mutable state without cleanup between runs | **Memory leak in long-lived process** | `STATE = AnalysisState()` that persists across multiple invocations will grow unbounded |

After this phase, produce a REALISTIC compliance report:
```markdown
## Functional Compliance Report (Deep Audit)

| Module | Code Exists? | Actually Works? | Real Coverage |
|--------|-------------|-----------------|---------------|
| §8 Vision | ✅ Yes | ❌ Stub (TODO comments) | 0% |
| §14 MCP Server | ✅ Partial | ❌ No request handler | 30% |
| §15 Error Handling | ✅ Yes | ⚠️ Fallback disconnected | 20% |

**Overall: X% real coverage** (vs Y% signature-based)
```

### Phase 6: Iterative Test Repair

Run tests → read failures → patch tests OR source code → repeat until green:

```bash
# Run targeted failing tests first (faster feedback)
pytest tests/test_new_file.py --tb=short -v

# Then full suite to check regressions
pytest tests/ --tb=short -q
```

**Key rules:**
- Fix the root cause, not symptoms. An `ImportError` means wrong function name — read source to find the real name.
- A `TypeError: missing positional argument` means you guessed the signature wrong — read the actual `def` line.
- A `TypeError: '<' not supported between instances of 'MagicMock' and 'str'` means your mock doesn't have the right attribute for a comparison — check what attribute the source code accesses.

### Phase 6: Commit Evidence

Commit all changes with descriptive messages referencing spec sections:

```bash
git add -A
git commit -m "feat: Tests M3/M4 (§19), acceptance (§24), config layer_mapping, deployment scripts"
git log --oneline -5  # Verify clean history
```

### Phase 7: Targeted GAP Audit (Avoid False Positives)

**Critical lesson from session 2026-07-24:** Generic pattern scanners (e.g., `grep "mkdir"` across all files, including dependencies) produce FALSE POSITIVES that waste time and erode confidence in the audit. A scanner that hits 3681 files is broken — it's scanning venv/dependencies instead of your codebase.

**Correct approach: Write a targeted GAP audit script** that checks SPECIFIC bugs against SPECIFIC modules, not generic patterns across all Python files:

```python
# scripts/gap_audit_v3.py — TARGETED, not broad-spectrum
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent  # Works in MSYS/bash
SRC = project_root / "src"

def rf(p):
    try:
        return (SRC / p).read_text(encoding="utf-8")
    except Exception:
        return None

checks = []

# BUG-XXX: Check SPECIFIC function for SPECIFIC defect pattern
m3 = rf("modules/module_3_rendering.py")
if m3 and "logger.error" in m3 and "dir()" not in m3.split("# BUG")[0]:
    checks.append({"id": "BUG-001", "status": "FIXED"})

# ... repeat for each known bug, checking its specific file

report = {"total": len(checks), "fixed": sum(1 for c in checks if c["status"] == "FIXED")}
print(json.dumps(report, indent=2))
```

**Key rules:**
- Scan ONLY `src/` — exclude `venv/`, `tests/`, `benchmarks/`
- Check SPECIFIC defects by reading the ACTUAL function bodies (not regex on filenames)
- A GAP audit should check ~20-50 specific items, not thousands of files
- If a "scanner" reports scanning 1000+ files, it's broken

See `scripts/gap_audit_v3.py` for the working template.

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| **Incomplete section coverage** — audit checks 18 sections when spec has 26+ (user calls out hallucination) | Re-read FULL spec. Count actual TOC entries. Expand audit to cover EVERY section before declaring compliance. Never trust a partial pass rate. |
| **execute_code sandbox isolation** — script reads 0 files because container can't access `/c/Projects/...` | **Never use execute_code for file-dependent audits.** Write the script to disk via `write_file`, run it via `terminal` from project directory with venv activated. |
| **Inline Python breaks on Windows bash** — quote escaping kills multi-line scripts (`unexpected EOF while looking for matching '...'`) | Always write audit scripts as files, never inline in terminal commands. Use `write_file(path=..., content=...)`. |
| File name mismatch between spec and implementation (spec says `module_1_layer_mapping.py` but actual file is `module_1_layer_classification.py`) | Verify actual file names with `ls src/modules/` **before** writing audit script. Adapt probe paths to reality, not spec text. |
| Overly strict function-name check — spec says `process_tiles_with_vlm` but implementation uses `analyze_all_tiles` | Accept aliases in audit: `hf(m4, "process_tiles_with_vlm") or hf(m4, "analyze_all_tiles")`. Or add missing function as alias/wrapper if spec requires exact name. |
| Missing imports when patching modules (e.g., adding `logger.warning()` without `import logging`) | When adding new functions via `patch`, **always check existing imports first**. Add missing imports in the same or separate patch op. Verify with `python -c "import src.modules.module_X"`. |
| Guessed function name → `ImportError` | Always extract symbols from source with regex before writing imports (see Phase 4) |
| Wrong arg count → `TypeError: missing X argument` | Read the full `def (...)` signature, not just the name |
| Mock returns MagicMock for comparison → `TypeError` | Set specific attributes on mock (`mock.dxfversion = "AC1027"`) matching what source accesses |
| Patching wrong module path (local import) | Use `patch.dict("sys.modules", ...)` or patch the exact string path used in `from X import Y` |
| **Signature-based audit claims 100% but features don't work** — functions exist as stubs returning empty values with TODO comments | After "100%" signature compliance, run Phase 5b: read actual source files and check if critical functions do real work or return stubs. Look for `# TODO`, commented-out API calls, unconditional `return []`. Report REAL functional coverage separately from signature coverage. |
| **Import wiring broken** — entry point imports `from X import Y` but the module file has a different name (e.g. imports `module_1_structured` but actual is `module_2_structured_parsing`) | Before declaring compliance, check every `from ... import ...` in entry points against actual filenames with `os.path.exists()`. A project that passes signature tests can still crash at runtime with `ModuleNotFoundError`. Verify wiring: read the importing file → extract all imports → confirm each target module exists on disk. |
| **Security/error-handling modules defined but never wired** — code exists in `security.py`/`error_handling.py`, unit tests pass, but main pipeline and MCP server never call these functions | After confirming module existence, grep for each public function name across ALL project files. If count ≤ 1 (only the definition itself), flag as "disconnected safety net." A spec-compliant security section requires wiring INTO the pipeline, not just definitions. This was discovered in DXF-MEP Analyzer: `PromptSanitizer`, `WorkspaceGuard`, and `retry_with_fallback` were all defined but never imported by `main.py` or `mcp_server.py`. |
| **GAP audit scans 3681 files → false positives everywhere** — scanning venv/dependencies instead of project code | Phase 7: write a TARGETED GAP audit script that checks SPECIFIC bugs against SPECIFIC modules (20-50 items). Scan ONLY `src/`, exclude `venv/`. A correct GAP report shows FIXED/OPEN per bug ID, not match counts. |
| **`patch()` corrupts regex backslashes** — `\b` becomes `\\b` in Python strings after patching | For complex regex rewrites: use `write_file` instead of `patch()`, or verify the written file contains correct escape sequences by reading it back. |

## Check Types (Building Effective Probes)

| Type | Function | Example | What it verifies |
|------|----------|---------|-----------------|
| `hf(c, n)` | Function existence | `hf(m0, "detect_scale")` | Required function is defined |
| String presence | Pattern/constant | `"SLA" in bn or "sla" in bn.lower()` | Key constant/config exists |
| File existence | Config/artifact | `fe("config/layer_mapping.yaml")` | External file created |
| Regex match | Complex pattern | `re.search(r'def\s+\w+\s*\(', content)` | Method signature format |
| Combined check | Multiple conditions | `"filter" in m1 and "category" in m1` | Feature concept present (even if function name differs) |

## Verification Checklist

- [ ] Full spec read (all sections covered)
- [ ] File names verified with `ls src/modules/` before writing audit script
- [ ] Audit script written as standalone file (not inline or in execute_code sandbox)
- [ ] Audit run → 100% pass rate achieved
- [ ] Gap analysis complete (spec section → file mapping, including name mismatches)
- [ ] All missing files/functions created per spec requirements
- [ ] Tests written against verified source signatures (not guessed)
- [ ] All tests pass (`pytest` exits 0, no failures)
- [ ] No regressions in existing test suite
- [ ] **Functional depth audit complete (Phase 5b)** — read actual source files and verified critical functions do real work (not stubs/TODO comments). Verified modules are wired together. Checked for dead code and disconnected safety nets. Reported REAL functional coverage separately from signature compliance.
- [ ] **Import wiring verified** — every `from ... import ...` in entry points resolves to an actual file on disk. Entry point commands (`python -m src.main analyze`) actually run without `ModuleNotFoundError`. File names match between spec and implementation (or aliases documented).
- [ ] **Safety nets wired into pipeline** — security modules, error handlers, and retry logic are imported AND called from main pipeline/MCP server, not just defined in isolation. Each public function has ≥2 callers across the project (definition + at least one import site).
- [ ] **Targeted GAP audit complete (Phase 7)** — wrote a specific bug-check script that scans ONLY `src/`, verified each known defect individually, no false positives from dependency scanning. Report shows FIXED/OPEN per bug ID.
- [ ] Changes committed with descriptive messages referencing spec sections

## Remediation Phase: Batch Bug Fixing Against Spec

When the gap audit produces a registry of bugs, apply fixes in **parallel waves** — independent modules can be patched simultaneously since they don't share state.

### Wave Strategy

1. **Read all affected files first** (batch reads are parallel and free)
2. **Group patches by independence**: Modules that don't import each other → same wave; dependent modules → sequential
3. **After EACH patch**: Verify the fix against the relevant spec section before moving on — user requires per-patch spec verification, not just end-of-run checks
4. **Format: `BUG-XXX FIX:` prefix** in code comments to link fixes back to the registry

### Per-Patch Spec Verification Protocol

User directive: "Проверять правильность выполнения каждого пункта! После выполнения каждого пункта сверяться с техническим заданием!"

After each patch, immediately verify:
1. Does the fix satisfy the spec requirement? (re-read the relevant §)
2. No regressions introduced? (lint passes, module imports cleanly)
3. The bug registry entry is marked resolved with evidence (diff output + line numbers)

### Common Remediation Patterns Discovered

| Pattern | Fix Approach | Spec Section |
|---------|-------------|--------------|
| Silent exceptions (`except: pass`) | Add `import logging; logger.error(...)` before the swallow | §7 Error Handling, §15 Monitoring |
| Unicode injection bypass in query validators | Decode escapes BEFORE scanning; use raw strings (`r"""` docstrings) to avoid Python interpreting `\uXXXX` | §17 Security |
| Memory leak from global state without cleanup | Add `.reset()` method that closes connections & nulls refs (§14.1) | §14 MCP Server, §8 Resource Management |
| Connection pool leak (graph_db driver not closed on reset) | Check `hasattr(db, 'close')` then close in reset() with try/except | §10 GraphRAG |
| Regex patterns broken by double backslash escaping | When using `patch`, raw strings in old_string/new_string get escaped. Verify the written file actually contains `\b` not `\\b`. Use `write_file` for complex regex rewrites where patch escaping becomes unreliable. | §17 Query Validation |
| **Vision API without retry/circuit breaker** | Add exponential backoff (3 retries, 2^attempt delay) + circuit breaker counter that stops after N consecutive failures. Log each fallback transition. | §8.3 Vision Analysis, §15.2 Retry Logic |
| **Cypher generation without self-correction loop** | Implement `retry_cypher_generation()` that feeds syntax error message back to LLM for 3 attempts with increasing context. Fallback: Python filter over all requirements if Cypher fails. | §10.4 Compliance Check, Step 2-3 |
| **Tile coordinates in pixel units instead of DXF units** | Convert tile step from pixels to DXF coordinate space using DPI/scale factors. Formula: `step_dxf = (tile_size - overlap) / dpi * scale_mm_per_unit`. Verify against §7.2.2 tiling spec. | §7.2.2 Tiling |

### Write-File Pitfall: Unicode Escape Sequences

When using `write_file` to replace a Python file that contains docstrings with literal backslash-u sequences (e.g., `\uXXXX`, `\UXXXXXXXX`), the Python parser interprets these as unicode escape codes. **Fix:** Use raw string docstrings (`r"""..."""`) for any function/docstring that mentions unicode escape patterns, or describe them without using actual `\u` notation.

- **test-driven-development** — TDD cycle for writing individual tests
- **systematic-debugging** — Root cause analysis when tests fail unexpectedly
- **plan** — Writing implementation plans from specifications

## Reference Files

- `references/full-section-audit-technique.md` — Session 2026-07-23: Windows path resolution, cross-platform script base paths, full section coverage technique, TOML validation gotchas
- `references/deep-functional-audit.md` — Phase 5b guide for detecting stubs vs real implementations (TODO comments, dead code, disconnected fallback chains)
- `references/gap-remediation-waves.md` — Session 2026-07-24: Wave-based batch bug fixing pattern, targeted GAP audit script template, verified fix patterns (Vision retry, Cypher self-correction, scale-aware tiling, unicode injection blocking)
- `scripts/check_hermes_integration.py` — MCP tool integration verification: checks 9 tools registered/routed, no duplicates, security validation present, Hermes skill conflicts absent
