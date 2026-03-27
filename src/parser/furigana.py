# src/parser/furigana.py
#
# Public API for obtaining furigana (hiragana readings) for a block of text.
# Delegates to SudachiParser; returns None gracefully when parser unavailable.

import logging
from typing import List, Optional

from src.parser.sudachi import SudachiParser, Token, is_sudachi_available

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True when the parser package is installed and usable."""
    return is_sudachi_available()


def get_tokens(text: str) -> Optional[List[Token]]:
    """
    Parse *text* and return morpheme tokens with hiragana readings.

    Returns None if SudachiPy is not installed or parsing fails.
    Each Token has:
        .surface    – original text of the morpheme
        .reading    – hiragana reading  (empty string when .is_kana is True)
        .is_kana    – True when the surface needs no furigana annotation
        .char_start – start offset within *text*
        .char_end   – end offset (exclusive) within *text*
    """
    parser = SudachiParser.get_instance()
    if parser is None:
        return None
    try:
        return parser.tokenize(text)
    except Exception as exc:
        logger.warning("Furigana parsing failed for text %r: %s", text[:20], exc)
        return None
