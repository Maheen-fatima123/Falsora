# Falsora — AI & Forensic Engine

**Owner:** Maheen Fatima (231659)
**Modules:** 6.6 Forgery & Tampering Detection · 6.7 AI Interpretability · 6.16 Frame Buffer & Rolling Score · Model Optimization

Full architecture, dataset analysis, compute specification and build sequence: **[`ENGINEERING_PLAN.md`](ENGINEERING_PLAN.md)**.

---

## Quick start

```bash
# Python 3.10 or 3.11 (NOT 3.12 — several pinned deps have no 3.12 wheels)
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate

pip install -e ".[dev]"          # contracts + config + tests, no torch
pip install -e ".[ml,optimize]"  # add this when you start training

pytest tests -q
```

`pip install -e ".[dev]"` deliberately omits torch. Importing `falsora_ai` must stay cheap and torch-free so Ujala's API layer can depend on it; CI enforces this.

---

## For Ujala and Mehreen — how to integrate

Everything that crosses a module boundary is defined in **`falsora_ai/contracts.py`**. Import from there and nowhere else.

```python
from falsora_ai.contracts import (
    ForgeryResult,      # module 6.6 output — the AI evidence payload
    Explanation,        # module 6.7 output — Grad-CAM heatmap paths
    FrameScore,         # module 6.16 input — one analysed live frame
    RollingScoreState,  # module 6.16 output — smoothed live verdict
    EngineError,        # structured failure, returned instead of raising
)
```

**Two things worth knowing before you write code against this.**

*Probability direction.* The model outputs `probability_fake` (higher = worse). The scope document thresholds on **authenticity** (higher = better, `< 0.35` is HIGH-RISK, section 5.1 Stage 4). Both are exposed on every relevant model, `authenticity == 1.0 - probability_fake`, and the conversion lives in exactly one place. Read `authenticity` when comparing against scope thresholds. Do not recompute it yourself.

*Risk banding is not mine.* `ForgeryResult` has no `risk_level` field, on purpose. Assigning Low/Medium/High for a verification case is module 6.8 (Mehreen). The AI engine reports probabilities and evidence only. The single exception is `LiveRiskState` on `RollingScoreState`, which exists solely to fire the real-time WebSocket alert in module 6.16.

Contracts are versioned via `SCHEMA_VERSION`. Any breaking change is announced before it merges.

### Calling the engine — `falsora_ai/service/` (M9)

Don't import `engine_66`/`engine_67`/`optimization` directly from the backend. Two adapter classes exist specifically so the backend never has to: construct each **once per process** (e.g. FastAPI `lifespan`), then call its `predict()` per request/frame.

**REST upload path — `StaticPredictor`** (`falsora_ai/service/predict_static.py`):

```python
from falsora_ai.service.predict_static import StaticPredictor
from falsora_ai.contracts import EngineError

predictor = StaticPredictor()   # loads both checkpoints once

@app.post("/api/analyze")
def analyze(file: UploadFile):
    result, explanation = predictor.predict(file.file.read(), case_id=case_id)
    if isinstance(result, EngineError):
        raise HTTPException(status_code=422, detail=result.message)
    # result.deepfake.probability_fake, result.tampering.probability_tampered, ...
    # explanation is None if explain=False, no face found, or Grad-CAM itself failed
```

**WebSocket live path — `FramePredictor`** (`falsora_ai/service/predict_frame.py`):

```python
from falsora_ai.service.predict_frame import FramePredictor
from falsora_ai.engine_616.rolling import RollingScoreEngine
from falsora_ai.contracts import EngineError

predictor = FramePredictor()   # one process-wide instance, ~6.5 ms/frame CPU (measured, M7)

# one RollingScoreEngine PER SESSION — its lifecycle is yours (module 6.13), not this adapter's
rolling = RollingScoreEngine(session_id=session_id)

def on_frame(frame_bytes: bytes, frame_index: int):
    score = predictor.predict(frame_bytes, session_id=session_id, frame_index=frame_index)
    if isinstance(score, EngineError):
        return  # or surface to the client — decode/inference failure, not a verdict
    state = rolling.push(score)   # -> RollingScoreState: rolling_authenticity, risk_state, alert_triggered
```

