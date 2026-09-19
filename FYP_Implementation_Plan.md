# Digital Media Forensics & Verification Platform
## Complete Implementation Plan

**Team:**
| Member | Reg # | Role | Modules |
|---|---|---|---|
| Ujala Zaib | 231689 | Full Stack Developer | 6.1, 6.2, 6.3, 6.4, 6.5, 6.13, 6.14 + DB, API, Deployment |
| Maheen Fatima | 231659 | AI & Forensic Engine Developer | 6.6, 6.7, 6.16 + Model Optimization |
| Mehreen Ali | 231692 | Workflow & Decision Governance Developer | 6.8, 6.9, 6.10, 6.11, 6.12, 6.15 |

---

## 1. Project Understanding

Based on the module list, this system is a **forensic media authentication and deepfake/tampering detection platform** with two operating modes:

1. **Offline/uploaded media verification** — images/video/audio uploaded, fingerprinted, checked for tampering, and turned into a forensic report with an audit trail (chain of custody).
2. **Live-stream verification** — a WebRTC/WebSocket live session is monitored frame-by-frame in near real-time, with a rolling authenticity score and quality/stream health monitoring.

Both pipelines converge on a **Decision Intelligence Engine** that takes AI signals + integrity signals and produces a verdict, which is then reported, logged, and alerted on.

---

## 2. Recommended Tech Stack

Given one AI-heavy member and two application/workflow-heavy members, a **two-language, service-oriented monolith** (not full microservices — too much DevOps overhead for a 3-person FYP) is the best fit. It cleanly maps to your team split and lets each person work independently without blocking each other.

| Layer | Technology | Why |
|---|---|---|
| **Frontend** | React (Next.js) + TypeScript + Tailwind CSS + shadcn/ui | Fast to build dashboards, case views, evidence visualizations. Next.js gives you SSR + API routes if needed for the demo. |
| **Core App Backend** (Ujala + Mehreen) | Node.js + Express (or NestJS) + TypeScript | Handles auth/RBAC, case management, orchestration, notifications, reporting — I/O-bound, not compute-bound, so Node is ideal. NestJS if you want structure (modules/DI) matching your section numbers. |
| **AI/Forensic Engine** (Maheen) | Python + FastAPI + PyTorch/TensorFlow + OpenCV | Forgery detection models, interpretability (Grad-CAM/SHAP), frame buffer scoring — Python is non-negotiable here for the ML ecosystem. Exposed as an internal REST/gRPC microservice the Node backend calls. |
| **Real-time / Live Stream** (Ujala) | WebRTC (mediasoup or simple-peer) + Socket.IO | Socket.IO for signaling + session/room management; mediasoup (SFU) if you need to route media server-side for frame extraction, otherwise a lighter peer-to-peer + server-side frame-grab approach is fine for FYP scale. |
| **Primary Database** | PostgreSQL | Relational integrity for users, roles, cases, audit trail, verdicts — Postgres also has good JSONB support for flexible AI-result payloads. |
| **Media/Object Storage** | MinIO (S3-compatible, self-hostable) or AWS S3 | Store uploaded images/video/audio + extracted frames outside the DB. |
| **Fingerprint/Vector Store** | Postgres + `pgvector`, or FAISS | Perceptual hashes (pHash/dHash) for dedup + embedding vectors for near-duplicate detection. |
| **Cache / Queue** | Redis + BullMQ (Node) or Celery (Python) | Async job queue for media processing pipeline (upload → fingerprint → forgery scan → decision), rolling score buffer for live streams, pub/sub for notifications. |
| **Message bus between Node ↔ Python services** | REST (simple) or gRPC (if you want speed/typed contracts) | REST + JSON is easier to demo/debug for an FYP; gRPC is a nice-to-have if time allows. |
| **Auth** | JWT (access + refresh tokens) + bcrypt/argon2, RBAC middleware | Standard, defensible in a viva. |
| **Deployment** | Docker + Docker Compose (dev), optional single VPS or free-tier cloud (Render/Railway/AWS EC2) for demo | Compose ties Node service, Python service, Postgres, Redis, MinIO together with one command — great for FYP demos. |
| **CI/CD** | GitHub Actions | Lint/test/build on push; optional auto-deploy to a demo server. |
| **Monitoring (lightweight)** | pino/winston logs + a simple `/health` endpoint per service | Enough for FYP scope; don't over-engineer with Prometheus/Grafana unless you have spare time. |

