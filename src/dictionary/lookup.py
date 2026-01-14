# src/dictionary/lookup.py
import logging
import os
import re
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Set, Dict, Tuple, List

import requests

from src.config.config import config, MAX_DICT_ENTRIES
from src.dictionary.customdict import Dictionary
from src.dictionary.deconjugator import Deconjugator, Form

KANJI_REGEX = re.compile(r'[\u4e00-\u9faf]')
JAPANESE_SEPARATORS = {"、", "。", "「", "」", "｛", "｝", "（", "）", "【", "】", "『", "』", "〈", "〉", "《", "》", "：", "・", "／",
                       "…", "︙", "‥", "︰", "＋", "＝", "－", "÷", "？", "！", "．", "～", "―", "!", "?"}


@dataclass
class DictionaryEntry:
    id: int
    written_form: str
    reading: str
    senses: list
    tags: Set[str]
    deconjugation_process: tuple
    priority: float = 0.0


logger = logging.getLogger(__name__)

def _resolve_dictionary_path() -> str:
    candidates = [
        os.path.abspath("jmdict_enhanced.pkl"),
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "jmdict_enhanced.pkl"))

    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


class Lookup(threading.Thread):
    def __init__(self, shared_state, popup_window):
        super().__init__(daemon=True, name="Lookup")
        self.shared_state = shared_state
        self.popup_window = popup_window
        self.last_hit_result = None

        self.dictionary = Dictionary()
        self.lookup_cache = OrderedDict()

        self.dictionary_loaded = self.dictionary.load_dictionary(_resolve_dictionary_path())
        self.deconjugator = Deconjugator(self.dictionary.deconjugator_rules if self.dictionary_loaded else [])

        self.CACHE_SIZE = 500
        self._id_translation_cache = OrderedDict()
        self._ID_TRANSLATION_CACHE_SIZE = 5000

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

    def _translate_text_to_indonesian(self, text: str):
        cleaned = text.strip()
        if not cleaned:
            return None

        cached = self._id_translation_cache.get(cleaned)
        if cached is not None:
            self._id_translation_cache.move_to_end(cleaned)
            return cached

        try:
            resp = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "en",
                    "tl": "id",
                    "dt": "t",
                    "q": cleaned,
                },
                timeout=1.5,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data or not data[0]:
                return None
            translated = "".join(seg[0] for seg in data[0] if seg and seg[0]).strip()
            if not translated:
                return None
            self._id_translation_cache[cleaned] = translated
            if len(self._id_translation_cache) > self._ID_TRANSLATION_CACHE_SIZE:
                self._id_translation_cache.popitem(last=False)
            return translated
        except Exception:
            return None

    def lookup(self, lookup_string):
        if not self.dictionary_loaded:
            return []
        if not lookup_string:
            return []
        logger.info(f"Looking up: {lookup_string}")  # keep at info level so people know whats up

        cleaned_lookup_string = lookup_string.strip()
        for i, char in enumerate(cleaned_lookup_string):
            if char in JAPANESE_SEPARATORS:
                cleaned_lookup_string = cleaned_lookup_string[:i]
                break

        truncated_lookup = cleaned_lookup_string[:config.max_lookup_length]

        if truncated_lookup in self.lookup_cache:
            self.lookup_cache.move_to_end(truncated_lookup)
            return self.lookup_cache[truncated_lookup]

        all_found_entries: Dict[int, Tuple[dict, Form, int]] = {}
        found_primary_match = False

        logger.trace(f"--- STARTING LOOKUP FOR: '{truncated_lookup}' ---")

        for i in range(len(truncated_lookup), 0, -1):
            prefix = truncated_lookup[:i]
            if not prefix: continue

            logger.trace(f"  [Lookup] Checking prefix: '{prefix}'")
            deconjugated_forms = self.deconjugator.deconjugate(prefix)
            deconjugated_forms.add(Form(text=prefix))

            if len(deconjugated_forms) > 1:
                deconjugated_forms_text = {f.text for f in deconjugated_forms}
                logger.trace(f"    [Decon] for '{prefix}' returned: {deconjugated_forms_text}")

            current_prefix_results = []

            for form in deconjugated_forms:
                entry_indices = []
                if self._is_kana_only(form.text):
                    entry_indices = self.dictionary.lookup_kana.get(form.text, [])
                else:
                    entry_indices = self.dictionary.lookup_kan.get(form.text, [])

                # After getting potential entries, filter them based on Part of Speech tags
                validated_indices = []
                for index in entry_indices:
                    entry = self.dictionary.entries[index]

                    # If the form has no tags, it's a direct match, always valid.
                    if not form.tags:
                        validated_indices.append(index)
                        continue

                    # If the form has tags, the entry must contain that tag as a part of speech.
                    required_pos = form.tags[-1]
                    all_pos_for_entry = {pos for sense in entry['senses'] for pos in sense['pos']}
                    if required_pos in all_pos_for_entry:
                        validated_indices.append(index)
                    else:
                        logger.trace(
                            f"      - Pruning Entry ID {entry['id']} ('{entry['kebs'][0] if entry['kebs'] else entry['rebs'][0]}'). Deconj required POS '{required_pos}', but entry only has {all_pos_for_entry}")

                entry_indices = validated_indices

                # strict_alternatives logic
                if found_primary_match and self._is_kana_only(prefix):
                    filtered_indices = []
                    logger.trace(f"    [Filter ACTIVE] for prefix '{prefix}'")
                    for index in entry_indices:
                        entry = self.dictionary.entries[index]
                        misc_tags = self._get_misc_tags(entry)

                        passes_filter = not entry['kebs'] or 'uk' in misc_tags or 'ek' in misc_tags
                        written_form_for_log = entry['kebs'][0] if entry['kebs'] else entry['rebs'][0]
                        logger.trace(f"      - Checking Entry ID {entry['id']} ('{written_form_for_log}')")
                        logger.trace(f"        - Has Kanji ('kebs'): {bool(entry['kebs'])}")
                        logger.trace(f"        - Misc Tags: {misc_tags}")
                        logger.trace(f"        - Filter Result: {'PASS' if passes_filter else 'BLOCK'}")

                        if passes_filter:
                            filtered_indices.append(index)
                    entry_indices = filtered_indices

                for index in set(entry_indices):
                    current_prefix_results.append((self.dictionary.entries[index], form, len(prefix)))

            if current_prefix_results:
                if not found_primary_match:
                    logger.trace(f"  [Lookup] Found primary match with prefix: '{prefix}'")
                    found_primary_match = True

                for entry, form, match_len in current_prefix_results:
                    if entry['id'] not in all_found_entries:
                        all_found_entries[entry['id']] = (entry, form, match_len)

        results = self._format_and_sort_results(list(all_found_entries.values()), truncated_lookup)

        self.lookup_cache[truncated_lookup] = results[:MAX_DICT_ENTRIES]
        if len(self.lookup_cache) > self.CACHE_SIZE:
            self.lookup_cache.popitem(last=False)

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

            senses = [dict(s) for s in entry_data['senses']]
            if config.show_indonesian:
                for sense in senses:
                    glosses_str = '; '.join(sense.get('glosses', []))
                    translated = self._translate_text_to_indonesian(glosses_str)
                    if translated:
                        sense['glosses_id'] = [translated]

            merge_key = (written_form, reading_to_display)
            if merge_key not in merged_entries:
                merged_entries[merge_key] = {
                    "id": entry_data['id'],
                    "written_form": written_form,
                    "reading": reading_to_display, "senses": senses,
                    "tags": self._get_misc_tags(entry_data),
                    "deconjugation_process": form.process,
                    "priority": priority,
                    "match_len": match_len
                }
            else:
                current_entry = merged_entries[merge_key]
                current_entry['senses'].extend(senses)
                current_entry['tags'].update(self._get_misc_tags(entry_data))
                if priority > current_entry['priority']:
                    current_entry['priority'] = priority
                    current_entry['id'] = entry_data['id']
                    current_entry['deconjugation_process'] = form.process

        final_results_as_dicts = list(merged_entries.values())
        final_results_as_dicts.sort(key=lambda x: (x['match_len'], x['priority']), reverse=True)
        final_results = []
        for val in final_results_as_dicts:
            del val['match_len']
            final_results.append(DictionaryEntry(**val))
        return final_results

    def _calculate_priority(self, entry_data, form, match_len, original_lookup, written_form, reading) -> float:
        is_original_lookup_kana = self._is_kana_only(original_lookup)
        priority = float(entry_data['id']) / -10000000.0
        priority += match_len

        is_kana_only_entry = not entry_data['kebs']
        is_exact_match = len(form.process) == 0
        if is_original_lookup_kana and is_kana_only_entry and is_exact_match:
            priority += 100

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

        priority += bonus
        priority -= len(form.process)
        return priority
