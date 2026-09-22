from database import get_connection

def create_notification(case_id: str, user_id: int, message: str, notif_type: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications (case_id, user_id, message, type)
        VALUES (%s, %s, %s, %s)
    """, (case_id, user_id, message, notif_type))
    conn.commit()
    conn.close()


def get_user_notifications(user_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, case_id, message, type, is_read, created_at
        FROM notifications WHERE user_id = %s
        ORDER BY created_at DESC LIMIT 50
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "case_id": str(r[1]), "message": r[2],
         "type": r[3], "is_read": r[4], "created_at": str(r[5])}
        for r in rows
    ]


def mark_as_read(notification_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (notification_id,))
    conn.commit()
    conn.close()


def notify_case_submitted(case_id: str, reviewer_id: int):
    create_notification(case_id, reviewer_id,
                        f"New case submitted — ID: {case_id[:8]}... requires your review.",
                        "case_submitted")

def notify_status_changed(case_id: str, user_id: int, new_status: str):
    create_notification(case_id, user_id,
                        f"Case {case_id[:8]}... status updated to: {new_status}",
                        "status_update")

def notify_high_risk_live(case_id: str, reviewer_id: int, trust_score: float):
    create_notification(case_id, reviewer_id,
                        f"⚠️ HIGH-RISK ALERT: Live stream Trust Score dropped to {trust_score}%. Immediate review needed.",
                        "high_risk_alert")