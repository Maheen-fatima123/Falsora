# Falsora — Viva Preparation

Living study doc. New questions get appended here. Answers reflect the **actual code** in this repo (not wishful design docs).

**System in one sentence:** Four services — Next.js frontend (3000/3001) → Express/Prisma core-api (4000) → FastAPI ai-engine (8000) + FastAPI decision-engine (8001) — analyze uploaded images for deepfake / tampering / synthetic faces, score trust, and drive case workflow.

---

## Q1. What frameworks did we use and why?

| Layer | Framework / stack | Why |
|-------|-------------------|-----|
| **Frontend** | **Next.js 16** (App Router) + **React 19** + **Tailwind CSS 4** + **shadcn/Base UI** | Modern dashboard UI, file-based routes per role (admin/reviewer/user), fast local DX with Bun. Charts via **Recharts**. |
| **Core API** | **Express 5** on **Bun** + **TypeScript** | Lightweight HTTP API for auth, cases, notifications, analytics. Bun runs TS directly (`bun run --watch`). |
| **ORM / DB** | **Prisma 7** + **PostgreSQL** (Supabase) via `@prisma/adapter-pg` | Typed models, migrations, seed; shared cloud DB for the team. |
| **AI Engine** | **FastAPI** + **Uvicorn** + **PyTorch** / **timm** / **ONNX Runtime** / **transformers** | Async Python HTTP around Maheen’s `falsora_ai` models; loads checkpoints once at lifespan. |
| **Decision Engine** | **FastAPI** + **Pydantic** | Stateless trust scoring (module 6.8) — no DB of its own. |
| **Auth crypto** | **JWT** (`jsonwebtoken`) + **bcryptjs** | Stateless sessions (httpOnly cookies) + hashed passwords. |
| **Media** | **Multer** + **Sharp** + **exifr** | Upload handling, image preprocess, EXIF read. |
| **Contracts** | **Pydantic** models in `falsora_ai/contracts.py` | Single cross-module data surface (`ForgeryResult`, `Explanation`, …) so Ujala/Mehreen never import torch internals. |

**Why split into 4 services?** Separation of concerns: UI ≠ case CRUD ≠ ML inference ≠ rule-based trust banding. Each can fail soft (e.g. AI down → cautious score, not a dead upload).

---

## Q2. What did we use for form validations?

**No Zod / Yup / React Hook Form** in the app forms.

### Frontend (login / register / forgot-password)
- HTML5 constraints: `required` on inputs, `type="email"` where used.
- Manual JS checks in the page handlers, e.g. register:
  - passwords must match
  - password length ≥ 6
- Server errors returned as JSON and shown in UI.

### Backend — auth
- Trim / type checks on `req.body` (email string required, etc.).
- Passwords hashed with **bcrypt** (cost factor **10**) before store.

### Backend — media upload (the important “form” for forensics)
Module **6.2** in `core-api/src/media/`:
1. **`validateUpload.ts`** — magic-byte detection (JPEG/PNG/WebP), not trusting client MIME/extension; size cap **10 MB**; min edge **64×64**; allowed formats only.
2. **`preprocessImage.ts`** — Sharp resize/normalize for the AI path (max edge 2048), writes processed file under uploads.

### AI / decision services
- **Pydantic** request/response models on FastAPI endpoints.

**Viva line:** “UI forms use HTML5 + light client checks; forensic uploads are validated server-side by magic bytes and Sharp; ML services validate payloads with Pydantic.”

---

## Q3. Connectivity & services for Grad-CAM heatmap and ELA

These are **different signals** on different branches.

### ELA (Error Level Analysis) — **inside ai-engine / tampering branch**
- Code: `falsora_ai/engine_66/tampering/ela.py`
- **Science:** Re-save the image at a fixed JPEG quality; measure per-pixel difference vs original. Regions already compressed “settle”; spliced/edited regions often show higher residual error → bright on the ELA map.
- Fed as **one channel** into **TamperingCNN** (5-channel input: RGB + ELA + SRM noise residual).
- Also exposed as scalar `ela_score` on `TamperingSignal`.
- **No separate microservice** — computed in-process when forgery analyze runs.

### Grad-CAM — **inside ai-engine / deepfake interpretability (6.7)**
- Code: `falsora_ai/engine_67/gradcam.py` (wraps `pytorch-grad-cam`)
- **Science:** Backprop from the “fake” logit into the last conv layer (`backbone.conv_head` of EfficientNet) → spatial heatmap of what drove the deepfake score (e.g. jaw/blend boundary vs irrelevant background).
- Only explains the **deepfake** branch (tampering already has ELA/residual maps).
- Writes PNGs under repo `gradcam/` (overlay + optional heatmap).

### How they reach the UI
```
Upload → core-api (6.9 pipeline)
      → HTTP POST ai-engine /ai/forgery/analyze?explain=true
      → ForgeryResult + Explanation { overlay_path, heatmap_path, method, target_layer }
      → core-api publishExplanationArtifacts() copies/publishes URLs
      → EvidenceVisual row in Postgres (heatmapUrl + explanation JSON)
      → core-api serves /gradcam and /uploads statically
      → frontend case detail shows AI Detection Breakdown + heatmap
```

