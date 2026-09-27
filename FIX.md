# Falsora — Module Gap Fixes Log

Living document. Updated every time a showcase-module gap is closed.
Showcase set: **6.1 · 6.2 · 6.3 · 6.6 · 6.7 · 6.8 · 6.9 · 6.10**

---

## Status overview

| Module | Status | Notes |
|--------|--------|-------|
| 6.1 Auth & RBAC | **Done (batch 1)** | Permissions + activity + forgot-password |
| 6.2 Media Processing | **Done (batch 1)** | Magic-byte validate + reject + preprocess |
| 6.3 Case Management | **Done (batch 1)** | Ownership + Verdict + auto-assign Flagged |
| 6.6 Forgery Detection | Pending | Retrain / scoped demo separate |
| 6.7 Interpretability | **Done (batch 1)** | Grad-CAM served + shown on case detail |
| 6.8 Decision Intelligence | **Done (batch 1)** | Low/Med/High + rule_trace + local fallback |
| 6.9 Orchestration | **Done (batch 1)** | VerificationJob stages + timeout + step UI |
| 6.10 Forensic Report | **Done (batch 1)** | Falsora PDF + Grad-CAM + DB-linked Report |

---

## 6.9 Verification Orchestration

### Gaps addressed (2026-09-27)

1. **Real VerificationJob tracking**
   - Creates `VerificationJob` on upload; stages `UPLOAD → FINGERPRINT → INTEGRITY → FORGERY → DECISION`.
   - Statuses: `PROCESSING` / `COMPLETED` / `FAILED` (+ `errorLog` on fail).
   - Exposed on `GET /api/cases/:id` as `verificationJob` (+ `progress` %).

2. **Dedicated orchestrator module**
   - `verificationPipeline.ts` sequences AI → trust → verdict → auto-assign (replaces inline `setTimeout` blob).
   - Outer **90s timeout** → Flagged + auto-assign + author notify (no forever-Analyzing).

3. **Fail-safe behavior**
   - AI down → cautious score, never silent Verified.
   - Cross-user duplicate stays Flagged for review (`forceFlagged`).
   - Status transitions fail-closed locally when decision-engine is down (mirror of `orchestration.py`).

4. **Pipeline UI + notifications**
   - Case detail: stage chips + **Verification Pipeline** card.
   - Alerts page reads real `/api/notifications` (submit / complete / fail / assign).

### Files touched (6.9)

- `core-api/src/services/verificationPipeline.ts` *(new)*
- `core-api/src/utils/notify.ts` *(new)*
- `core-api/src/routes/cases.ts`
- `core-api/src/services/decisionEngine.ts`
- `decision-engine/modules/notifications.py`
- `decision-engine/main.py`
- `frontend/app/dashboard/cases/[id]/page.tsx`
- `frontend/app/dashboard/alerts/page.tsx`
- `FIX.md`

### How to verify

1. Upload image → case detail shows pipeline stages advancing (FORGERY → DECISION).
2. Open **Alerts** — see `CASE_SUBMITTED` then `ANALYSIS_COMPLETE` or `CASE_FLAGGED`.
3. Stop AI engine, upload again → job may `FAILED` or Flagged with cautious path; case leaves Analyzing.
4. Stop decision-engine → invalid PATCH (e.g. Verified→Flagged) is rejected via local rules.

---

## 6.8 Decision Intelligence Engine

### Gaps addressed (2026-09-27)

1. **Risk bands = Low / Medium / High** (scope wording)
   - `trust_engine.py` now returns `risk_level: Low|Medium|High` plus `legacy_risk_level` (Authentic/Uncertain/High-Risk).
   - Case `riskLevel` stores the new band; UI still understands legacy values.

2. **Fuller rule trace**
   - Response includes `rule_trace` (weights, thresholds, inputs, `rules_fired`, recommended status).
   - Persisted on `Verdict.ruleTraceJson` when AI decision completes.
   - Case detail exposes `decision` object + **Decision Intelligence** card (band, rules, factor breakdown).

3. **Better EXIF / fingerprint use**
   - Optional `integrity_score` and `fingerprint_kind` (`exact`/`near`) in `/trust-score`.
   - Missing EXIF treated as inconclusive (0.70), not harsh fail.
   - Near vs exact duplicate different penalties.

