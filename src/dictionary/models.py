from dataclasses import dataclass, field
from typing import List, Set, Optional, Tuple


@dataclass
class Sense:
    __slots__ = ['pos', 'tags', 'glosses']  # Saves ~100 bytes per instance!

    def __init__(self, pos, tags, glosses):
        self.pos = pos
        self.tags = tags
        self.glosses = glosses


@dataclass
class DictionaryEntry:
    __slots__ = ['keb', 'reb', 'freq', 'sense_indices']
    keb: str  # The writing (Kanji or Kana)
    reb: str  # The reading
    freq: int  # Rank (lower is better)
    sense_indices: List[int]  # Pointers to the central definition registry
