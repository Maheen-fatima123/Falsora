# Falsora — AI & Forensic Engine: Master Engineering Plan

**Owner:** Maheen Fatima (231659) — AI & Forensic Engine Developer
**Modules in scope:** 6.6 Forgery & Tampering Detection Engine · 6.7 AI Interpretability & Evidence Visualization · 6.16 Frame Buffer & Rolling Score Engine · Model Optimization
**Explicitly NOT in scope (reassigned to Ujala):** 6.5 Source Integrity / EXIF metadata analysis
**Status:** Plan locked. Implementation begins at Module 0.

---

## 1. Audit of the current state

### 1.1 Code

Eight files exist. Six are empty or stubs.

| File | State | Verdict |
|---|---|---|
| `app.py` | Prints a string | Placeholder, will be replaced |
| `utils/config.py` | Paths + hyperparameters, prints device at import | Salvage the values, rewrite the module |
| `preprocessing/transforms.py` | **Empty** | Write from scratch |
| `preprocessing/dataset.py` | **Empty** | Write from scratch |
| `training/train.py` | **Empty** | Write from scratch |
| `inference/predict.py` | **Empty** | Write from scratch |
| `scripts/extract_frames.py` | Working but defective | Rewrite (see 1.2) |
| `requirements.txt` | 68 pinned packages, sensible set | Keep, prune, add |

`models/`, `outputs/`, `gradcam/`, `optimization/`, `websocket/`, `extracted_frames/`, and all six `datasets/{train,validation,test}/{real,fake}` folders are empty. Nothing has been trained. There is no git repository in this folder.

### 1.2 Defects in `scripts/extract_frames.py`

Three defects, in descending order of severity.

**No identity-disjoint splitting.** The script writes frames into `extracted_frames/<dataset>/<label>/<video_stem>/`. If a later split step shuffles at the *frame* level, frames of the same person — often of the same video — land in both train and test. The measured accuracy then reflects memorisation, not detection. A model that reports 99% under frame-level shuffling routinely drops to 65–75% under video-level splitting. This is the single most common way an FYP deepfake project fails its demo, and it must be designed out from the start, not patched later.

**No face detection or cropping.** Section 5.1 Stage 3 of the scope document commits to "OpenCV is used to detect and crop the face region before inference." Training on full 1920×1080 frames while inferring on face crops is a train/serve mismatch that destroys accuracy. Face cropping belongs in extraction, not inference.

**No crash safety.** `metadata_rows` accumulates in memory for the entire run and is written once at the end. This job takes hours; any interruption loses all metadata. The resume check (`if len(existing) >= MAX_FRAMES_PER_VIDEO: return`) also skips re-recording metadata for already-extracted videos, so a resumed run silently produces an incomplete manifest.

Two lesser issues: `FRAME_INTERVAL = 50` with the comment "every 30 frames" (stale comment), and fixed-stride sampling that biases toward the start of long videos rather than sampling uniformly across the whole clip.

### 1.3 Datasets — verified on disk

| Path | Videos | Label | Size |
|---|---:|---|---:|
| `FaceForensics++_C23/original` | 1,000 | REAL | 1.9 GB |
| `FaceForensics++_C23/Deepfakes` | 1,000 | FAKE | 1.9 GB |
| `FaceForensics++_C23/Face2Face` | 1,000 | FAKE | 1.9 GB |
| `FaceForensics++_C23/FaceSwap` | 1,000 | FAKE | 1.6 GB |
| `FaceForensics++_C23/FaceShifter` | 1,000 | FAKE | 1.8 GB |
| `FaceForensics++_C23/NeuralTextures` | 1,000 | FAKE | 1.5 GB |
| `FaceForensics++_C23/DeepFakeDetection` | 1,000 | FAKE | 6.5 GB |
| `FF++/real` | 200 | REAL | 1.5 GB |
| `FF++/fake` | 200 | FAKE | 1.3 GB |
| `Celeb DF/Celeb-real` | 590 | REAL | — |
| `Celeb DF/YouTube-real` | 300 | REAL | — |
| `Celeb DF/Celeb-synthesis` | 5,639 | FAKE | — |

**Verified finding — `FF++/fake` is a duplicate.** All 200 filenames in `FF++/fake` are an exact subset of the 1,000 in `FaceForensics++_C23/DeepFakeDetection`. Including both double-counts those videos and, worse, can place the same video in train and test. **`FF++/fake` is excluded from the pipeline.**

