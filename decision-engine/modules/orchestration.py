"""
Orchestration — Pure status-transition validator, zero DB access.
DB reads/writes for case status are handled exclusively by core-api (Prisma).
"""

# Valid case status transitions in the Falsora workflow.
# Matches the status vocabulary in core-api/prisma/schema.prisma.
VALID_TRANSITIONS: dict[str, list[str]] = {
    "Analyzing": ["Flagged", "Verified"],
    "Flagged":   ["Verified", "Analyzing"],
    "Verified":  [],          # Terminal state — no further transitions
    "Archived":  [],          # Terminal state
}


def validate_status_transition(current_status: str, new_status: str) -> dict:
    """
    Validate whether a case status transition is permitted.

    Args:
        current_status: The case's current status string.
        new_status:     The requested target status string.

    Returns:
        On success: { "valid": True, "new_status": str }
        On failure: { "valid": False, "error": str }
    """
    if current_status not in VALID_TRANSITIONS:
        return {
            "valid": False,
            "error": f"Unknown current status: '{current_status}'",
        }

    allowed = VALID_TRANSITIONS[current_status]

    if not allowed:
        return {
            "valid": False,
            "error": f"'{current_status}' is a terminal state — no further transitions are permitted.",
        }

    if new_status not in allowed:
        return {
            "valid": False,
            "error": (
                f"Cannot transition from '{current_status}' to '{new_status}'. "
                f"Allowed next states: {allowed}"
            ),
        }

    return {"valid": True, "new_status": new_status}
