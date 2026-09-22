from database import get_connection

def get_dashboard_stats() -> dict:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM cases")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT risk_level, COUNT(*) FROM cases
        WHERE risk_level IS NOT NULL
        GROUP BY risk_level
    """)
    risk_counts = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM cases
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY day ORDER BY day
    """)
    daily = [{"date": str(row[0]), "count": row[1]} for row in cur.fetchall()]

    cur.execute("SELECT status, COUNT(*) FROM cases GROUP BY status")
    by_status = {row[0]: row[1] for row in cur.fetchall()}

    conn.close()
    return {
        "total_cases": total,
        "by_risk_level": {
            "Authentic": risk_counts.get("Authentic", 0),
            "Uncertain": risk_counts.get("Uncertain", 0),
            "High-Risk": risk_counts.get("High-Risk", 0)
        },
        "daily_trend": daily,
        "by_status": by_status
    }