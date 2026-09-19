"""
Explanation engine — module 6.7, fully assembled.
====================================================

Turns one :class:`~falsora_ai.contracts.ForgeryResult` (module 6.6's output)
into one :class:`~falsora_ai.contracts.Explanation`: re-crops the same face
region the deepfake branch scored, runs Grad-CAM over it, renders the overlay
and raw heatmap, persists both, and extracts salient-region boxes for report
annotation.

Depends only on 6.6's *model handle* (a ``DeepfakeNet``, loadable the same way
``ForgeryEngine`` loads it), never on its training code — see
``ENGINEERING_PLAN.md`` section 3.1. In particular this module does not import
``falsora_ai.engine_66.engine``; a caller that already has a live
``ForgeryEngine`` should pass its ``deepfake_model`` in here directly rather
than this module loading a second copy of the same checkpoint.

Explains the deepfake branch only. See ``gradcam.py``'s module docstring for
why the tampering branch (which already exposes ELA/residual maps directly)
is out of scope here.
"""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import torch

from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config, resolve_device
from falsora_ai.contracts import Explanation, ForgeryResult
from falsora_ai.data.transforms import deepfake_transforms
from falsora_ai.engine_66.deepfake.model import DeepfakeNet
from falsora_ai.engine_66.deepfake.train import load_checkpoint as load_deepfake_checkpoint
from falsora_ai.engine_67.gradcam import TARGET_LAYER_NAME, compute_cam
from falsora_ai.engine_67.overlay import render_heatmap, render_overlay, salient_regions, save_evidence

__all__ = ["ExplanationEngine"]

logger = get_logger(__name__)


class ExplanationEngine:
    """Module 6.7, fully assembled: loads (or reuses) the deepfake model once,
    explains ``ForgeryResult``s on demand.

    Args:
        cfg: Resolves the checkpoint path, backbone architecture and gradcam
            output directory. Defaults to a fresh :class:`Config`.
        device: Forwarded to the model. Defaults to :func:`resolve_device`.
        model: Pre-built ``DeepfakeNet``, e.g. the same instance
            ``ForgeryEngine.deepfake_model`` already holds, so the checkpoint
            is loaded once for both branches. Defaults to loading
            ``<architecture>_best.pt`` from ``cfg.paths.checkpoints``, or an
            untrained model if no checkpoint is on disk — same fallback
            ``ForgeryEngine`` uses, so a fresh clone never crashes here either.
    """

    def __init__(
        self,
        cfg: Config | None = None,
        device: str | None = None,
        model: torch.nn.Module | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.device = device or resolve_device()

        self.model = (model or self._load_model()).to(self.device)
        self.model.eval()

    def _load_model(self) -> torch.nn.Module:
        model = DeepfakeNet(self.cfg.model)
        checkpoint = self.cfg.paths.checkpoints / f"{self.cfg.model.architecture}_best.pt"
        if checkpoint.exists():
            load_deepfake_checkpoint(checkpoint, model, device=self.device)
        else:
            logger.warning("No deepfake checkpoint at %s — using untrained weights.", checkpoint)
        return model

    def explain(
        self, image: np.ndarray, result: ForgeryResult, method: str = "gradcam"
    ) -> Explanation | None:
        """Explain one ``ForgeryResult`` against the frame it was computed on.

        Returns ``None`` — not an error — when there is nothing to explain:
        no face was detected, or the deepfake branch didn't run. Both mirror
        ``ForgeryResult``'s own contract, which forbids a deepfake signal
        without a face in the first place.

        Args:
            image: The **same** whole RGB ``uint8`` frame
                ``ForgeryEngine.analyze_image`` was called with — this method
                re-crops using ``result.face.box`` rather than accepting a
                pre-cropped face, so the crop geometry can never drift from
                what module 6.6 actually scored.
            result: Module 6.6's output for ``image``.
            method: ``"gradcam"`` or ``"gradcam++"``.
        """
        if result.face is None or result.deepfake is None:
            return None

        box = result.face.box
        x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            logger.warning("Empty re-crop for result %s — skipping explanation.", result.result_id)
            return None

        transform = deepfake_transforms(self.cfg, split="test")
        tensor = transform(image=crop)["image"].unsqueeze(0).to(self.device)

        cam = compute_cam(self.model, tensor, method=method)

        size = self.cfg.model.resolved_input_size()
        interpolation_area, interpolation_cubic = _cv2_interpolations()
        interpolation = interpolation_area if crop.shape[0] > size else interpolation_cubic
        crop_resized = _cv2_resize(crop, size, interpolation)
        overlay_rgb = render_overlay(crop_resized.astype(np.float32) / 255.0, cam)
        heatmap_bgr = render_heatmap(cam)

        explanation_id = uuid4()
        overlay_path, heatmap_path = save_evidence(self.cfg, explanation_id, overlay_rgb, heatmap_bgr)

        return Explanation(
            explanation_id=explanation_id,
            result_id=result.result_id,
            method=method,
            target_layer=TARGET_LAYER_NAME,
            overlay_path=overlay_path,
            heatmap_path=heatmap_path,
            salient_regions=salient_regions(cam, box),
        )


def _cv2_interpolations() -> tuple[int, int]:
    """Local import wrapper, same rationale as ``common/faces.crop_face``:
    keeps OpenCV off any path that only needs this module's dataclasses."""
    import cv2

    return cv2.INTER_AREA, cv2.INTER_CUBIC


def _cv2_resize(image: np.ndarray, size: int, interpolation: int) -> np.ndarray:
    import cv2

    return cv2.resize(image, (size, size), interpolation=interpolation)