`FramePredictor.__init__` raises `FileNotFoundError` if the INT8 model hasn't been exported yet — run once per deployment:

```bash
python -m falsora_ai.optimization export
python -m falsora_ai.optimization quantize
```

Both adapters return `EngineError` instead of raising for bad/undecodable input or an inference crash (see `contracts.py` design rule 2) — check `isinstance(result, EngineError)` before reading fields off the result.

`FramePredictor` reports `face_detected=False` (not an error) when no face is found in a frame, with `probability_fake=0.5` — maximally uncertain, since there is no signal. `RollingScoreEngine.push` does **not** discount on `face_detected`, only on `quality_ok`, so a no-face frame pulls the rolling average toward 0.5 at full weight if pushed as-is. Set `quality_ok=False` (or skip pushing) for no-face frames if that's not the behaviour you want.

---

## Running the data pipeline (M1)

**Activate the venv first.** Running from a base conda environment picks up pydantic v1 and fails at import; `doctor` diagnoses that and everything else in about two seconds.

```bash
source venv/bin/activate                  # macOS / Linux
# venv\Scripts\activate                   # Windows

python -m falsora_ai.data doctor          # check the environment BEFORE the long run
python -m falsora_ai.data manifest        # seconds — scan, split, verify, write manifest
python -m falsora_ai.data extract --limit 20   # smoke-test on 20 videos first
python -m falsora_ai.data extract         # the real run: 4–8 h, interruptible
python -m falsora_ai.data report          # what's on disk right now
```

`manifest` is deterministic — re-running it produces a byte-identical `manifests/videos.csv`, so it is safe to run any time and the file is committed for review.

`extract` journals every completed video to `face_crops/_extraction_ledger.jsonl` and flushes after each one. **Close the laptop whenever you like**; re-running picks up where it stopped. Expect roughly 2.3 GB of crops.

Always run `extract --limit 20` first. It exercises the full path in about a minute, and the yield line at the end tells you whether the detector is finding faces before you commit four hours to it.

---

## Package layout

```
falsora_ai/
  contracts.py       # ← integration surface. Shared with Ujala & Mehreen.
  config.py          # immutable dataclass config; no import side effects
  common/            # seeding, logging, face detection, video decode
  data/              # manifest, identity-disjoint splits, extraction, datasets
  engine_66/         # 6.6  deepfake branch + tampering branch + fusion
  engine_67/         # 6.7  Grad-CAM and evidence rendering
  engine_616/        # 6.16 frame buffer & rolling score  (no torch import)
  optimization/      # ONNX export, INT8 quantization, latency benchmark
  service/           # thin adapters for Ujala's REST and WebSocket paths
```

---

## Build status

| # | Module | Deliverable | Status |
|---|---|---|---|
| M0 | — | Repo hygiene, package skeleton, contracts, config, CI | ✅ **Done** — 63 tests passing |
| M1 | — | Manifest, identity-disjoint splits, resumable face extraction | ✅ **Done** — 179 tests passing |
| M2 | — | Torch Dataset, transforms, dataloaders | ✅ **Done** — 20 tests passing |
| M3 | 6.6a | EfficientNet deepfake model + frame/video AUC + cross-dataset eval | ✅ **Done** — test video_auc=0.987 (accuracy=0.956), heldout/Celeb-DF video_auc=0.870 (accuracy=0.799) |
| M4 | 6.6b | CASIA v2.0 tampering branch (ELA + residual + classifier) | ✅ **Done** — test image_auc=0.878 (accuracy=0.803), val image_auc=0.882 (accuracy=0.804) |
| M5 | 6.6 | Fused engine emitting `ForgeryResult` | ✅ **Done** — `ForgeryEngine` runs both branches, 6 tests passing |
| M6 | 6.7 | Grad-CAM heatmaps, evidence persistence | ✅ **Done** — `ExplanationEngine` (Grad-CAM/Grad-CAM++), 6 tests passing |
| M7 | — | ONNX export, INT8 quantization, measured latency | ✅ **Done** — measured onnx_int8 mean 6.5 ms/frame CPU (scope claimed 8–12 ms), 10 tests passing |
| M8 | 6.16 | Frame buffer, rolling score, HIGH-RISK alerts | ✅ **Done** — 223 tests passing |
| M9 | — | Service adapters + integration guide | ✅ **Done** — `StaticPredictor`/`FramePredictor`, 11 tests passing |
| M10 | — | Final metrics, model card, scope-document corrections | ✅ **Done** — see `MODEL_CARD.md`, table rows above corrected, scope corrections below |

