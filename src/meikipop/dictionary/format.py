"""Safe, versioned serialization for meikipop dictionaries."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO

FORMAT_NAME = "meikipop-dictionary"
FORMAT_VERSION = 1
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024


class DictionaryFormatError(ValueError):
    """Raised when a dictionary is malformed or uses an unsupported format."""


def _normalise_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "entries": payload["entries"],
        "lookup_map": payload["lookup_map"],
        "kanji_entries": payload.get("kanji_entries", {}),
        "deconjugator_rules": payload.get("deconjugator_rules", []),
    }


def write_dictionary(file_path: str | os.PathLike[str], payload: dict[str, Any]) -> None:
    """Write a compressed dictionary atomically without executable serialization."""
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalised = _normalise_payload(payload)

    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as raw_file:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_file, mtime=0) as compressed:
                for chunk in json.JSONEncoder(
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).iterencode(normalised):
                    compressed.write(chunk.encode("utf-8"))
            raw_file.flush()
            os.fsync(raw_file.fileno())
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def load_dictionary(file_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load and minimally validate a safe dictionary file."""
    path = Path(file_path)
    if path.suffixes[-2:] != [".json", ".gz"]:
        raise DictionaryFormatError(
            "Legacy pickle dictionaries are not supported. Run `meikipop build-dict` "
            "or import a Yomitan dictionary again to create dictionary.json.gz."
        )
    if path.stat().st_size > MAX_COMPRESSED_BYTES:
        raise DictionaryFormatError("Compressed dictionary exceeds the 512 MiB safety limit")

    try:
        with gzip.open(path, "rb") as dictionary_file:
            encoded_payload = dictionary_file.read(MAX_UNCOMPRESSED_BYTES + 1)
        if len(encoded_payload) > MAX_UNCOMPRESSED_BYTES:
            raise DictionaryFormatError("Uncompressed dictionary exceeds the 1 GiB safety limit")
        payload = json.loads(encoded_payload)
    except (gzip.BadGzipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DictionaryFormatError(f"Invalid compressed dictionary: {error}") from error

    if not isinstance(payload, dict):
        raise DictionaryFormatError("Dictionary root must be an object")
    if payload.get("format") != FORMAT_NAME or payload.get("version") != FORMAT_VERSION:
        raise DictionaryFormatError("Unsupported dictionary format or version")

    entries = payload.get("entries")
    lookup_map = payload.get("lookup_map")
    if not isinstance(entries, dict) or not isinstance(lookup_map, dict):
        raise DictionaryFormatError("Dictionary entries and lookup_map must be objects")

    try:
        restored_entries = {int(entry_id): senses for entry_id, senses in entries.items()}
        restored_lookup = defaultdict(
            list,
            {
                surface: [tuple(map_entry) for map_entry in map_entries]
                for surface, map_entries in lookup_map.items()
            },
        )
    except (TypeError, ValueError) as error:
        raise DictionaryFormatError(f"Malformed dictionary index: {error}") from error

    return {
        "entries": restored_entries,
        "lookup_map": restored_lookup,
        "kanji_entries": payload.get("kanji_entries", {}),
        "deconjugator_rules": payload.get("deconjugator_rules", []),
    }


def copy_verified_download(
    source: BinaryIO,
    destination: str | os.PathLike[str],
    expected_sha256: str,
) -> None:
    """Copy a bounded download to its destination after SHA-256 verification."""
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise DictionaryFormatError("Dictionary SHA-256 is malformed")

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".download", dir=target.parent)
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_COMPRESSED_BYTES:
                    raise DictionaryFormatError("Dictionary download exceeds the 512 MiB safety limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

        if digest.hexdigest() != expected:
            raise DictionaryFormatError("Dictionary SHA-256 verification failed")
        os.replace(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
