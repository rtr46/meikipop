import gzip
import json
import xml.etree.ElementTree as ET
import requests
import io
import re
from collections import Counter, defaultdict

# --- Configuration ---
URL_KANJI = 'http://www.edrdg.org/kanjidic/kanjidic2.xml.gz'
URL_JMDICT = 'http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz'
URL_FREQ = 'https://api.jiten.moe/api/frequency-list/download?downloadType=csv'
URL_IDS = 'https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt'

PRIORITY_TAGS = {"news1", "news2", "ichi1", "ichi2", "spec1", "spec2", "gai1", "gai2"}

RENDAKU_MAP = {
    'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
    'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'ぜ': 'ぜ', 'そ': 'ぞ',
    'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'て', 'ど': 'と',
    'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
    'ぱ': 'は', 'ぴ': 'ひ', 'ぷ': 'ぷ', 'ぺ': 'ぺ', 'ほ': 'ほ'
}
SOKUON_ENDINGS = ('く', 'き', 'つ', 'ち')


def hira_to_kata(text):
    return ''.join(chr(ord(c) + 96) if 0x3041 <= ord(c) <= 0x3096 else c for c in text)


def kata_to_hira(text):
    return ''.join(chr(ord(c) - 96) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in text)


def is_hiragana(c):
    return 0x3040 <= ord(c) <= 0x309F


def get_variants(reading):
    variants = {reading}
    if not reading: return variants
    first = reading[0]
    if first in RENDAKU_MAP:
        variants.add(RENDAKU_MAP[first] + reading[1:])
    if reading.endswith(SOKUON_ENDINGS):
        variants.add(reading[:-1] + 'っ')
        if first in RENDAKU_MAP:
            variants.add(RENDAKU_MAP[first] + reading[1:-1] + 'っ')
    return variants


