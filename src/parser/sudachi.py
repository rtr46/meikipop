# src/parser/sudachi.py
#
# Wraps SudachiPy for Japanese morphological analysis.
# Provides tokenization with hiragana readings, used for both
# furigana display and word-level gamepad navigation.
#
# Required packages (optional install):
#   pip install sudachipy sudachidict-full
#
# sudachidict_full (~130 MB) is recommended over sudachidict_core
# because game text frequently contains proper nouns and made-up
# compound words that only the full dictionary covers well.

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------

def is_sudachi_available() -> bool:
    """Return True if sudachipy and sudachidict_full are both importable."""
    try:
        import sudachipy  # noqa: F401
        import sudachidict_full  # noqa: F401
        return True
    except ImportError:
        return False


def get_install_instructions() -> str:
    return "pip install sudachipy sudachidict-full"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Token:
    """A single morpheme produced by SudachiPy."""
    surface: str  # The original text of this token
    reading: str  # Hiragana reading (empty if surface is already kana)
    is_kana: bool  # True when no furigana annotation is needed
    char_start: int  # Start index within the paragraph's full_text
    char_end: int  # End index (exclusive) within the paragraph's full_text


# ---------------------------------------------------------------------------
# Katakana / kana utilities
# ---------------------------------------------------------------------------

def _katakana_to_hiragana(text: str) -> str:
    """Convert full-width katakana codepoints to hiragana."""
    result = []
    for ch in text:
        code = ord(ch)
        # Katakana block: U+30A1 (ァ) – U+30F6 (ヶ)  →  hiragana offset −0x60
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return ''.join(result)


def _is_all_kana(text: str) -> bool:
    """
    Return True when every character in *text* is hiragana, katakana,
    the katakana-hiragana prolonged sound mark, or common punctuation
    that needs no furigana annotation.
    """
    if not text:
        return False
    for ch in text:
        code = ord(ch)
        # Hiragana: 3040–309F  |  Katakana: 30A0–30FF  |  ー (30FC)  |  ｰ (FF70)
        if not (0x3040 <= code <= 0x30FF or code == 0xFF70):
            return False
    return True


# ---------------------------------------------------------------------------
# Parser singleton
# ---------------------------------------------------------------------------

class SudachiParser:
    """
    Thin singleton around a SudachiPy tokenizer.

    Using SplitMode.C (the coarsest split) produces tokens that most
    closely align with dictionary head-words, which gives the most natural
    furigana groupings and the best word-jump boundaries for navigation.
    """

    _instance: Optional['SudachiParser'] = None

    def __init__(self):
        import sudachipy
        import sudachipy.dictionary

        # 'full' selects sudachidict_full when installed
        self._dict = sudachipy.dictionary.Dictionary(dict="full")
        self._tokenizer = self._dict.create()
        self._split_mode = sudachipy.SplitMode.C
        logger.info("SudachiParser initialised with sudachidict_full (SplitMode.C).")

    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> Optional['SudachiParser']:
        """
        Return the shared SudachiParser, creating it on first call.
        Returns None if SudachiPy or its dictionary are not installed.
        """
        if cls._instance is None:
            if not is_sudachi_available():
                logger.debug("SudachiPy / sudachidict_full not available – parser disabled.")
                return None
            try:
                cls._instance = SudachiParser()
            except Exception as exc:
                logger.error("Failed to initialise SudachiParser: %s", exc)
                return None
        return cls._instance

    # ------------------------------------------------------------------

    def tokenize(self, text: str) -> List[Token]:
        """
        Tokenize *text* and return a list of Token objects.

        Each token carries the surface form, a hiragana reading, a flag
        indicating whether the surface is already kana, and the byte-
        exact start/end offsets within *text*.
        """
        morphemes = self._tokenizer.tokenize(text, self._split_mode)
        tokens: List[Token] = []
        char_pos = 0

        for m in morphemes:
            surface = m.surface()
            reading_kata = m.reading_form()  # katakana from the dictionary
            reading_hira = _katakana_to_hiragana(reading_kata)
            is_kana = _is_all_kana(surface)

            # When the surface is already hiragana/katakana the reading
            # is redundant – mark it so callers can skip the annotation.
            if is_kana:
                reading_hira = ''

            tokens.append(Token(
                surface=surface,
                reading=reading_hira,
                is_kana=is_kana,
                char_start=char_pos,
                char_end=char_pos + len(surface),
            ))
            char_pos += len(surface)

        return tokens
