# Falsora AI Engine — Model Card

**Module:** M10 (final metrics, model card, scope-document corrections)
**Owner:** Maheen Fatima (231659)
**Scope:** covers the two trained models behind `falsora_ai.engine_66` — the deepfake branch (6.6a) and the tampering branch (6.6b) — as fused by `ForgeryEngine` (6.6) and exported/quantized for the live path (Model Optimization). Does not cover module 6.8's risk banding, which is out of this engine's scope by design (see `README_AI.md`).

---

## 1. Deepfake branch (6.6a)

- **Architecture:** EfficientNet-B0 (`timm`), single logit output, sigmoid → `probability_fake`.
- **Input:** 224×224 RGB face crop (MTCNN-detected, single face per frame).
- **Training data:** FaceForensics++ (`DeepFakeDetection` C23) + DFD real originals, identity-disjoint train/val/test split. See "Training data" below for exact crop counts.
- **Checkpoint:** `checkpoints/efficientnet_b0_best.pt` (selected on best validation frame-level AUC, epoch 4: val AUC = 0.9793).

**Test-set results** (FF++/DFD, held-out identities, same distribution as training):

| Metric | Value |
|---|---|
| Video-level AUC | **0.987** |
| Video-level accuracy | 0.956 |

**Cross-dataset generalisation** (Celeb-DF v2, entirely unseen dataset — see "Verified dataset notes" in `README_AI.md` for why this split is identity-disjoint from training by construction):

| Metric | Value |
|---|---|
| Video-level AUC | **0.870** |
| Video-level accuracy | 0.799 |

The drop from 0.987 → 0.870 crossing datasets is expected and normal for deepfake detectors (domain shift between compression/generation methods); it is reported here specifically so a reader isn't misled by the in-distribution number alone.

Source of these numbers: `falsora_ai/engine_66/deepfake/evaluate.py`'s `video_level_auc`, run against the trained checkpoint (commit `781fa28`).

---

## 2. Tampering branch (6.6b)

- **Architecture:** custom CNN (`TamperingCNN`) over a stacked ELA + residual input, whole-image (no face detection needed).
- **Training data:** CASIA v2.0.
- **Checkpoint:** `checkpoints/tampering_cnn_best.pt`.

| Split | Image-level AUC | Accuracy |
|---|---|---|
| Validation | 0.882 | 0.804 |
| Test | 0.878 | 0.803 |

---

## 3. Live path — ONNX INT8 (Model Optimization)

Same deepfake branch, exported to ONNX and dynamically quantized (`MatMul` ops only — see `falsora_ai/optimization/quantize.py` for why `Conv` quantization is excluded on this platform).

| Variant | Mean latency / frame (CPU) |
|---|---|
| PyTorch fp32 | ~33.5 ms |
| ONNX fp32 | (see `falsora_ai/optimization/benchmark.py` output) |
| **ONNX INT8 (live path)** | **~6.5 ms** |

Scope document (section 5.1) claimed 8–12 ms, unverified at time of writing; the measured 6.5 ms comfortably clears the 1 fps live-capture requirement (Stage 1).

---

## 4. Training data — actual crop counts

Actual crops on disk (`falsora_ai/data report`, `face_crops/`), as opposed to pre-registration estimates:

| Split | Crops |
|---|---|
| train | 58,825 |
| val | 9,317 |
| test | 11,485 |
| heldout (Celeb-DF v2) | 16,490 |
| **Total** | **96,117** |

This is the real, current figure. Two other numbers appear elsewhere and are both superseded:
- `README_AI.md`'s "Frame budget: 80,400 + ~16,600" is the pre-registration **target** balance (`tests/test_config.py::TestFrameBudget` enforces this ratio, not the raw count).
- `ENGINEERING_PLAN.md` section 8.3's "~137,000" (and the submitted scope document's "~1 million frames") are both stale — an earlier, larger extraction plan (13,729 videos, all Celeb-DF) was deliberately trimmed to 7,718 videos (including only the 518 official Celeb-DF test-list videos) to keep the cross-dataset benchmark identity-disjoint. See `README_AI.md`'s "Known deviations" section, item 4.

Balance: 1:1.09 real:fake, held both globally and within each source domain (FF++/DFD).

---

## 5. Known limitations

- Deepfake branch generalisation (Celeb-DF AUC 0.870) is meaningfully lower than in-distribution (0.987) — expected, but means live-path confidence should be read as directional, not absolute, on generation methods not represented in FF++/DFD.
- INT8 quantization is head-only (linear layer), not full-network — see section 3. Latency gain is smaller than a fully quantized backbone would give, but the platform's `onnxruntime` CPU build cannot run `ConvInteger`.
- Tampering branch (CASIA v2.0) has not been evaluated cross-dataset; its 0.878/0.882 AUC is in-distribution only.
- No risk-banding (Low/Medium/High) is produced by this engine — see `README_AI.md`, "Risk banding is not mine."

---

## 6. Where each number comes from (reproducibility)

| Number | Command / file |
|---|---|
| Deepfake test/heldout AUC | `git show 781fa28` (recorded run); re-run via `falsora_ai/engine_66/deepfake/evaluate.py` against `checkpoints/efficientnet_b0_best.pt` |
| Tampering val/test AUC | `README_AI.md` M4 row; re-run via the tampering branch's own eval path |
| ONNX INT8 latency | `python -m falsora_ai.optimization benchmark` → `falsora_ai/optimization/benchmark.py::run_full_benchmark` |
| Crop counts | `python -m falsora_ai.data report` |