def run_process():
    print("downloading data files...")
    kanji_xml = requests.get(URL_KANJI).content
    jmdict_xml = requests.get(URL_JMDICT).content
    vocab_csv = requests.get(URL_FREQ).content.decode('utf-8')
    ids_text = requests.get(URL_IDS).text

    print("parsing Frequency data...")
    word_to_rank = {}
    for line in vocab_csv.splitlines()[:500000]:
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                word_to_rank[parts[0]] = int(parts[2])
            except:
                continue

    print("parsing JMdict data...")
    word_to_readings = defaultdict(list)
    word_to_jm_info = {}  # word -> {'r': display_reading, 'm': meaning}
    kanji_to_words = defaultdict(list)

    ctx = ET.iterparse(gzip.open(io.BytesIO(jmdict_xml), 'rb'), events=('end',))
    for _, elem in ctx:
        if elem.tag == 'entry':
            k_nodes = elem.findall('k_ele')
            r_nodes = elem.findall('r_ele')
            if k_nodes and r_nodes:
                all_tags = [t.text for t in elem.findall('.//ke_pri')] + [t.text for t in elem.findall('.//re_pri')]
                is_priority = any(tag in PRIORITY_TAGS for tag in all_tags)

                # Use the very first reading and first gloss as the "display" info for examples
                display_reading = r_nodes[0].find('reb').text
                gloss_node = elem.find('.//sense/gloss')
                display_meaning = gloss_node.text if gloss_node is not None else ""

                entry_readings = [kata_to_hira(r.find('reb').text) for r in r_nodes]
                for k_node in k_nodes:
                    word = k_node.find('keb').text
                    if word in word_to_rank:
                        for r in entry_readings:
                            word_to_readings[word].append((r, is_priority))

                        word_to_jm_info[word] = {'r': display_reading, 'm': display_meaning}

                        for char in word:
                            if 0x4E00 <= ord(char) <= 0x9FFF:
                                kanji_to_words[char].append(word)
            elem.clear()

    print("parsing CHISE IDS...")
    ids_map = {}
    for line in ids_text.splitlines():
        if not line or line.startswith(';'): continue
        parts = line.split('\t')
        if len(parts) < 3: continue

        kanji = parts[1]
        best_seq = parts[2]
        for p in parts[2:]:
            if '[J]' in p or '[JA]' in p:
                best_seq = p
                break

        clean_seq = re.sub(r'\[.*?\]|&[^;]+;|[\u2FF0-\u2FFB]', '', best_seq)

        components = []
        for char in clean_seq:
            if char != kanji and char not in components:
                code = ord(char)
                # Comprehensive check for Kanji, Radicals, Extensions, and Strokes
                is_valid = (
                        (0x4E00 <= code <= 0x9FFF) or  # Main Unified Ideographs
                        (0x2E80 <= code <= 0x2FDF) or  # Radicals Supplement & Kangxi Radicals
                        (0x3400 <= code <= 0x4DBF) or  # Extension A
                        (0x31C0 <= code <= 0x31EF) or  # CJK Strokes
                        (code >= 0x20000)  # Extensions B, C, D, etc.
                )
                if is_valid:
                    components.append(char)
        ids_map[kanji] = components

    print("parsing kanjidic2 & calculating frequencies...")
    meaning_lookup = {}
    kanji_data_list = []

    with gzip.open(io.BytesIO(kanji_xml), 'rb') as f:
        root = ET.parse(f).getroot()
        for char_elem in root.findall('character'):
            literal = char_elem.find('literal').text
            m_node = char_elem.find('.//rmgroup/meaning')
            if m_node is not None and m_node.get('m_lang') is None:
                meaning_lookup[literal] = re.sub(r'\s*\(.*?\)', '', m_node.text).strip()

        for char_elem in root.findall('character'):
            literal = char_elem.find('literal').text
            meanings = [m.text for m in char_elem.findall('.//rmgroup/meaning') if m.get('m_lang') is None]
            if not meanings: continue

            raw_readings = char_elem.findall('.//rmgroup/reading')
            reading_attribs = defaultdict(lambda: {'type': None, 'is_stem': False, 'is_full': False})
            for r in raw_readings:
                text = r.text.replace('-', '')
                stem, full = text.split('.')[0], text.replace('.', '')
                h_stem, h_full = kata_to_hira(stem), kata_to_hira(full)
                if r.get('r_type') == 'ja_on':
                    reading_attribs[h_full].update({'type': 'on', 'is_full': True})
                else:
                    reading_attribs[h_stem].update({'type': 'kun', 'is_stem': True})
                    reading_attribs[h_full].update({'type': 'kun', 'is_full': True})

            total_score = Counter()
            standalone_score = Counter()
            reading_to_best_words = defaultdict(list)  # stem -> list of {w, r, m, rank}

            for word in set(kanji_to_words.get(literal, [])):
                rank = word_to_rank.get(word, 500000)
                base_weight = 1000000 / (rank + 100)
                w_chars, r_chars_orig = list(word), []

                for word_reading, is_priority in word_to_readings.get(word, []):
                    weight = base_weight * 10 if is_priority else base_weight
                    r_chars = list(word_reading)
                    w_temp = list(w_chars)
                    while w_temp and r_chars and is_hiragana(w_temp[-1]) and w_temp[-1] == r_chars[-1]:
                        w_temp.pop()
                        r_chars.pop()
                    extracted_reading = "".join(r_chars)

                    for base_r, attr in reading_attribs.items():
                        is_cand = (attr['type'] == 'on') or (word == literal and attr['is_full']) or (
                                word != literal and attr['is_stem'])
                        if not is_cand: continue

                        for variant in get_variants(base_r):
                            if variant in extracted_reading:
                                total_score[base_r] += weight
                                if word == literal: standalone_score[base_r] += weight

                                # Store word info for example selection
                                info = word_to_jm_info[word]
                                reading_to_best_words[base_r].append(
                                    {'w': word, 'r': info['r'], 'm': info['m'], 'rank': rank})
                                break

            # Sort candidate words for each reading by rank
            for r in reading_to_best_words:
                reading_to_best_words[r].sort(key=lambda x: x['rank'])

            attested = [r for r, count in total_score.items() if count > 0]
            ranked_stems = sorted(attested, key=lambda r: (standalone_score[r] > 0, total_score[r]), reverse=True)

            # --- Example Selection Logic ---
            final_examples = []
            used_words = set()

            def add_ex(stem_idx, word_idx):
                if stem_idx < len(ranked_stems):
                    stem = ranked_stems[stem_idx]
                    words = [w for w in reading_to_best_words[stem] if w['w'] not in used_words]
                    if word_idx < len(words):
                        ex = words[word_idx]
                        final_examples.append({'w': ex['w'], 'r': ex['r'], 'm': ex['m']})
                        used_words.add(ex['w'])

            if len(ranked_stems) >= 3:
                add_ex(0, 0);
                add_ex(1, 0);
                add_ex(2, 0)
            elif len(ranked_stems) == 2:
                add_ex(0, 0);
                add_ex(0, 1);
                add_ex(1, 0)
            elif len(ranked_stems) == 1:
                add_ex(0, 0);
                add_ex(0, 1);
                add_ex(0, 2)

            final_readings = []
            for r in ranked_stems:
                final_readings.append(hira_to_kata(r) if reading_attribs[r]['type'] == 'on' else r)

            if not final_readings: continue

            comp_list = []
            if literal in ids_map:
                for c_char in ids_map[literal]:
                    comp_data = {"c": c_char}
                    if c_char in meaning_lookup:
                        comp_data["m"] = meaning_lookup[c_char]
                    comp_list.append(comp_data)

            kanji_data_list.append({
                "character": literal,
                "meanings": meanings,
                "readings": final_readings,
                "components": comp_list,
                "examples": final_examples
            })

    print(f"processed {len(kanji_data_list)} kanji entries.")
    with open('kanjidic2.json', 'w', encoding='utf-8') as f:
        json.dump(kanji_data_list, f, ensure_ascii=False, separators=(',', ':'))


if __name__ == "__main__":
    run_process()
