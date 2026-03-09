"""Data analysis and export module."""


def sanitise_mermaid_id(node_id: str) -> str:
    """Make node_id safe for Mermaid identifiers (no hyphens)."""
    return node_id.replace("-", "_")
