# 🦋 Titli Forensics Platform

Advanced AI Deepfake Detection & Media Forensics System.

## Documentation

For a full breakdown of the architecture, tech stack, and implemented frontend/backend features, see **[SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md)**.

## Getting Started

### 1. Configure Environment Variables
Copy the `.env.example` files to `.env` in both the `core-api/` and `frontend/` directories.
Make sure to provide your real PostgreSQL database connection string in `core-api/.env`.

### 2. Start Core API (Backend)
```bash
cd core-api
bun install
bun run dev
```

### 3. Start Frontend (Next.js)
```bash
cd frontend
bun install
bun run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Start AI Engine (Python Microservice)
*Note: Ensure Python 3.10+ is installed.*
```bash
cd ai-engine
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 5. Start Decision Engine (Mehreen's Trust Scoring Service)
```bash
cd decision-engine
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

### Credentials
* **Email:** `admin@titli.ai`
* **Password:** `admin123`
