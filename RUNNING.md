# Running Falsora locally

The system is four separate services that talk to each other over HTTP.
All four must be running at once for the full app (upload -> AI analysis ->
trust score -> dashboard) to work end to end.

| Service         | Owner   | Port | What it is                                      |
|-----------------|---------|------|--------------------------------------------------|
| `frontend`      | Ujala   | 3000 | Next.js dashboard (what you open in the browser) |
| `core-api`      | Ujala   | 4000 | Express + Prisma API, case/user management        |
| `decision-engine` | Mehreen | 8001 | FastAPI trust-scoring service                    |
| `ai-engine`     | Maheen  | 8000 | FastAPI wrapper around the deepfake/tampering models |

Start them in this order (each in its own terminal tab), from the repo root.

## 0. Prerequisites (one-time setup)

- **Node.js** >= 20.19 (Prisma 7 requirement) — check with `node -v`
- **Bun** — `npm install -g bun` if you don't have it
- **Python 3.11+** with a venv per Python service (see below) — each
  service has its own `venv`/`venv_de` folder; do not share one venv
  between `ai-engine` and `decision-engine`, their dependency sets differ
- **PostgreSQL** — either:
  - the shared Supabase project (ask a teammate for the connection string), or
  - your own local Postgres instance for isolated dev

## 1. ai-engine (port 8000)

```bash
# from repo root — falsora_ai must be pip-installed editable first
python3 -m venv venv
source venv/bin/activate
pip install -e ".[ml,optimize]"
pip install -r ai-engine/requirements.txt

uvicorn ai-engine.main:app --port 8000 --reload
```

Loads the trained model checkpoints at startup (`StaticPredictor` +
`FramePredictor`), so the first request may take a moment. Check
`http://localhost:8000/health` returns `{"status":"ok"}`.

## 2. decision-engine (port 8001)

```bash
cd decision-engine
python3 -m venv venv_de
source venv_de/bin/activate
pip install -r requirements.txt

uvicorn main:app --port 8001 --reload
```

Stateless — no database, no env vars needed.

## 3. core-api (port 4000)

```bash
cd core-api
cp .env.example .env   # then fill in DATABASE_URL (ask a teammate for the Supabase string)
bun install
bunx --bun prisma generate
bun run --watch src/index.ts
```

`.env` needs at minimum:
```
DATABASE_URL="<ask teammate for the Supabase connection string>"
JWT_SECRET="anything-for-local-dev"
AI_ENGINE_URL="http://localhost:8000"
DECISION_ENGINE_URL="http://localhost:8001"
```

Check `http://localhost:4000/health`.

Demo login credentials (fallback, work even without a DB row):
- `admin@falsora.ai` / `admin123`
- `reviewer@falsora.ai` / `reviewer123`
- `user@falsora.ai` / `user123`

## 4. frontend (port 3000)

```bash
cd frontend
cp .env.example .env.local
bun install   # or npm install
bun run dev   # or npm run dev
```

Open `http://localhost:3000`, log in with one of the demo credentials
above, and upload an image on the case creation page. Within ~5 seconds
you should see a real per-image AI Detection Breakdown (not identical
numbers on every case) — that confirms all four services are talking to
each other correctly.

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