**Why not a single Node-only or Python-only stack?** A Node-only stack forces you to bolt ML onto a runtime that's weak for it (via child processes or ONNX.js, losing PyTorch flexibility). A Python-only stack (e.g., Django for everything) works but makes WebRTC signaling and real-time socket work clunkier than Node's ecosystem. The two-service split matches your team's actual skill split and lets Maheen iterate on models independently without touching the app backend.

---

## 3. High-Level Architecture

```
┌─────────────────────────────┐
│   Frontend (Next.js)        │
│  Dashboards / Case Viewer /  │
│  Live Session UI / Reports   │
└───────────┬──────────────────┘
            │ REST + WebSocket (JWT auth)
┌───────────▼──────────────────────────────────────────────┐
│              Core App Backend (Node/NestJS)                │
│  6.1 Auth & RBAC     6.3 Case Mgmt & Audit                  │
│  6.13 Live Session    6.14 WebRTC/WS Signaling               │
│  6.9 Verification Orchestration (calls into AI + Decision)   │
│  6.11 Reporting/Analytics   6.12 Notifications                │
└─────┬───────────────┬──────────────────┬────────────────────┘
      │ REST/gRPC      │ REST/gRPC        │ SQL
┌─────▼───────────┐ ┌──▼────────────────┐ ┌▼──────────────────┐
│ AI/Forensic       │ │ Decision & Report │ │ PostgreSQL          │
│ Engine (FastAPI)  │ │ Engine (FastAPI/  │ │ + pgvector           │
│ 6.6 Forgery Det.  │ │ Node)             │ │ (users, cases,       │
│ 6.7 Interpretab.  │ │ 6.8 Decision Intel│ │ audit, verdicts,     │
│ 6.16 Frame Buffer │ │ 6.10 Forensic Rpt │ │ fingerprints)        │
│ 6.4 Fingerprinting│ │ 6.15 Stream QoS   │ └──────────────────────┘
│ 6.5 Source Integ. │ └───────────────────┘
└─────┬──────────────┘
      │
┌─────▼──────────────┐   ┌────────────────┐
│ MinIO/S3 (media)     │   │ Redis (queue,   │
│                       │   │ rolling scores) │
└───────────────────────┘   └────────────────┘
```

**Pipeline flow (uploaded media):**
Upload → Media Processing & Validation (6.2) → Fingerprinting/Dedup (6.4) → Source Integrity Analysis (6.5) → Forgery/Tampering Detection (6.6) → Interpretability overlay (6.7) → Decision Intelligence (6.8) → Verification Orchestration ties it together (6.9) → Forensic Report (6.10) → stored in Case (6.3) with Audit Trail → Notification (6.12) → visible in Reporting/Analytics (6.11).

**Pipeline flow (live stream):**
Session start (6.13) → WebRTC/WS media in (6.14) → Frame Buffer & Rolling Score Engine (6.16) → per-frame forgery signal (6.6) → Stream Quality Monitoring (6.15) → rolling Decision updates (6.8) → live alerts (6.12) → session summary becomes a Case (6.3) at end.

---

## 4. Database Design (Core Schema)

