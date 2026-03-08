"""Project-level constants shared across core, validation, and query layers."""

PROJECT_SCHEMA_VERSION = 2
VALID_NODE_STATUSES = {"pending", "in_progress", "blocked", "done", "expanded", "skipped"}
VALID_DECISION_STATUSES = {"active", "superseded", "reverted", "pending"}
VALID_POC_STATUSES = {"pending", "go", "caution", "no-go"}
VALID_REVIEW_VERDICTS = {"GO", "CAUTION", "NO-GO", "HIGH RISK", "CONDITIONAL GO", "HIGHLY FEASIBLE"}
