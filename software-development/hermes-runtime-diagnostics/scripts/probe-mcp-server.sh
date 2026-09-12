#!/usr/bin/env bash
# probe-mcp-server.sh — verify a stdio MCP server starts and answers initialize.
# Usage: probe-mcp-server.sh '<command...>' [timeout_s]
# Examples:
#   probe-mcp-server.sh 'npx.cmd -y @upstash/context7-mcp' 30
#   probe-mcp-server.sh 'C:/Projects/dxf-mep-analyzer/.venv/Scripts/python.exe src/mcp_server.py' 30   (run from project dir)
# A healthy server replies with a JSON-RPC "result" containing serverInfo/capabilities.
# An npm 404 or a crash line in stderr means the package name or config is wrong.
set -u
CMD="$1"
TIMEOUT="${2:-30}"
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'
echo "$INIT" | timeout "$TIMEOUT" bash -c "$CMD" 2>/tmp/mcp_probe_err.txt | head -c 400
echo
echo "EXIT:$?"
tail -3 /tmp/mcp_probe_err.txt