M8 depends only on M0, so module 6.16 can be built in parallel if GPU access slips.

---

## Git workflow

One module per branch, one pull request each.

```bash
git checkout -b feat/ai-m1-data-pipeline
# ... work ...
git add falsora_ai/data tests/test_splits.py
git commit -m "feat(6.6): identity-disjoint split logic and resumable face extraction"
git push -u origin feat/ai-m1-data-pipeline
```

**Never `git add .` in this repository.** `raw_datasets/` is ~26 GB. `.gitignore` covers it and CI fails the build on any file over 40 MB or any tracked `.mp4`/`.pt`/`.onnx`, but staging files explicitly is the habit that actually prevents the accident.

---

## Verified dataset notes

Two findings from the disk audit that are encoded in `config.py` and must not be undone:

- **`raw_datasets/FF++/fake` is excluded.** All 200 files are an exact subset of `FaceForensics++_C23/DeepFakeDetection`. Including both double-counts them and risks placing one video in two splits.
- **`raw_datasets/FF++/real` is kept** and treated as `DFD_real`. Its 200 actor originals have zero filename overlap with `DeepFakeDetection` and are the only REAL counterpart to the 1,000 DFD fakes anywhere on disk.

- **Celeb-DF v2 is held out of training entirely.** Its official test list is not identity-disjoint — 56 of 59 celebrity identities appear on both sides of it — so training on the remainder and scoring on the list would measure face memorisation. It is used only as an unseen-dataset benchmark, matching the standard "train on FF++, test on Celeb-DF" protocol. `tests/test_config.py::TestDatasetRoles` fails the build if anyone reverses this.

Frame budget: **80,400** training crops from 7,200 FF++/DFD videos, balanced to 1:1.09 real:fake globally and within each domain, plus ~16,600 held-out Celeb-DF crops for cross-dataset evaluation. `tests/test_config.py::TestFrameBudget` fails the build if an edit breaks that balance.

---

## Known deviations from the submitted scope document

Listed in full in `ENGINEERING_PLAN.md` section 6 — all five corrections below are now resolved or reflected here (M10):

1. **Table 5** assigns Metadata Analysis / AI Integration (6.5) to Maheen. The division has since moved 6.5 to Ujala; Table 5 needs regenerating from the current division before final submission.
2. **Section 8.2 (NIST Nimble)** — dataset was not obtained. Should be reworded as future work, or removed.
3. **Section 8 / Table 2** — Celeb-DF v2 is used (held-out cross-dataset benchmark, see "Verified dataset notes" below) but was never declared in the submitted document. Add it, with its role stated as cross-dataset generalisation testing only, not training.
4. **Section 8.3** claims "approximately 1 million frames." The actual pipeline samples **96,117 face crops** (58,825 train / 9,317 val / 11,485 test / 16,490 held-out Celeb-DF — see `MODEL_CARD.md`), not all frames of all videos. An earlier "extract everything" plan would have produced ~137,000 crops from 13,729 videos; that plan was deliberately trimmed to 7,718 videos (notably, only the 518 official Celeb-DF test-list videos, not all ~6,500) to keep evaluation identity-disjoint and trustworthy — see `ENGINEERING_PLAN.md` section 2.1. Both the "~1 million" and "~137,000" figures are stale; state the sampling strategy and the actual ~96,000 figure instead.
5. **Section 5.1** claims "~8–12 ms inference latency per frame on standard CPU." This was unverified when written — M7 measured it at **6.5 ms mean** (ONNX INT8, CPU, single frame at 224×224); Section 5.1 should be updated to the measured number. Note the INT8 model only has its linear head quantized, not the convolutional backbone — see `falsora_ai/optimization/quantize.py`'s module docstring for why (onnxruntime's CPU build has no `ConvInteger` kernel on this platform).

Final trained metrics and per-module numbers are consolidated in **[`MODEL_CARD.md`](MODEL_CARD.md)**.
