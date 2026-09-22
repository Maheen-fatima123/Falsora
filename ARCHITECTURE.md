# Falsora — Architecture & Data Model

**Scope of this document.** Two diagrams follow, held to different standards of
certainty:

1. **AI & Forensic Engine architecture** (Maheen's modules 6.6 / 6.7 / 6.16 /
   Model Optimization) — every box and arrow below traces directly to a file,
   class, or config value in this repository (`ENGINEERING_PLAN.md`,
   `falsora_ai/contracts.py`, `falsora_ai/config.py`). This is accurate as of
   `git log -1` on the branch this file was written from.
2. **Entity-Relationship Diagram** — deliberately **partial**. This repository
   contains no formal schema (no migration files, no ORM models, no `.sql`
   files — verified by search). The only tables that exist anywhere in code
   are `cases` and `analytics_logs`, referenced via raw SQL in
   `backend/main.py` and `backend/modules/orchestration.py`, an early
   scaffold that is not part of Maheen's owned modules. The columns shown are
   exactly the columns those queries touch — nothing more. Tables for
   auth/RBAC (6.1), media processing (6.2), fingerprinting (6.4), source
   integrity (6.5), and notifications (6.12) are owned by Ujala and Mehreen
   and do not exist in this codebase, so they are **not diagrammed** rather
   than guessed at. Treat this ERD as a starting point to be completed once
   their schema is available, not as a finished system ERD.

---

## 1. AI & Forensic Engine — module architecture

Source: `ENGINEERING_PLAN.md` §3.2 (package layout), §4 (build sequence),
`falsora_ai/contracts.py` (integration surface). Build status as of this
branch: M0, M1, M2, M8 done; M3 (this branch) done; M4 partially done
(ELA/residual/`TamperingCNN` architecture only, no training loop yet); M5–M7,
M9, M10 not started.

```mermaid
flowchart TB
    subgraph OFFLINE["Offline pipeline — runs once per dataset"]
        direction TB
        RAW["raw_datasets/\n(FF++, DFD, Celeb-DF, CASIA v2.0)"]
        MANIFEST["data/manifest.py\nidentity-disjoint splits"]
        EXTRACT["data/extract.py\nMTCNN face detect + crop\n(common/faces.py)"]
        CROPS["face_crops/\nmanifests/crops.csv"]
        CASIASPLIT["data/casia_manifest.py\ndata/casia_splits.py"]
        RAW --> MANIFEST --> EXTRACT --> CROPS
        RAW --> CASIASPLIT
    end

    subgraph M2["M2 — Dataset layer (done)"]
        DATASETS["data/datasets.py\nFaceCropDataset · TamperingDataset"]
        TRANSFORMS["data/transforms.py\ndeepfake_transforms (damage-sim)\ntampering_spatial_transforms (geometry-only)"]
        CROPS --> DATASETS
        CASIASPLIT --> DATASETS
        TRANSFORMS --> DATASETS
    end

    subgraph BRANCH_A["Branch A — 6.6a Deepfake (M3, done this branch)"]
        DFMODEL["engine_66/deepfake/model.py\nDeepfakeNet (timm EfficientNet-B0/B3/B4)"]
        DFTRAIN["engine_66/deepfake/train.py\ncheckpoint-resume · AMP · early stop"]
        DFEVAL["engine_66/deepfake/evaluate.py\nframe AUC · video AUC · cross-dataset (Celeb-DF)"]
        DFTRAIN --> DFMODEL
        DFEVAL --> DFMODEL
    end

    subgraph BRANCH_B["Branch B — 6.6b Tampering (M4, partial)"]
        ELA["engine_66/tampering/ela.py\nError Level Analysis"]
        RESIDUAL["engine_66/tampering/residual.py\nSRM noise residual"]
        TAMPMODEL["engine_66/tampering/model.py\nTamperingCNN (5-channel: RGB+ELA+residual)"]
        ELA --> TAMPMODEL
        RESIDUAL --> TAMPMODEL
    end

    DATASETS --> DFTRAIN
    DATASETS --> TAMPMODEL

    subgraph FUSION["6.6 fused engine (M5, not built)"]
        ENGINE["engine_66/engine.py"]
    end
    DFMODEL --> ENGINE
    TAMPMODEL --> ENGINE
    ENGINE -->|"ForgeryResult"| CONTRACTS

    subgraph M7["Model Optimization (M7, not built)"]
        ONNX["optimization/export_onnx.py"]
        QUANT["optimization/quantize.py\nINT8 dynamic quantization"]
        BENCH["optimization/benchmark.py\nmeasured latency"]
        ONNX --> QUANT --> BENCH
    end
    DFMODEL -.->|"B0, live path"| ONNX

    subgraph M6["6.7 Interpretability (M6, not built)"]
        GRADCAM["engine_67/gradcam.py\nGrad-CAM / Grad-CAM++"]
        OVERLAY["engine_67/overlay.py\nheatmap render + evidence PNG"]
        GRADCAM --> OVERLAY
    end
    ENGINE -.->|"model handle"| GRADCAM
    OVERLAY -->|"Explanation"| CONTRACTS

    subgraph M8["6.16 Frame Buffer & Rolling Score (done, no torch)"]
        BUFFER["engine_616/buffer.py\ndeque(maxlen=5)"]
        ROLLING["engine_616/rolling.py\nrolling score · hysteresis · HIGH_RISK trigger"]
        EVIDENCE["engine_616/evidence.py\nsnapshot capture on alert"]
        BUFFER --> ROLLING --> EVIDENCE
    end
    CONTRACTS -->|"FrameScore"| BUFFER
    ROLLING -->|"RollingScoreState"| CONTRACTS

    subgraph M9["Service adapters (M9, not built)"]
        PREDICT_STATIC["service/predict_static.py\nREST entry point"]
        PREDICT_FRAME["service/predict_frame.py\nWebSocket entry point"]
    end
    ENGINE -.-> PREDICT_STATIC
    ROLLING -.-> PREDICT_FRAME

    CONTRACTS["falsora_ai/contracts.py\n(Pydantic — the ONLY cross-module surface)\nForgeryResult · Explanation · FrameScore\nRollingScoreState · EngineError"]

    PREDICT_STATIC -->|"ForgeryResult, Explanation"| UJALA["Ujala\n6.2 Media · 6.13 Live Session · 6.14 WebSocket\nAPI / DB layer"]
    PREDICT_FRAME -->|"RollingScoreState"| UJALA
    CONTRACTS -->|"ForgeryResult"| MEHREEN["Mehreen\n6.8 Decision Intelligence\n6.10 Forensic Report · 6.12 Notifications"]
```

