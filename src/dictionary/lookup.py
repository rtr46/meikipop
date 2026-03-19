# lookup.py
import logging
import math
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from src.config.config import config, MAX_DICT_ENTRIES
from src.dictionary.customdict import Dictionary, WRITTEN_FORM_INDEX, READING_INDEX, FREQUENCY_INDEX, ENTRY_ID_INDEX, DEFAULT_FREQ
from src.dictionary.deconjugator import Deconjugator, Form

KANJI_REGEX = re.compile(r'[\u4e00-\u9faf]')
JAPANESE_SEPARATORS = {
    "、", "。", "「", "」", "｛", "｝", "（", "）", "【", "】",
    "『", "』", "〈", "〉", "《", "》", "：", "・", "／",
    "…", "︙", "‥", "︰", "＋", "＝", "－", "÷", "？", "！",
    "．", "～", "―", "!", "?",
}

logger = logging.getLogger(__name__)


@dataclass
class DictionaryEntry:
    id: int
    written_form: str
    reading: str  # empty when written_form is already kana
    senses: list
    freq: int
    deconjugation_process: tuple
    priority: float = 0.0


@dataclass
class KanjiEntry:
    character: str
    meanings: List[str]
    readings: List[str]
    components: List[Dict[str, str]]
    examples: List[Dict[str, str]]


