# Running Falsora locally

The system is four separate services that talk to each other over HTTP.
All four must be running at once for the full app (upload -> AI analysis ->
trust score -> dashboard) to work end to end.

| Service           | Owner   | Port | What it is                                      |
|-------------------|---------|------|--------------------------------------------------|
| `frontend`        | Ujala   | 3000 | Next.js dashboard (what you open in the browser) |
| `core-api`        | Ujala   | 4000 | Express + Prisma API, case/user management        |
| `decision-engine` | Mehreen | 8001 | FastAPI trust-scoring service                    |
| `ai-engine`       | Maheen  | 8000 | FastAPI wrapper around the deepfake/tampering models |

Run everything inside **Cursor’s built-in Terminal** panel — not the
Windows PowerShell app. Open four tabs there:

1. ``Ctrl+` `` (or **View → Terminal**) to open the Terminal panel
2. Click **+** (or the dropdown → **New Terminal**) until you have 4 tabs
3. Optionally rename each tab (right-click the tab) to `ai-engine`,
   `decision-engine`, `core-api`, `frontend`

Start the four services in the order below. On Windows, Cursor’s terminal
is usually PowerShell already — the commands below work as-is from the
repo root (`D:\FYP\Falsora` or wherever you cloned it).

## 0. Prerequisites (one-time setup)

- **Node.js** >= 20.19 (Prisma 7 requirement) — check with `node -v`
- **Bun** — `npm install -g bun` if you don't have it
- **Python 3.11** (required — `falsora-ai` is `<3.12`; Python 3.13 will fail).
  Check with `py -0p`. Install with:
  `winget install Python.Python.3.11`
- **PostgreSQL** — either the shared Supabase/Neon string from a teammate,
  or your own local Postgres
- **Model weights** (gitignored; get from Maheen) — copy into the repo root:
  - `checkpoints/efficientnet_b0_best.pt`
  - `checkpoints/tampering_cnn_best.pt`
  - `models/efficientnet_b0.onnx`
  - `models/efficientnet_b0_int8.onnx`

Without the weight files, ai-engine still starts but `/health` shows
`models_loaded` false and analyze endpoints return `503`.

### One-time installs

**Terminal A — ai-engine venv (repo root):**

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install "stringzilla==5.0.3"
pip install -e ".[ml,optimize]"
pip install "grad-cam==1.5.5"
pip install -r ai-engine\requirements.txt
```

> If `Activate.ps1` is blocked, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

> Pin `stringzilla==5.0.3` (has a Windows wheel; newer versions need MSVC
> Build Tools). Pin `grad-cam==1.5.5` (`1.5.7` ships an empty package on
> Windows and breaks with `No module named 'pytorch_grad_cam'`).

**Terminal B — decision-engine venv:**

```powershell
cd decision-engine
py -3.11 -m venv venv_de
.\venv_de\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
```

**Terminal C — core-api:**

```powershell
cd core-api
copy .env.example .env
# edit .env — set DATABASE_URL, JWT_SECRET, AI_ENGINE_URL, DECISION_ENGINE_URL
bun install
bunx --bun prisma generate
# If the schema changed or this is a fresh DB, also:
# npx prisma db push
# npx tsx prisma/seed.ts
cd ..
```

### When to run `prisma generate` (not every day)

`npx prisma generate` / `bunx --bun prisma generate` is **not** part of the
daily start. Run it only when:

| Situation | Command |
|-----------|---------|
| First-time setup / after `bun install` | `bunx --bun prisma generate` (already in one-time installs above) |
| Someone changed `core-api/prisma/schema.prisma` (or you pulled such a change) | `npx prisma db push` then `npx prisma generate`, then **hard-restart** core-api |
| Auth activity / new models missing at runtime (`prisma.xyz is undefined`) | Same as above — Bun `--watch` often does **not** reload `@prisma/client` |

You do **not** need `prisma generate` every time you open the four terminals
for a normal coding day.

`.env` needs at minimum:

```
DATABASE_URL="<ask teammate for the Supabase/Neon connection string>"
JWT_SECRET="anything-for-local-dev"
AI_ENGINE_URL="http://localhost:8000"
DECISION_ENGINE_URL="http://localhost:8001"
```

**Terminal D — frontend:**

```powershell
cd frontend
copy .env.example .env.local
bun install
cd ..
```

---

## Daily run (four Cursor terminals)