**Key architectural rules encoded above (from `ENGINEERING_PLAN.md` §3.1 and
`contracts.py`'s module docstring — not stylistic choices):**

- `falsora_ai/contracts.py` is the **only** cross-module data surface. Ujala
  and Mehreen import from there and nowhere else inside `falsora_ai`.
- `engine_616` (M8) never imports torch — it is pure Python over a `deque`,
  independently usable by Ujala's WebSocket server without loading a model.
- `ForgeryResult` deliberately has **no** `risk_level` field — Low/Medium/High
  banding belongs to Mehreen's 6.8 Decision Intelligence Engine, not the AI
  engine.
- `probability_fake` (ML convention, higher = worse) and `authenticity`
  (scope convention, higher = better) are complements exposed on every
  relevant model; the conversion lives in exactly one place
  (`FrameScore`/`DeepfakeSignal`'s `authenticity` computed field).

---

## 2. Entity-Relationship Diagram — verified portion only

Source: raw SQL in `backend/main.py` and `backend/modules/orchestration.py`.
No primary-key or foreign-key constraints, data types, or additional columns
are declared anywhere in code — the ones below are the exact columns each
query reads or writes, nothing inferred beyond that.

```mermaid
erDiagram
    CASES {
        string id "referenced as WHERE id = %s; type not declared in code"
        string status "e.g. submitted, under_analysis, pending_review, approved, rejected"
        float trust_score "written by /api/calculate-trust-score"
        string risk_level "Authentic | Uncertain | High-Risk (trust_engine.py)"
        int assigned_to "reviewer id; FK implied, not declared"
        datetime created_at
        datetime updated_at
    }
    ANALYTICS_LOGS {
        string case_id "FK to CASES.id, implied not declared"
        string event_type "e.g. status_changed_to_<new_status>"
    }
    CASES ||--o{ ANALYTICS_LOGS : "logs status changes for"
```

**Explicitly not diagrammed** (no code exists in this repo to verify them):
users/accounts + roles (6.1 Auth/RBAC), media/upload records (6.2), file
fingerprints (6.4), EXIF/source-integrity findings (6.5), notifications
(6.12), live session records (6.13). These belong to Ujala's and Mehreen's
modules. Ask them for their schema (or migration files, if any exist) to
extend this ERD accurately — I won't fabricate table structures I can't
verify.

**`VALID_TRANSITIONS` state machine** for `CASES.status`, from
`backend/modules/orchestration.py` (this part *is* fully verifiable — it's
plain Python, not inferred from SQL):

```mermaid
stateDiagram-v2
    [*] --> submitted
    submitted --> under_analysis
    under_analysis --> pending_review
    under_analysis --> approved
    pending_review --> approved
    pending_review --> rejected
    approved --> [*]
    rejected --> [*]
```
