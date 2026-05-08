---
name: critical-component-selection
description: >-
  Use this skill when the user is making a freeze-grade component selection decision for hardware where the choice will be locked into schematic/BOM/pin assignment and at least two critical conditions apply: multi-year lifecycle/EOL/PCN/lead-time risk, toolchain verification such as EMIF/fitter/SI/PI/thermal, pinout/power/SI/thermal architecture impact, or vendor evidence that must be reconciled against requirements. Triggers include: 关键物料选型, BOM 冻结前评审, EOL/PCN 替代, 候选料号决策, vendor 反馈与需求基线对账. Do NOT use for casual comparisons, learning questions, architecture sketches, or selections that do not require evidence reconciliation and freeze conditions.
---

# Critical Component Selection

## Purpose

Drive hardware component choices that are serious enough to freeze into schematic, BOM, pin assignment, or layout constraints. Treat the skill as a per-decision workflow, not a project database.

Keep project facts outside the skill. Use `CONTEXT_INDEX.md` when present, project folders such as `hardware-projects/prj/<project>/`, vendor files, datasheets, PCNs, and current email/procurement evidence as the source of truth.

## Entry Phase

Identify the current entry phase before producing output:

1. New requirement: create the requirement baseline first.
2. Vendor substitute or feedback: update candidates, evidence gaps, and risk deltas.
3. Existing shortlist: compare candidates, classify them, and recommend next action.
4. Pre-freeze review: run the freeze checklist and list blockers.
5. Post-decision update: update the decision record, risks, and review date.

Trim output to the active phase. Do not repeat all seven workflow steps when the user only needs an increment, but mention any missing prerequisite that blocks the phase.

## Evidence Rules

Never assert specific lifecycle, price, lead time, MOQ/MPQ, temperature grade, stock status, PCN/EOL status, tool support, or validation pass/fail from model memory.

For every concrete component fact, cite one of:

1. Datasheet section or table.
2. PCN/EOL number and date.
3. Vendor or distributor URL with access date.
4. Supplier email or message with date and sender.
5. Tool output file, report, or run date.
6. Project decision record or requirements file.

Mark unknown or unsupported fields exactly as `TBD-evidence`. Mark contradictions as `conflict`. Do not soften either state in prose.

## Workflow Checklist

1. Requirement baseline: identify hard constraints, changeable constraints, target lifetime, and acceptance criteria.
2. Hard-gate screen: reject candidates that fail non-negotiable constraints or lack required evidence.
3. Candidate evidence matrix: compare fields across candidates using evidence status, not confidence language.
4. Candidate classification: assign each candidate to `Primary`, `Backup`, `Rejected`, or `Watchlist`.
5. Risk register: record supply, EOL, package/pinout, SI/PI/thermal, firmware/logic, cost, and substitute risks with mitigation owners.
6. Engineering verification gate: state this decision's required validation, owner, pass criteria, and output artifact; do not assume device-category-specific gates.
7. Decision and freeze path: recommend one next decision, list freeze blockers, and propose where to save the record.

## Output Schema

Use these section names unless the user requests a different format:

1. `Decision Objective`
2. `Entry Phase`
3. `Requirement Baseline`
4. `Candidate Classification`
5. `Evidence Matrix`
6. `Evidence Gaps`
7. `Risk Register`
8. `Engineering Verification Gates`
9. `Recommendation`
10. `Freeze Checklist`
11. `Record Location`
12. `Next Actions`

For phase-trimmed responses, include only the relevant sections plus `Evidence Gaps`, `Recommendation`, and `Next Actions` when applicable.

## Workspace Interface

When working inside an existing workspace:

1. Read `CONTEXT_INDEX.md` first if it exists and the project/component is ambiguous.
2. Search project evidence before browsing the web. Browse only when current vendor, lifecycle, PCN, price, stock, standard, or tool support facts may have changed.
3. Suggest saving the final decision to `hardware-projects/prj/<project>/decisions/<YYYYMMDD>-<component>-selection.md` or the closest existing project decision folder.
4. Suggest adding a pointer to `CONTEXT_INDEX.md` after the decision record exists.
5. Do not store real project facts, vendor-specific cheatsheets, or concrete part numbers in this skill.

## References

Load only the template needed for the active phase:

1. `references/evidence-matrix-template.md` for candidate evidence comparison.
2. `references/risk-register-template.md` for structured risk capture.
3. `references/decision-record-template.md` for the final selection record.
4. `references/freeze-checklist-template.md` for pre-freeze gate review.

## Anti-Patterns

Do not include in this skill:

1. Real project data or real part-number examples.
2. Vendor-specific lifecycle claims.
3. Domain cheatsheets such as DDR pinout rules, PMIC compensation recipes, or connector SI tables.
4. Scripts that parse datasheets, query suppliers, or scrape PCNs; those belong in project tooling after repeated use proves the schema is stable.
