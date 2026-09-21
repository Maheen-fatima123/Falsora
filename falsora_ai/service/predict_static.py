"""
Static (REST) prediction adapter — module M9.
==================================================

**Single entry point for Ujala's REST upload path.** Wraps module 6.6
(``ForgeryEngine``) and module 6.7 (``ExplanationEngine``) behind one class so
her API layer never has to import ``falsora_ai.engine_66``/``engine_67``
directly, load a checkpoint itself, or guess at crop geometry.

Construct :class:`StaticPredictor` **once**, at process startup (e.g. FastAPI
``lifespan``/``on_startup``), and call :meth:`StaticPredictor.predict` per
request. Constructing it per-request reloads both model checkpoints on every
upload — the same mistake ``ForgeryEngine``'s own docstring warns about, just
one layer further out.

``ExplanationEngine`` is handed the *same* ``deepfake_model`` instance
``ForgeryEngine`` already loaded (see ``engine_67/explain.py``'s docstring),
so the checkpoint is read from disk once per process, not once per engine.

Every failure mode crosses this boundary as data, not an exception:
``predict()`` never raises for a bad/undecodable image or an inference
failure — it returns :class:`~falsora_ai.contracts.EngineError` in place of
the ``ForgeryResult``, per ``contracts.py``'s own stated design rule 2, so the
REST layer can serialise a 4xx/5xx with a real message instead of catching a
bare traceback. An explanation failure is treated as non-fatal (Grad-CAM is
supplementary evidence, not the primary verdict) and just comes back as
``None`` with a logged warning, never as an ``EngineError``.
"""

from __future__ import annotations

import numpy as np

from falsora_ai.common.logging import get_logger
from falsora_ai.config import Config, resolve_device
from falsora_ai.contracts import EngineError, Explanation, ForgeryResult
from falsora_ai.engine_66.engine import ForgeryEngine
from falsora_ai.engine_67.explain import ExplanationEngine

__all__ = ["StaticPredictor", "decode_image"]

logger = get_logger(__name__)


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Raw upload bytes (JPEG/PNG/...) -> RGB ``uint8`` ``np.ndarray``.

    Matches every other read path in this project
    (``falsora_ai.data.datasets._read_image``, ``engine_66/tampering/ela.py``):
    OpenCV decodes BGR, this function converts to RGB so every model
    downstream of it sees the same channel order it was trained on.

    Raises:
        ValueError: ``image_bytes`` does not decode to an image — corrupt
            upload or unsupported format. Caught by
            :meth:`StaticPredictor.predict` and turned into an
            :class:`~falsora_ai.contracts.EngineError`.
    """
    import cv2  # local: keeps this module importable without OpenCV

    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image bytes — corrupt upload or unsupported format.")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


class StaticPredictor:
    """Process-lifetime adapter over ``ForgeryEngine`` + ``ExplanationEngine``
    for Ujala's single-image REST upload path (module 6.2/6.3).

    Args:
        cfg: Resolves checkpoint paths and architectures for both engines.
            Defaults to a fresh :class:`~falsora_ai.config.Config`.
        device: Forwarded to both engines. Defaults to
            :func:`~falsora_ai.config.resolve_device`.
        forgery_engine: Pre-built engine — e.g. for tests, so a tiny
            untrained model and a stubbed face detector can be injected the
            same way ``ForgeryEngine`` itself allows. Defaults to
            constructing a real one from ``cfg``/``device``.
        explanation_engine: Same idea. Defaults to an ``ExplanationEngine``
            sharing ``forgery_engine.deepfake_model`` (see module docstring
            for why that sharing matters).
    """

    def __init__(
        self,
        cfg: Config | None = None,
        device: str | None = None,
        forgery_engine: ForgeryEngine | None = None,
        explanation_engine: ExplanationEngine | None = None,
    ) -> None:
        self.cfg = cfg or Config()
        self.device = device or resolve_device()

        self.forgery_engine = forgery_engine or ForgeryEngine(cfg=self.cfg, device=self.device)
        self.explanation_engine = explanation_engine or ExplanationEngine(
            cfg=self.cfg, device=self.device, model=self.forgery_engine.deepfake_model
        )

    def predict(
        self,
        image_bytes: bytes,
        case_id: str | None = None,
        explain: bool = True,
    ) -> tuple[ForgeryResult | EngineError, Explanation | None]:
        """Analyze one uploaded image.

        Args:
            image_bytes: Raw file bytes exactly as received on the upload
                endpoint — decoding happens here, not in the API layer.
            case_id: Verification case UUID from module 6.3, threaded through
                to ``ForgeryResult.case_id`` unchanged.
            explain: Set False to skip Grad-CAM (e.g. a fast preview call) and
                save the extra forward+backward pass.

        Returns:
            ``(result, explanation)``. ``result`` is a ``ForgeryResult`` on
            success or an ``EngineError`` on failure (bad image, inference
            crash) — check ``isinstance(result, EngineError)`` before reading
            ``.deepfake``/``.tampering``. ``explanation`` is ``None`` when
            ``explain=False``, no face was detected, or Grad-CAM itself
            failed; it is never populated alongside an ``EngineError`` result.
        """
        try:
            image = decode_image(image_bytes)
        except ValueError as exc:
            return EngineError(
                code="decode_failed", message=str(exc), module="6.6", recoverable=True
            ), None

        try:
            result = self.forgery_engine.analyze_image(image, case_id=case_id)
        except Exception as exc:  # noqa: BLE001 — this boundary must not raise, see module docstring
            logger.exception("Static inference failed for case_id=%s", case_id)
            return EngineError(
                code="inference_failed",
                message=str(exc),
                module="6.6",
                recoverable=False,
                context={"case_id": case_id} if case_id else {},
            ), None

        explanation: Explanation | None = None
        if explain:
            try:
                explanation = self.explanation_engine.explain(image, result)
            except Exception:  # noqa: BLE001 — explanation is supplementary, never fails the request
                logger.exception("Grad-CAM explanation failed for result_id=%s", result.result_id)

        return result, explanation