class Lookup(threading.Thread):
    def __init__(self, shared_state, popup_window):
        super().__init__(daemon=True, name="Lookup")
        self.shared_state = shared_state
        self.popup_window = popup_window
        self.last_hit_result = None

        self.dictionary = Dictionary()
        self.lookup_cache: OrderedDict = OrderedDict()
        self.CACHE_SIZE = 500

        if not self.dictionary.load_dictionary('dictionary.pkl'):
            raise RuntimeError("Failed to load dictionary.")
        self.deconjugator = Deconjugator(self.dictionary.deconjugator_rules)

    def clear_cache(self):
        self.lookup_cache = OrderedDict()

    def run(self):
        logger.debug("Lookup thread started.")
        while self.shared_state.running:
            try:
                hit_result = self.shared_state.lookup_queue.get()
                if not self.shared_state.running: break
                logger.debug("Lookup: Triggered")

                # skip lookup if hit_result didnt change
                if hit_result == self.last_hit_result:
                    continue
                self.last_hit_result = hit_result

                lookup_result = self.lookup(self.last_hit_result) if self.last_hit_result else None
                self.popup_window.set_latest_data(lookup_result)
            except:
                logger.exception("An unexpected error occurred in the lookup loop. Continuing...")
        logger.debug("Lookup thread stopped.")

    def lookup(self, lookup_string: str) -> List:
        if not lookup_string:
            return []
        logger.info(f"Looking up: {lookup_string}")  # keep at info level so people know whats up

        text = lookup_string.strip()
        text = text[:config.max_lookup_length]
        for i, ch in enumerate(text):
            if ch in JAPANESE_SEPARATORS:
                text = text[:i]
                break
        if not text:
            return []

        if text in self.lookup_cache:
            self.lookup_cache.move_to_end(text)
            return self.lookup_cache[text]

        results = self._do_lookup(text)

        # Append kanji entry for the first character if applicable
        if config.show_kanji and KANJI_REGEX.match(text[0]):
            kd = self.dictionary.kanji_entries.get(text[0])
            if kd:
                results.append(KanjiEntry(
                    character=kd['character'],
                    meanings=kd['meanings'],
                    readings=kd['readings'],
                    components=kd.get('components', []),
                    examples=kd.get('examples', []),
                ))

        self.lookup_cache[text] = results
        if len(self.lookup_cache) > self.CACHE_SIZE:
            self.lookup_cache.popitem(last=False)
        return results

    def _do_lookup(self, text: str) -> List[DictionaryEntry]:
        """
        Scan all prefixes of `text` (longest first), deconjugate each, then
        look up every resulting form in the kanji / kana maps.

        Collected results are keyed by (written_form, reading) to merge duplicate
        map entries that resolve to the same display pair. The final list is
        sorted by (match_length DESC, priority DESC).
        """
        # entry_id -> (map_entry, form, match_len)
        collected: Dict[int, Tuple[tuple, Form, int]] = {}
        found_primary_match = False

        for prefix_len in range(len(text), 0, -1):
            prefix = text[:prefix_len]

            forms = self.deconjugator.deconjugate(prefix)
            forms.add(Form(text=prefix))

            prefix_hits = []

            for form in forms:
                map_entries = self._get_map_entries(form.text)
                if not map_entries:
                    continue

                for map_entry in map_entries:
                    written = map_entry[WRITTEN_FORM_INDEX]
                    entry_id = map_entry[ENTRY_ID_INDEX]

                    if written is None and KANJI_REGEX.search(form.text):
                        logger.warning(f"Skipping malformed dictionary entry: kanji key '{form.text}'")
                        continue

                    # POS validation: if the deconjugator tagged this form,
                    # the entry must contain that part-of-speech.
                    if form.tags:
                        required_pos = form.tags[-1]
                        entry_senses = self.dictionary.entries.get(entry_id, [])
                        all_pos = {p for s in entry_senses for p in s['pos']}
                        if required_pos not in all_pos:
                            logger.debug(
                                f"Pruning id={entry_id} ({written}): "
                                f"required POS '{required_pos}' not in {all_pos}"
                            )
                            continue

                    # Kana-only prefix filter: once a primary match with kanji
                    # exists, suppress kana-path entries that have a kanji form
                    if found_primary_match and not KANJI_REGEX.search(prefix):
                        if written and KANJI_REGEX.search(written):
                            continue

                    prefix_hits.append((map_entry, form))

            if prefix_hits:
                if not found_primary_match:
                    found_primary_match = True

                for map_entry, form in prefix_hits:
                    entry_id = map_entry[ENTRY_ID_INDEX]
                    if entry_id not in collected:
                        collected[entry_id] = (map_entry, form, prefix_len)

        return self._format_and_sort(list(collected.values()), text)

    def _get_map_entries(self, text: str) -> List[tuple]:
        """
        Look up `text` in lookup_map with hira↔kata fallback.
        Kanji and kana strings never share keys so a single map suffices.
        """
        result = self.dictionary.lookup_map.get(text, [])
        if result:
            return list(result)
        kata = self._hira_to_kata(text)
        if kata != text:
            result = self.dictionary.lookup_map.get(kata, [])
            if result:
                return list(result)
        hira = self._kata_to_hira(text)
        if hira != text:
            result = self.dictionary.lookup_map.get(hira, [])
            if result:
                return list(result)
        return []

    def _format_and_sort(
        self,
        raw: List[Tuple[tuple, Form, int]],
        original_lookup: str,
    ) -> List[DictionaryEntry]:
        """
        Merge map entries that share (written_form, reading) across different
        deconjugation paths, compute priority, then sort and return DictionaryEntry list.
        """
        # Key: (written_form, reading)  Value: accumulated data dict
        merged: Dict[Tuple[str, str], dict] = {}

        for map_entry, form, match_len in raw:
            written  = map_entry[WRITTEN_FORM_INDEX]
            reading  = map_entry[READING_INDEX] or ''
            freq     = map_entry[FREQUENCY_INDEX]
            entry_id = map_entry[ENTRY_ID_INDEX]

            entry_senses = self.dictionary.entries.get(entry_id, [])
            priority     = self._calculate_priority(written, freq, form, match_len, original_lookup)

            key = (written, reading)
            if key not in merged:
                merged[key] = {
                    'id':                    entry_id,
                    'written_form':          written,
                    'reading':               reading,
                    'senses':                list(entry_senses),
                    'freq':                  freq,
                    'deconjugation_process': form.process,
                    'priority':              priority,
                    'match_len':             match_len,
                }
            else:
                # Same (written_form, reading) reached via a different deconjugation path
                # or from a different entry ID (genuine homograph with identical display forms).
                # Merge senses from the other entry and keep the best freq/priority/match_len.
                cur = merged[key]
                if entry_id != cur['id']:
                    cur['senses'].extend(entry_senses)
                if priority > cur['priority']:
                    cur['priority']              = priority
                    cur['id']                    = entry_id
                    cur['deconjugation_process'] = form.process
                if freq < cur['freq']:
                    cur['freq'] = freq
                if match_len > cur['match_len']:
                    cur['match_len'] = match_len

        sorted_entries = sorted(
            merged.values(),
            key=lambda x: (x['match_len'], x['priority']),
            reverse=True,
        )

        results = []
        for d in sorted_entries[:MAX_DICT_ENTRIES]:
            results.append(DictionaryEntry(
                id=d['id'],
                written_form=d['written_form'],
                reading=d['reading'],
                senses=d['senses'],
                freq=d['freq'],
                deconjugation_process=d['deconjugation_process'],
                priority=d['priority'],
            ))
        return results

    def _calculate_priority(
        self,
        written_form: str,
        freq: int,
        form: Form,
        match_len: int,
        original_lookup: str,
    ) -> float:
        priority = float(match_len)

        # Frequency: log scale maps rank 1..999_999 evenly to ~0..10
        # rank 1 → ~10, rank 1000 → ~5, rank 50000 → ~2.8, rank 999_999 → 0
        if freq < DEFAULT_FREQ:
            priority += 10.0 * (1.0 - math.log(freq) / math.log(DEFAULT_FREQ))

        # Kana vs kanji preference
        original_is_kana = not KANJI_REGEX.search(original_lookup)
        written_is_kana = not KANJI_REGEX.search(written_form) if written_form else True

        if original_is_kana:
            # Kana-only entry looked up via kana: small bonus
            if written_is_kana and not form.process:
                priority += 3.0

        # Deconjugation cost
        priority -= len(form.process)

        return priority

    def _hira_to_kata(self, text: str) -> str:
        res = []
        for c in text:
            code = ord(c)
            res.append(chr(code + 0x60) if 0x3041 <= code <= 0x3096 else c)
        return ''.join(res)

    def _kata_to_hira(self, text: str) -> str:
        res = []
        for c in text:
            code = ord(c)
            if   0x30A1 <= code <= 0x30F6: res.append(chr(code - 0x60))
            elif code == 0x30FD:           res.append('\u309D')  # ヽ → ゝ
            elif code == 0x30FE:           res.append('\u309E')  # ヾ → ゞ
            else:                          res.append(c)
        return ''.join(res)
