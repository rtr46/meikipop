# meikipop/utils/csv_export.py
import csv
import logging
import os
import threading
from typing import Optional

from meikipop.dictionary.lookup import KanjiEntry

logger = logging.getLogger(__name__)


class CsvExporter:
    """Appends dictionary entries as (kanji, reading, meaning) rows to a CSV file."""

    def __init__(self):
        self.path: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def set_path(self, path: Optional[str]):
        self.path = os.path.abspath(path) if path else None
        if self.path:
            logger.info(f"CSV export: appending selected entries to '{self.path}'")

    @staticmethod
    def entry_to_row(entry) -> tuple[str, str, str]:
        if isinstance(entry, KanjiEntry):
            return entry.character, ", ".join(entry.readings), ", ".join(entry.meanings)

        sense_texts = []
        for sense in entry.senses:
            glosses = sense.get('glosses', [])
            if glosses:
                sense_texts.append(", ".join(glosses))
        meaning = "; ".join(f"({i}) {t}" for i, t in enumerate(sense_texts, 1)) if len(sense_texts) > 1 \
            else "".join(sense_texts)
        return entry.written_form, entry.reading or entry.written_form, meaning

    def append(self, entry) -> bool:
        if not self.path:
            return False
        row = self.entry_to_row(entry)
        try:
            with self._lock:
                is_new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
                # BOM only on a fresh file so Excel detects UTF-8; appending keeps the file intact
                with open(self.path, "a", newline="", encoding="utf-8-sig" if is_new else "utf-8") as f:
                    writer = csv.writer(f)
                    if is_new:
                        writer.writerow(("Kanji", "Reading", "Meaning"))
                    writer.writerow(row)
            logger.info(f"CSV export: saved {row[0]} [{row[1]}]")
            return True
        except OSError:
            logger.exception(f"CSV export: failed to write to '{self.path}'")
            return False


csv_exporter = CsvExporter()