**Clients:** `core-api/src/services/aiEngine.ts` talks to `AI_ENGINE_URL` (default `http://localhost:8000`).

---

## Q4. What are flagged cases?

`Case.status = "Flagged"` means: **needs human review — do not auto-trust**.

### How a case becomes Flagged
From `verificationPipeline.ts` (module 6.9) + upload path:

| Trigger | Meaning |
|---------|---------|
| Decision risk **Medium** or **High** | Trust score below Low band (`trust < 0.7`) |
| **Duplicate** fingerprint (exact SHA / near dHash) | `forceFlagged` — prior evidence exists |
| **AI engine unreachable** | Never auto-`Verified`; forced Flagged at Medium |
| **Pipeline failure** | Status set Flagged + High risk, reviewer auto-assigned |
| Reviewer / admin manual status change | Allowed transitions include → Flagged |

### What happens next
- Notification event `CASE_FLAGGED` (or related).
- **`autoAssignReviewer`** — least-loaded active Reviewer gets the case.
- Reviewer queue shows assigned + unassigned Flagged cases for pickup.

Opposite status: **`Verified`** when risk band is **Low** and nothing forces review.

---

## Q5. Reset password — random password? What’s the algorithm?

Yes — **temporary random password**, demo-safe (no SMTP email).

### Flow (`POST /api/auth/forgot-password`)
1. Look up user by email.
2. If unknown email → same generic success message (**no account enumeration**), no password issued.
3. If found → `generateTempPassword()` → `bcrypt.hash(..., 10)` → update `passwordHash`.
4. Log `FORGOT_PASSWORD` in auth activity.
5. **Return `temporaryPassword` in JSON** (FYP demo; production would email it).

Admin can also `POST /api/auth/users/:id/reset-password` (permission-gated) — same generator.

### Generator (exact algorithm in `auth.ts`)
```ts
function generateTempPassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%";
  // note: drops ambiguous chars I,O,l,0,1
  let pw = "Fls-";
  for (let i = 0; i < 8; i++) {
    pw += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return pw; // e.g. Fls-aK3$mN2p
}
```

- Prefix `Fls-` + **8** chars from a curated alphabet.
- Uses `Math.random()` (fine for FYP demo; production would use `crypto.randomBytes`).
- Storage always **bcrypt**, never plaintext in DB.

---

## Q6. What technique did we use for auth activity?

**Append-only audit / event log** (not a SIEM product).

- Table: `auth_activity_logs` (`AuthActivityLog` in Prisma).
- Writer: `logAuthActivity()` — **best-effort** (never throws to the login path).
- Fields: `action`, `userId`, `email`, `ip`, `userAgent`, `metadata` JSON, `createdAt`.
- Actions: `LOGIN_SUCCESS`, `LOGIN_FAIL`, `LOGOUT`, `REGISTER`, `PASSWORD_RESET`, `FORGOT_PASSWORD`.
- IP from `X-Forwarded-For` or socket; UA from request headers.
- Admin UI reads via authenticated `GET` on auth activity (permission `auth:activity:read`).

**Viva line:** “We treat auth as an auditable event stream — every success/fail writes a row with IP and user-agent for accountability.”

Related but separate: **case audit trail** (`AuditLog`) with hash-chaining in `utils/audit.ts` for case actions (CREATE_CASE, UPDATE_STATUS, …).

---

## Q7. Why thresholds?

Thresholds turn continuous model scores into **actionable decisions** (Verified vs Flagged, risk bands).

### Decision-engine trust bands (module 6.8)
Weights (same in `decisionEngine.ts` local fallback and Python trust engine):

- Forgery **60%** + EXIF/integrity **25%** + fingerprint **15%**
- `trust = forgeryFactor*0.6 + exifFactor*0.25 + fingerprintFactor*0.15`
- Bands:
  - **Low risk (Authentic)** if `trust ≥ 0.7`
  - **Medium (Uncertain)** if `0.4 ≤ trust < 0.7`
  - **High (High-Risk)** if `trust < 0.4`

Low → recommend **Verified**; Medium/High → **Flagged**.

Also rule thresholds on forgery probability itself (e.g. ≥0.7 “high”, ≥0.4 “moderate”) for `rule_trace` explainability.

### Why not “just use the raw AI score”?
- Models output probabilities with noise; a hard cutoff + multi-signal fusion (forgery + EXIF + duplicate) matches the **scope’s decision intelligence** design.
- Separates **evidence** (ai-engine) from **policy** (decision-engine) — AI never sets `risk_level` on `ForgeryResult`.

### Other thresholds in the system
- Live rolling authenticity / hysteresis in module **6.16** (frame buffer).
- Media: min **64×64**, max file **10 MB**.
- Deepfake authenticity convention in contracts: authenticity = `1 - probability_fake` (scope Stage 4).

---

## Q8. Alerts flow?

