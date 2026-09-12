# Unicode Escape Injection Bypass in Query Validators

Session: 2026-07-24 (DXF MEP Analyzer audit)

## The Vulnerability

Query validators that scan for forbidden keywords (e.g., `DELETE`, `DROP` in Cypher; `DROP TABLE` in SQL) but operate on the raw input string are vulnerable to unicode escape injection. An attacker encodes a forbidden word:

```
# Instead of: MATCH n DELETE n
# Attacker sends: MATCH \u0064\u0065\u006c\u0065\u0074\u0065 n  (DELETE in unicode)
```

The validator sees `\u0064...` — no match for "DELETE". The database engine decodes it and executes the write operation.

## Fix Applied

In `mcp_server.py:_validate_cypher()`:

```python
def _validate_cypher(query: str):
    r"""Validate Cypher query - docstring must be raw string to avoid \u interpretation."""
    
    # Decode unicode escapes BEFORE scanning (§17.2)
    decoded = query
    if '\\u' in query or '\\U' in query or '\\x' in query:
        try:
            decoded = query.encode('utf-8').decode('unicode_escape', errors='replace')
        except (UnicodeDecodeError, UnicodeEncodeError):
            for seq in [r'\u', r'\U', r'\x']:
                decoded = decoded.replace(seq, '')
    
    # Additional: strip control characters
    import unicodedata
    normalized = ''.join(c for c in decoded if not unicodedata.category(c).startswith('C'))
    
    # Now scan the NORMALIZED string (not the original)
    forbidden = ["DELETE", "DROP", "CREATE", "MERGE", "SET ", "REMOVE"]
    for op in forbidden:
        if re.search(r'\b' + op + r'\b', normalized, re.IGNORECASE):
            raise ValueError(f"Forbidden operation: {op}")
```

## The Write-File Gotcha

When writing this fix via `write_file()`, Python's parser interpreted `\uXXXX` inside docstrings as unicode escape sequences, causing a syntax error:
```
SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes in position 304-305
```

**Fix:** Use raw string prefix for the docstring (`r"""..."""`) or describe the pattern without literal `\uXXXX`.

## Patch Tool Gotcha

When using `patch()` to write regex patterns containing `\b` (word boundary), the tool layer double-escaped them to `\\b`, which broke the regex. The written file contained literal backslash-backslash-b instead of word-boundary anchors.

**Fix:** When patching files with dense regex content, verify the output actually contains correct single-backslash patterns. Consider using `write_file` for complete rewrites where escaping is complex.

## Checklist for Query Validators

- [ ] Decode unicode escapes BEFORE keyword scanning
- [ ] Strip control characters (category C) from normalized input
- [ ] Whitelist approach: require read-only keywords present, not just forbidden absent
- [ ] Raw string docstrings when documenting escape patterns
- [ ] Verify regex backslashes aren't double-escaped after patch/write_file
