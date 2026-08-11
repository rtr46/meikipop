from __future__ import annotations

import hashlib
import io
from collections import defaultdict

import pytest

from meikipop.dictionary import format as dictionary_format
from meikipop.dictionary.format import (
    DictionaryFormatError,
    copy_verified_download,
    load_dictionary,
    write_dictionary,
)


def sample_dictionary() -> dict:
    return {
        "entries": {1: [{"glosses": ["cat"], "pos": ["noun"], "misc": []}]},
        "lookup_map": defaultdict(list, {"猫": [("猫", "ねこ", 100, 1)]}),
        "kanji_entries": {"猫": {"meanings": ["cat"]}},
        "deconjugator_rules": [{"kanaIn": "た", "kanaOut": "る"}],
    }


def test_dictionary_round_trip(tmp_path):
    dictionary_path = tmp_path / "dictionary.json.gz"
    write_dictionary(dictionary_path, sample_dictionary())

    loaded = load_dictionary(dictionary_path)

    assert loaded["entries"][1][0]["glosses"] == ["cat"]
    assert loaded["lookup_map"]["猫"] == [("猫", "ねこ", 100, 1)]
    assert loaded["kanji_entries"]["猫"]["meanings"] == ["cat"]
    assert loaded["deconjugator_rules"][0]["kanaOut"] == "る"


def test_legacy_pickle_is_rejected_before_reading(tmp_path):
    dictionary_path = tmp_path / "dictionary.pkl"
    dictionary_path.write_bytes(b"not even a valid pickle")

    with pytest.raises(DictionaryFormatError, match="Legacy pickle"):
        load_dictionary(dictionary_path)


def test_dictionary_decompression_is_bounded(tmp_path, monkeypatch):
    dictionary_path = tmp_path / "dictionary.json.gz"
    write_dictionary(dictionary_path, sample_dictionary())
    monkeypatch.setattr(dictionary_format, "MAX_UNCOMPRESSED_BYTES", 16)

    with pytest.raises(DictionaryFormatError, match="Uncompressed dictionary"):
        load_dictionary(dictionary_path)


def test_verified_download_replaces_destination(tmp_path):
    payload = b"compressed dictionary bytes"
    destination = tmp_path / "dictionary.json.gz"
    destination.write_bytes(b"old")

    copy_verified_download(io.BytesIO(payload), destination, hashlib.sha256(payload).hexdigest())

    assert destination.read_bytes() == payload


def test_failed_verification_preserves_existing_destination(tmp_path):
    destination = tmp_path / "dictionary.json.gz"
    destination.write_bytes(b"known-good")

    with pytest.raises(DictionaryFormatError, match="verification failed"):
        copy_verified_download(io.BytesIO(b"untrusted"), destination, "0" * 64)

    assert destination.read_bytes() == b"known-good"
    assert not any(path.name.endswith(".download") for path in tmp_path.iterdir())