**Alerts page = in-app notifications** backed by Postgres `Notification` rows (module 6.12), not a separate push service.

```
Case event (upload / pipeline / assign / flag / fail)
   → notifyCaseEvent() in core-api
   → optional template from decision-engine formatNotification()
   → prisma.notification.create({ userId, type, message })
   → Frontend /dashboard/alerts polls GET /api/notifications
   → User marks read via POST /api/notifications/:id/read
```

### Typical event types
- `CASE_SUBMITTED`, `CASE_FLAGGED`, `ANALYSIS_COMPLETE`, `ANALYSIS_FAILED`, assignment messages, etc.
- UI maps type keywords → severity (FLAG/FAIL → critical, ASSIGN → warning, COMPLETE → success).

**Who gets alerted:** the `targetUserId` (uploader and/or assigned reviewer depending on the event).

---

## Q9. Are analytics hardcoded or connected to real cases?

**Honest answer for viva: both exist — the dashboard page you open is still mock.**

| Piece | Status |
|-------|--------|
| **`frontend/app/dashboard/analytics/page.tsx`** | **Hardcoded mock arrays** (`monthlyTrendData`, fake “14,290 scanned”, etc.) + Recharts. Does **not** call the API today. |
| **`GET /api/analytics/dashboard`** in core-api | **Live** Prisma aggregates: `total_cases`, `by_status`, `by_risk_level`, 7-day `daily_trend`, `avg_trust_score` from real `cases` table. |
| Admin overview / cases list | Connected to real DB (with demo fallback only if cases table empty). |

**Viva line:** “Analytics *API* is wired to real case aggregates; the Analytics *UI page* still shows placeholder charts for the FYP demo. Cases and alerts are live.”

---

## Quick system map (memorize)

```
Browser (Next.js)
    │  HTTP + cookies / Bearer
    ▼
core-api :4000  (Express + Prisma + Supabase Postgres)
    │                    │
    │ analyzeForgery     │ getTrustScore
    ▼                    ▼
ai-engine :8000      decision-engine :8001
(deepfake,             (weighted trust,
 tampering+ELA,         risk bands,
 synthetic,             notification templates)
 Grad-CAM)
```

**Demo logins:** `admin@falsora.ai` / `admin123` · `reviewer@falsora.ai` / `reviewer123` · `user@falsora.ai` / `user123`

**Health checks:**  
`http://localhost:8000/health` → `models_loaded.synthetic/static/frame`  
`http://localhost:8001/health`  
`http://localhost:4000/health`

---

## Q10. Admin vs Reviewer — and how does case assignment work?

### Roles (easy)

| | **Admin** | **Reviewer** |
|---|---|---|
| Job | Run the platform | Review suspicious cases |
| Can assign reviewers | Yes | No |
| Can manage users | Yes | No |
| Can archive cases | Yes | No |
| Review Flagged cases | Yes | Yes (main job) |

**Admin** = system owner. **Reviewer** = human check after AI flags something.

The reviewer does **not** re-run the AI engine. AI already ran on upload. Reviewer reads the scores, Grad-CAM, trust risk, then decides **Verified** or keeps **Flagged**.

---

### How a case reaches the reviewer panel

Every case has a DB field: `assigned_to` (the reviewer’s user id).  
The reviewer home page loads: `GET /api/cases?scope=assigned`.

That API returns cases where:

1. `assigned_to` = **this reviewer**, **or**
2. status = **Flagged** and nobody assigned yet (open queue / pickup)

So once `assigned_to` is set to them, the case shows under **“Cases assigned to you.”**

---

### Two ways assignment happens

**A) Auto-assign (system)**  
When a case becomes **Flagged** and has no reviewer yet (Medium/High trust risk, duplicate, AI down, pipeline fail):

1. `autoAssignReviewer()` runs.
2. Finds all **active Reviewer** accounts.
3. Picks the one with the **fewest** open Flagged/Analyzing cases.
4. Sets `assigned_to` to that person.
5. Sends a `CASE_ASSIGNED` notification.

Admin does not need to click anything for this path.

**B) Manual assign (admin)**  
1. Admin opens a case detail page.  
2. Chooses a Reviewer from the dropdown.  
3. Clicks **Assign** → `POST /api/cases/:id/assign` (admin-only).  
4. DB: `assigned_to = that reviewer`.  
5. Notification + audit log (`ASSIGN_REVIEWER`).

---

### One picture to remember

```
Upload → AI + decision-engine
              ↓
     Often becomes Flagged
              ↓
   ┌──────────┴──────────┐
   │ auto-assign         │ admin picks reviewer
   │ (least busy)        │ from case page
   └──────────┬──────────┘
              ↓
     assigned_to = reviewerId
              ↓
     Reviewer panel (?scope=assigned)
              ↓
     Human decides Verified / Flagged
```

**Viva one-liner:** “Flagged cases are routed to a reviewer by auto-assign or by the admin. The reviewer panel just lists cases where `assigned_to` is me (or unassigned Flagged). Assignment routes work — it does not run AI again.”

---

## Append new Q&A below

<!-- Next viva questions go here -->
