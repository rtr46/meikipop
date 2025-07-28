# lookup.py
import time
from dataclasses import dataclass
from typing import List, Set, Dict, Tuple
import re
from collections import OrderedDict
from multiprocessing import Process, Queue
import atexit

from dictionary import Dictionary
from deconjugator import Deconjugator, Form
from settings import settings

KANJI_REGEX = re.compile(r'[\u4e00-\u9faf]')

@dataclass
class DictionaryEntry:
    id: int; written_form: str; reading: str; definitions: list; deconjugation_process: tuple; priority: float = 0.0

class Lookup:
    def __init__(self):
        self.request_queue = Queue()
        self.result_queue = Queue()
        
        self.worker_process = Process(
            target=lookup_worker_main,
            args=(self.request_queue, self.result_queue),
            daemon=True
        )
        self.worker_process.start()
        
        atexit.register(self.stop_worker)
        
        initialization_result = self.result_queue.get(timeout=60) # 60s timeout for slow systems
        if initialization_result != "READY":
            raise RuntimeError(f"Lookup worker failed to initialize: {initialization_result}")

    def generate_entries(self, text: str, char_pos: int, char: str, lookup_string: str) -> List[DictionaryEntry]:
        if not self.worker_process.is_alive():
            raise RuntimeError("Lookup worker process is not running.")
        request = (text, char_pos, char, lookup_string)
        self.request_queue.put(request)
        results = self.result_queue.get()
        return results

    def stop_worker(self):
        if self.worker_process and self.worker_process.is_alive():
            settings.user_log("Terminating lookup worker process...")
            self.worker_process.terminate()
            self.worker_process.join()

def lookup_worker_main(request_queue: Queue, result_queue: Queue):
    try:
        dictionary = Dictionary()
        if not dictionary.load_dictionary('jmdict_enhanced.pkl'):
             raise RuntimeError("Failed to load dictionary in worker process.")
        
        lookup_engine = _InternalLookupEngine(dictionary)
        result_queue.put("READY")
        
    except Exception as e:
        result_queue.put(f"WORKER_ERROR: {e}")
        return

    while True:
        try:
            request = request_queue.get()
            if request is None:
                break
            text, char_pos, char, lookup_string = request
            results = lookup_engine.generate_entries(text, char_pos, char, lookup_string)
            result_queue.put(results)
        except (KeyboardInterrupt, EOFError):
            break

class _InternalLookupEngine:
    def __init__(self, dictionary: Dictionary):
        self.dictionary = dictionary
        self.deconjugator = Deconjugator(self.dictionary.deconjugator_rules)
        self.lookup_cache = OrderedDict()
        self.CACHE_SIZE = 500
        
    def generate_entries(self, text: str, char_pos: int, char: str, lookup_string: str) -> List[DictionaryEntry]:
        truncated_lookup = lookup_string[:settings.max_lookup_length]
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
        self.lookup_cache[truncated_lookup] = results[:10]
        if len(self.lookup_cache) > self.CACHE_SIZE:
            self.lookup_cache.popitem(last=False)
        return results[:10]

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
            priority = self._calculate_priority(entry_data, form, match_len, original_lookup, written_form, matched_reading)
            merge_key = (written_form, reading_to_display)
            if merge_key not in merged_entries:
                merged_entries[merge_key] = {"id": entry_data['id'], "written_form": written_form, "reading": reading_to_display, "definitions": [s['glosses'] for s in entry_data['senses']], "deconjugation_process": form.process, "priority": priority}
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