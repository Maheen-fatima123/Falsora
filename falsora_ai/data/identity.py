"""
Filename → identity parsing.
============================

This is the smallest module in the project and the one most capable of
invalidating every number we report.

Deepfake datasets are built by pairing people: a manipulated video is made from
a *target* face and a *source* face, and both people's names are in the
filename. If ``000_003.mp4`` goes to train and ``003_000.mp4`` goes to test,
the model has seen both faces during training and the test score measures face
recognition rather than forgery detection. In the published literature this
mistake is the difference between a reported 99% and a real 65%.

So every video is mapped here to the **set of human identities that appear in
it**, and :mod:`falsora_ai.data.splits` guarantees that all videos sharing an
identity land in the same split.

Identity keys are namespaced by *domain*, not by source directory. This matters:
``FF++/real/01__exit_phone_room.mp4`` and
``DeepFakeDetection/01_02__meeting_serious__XYZ.mp4`` are the same actor 01, and
they live in different directories. Namespacing by source would let actor 01's
real videos train the model and actor 01's fake videos test it.

Conventions verified against all 13,729 files on disk — zero non-conforming
filenames. The verification is re-run as a test, so a future dataset drop that
breaks a convention fails the build instead of silently corrupting the splits.
"""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = [
    "IdentityParseError",
    "identities_for",
    "PARSERS",
]


class IdentityParseError(ValueError):
    """A filename did not match the convention its source directory requires.

    Raised rather than swallowed. A file we cannot attribute to a person cannot
    be placed in a split safely, and dropping it silently would quietly shrink
    the dataset.
    """


# --------------------------------------------------------------------------
# Per-source parsers
# --------------------------------------------------------------------------
# Each returns the identities appearing in the video, already namespaced.
# A tuple rather than a set so the manifest is byte-for-byte reproducible.

_FFPP_ORIGINAL = re.compile(r"^(\d{3})\.mp4$")
_FFPP_MANIPULATED = re.compile(r"^(\d{3})_(\d{3})\.mp4$")
_DFD_FAKE = re.compile(r"^(\d{2})_(\d{2})__.+\.mp4$")
_DFD_REAL = re.compile(r"^(\d{2})__.+\.mp4$")
_CELEB_REAL = re.compile(r"^(id\d+)_\d{4}\.mp4$")
_CELEB_SYNTHESIS = re.compile(r"^(id\d+)_(id\d+)_\d{4}\.mp4$")
_YOUTUBE_REAL = re.compile(r"^(\d{5})\.mp4$")


def _ffpp_original(name: str) -> tuple[str, ...]:
    """``000.mp4`` → the person in pristine video 000."""
    m = _FFPP_ORIGINAL.match(name)
    if not m:
        raise IdentityParseError(f"FF++ original must be NNN.mp4, got {name!r}")
    return (f"ffpp:{m.group(1)}",)


def _ffpp_manipulated(name: str) -> tuple[str, ...]:
    """``000_003.mp4`` → target 000 wearing source 003's face. Both are present.

    Returning both is what forces the union: 000 and 003 become one identity
    group, and every video mentioning either follows them into the same split.
    """
    m = _FFPP_MANIPULATED.match(name)
    if not m:
        raise IdentityParseError(
            f"FF++ manipulation must be TARGET_SOURCE.mp4, got {name!r}"
        )
    return (f"ffpp:{m.group(1)}", f"ffpp:{m.group(2)}")


def _dfd_fake(name: str) -> tuple[str, ...]:
    """``01_02__meeting_serious__YVGY8LOK.mp4`` → actors 01 and 02."""
    m = _DFD_FAKE.match(name)
    if not m:
        raise IdentityParseError(
            f"DFD fake must be AA_BB__scene__HASH.mp4, got {name!r}"
        )
    return (f"dfd:{m.group(1)}", f"dfd:{m.group(2)}")


def _dfd_real(name: str) -> tuple[str, ...]:
    """``01__exit_phone_room.mp4`` → actor 01, alone."""
    m = _DFD_REAL.match(name)
    if not m:
        raise IdentityParseError(f"DFD real must be AA__scene.mp4, got {name!r}")
    return (f"dfd:{m.group(1)}",)


def _celeb_real(name: str) -> tuple[str, ...]:
    """``id0_0000.mp4`` → celebrity id0."""
    m = _CELEB_REAL.match(name)
    if not m:
        raise IdentityParseError(f"Celeb-real must be idN_NNNN.mp4, got {name!r}")
    return (f"celebdf:{m.group(1)}",)


def _celeb_synthesis(name: str) -> tuple[str, ...]:
    """``id0_id16_0000.mp4`` → celebrities id0 and id16."""
    m = _CELEB_SYNTHESIS.match(name)
    if not m:
        raise IdentityParseError(
            f"Celeb-synthesis must be idN_idM_NNNN.mp4, got {name!r}"
        )
    return (f"celebdf:{m.group(1)}", f"celebdf:{m.group(2)}")


def _youtube_real(name: str) -> tuple[str, ...]:
    """``00000.mp4`` → an unidentified member of the public.

    Celeb-DF gives these no identity annotation, so each video is treated as its
    own identity. That is the conservative reading: assuming two of them are the
    same person when they are not merely wastes a little split flexibility,
    whereas assuming they differ when they do not would leak. If two clips of
    the same stranger do exist, they can still straddle a split boundary — a
    residual risk that is acceptable here only because YouTube-real is inside
    the held-out domain and is never trained on.
    """
    m = _YOUTUBE_REAL.match(name)
    if not m:
        raise IdentityParseError(f"YouTube-real must be NNNNN.mp4, got {name!r}")
    return (f"celebdf:yt{m.group(1)}",)


PARSERS: dict[str, Callable[[str], tuple[str, ...]]] = {
    "FaceForensics++_C23/original": _ffpp_original,
    "FaceForensics++_C23/Deepfakes": _ffpp_manipulated,
    "FaceForensics++_C23/Face2Face": _ffpp_manipulated,
    "FaceForensics++_C23/FaceSwap": _ffpp_manipulated,
    "FaceForensics++_C23/FaceShifter": _ffpp_manipulated,
    "FaceForensics++_C23/NeuralTextures": _ffpp_manipulated,
    "FaceForensics++_C23/DeepFakeDetection": _dfd_fake,
    "FF++/real": _dfd_real,
    "Celeb DF/Celeb-real": _celeb_real,
    "Celeb DF/YouTube-real": _youtube_real,
    "Celeb DF/Celeb-synthesis": _celeb_synthesis,
}


def identities_for(source: str, filename: str) -> tuple[str, ...]:
    """Return the namespaced identities appearing in ``filename``.

    Args:
        source: Source directory relative to ``raw_datasets``, exactly as it
            appears in :data:`falsora_ai.config.DataConfig.SOURCE_LABELS`.
        filename: Basename of the video.

    Raises:
        IdentityParseError: If the source is unknown or the filename does not
            match that source's convention.
    """
    parser = PARSERS.get(source)
    if parser is None:
        raise IdentityParseError(
            f"No identity parser registered for source {source!r}. "
            "Add one to PARSERS before adding the source to SOURCE_LABELS."
        )
    return parser(filename)