```sql
-- Auth & RBAC (6.1)
users(id, name, email, password_hash, role_id, is_active, created_at)
roles(id, name)                  -- Admin, Analyst, Reviewer, Viewer
permissions(id, name)
role_permissions(role_id, permission_id)

-- Case Management & Audit Trail (6.3)
cases(id, title, created_by, status, created_at, closed_at)
audit_logs(id, case_id, user_id, action, metadata_json, timestamp)

-- Media Processing (6.2)
media_assets(id, case_id, uploaded_by, file_type, storage_url,
             validation_status, duration_sec, resolution, created_at)

-- Fingerprinting & Dedup (6.4)
media_fingerprints(id, media_id, phash, dhash, embedding_vector, created_at)
duplicate_matches(id, media_id_a, media_id_b, similarity_score)

-- Source Integrity (6.5)
source_metadata(id, media_id, exif_json, c2pa_signature, gps_data,
                 device_fingerprint, integrity_score)

-- Forgery Detection (6.6)
forgery_results(id, media_id, model_name, confidence_score,
                 manipulation_type, raw_output_json, created_at)

-- Interpretability (6.7)
evidence_visuals(id, forgery_result_id, heatmap_url, explanation_text)

-- Decision Intelligence (6.8)
verdicts(id, case_id, media_id, final_verdict, confidence,
         rule_trace_json, decided_at)

-- Verification Orchestration (6.9)
verification_jobs(id, case_id, media_id, status, stage, error_log, updated_at)

-- Forensic Report (6.10)
reports(id, case_id, generated_by, pdf_url, generated_at)

-- Reporting & Analytics (6.11)  -- mostly aggregate queries, minimal own tables
analytics_snapshots(id, metric_name, value, period, created_at)

-- Notifications (6.12)
notifications(id, user_id, type, message, is_read, created_at)

-- Live Streaming (6.13, 6.14, 6.15, 6.16)
stream_sessions(id, case_id, host_id, status, started_at, ended_at)
stream_frames(id, session_id, frame_ts, forgery_score, buffer_index)
stream_quality_logs(id, session_id, bitrate, packet_loss, latency_ms, timestamp)
rolling_scores(id, session_id, window_start, window_end, avg_score, flagged)
```

---

## 5. Module Breakdown by Team Member

### Ujala Zaib — Full Stack Developer

| Module | Key Deliverables |
|---|---|
| 6.1 Auth & RBAC | JWT login/refresh, role-based route guards, role/permission admin UI |
| 6.2 Media Processing & Validation | Upload endpoint, file-type/size/codec validation, virus/format sanity checks, thumbnail/frame extraction (ffmpeg) |
| 6.3 Case Management & Audit Trail | Case CRUD, case timeline, immutable audit log (append-only table + hash chaining for tamper-evidence) |
| 6.4 Image Fingerprinting & Dedup | pHash/dHash generation, near-duplicate search via pgvector or FAISS |
| 6.5 Source Integrity Analysis | EXIF/metadata extraction, C2PA content-credential check (if available), GPS/device consistency checks |
| 6.13 Live Stream Session Mgmt | Session create/join/end, participant/role control, session-to-case linking |
| 6.14 WebRTC & WebSocket Comm | Signaling server (Socket.IO), SFU/peer setup (mediasoup or simple-peer), server-side frame grabbing for analysis |
| DB / API / Deployment | Schema ownership, OpenAPI spec, Docker Compose, CI/CD pipeline |

### Maheen Fatima — AI & Forensic Engine Developer

| Module | Key Deliverables |
|---|---|
| 6.6 Forgery & Tampering Detection | CNN/transformer-based deepfake classifier (e.g., fine-tuned XceptionNet/EfficientNet for face-swap detection, ELA/noise-analysis for splicing), exposed via FastAPI `/analyze` endpoint |
| 6.7 AI Interpretability & Evidence Visualization | Grad-CAM/SHAP heatmaps overlaid on frames, human-readable explanation text generation |
| 6.16 Frame Buffer & Rolling Score Engine | Sliding-window buffer of recent frames, moving-average/EWMA authenticity score, flag-on-threshold logic for live streams |
| Model Optimization | Quantization/ONNX export for inference speed, batching for throughput, benchmarking (latency vs. accuracy trade-offs) |

### Mehreen Ali — Workflow & Decision Governance Developer

