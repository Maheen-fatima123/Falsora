"""
Heatmap rendering, salient-region extraction and evidence persistence
(module 6.7).
=================================================================================

Three separate artefacts come out of one CAM array:

* an **overlay** (heatmap blended over the face crop) — what the UI shows,
  ``Explanation.overlay_path``;
* a **raw heatmap** (colourised, but not blended) — kept for the forensic
  report so a reviewer can read activation intensity without the source image
  competing with it underneath, ``Explanation.heatmap_path``;
* a handful of **salient region boxes** — the CAM's highest-activation
  connected components, mapped back into absolute pixel coordinates of the
  *source* image (not the face crop), for report annotation,
  ``Explanation.salient_regions``.

Both PNGs are written to ``cfg.paths.gradcam`` rather than inlined into the
contract, for the same reason ``Explanation``'s own docstring gives: large
PNGs do not belong on the WebSocket or in the database.
"""

from __future__ import annotations

import numpy as np

from falsora_ai.config import Config
from falsora_ai.contracts import BoundingBox

__all__ = ["render_overlay", "render_heatmap", "salient_regions", "save_evidence"]


def render_overlay(crop_rgb_float01: np.ndarray, cam: np.ndarray) -> np.ndarray:
    """Heatmap composited over the face crop. RGB ``uint8``, same size as ``cam``.

    Args:
        crop_rgb_float01: The face crop the CAM was computed on, RGB, resized
            to ``cam``'s resolution, values in ``[0, 1]`` — exactly what
            ``pytorch_grad_cam.utils.image.show_cam_on_image`` expects.
        cam: Output of :func:`falsora_ai.engine_67.gradcam.compute_cam`.
    """
    from pytorch_grad_cam.utils.image import show_cam_on_image  # local: keeps this importable without torch

    return show_cam_on_image(crop_rgb_float01, cam, use_rgb=True)


def render_heatmap(cam: np.ndarray) -> np.ndarray:
    """Raw activation map, colourised but **not** blended with the source
    image. BGR ``uint8`` (OpenCV's native channel order, since this is only
    ever passed straight to ``cv2.imwrite``).
    """
    import cv2  # local: keeps this module importable without OpenCV

    return cv2.applyColorMap((np.clip(cam, 0.0, 1.0) * 255).astype(np.uint8), cv2.COLORMAP_JET)


def salient_regions(
    cam: np.ndarray,
    box: BoundingBox,
    threshold: float = 0.6,
    max_regions: int = 3,
    min_area_fraction: float = 0.01,
) -> list[BoundingBox]:
    """Bounding boxes of the CAM's highest-activation regions, in absolute
    pixel coordinates of the *source* image.

    ``cam`` lives in the face crop's coordinate system (``box``'s square, at
    whatever resolution the model was fed). Every returned box is rescaled by
    ``box``'s pixel size and offset by ``box.x1``/``box.y1``, so a consumer
    never needs to know the crop or CAM resolution to draw them on the
    original frame — matching ``BoundingBox``'s own contract ("absolute pixel
    coordinates of the source image").

    Args:
        cam: ``HxW`` float32, ``[0, 1]``, from :func:`compute_cam`.
        box: The (already margin-expanded) face box the crop was taken from —
            ``ForgeryResult.face.box``.
        threshold: Fraction of peak activation a pixel must reach to count.
        max_regions: At most this many boxes, largest connected component
            first — a report wants the handful of regions that mattered, not
            every speck above threshold.
        min_area_fraction: Connected components smaller than this fraction of
            the CAM's area are noise, not evidence, and are dropped.

    Returns:
        Up to ``max_regions`` boxes, largest first. Empty if nothing clears
        ``threshold``.
    """
    import cv2  # local: keeps this module importable without OpenCV

    mask = (cam >= threshold).astype(np.uint8)
    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    min_area = min_area_fraction * cam.shape[0] * cam.shape[1]
    scale_x = (box.x2 - box.x1) / cam.shape[1]
    scale_y = (box.y2 - box.y1) / cam.shape[0]

    # label 0 is the background component — always skip it.
    candidates = [
        (int(stats[label, cv2.CC_STAT_AREA]), label)
        for label in range(1, num_labels)
        if stats[label, cv2.CC_STAT_AREA] >= min_area
    ]
    candidates.sort(reverse=True)

    regions: list[BoundingBox] = []
    for _area, label in candidates[:max_regions]:
        x, y, w, h = (
            stats[label, cv2.CC_STAT_LEFT],
            stats[label, cv2.CC_STAT_TOP],
            stats[label, cv2.CC_STAT_WIDTH],
            stats[label, cv2.CC_STAT_HEIGHT],
        )
        regions.append(
            BoundingBox(
                x1=box.x1 + x * scale_x,
                y1=box.y1 + y * scale_y,
                x2=box.x1 + (x + w) * scale_x,
                y2=box.y1 + (y + h) * scale_y,
            )
        )
    return regions


def save_evidence(
    cfg: Config,
    explanation_id: object,
    overlay_rgb: np.ndarray,
    heatmap_bgr: np.ndarray,
) -> tuple[str, str]:
    """Write both PNGs under ``cfg.paths.gradcam``, named by ``explanation_id``.

    Returns ``(overlay_path, heatmap_path)`` as strings, ready for
    ``Explanation.overlay_path``/``.heatmap_path``.
    """
    import cv2  # local: keeps this module importable without OpenCV

    out_dir = cfg.paths.gradcam
    out_dir.mkdir(parents=True, exist_ok=True)

    overlay_path = out_dir / f"{explanation_id}_overlay.png"
    heatmap_path = out_dir / f"{explanation_id}_heatmap.png"

    cv2.imwrite(str(overlay_path), cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(heatmap_path), heatmap_bgr)

    return str(overlay_path), str(heatmap_path)
