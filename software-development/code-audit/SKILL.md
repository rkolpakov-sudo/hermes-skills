---
name: code-audit
description: "Static code audit for large Python files: automated pattern scanning, severity classification, surgical patching with per-patch verification."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audit, static-analysis, code-review, python, quality-assurance, refactoring]
    related_skills: [systematic-debugging, requesting-code-review]
---

# Code Audit — Static Analysis for Python Files

## Overview

When auditing a large Python file (1000+ lines), don't read it linearly. Use **automated pattern scanning** to find latent defects, classify by severity, and apply surgical patches with per-patch verification.

**Core principle:** Find bugs via code patterns first, human review second. Read selectively — target only the hotspots your scanner flags.

## When to Use

- Auditing a large file before making changes (avoid breaking existing logic)
- Post-hoc review after multiple developers patched the same file
- Security/reliability audit of critical infrastructure code
- Before merging a PR that touches a complex module
- **Multi-file architectural audit** — user demands "глубокий критический анализ" (deep critical analysis): go beyond single-file patterns and check cross-module wiring, dead code paths, stubs vs real implementations, and spec violations hidden as hardcoded defaults

## The Audit Pipeline

### Phase 1: Structural Mapping

Before scanning for bugs, understand the file topology.

```python
import ast, os

path = "/path/to/file.py"
with open(path) as f:
    tree = ast.parse(f.read())

# Count functions by scope
funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
print(f"Functions: {len(funcs)}, Classes: {len(classes)}")

# Map line ranges for critical functions
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and 'critical_function' in node.name:
        print(f"{node.name}: L{node.lineno}-L{node.end_lineno}")
```

**Deliverable:** A map of function names → line ranges for the target file.

### Phase 2: Automated Pattern Scanning

Run targeted scans against known bug patterns. **Batch these into a single script** — don't run them one-by-one in terminal.

#### Critical Patterns (scan first):

```python
# Undefined references — functions called but never defined
import re
with open(path) as f:
    content = f.read()
called_but_undefined = []
for match in re.finditer(r'(?<!def\s)(\w+)\s*\(', content):
    name = match.group(1)
    if not re.search(rf'def {name}\b', content) and not re.search(rf'from .+ import .*{name}', content):
        called_but_undefined.append(name)

# Schema/enum mismatches — values dispatched but not declared in validation lists
dispatch_modes = re.findall(r'(?:elif|if)\s+\w+\s*==\s*"([^"]+)"', content)
schema_enum = re.search(r'"enum"\s*:\s*\[(.*?)\]', content)
missing_from_schema = [m for m in dispatch_modes if schema_enum and m not in schema_enum.group(1)]

# Silent error swallowing — except...pass with no logging
for i, line in enumerate(content.split('\n'), 1):
    if 'except' in line:
        # Check next non-empty line is bare pass
        ...
```

#### High-Severity Patterns:

```python
# Missing input validation on public functions — check for type/state guards
# Race conditions — global mutable state without locks
global_mutables = re.findall(r'^(\w+)\s*=\s*(\{\}|\[\]|None|False)', content, re.MULTILINE)
has_locking = 'threading.Lock' in content or 'multiprocessing.Lock' in content

# State machine inconsistencies — transitions without guards
state_assignments = re.findall(r'\["state"\]\s*=\s*"([^"]+)"', content)
guard_checks = re.findall(r'\["state"\]\s*(?:==|in)\s*', content)
unguarded_transitions = len(state_assignments) > len(guard_checks)  # rough heuristic

# Graph/data structure mutations without persistence — modify in-memory but don't save
graph_mutations = re.findall(r'graph\["nodes"\]\.pop\(|graph\["edges"\]', content)
save_calls = content.count('_save_journal') or content.count('db.commit()')
```

#### Medium-Severity Patterns:

```python
# Parameter validation gaps — functions that accept unbounded integers/strings
# Memory leaks — growing global dicts without cleanup
global_dicts = re.findall(r'^(\\w+)\\s*=\\s*\\{\\}', content, re.MULTILINE)
cleanup_patterns = 'pop' in content or '.clear()' in content

# Threshold parameters hardcoded — should be configurable
thresholds = re.findall(r'>=?\\s*(\\d+)', content)  # magic numbers in comparisons
```

#### Multi-File Architectural Patterns (DEEP ANALYSIS):

When auditing an entire project (not just one file), check these cross-module patterns:

