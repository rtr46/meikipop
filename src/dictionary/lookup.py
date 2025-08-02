# src/dictionary/lookup.py
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Set, Dict, Tuple, List

from src.config.config import config, MAX_DICT_ENTRIES
from src.dictionary.deconjugator import Deconjugator, Form
from src.dictionary.dictionary import Dictionary

KANJI_REGEX = re.compile(r'[\u4e00-\u9faf]')

@dataclass
class DictionaryEntry:
    id: int; written_form: str; reading: str; definitions: list; deconjugation_process: tuple; priority: float = 0.0

logger = logging.getLogger(__name__)

class Lookup(threading.Thread):
    def __init__(self, shared_state, popup_window):
        super().__init__(daemon=True, name="Lookup")
        self.shared_state = shared_state
        self.popup_window = popup_window
        self.last_hit_result = None

        self.dictionary = Dictionary()
        if not self.dictionary.load_dictionary('jmdict_enhanced.pkl'):
             raise RuntimeError("Failed to load dictionary.")
        self.deconjugator = Deconjugator(self.dictionary.deconjugator_rules)
        self.lookup_cache = OrderedDict()

        self.CACHE_SIZE = 500

    def run(self):
        logger.debug("Lookup thread started.")
        while self.shared_state.running:
            try:
                hit_result = self.shared_state.lookup_queue.get()
                if not self.shared_state.running: break
                logger.debug("Lookup: Triggered")

                # skip lookup if hit_result didnt change # todo seems however lookup triggers popup to show if hidden
                if hit_result == self.last_hit_result and self.popup_window.isVisible():
                    continue
                self.last_hit_result = hit_result
                if not self.last_hit_result:
                    self.shared_state.lookup_result = None  # todo see below
                    continue

                lookup_result = self.lookup(self.last_hit_result)
                self.shared_state.lookup_result = lookup_result  # todo why is shared_state.lookup_result needed here?
                self.popup_window.set_latest_data(lookup_result)
            except:
                logger.exception("An unexpected error occurred in the lookup loop. Continuing...")
        logger.debug("Lookup thread stopped.")

    def lookup(self, hit_result):
        truncated_lookup = hit_result[3][:config.max_lookup_length]  # todo 3 == lookup_string
        if truncated_lookup in self.lookup_cache:
            self.lookup_cache.move_to_end(truncated_lookup)
            return self.lookup_cache[truncated_lookup]

        all_found_entries: Dict[int, Tuple[dict, Form, int]] = {}
        original_lookup_is_kana = self._is_kana_only(truncated_lookup)

        for i in range(len(truncated_lookup), 0, -1):
            prefix = truncated_lookup[:i]
            if not prefix: continue

            is_first_prefix = (i == len(truncated_lookup))
            deconjugated_forms = self.deconjugator.deconjugate(prefix)
            deconjugated_forms.add(Form(text=prefix))

            for form in deconjugated_forms:
                entry_indices = []
                if self._is_kana_only(form.text):
                    entry_indices = self.dictionary.lookup_kana.get(form.text, [])
                else:
                    entry_indices = self.dictionary.lookup_kan.get(form.text, [])

                if not is_first_prefix and original_lookup_is_kana:
                    filtered_indices = []
                    for index in entry_indices:
                        entry = self.dictionary.entries[index]
                        misc_tags = self._get_misc_tags(entry)
                        if not entry['kebs'] or 'uk' in misc_tags:
                            filtered_indices.append(index)
                    entry_indices = filtered_indices

                for index in set(entry_indices):
                    entry = self.dictionary.entries[index]
                    if form.tags and entry['senses']:
                        last_tag = form.tags[-1]
                        if not any(last_tag in s['pos'] for s in entry['senses']):
                            continue
                    if entry['id'] not in all_found_entries:
                        all_found_entries[entry['id']] = (entry, form, len(prefix))

        results = self._format_and_sort_results(list(all_found_entries.values()), truncated_lookup)

        self.lookup_cache[truncated_lookup] = results[:MAX_DICT_ENTRIES]
        if len(self.lookup_cache) > self.CACHE_SIZE:
            self.lookup_cache.popitem(last=False)
        if results:
            logger.info("Found %d entries for '%s...'", len(results), truncated_lookup[:15])
        return results[:MAX_DICT_ENTRIES]

    def _is_kana_only(self, text: str) -> bool:
        return not KANJI_REGEX.search(text)

    def _get_misc_tags(self, entry: dict) -> Set[str]:
        tags = set()
        for sense in entry.get('raw_sense', []):
            for misc in sense.get('misc', []):
                tags.add(misc.strip('&;'))
        return tags

    def _prefers_kana(self, misc_tags: Set[str]) -> bool:
        return 'uk' in misc_tags or 'ek' in misc_tags

    def _prefers_kanji(self, misc_tags: Set[str]) -> bool:
        return 'uK' in misc_tags or 'eK' in misc_tags

    def _is_irregular(self, entry: dict, reading: str, spelling: str) -> bool:
        for r_ele in entry.get('raw_r_ele', []):
            if r_ele['reb'] == reading:
                for info in r_ele.get('inf', []):
                    if info.strip('&;') in {'ik', 'ok', 'io'}: return True
        for k_ele in entry.get('raw_k_ele', []):
            if k_ele['keb'] == spelling:
                for info in k_ele.get('inf', []):
                    if info.strip('&;') in {'iK', 'oK'}: return True
        return False

    def _has_priority(self, entry: dict) -> bool:
        if any(k.get('pri') for k in entry.get('raw_k_ele', [])): return True
        if any(r.get('pri') for r in entry.get('raw_r_ele', [])): return True
        return False

    def _all_senses_have_tag(self, entry: dict, tags_to_check: Set[str]) -> bool:
        senses = entry.get('raw_sense', [])
        if not senses: return False
        for sense in senses:
            sense_misc = {m.strip('&;') for m in sense.get('misc', [])}
            if not sense_misc.intersection(tags_to_check):
                return False
        return True

    def _format_and_sort_results(self, entries_with_forms: list, original_lookup: str) -> List[DictionaryEntry]:
        merged_entries: Dict[Tuple[str, str], Dict] = {}
        for entry_data, form, match_len in entries_with_forms:
            matched_reading = ""
            primary_keb = ""
            if self._is_kana_only(form.text):
                matched_reading = form.text
                for k in entry_data['raw_k_ele']:
                    restrs = k.get('restr', [])
                    if not restrs or matched_reading in restrs:
                        primary_keb = k['keb']
                        break
                if not primary_keb and entry_data['kebs']:
                    primary_keb = entry_data['kebs'][0]
            else:
                primary_keb = form.text
                for r in entry_data['raw_r_ele']:
                    restrs = r.get('restr', [])
                    if not restrs or primary_keb in restrs:
                        matched_reading = r['reb']
                        break
                if not matched_reading and entry_data['rebs']:
                    matched_reading = entry_data['rebs'][0]

            written_form = primary_keb if primary_keb else matched_reading
            reading_to_display = matched_reading if primary_keb else ""

            priority = self._calculate_priority(entry_data, form, match_len, original_lookup, written_form,
                                                matched_reading)

            merge_key = (written_form, reading_to_display)
            if merge_key not in merged_entries:
                merged_entries[merge_key] = {
                    "id": entry_data['id'],
                    "written_form": written_form,
                    "reading": reading_to_display,
                    "definitions": [s['glosses'] for s in entry_data['senses']],
                    "deconjugation_process": form.process,
                    "priority": priority
                }
            else:
                if priority > merged_entries[merge_key]['priority']:
                    merged_entries[merge_key]['definitions'].extend([s['glosses'] for s in entry_data['senses']])
                    merged_entries[merge_key]['priority'] = priority
                    merged_entries[merge_key]['id'] = entry_data['id']
                    merged_entries[merge_key]['deconjugation_process'] = form.process

        final_results = [DictionaryEntry(**val) for val in merged_entries.values()]
        final_results.sort(key=lambda x: x.priority, reverse=True)
        return final_results

    def _calculate_priority(self, entry_data, form, match_len, original_lookup, written_form, reading) -> float:
        is_original_lookup_kana = self._is_kana_only(original_lookup)
        priority = float(entry_data['id']) / -10000000.0
        priority += match_len * 1000

        misc_tags = self._get_misc_tags(entry_data)
        if is_original_lookup_kana:
            if self._prefers_kana(misc_tags): priority += 10
            if self._prefers_kanji(misc_tags): priority -= 12
        else:
            if self._prefers_kana(misc_tags): priority -= 10
            if self._prefers_kanji(misc_tags): priority += 12

        if self._is_irregular(entry_data, reading, written_form):
            priority -= 50
        if self._has_priority(entry_data):
            priority += 30
        if self._all_senses_have_tag(entry_data, {'obs', 'rare', 'obsc'}):
            priority -= 5
        if len(entry_data['senses']) >= 3:
            priority += 3

        bonus = 0
        bonus_reading = self.dictionary.priority_map.get(("", reading), 0)
        bonus_written = self.dictionary.priority_map.get((written_form, reading), 0) if written_form else 0
        bonus = max(bonus_reading, bonus_written)
        if bonus > 1000:
            relevance_ratio = len(form.text) / len(original_lookup)
            bonus *= relevance_ratio

        priority += bonus
        priority -= len(form.process) * 5
        return priority
