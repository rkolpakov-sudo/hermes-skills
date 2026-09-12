---
name: spec-verification
description: "Cross-check codebase implementation against specification document. Section-by-section gap analysis with honest status reporting."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [specification, requirements, verification, gap-analysis]
    related_skills: [code-audit, writing-plans]
---

# Specification Verification — Implementation Gap Analysis

## Trigger

- User provides a spec/requirements doc and asks "what's implemented vs missing"
- Need to verify codebase against a spec after development phases
- User demands section-by-section comparison with implementation status

## Core Principle

**HONESTY OVER OPTIMISM.** Never claim sections are implemented unless actual code exists. Status lines must be independently verifiable from file system evidence, not inference. The user has explicitly called out contradictory reporting (saying "not implemented" then claiming "complete") as unacceptable — every status line must match the detail rows exactly.

**CRITICAL: Cover EVERY section.** In session 2026-07-23, an audit checked ~18 of 29 spec sections and declared "87% compliance" while missing entire chapters (§§1-3 Architecture/Tech Stack/Data Flow). The user called this out directly. Before declaring any coverage percentage, verify the check count matches the actual number of sections in the TOC.

## Workflow

### Phase 1: Save Spec Locally

Always save the spec document to `docs/spec_v{VERSION}.md` so future sessions can reference it without re-attaching context.

### Phase 2: Enumerate Spec Sections

Parse TOC/section headers. Distinguish:
- **Code sections** — require actual implementation (modules, algorithms)
- **Documentation sections** — descriptive only (glossary, hardware sizing)
- **Operational sections** — deployment, monitoring, maintenance

### Phase 3: Map Code to Sections

For each code section:
1. Search for corresponding module in `src/modules/` or equivalent
2. Verify functions exist by scanning `def` declarations (not just file presence)
3. Cross-check function signatures against spec requirements
4. **Pitfall — API mismatch between spec and source:** Spec documents often use placeholder names (`FusedEntity`, `resolve_conflicts`) that differ from actual implementation (`FusionResult`, `calculate_discrepancy`). When test imports fail, READ the source file to discover real public signatures — source code is authoritative over spec documentation.
5. Mark status based on EVIDENCE only:

| Status | Criteria |
|--------|----------|
| ✅ Implemented | Module exists, matching functions, tests pass |
| ⚠️ Partial | Module exists but missing key algorithms from spec |
| ❌ Not implemented | No code found; module absent or empty stub |

### Phase 4: Produce Report

Format as table: `§`, Name, Status, Evidence.

**CRITICAL RULES:**
- Each row independently verifiable from file system state
- Do NOT summarize "X out of Y done" unless math actually checks out
- If implementation deviates (e.g., built Quantification instead of Rendering), flag explicitly as DEVIATION — do not count as matching

### Reference: Session notes for DXF MEP Analyzer project → `references/session-2026-07-23-dxf-mep.md`

## Common Pitfalls

1. **Contradictory summaries** — Saying sections missing in detail but claiming "90% done" in summary. Summary MUST match detail rows exactly.
2. **Counting wrong modules** — Module 3 exists but implements different functionality than spec §7 requires. This is a DEVIATION, not completion.
3. **Inferring from tests alone** — Tests passing ≠ production code matches spec. Check source modules directly.
4. **Incomplete section coverage** — Audit script checks subset of sections and declares high compliance while missing entire chapters. User will call this out. Always verify check count against TOC before reporting.
5. **Windows path resolution in audit scripts** — Hardcoded `/c/Projects/...` paths fail when Python runs from MSYS bash context. Use `Path(__file__).resolve().parent.parent` for cross-platform script-relative base paths (see `spec-compliance-audit` skill for details).

## Integration

| Skill | When |
|-------|------|
| `writing-plans` | After verification reveals gaps |
| `code-audit` | To audit implemented sections for quality |
