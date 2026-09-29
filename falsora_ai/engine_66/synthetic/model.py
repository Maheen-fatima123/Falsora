"""
Synthetic-face classifier — dima806/deepfake_vs_real_image_detection (module 6.6c).
=====================================================================================

Wraps the public Hugging Face model
``dima806/deepfake_vs_real_image_detection`` as a **third, additive** signal
alongside the two branches in ``engine_66/engine.py``:

    * Branch A (``deepfake/model.py``)   — our own EfficientNet, trained on
      FaceForensics++/CelebDF face-SWAPS (identity replacement).
    * Branch B (``tampering/model.py``)  — our own CNN, trained on CASIA v2.0
      splicing/copy-move.
    * Branch C (this file)               — a ViT-base classifier
      (``dima806/deepfake_vs_real_image_detection``, fine-tuned on the public
      "140k Real and Fake Faces" dataset: 70k real FFHQ portraits vs 70k
      StyleGAN-synthesized faces) — covers the fully-synthetic-image case
      our own training data does not.

Why this exists: neither branch A nor branch B was trained to recognise a
face that was never a real photo at all (GAN/diffusion-generated). This gap
was identified and confirmed during dataset review (raw_datasets/ contains
only face-swap and splicing data). This module covers that gap with a
well-documented public model until branch A is retrained on a
fully-synthetic dataset — see the scope note below before relying on it.

SCOPE / ACCURACY NOTE (read before treating this as ground truth):
  Sanity-checked against our own labelled ``face_crops/test`` split
  (30 images, 15 real / 15 fake, all face-SWAP data — not this model's
  target domain): 11/15 real correct, 7/15 fake correct. This confirms the
  model is a StyleGAN-vs-real classifier, NOT a face-swap detector — it is
  expected to perform poorly on our face-swap fakes and should only be
  read as evidence of *fully-synthetic* generation, not forgery in general.
  It has not been validated against real GAN/diffusion-generated images from
  our own domain. Treat ``probability_synthetic`` as a supplementary,
  lower-confidence signal, not a verdict.

Optional dependency: ``transformers`` (pinned to 4.44.2 — newer releases
require torch>=2.5, and this project pins torch<2.6, see pyproject.toml).
Not part of the ``ml`` extra so a missing/incompatible install degrades this
one signal, not the whole engine — mirrors ``deepfake/model.py``'s local
``import timm``.
"""

from __future__ import annotations

import numpy as np

from falsora_ai.common.logging import get_logger

logger = get_logger(__name__)

MODEL_ID = "dima806/deepfake_vs_real_image_detection"
MODEL_VERSION = "huggingface:dima806/deepfake_vs_real_image_detection"

__all__ = ["SyntheticFaceDetector", "MODEL_ID"]


class SyntheticFaceDetector:
    """Loads the dima806/deepfake_vs_real_image_detection pipeline once,
    reused across calls.

    Construct once per process (same discipline as ``ForgeryEngine`` and
    ``StaticPredictor`` — reloading per request is the expensive mistake
    their docstrings already warn about).

    Raises:
        ImportError: ``transformers`` is not installed. Raised here, at
            construction, not at module import time, so importing this
            module never forces the dependency on code that doesn't
            construct the detector (mirrors ``DeepfakeNet``'s local
            ``import timm``).
        OSError: the model is not in the local Hugging Face cache and could
            not be downloaded (first run without internet).
    """

    def __init__(self, device: str = "cpu") -> None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise ImportError(
                "SyntheticFaceDetector requires `transformers`. Install with:\n"
                '  pip install "transformers==4.44.2"\n'
                "(pinned — transformers>=4.46 requires torch>=2.5, and this "
                "project pins torch<2.6; see pyproject.toml's [ml] extra.)"
            ) from exc

        device_index = -1 if device == "cpu" else 0
        self._pipe = pipeline("image-classification", model=MODEL_ID, device=device_index)

    def predict(self, image_rgb: np.ndarray) -> float:
        """``image_rgb``: HxWx3 ``uint8`` RGB image — the **whole frame**,
        not a tight face crop. Verified empirically (see ``engine.py``'s
        ``_run_synthetic``): this model was fine-tuned on loosely-framed
        FFHQ-style portraits and gives unreliable/flipped results on a
        tightly-cropped, margin-expanded face (our own ``crop_face()``
        convention) — feeding it the uncropped frame matches its training
        distribution far better.

        Returns:
            P(face is fully synthetic / GAN-generated), in ``[0, 1]``.
        """
        from PIL import Image

        image = Image.fromarray(image_rgb)
        results = self._pipe(image)
        fake_score = next(
            (r["score"] for r in results if r["label"].lower() == "fake"),
            0.0,
        )
        return float(fake_score)