```python
# 1. Stub detection — functions that return empty values unconditionally
import re
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    # Functions returning empty containers without conditional logic
    stubs = re.findall(r'return\s+(?:\[\]|\{\}|None)\s*$' + r'|# TODO:' , content, re.MULTILINE)
    
# 1b. Commented-out real implementations — code exists but is disabled
# Pattern: actual function call followed by return of empty value on next line
commented_impls = re.findall(r'#\s*\w+\s*=\s*(?:call_|invoke_)', content, re.MULTILINE)
if commented_impls:
    print(f"⚠️ Commented-out implementation calls found — feature is non-functional")

# 2. Dead code — functions defined but never called outside own file
from collections import Counter
all_calls = Counter()
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    # Find all function calls (name followed by parenthesis)
    for call in re.findall(r'(\w+)\s*\(', content):
        if not call.startswith('_'): all_calls[call] += 1

# Functions defined in one file, called only within that same file → potentially dead code path
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    for func_name in re.findall(r'^def\s+(\w+)', content, re.MULTILINE):
        if all_calls.get(func_name, 0) == 1:  # Only self-reference (the def itself)
            print(f"⚠️ {py_file}: '{func_name}' may be dead code — never called from other files")

# 3. Disconnected safety nets — error handlers/fallbacks not wired to real modules
fallback_functions = grep_project("def.*fallback", "src/")
for fb in fallback_functions:
    func_name = extract_function_name(fb)
    call_count = grep_count(f"\\b{func_name}\\b", project_dir)
    if call_count <= 2:  # Only definition + docstring reference
        print(f"⚠️ '{func_name}' exists but is NEVER invoked — disconnected safety net")

# 3b. Verify fallback wiring — a class with execute_fallbacks() should be 
# imported and called from the modules it protects
import grep_results for "FallbackMatrix|retry_with_fallback" in vision/fusion/graph modules
if no import found: print("⚠️ Fallback infrastructure exists but is disconnected from pipeline")

# 4. Hardcoded defaults that contradict spec claims
config_defaults = grep_project(r'or\s+["\']', "src/")
# Each match reveals a hardcoded fallback when config value is missing/empty
# CRITICAL: If spec says "ноль захардкоженных моделей" (zero hardcoded models), 
# any `model or "qwen3-235b"` pattern is a spec violation

# 4b. Hardcoded defaults as ValueError vs silent degradation
# Prefer explicit ValueError over silently using wrong defaults — user should know config is missing
grep_project(r'or\s+["\']default', "src/") → should raise ValueError instead

# 5. Memory leaks in long-lived processes — global state without cleanup
global_state = grep_project(r"^(\\w+)\\s*=\\s*(AnalysisState|GlobalState|Session)", "src/")
cleanup_calls = grep_count("del STATE|STATE.*= None|reset()", project_dir)
if len(global_state) and not cleanup_calls:
    print(f"⚠️ {len(global_state)} global state objects with NO cleanup mechanism — memory leak risk")

# 5b. Add reset/cleanup method to global state classes
# Pattern: @dataclass with doc=None → needs .reset() method that sets all fields to defaults
grep_project(r"@dataclass.*\\n.*doc:\\s*object\\s*=\\s*None", "src/")

# 6. Thread safety audit — mutable globals without locks
threading_imports = grep_count("import threading|from threading import Lock", project_dir)
mutable_globals = grep_count(r"^(counters|histograms|gauges|errors)\\s*=\\s*(?:\\{\\}|\\[\\])", "src/")
if mutable_globals > threading_imports:
    print(f"⚠️ {mutable_globals} mutable globals but only {threading_imports} lock(s) — race condition risk")

# 7. Query language injection (Cypher, SQL-like) — whitelist approach
grep_project(r"_validate_.*\\(query\\)", project_dir)
# Verify: blocks ALL write keywords (MERGE, CREATE, DELETE, SET, REMOVE), not just some

# 8. Import wiring audit — imported modules actually exist?
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    for imp in re.findall(r"from\\s+([\\w.]+)\\s+import", content):
        mod_path = imp.replace(".", "/") + ".py"
        if not os.path.exists(mod_path):
            # Also check as package __init__.py
            pkg_path = imp.replace(".", "/") + "/__init__.py"
            if not os.path.exists(pkg_path):
                print(f"⚠️ {py_file}: imports '{imp}' but no matching file found — ModuleNotFoundError at runtime")

# 9. Disconnected safety nets — modules defined in dedicated files, never imported by callers
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    # Find all public function defs (not starting with _)
    funcs = [m for m in re.findall(r'^def\\s+(\\w+)', content, re.MULTILINE) if not m.startswith('_')]
    for fn in funcs:
        callers = grep_count(f"import.*{fn}|from.*import.*{fn}", project_dir)
        if callers <= 1:  # Only the definition itself
            print(f"⚠️ {py_file}: '{fn}' defined but NEVER imported elsewhere — disconnected safety net")

# 10. Orphaned modules — files exist but nothing imports them by module name
all_imports = set()
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    for imp in re.findall(r"from\\s+([\\w.]+)\\s+import|import\\s+(\\w+)", content):
        all_imports.update([x.strip() for x in imp.split("|") if x])

for py_file in glob("src/**/*.py", recursive=True):
    stem = Path(py_file).stem.replace("_", ".")  # e.g. cli_agent → cli.agent
    module_name = "src." + stem
    if module_name not in all_imports and "__init__" not in stem:
        print(f"⚠️ {py_file}: possibly orphaned — no other file imports this module")

# 11. Numbering conflicts — modules sharing the same numeric prefix (semantically confusing)
module_stems = [Path(f).stem for f in glob("src/modules/module_*.py")]
prefixes = Counter("_".join(s.split("_")[:2]) for s in module_stems)
for prefix, count in prefixes.items():
    if count > 1:
        print(f"⚠️ Numbering conflict: {count} modules share prefix '{prefix}' — semantically ambiguous")

# 12. MCP server audit — stdio transport, thread safety, UTF-8 encoding
mcp_server = read_file("src/mcp_server.py") if exists("src/mcp_server.py") else ""
if mcp_server:
    # Hermes Desktop REQUIRES stdio JSON-RPC (not HTTP)
    has_stdio = "sys.stdin" in mcp_server or "stdin.readline" in mcp_server
    has_http_only = ("Flask(" in mcp_server or "FastAPI()" in mcp_server) and not has_stdio
    if has_http_only: print("⚠️ MCP server uses HTTP-only — Hermes requires stdio JSON-RPC")

    # Global mutable state without locks → race conditions on parallel tool calls
    has_global_state = bool(re.search(r"^(\\w+)\\s*=\\s*(AnalysisState|GlobalState)", mcp_server, re.M))
    has_locking = "threading.Lock" in mcp_server or "asyncio.Lock" in mcp_server
    if has_global_state and not has_locking: print("⚠️ MCP server: global mutable state without thread locks")

    # UTF-8 encoding on Windows stdout (Cyrillic through stdio crashes without reconfigure)
    has_utf8_fix = "reconfigure" in mcp_server or "ensure_ascii=True" in mcp_server
    if not has_utf8_fix and "json.dumps" in mcp_server: print("⚠️ MCP server: no UTF-8 stdout fix — will crash on Windows")

# 13. ezdxf-specific pitfalls (version-dependent)
for py_file in glob("src/**/*.py", recursive=True):
    with open(py_file) as f: content = f.read()
    if "import ezdxf" in content or "ezdxf.readfile" in content:
        # doc.layers returns ONLY table entries, NOT entity layers (ezdxf 1.4.x)
        has_doc_layers = bool(re.search(r"\.layers\\b", content))
        uses_entity_layers = "[e.dxf.layer for e in" in content or "for e in doc.modelspace()" in content
        if has_doc_layers and not uses_entity_layers: print(f"⚠️ {py_file}: uses .layers — ezdxf 1.4.x returns empty layer table")
```\n\nSee also: `references/dxf-mep-analyzer-architectural-findings.md` for a complete case study of 11 architectural issues found and fixed in a real project.

