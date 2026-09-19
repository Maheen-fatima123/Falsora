# 🦋 Falsora — System & Architecture Document

> **Last Updated:** September 2, 2026  
> **Status:** Active Development  
> **Maintainer:** Falsora FYP Engineering Team  
> **Note:** Updated to match approved proposal branding (**Falsora**).

---

## 1. System Architecture

```
                    ┌────────────────────────────────────┐
                    │   Next.js Frontend (React)         │
                    │   Port: 3000 (Bun)                 │
                    └───────────────┬────────────────────┘
                                    │ HTTP / CORS (Credentials)
                                    │ WebSocket (1 FPS live frames)
                                    ▼
                    ┌────────────────────────────────────┐
                    │   Express.js Core API              │
                    │   Port: 4000 (Bun Runtime)         │
                    │   Auth · RBAC · Case Mgmt · Audit  │
                    │   Streams · Analytics · Notifs     │
                    └───┬─────────────────┬─────────────┘
                        │ Prisma ORM      │ fetch() internal calls
                        ▼                 ├───────────────────────────────┐
        ┌───────────────────────┐         ▼                               ▼
        │  PostgreSQL Database  │  ┌──────────────────────┐  ┌──────────────────────────┐
        │  Hosted Neon.tech     │  │  AI Engine (Python)  │  │  Decision Engine (Python) │
        │  (SINGLE source of   │  │  FastAPI · Port 8000 │  │  FastAPI · Port 8001      │
        │   truth for all data) │  │  EfficientNet-B0     │  │  Trust scoring (stateless)│
        └───────────────────────┘  │  Grad-CAM · OpenCV   │  │  Status validation        │
                                   └──────────────────────┘  │  Notif templates          │
                                                              └──────────────────────────┘
```

---

## 2. Tech Stack & Dependencies

| Layer | Technology / Libraries |
| :--- | :--- |
| **Frontend Framework** | Next.js 16 (App Router + Turbopack), React 19, Bun runtime |
| **Styling & Icons** | Tailwind CSS v4, Lucide Icons, `next-themes` (Dark/Light mode) |
| **UI Component Library**| Shadcn UI powered by `@base-ui/react` primitives |
| **Typography** | Fontshare API (**Erode** for Headings, **Recia** for Body text) |
| **Data Visualization** | `recharts` (Area, Bar, Donut, and Horizontal charts) |
| **Backend API** | Express.js (TypeScript), `cors`, `cookie-parser`, `bcryptjs`, `jsonwebtoken` |
| **Database & ORM** | PostgreSQL (Neon.tech Hosted DB), Prisma ORM (`@prisma/client`) |
| **AI/Forensic Engine** | Python, FastAPI (port 8000), PyTorch, Quantized EfficientNet-B0, OpenCV, Grad-CAM |
| **Decision Engine** | Python, FastAPI (port 8001) — stateless trust scoring, orchestration, notif templates |
| **Live Stream Transport**| WebRTC (`getUserMedia`), Native WebSocket via Socket.IO (1 FPS) |

---

## 3. Completed Implementations & Alignment

### A. Authentication & Security (Module 6.1)
* **Next.js Auth Route Protection (`proxy.ts`):** Intercepts requests to `/dashboard/*`. Unauthenticated users redirected to `/login`.
* **JWT Cookie Authentication:** `POST /api/auth/login` verifies credentials with `bcrypt.compare` and issues HttpOnly JWT cookie.
* **Refresh Token Rotation:** Integrated short-lived access tokens (15m) and long-lived refresh tokens (7d).
* **Role-Based UI Gating:** Dynamic rendering based on role (`User`, `Reviewer`, `Administrator`), securely verified via `requireAuth` API middleware.
* **Proposal RBAC Roles Seeded (`prisma/seed.ts`):**
  * 🛡️ `Administrator` (`admin@falsora.ai` / `admin123`, `admin@titli.ai`)
  * 🔍 `Reviewer` (`reviewer@falsora.ai` / `reviewer123`)
  * 👤 `User` (`user@falsora.ai` / `user123`)

### B. Media Ingestion & Upload Whitelist (Module 6.2)
* **Human Face Images Only:** Restricted `POST /api/cases/upload` to `.jpg`, `.jpeg`, `.png`, `.webp` images (Max 15MB).
* **New Case Modal:** Updated UI drag-and-drop to accept face images.

### C. Case Management & Database (Module 6.3 & 6.4)
* **Live Neon PostgreSQL DB:** Connected and seeded hosted database `neondb` at `ep-winter-feather-az1kqmwd...`.
* **UUID Case Keys:** Verified `Case.id` uses UUID string primary keys (`@default(uuid())`).
* **Source Integrity & Cryptography (Module 6.5):** Implemented SHA-256 + dHash generation on upload. Detects exact and near-duplicates and reuses analysis results. Parses EXIF data and calculates integrity score, treating missing EXIF gracefully.

### D. Streams & Live Verification (Module 6.13)
* **Webcam Streams:** Shifted from generic RTMP endpoints to DB-backed `StreamSession` instances linked directly to a Verification Case. Active state machine (`ACTIVE` to `ENDED`).

### D. Digital Forensic PDF Export (Module 6.10)
* **Native jsPDF Generator:** Coordinate-based PDF generation eliminating browser CSS color errors.

---

### E. Decision Engine Integration (Module 6.8)
* **Stateless FastAPI Microservice (`decision-engine/`, port 8001):** Pure-compute service with no DB connection.
  * `POST /trust-score` — weighted composite score from forgery probability, EXIF flags, and fingerprint match.
  * `POST /trust-score/rolling` — exponentially-weighted rolling score for live webcam sessions.
  * `POST /case-status/validate` — enforces `Analyzing → Flagged/Verified` state machine rules.
  * `POST /notifications/format` — generates notification message text.
* **`core-api` Decision Engine Client (`src/services/decisionEngine.ts`):** Type-safe fetch wrapper. Every call degrades gracefully — if the service is unreachable, cases still save with `riskLevel: "Pending"`.
* **Trust score wired into upload flow:** After EXIF extraction, core-api calls `getTrustScore()` and persists `trustScore` and `riskLevel` on the `Case` record.
* **Hardened PATCH `/api/cases/:id`:** Now reads current status, validates the transition via decision-engine, and rejects invalid moves (e.g. `Verified → Analyzing`) with a 400.

### F. New core-api Routes
* **`POST /api/cases/:id/assign`** — assigns a reviewer to a case, writes audit log.
* **`GET /api/analytics/dashboard`** — real Prisma aggregates (total, by-status, by-risk-level, 7-day daily trend, avg trust score).
* **`GET /api/analytics/reviewer/:id/cases`** — cases assigned to a specific reviewer.
* **`GET /api/notifications`**, **`POST /api/notifications/:id/read`**, **`POST /api/notifications/case-event`** — full notification lifecycle via Prisma.

## 4. Immediate Roadmap (Ujala Scope)

1. **Step 1:** Implement Socket.IO 1 FPS Live Webcam Verification Session Pipeline (Modules 6.13 & 6.14).