**Verified finding — `FF++/real` is essential, not a duplicate.** Its 200 files (actors `01`–`16`) have zero overlap with `DeepFakeDetection` and are the DFD *actor originals*. They are the only REAL counterpart to the 1,000 DFD fakes anywhere on disk. **`FF++/real` is kept and relabelled `DFD_real`.**

**Supporting metadata available.** `FaceForensics++_C23/csv/` contains per-manipulation CSVs with frame count, resolution, codec and file size for all 7,000 C23 videos — useful for stratifying by resolution and for the dataset section of the final report. `Celeb DF/List_of_testing_videos.txt` is present, which gives us the *official* Celeb-DF test split; we will honour it rather than inventing our own.

**Gap — CASIA v2.0 and NIST Nimble are absent.** Per your decision: download CASIA v2.0 (~1.2 GB) to train the tampering branch; drop NIST Nimble and correct Section 8.2 of the scope document to list it as future work. Section 8 must also be amended to declare Celeb-DF v2, which is on disk and central to our cross-dataset evaluation but is not currently mentioned anywhere in the document.

---

## 2. Compute specification

You asked what you need. Here is the answer, derived from measured dataset sizes.

### 2.1 The work, quantified

The pipeline has two cost centres with completely different hardware needs.

**Frame extraction + face cropping** is I/O and CPU bound over 13,729 videos and 26 GB of source data. Estimated 3–5 hours on 4 CPU workers, one time only. Sending 26 GB to Colab to do this would take longer than doing it locally.

**Model training** is GPU bound over ~137,000 face crops totalling roughly 3.5 GB. This is where a GPU is worth 20× the wall-clock.

### 2.2 Recommended setup: hybrid

> **Extract locally on CPU (overnight, once). Upload only the ~3.5 GB crop dataset. Train on Colab or Kaggle GPU.**

This is the right answer for your situation and I will build the pipeline around it. The extraction script will be checkpointed and resumable so an overnight run that dies at 70% resumes where it stopped.

### 2.3 Minimum requirements

**Your local machine (extraction only):**

- 4+ CPU cores, 8 GB RAM
- **~35 GB free disk** — 26 GB raw (already used) + ~4 GB crops + ~2 GB checkpoints + headroom
- Python 3.10 or 3.11. **Not 3.12+** — several pinned packages in `requirements.txt` have no 3.12 wheels
- No GPU required for this stage

**Training (pick one):**

| Option | VRAM | Suitability |
|---|---|---|
| Colab free (T4, 16 GB) | 16 GB | **Sufficient for everything we need.** 12h session cap → checkpoint-resume is mandatory, which I am building in regardless |
| Kaggle (P100/T4, 30h/week quota) | 16 GB | Better than Colab free: 9h uninterrupted sessions, more reliable. **My recommendation if you have to choose one** |
| Colab Pro | 16–40 GB | Worth ~$10 for the month you train. Removes most of the pain |
| Local NVIDIA GPU | 6 GB min / 8 GB comfortable | Only if you already have one |

**Apple Silicon note:** if your Mac is M1/M2/M3, MPS will run this but at roughly 4–6× a T4, and a few ops silently fall back to CPU. Use it for debugging and short runs; use a real GPU for the final training run.

### 2.4 Estimated training time (T4)

| Model | Input | Purpose | ~min/epoch | 12 epochs |
|---|---|---|---:|---:|
| EfficientNet-B0 | 224 | **Live-stream path (scope-mandated)** | ~9 | ~1.8 h |
| EfficientNet-B3 | 300 | Static path, balanced | ~26 | ~5.2 h |
| EfficientNet-B4 | 320 | Static path, best accuracy | ~42 | ~8.4 h |

Strategy: train B0 first and get the entire pipeline working end to end with a real (if modest) number. Only then scale to B3/B4. Never leave the pipeline unproven while chasing accuracy.

---

## 3. Architecture

### 3.1 Design principle

Your requirement was that each module be independent yet properly integrated. Those pull in opposite directions unless the seam between modules is an explicit, versioned data contract rather than a shared import. So:

- Every module exposes **one function or one class** with a typed signature.
- All cross-module data structures live in **`falsora_ai/contracts.py`** as Pydantic models. This file is the integration surface with Ujala (6.13/6.14 backend) and Mehreen (6.8 Decision Intelligence). It is versioned; changing it is a deliberate, announced act.
- **Module 6.16 must not import torch.** It is pure Python over a `deque`. This makes it independently unit-testable in milliseconds, and lets Ujala's WebSocket server use it without loading a model.
- Module 6.7 (Grad-CAM) depends on 6.6's model handle but never on its training code.
- No module reads global mutable state. Configuration is injected.

