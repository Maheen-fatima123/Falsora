"""
Grad-CAM over the deepfake branch's backbone (module 6.7).
=============================================================

Explains *why* :class:`~falsora_ai.engine_66.deepfake.model.DeepfakeNet` called
a face crop fake, not just that it did. ``ForgeryResult.deepfake.probability_fake``
is a number; a reviewer deciding whether to trust it needs to see whether that
number came from the mouth/jaw blending boundary a face swap typically leaves,
or from something irrelevant like a shadow — the latter is a hint the model is
not to be trusted on that image, and it never shows up in the probability alone.

Only the deepfake branch is explained here. The tampering branch already
produces two spatial evidence maps of its own (ELA, noise residual — see
``engine_66/tampering/ela.py`` / ``residual.py``), so a CAM would duplicate
evidence that branch already exposes directly.

Wraps ``pytorch-grad-cam`` (the ``grad-cam`` dependency in ``pyproject.toml``'s
``[ml]`` extra) rather than reimplementing the hook/backward bookkeeping —
Grad-CAM and Grad-CAM++ are the only two methods this project claims support
for (``Explanation.method``'s documented values), so this module does not
expose the library's other CAM variants.

Torch is imported at module level, same rationale as the rest of
``engine_66``/``engine_67``: nothing on Ujala's or Mehreen's torch-free import
path ever imports this module.
"""

from __future__ import annotations

import numpy as np
import torch
from pytorch_grad_cam import GradCAM, GradCAMPlusPlus
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

from falsora_ai.engine_66.deepfake.model import DeepfakeNet

__all__ = ["TARGET_LAYER_NAME", "compute_cam"]

# The last convolutional layer before EfficientNet's global pool and this
# project's custom classification head (see DeepfakeNet) — the deepest point
# in the network where activations still carry spatial layout (7x7 at a 224
# input), so the CAM localises *where* in the crop drove the decision instead
# of collapsing to a single pooled vector. Recorded as a string on
# ``Explanation.target_layer`` so a report can say which layer the evidence
# came from.
TARGET_LAYER_NAME = "backbone.conv_head"

_CAM_CLASSES = {"gradcam": GradCAM, "gradcam++": GradCAMPlusPlus}


def compute_cam(model: DeepfakeNet, tensor: torch.Tensor, method: str = "gradcam") -> np.ndarray:
    """Run Grad-CAM (or Grad-CAM++) for the fake logit on one input batch.

    Args:
        model: A ``DeepfakeNet`` in eval mode. Grad-CAM performs a backward
            pass internally, so this must **not** be called inside
            ``torch.no_grad()`` — unlike every other inference path in
            ``engine_66``.
        tensor: ``1xCxHxW``, already resized/normalised — the exact tensor
            that was (or would be) fed to the model for scoring.
        method: ``"gradcam"`` or ``"gradcam++"``, matching
            ``Explanation.method``.

    Returns:
        ``HxW`` float32 array in ``[0, 1]``, resized to ``tensor``'s spatial
        size. Higher values mean more contribution to the fake logit.

    Raises:
        ValueError: ``method`` is not one of the two supported values.
    """
    if method not in _CAM_CLASSES:
        raise ValueError(
            f"unknown Grad-CAM method {method!r}, expected one of {sorted(_CAM_CLASSES)}"
        )

    cam_cls = _CAM_CLASSES[method]
    target_layers = [model.backbone.conv_head]

    # category=0: DeepfakeNet's single logit (P(fake) pre-sigmoid, see its
    # forward()) — "what pushed this crop toward fake" is the only question
    # an evidence heatmap needs to answer; there is no second class to
    # contrast against.
    with cam_cls(model=model, target_layers=target_layers) as cam:
        grayscale_cam = cam(input_tensor=tensor, targets=[ClassifierOutputTarget(0)])

    return grayscale_cam[0]