4. **Local fallback**
   - If decision-engine is down, `calculateTrustScoreLocal` in core-api applies the same rules so decisions still persist.

### Files touched (6.8)

- `decision-engine/modules/trust_engine.py`
- `decision-engine/main.py`
- `core-api/src/services/decisionEngine.ts`
- `core-api/src/routes/cases.ts`
- `core-api/src/utils/verdicts.ts`
- `core-api/prisma/schema.prisma` (comment)
- `frontend/app/dashboard/cases/[id]/page.tsx`
- `frontend/app/dashboard/cases/page.tsx`
- `frontend/app/dashboard/reviewer/page.tsx`
- `frontend/components/report-modal.tsx` (score notes → Low/Med/High)
- `FIX.md`

### How to verify

1. Ensure decision-engine (`:8001`) is running (or rely on fallback).
2. Upload an image → after analysis, case detail shows **Decision Intelligence** with Low/Medium/High.
3. Expand rules fired / factor %.
4. Stop decision-engine briefly → upload still gets a score (local fallback log in core-api).

---

## 6.10 Digital Forensic Report Generation

### Gaps addressed (2026-09-27)

1. **Branding**
   - Replaced TITLI FORENSICS → **FALSORA** in PDF + modal preview.
   - Filename `Falsora_Forensic_Report_*.pdf`.

2. **Real case signals (not hardcoded 99.2%)**
   - Deepfake / tampering scores, risk level, verdict, SHA-256, format, EXIF device, access mode.

3. **Grad-CAM in report**
   - Preview shows overlay image; PDF embeds Grad-CAM PNG when URL is available.

4. **Persist Report + pdfUrl**
   - `POST /api/cases/:id/reports` (multipart PDF) → `uploads/reports/` + Prisma `Report` row.
   - `GET /api/cases/:id/reports` lists linked PDFs.
   - Audit action `GENERATE_REPORT`.
   - Modal “Download & Save” uploads after local download; lists saved reports with open links.

### Files touched (6.10)

- `core-api/src/routes/reports.ts` *(new)*
- `core-api/src/routes/cases.ts` (mount nested reports router)
- `frontend/components/report-modal.tsx`
- `frontend/app/dashboard/cases/[id]/page.tsx`
- `FIX.md`

### How to verify

1. Open a finished case → View / Export Report.
2. Confirm FALSORA header + real scores + Grad-CAM if present.
3. Download & Save → file downloads; “Saved case reports” lists a PDF; open link works at `:4000/uploads/reports/...`.

---

## 6.7 AI Interpretability & Evidence Visualization

### Gaps addressed (2026-09-27)

1. **Heatmap not HTTP-served**
   - `publishExplanationArtifacts` copies Grad-CAM PNGs from AI `gradcam/` into
     `core-api/uploads/evidence/` and stores `/uploads/evidence/...` URLs.
   - Legacy absolute paths are migrated on `GET /api/cases/:id` via `ensurePublicMediaUrl`.

2. **Frontend never rendered Grad-CAM**
   - Case detail viewport modes: **Grad-CAM** (overlay) and **Heatmap** (raw).
   - Auto-opens Grad-CAM once when evidence first arrives.
   - Right panel **AI Interpretability** card with method/layer + jump buttons.

3. **Evidence metadata**
   - `explanationText` stored as JSON: method, targetLayer, overlayUrl, heatmapUrl, summary.
   - API returns `overlayUrl`, `rawHeatmapUrl`, `explanationMethod`, `faceDetected`.

### Still open for 6.7

- Tampering-branch localization heatmap (still deepfake-only by design).
- Serving evidence across machines if AI and core-api are not on the same disk
  (copy assumes shared/local filesystem).

### Files touched (6.7)

- `core-api/src/utils/evidenceAssets.ts` *(new)*
- `core-api/src/routes/cases.ts`
- `frontend/app/dashboard/cases/[id]/page.tsx`
- `FIX.md`

### How to verify