### 3.2 Package layout

```
falsora_ai/
  __init__.py
  contracts.py           # ← THE integration contract (Pydantic). Shared with Ujala & Mehreen.
  config.py              # dataclass config, no side effects on import
  common/
    faces.py             # face detection + margin cropping (MTCNN)
    video.py             # uniform frame sampling, robust decode
    seed.py              # determinism
    logging.py
  data/
    manifest.py          # build video-level manifest from raw_datasets/
    splits.py            # ← identity-disjoint split logic. Highest-risk file in the repo.
    extract.py           # parallel, resumable frame+face extraction
    datasets.py          # torch Dataset over the crop manifest
    transforms.py        # albumentations; compression-aware augmentation
  engine_66/             # 6.6 Forgery & Tampering Detection Engine
    deepfake/
      model.py           # EfficientNet-B0/B3/B4 backbone, 1 logit
      train.py           # checkpoint-resume, AMP, early stop
      evaluate.py        # frame-level + video-level AUC, cross-dataset
    tampering/
      ela.py             # Error Level Analysis
      residual.py        # noise / SRM residual features
      model.py           # CASIA v2.0-trained tampering classifier
    engine.py            # fuses both branches → ForgeryResult
  engine_67/             # 6.7 Interpretability
    gradcam.py           # Grad-CAM / Grad-CAM++ over the 6.6 backbone
    overlay.py           # heatmap rendering, evidence PNG persistence
  engine_616/            # 6.16 Frame Buffer & Rolling Score  (NO torch import)
    buffer.py            # deque(maxlen=5) sliding window
    rolling.py           # rolling score, hysteresis, HIGH-RISK trigger
    evidence.py          # snapshot capture on alert
  optimization/          # Model Optimization
    export_onnx.py
    quantize.py          # INT8 dynamic quantization
    benchmark.py         # latency proof for the 8–12 ms scope claim
  service/
    predict_static.py    # single entry point for Ujala's REST path
    predict_frame.py     # single entry point for Ujala's WebSocket path
tests/
scripts/
notebooks/
```

### 3.3 Module 6.6 — two branches, one engine

The scope commits to detecting *both* AI face forgery *and* classical tampering (splicing, copy-move). These are different problems with different data and cannot share one model.

**Branch A — Deepfake detection.** EfficientNet backbone, single logit, sigmoid → P(fake). Trained on face crops from FF++ C23, DFD and Celeb-DF. Two trained variants: B0@224 for the live path (quantized, per scope Section 5.1), and B3 or B4 for the static path.

**Branch B — Tampering detection.** Trained on CASIA v2.0. Operates on the *whole image*, not the face crop, because splicing artefacts are global. Input is the image plus its Error Level Analysis map and a noise residual — a well-established and defensible approach for CASIA-scale data.

**Fusion.** `engine.py` runs both branches and emits a single `ForgeryResult` carrying both probabilities, the individual signals, and a calibrated confidence. It deliberately does **not** decide Low/Medium/High risk — that is Mehreen's 6.8 Decision Intelligence Engine. Keeping that boundary clean matters; if 6.6 starts assigning risk levels, 6.8 has nothing to do and the module division collapses.

### 3.4 The split protocol (the part that must not be got wrong)

Every dataset here is assigned exactly one **role**, encoded in `DataConfig.DOMAIN_ROLES` and enforced by `tests/test_config.py::TestDatasetRoles`:

| Domain | Role | Meaning |
|---|---|---|
| `ffpp` | `train_pool` | split into train / val / test by identity |
| `dfd` | `train_pool` | split into train / val / test by actor |
| `celebdf` | `heldout_test` | never seen during training, at all |

**FF++ C23** splits by the *original* video id. A manipulated file `TARGET_SOURCE.mp4` inherits the split of `TARGET`, and both identities in a pair must land in the same split. A union-find pass over the 1,000 original ids and their 5,000 manipulation filenames confirms the graph is 500 clean components of size 2, which partitions exactly into 720/140/140 at our ratios.

**DFD** splits by actor id (`01`–`28`). The connectivity here is coarse — the actor-pairing graph collapses to 3 components of 18, 5 and 5 actors, so the best achievable partition is 18/5/5 actors rather than a clean 72/14/14 percentage. That is a property of the data, not a bug, and the split code must not "fix" it by breaking a component apart.

