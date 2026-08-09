"""
CASIA v2.0 filename → source-image parsing.
============================================

The tampering branch has the same leakage risk as the deepfake branch, keyed
on a different unit. There it is a human identity; here it is a **source
image**. CASIA v2.0's tampered images (``Tp/``) are built by splicing or
copy-moving content from one or two authentic images (``Au/``), and the
filename encodes exactly which ones:

    Tp_D_CND_M_N_ani00018_sec00096_00138.tif
                  ^^^^^^^^ ^^^^^^^^
                  source 1 source 2  → Au_ani_00018.jpg, Au_sec_00096.jpg

If ``Au_ani_00018.jpg`` lands in train while a ``Tp`` image spliced from it
lands in test, the model can learn that specific image's content instead of
what tampering looks like in general — train/test share pixels, not just a
"style". So every image here is mapped to the source id(s) it is built from,
and :mod:`falsora_ai.data.casia_splits` guarantees every image sharing a
source lands in the same split.

Conventions verified against all 12,614 files on disk (7,491 Au + 5,123 Tp):
zero non-conforming filenames, and every Tp source id resolves to an Au image
that actually exists. One quirk the regex below absorbs deliberately: source
ids are not always zero-padded to 5 digits (``pla0006`` alongside
``pla00006``), a known typo in the original CASIA v2.0 release. Keys are
normalised on the integer value, not the digit string, so both forms of the
same id collide correctly instead of silently forming two separate groups.
"""

from __future__ import annotations

import re

from falsora_ai.data.identity import IdentityParseError

__all__ = ["au_source", "tp_sources"]

_AU_RE = re.compile(r"^Au_([A-Za-z]{3})_(\d+)\.(jpg|bmp)$")

# Tp_<D|S>_<3-letter tamper type>_<size>_<post-proc>_<src1>_<src2>_<serial>.<ext>
# The type/size/post-proc fields are looser than they look on the surface —
# CASIA v2.0 ships at least one lowercase typo in that block ("CnN") — so only
# the two fields that matter for leakage (the source ids) are captured tightly.
_TP_RE = re.compile(
    r"^Tp_[A-Za-z]_[A-Za-z]{3}_[A-Za-z]_[A-Za-z]_"
    r"([A-Za-z]{3}\d{4,5})_([A-Za-z]{3}\d{4,5})_\d+\.(jpg|tif)$"
)
_SOURCE_TOKEN_RE = re.compile(r"^([A-Za-z]{3})(\d+)$")


def _normalise(category: str, number: str) -> str:
    """``("ani", "00018")`` and ``("ani", "18")`` must collide on the same key."""
    return f"casia:{category.lower()}{int(number)}"


def au_source(name: str) -> tuple[str, ...]:
    """``Au_ani_00018.jpg`` → the one source id this authentic image *is*."""
    m = _AU_RE.match(name)
    if not m:
        raise IdentityParseError(
            f"CASIA authentic image must be Au_CAT_NNNNN.{{jpg,bmp}}, got {name!r}"
        )
    category, number, _ext = m.groups()
    return (_normalise(category, number),)


def tp_sources(name: str) -> tuple[str, ...]:
    """``Tp_..._ani00018_sec00096_....tif`` → the one or two ids it was built from.

    Both are returned even when copy-move makes them identical
    (``..._cha00084_cha00084_...``) — a duplicate key is harmless to
    union-find (``union(a, a)`` is a no-op) and keeping the parser's shape
    uniform is simpler than special-casing the copy-move files.
    """
    m = _TP_RE.match(name)
    if not m:
        raise IdentityParseError(
            f"CASIA tampered image did not match the Tp_..._SRC1_SRC2_NNNNN "
            f"naming convention, got {name!r}"
        )
    src1, src2, _ext = m.groups()

    keys = []
    for token in (src1, src2):
        # Always matches: _TP_RE's own character classes already guarantee
        # this shape for src1/src2, so this just splits category from number.
        token_match = _SOURCE_TOKEN_RE.match(token)
        assert token_match is not None
        category, number = token_match.groups()
        keys.append(_normalise(category, number))
    return tuple(keys)
