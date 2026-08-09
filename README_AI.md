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
| M2 | — | Torch Dataset, transforms, dataloaders | ⬜ |
| M3 | 6.6a | EfficientNet deepfake model + frame/video AUC + cross-dataset eval | ⬜ |
| M4 | 6.6b | CASIA v2.0 tampering branch (ELA + residual + classifier) | ⬜ |
| M5 | 6.6 | Fused engine emitting `ForgeryResult` | ⬜ |
| M6 | 6.7 | Grad-CAM heatmaps, evidence persistence | ⬜ |
| M7 | — | ONNX export, INT8 quantization, measured latency | ⬜ |
| M8 | 6.16 | Frame buffer, rolling score, HIGH-RISK alerts | ✅ **Done** — 223 tests passing |
| M9 | — | Service adapters + integration guide | ⬜ |
| M10 | — | Final metrics, model card, scope-document corrections | ⬜ |

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

Listed in full in `ENGINEERING_PLAN.md` section 6. Summary: NIST Nimble was not obtained; Celeb-DF v2 is used but undeclared in Section 8; Table 5 still assigns metadata analysis to Maheen after the division changed; and the "8–12 ms" latency figure in Section 5.1 is currently unverified and will be replaced with a measured number in M7.