See also: `references/multi-module-pipeline-repair.md` for the ordered repair sequence when fixing cascading import/signature bugs across interconnected Python modules (session-proven on DXF-MEP Analyzer, commit e3ab1f6).
```

### Phase 3: Severity Classification

Classify each finding into a severity tier. This determines fix priority:

| Tier | Criteria | Fix Before Use? |
|------|----------|-----------------|
| 🔴 Critical | Undefined references, data loss risk, silent crashes, **stub functions returning empty values (feature non-functional)** | YES — block deployment |
| 🟠 High | Race conditions, missing validation, dangling state refs, **disconnected error handlers/fallbacks**, global memory leaks | YES — within same session |
| 🟡 Medium | Hardcoded thresholds, missing logging, memory leaks | SOON — document and schedule |
| 🔵 Low/Info | Style inconsistencies, redundant code paths | WHENEVER — backlog item |

### Phase 4: Surgical Patching

**Rules:**

1. **One bug → one patch.** Don't bundle fixes in a single `patch()` call unless they're on adjacent lines (< 5 lines apart).
2. **Read before write.** Verify the exact string you're replacing exists at the expected line number — files shift after each patch.
3. **Preserve intent.** If the existing code has a comment explaining WHY, keep it and append your fix rationale.
4. **Verify lint after each patch.** The `patch` tool auto-runs syntax checks — if it fails, read the affected region and re-patch with correct context.

```python
# Pattern for a safe surgical patch:
patch(
    mode="replace",
    path="/path/to/file.py",
    old_string="<exact existing code, including surrounding context>",  # MUST be unique
    new_string="<fixed code — minimal diff>",  # change only what's broken
)
```

### Phase 5: Post-Audit Verification

After all patches:

1. **Syntax check** — `python -m py_compile /path/to/file.py` (auto-done by `patch`)
2. **Import check** — verify the module loads without errors
3. **Regression scan** — re-run your Phase 2 patterns to confirm findings are resolved:

```python
# Re-scan for silent pass blocks — should return fewer results
silent_passes = find_silent_except_pass(path)
print(f"Remaining silent passes: {len(silent_passes)} (was {original_count})")
```

## Common Bug Patterns by Category

### Error Handling
- `except Exception: pass` → always log the exception, even at debug level
- Missing error type specificity → catch `FileNotFoundError`, `json.JSONDecodeError` instead of bare `Exception`
- Double-except nesting with inner `pass` swallows outer context

### Security / Injection
- **Unicode escape bypass**: Query validators that check for forbidden keywords but don't decode `\uXXXX`/`\UXXXXXXXX` first are vulnerable. Attackers encode `DELETE` as `\u0044\u0065\u006c...`. Fix: `.encode('utf-8').decode('unicode_escape')` BEFORE scanning, wrapped in try/except for malformed sequences.
- **Docstring gotcha**: Python interprets `\uXXXX` inside regular docstrings (`"""..."""`). Use raw docstrings (`r"""..."""`) when documenting unicode escape patterns — or describe them without literal backslash-u notation. Otherwise `write_file()` produces a syntax error.
- **Double-backslash in regex via `patch`**: When `patch()` writes strings containing `\b`, `\w`, etc., the tool layer can double-escape to `\\b`. Verify written output actually contains single-backslash patterns. Prefer `write_file` for files with dense regex content where patch escaping is unreliable.
### State Machines
- Transition without guard check → verify current state before changing it
- Terminal state overwrite (e.g., setting "stopped" on already "completed") → return early, don't mutate
- Missing inverse transition (pause→resume exists but not resume→pause validation)

### Data Persistence
- In-memory mutation without save → every graph/DB change must call `_save_journal()` or `commit()`
- Rollback removes nodes but not edges → always clean dangling references
- Global counter dict grows unbounded → cleanup on terminal state events

### Concurrency
- Lazy init without lock → double-checked locking pattern: check → acquire → re-check → initialize
- TOCTOU on file operations → use atomic rename (`os.replace`) for writes
- Shared mutable globals in multi-process context → use `threading.Lock` or process-safe alternatives

## Deliverable Format

After a complete audit, produce a structured report:

```markdown
# Audit Report — <file>

| # | Bug | Severity | Line(s) | Fix Applied? |
|---|-----|----------|---------|--------------|
| 1 | ... | 🔴 Critical | L... | ✅ Patched    |
| 2 | ... | 🟠 High     | L...   | ✅ Patched    |

## Summary
- Total findings: N
- Resolved: M (X%)
- Deferred: K (with rationale)
```

## Red Flags — STOP and Rethink

- **3+ patches to the same line range** → the area is fundamentally broken; refactor, don't patch
- **Patch fails lint twice** → you're fighting the file's structure; read more context before retrying
- **Findings exceed 20% of lines** → this isn't an audit, it's a rewrite
- **Signature-based compliance says 100%, but features don't work** → functions exist as stubs with TODO comments returning empty values. Run multi-file architectural scan (Phase 2b) to find real functional coverage vs nominal code presence

## Integration with Other Skills

| Skill | When to Use Together |
|-------|---------------------|
| `systematic-debugging` | After audit finds a bug you need to reproduce and verify |
| `requesting-code-review` | Before submitting audited file as a PR — run security scan + quality gates |
| `writing-plans` | If audit reveals architectural issues requiring multi-session refactoring |
