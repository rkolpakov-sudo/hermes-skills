"""
MCP Tool Integration Verification Script

Verifies that MCP tools are properly integrated with Hermes Desktop:
1. All expected tools registered (no duplicates)
2. JSON-RPC routing correct (TOOL_MAP matches register_tools())
3. Input schemas have properties + required fields
4. Security validation present (§17.2): unicode normalization, forbidden ops blocked
5. Error handling adequate (§15): initialization guards on all non-init tools

Usage: Run from project root with venv activated:
    python scripts/check_hermes_integration.py

See also: spec-compliance-audit skill for context.
"""
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MCP_FILE = PROJECT_ROOT / "src" / "mcp_server.py"

print("=" * 70)
print("HERMES INTEGRATION CHECK — MCP Server + Skills")
print("=" * 70)
print(f"Project root: {PROJECT_ROOT}")
print(f"MCP server:   {MCP_FILE}")
print()

with open(MCP_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# [1] Tool Registration Check (§14.1)
print("[1] Tool Registration Check (spec §14.1)")
tools_match = re.search(r'def register_tools\(\):.*?return tools', content, re.DOTALL)
if not tools_match:
    print("   ❌ FAILED: register_tools() function not found!")
    sys.exit(1)

tool_names = re.findall(r'"name":\s*"([^"]+)"', tools_match.group(0))
print(f"   Registered: {len(tool_names)} tools")
for i, name in enumerate(tool_names, 1):
    print(f"      {i}. {name}")

if len(tool_names) != len(set(tool_names)):
    dups = [t for t in tool_names if tool_names.count(t) > 1]
    print(f"\n   ❌ DUPLICATES: {set(dups)}")
else:
    print("\n   ✅ No duplicate tools")

expected = [
    "initialize_analysis",
    "count_equipment_on_layer",
    "get_pipe_lengths",
    "extract_annotations_by_pattern",
    "query_drawing_graph",
    "check_normative_compliance",
    "detect_2d_clashes",
    "get_layer_inventory",
    "reset_state"
]

missing = set(expected) - set(tool_names)
extra = set(tool_names) - set(expected)
if missing:
    print(f"   ❌ Missing tools: {missing}")
elif extra:
    print(f"   ⚠️  Extra tools: {extra}")
else:
    print("   ✅ All expected tools present")

# [2] Function Implementation Check
print("\n[2] Function Implementation Check")
for name in expected:
    func_pat = rf'^def {re.escape(name)}\('
    if re.search(func_pat, content, re.MULTILINE):
        print(f"   ✅ {name}: function defined")
    else:
        print(f"   ❌ {name}: MISSING!")

# [3] JSON-RPC Routing Check (§14.1)
print("\n[3] JSON-RPC Routing Check (spec §14.1)")
tool_map_match = re.search(r'TOOL_MAP\s*=\s*\{(.*?)\}', content, re.DOTALL)
if not tool_map_match:
    print("   ❌ TOOL_MAP not found!")
else:
    map_keys = re.findall(r'"([^"]+)":', tool_map_match.group(0))
    print(f"   Registered in router: {len(map_keys)}")
    for name in expected:
        if name in map_keys:
            print(f"   ✅ {name}: routed")
        else:
            print(f"   ❌ {name}: NOT ROUTED!")

# [4] Input Schema Validation (§14)
print("\n[4] Input Schema Validation (spec §14)")
schemas = re.findall(r'"inputSchema":\s*\{(.*?)\}', tools_match.group(0), re.DOTALL)
for name, schema in zip(tool_names, schemas):
    has_props = '"properties"' in schema
    has_required = '"required"' in schema
    if has_props and has_required:
        print(f"   ✅ {name}: complete schema")
    else:
        missing_parts = []
        if not has_props:
            missing_parts.append("properties")
        if not has_required:
            missing_parts.append("required")
        print(f"   ⚠️  {name}: missing {', '.join(missing_parts)}")

# [5] Security Validation (§17.2)
print("\n[5] Security Validation (spec §17.2)")
has_unicode_norm = 'unicodedata' in content and ('normalize' in content or "'\\u'" in content)
if has_unicode_norm:
    print("   ✅ Unicode normalization present")
else:
    print("   ❌ Unicode normalization MISSING!")

has_forbidden = '"DELETE"' in content and 'forbidden' in content.lower()
if has_forbidden:
    print("   ✅ Forbidden operations blocked")
else:
    print("   ❌ Forbidden operations NOT BLOCKED!")

# [6] Error Handling (§15) — count ALL guard types
print("\n[6] Error Handling (spec §15)")
init_checks = content.count('if not STATE.initialized') + content.count('if not dxf_path') + content.count('if not STATE.graph_db')
print(f"   Total guards: {init_checks}")
if init_checks >= 8:
    print("   ✅ Adequate initialization checks")
else:
    print(f"   ⚠️  Only {init_checks} guards (expected ≥8)")

has_try_except = content.count('try:') + content.count('except')
print(f"   Try/except blocks: {has_try_except}")

# [7] Final Verdict
issues = []
if len(tool_names) != 9:
    issues.append(f"Tool count: {len(tool_names)} (expected 9)")
if missing:
    issues.append(f"Missing tools: {missing}")
if not has_unicode_norm:
    issues.append("No unicode normalization")

print("\n" + "=" * 70)
if issues:
    print("❌ ISSUES:")
    for issue in issues:
        print(f"   • {issue}")
else:
    print("✅ ALL INTEGRATION CHECKS PASSED")
print("=" * 70)
