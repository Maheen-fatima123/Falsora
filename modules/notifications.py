"""
Notification template helpers — pure formatting, zero DB access.
core-api calls these to generate message text, then persists the
Notification record itself via Prisma.
"""


def format_case_submitted(case_id: str, case_title: str, submitted_by: str) -> dict:
    return {
        "type": "CASE_SUBMITTED",
        "message": f"New case '{case_title}' (#{case_id[:8]}) submitted by {submitted_by} and is awaiting review.",
    }


def format_case_assigned(case_id: str, case_title: str, reviewer_name: str) -> dict:
    return {
        "type": "CASE_ASSIGNED",
        "message": f"Case '{case_title}' (#{case_id[:8]}) has been assigned to you for review.",
    }


def format_case_flagged(case_id: str, case_title: str, risk_level: str) -> dict:
    return {
        "type": "CASE_FLAGGED",
        "message": (
            f"Case '{case_title}' (#{case_id[:8]}) has been flagged as {risk_level}. "
            "Immediate review is recommended."
        ),
    }


def format_case_verified(case_id: str, case_title: str, verdict: str) -> dict:
    return {
        "type": "CASE_VERIFIED",
        "message": f"Case '{case_title}' (#{case_id[:8]}) has been verified with verdict: {verdict}.",
    }