Leave each process running in its own Cursor terminal tab (do not close
the tab). To stop a service later, focus that tab and press `Ctrl+C`.

### 1. ai-engine (port 8000) — Cursor terminal tab 1

```powershell
cd D:\FYP\Falsora
.\venv\Scripts\Activate.ps1
uvicorn ai-engine.main:app --port 8000 --reload
```

Check: http://localhost:8000/health  
Expect `"models_loaded":{"static":true,"frame":true}` when weights are present.

### 2. decision-engine (port 8001) — Cursor terminal tab 2

```powershell
cd D:\FYP\Falsora\decision-engine
.\venv_de\Scripts\Activate.ps1
uvicorn main:app --port 8001 --reload
```

Check: http://localhost:8001/health  
Stateless — no database, no env vars needed.

### 3. core-api (port 4000) — Cursor terminal tab 3

```powershell
cd D:\FYP\Falsora\core-api
bun run --watch src/index.ts
```

Check: http://localhost:4000/health

> No `prisma generate` here on a normal day. Only re-run generate (and
> restart this process with Ctrl+C → start again) after a schema change —
> see **When to run `prisma generate`** above.

Demo login credentials (fallback, work even without a DB row):

- `admin@falsora.ai` / `admin123`
- `reviewer@falsora.ai` / `reviewer123`
- `user@falsora.ai` / `user123`

### 4. frontend (port 3000) — Cursor terminal tab 4

```powershell
cd D:\FYP\Falsora\frontend
bun run dev
```

Open http://localhost:3000, log in with a demo credential above, and
upload an image on the case creation page. Within ~5 seconds you should
see a real per-image AI Detection Breakdown (not identical numbers on
every case) — that confirms all four services are talking to each other.

---

## macOS / Linux (same order)

```bash
# 1. ai-engine — from repo root
python3.11 -m venv venv && source venv/bin/activate
pip install -e ".[ml,optimize]" && pip install -r ai-engine/requirements.txt
uvicorn ai-engine.main:app --port 8000 --reload

# 2. decision-engine
cd decision-engine
python3.11 -m venv venv_de && source venv_de/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8001 --reload

# 3. core-api
cd core-api
cp .env.example .env   # fill DATABASE_URL etc.
bun install && bunx --bun prisma generate
bun run --watch src/index.ts

# 4. frontend
cd frontend
cp .env.example .env.local
bun install && bun run dev
```

---

## Troubleshooting

- **AI Detection Breakdown shows the same numbers on every case** — the
  ai-engine (port 8000) isn't running or `core-api`'s `AI_ENGINE_URL` is
  wrong; `core-api` degrades gracefully to a `0.0` score if it can't
  reach it, check `core-api`'s terminal for `[ai-engine] ... unreachable`
  warnings.
- **Cases list only shows canned demo cases (CAS-142, etc.)** — this is
  expected fallback behavior when the real `cases` table is empty; upload
  something to create a real case.
- **Prisma "Environment variable not found: DATABASE_URL"** — you skipped
  the `.env` setup step in `core-api`.
- **Admin Settings → Auth activity stays empty / `prisma.authActivityLog`
  undefined in core-api logs** — schema/client was updated but core-api
  still has an old Prisma client in memory. From `core-api`:
  `npx prisma db push`, `npx prisma generate`, then **Ctrl+C** and
  restart `bun run --watch src/index.ts` (watch alone is not enough).
  Log in again as User then Admin and click Refresh on Auth activity.
- **ai-engine `/health` shows `models_loaded: {"static": false}` or
  `{"frame": false}`, or a request returns `503 model_unavailable`** —
  the trained model checkpoints/ONNX files are gitignored (too large for
  GitHub) so a fresh clone never has them. This is expected on a new
  machine, not a bug — the service now starts and stays up in this
  degraded mode instead of crashing entirely. Get the real
  `checkpoints/` and `models/` files from Maheen and drop them in the
  repo root, then restart ai-engine; `/health` should show both as
  `true`.
- **`Package 'falsora-ai' requires a different Python: 3.13.x not in
  '<3.12,>=3.10'`** — recreate the venv with Python 3.11:
  `py -3.11 -m venv venv`.
- **`No module named 'pytorch_grad_cam'`** — install `grad-cam==1.5.5`
  (not 1.5.7).
- **`Failed building wheel for stringzilla` / MSVC required** — install
  `stringzilla==5.0.3` before `pip install -e ".[ml,optimize]"`.
