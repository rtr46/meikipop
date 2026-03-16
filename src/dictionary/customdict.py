# customdict.py
import logging
import pickle
import time
from collections import defaultdict

from src.config.config import IS_WINDOWS

logger = logging.getLogger(__name__)

DEFAULT_FREQ = 999_999

# MapEntry tuple field indices. value: (written_form, reading, freq, entry_id)
WRITTEN_FORM_INDEX = 0
READING_INDEX = 1
FREQUENCY_INDEX = 2
ENTRY_ID_INDEX = 3

class Dictionary:
    def __init__(self):
        # Core entries: {entry_id: [sense, ...]}
        # Each sense: {'glosses': [...], 'pos': [...], 'misc': [...]}
        self.entries: dict[int, list] = {}

        # lookup_map: surface_form → [(written_form, reading_or_None, freq, entry_id), ...]
        self.lookup_map: dict[str, list] = defaultdict(list)

        # Kanji character entries from kanjidic2: {character: {...}}
        self.kanji_entries: dict[str, dict] = {}

        # Deconjugation rules consumed by Deconjugator at runtime
        self.deconjugator_rules: list[dict] = []

        self._is_loaded = False

    def load_dictionary(self, file_path: str) -> bool:
        if self._is_loaded:
            return True
        logger.info("Loading dictionary ...")
        start = time.perf_counter()
        try:
            with open(file_path, 'rb') as f:
                data = pickle.load(f)
            self.entries            = data['entries']
            self.lookup_map         = data['lookup_map']
            self.kanji_entries      = data.get('kanji_entries', {})
            self.deconjugator_rules = data.get('deconjugator_rules', [])
            self._is_loaded = True
            n_refs = sum(len(v) for v in self.lookup_map.values())
            logger.info(
                f"Dictionary loaded in {time.perf_counter() - start:.2f}s  "
                f"({len(self.entries)} core entries, {n_refs} lookup refs)"
            )
            self._validate()
            return True
        except FileNotFoundError:
            logger.error(
                f"Dictionary file '{file_path}' not found. "
                f"Run build_dictionary.{"bat" if IS_WINDOWS else "sh"} to create it."
            )
            return False
        except Exception as e:
            logger.error(f"Failed to load dictionary from '{file_path}': {e}")
            return False

    def _validate(self):
        """
        Scan the loaded dictionary for structural invariants and log warnings
        for any violations found. Never raises — validation is advisory only.

        Invariants checked:
          - Every map entry tuple has exactly 4 elements
          - written_form is a non-empty str or None (None is valid for kana-only)
          - reading is a str or None
          - freq is an int
          - entry_id exists in self.entries
          - A map entry reached via a kanji-containing key must not have
            written_form=None (that would render as an invisible entry)
        """
        issues = 0
        missing_entry_ids = set()

        for surface, me_list in self.lookup_map.items():
            surface_has_kanji = any(0x4E00 <= ord(c) <= 0x9FFF for c in surface)
            for me in me_list:
                if len(me) != 4:
                    logger.warning(
                        f"Malformed map entry under key '{surface}': "
                        f"expected 4 fields, got {len(me)} — {me!r}"
                    )
                    issues += 1
                    continue

                wf, rd, freq, entry_id = me

                if wf is not None and not isinstance(wf, str):
                    logger.warning(
                        f"Map entry under '{surface}': written_form is {type(wf).__name__} "
                        f"(expected str or None) — entry_id={entry_id}"
                    )
                    issues += 1

                if rd is not None and not isinstance(rd, str):
                    logger.warning(
                        f"Map entry under '{surface}': reading is {type(rd).__name__} "
                        f"(expected str or None) — entry_id={entry_id}"
                    )
                    issues += 1

                if not isinstance(freq, int):
                    logger.warning(
                        f"Map entry under '{surface}': freq is {type(freq).__name__} "
                        f"(expected int) — entry_id={entry_id}"
                    )
                    issues += 1

                if surface_has_kanji and wf is None:
                    logger.warning(
                        f"Map entry under kanji key '{surface}' has written_form=None "
                        f"(entry will display incorrectly) — entry_id={entry_id}"
                    )
                    issues += 1

                if entry_id not in self.entries:
                    missing_entry_ids.add(entry_id)
                    issues += 1

        if missing_entry_ids:
            logger.warning(
                f"{len(missing_entry_ids)} entry ID(s) referenced in lookup_map "
                f"have no matching core entry — first few: "
                f"{sorted(missing_entry_ids)[:5]}"
            )

        if issues == 0:
            logger.info("Dictionary validation passed with no issues.")
        else:
            logger.warning(f"Dictionary validation found {issues} issue(s) — "
                           f"some entries may display incorrectly.")
