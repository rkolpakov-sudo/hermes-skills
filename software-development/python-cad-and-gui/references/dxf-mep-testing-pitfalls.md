# DXF-MEP Pipeline Testing Pitfalls

Session-verified patterns from `dxf-mep-analyzer` project (2026-07-23). 155 tests, all passing.

## Logger Compatibility: Standard `logging` vs Structured Logging

When using Python standard `logging` module (not structlog), keyword args after the message string are NOT accepted — they're treated as positional arguments and cause failures:

```python
import logging
logger = logging.getLogger(__name__)

# ❌ WRONG — keyword args not accepted by stdlib logging
logger.warning("retry_attempt", module=module_name, attempt=attempt)
# → TypeError: warning() got multiple values for argument 'msg'

# ✅ CORRECT — format string with positional args
logger.warning(
    "retry_attempt | module=%s | attempt=%d | next_wait=%.1fs",
    module_name, attempt, wait_time,
)
```

**Fix pattern discovered:** When migrating code that uses structlog-style logging to standard logging (or vice versa), all log calls need conversion. The structlog approach (`logger.info("event", key=value)`) is incompatible with `logging.Logger` directly.

## File I/O: Binary Mode Rejects `encoding=` Parameter

```python
# ❌ WRONG — binary mode doesn't accept encoding parameter
with open(path, "rb", encoding="latin-1") as f:
    content = f.read(4096)  # TypeError: can't have both text and binary mode

# ✅ CORRECT — read bytes, decode if needed
with open(path, "rb") as f:
    raw_bytes = f.read(4096)
    content = raw_bytes.decode("latin-1", errors="replace")  # Decode explicitly
```

**Context:** DXF files are text-based but the initial scan for executable attachments (MZ headers) needs binary mode. Separate concerns: security scan reads bytes; DXF parsing uses `ezdxf.readfile()` which handles encoding internally.

## Regex Pitfalls in Security Validation

### URL Endpoint Validation — Bare Strings Pass Permissive Regex

```python
# ❌ TOO PERMISSIVE — accepts "not-a-url-at-all" as valid host
url_match = re.match(r'^(https?://)?([^/:]+)(:\d+)?(/.*)?$', url)

# ✅ ADDITIONAL CHECK — require scheme OR dot in hostname
scheme_part = url_match.group(1)
if not scheme_part and "." not in host:
    return {"valid": False, "issues": ["Invalid URL format"]}
```

### Prompt Injection Patterns — Whitespace Sensitivity

The pattern `r"(?i)ignore\s+(previous|all)\s+instructions"` requires whitespace between tokens. Test inputs like `"ignore.previous.instructions"` (dots instead of spaces) bypass it:

```python
# ✅ BROADER PATTERNS that handle various separators
INJECTION_PATTERNS = [
    r"(?i)ignore[\s.]+(?:previous|all)[\s.]+instructions",  # Handles dots/spaces/tabs
    r"(?i)(?:ignore|override)[\s.]+(?:previous|all)",
]
```

## Testing Infrastructure Code (MCP Server, Error Handling, Security)

### Pattern: Mock External Dependencies Without Simulating Implementation

When testing `mcp_server.py` tools that call downstream modules:
- Mock the **result** of analysis functions (`analyze_dxf_entities`), not their internals
- Test tool input validation separately from business logic
- Use `pytest.mark.parametrize` for multiple valid/invalid input combinations

### Pattern: Error Handling Tests — Verify Fallback Chain Order

```python
# Test that primary_fn is called first, then fallbacks in order
@patch("src.error_handling.retry_with_fallback")
def test_fallback_order(mock_retry):
    calls = []
    def track(fn_name):
        return lambda: (calls.append(fn_name), None)[-1]

    retry_with_fallback(
        primary_fn=track("primary"),
        fallbacks=[track("fb1"), track("fb2")],
        module_name="test",
    )
    # Verify call order: primary attempted, then fallbacks sequentially
```

## DXF File Validation — False Positives on Binary Headers

DXF files start with ASCII text (`ACAD\nDXF`), NOT binary headers. Checking for `b"MZ"` anywhere in the first bytes produces false positives if the check scans too broadly:

```python
# ❌ WRONG — "MZ" could appear coincidentally in DXF header text
if b"MZ" in content[:8]:  # False positive on ACAD/DXF headers

# ✅ CORRECT — check ONLY file start for executable signatures (MZ is at offset 0)
if content[:2] == b"MZ":  # PE/Windows executable signature
```

## Test Fix Workflow (Discovered Pattern)

When tests fail due to API mismatches:
1. **Read source** → `read_file(path="src/module.py", limit=50)` to see actual exports
2. **Compare** test imports vs module's `__all__` or actual `class/def` declarations
3. **Patch tests** — not the source code (source is authoritative)

This pattern resolved 3+ import mismatches in this session without changing production code.

## Cross-Sheet Duplicate Detection — Edge Cases

When aggregating equipment across DXF sheets:
- Equipment with identical properties on different sheets = potential duplicate of same physical asset shown in section view
- Same equipment type appearing on the SAME sheet = NOT a duplicate (just multiple instances)
- Empty property dicts should be skipped entirely to avoid false grouping