1. Upload a **face** image with ai-engine running + weights loaded.
2. Wait for analysis → case detail should switch to Grad-CAM and show the overlay.
3. Toggle Original / Grad-CAM / Heatmap.
4. Confirm PNGs appear under `core-api/uploads/evidence/`.

---

## 6.3 Case Management & Audit Trail

### Gaps addressed (2026-09-27)

1. **Ownership / access checks**
   - `canAccessCase` / `canDeleteCase` (`core-api/src/utils/caseAccess.ts`).
   - `GET /api/cases/:id` → 403 if User opens another user’s case; Reviewer only assigned or unassigned Flagged.
   - Delete (single + bulk): User may only delete own cases.

2. **Verdict records**
   - `writeCaseVerdict` (`core-api/src/utils/verdicts.ts`) on AI finish and human Approve/Reject.
   - Values: `GENUINE` / `MANIPULATED` / `INCONCLUSIVE` + `ruleTraceJson`.
   - Case detail returns `latestVerdict`.

3. **Public vs organizational**
   - Case detail exposes `accessMode` from author’s role (User = public).
   - Public User **cannot** PATCH status (no approve/reject/archive).

4. **Auto-queue Flagged → Reviewer (optional done)**
   - `autoAssignReviewer` picks least-loaded active Reviewer.
   - Runs after AI → Flagged and after human Flag without assignee.
   - Audit `AUTO_ASSIGN_REVIEWER` + notifications to reviewer and case author.
   - Reviewer list `scope=assigned` also includes **unassigned Flagged** for pickup.

5. **Assign hardening**
   - `POST /assign` requires Administrator + target must be Reviewer role.

### Files touched (6.3)

- `core-api/src/utils/caseAccess.ts` *(new)*
- `core-api/src/utils/verdicts.ts` *(new)*
- `core-api/src/utils/autoAssign.ts` *(new)*
- `core-api/src/routes/cases.ts`
- `frontend/app/dashboard/cases/[id]/page.tsx`
- `FIX.md`

### How to verify

1. Login as User → open only own case URLs (other id → 403).
2. Upload image that Flags → Reviewer home shows it; Settings/alerts may show assign notification.
3. Approve/Reject as Reviewer → `latestVerdict` on case detail.
4. User cannot Approve (API 403).

---

## 6.2 Media Processing & Validation

### Gaps addressed (2026-09-27)

1. **Extension-only filter**
   - Magic-byte detection for JPEG / PNG / WEBP (`core-api/src/media/validateUpload.ts`).
   - Extension must match content; declared MIME cross-checked.
   - Multer still does a first-pass extension gate + 10MB limit.

2. **Always `VALIDATED`**
   - Bad files return **HTTP 400** with `validation.status: "REJECTED"` and a reason code
     (`BAD_MAGIC`, `TOO_SMALL`, `EXT_MISMATCH`, …). No case row created.
   - Good files create `MediaAsset.validationStatus = "VALIDATED"` after the pipeline passes.

3. **No dedicated preprocess step**
   - `validateAndPreprocessImage` (`core-api/src/media/preprocessImage.ts`):
     EXIF-orient, downscale if edge &gt; 2048px, re-encode JPEG q=92 for analysis.
   - SHA-256 / EXIF / dHash use **original** bytes; AI gets **processed** buffer.
   - Stored file is the processed JPEG under `/uploads/processed-…`.

4. **Public vs org upload tag**
   - Response includes `accessMode: "public" | "organizational"` from the uploader role.
   - Audit log metadata includes `accessMode` + preprocess stats.

5. **Frontend**
   - Client-side 10MB check; shows server validation reason in the modal + toast.
   - Help text updated to match 10MB + content checks.

### Still open for 6.2 (later if needed)

- Persist a separate original file + processed file (currently only processed kept on disk).
- Public “temporary / minimal storage” TTL (still full Case for User).
- Deep virus/malware scanning (out of FYP scope).

### Files touched (6.2)

- `core-api/src/media/validateUpload.ts` *(new)*
- `core-api/src/media/preprocessImage.ts` *(new)*
- `core-api/src/routes/cases.ts` (upload route)
- `frontend/components/new-case-modal.tsx`
- `FIX.md`

### How to verify