| Module | Key Deliverables |
|---|---|
| 6.8 Decision Intelligence Engine | Rule engine / weighted scoring combining forgery score + source integrity + dedup signals into a final verdict, with explainable rule trace |
| 6.9 Verification Orchestration Engine | Pipeline/job orchestrator (state machine) driving media through validation → fingerprint → integrity → forgery → decision stages; retry/error handling |
| 6.10 Digital Forensic Report Generation | PDF report generator (case summary, evidence, verdict, chain of custody) — e.g., via a templating engine + headless rendering |
| 6.11 Reporting & Analytics | Dashboard queries: verdict trends, case throughput, model accuracy over time, exportable analytics |
| 6.12 Notification & Alert Module | Real-time in-app + email alerts on verdict/flag events, notification preferences |
| 6.15 Stream Quality Monitoring | Bitrate/latency/packet-loss tracking from WebRTC stats API, quality-degradation alerts |

---

## 6. Integration Contracts (so no one blocks anyone)

Define these API contracts in Week 1–2 so all three can build in parallel against mocks:

- `POST /api/media/upload` → returns `media_id` (Ujala provides; Mehreen's orchestrator calls it)
- `POST /ai/forgery/analyze` `{media_url}` → `{confidence, manipulation_type, heatmap_url}` (Maheen provides; Mehreen's decision engine calls it)
- `POST /ai/frame/score` `{frame}` → `{score}` (Maheen, used by live pipeline)
- `POST /decision/verdict` `{case_id, media_id}` → `{verdict, confidence, trace}` (Mehreen provides; Ujala's case UI displays it)
- WebSocket events: `session:join`, `frame:score:update`, `alert:new` (Ujala + Mehreen agree on payload shape)

Recommend documenting these in a shared OpenAPI/Postman collection from day one.

---

## 7. Suggested Timeline (14-week semester)

| Weeks | Focus |
|---|---|
| 1–2 | Requirements freeze, DB schema finalized, API contracts agreed, repo/CI/Docker skeleton up |
| 3–5 | Core builds in parallel: Auth/RBAC + Case mgmt (Ujala), first forgery model baseline (Maheen), orchestration skeleton + rule engine draft (Mehreen) |
| 6–8 | Media pipeline end-to-end (upload→fingerprint→integrity→forgery→decision) working on uploaded files; report generation v1 |
| 9–10 | Live streaming: WebRTC/WS signaling, frame buffer, rolling score, stream quality monitoring |
| 11–12 | Interpretability visuals, analytics dashboard, notifications, model optimization pass |
| 13 | Integration testing, bug fixing, security pass (auth edge cases, audit trail immutability) |
| 14 | FYP documentation, demo rehearsal, deployment freeze |

---

## 8. Deployment Plan

1. **Dev:** `docker-compose up` running: `frontend`, `core-api` (Node), `ai-engine` (FastAPI), `decision-engine`, `postgres`, `redis`, `minio`.
2. **Staging/Demo:** Single VPS (e.g., a $10–20/mo droplet) or free-tier Render/Railway for the demo; use Docker Compose there too for simplicity — avoids Kubernetes overhead you don't need for an FYP.
3. **Secrets:** `.env` files per service, never committed; use GitHub Actions secrets for CI.
4. **CI/CD:** On push to `main` → lint + test → build Docker images → (optional) deploy to staging.

---

## 9. Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Forgery detection model accuracy is weak/generic | Use a well-known public deepfake dataset (e.g., FaceForensics++, Celeb-DF) for baseline training; be transparent in the report about dataset limitations |
| Live-stream real-time performance (latency) | Don't analyze every frame — sample at fixed intervals (e.g., every 5th frame) and use a lightweight optimized model (ONNX/quantized) for the rolling score |
| Scope too large for 3 people in one semester | Treat live-stream (6.13–6.16) as a stretch goal; get the uploaded-media pipeline rock solid first, since it's the core FYP value |
| Integration bugs between Node and Python services | Lock API contracts early (Section 6), use mock servers so each person can develop independently before wiring up |
| Audit trail must be tamper-evident (forensic credibility) | Hash-chain audit log entries (each entry stores hash of previous entry) so any dashboard can verify integrity |

---

## 10. Next Steps

1. Confirm this stack with your supervisor.
2. Set up the shared repo with three folders: `frontend/`, `core-api/`, `ai-engine/` (+ `decision-engine/` if Mehreen's parts run as a separate Python service).
3. Finalize the DB schema together (Section 4) — everyone builds against it.
4. Lock the API contracts (Section 6) before writing pipeline code.
