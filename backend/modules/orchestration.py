from database import get_connection

VALID_TRANSITIONS = {
    "submitted":       ["under_analysis"],
    "under_analysis":  ["pending_review", "approved"],
    "pending_review":  ["approved", "rejected"],
    "approved":        [],
    "rejected":        []
}

def update_case_status(case_id: str, new_status: str, reviewer_id: int = None) -> dict:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT status FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return {"error": "Case not found"}

    current_status = row[0]
    allowed = VALID_TRANSITIONS.get(current_status, [])
    if new_status not in allowed:
        conn.close()
        return {"error": f"Cannot move from {current_status} to {new_status}"}

    cur.execute("""
        UPDATE cases
        SET status = %s, assigned_to = %s, updated_at = NOW()
        WHERE id = %s
    """, (new_status, reviewer_id, case_id))

    cur.execute("""
        INSERT INTO analytics_logs (case_id, event_type)
        VALUES (%s, %s)
    """, (case_id, f"status_changed_to_{new_status}"))

    conn.commit()
    conn.close()
    return {"success": True, "new_status": new_status}


def assign_reviewer(case_id: str, reviewer_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE cases SET assigned_to = %s, updated_at = NOW() WHERE id = %s
    """, (reviewer_id, case_id))
    conn.commit()
    conn.close()
    return {"success": True, "assigned_to": reviewer_id}


def get_cases_for_reviewer(reviewer_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, status, trust_score, risk_level, created_at
        FROM cases WHERE assigned_to = %s
        ORDER BY created_at DESC
    """, (reviewer_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": str(r[0]), "status": r[1], "trust_score": r[2],
         "risk_level": r[3], "created_at": str(r[4])}
        for r in rows
    ]

