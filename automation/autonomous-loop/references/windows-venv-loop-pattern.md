# Windows venv Loop Pattern

## Problem

`execute_code` runs in a **Linux sandbox** that cannot access Windows filesystem paths (`C:\Users\...`, `C:\Projects\...`). Writing files via `write_file()` to Windows paths works, but verification (reading those files, running pytest) fails because the Linux sandbox sees a different root.

## Solution: Hybrid Pattern

Use `execute_code` for **file creation** (write_file supports cross-platform paths), then verify with **PowerShell MCP**:

```python
# In execute_code — create files (works):
from hermes_tools import write_file
write_file("C:\\Projects\\VDAS\\src\\module.py", content)

# Record in loop:
run({"mode":"run","id":lid,"mode_phase":"act",
     "action_result": "Created module.py. Verify with pytest via PowerShell."})
```

```powershell
# In mcp_windows_mcp_PowerShell — verify (required for Windows paths):
cd C:\Projects\VDAS; .\.venv\Scripts\python.exe -m pytest tests/ -q --tb=line 2>&1 | Out-String -Width 300
```

## Key Rules

| Tool | Can access `C:\`? | Use for... |
|------|-------------------|------------|
| `execute_code` (write_file) | Yes — writes succeed | File creation, patching |
| `execute_code` (terminal/read_file) | No — Linux sandbox | Python logic, JSON processing, loop_handler calls |
| `mcp_windows_mcp_PowerShell` | Yes | pytest, import verification, file existence checks |

## Loop handler quirk on Windows

`loop_handler()` expects a **dict**, not a JSON string:
```python
from tools.loop_tool import loop_handler
# CORRECT — pass dict directly:
run = lambda args: j.loads(loop_handler(args))  # returns JSON string → parse
run({"mode": "run", "id": lid, ...})

# WRONG — double-encoding:
j.loads(loop_handler(j.dumps(args)))  # crashes with json.JSONDecodeError
```

## Running pytest from PowerShell

Always use explicit venv python to avoid PYTHONPATH pollution:
```powershell
cd C:\Projects\VDAS; .\.venv\Scripts\python.exe -m pytest tests/ -q --tb=line 2>&1 | Out-String -Width 300
```

For verbose output with specific test results:
```powershell
. .venv\Scripts\python.exe -m pytest tests/test_l2_core_engine.py -v 2>&1 | Select-String "PASSED|FAILED" | Out-String
```

## Verify imports from PowerShell

```powershell
cd C:\Projects\VDAS; .\.venv\Scripts\python.exe -c "from src.l3_model import Wall, Room; print('OK')" 2>&1
```

This avoids the Linux sandbox entirely and confirms the Windows venv is correctly configured.
