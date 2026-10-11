import logging
import os
from collections import defaultdict
from html import escape

from meikipop.utils.paths import paths

logger = logging.getLogger(__name__)

PITCH_PATH = os.path.join(paths.data_dir, "accents.txt")


def to_hiragana(text: str) -> str:
    """Convert katakana to hiragana."""
    result = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            result.append(chr(code - 0x60))
        else:
            result.append(ch)
    return "".join(result)


def split_mora(reading: str) -> list[str]:
    """
    Split a Japanese reading into morae.

    Small kana such as ゃゅょ are attached to the preceding mora.
    っ, ん, and ー are independent morae.
    """
    reading = to_hiragana(reading)

    small_kana = set("ぁぃぅぇぉゃゅょゎゕゖ")

    morae = []
    for ch in reading:
        if ch in small_kana and morae:
            morae[-1] += ch
        else:
            morae.append(ch)

    return morae


def mark_high_morae(reading: str, accent: int) -> str:
    """
    Return HTML which places an overline over the high morae.

    Accent:
      0 = heiban: don't mark anything
      1 = atamadaka: first mora is high
      2+ = high from mora 2 through mora N
      N == mora count = odaka
    """
    morae = split_mora(reading)

    if accent == 0 or not morae:
        return escape(reading)

    if accent == 1:
        high_indices = {0}
    else:
        # For accent 2: mora 2 is high.
        # For accent 3: morae 2 and 3 are high.
        # For odaka: all morae after the first are high.
        high_indices = set(range(1, min(accent, len(morae))))

    result = []

    for i, mora in enumerate(morae):
        mora_html = escape(mora)

        if i in high_indices:
            mora_html = (
                '<span style="text-decoration: overline;">'
                f"{mora_html}"
                "</span>"
            )

        result.append(mora_html)

    return "".join(result)


class PitchAccentDictionary:
    def __init__(self):
        self.data: dict[tuple[str, str], tuple[int, ...]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(PITCH_PATH):
            logger.warning(
                "Pitch accent data not found at '%s'. "
                "Pitch accent display will be disabled.",
                PITCH_PATH,
            )
            return

        logger.info("Loading pitch accent data from '%s'", PITCH_PATH)

        data = defaultdict(list)

        try:
            with open(PITCH_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if not line or line.startswith("#"):
                        continue

                    parts = line.split("\t")
                    if len(parts) < 3:
                        continue

                    word, reading, accents = parts[:3]

                    try:
                        accent_values = [
                            int(x)
                            for x in accents.split(",")
                            if x.strip()
                        ]
                    except ValueError:
                        continue

                    key = (word, to_hiragana(reading))

                    for accent in accent_values:
                        if accent not in data[key]:
                            data[key].append(accent)

            self.data = {
                key: tuple(values)
                for key, values in data.items()
            }

            logger.info(
                "Loaded pitch accent data (%d word/reading pairs)",
                len(self.data),
            )

        except Exception:
            logger.exception("Failed to load pitch accent data.")

    def lookup(self, word: str, reading: str) -> tuple[int, ...]:
        if not word or not reading:
            return ()

        reading = to_hiragana(reading)

        # Normal lookup.
        result = self.data.get((word, reading))
        if result:
            return result

        # Kanjium also contains kana-only entries, so fall back
        # to the reading as the word.
        result = self.data.get((reading, reading))
        if result:
            return result

        return ()
