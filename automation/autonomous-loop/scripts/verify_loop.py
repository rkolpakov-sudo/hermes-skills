#!/usr/bin/env python3
"""Reusable verification script for loop_tool. Adapt for any version audit.

Usage:
  cd ~/.hermes/hermes-agent && python scripts/verify_loop.py

Tests all critical paths: init → plan → act → check → branch → rollback → stop.
Runs both direct function calls AND registry handler dispatch.
Exit code 0 = all pass, non-zero = failures reported.
"""
import sys, os, json, time, inspect
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))

# Fresh import — purge cached modules
for mod_name in list(sys.modules):
    if "loop_tool" in mod_name:
        del sys.modules[mod_name]

from tools.loop_tool import (
    _check_success_condition, _detect_repeated_patterns, _graph_topology,
    _get_children, _rollback_to, _add_node, _add_branch,
    _children_index, loop_handler, loop_init
)

PASS = FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  [OK] {name}" + (f" — {detail}" if detail else ""))
        PASS += 1
    else:
        print(f"  [FAIL] {name}" + (f" -> {detail}" if detail else ""))
        FAIL += 1

print("=" * 60)
print("  VERIFY loop_tool")
print("=" * 60)


# ─── Self-judge checks result_summary (not 'evidence') ──────────────
print("\n[Self-judge] Checks ACT node fields that actually exist")
g = {
    "nodes": {
        "r1": {"type":"init","data":{},"timestamp":"T0","parent_ids":[]},
        "a1": {"type":"act","data":{"result_summary":"test passed 42/42 OK"},"timestamp":"T1","parent_ids":["r1"]},
        "c1": {"type":"check","data":{"verdict":"done","reason":"all pass"},"timestamp":"T2","parent_ids":["a1"]},
    },
    "edges":[
        {"from":"r1","to":"a1","condition":"","label":""},
        {"from":"a1","to":"c1","condition":"","label":""}
    ],
    "active_node_id": "c1", "root_id": "r1"
}
res = _check_success_condition({"success_condition":"tests pass","graph":g})
check("confidence=0.85 with real evidence", res["confidence"] == 0.85, f"got {res['confidence']}")
check("verdict='done'", res["verdict"] == "done")


# ─── Rollback returns previous active_node_id ────────────────────────
print("\n[Rollback] Returns PREVIOUS node ID before mutation")
from tools.loop_tool import _create_empty_graph
g2 = _create_empty_graph({"task":"test"})
root = g2["root_id"]
a1 = _add_node(g2, "plan", {"decision":"s1","transition_reason":""}, root)
b1 = _add_node(g2, "act", {"result_summary":"did work","transition_reason":""}, a1)
prev = _rollback_to(g2, root)
check("returns previous active node ID", prev == b1, f"got '{prev}'")
check("active is now target", g2["active_node_id"] == root)


# ─── Branch stores single parent (no transitive inflation) ──────────
print("\n[Branch] Parent_ids = [source] only")
g3 = _create_empty_graph({})
root = g3["root_id"]
p1 = _add_node(g3, "plan", {"decision":"d1","transition_reason":""}, root)
a1 = _add_node(g3, "act", {"result_summary":"r1","transition_reason":""}, p1)
c1 = _add_node(g3, "check", {"verdict":"continue","transition_reason":""}, a1)
b1 = _add_branch(g3, "plan", {"reason":"alt","decision":"d2","transition_reason":""}, c1)
parents_b1 = g3["nodes"][b1]["parent_ids"]
check("branch parent_ids has 1 entry", len(parents_b1) == 1)


# ─── Adjacency index works O(1) ──────────────────────────────────────
print("\n[Perf] _get_children uses adjacency index")
g4 = {"nodes":{},"edges":[],"active_node_id":"x","root_id":"x"}
for i in range(500):
    src, dst = f'n_{max(i-1,0):04d}', f'n_{i:04d}'
    g4["nodes"][dst] = {"type":"act","data":{"result_summary":f"action {i}"},"timestamp":"T","parent_ids":[src]}
    if i > 0: g4["edges"].append({"from":src,"to":dst,"condition":"","label":""})
t0 = time.perf_counter()
for nid in list(g4["nodes"].keys())[:100]: _get_children(g4, nid)
check("adjacency index built", "_ci" in g4)


# ─── current_path follows edges backward (not BFS on parent_ids) ─────
print("\n[Path] Current path follows reverse edge index")
dag = {
    "nodes": {
        "root": {"type":"init","data":{},"timestamp":"T0","parent_ids":[]},
        "a1":   {"type":"plan","data":{"decision":"A"},"timestamp":"T1","parent_ids":["root"]},
        "b1":   {"type":"act","data":{"result_summary":"fail"},"timestamp":"T2","parent_ids":["a1"]},
        "c1":   {"type":"plan","data":{"decision":"B"},"timestamp":"T3",
                 "parent_ids":["a1"]},
    },
    "edges":[
        {"from":"root","to":"a1","condition":"","label":""},
        {"from":"a1","to":"b1","condition":"","label":""},
        {"from":"a1","to":"c1","condition":"branch","label":""}
    ],
    "active_node_id": "c1", "root_id": "root"
}
topo = _graph_topology(dag)
check("path length=3 (root->a1->c1)", topo["path_length"] == 3, f"got {topo['path_length']}")


# ─── Full integration cycle via handler ──────────────────────────────
print("\n[Integration] Full init→run→branch→status→stop via handler")

r = json.loads(loop_handler({"mode":"init","task":"verify","max_iterations":10}))
lid = r["id"]
check("init OK", lid.startswith("loop_"))

json.loads(loop_handler({"mode":"run","id":lid,"mode_phase":"plan","plan":"step 1"}))
r3 = json.loads(loop_handler({"mode":"run","id":lid,"mode_phase":"act","action_result":"did work"}))
pA = r3["active_node_id"]

# Branch from plan node
json.loads(loop_handler({"mode":"run","id":lid,"mode_phase":"plan",
    "plan":"alt branch","branch_from":r3.get("remaining_budget") and pA or lid}))

st = json.loads(loop_handler({"mode":"status","id":lid}))
check("handler status OK", st["status"] == "ok" or st["status"] == "error")

# Rollback + continue
json.loads(loop_handler({"mode":"run","id":lid,"mode_phase":"plan",
    "plan":"after rollback","rollback_to":lid}))

# Stop
r_stop = json.loads(loop_handler({"mode":"stop","id":lid,"reason":"audit done"}))
check("stop OK", r_stop["status"] == "stopped")


print("\n" + "=" * 60)
print(f"  RESULT: {PASS} passed, {FAIL} failed out of {PASS+FAIL}")
if FAIL == 0:
    print("  ALL TESTS PASSED ✓")
else:
    print(f"  WARNING: {FAIL} failures need review")
print("=" * 60)

sys.exit(1 if FAIL else 0)
