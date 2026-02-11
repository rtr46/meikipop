import gzip
import json
import xml.etree.ElementTree as ET
import requests
import io

print("downloading kanjidic2...")
url = 'http://www.edrdg.org/kanjidic/kanjidic2.xml.gz'
response = requests.get(url)

print("parsing kanjidic2...")
entries = []

with gzip.open(io.BytesIO(response.content), 'rb') as f:
    tree = ET.parse(f)
    root = tree.getroot()

    for char_elem in root.findall('character'):
        literal = char_elem.find('literal').text

        meanings = []
        rmgroup = char_elem.find('.//rmgroup')
        if rmgroup is None:
            continue

        for meaning in rmgroup.findall('meaning'):
            if meaning.get('m_lang') is None:
                meanings.append(meaning.text)

        if not meanings:
            continue

        readings_set = set()

        for reading in rmgroup.findall('reading'):
            r_type = reading.get('r_type')
            text = reading.text

            if r_type == 'ja_kun':
                clean_text = text.split('.')[0]
                if clean_text:
                    readings_set.add(clean_text)

            elif r_type == 'ja_on':
                if text:
                    readings_set.add(text)

        sorted_readings = sorted(
            list(readings_set),
            key=lambda x: (0 if (x and 0x30A0 <= ord(x[0]) <= 0x30FF) else 1, x)
        )

        entries.append({
            "character": literal,
            "meanings": meanings,
            "readings": sorted_readings
        })

print(f"processed {len(entries)} kanji entries.")

with open('kanjidic2.json', 'w', encoding='utf-8') as f:
    json.dump(entries, f, ensure_ascii=False, separators=(',', ':'))
