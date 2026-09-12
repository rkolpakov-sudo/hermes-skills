# Session 2026-07-23: DXF MEP Analyzer Full Build

## Key Lessons Learned

### 1. API Mismatch Between Spec and Source (Critical Pattern)

**Problem:** Tests written against spec names (`FusedEntity`, `resolve_conflicts`) failed with import errors because actual module exports differed (`FusionResult`, `calculate_discrepancy`).

**Fix:** Read source file directly via `read_file` to discover real public signatures. Do NOT guess at corrections or rewrite tests blindly from assumptions about naming conventions.

**Rule: Source code > spec documentation when resolving API mismatches.**

### 2. Context Recovery Protocol (Empty Responses After Tool Calls)

Three instances of empty assistant responses after tool calls were resolved via forced protocol:
1. Manual parsing of `read_file` results by offset/line number from spec document
2. File structure verification against TZ sections (§§9-13, then §§14-24)
3. Direct continuation in main flow — no delegation to background agents

### 3. Test Fix Patterns (This Session)

| Module | Issue | Resolution |
|--------|-------|------------|
| `module_5_fusion.py` | Import mismatch: spec names vs actual exports | Read source, rewrite imports |
| `error_handling.py` | Logger keyword args treated as positional by `logging.warning()` | Switch to `%s` format strings with explicit arguments |
| `mcp_server.py` | `re` imported inside function scope, unavailable in `_validate_cypher()` at module level | Move import to top of file |
| `security.py` — DXF validation | `open(path, "rb", encoding="latin-1")` — binary mode rejects encoding param | Remove `encoding=`; use `.decode("latin-1")` on bytes if needed |
| `security.py` — injection patterns | `\s+` too strict for test inputs without whitespace | Added broader patterns: `(?:ignore\|override)\s+(?:previous\|all)` |
| `security.py` — endpoint validation | Regex accepted bare strings as valid hosts | Added check: no scheme requires a dot in hostname |

### 4. Logger Compatibility (Standard vs structlog)

When using standard Python `logging` module, calls like `logger.warning("msg", key=value)` fail because positional args are expected after the message. Use format strings instead:
```python
# WRONG — keyword args not accepted by stdlib logging
logger.warning("retry_attempt", module=module_name, attempt=attempt)

# CORRECT — format string with positional args
logger.warning(
    "retry_attempt | module=%s | attempt=%d",
    module_name, attempt,
)
```

### 5. Project Structure Achieved (Reference Point)

```
src/
├── config.py              # Dynamic LLM routing (§13)
├── main.py                # CLI Entry Point (§20)
├── mcp_server.py          # MCP Server — 8 tools (§14)
├── error_handling.py      # Retry + fallback matrix (§15)
├── security.py            # DXF validation, prompt sanitization (§17)
├── logging_config.py      # Structured logging + metrics (§21)
├── modules/
│   ├── module_0_preprocessing.py    (21 tests)
│   ├── module_1_layer_classification.py  (14 tests)
│   ├── module_2_structured_parsing.py    (26 tests)
│   ├── module_3_quantification.py        (19 tests)
│   ├── module_3_rendering.py             (§7, 291 lines)
│   ├── module_4_vision.py                (§8, 334 lines)
│   ├── module_5_fusion.py                (§9, 372 lines)
│   ├── module_6_graphrag.py              (§10, 440 lines)
│   ├── module_7_report.py                (§11, 580 lines)
│   └── module_8_multisheet.py            (§16, cross-sheet aggregation)
├── graphdb/schema.py       (§12, 3 graph types)
└── llm/client.py           (§13, OpenAI-compatible dynamic routing)

tests/ — 155 tests total (all passing in ~1.5s)
benchmarks/benchmark_runner.py — SLA ≤420s pipeline timing
docs/spec_v1.0.0.md — Full specification (~2709 lines, 29 sections)
```

### 6. Git History (Reference for Future Sessions)

| Commit | Message | Sections Covered |
|--------|---------|-----------------|
| `d282747` | Remove hardcoded LLM names from spec v1.0.0 | Spec cleanup |
| `a0a19c1` | Modules 5-7 + GraphDB Schema + LLM Client (§9-13) | Core pipeline |
| `685a18f` | MCP Server, Error Handling, Logging, CLI Entry Point (§14-21, §20) | Infrastructure |
| `d3118fd` | Security Model, Performance Benchmark (§17, §18) | Security + performance |
| `83eb169` | Multi-Sheet Support (§16) — cross-sheet aggregation, duplicates | Cross-sheet analysis |
| `6e85f82` | README.md + pyproject.toml (setup, CLI entry point) | Documentation |

### 7. Configuration Without Hardcoded LLM Names

All model references replaced with `{LLM_STRUCTURED_MODEL}`, `{LLM_VISION_MODEL}` placeholders in spec and code. Dynamic routing via `src/config.py`:
```python
# Via environment variables
os.environ.get("LLM_STRUCTURED_MODEL", "default")
os.environ.get("VISION_ENDPOINT", "http://localhost:1234/v1/chat/completions")
```

No model names hardcoded in any source file — verified via `search_files`.
