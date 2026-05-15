# Project Data Layout

This repository separates four kinds of project material:

1. **Runtime project state** lives in `projects/<PROJECT_ID>.yaml`.
2. **Sanitized examples** live in `examples/projects/*.yaml`.
3. **Reusable templates** live in `flows/` and `tracker/templates/`.
4. **Project truth documents and evidence** live in the linked project repo,
   not inside `project-tracker`.

## A57 Handling

`projects/A57.yaml` is currently the strongest complex hardware regression
case in the repository. Do not delete it blindly. It drives documentation,
close-gate examples, and tests.

The sanitized copy is:

```text
examples/projects/hardware-platform-demo.yaml
```

That file is a **demo**, not a template. It is useful for showing how the CLI
behaves on a realistic project graph, including critical path, risk ranking,
requirements, and Merge-to-Close gaps. New projects should not be copied from
it. New projects should start from a flow template.

## New Project Storage

For a new project `CASE1`, use this layout:

```text
project-tracker/
  projects/
    CASE1.yaml                  # tracker runtime state

CASE1-docs/                     # linked project truth repo
  .pt/
    CASE1.yaml                  # optional synced tracker snapshot
    requirements_manifest.yaml  # requirements binding manifest
  01_需求阶段_Requirements/
  02_可行性评估_Feasibility/
  evidence/
  reviews/
  reports/
```

`project-tracker/projects/<PROJECT_ID>.yaml` answers: what is the current task
graph, status, owner, risk, close metadata, and linked evidence path?

`<PROJECT_ID>-docs/` answers: what is the formal project truth, source
document, meeting record, review result, test evidence, and final conclusion?

## Raw vs Generated

Raw or human-authored material belongs in the linked project repo:

- requirements and formal conclusions
- design notes and interface definitions
- meeting minutes and decision records
- review reports from domain tools
- test evidence, screenshots, logs, and measurement files

Generated or tool-maintained material belongs in predictable generated areas:

- `projects/.pt_history/` for local safety snapshots
- `<PROJECT_ID>-docs/.pt/` for synced tracker manifests/snapshots
- `docs/issues/*BACKLOG*` for generated backlog reports
- exported HTML/CSV/Mermaid files in a caller-selected output folder

Do not put large raw evidence files into `project-tracker`. Store them in the
linked project repo and reference them from the YAML.

## New Project Flow

```powershell
python -m tracker init CASE1 --name "Case 1" --flow generic --repo "D:\MY PRJ\CASE1-docs"
python -m tracker switch CASE1
python -m tracker req init --subprojects MODULE_A,MODULE_B
python -m tracker status
python -m tracker next
```

If the project already has documents, link it first and then scan/import:

```powershell
python -m tracker docs --link "D:\MY PRJ\CASE1-docs"
python -m tracker scan --repo "D:\MY PRJ\CASE1-docs" --arch
python -m tracker req init
```

## Naming Rules

- Use stable ASCII project IDs: `CASE1`, `PILLOW`, `HARDWARE_DEMO`.
- Keep real project YAML in `projects/`.
- Keep demos in `examples/projects/`.
- Keep reusable process templates in `flows/`.
- Keep reusable document scaffolds in `tracker/templates/`.
- Keep project truth and evidence in the linked project repo.

