"""Tests for filename → identity parsing.

Two properties matter here and nothing else does:

  1. A manipulated video must yield **both** people in it. Missing the second
     identity is the exact bug that produces identity leakage, and it is
     invisible — the manifest looks fine, the splits look fine, and the test
     AUC is simply wrong.
  2. Identity keys must be namespaced by domain, so that DFD actor 01's real
     videos and fake videos are recognised as the same person despite living in
     different source directories.
"""

from __future__ import annotations

import pytest

from falsora_ai.config import DataConfig
from falsora_ai.data.identity import (
    PARSERS,
    IdentityParseError,
    identities_for,
)


class TestCoverage:
    def test_every_source_has_a_parser(self) -> None:
        """A source without a parser cannot be split and must not be added."""
        data = DataConfig()
        missing = set(data.SOURCE_LABELS) - set(PARSERS)
        assert not missing, f"Sources with no identity parser: {missing}"

    def test_no_parser_for_excluded_source(self) -> None:
        """FF++/fake is excluded as a duplicate; a parser would invite its use."""
        data = DataConfig()
        for source in data.EXCLUDED_SOURCES:
            assert source not in PARSERS


class TestManipulatedVideosYieldBothIdentities:
    """The property that prevents leakage."""

    @pytest.mark.parametrize(
        "source",
        [
            "FaceForensics++_C23/Deepfakes",
            "FaceForensics++_C23/Face2Face",
            "FaceForensics++_C23/FaceSwap",
            "FaceForensics++_C23/FaceShifter",
            "FaceForensics++_C23/NeuralTextures",
        ],
    )
    def test_ffpp_manipulation_returns_target_and_source(self, source: str) -> None:
        assert identities_for(source, "000_003.mp4") == ("ffpp:000", "ffpp:003")

    def test_dfd_fake_returns_both_actors(self) -> None:
        got = identities_for(
            "FaceForensics++_C23/DeepFakeDetection",
            "01_02__meeting_serious__YVGY8LOK.mp4",
        )
        assert got == ("dfd:01", "dfd:02")

    def test_celeb_synthesis_returns_both_celebrities(self) -> None:
        got = identities_for("Celeb DF/Celeb-synthesis", "id0_id16_0000.mp4")
        assert got == ("celebdf:id0", "celebdf:id16")

    def test_reversed_pair_yields_the_same_identity_set(self) -> None:
        """``000_003`` and ``003_000`` both exist in FF++ and involve the same
        two people. If these produced disjoint identity sets, union-find would
        never link them and both could be split apart."""
        a = identities_for("FaceForensics++_C23/Deepfakes", "000_003.mp4")
        b = identities_for("FaceForensics++_C23/Deepfakes", "003_000.mp4")
        assert set(a) == set(b)


class TestPristineVideos:
    def test_ffpp_original(self) -> None:
        assert identities_for("FaceForensics++_C23/original", "000.mp4") == ("ffpp:000",)

    def test_dfd_real(self) -> None:
        assert identities_for("FF++/real", "01__exit_phone_room.mp4") == ("dfd:01",)

    def test_celeb_real(self) -> None:
        assert identities_for("Celeb DF/Celeb-real", "id0_0000.mp4") == ("celebdf:id0",)

    def test_youtube_real_is_unique_per_video(self) -> None:
        a = identities_for("Celeb DF/YouTube-real", "00000.mp4")
        b = identities_for("Celeb DF/YouTube-real", "00001.mp4")
        assert a != b


class TestNamespacing:
    def test_dfd_real_and_fake_share_the_actor_namespace(self) -> None:
        """Actor 01 appears in FF++/real and in DeepFakeDetection. If those two
        directories produced different keys, actor 01 could train the model on
        their real videos and test it on their fakes."""
        real = identities_for("FF++/real", "01__exit_phone_room.mp4")
        fake = identities_for(
            "FaceForensics++_C23/DeepFakeDetection", "01_02__scene__ABC123.mp4"
        )
        assert real[0] in fake

    def test_ffpp_and_dfd_do_not_collide(self) -> None:
        """FF++ video ``010`` and DFD actor ``10`` are different people; only the
        namespace prefix keeps their keys apart."""
        ffpp = identities_for("FaceForensics++_C23/original", "010.mp4")
        dfd = identities_for("FF++/real", "10__scene.mp4")
        assert set(ffpp).isdisjoint(dfd)

    @pytest.mark.parametrize(
        ("source", "name", "prefix"),
        [
            ("FaceForensics++_C23/original", "000.mp4", "ffpp:"),
            ("FaceForensics++_C23/Deepfakes", "000_003.mp4", "ffpp:"),
            ("FaceForensics++_C23/DeepFakeDetection", "01_02__s__A.mp4", "dfd:"),
            ("FF++/real", "01__s.mp4", "dfd:"),
            ("Celeb DF/Celeb-real", "id0_0000.mp4", "celebdf:"),
            ("Celeb DF/Celeb-synthesis", "id0_id1_0000.mp4", "celebdf:"),
            ("Celeb DF/YouTube-real", "00000.mp4", "celebdf:"),
        ],
    )
    def test_every_key_is_namespaced(self, source: str, name: str, prefix: str) -> None:
        assert all(i.startswith(prefix) for i in identities_for(source, name))

    def test_identity_keys_never_contain_spaces(self) -> None:
        """The manifest serialises identities space-separated."""
        for source, name in [
            ("FaceForensics++_C23/Deepfakes", "000_003.mp4"),
            ("FaceForensics++_C23/DeepFakeDetection", "01_02__a b c__X.mp4"),
            ("FF++/real", "01__exit phone room.mp4"),
        ]:
            assert all(" " not in i for i in identities_for(source, name))


class TestMalformedInputIsRejected:
    """Unparseable filenames raise. Skipping them would shrink the dataset
    silently; guessing an identity would risk leakage."""

    @pytest.mark.parametrize(
        ("source", "name"),
        [
            ("FaceForensics++_C23/original", "000_003.mp4"),  # manipulation in real dir
            ("FaceForensics++_C23/original", "abc.mp4"),
            ("FaceForensics++_C23/Deepfakes", "000.mp4"),  # missing source id
            ("FaceForensics++_C23/DeepFakeDetection", "01__scene.mp4"),  # real pattern
            ("FF++/real", "01_02__scene__ABC.mp4"),  # fake pattern in real dir
            ("Celeb DF/Celeb-real", "id0_id1_0000.mp4"),  # synthesis in real dir
            ("Celeb DF/Celeb-synthesis", "id0_0000.mp4"),
            ("Celeb DF/YouTube-real", "id0_0000.mp4"),
        ],
    )
    def test_wrong_convention_raises(self, source: str, name: str) -> None:
        with pytest.raises(IdentityParseError):
            identities_for(source, name)

    def test_unknown_source_raises_with_actionable_message(self) -> None:
        with pytest.raises(IdentityParseError, match="No identity parser"):
            identities_for("Some/New/Dataset", "whatever.mp4")
