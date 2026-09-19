"""
Fused forgery-detection engine (module 6.6).
==============================================

Combines branch A (deepfake, face crops, M3) and branch B (tampering, whole
image, M4) into one :class:`~falsora_ai.contracts.ForgeryResult` — the
payload the rest of the system (6.7 Grad-CAM, 6.8 Decision Intelligence,
6.9/6.10 Mehreen, 6.3 Ujala) actually consumes. Neither branch's own signal
class is that payload on its own: ``DeepfakeSignal``/``TamperingSignal`` are
per-branch evidence, ``ForgeryResult`` is what crosses the module boundary.

Both branches are independent and both run whenever their precondition is
met — this is not a router that picks one:
    * the deepfake branch requires a detected face (crop-based, using the
      same detector + margin as extraction, ``falsora_ai.common.faces``)
    * the tampering branch runs on the whole image unconditionally —
      splicing/copy-move artefacts are global, per the same reasoning
      ``engine_66/tampering/evaluate.py`` gives for why CASIA v2.0 has no
      per-region aggregation

A face-swap deepfake with no splicing, and a spliced photo with no face,
both need to be caught, so ``ForgeryResult`` can carry one signal, the
other, or both — never neither (enforced by the contract itself).

Models and the face detector are constructed once, in ``__init__``, and
reused across calls: reloading a checkpoint per image is the difference
between a request taking milliseconds and seconds. All three are
injectable so tests exercise the fusion logic with tiny untrained models
instead of the real checkpoints.

Torch is imported at module level, same rationale as
``engine_66/deepfake/model.py`` and ``engine_66/tampering/model.py``: this
module is only ever imported by code that already intends to run both
branches, so it never sits on Ujala's or Mehreen's torch-free import path
(``falsora_ai/contracts.py``, ``tests/test_dependencies.py``).
"""

from __future__ import annotations

import time

import numpy as np
import torch

from falsora_ai.common.faces import FaceDetector, MTCNNDetector, crop_face, expand_box
from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config, resolve_device
from falsora_ai.contracts import (
    AnalysisMode,
    BoundingBox,
    DeepfakeSignal,
    FaceDetection,
    ForgeryResult,
    TamperingSignal,
)
from falsora_ai.data.transforms import deepfake_transforms, resize_stacked_input
from falsora_ai.engine_66.deepfake.model import DeepfakeNet
from falsora_ai.engine_66.deepfake.train import load_checkpoint as load_deepfake_checkpoint
from falsora_ai.engine_66.tampering.ela import ela_score
from falsora_ai.engine_66.tampering.model import TamperingCNN, build_model_input
from falsora_ai.engine_66.tampering.residual import residual_score
from falsora_ai.engine_66.tampering.train import CHECKPOINT_STEM as TAMPERING_CHECKPOINT_STEM
from falsora_ai.engine_66.tampering.train import load_checkpoint as load_tampering_checkpoint

__all__ = ["ForgeryEngine"]

logger = get_logger(__name__)


