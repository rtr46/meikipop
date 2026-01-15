# process_kanjidic.py
# Parses KANJIDIC2 XML and outputs a JSON file with kanji data
# KANJIDIC2 source: http://www.edrdg.org/kanjidic/kanjidic2.xml.gz

import gzip
import json
import xml.etree.ElementTree as ET
from typing import Dict, Any


def parse_kanjidic2(xml_path: str) -> Dict[str, Any]:
    """
    Parse KANJIDIC2 XML file and extract kanji information.

    Returns a dict mapping kanji characters to their data:
    {
        "食": {
            "literal": "食",
            "onyomi": ["ショク", "ジキ"],
            "kunyomi": ["た.べる", "く.う", "く.らう"],
            "meanings": ["eat", "food"],
            "stroke_count": 9,
            "grade": 2,
            "jlpt": 5,
            "frequency": 328
        },
        ...
    }
    """
    kanji_dict = {}

    tree = ET.parse(xml_path)
    root = tree.getroot()

    for character in root.findall('character'):
        literal = character.find('literal')
        if literal is None:
            continue

        kanji_char = literal.text

        entry = {
            "literal": kanji_char,
            "onyomi": [],
            "kunyomi": [],
            "meanings": [],
            "stroke_count": 0,
            "grade": 0,
            "jlpt": 0,
            "frequency": 0
        }

        misc = character.find('misc')
        if misc is not None:
            stroke_count = misc.find('stroke_count')
            if stroke_count is not None:
                try:
                    entry["stroke_count"] = int(stroke_count.text)
                except (ValueError, TypeError):
                    pass

            grade = misc.find('grade')
            if grade is not None:
                try:
                    entry["grade"] = int(grade.text)
                except (ValueError, TypeError):
                    pass

            jlpt = misc.find('jlpt')
            if jlpt is not None:
                try:
                    entry["jlpt"] = int(jlpt.text)
                except (ValueError, TypeError):
                    pass

            freq = misc.find('freq')
            if freq is not None:
                try:
                    entry["frequency"] = int(freq.text)
                except (ValueError, TypeError):
                    pass

        reading_meaning = character.find('reading_meaning')
        if reading_meaning is not None:
            rmgroup = reading_meaning.find('rmgroup')
            if rmgroup is not None:
                for reading in rmgroup.findall('reading'):
                    r_type = reading.get('r_type')
                    if reading.text:
                        if r_type == 'ja_on':
                            entry["onyomi"].append(reading.text)
                        elif r_type == 'ja_kun':
                            entry["kunyomi"].append(reading.text)

                for meaning in rmgroup.findall('meaning'):
                    m_lang = meaning.get('m_lang')
                    if m_lang is None and meaning.text:
                        entry["meanings"].append(meaning.text)

        if entry["onyomi"] or entry["kunyomi"] or entry["meanings"]:
            kanji_dict[kanji_char] = entry

    return kanji_dict


def decompress_gzip(gz_path: str, output_path: str):
    """Decompress a .gz file."""
    with gzip.open(gz_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            f_out.write(f_in.read())


def main():
    import os
    import sys

    gz_path = 'kanjidic2.xml.gz'
    xml_path = 'kanjidic2.xml'
    output_path = 'data/kanjidic.json'

    if os.path.exists(gz_path):
        print(f"Decompressing {gz_path}...")
        decompress_gzip(gz_path, xml_path)

    if not os.path.exists(xml_path):
        print(f"Error: {xml_path} not found. Please download KANJIDIC2 from:", file=sys.stderr)
        print("  http://www.edrdg.org/kanjidic/kanjidic2.xml.gz", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {xml_path}...")
    kanji_dict = parse_kanjidic2(xml_path)

    print(f"Parsed {len(kanji_dict)} kanji entries.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(kanji_dict, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    if os.path.exists(gz_path) and os.path.exists(xml_path):
        os.remove(xml_path)
        print(f"Cleaned up {xml_path}")


if __name__ == "__main__":
    main()
