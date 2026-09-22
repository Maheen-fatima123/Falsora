"""Tests for CASIA v2.0 filename → source-image parsing.

Mirrors ``tests/test_identity.py``'s concerns for a different unit: a
``Tp`` image must yield **every** source it was built from (missing one is
the exact bug that produces source leakage), and a known dataset quirk —
inconsistent zero-padding on source ids — must not split one source image
into two different keys.
"""

from __future__ import annotations

import pytest

from falsora_ai.data.casia_identity import au_source, tp_sources
from falsora_ai.data.identity import IdentityParseError


class TestAuthenticImages:
    def test_au_source_is_namespaced(self) -> None:
        assert au_source("Au_ani_00018.jpg") == ("casia:ani18",)

    def test_bmp_extension_is_accepted(self) -> None:
        assert au_source("Au_sec_00096.bmp") == ("casia:sec96",)

    def test_wrong_convention_raises(self) -> None:
        with pytest.raises(IdentityParseError):
            au_source("Tp_D_CND_M_N_ani00018_sec00096_00138.tif")

    def test_malformed_name_raises(self) -> None:
        with pytest.raises(IdentityParseError):
            au_source("not_an_au_image.jpg")


class TestTamperedImages:
    def test_splice_returns_both_sources(self) -> None:
        got = tp_sources("Tp_D_CND_M_N_ani00018_sec00096_00138.tif")
        assert got == ("casia:ani18", "casia:sec96")

    def test_copy_move_within_one_image_returns_the_same_source_twice(self) -> None:
        got = tp_sources("Tp_S_NNN_S_O_ani00011_ani00011_00835.tif")
        assert got == ("casia:ani11", "casia:ani11")

    def test_jpg_extension_is_accepted(self) -> None:
        got = tp_sources("Tp_D_CNN_M_B_nat00056_nat00099_11105.jpg")
        assert got == ("casia:nat56", "casia:nat99")

    def test_wrong_convention_raises(self) -> None:
        with pytest.raises(IdentityParseError):
            tp_sources("Au_ani_00018.jpg")

    def test_malformed_name_raises(self) -> None:
        with pytest.raises(IdentityParseError):
            tp_sources("Tp_totally_wrong_shape.tif")


class TestZeroPaddingQuirk:
    """CASIA v2.0 ships at least one Tp file with an unpadded source id
    (``pla0006`` alongside ``pla00006``). Both must resolve to the same key,
    or the split code would treat one source image as two."""

    def test_padded_and_unpadded_ids_collide(self) -> None:
        assert au_source("Au_pla_00006.jpg") == ("casia:pla6",)
        got = tp_sources("Tp_S_NNN_M_N_pla0006_pla00006_01128.tif")
        assert got == ("casia:pla6", "casia:pla6")
        assert got[0] == au_source("Au_pla_00006.jpg")[0]

    def test_five_digit_ids_are_also_supported(self) -> None:
        got = tp_sources("Tp_S_CNN_S_O_ani10103_ani10111_10637.jpg")
        assert got == ("casia:ani10103", "casia:ani10111")


class TestNamespacing:
    def test_source_keys_never_contain_spaces(self) -> None:
        for key in tp_sources("Tp_D_CND_M_N_ani00018_sec00096_00138.tif"):
            assert " " not in key

    def test_all_keys_share_the_casia_namespace(self) -> None:
        keys = au_source("Au_ani_00018.jpg") + tp_sources(
            "Tp_D_CND_M_N_ani00018_sec00096_00138.tif"
        )
        assert all(k.startswith("casia:") for k in keys)