class ForgeryEngine:
    """Module 6.6, fully assembled: loads both branches once, runs both on
    demand, returns the fused :class:`ForgeryResult`.

    Args:
        cfg: Resolves checkpoint paths, model architectures and face-crop
            geometry. Defaults to a fresh :class:`Config`.
        device: Forwarded to both models and the detector. Defaults to
            :func:`resolve_device`.
        deepfake_model: Pre-built model, e.g. for tests with
            ``pretrained=False`` to skip the ImageNet download. Defaults to
            loading ``<architecture>_best.pt`` from ``cfg.paths.checkpoints``
            if present, or a freshly initialised (untrained) model if not.
        tampering_model: Same idea, for ``tampering_cnn_best.pt``.
        face_detector: Anything satisfying :class:`FaceDetector`. Defaults to
            :class:`MTCNNDetector`.
    """

    def __init__(
        self,
        cfg: Config | None = None,
        device: str | None = None,
        deepfake_model: torch.nn.Module | None = None,
        tampering_model: torch.nn.Module | None = None,
        face_detector: FaceDetector | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.device = device or resolve_device()

        self.deepfake_model = (deepfake_model or self._load_deepfake_model()).to(self.device)
        self.tampering_model = (tampering_model or self._load_tampering_model()).to(self.device)
        self.deepfake_model.eval()
        self.tampering_model.eval()

        self.face_detector = face_detector or MTCNNDetector(self.cfg.face, device=self.device)

    def _load_deepfake_model(self) -> torch.nn.Module:
        model = DeepfakeNet(self.cfg.model)
        checkpoint = self.cfg.paths.checkpoints / f"{self.cfg.model.architecture}_best.pt"
        if checkpoint.exists():
            load_deepfake_checkpoint(checkpoint, model, device=self.device)
        else:
            logger.warning("No deepfake checkpoint at %s — using untrained weights.", checkpoint)
        return model

    def _load_tampering_model(self) -> torch.nn.Module:
        model = TamperingCNN(self.cfg.tampering)
        checkpoint = self.cfg.paths.checkpoints / f"{TAMPERING_CHECKPOINT_STEM}_best.pt"
        if checkpoint.exists():
            load_tampering_checkpoint(checkpoint, model, device=self.device)
        else:
            logger.warning("No tampering checkpoint at %s — using untrained weights.", checkpoint)
        return model

    @torch.no_grad()
    def _run_deepfake(
        self, image: np.ndarray
    ) -> tuple[DeepfakeSignal, FaceDetection] | tuple[None, None]:
        """Detect the largest face, crop with the training-time margin, score
        it. Returns ``(None, None)`` when no face passes the detector's
        confidence/size filters — the caller is responsible for leaving
        ``ForgeryResult.deepfake``/``.face`` unset in that case, since the
        contract forbids a deepfake signal without a face."""
        box = self.face_detector.detect_batch([image])[0]
        if box is None:
            return None, None

        crop = crop_face(image, box, self.cfg.face)
        transform = deepfake_transforms(self.cfg, split="test")
        tensor = transform(image=crop)["image"].unsqueeze(0).to(self.device)

        logit = self.deepfake_model(tensor)
        prob_fake = float(torch.sigmoid(logit).item())

        h, w = image.shape[:2]
        expanded = expand_box(box, self.cfg.face.margin, w, h)
        face = FaceDetection(
            box=BoundingBox(x1=expanded.x1, y1=expanded.y1, x2=expanded.x2, y2=expanded.y2),
            confidence=box.confidence,
            margin=self.cfg.face.margin,
            detector=self.cfg.face.detector,
        )
        signal = DeepfakeSignal(
            probability_fake=prob_fake,
            model_name=self.cfg.model.architecture,
            model_version="unversioned",
            input_size=self.cfg.model.resolved_input_size(),
            quantized=False,
        )
        return signal, face

    @torch.no_grad()
    def _run_tampering(self, image: np.ndarray) -> TamperingSignal:
        """Runs on the full, uncropped image — see module docstring for why
        this branch has no face precondition."""
        stacked = build_model_input(image, self.cfg.tampering)  # HxWx5, float32, [0, 1]
        resized = resize_stacked_input(stacked, self.cfg.tampering.input_size)
        # Matches TamperingDataset.__getitem__'s exact convention: numpy
        # transpose + copy (contiguous), not a torch permute view.
        tensor = torch.from_numpy(resized.transpose(2, 0, 1).copy()).unsqueeze(0).to(self.device)

        logit = self.tampering_model(tensor)
        prob_tampered = float(torch.sigmoid(logit).item())

        return TamperingSignal(
            probability_tampered=prob_tampered,
            ela_score=ela_score(image, self.cfg.tampering),
            residual_score=residual_score(image),
        )

    def analyze_image(self, image: np.ndarray, case_id: str | None = None) -> ForgeryResult:
        """Run both branches on one RGB ``uint8`` image, assemble the fused
        result.

        ``image`` is the **whole** uploaded/captured frame, not a
        pre-cropped face — face cropping for the deepfake branch happens
        internally, using the same detector and margin as M1's extraction
        pipeline.
        """
        t0 = time.perf_counter()

        deepfake_signal, face = self._run_deepfake(image)
        tampering_signal = self._run_tampering(image)

        latency_ms = (time.perf_counter() - t0) * 1000

        return ForgeryResult(
            case_id=case_id,
            mode=AnalysisMode.STATIC,
            face_detected=face is not None,
            face=face,
            deepfake=deepfake_signal,
            tampering=tampering_signal,
            latency_ms=latency_ms,
        )
