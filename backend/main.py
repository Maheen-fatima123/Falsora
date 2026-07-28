from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import get_connection
from modules.trust_engine import calculate_trust_score
from modules.orchestration import update_case_status, assign_reviewer, get_cases_for_reviewer

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    conn = get_connection()
    conn.close()
    return {"status": "ok"}

@app.post("/api/calculate-trust-score")
def get_trust_score(data: dict):
    result = calculate_trust_score(
        forgery_score=data["forgery_score"],
        exif_flags=data.get("exif_flags", []),
        fingerprint_match=data.get("fingerprint_match", False)
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE cases
        SET trust_score = %s, risk_level = %s, updated_at = NOW()
        WHERE id = %s
    """, (result["trust_score"], result["risk_level"], data["case_id"]))
    conn.commit()
    conn.close()

    return result

@app.post("/api/cases/{case_id}/status")
def change_status(case_id: str, data: dict):
    return update_case_status(case_id, data["new_status"], data.get("reviewer_id"))

@app.post("/api/cases/{case_id}/assign")
def assign_case(case_id: str, data: dict):
    return assign_reviewer(case_id, data["reviewer_id"])

@app.get("/api/reviewer/{reviewer_id}/cases")
def reviewer_cases(reviewer_id: int):
    return get_cases_for_reviewer(reviewer_id)