**Celeb-DF v2 is held out entirely.** This overturns the obvious approach and the reason is worth recording. Celeb-DF ships an official `List_of_testing_videos.txt`, and the natural move is to train on the remainder and evaluate on that list. Checking it first: **56 of the 59 celebrity identities appear on both sides.** Training on the remainder and reporting accuracy on the test list would largely measure whether the model has memorised those 56 faces. The number would be high and it would mean nothing.

So Celeb-DF is not trained on in any form. It becomes a genuine unseen-dataset benchmark, which is also the standard "train on FF++, evaluate on Celeb-DF" protocol used throughout the deepfake detection literature — so our number will be directly comparable to published ones. Expect it to be substantially lower than in-domain AUC. That gap is the honest generalisation result and belongs in the report explicitly rather than buried.

`tests/test_splits.py` will **assert zero identity overlap** between splits and fail the build if it is ever violated. `tests/test_config.py::TestDatasetRoles` separately pins the hold-out, so no future edit can quietly promote Celeb-DF into the training pool.

### 3.5 Frame budget

Two budgets, because the two roles have different goals. The training pool is tuned for class balance; the held-out benchmark is tuned for uniform evaluation depth.

**Training pool** — balanced globally *and within each domain*, so no class re-weighting is needed:

| Source | Videos | Label | Frames/video | Crops |
|---|---:|---|---:|---:|
| FF++ original | 1,000 | REAL | 32 | 32,000 |
| FF++ Deepfakes | 1,000 | FAKE | 7 | 7,000 |
| FF++ Face2Face | 1,000 | FAKE | 7 | 7,000 |
| FF++ FaceSwap | 1,000 | FAKE | 7 | 7,000 |
| FF++ FaceShifter | 1,000 | FAKE | 7 | 7,000 |
| FF++ NeuralTextures | 1,000 | FAKE | 7 | 7,000 |
| DFD real (`FF++/real`) | 200 | REAL | 32 | 6,400 |
| DFD fake | 1,000 | FAKE | 7 | 7,000 |
| **Total** | **7,200** | | | **80,400** |

Balance: 38,400 real vs 42,000 fake — **1 : 1.09**, and 1:1.09 within both `ffpp` and `dfd` independently. Storage ≈ **2.0 GB** at 300 px JPEG q95.

**Held-out benchmark (Celeb-DF).** Only the 518 videos on the official test list are extracted at all; the other ~6,000 would cost hours of CPU for data we have committed never to train on. Uniform 32 frames/video, ≈ 16,600 crops, ≈ 0.4 GB. Balance is irrelevant here because evaluation is by AUC, which is insensitive to class prior — but the metric is reported per class as well so a skewed accuracy figure can't hide behind it.

Total extraction is therefore ~97k crops from 7,718 videos, down from the 137k/13,729 of the earlier all-in plan — roughly two hours of CPU saved and a materially more trustworthy evaluation.

Frames are sampled **uniformly across each video's full duration**, not at a fixed stride from the start, so we capture varied pose and lighting rather than 20 near-identical frames from the opening seconds.

### 3.6 Augmentation

The scope acknowledges that compression and lighting degrade live-stream accuracy. Augmentation is where we mitigate that, so it is a correctness concern rather than a nicety: JPEG compression (quality 30–95), downscale-and-upscale, Gaussian blur and motion blur, brightness/contrast/gamma jitter, and horizontal flip. No vertical flip and no aggressive rotation — faces have a canonical orientation and destroying it costs accuracy.

---

## 4. Build sequence

Each module is one branch, one pull request, one demonstrable artefact. Nothing merges without its test passing.

