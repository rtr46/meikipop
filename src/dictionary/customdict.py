# customdict.py
import json
import logging
import pickle
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.config.config import IS_WINDOWS

logger = logging.getLogger(__name__) # Get the logger


@dataclass
class KanjiEntry:
    literal: str
    onyomi: List[str]
    kunyomi: List[str]
    meanings: List[str]
    stroke_count: int = 0
    jlpt: int = 0
    grade: int = 0
    frequency: int = 0


class Dictionary:
    def __init__(self):
        self.entries = []
        self.lookup_kan = defaultdict(list)
        self.lookup_kana = defaultdict(list)
        self.deconjugator_rules = []
        self.priority_map = {}
        self.kanji_entries: Dict[str, KanjiEntry] = {}  # Maps kanji character -> KanjiEntry
        self._is_loaded = False

    def import_jmdict_json(self, json_paths: list[str]):
        all_jmdict_entries = []
        for path in sorted(json_paths):
            with open(path, 'r', encoding='utf-8') as f:
                all_jmdict_entries.extend(json.load(f))
        for entry_data in all_jmdict_entries:
            kebs = [k['keb'] for k in entry_data.get('k_ele', [])]
            rebs = [r['reb'] for r in entry_data.get('r_ele', [])]
            senses_processed = []
            last_pos = []
            for sense in entry_data.get('sense', []):
                glosses = [g for g in sense.get('gloss', [])]
                pos = sense.get('pos', last_pos)
                last_pos = pos
                if glosses:
                    senses_processed.append({'glosses': glosses, 'pos': [p.strip('&;') for p in pos]})
            if not (kebs or rebs) or not senses_processed:
                continue
            entry = {'id': entry_data['seq'], 'kebs': kebs, 'rebs': rebs, 'senses': senses_processed, 'raw_k_ele': entry_data.get('k_ele', []), 'raw_r_ele': entry_data.get('r_ele', []), 'raw_sense': entry_data.get('sense', [])}
            self.entries.append(entry)
            entry_index = len(self.entries) - 1
            for keb in kebs:
                self.lookup_kan[keb].append(entry_index)
            for reb in rebs:
                self.lookup_kana[reb].append(entry_index)

    def import_deconjugator(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
            self.deconjugator_rules = [r for r in rules if isinstance(r, dict)]

    def import_priority(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            priority_data = json.load(f)
            for item in priority_data:
                key = (item[0], item[1])
                self.priority_map[key] = item[2]

    def import_kanjidic(self, kanji_dict: Dict[str, dict]):
        for kanji_char, data in kanji_dict.items():
            self.kanji_entries[kanji_char] = KanjiEntry(
                literal=data.get('literal', kanji_char),
                onyomi=data.get('onyomi', []),
                kunyomi=data.get('kunyomi', []),
                meanings=data.get('meanings', []),
                stroke_count=data.get('stroke_count', 0),
                jlpt=data.get('jlpt', 0),
                grade=data.get('grade', 0),
                frequency=data.get('frequency', 0)
            )

    def get_kanji(self, char: str) -> Optional[KanjiEntry]:
        return self.kanji_entries.get(char)

    def save_dictionary(self, file_path: str):
        kanji_data = {}
        for char, entry in self.kanji_entries.items():
            kanji_data[char] = {
                'literal': entry.literal,
                'onyomi': entry.onyomi,
                'kunyomi': entry.kunyomi,
                'meanings': entry.meanings,
                'stroke_count': entry.stroke_count,
                'jlpt': entry.jlpt,
                'grade': entry.grade,
                'frequency': entry.frequency
            }

        data_to_save = {
            'entries': self.entries,
            'lookup_kan': self.lookup_kan,
            'lookup_kana': self.lookup_kana,
            'deconjugator_rules': self.deconjugator_rules,
            'priority_map': self.priority_map,
            'kanji_entries': kanji_data
        }
        with open(file_path, 'wb') as f:
            pickle.dump(data_to_save, f, protocol=pickle.HIGHEST_PROTOCOL)

    def load_dictionary(self, file_path: str) -> bool:
        if self._is_loaded:
            return True
        logger.info("Loading dictionary from file...")
        start_time = time.perf_counter()
        try:
            with open(file_path, 'rb') as f:
                data = pickle.load(f)
            self.entries = data['entries']
            self.lookup_kan = data['lookup_kan']
            self.lookup_kana = data['lookup_kana']
            self.deconjugator_rules = data['deconjugator_rules']
            self.priority_map = data['priority_map']

            kanji_data = data.get('kanji_entries', {})
            for char, entry_dict in kanji_data.items():
                self.kanji_entries[char] = KanjiEntry(
                    literal=entry_dict.get('literal', char),
                    onyomi=entry_dict.get('onyomi', []),
                    kunyomi=entry_dict.get('kunyomi', []),
                    meanings=entry_dict.get('meanings', []),
                    stroke_count=entry_dict.get('stroke_count', 0),
                    jlpt=entry_dict.get('jlpt', 0),
                    grade=entry_dict.get('grade', 0),
                    frequency=entry_dict.get('frequency', 0)
                )

            self._is_loaded = True
            duration = time.perf_counter() - start_time
            logger.info(f"Dictionary loaded in {duration:.2f} seconds. ({len(self.entries)} words, {len(self.kanji_entries)} kanji)")
            return True
        except FileNotFoundError:
            script_extension = "bat" if IS_WINDOWS else "sh"
            logger.error(
                f"ERROR: Dictionary file '{file_path}' not found. Add the file or try running the build.dictonary.{script_extension} script in the repo.")
            return False
        except Exception as e:
            logger.error(f"ERROR: Failed to load dictionary from {file_path}: {e}")
            return False