# Freeze Checklist Template

Use this as a boolean pre-freeze gate. Do not mark a line complete without a linked artifact or cited evidence.

Allowed status values: `pass`, `blocked`, `TBD-evidence`, `N-A`.

| Gate | Required evidence | Owner | Status | Notes |
|---|---|---|---|---|
| Requirement baseline approved | Requirement record with hard/changeable constraints |  | TBD-evidence |  |
| Primary candidate selected | Decision record with Primary/Backup/Rejected/Watchlist |  | TBD-evidence |  |
| Vendor evidence reconciled | Datasheet, PCN/EOL, supplier response, or official URL |  | TBD-evidence |  |
| Lifecycle and PCN window acceptable | PCN/EOL evidence and project lifetime criterion |  | TBD-evidence |  |
| Commercial terms acceptable | Price, MOQ/MPQ, sample and production lead time |  | TBD-evidence |  |
| Toolchain or engineering validation passed | Tool report, simulation, lab result, or review artifact |  | TBD-evidence |  |
| Package / footprint / pinout checked | Library, pinout, layout, or mechanical evidence |  | TBD-evidence |  |
| SI / PI / thermal / mechanical constraints checked | Decision-specific validation artifact |  | TBD-evidence |  |
| Firmware / logic / software impact accepted | Owner signoff or linked change record |  | TBD-evidence |  |
| Substitute or mitigation path recorded | Backup candidate or explicit risk acceptance |  | TBD-evidence |  |
| Open risks have owners and review dates | Risk register |  | TBD-evidence |  |
| Project record location created | Saved decision artifact and index pointer |  | TBD-evidence |  |

Freeze recommendation:

- `pass`: all non-N-A gates are pass.
- `blocked`: any hard gate is blocked or `TBD-evidence`.
- `conditional`: only acceptable when the project owner explicitly accepts named residual risks with review dates.
