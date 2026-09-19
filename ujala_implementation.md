# Ujala Zaib — FYP Implementation Checklist

**Role:** Full Stack Developer + DB / API / Deployment Owner  
**Stack:** Next.js (Frontend) · Node.js/Express (Core API) · Prisma · PostgreSQL · Socket.IO · Docker

---

## Module 6.1 — Auth & RBAC

> JWT-based authentication + role-based access control (Admin, Analyst, Reviewer, Viewer)

- [x] `POST /api/auth/register` — user registration endpoint exists
- [x] `POST /api/auth/login` — login with JWT issuance exists
- [ ] JWT refresh token flow (`POST /api/auth/refresh`)
- [ ] Frontend login page wired to API (currently goes to dashboard directly)
- [ ] Frontend stores JWT in `httpOnly` cookie or `localStorage` + attaches to requests
- [ ] Protected API route middleware (verify JWT on every route)
- [ ] Role enum in DB (`Admin`, `Analyst`, `Reviewer`, `Viewer`)
- [ ] Frontend route guards (redirect to login if not authenticated)
- [ ] Role-based UI elements (e.g. only Admins see Settings, only Analysts can create cases)

---

## Module 6.2 — Media Processing & Validation

> Upload endpoint, file-type/size/codec validation, thumbnail/frame extraction

- [x] `POST /api/cases/upload` — multer file upload accepts media
- [x] 100MB file size limit configured
- [x] File-type whitelist validation (only accept `.mp4`, `.mov`, `.jpg`, `.png`, `.wav`, `.mp3`)
- [ ] Virus/format sanity check (mime-type validation, magic bytes check)
- [ ] Thumbnail generation for video uploads (via `ffmpeg`)
- [ ] Frame extraction from video (extract keyframes for AI analysis)
- [ ] Store media file in MinIO/S3 (currently saving to local `/uploads/` disk — not production-ready)
- [ ] Return `media_id` in upload response (for Mehreen's orchestrator to call)

---

## Module 6.3 — Case Management & Audit Trail

> Case CRUD, timeline view, immutable append-only audit log with hash chaining

- [x] `GET /api/cases` — fetch all cases (with DB + memory fallback)
- [x] `POST /api/cases/upload` — create a new case with uploaded file
- [x] Prisma schema has `Case` model
- [x] Cases list visible in frontend dashboard
- [x] New Case Modal in frontend (opens, has form)
- [x] Frontend New Case Modal actually POSTs to `POST /api/cases/upload`
- [x] `GET /api/cases/:id` — fetch a single case with full details
- [ ] `PATCH /api/cases/:id` — update case status (`Analyzing` → `Flagged` / `Verified`)
- [ ] `DELETE /api/cases/:id` — archive/soft-delete a case
- [ ] Audit log: `audit_logs` table in schema with `case_id`, `user_id`, `action`, `metadata_json`, `timestamp`
- [ ] Every case mutation appends an audit log entry
- [ ] Hash-chaining on audit entries (each entry stores SHA-256 of the previous entry for tamper-evidence)
- [ ] Case detail page (`/dashboard/cases/[id]`) showing timeline, evidence, verdict, and audit trail
- [ ] Forensic Report Modal pulls real case data from API (currently hardcoded defaults)

---

## Module 6.4 — Image Fingerprinting & Dedup

> pHash/dHash perceptual hashing, near-duplicate evidence detection

- [x] `media_fingerprints` table in Prisma schema (`media_id`, `phash`, `dhash`, `sha256`, `created_at`)
- [x] On file upload: compute SHA-256 hash of the file
- [x] On file upload: compute pHash/dHash (use `sharp` + bit-distance library or `imghash`)
- [x] `POST /api/cases/upload` stores the hash in `media_fingerprints`
- [x] Duplicate detection: on each upload, query for existing fingerprints with similarity score > threshold
- [x] Return duplicate warning in upload response if match found
- [ ] Frontend shows duplicate warning in New Case Modal if a duplicate is detected
- [ ] Forensic Report shows the SHA-256 hash (already visible in UI, needs real value from API)

---

## Module 6.5 — Source Integrity Analysis

> EXIF/metadata extraction, camera model, GPS consistency, device fingerprint

- [x] `source_metadata` table in Prisma schema (`media_id`, `exif_json`, `gps_data`, `device_fingerprint`, `integrity_score`)
- [x] On video/image upload: extract EXIF using `exiftool` or `exifr` npm package
- [x] Store extracted fields: camera model, resolution, creation date, GPS coords, software
- [x] Flag inconsistencies: e.g. metadata says "iPhone" but codec is unusual for iPhone
- [x] `GET /api/cases/:id` returns source integrity details
- [ ] Forensic Report Modal's metadata table (`Container/Format`, `Resolution`, `SHA-256`, `Camera Profile`) populated from real API data

---

## Module 6.13 — Live Stream Session Management

> Session create/join/end, participant/role control, session-to-case linking

- [x] Streams page exists in frontend (`/dashboard/streams`)
- [x] Add Stream Modal exists in frontend
- [ ] `stream_sessions` table in Prisma schema (`id`, `case_id`, `host_id`, `status`, `started_at`, `ended_at`)
- [ ] `POST /api/streams` — create a new stream session, return `session_id`
- [ ] `GET /api/streams` — list all stream sessions
- [ ] `GET /api/streams/:id` — get stream session details
- [ ] `POST /api/streams/:id/end` — mark session as ended, link to case
- [ ] Frontend Add Stream Modal POSTs to `POST /api/streams`
- [ ] Streams list in frontend fetches from `GET /api/streams`

---

## Module 6.14 — WebRTC & WebSocket Communication

> Socket.IO signaling server, peer setup, server-side frame grabbing for analysis

- [ ] Install `socket.io` in `core-api`
- [ ] Socket.IO server attached to Express HTTP server
- [ ] Signaling events: `session:join`, `session:leave`, `offer`, `answer`, `ice-candidate`
- [ ] Server-side room management per `session_id`
- [ ] Frame extraction from incoming stream (sample every Nth frame for AI analysis)
- [ ] Emit `frame:score:update` event to clients when AI returns a score
- [ ] Emit `alert:new` event when a frame is flagged
- [ ] Frontend streams page connects to Socket.IO and displays live rolling score

---

## DB / API / Deployment

- [x] Prisma schema defined (`schema.prisma`)
- [x] Docker Compose configured (Postgres port `5433`, Redis `6379`, MinIO `9000`)
- [x] `core-api` runs with `bun run dev`
- [x] `frontend` runs with `bun run dev`
- [ ] **Run `docker compose up -d`** to start Postgres, Redis, MinIO containers
- [ ] **Run `npx prisma migrate dev`** to apply schema migrations
- [ ] **Run `npx prisma db seed`** to populate seed data
- [ ] OpenAPI spec kept up to date (`openapi.yaml` in root)
- [ ] Environment variables documented in `.env.example`
- [ ] CI/CD: GitHub Actions lint + build on push to `main`

---

## Priority Order (What to Build Next)

1. 🔴 **Start Docker + run migrations** — everything else depends on a live DB
2. 🟠 **Module 6.3:** Wire frontend New Case Modal → real API → real DB
3. 🟠 **Module 6.5:** Add EXIF extraction on upload → populate real metadata in report
4. 🟡 **Module 6.4:** Add SHA-256 + pHash on upload → display real hash in report
5. 🟡 **Module 6.1:** Wire login page → API → JWT → route guards
6. 🟢 **Module 6.13:** Add streams API routes
7. 🟢 **Module 6.14:** Add Socket.IO signaling server