1. Upload a normal JPG → case created, `validation.status` VALIDATED.
2. Rename a `.txt` to `.jpg` → 400 REJECTED (`BAD_MAGIC`).
3. Tiny &lt;64px image → 400 REJECTED (`TOO_SMALL`).
4. Core-api `--watch` should pick up TS changes (no prisma generate needed).

---

## 6.1 User Authentication and RBAC

### Gaps addressed (2026-09-27)

1. **Permission / RolePermission unused**
   - Added canonical permission names in `core-api/src/rbac/permissions.ts`.
   - Seed now upserts permissions and `RolePermission` grants (`core-api/prisma/seed.ts`).
   - New `requirePermission()` middleware (`core-api/src/middleware/auth.ts`).
   - JWT + `/api/auth/me` / login payload include `permissions[]`.
   - Admin user routes gated with `users:manage`; activity feed with `auth:activity:read`.

2. **No login/logout/user activity logs**
   - New Prisma model `AuthActivityLog` (`auth_activity_logs`).
   - Helper `logAuthActivity` (`core-api/src/utils/authActivity.ts`).
   - Events: `LOGIN_SUCCESS`, `LOGIN_FAIL`, `LOGOUT`, `REGISTER`, `PASSWORD_RESET`, `FORGOT_PASSWORD`.
   - Admin UI: Settings → **Auth activity** table (`GET /api/auth/activity`).

3. **Forgot password link dead**
   - `POST /api/auth/forgot-password` issues a temporary password for known emails (demo; no SMTP).
   - Login page dialog wired to that endpoint.

4. **Public vs organizational clarity**
   - Login/register/user list expose `mode: "public" | "organizational"` (`User` = public; Reviewer/Admin = org).
   - Frontend helper `accessMode()` / `hasPermission()` in `frontend/lib/rbac.ts`.
   - Settings user table shows public/org tag.

5. **Hardening**
   - Inactive accounts rejected at login.
   - `/users`, delete, reset-password require auth + `users:manage`.

### Still open for 6.1 (later if needed)

- Full multi-tenant **Organization** entity (not required for demo; mode flag is enough).
- SMTP email delivery for forgot-password (demo returns temp password in response).
- Wire `requirePermission` on every case route (role checks still dominate some paths).

### Bugfix (2026-09-27 evening) — activity empty in Admin Settings

**Cause:** Yes it is wired to Postgres (`auth_activity_logs`), but the running **core-api Bun process** still had an **old Prisma client** where `prisma.authActivityLog` was `undefined`. Writes failed silently; Settings fetch also failed (empty list, no toast).

**Fix:** Hard-restart core-api after `npx prisma generate` (file `--watch` does **not** reload `@prisma/client`). Settings now shows API errors and refreshes when the tab becomes visible.

```bash
# stop core-api terminal (Ctrl+C), then:
cd core-api
npx prisma generate
bun run --watch src/index.ts
```

Then: login as User → login as Admin (same browser OK; cookie switches to admin) → Settings → Refresh auth activity. You should see both `LOGIN_SUCCESS` rows.

### Apply locally

```bash
cd core-api
npx prisma db push
npx prisma generate
npx tsx prisma/seed.ts
# restart core-api (so AuthActivityLog + permission middleware load)
```

`seed.ts` now loads `.env` via `dotenv`. If seed fails with SCRAM password errors, confirm `DATABASE_URL` is set in `core-api/.env`.

Then: login as admin → **Settings → Auth activity**; try **Forgot password?** on the login page.

### Files touched (6.1)

- `core-api/prisma/schema.prisma`
- `core-api/prisma/seed.ts`
- `core-api/src/rbac/permissions.ts` *(new)*
- `core-api/src/utils/authActivity.ts` *(new)*
- `core-api/src/middleware/auth.ts`
- `core-api/src/routes/auth.ts`
- `frontend/lib/rbac.ts`
- `frontend/app/(auth)/login/page.tsx`
- `frontend/app/dashboard/settings/page.tsx`
- `FIX.md` *(this file)*

---

## Next up

Showcase modules for Mehreen’s batch are largely closed (**6.1–6.3, 6.7–6.10**). Optional polish: public TTL cases, SMTP forgot-password, or leave **6.6** to the AI owner.