| # | Branch | Deliverable | Depends on |
|---|---|---|---|
| **M0** | `feat/ai-m0-skeleton` | `.gitignore`, package skeleton, `contracts.py`, `config.py`, pytest + CI | — |
| **M1** | `feat/ai-m1-data-pipeline` | Manifest builder, identity-disjoint splits, resumable face extraction | M0 |
| **M2** | `feat/ai-m2-datasets` | Torch Dataset, transforms, dataloaders, sanity notebook | M1 |
| **M3** | `feat/ai-m3-deepfake-model` | **6.6a** — EfficientNet trained; frame + video AUC; cross-dataset eval | M2 |
| **M4** | `feat/ai-m4-tampering` | **6.6b** — CASIA v2.0 branch: ELA, residual, classifier | M2 |
| **M5** | `feat/ai-m5-engine-66` | **6.6** — fused engine emitting `ForgeryResult` | M3, M4 |
| **M6** | `feat/ai-m6-gradcam` | **6.7** — Grad-CAM heatmaps, evidence persistence | M5 |
| **M7** | `feat/ai-m7-optimization` | **Model Optimization** — ONNX, INT8, latency benchmark | M5 |
| **M8** | `feat/ai-m8-rolling-score` | **6.16** — frame buffer, rolling score, HIGH-RISK alerts | M0 only |
| **M9** | `feat/ai-m9-service` | Service adapters + integration guide for Ujala and Mehreen | M6, M7, M8 |
| **M10** | `feat/ai-m10-eval-report` | Final metrics, model card, scope-document corrections | all |

Note that **M8 depends only on M0**. Module 6.16 has no ML dependency, so if training stalls or the GPU is unavailable, 6.16 can be built and merged in parallel. That is deliberate scheduling insurance.

### 4.1 M1 as built — realised splits

`python -m falsora_ai.data manifest` scans the datasets, assigns splits, verifies disjointness and writes `manifests/videos.csv` (committed, 1 MB, so the split is reviewable in a pull request). Re-running it produces a byte-identical file.

| domain | split | videos | crops | identity groups |
|---|---|---:|---:|---:|
| ffpp | train | 4,320 | 48,240 | 360 |
| ffpp | val | 840 | 9,380 | 70 |
| ffpp | test | 840 | 9,380 | 70 |
| dfd | train | 1,005 | 11,210 | 1 |
| dfd | test | 195 | 2,190 | 2 |
| celebdf | heldout | 518 | 16,576 | 79 |

Training balance after assignment: 28,384 real vs 31,066 fake crops, **1:1.09**.

Two consequences of the data that the numbers above make visible:

**DFD gets no validation set.** Its 28 actors form only 3 identity components (18, 5 and 5 actors), so 83% of the domain is a single indivisible block. A three-way split would have left validation with 22 real videos and test with 11 — sample sizes on which an AUC is indistinguishable from noise. `DataConfig.min_groups_for_val` folds validation's share into test instead, giving one usable evaluation slice of 33 real / 162 fake videos. Model selection therefore runs on the FF++ validation set, which has 840 videos across 70 independent groups.

**Celeb-DF's 340 test-list fakes span only 4 identity components.** This is the quantitative confirmation of the leakage finding in section 3.4: the synthesis identity graph is so densely connected that the official test list cannot be identity-disjoint from the remainder. It is the reason the domain is held out rather than split.

Measured on this machine: decode-and-crop runs at ~0.9 s/video (≈2 hours for all 7,718), and crops average 23 KB, projecting to **2.3 GB** of face crops. MTCNN detection is the dominant remaining cost and is expected to take the total to roughly 4–8 hours on 4 CPU cores — hence the resumable ledger.

---

## 5. Definition of done per module

A module is complete only when all four hold:

1. Public API matches its `contracts.py` type signature.
2. Unit tests pass and cover the failure paths, not only the happy path.
3. It runs standalone via a documented CLI or function call.
4. Its README section states inputs, outputs, and how the other two team members call it.

---

## 6. Scope-document corrections required before final submission

These are factual mismatches between the submitted document and what the project actually does. Flagging them now avoids an awkward panel question later.

1. **Table 5** lists Metadata Analysis and AI Integration under Maheen; the updated division moves 6.5 to Ujala. Table 5 must be regenerated from the current division.
2. **Section 8.2 (NIST Nimble)** — dataset not obtained. Reword as future work, or remove.
3. **Section 8 / Table 2** — Celeb-DF v2 is used (6,529 videos) but is not declared. Add it, with its role stated as cross-dataset generalisation testing.
4. **Section 8.3** claims "approximately 1 million frames." We use ~137,000 face crops sampled from those frames. State the sampling strategy rather than implying all frames are used — a panel will ask.
5. **Section 5.1** claims "~8–12 ms inference latency per frame on standard CPU." This is currently an unverified claim copied from literature. Module M7 will measure it on your actual hardware, and the number in the document must be replaced with the measured one.

---

## 7. Open item

The GitHub repository URL and its current branch/folder structure are still needed before M0 can be pushed. Everything in M0 can be built locally in the meantime.
