"""
build_dictionary.py
Builds dictionary.pkl from downloaded source files.
Downloaded source files are cached in ./cache/ and reused on subsequent runs.
"""

import gzip
import io
import json
import os
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from itertools import count
from typing import Optional
import xml.etree.ElementTree as StdET

import requests
from lxml import etree

# ── Constants ──────────────────────────────────────────────────────────────────

DATA_DIR           = 'data'
OUTPUT_PATH        = 'dictionary.pkl'
DECONJUGATOR_PATH  = os.path.join(DATA_DIR, 'deconjugator.json')
SYNTHETIC_ID_START = 10_000_000  # safely above any real JMdict seq number
DEFAULT_FREQ       = 999_999

URLS = {
    'jmdict_e':  'http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz',
    'kanjidic':  'http://www.edrdg.org/kanjidic/kanjidic2.xml.gz',
    'ids':       'https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt',
    'frequency': 'https://api.jiten.moe/api/frequency-list/download?downloadType=csv',
}

XML_LANG      = '{http://www.w3.org/XML/1998/namespace}lang'
PRIORITY_TAGS = {"news1", "news2", "ichi1", "ichi2", "spec1", "spec2", "gai1", "gai2"}

RENDAKU_MAP = {
    'か': 'が', 'き': 'ぎ', 'く': 'ぐ', 'け': 'げ', 'こ': 'ご',
    'さ': 'ざ', 'し': 'じ', 'す': 'ず', 'せ': 'ぜ', 'そ': 'ぞ',
    'た': 'だ', 'ち': 'ぢ', 'つ': 'づ', 'て': 'で', 'と': 'ど',
    'は': 'ば', 'ひ': 'び', 'ふ': 'ぶ', 'へ': 'べ', 'ほ': 'ぼ',
}
SOKUON_ENDINGS = ('く', 'き', 'つ', 'ち')


# ── Utilities ──────────────────────────────────────────────────────────────────

def kata_to_hira(t: str) -> str:
    return ''.join(chr(ord(c) - 96) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in t)

def hira_to_kata(t: str) -> str:
    return ''.join(chr(ord(c) + 96) if 0x3041 <= ord(c) <= 0x3096 else c for c in t)

def is_hiragana(c: str) -> bool:
    return 0x3040 <= ord(c) <= 0x309F

def get_variants(reading: str) -> set:
    v = {reading}
    if not reading:
        return v
    f = reading[0]
    if f in RENDAKU_MAP:
        v.add(RENDAKU_MAP[f] + reading[1:])
    if reading.endswith(SOKUON_ENDINGS):
        v.add(reading[:-1] + 'っ')
        if f in RENDAKU_MAP:
            v.add(RENDAKU_MAP[f] + reading[1:-1] + 'っ')
    return v


# ── Download / cache ───────────────────────────────────────────────────────────

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_or_download(key: str) -> bytes:
    path = os.path.join(DATA_DIR, key)
    if os.path.exists(path):
        print(f"  Using cached: {path}")
        with open(path, 'rb') as f:
            return f.read()
    url = URLS[key]
    print(f"  Downloading {key} from {url} ...")
    data = requests.get(url, timeout=120).content
    with open(path, 'wb') as f:
        f.write(data)
    print(f"  Saved {len(data) // 1024} KB to {path}")
    return data


# ── Frequency ──────────────────────────────────────────────────────────────────

def load_freq_map(csv_bytes: bytes) -> dict:
    """Returns {(word, form): rank} from the frequency CSV."""
    result = {}
    for line in csv_bytes.decode('utf-8').splitlines()[1:]:  # skip header
        parts = line.split(',')
        if len(parts) >= 3:
            try:
                if result.get((parts[0], parts[1])) is None: # avoid redundant entries
                    result[(parts[0], parts[1])] = int(parts[2])
            except ValueError:
                pass
    print(f"  {len(result)} frequency entries loaded")
    return result


# ── JMdict parsing ─────────────────────────────────────────────────────────────

def parse_jmdict_root(gz_bytes: bytes):
    """Parse JMdict_e from gzipped bytes, resolving entity references."""
    xml_bytes = gzip.decompress(gz_bytes)
    parser    = etree.XMLParser(resolve_entities=False)
    tree      = etree.parse(io.BytesIO(xml_bytes), parser)
    # Entity nodes (e.g. &v1;) carry their resolved text; append into parent.text
    for ent in tree.iter(etree.Entity):
        parent = ent.getparent()
        if parent is not None:
            parent.text = (parent.text or '') + (ent.text or '')
            if ent.tail:
                parent.text += ent.tail
    return tree.getroot()


def _process_senses(entry_elem) -> list:
    """Extract and normalise sense elements. Propagates pos across senses per JMdict spec."""
    senses   = []
    last_pos = []
    for sense in entry_elem.iter('sense'):
        stagk   = [e.text for e in sense.findall('stagk') if e.text]
        stagr   = [e.text for e in sense.findall('stagr') if e.text]
        pos_raw = [e.text.strip('&;') for e in sense.findall('pos') if e.text]
        if pos_raw:
            last_pos = pos_raw
        tags    = [e.text.strip('&;') for e in sense.findall('misc') if e.text]
        glosses = [g.text for g in sense.findall('gloss')
                   if g.get(XML_LANG, 'eng') == 'eng' and g.text]
        if not glosses:
            continue
        normalized_sense = {'glosses': glosses, 'pos': list(last_pos), 'tags': tags}
        if stagk:
            normalized_sense['stagk'] = stagk
        if stagr:
            normalized_sense['stagr'] = stagr
        senses.append(normalized_sense)
    return senses


def _applicable_sense_indices(senses: list, keb: Optional[str], reb: str) -> tuple:
    """
    Return tuple of sense indices applicable to a (keb, reb) pair.
    keb=None means kana-only (no kanji form for this lookup path).
    """
    out = []
    for i, s in enumerate(senses):
        stagk = s.get('stagk', [])
        stagr = s.get('stagr', [])
        keb_ok = (not stagk) or (keb is None) or (keb in stagk)
        reb_ok = (not stagr) or (reb in stagr)
        if keb_ok and reb_ok:
            out.append(i)
    return tuple(out)


def build_jmdict_data(root, freq_map: dict):
    """
    Walk the parsed JMdict root and produce:
      entries    – {entry_id: [sense, ...]}
      lookup_map – {surface_form: [MapEntry, ...]}

    MapEntry = (written_form, reading_or_None, freq, entry_id)

    lookup_map keys are keb or reb surface strings
    """
    entries    = {}
    lookup_map = defaultdict(list)
    syn_id     = count(SYNTHETIC_ID_START)

    for entry_elem in root.iter('entry'):
        seq    = int(entry_elem.find('ent_seq').text)
        k_eles = entry_elem.findall('k_ele')
        r_eles = entry_elem.findall('r_ele')

        # (keb, frozenset of ke_inf flags)
        k_data = [
            (k.find('keb').text,
             frozenset(e.text.strip('&;') for e in k.findall('ke_inf') if e.text))
            for k in k_eles
        ]

        # (reb, no_kanji_bool, restr_list, frozenset of re_inf flags)
        r_data = [
            (r.find('reb').text,
             r.find('re_nokanji') is not None,
             [e.text for e in r.findall('re_restr') if e.text],
             frozenset(e.text.strip('&;') for e in r.findall('re_inf') if e.text))
            for r in r_eles
        ]

        senses = _process_senses(entry_elem)
        if not senses:
            continue

        # Canonical forms: first form not marked search-only
        # None when all kanji forms are search-only — treat entry as kana-only for display
        canonical_keb = next(
            (keb for keb, flags in k_data if 'sK' not in flags),
            None
        )
        canonical_reb = next(
            (reb for reb, _, _, flags in r_data if 'sk' not in flags),
            r_data[0][0]
        )

        # all_uk: every sense prefers kana — kana-path lookups show kana as written form
        all_uk = bool(senses) and all('uk' in s['tags'] for s in senses)

        # Build all valid (keb_or_None, k_flags, reb, r_flags, is_restr_pair) tuples.
        form_pairs = []
        if not k_data:
            for reb, _, _, r_flags in r_data:
                if 'ok' in r_flags:
                    continue
                form_pairs.append((None, frozenset(), reb, r_flags, False))
        else:
            for reb, no_kanji, restr, r_flags in r_data:
                if 'ok' in r_flags:
                    continue
                if no_kanji:
                    form_pairs.append((None, frozenset(), reb, r_flags, False))
                elif restr:
                    for keb, k_flags in k_data:
                        if keb in restr:
                            form_pairs.append((keb, k_flags, reb, r_flags, True))
                else:
                    for keb, k_flags in k_data:
                        form_pairs.append((keb, k_flags, reb, r_flags, False))

        # Group by applicable sense subset (stagk/stagr resolution)
        sense_groups: dict[tuple, list] = defaultdict(list)
        for pair in form_pairs:
            keb, _, reb, _, _ = pair
            sense_indices = _applicable_sense_indices(senses, keb, reb)
            if sense_indices:
                sense_groups[sense_indices].append(pair)

        if not sense_groups:
            continue

        # Largest sense group keeps the real JMdict ID; smaller variants get synthetic IDs
        sorted_sense_groups = sorted(sense_groups.keys(), key=len, reverse=True)
        ids_for_sense_groups  = {sorted_sense_groups[0]: seq}
        for g in sorted_sense_groups[1:]:
            ids_for_sense_groups[g] = next(syn_id)

        for sense_indices_of_sense_group, form_pairs_of_sense_group in sense_groups.items():
            entry_id = ids_for_sense_groups[sense_indices_of_sense_group]

            entries[entry_id] = [
                {'glosses': senses[i]['glosses'],
                 'pos':     senses[i]['pos'],
                 'tags':    senses[i]['tags']}
                for i in sense_indices_of_sense_group
            ]

            seen_lookup: set = set()

            # ── kanji entries: one per surface keb ───────────────────────────
            for keb, k_flags, reb, r_flags, _ in form_pairs_of_sense_group:
                if keb is None:
                    continue
                display_reb = canonical_reb if 'sk' in r_flags else reb
                if canonical_keb is None:
                    written_form = canonical_reb
                    reading = None
                else:
                    written_form = canonical_keb if 'sK' in k_flags else keb
                    reading = display_reb

                dedup = (keb, written_form, reading, entry_id)
                if dedup not in seen_lookup:
                    seen_lookup.add(dedup)
                    freq = freq_map.get((keb, display_reb), DEFAULT_FREQ)
                    lookup_map[keb].append((written_form, reading, freq, entry_id))

            # ── kana entries: one per surface reb ────────────────────────────
            seen_rebs: set = set()
            for keb, k_flags, reb, r_flags, is_restr in form_pairs_of_sense_group:
                if reb in seen_rebs:
                    continue
                seen_rebs.add(reb)

                display_reb = canonical_reb if 'sk' in r_flags else reb
                display_keb = canonical_keb if (keb is not None and 'sK' in k_flags) else keb

                if all_uk or keb is None or canonical_keb is None:
                    written_form = display_reb
                    reading = None
                elif is_restr:
                    written_form = display_keb
                    reading = display_reb
                else:
                    written_form = canonical_keb
                    reading = display_reb

                dedup = (reb, written_form, reading, entry_id)
                if dedup not in seen_lookup:
                    seen_lookup.add(dedup)
                    freq = freq_map.get((reb, display_reb), DEFAULT_FREQ)
                    lookup_map[reb].append((written_form, reading, freq, entry_id))

    n_refs = sum(len(v) for v in lookup_map.values())
    print(f"  {len(entries)} core entries | {n_refs} lookup refs")
    return entries, lookup_map


# ── Kanjidic + IDS ─────────────────────────────────────────────────────────────

def build_kanjidic_data(kanjidic_gz: bytes, ids_text: str,
                        jmdict_root, freq_map: dict) -> dict:
    """
    Build kanji_entries from kanjidic2 + CHISE IDS + JMdict example data.
    Returns {character: {character, meanings, readings, components, examples}}.
    """
    word_freq: dict[str, int] = {}
    for (word, _form), rank in freq_map.items():
        if word not in word_freq or rank < word_freq[word]:
            word_freq[word] = rank

    word_to_readings:    dict[str, list] = defaultdict(list)
    word_to_jmdict_info: dict[str, dict] = {}
    kanji_to_words:      dict[str, list] = defaultdict(list)

    for entry_elem in jmdict_root.iter('entry'):
        k_nodes = entry_elem.findall('k_ele')
        r_nodes = entry_elem.findall('r_ele')
        if not k_nodes or not r_nodes:
            continue
        all_tags    = ([t.text for t in entry_elem.findall('.//ke_pri')] +
                       [t.text for t in entry_elem.findall('.//re_pri')])
        is_priority = any(t in PRIORITY_TAGS for t in all_tags if t)
        display_reb = r_nodes[0].find('reb').text
        gloss_node  = entry_elem.find('.//sense/gloss')
        display_m   = gloss_node.text if gloss_node is not None else ''
        entry_readings = [kata_to_hira(r.find('reb').text) for r in r_nodes]
        for k_node in k_nodes:
            word = k_node.find('keb').text
            if word not in word_freq:
                continue
            for r in entry_readings:
                word_to_readings[word].append((r, is_priority))
            word_to_jmdict_info[word] = {'r': display_reb, 'm': display_m}
            for char in word:
                if 0x4E00 <= ord(char) <= 0x9FFF:
                    kanji_to_words[char].append(word)

    # Parse CHISE IDS
    ids_map: dict[str, list] = {}
    for line in ids_text.splitlines():
        if not line or line.startswith(';'):
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            continue
        kanji    = parts[1]
        best_seq = parts[2]
        for p in parts[2:]:
            if '[J]' in p or '[JA]' in p:
                best_seq = p
                break
        clean = re.sub(r'\[.*?\]|&[^;]+;|[\u2FF0-\u2FFB]', '', best_seq)
        components = []
        for char in clean:
            if char == kanji or char in components:
                continue
            code = ord(char)
            if ((0x4E00 <= code <= 0x9FFF) or (0x2E80 <= code <= 0x2FDF) or
                    (0x3400 <= code <= 0x4DBF) or (0x31C0 <= code <= 0x31EF) or
                    code >= 0x20000):
                components.append(char)
        ids_map[kanji] = components

    # Parse kanjidic2
    with gzip.open(io.BytesIO(kanjidic_gz), 'rb') as f:
        kd_root = StdET.parse(f).getroot()

    meaning_lookup: dict[str, str] = {}
    for char_elem in kd_root.findall('character'):
        literal = char_elem.find('literal').text
        m_node  = char_elem.find('.//rmgroup/meaning')
        if m_node is not None and m_node.get('m_lang') is None and m_node.text:
            meaning_lookup[literal] = re.sub(r'\s*\(.*?\)', '', m_node.text).strip()

    kanji_entries = {}
    for char_elem in kd_root.findall('character'):
        literal  = char_elem.find('literal').text
        meanings = [m.text for m in char_elem.findall('.//rmgroup/meaning')
                    if m.get('m_lang') is None]
        if not meanings:
            continue

        raw_readings = char_elem.findall('.//rmgroup/reading')
        reading_attribs: dict = defaultdict(lambda: {'type': None, 'is_stem': False, 'is_full': False})
        for r in raw_readings:
            text       = r.text.replace('-', '')
            stem, full = text.split('.')[0], text.replace('.', '')
            h_stem, h_full = kata_to_hira(stem), kata_to_hira(full)
            if r.get('r_type') == 'ja_on':
                reading_attribs[h_full].update({'type': 'on', 'is_full': True})
            else:
                reading_attribs[h_stem].update({'type': 'kun', 'is_stem': True})
                reading_attribs[h_full].update({'type': 'kun', 'is_full': True})

        total_score      = Counter()
        standalone_score = Counter()
        reading_to_words: dict[str, list] = defaultdict(list)

        for word in set(kanji_to_words.get(literal, [])):
            rank        = word_freq.get(word, 500_000)
            base_weight = 1_000_000 / (rank + 100)
            for word_reading, is_priority in word_to_readings.get(word, []):
                weight  = base_weight * 10 if is_priority else base_weight
                w_chars = list(word)
                r_chars = list(word_reading)
                while (w_chars and r_chars and
                       is_hiragana(w_chars[-1]) and w_chars[-1] == r_chars[-1]):
                    w_chars.pop()
                    r_chars.pop()
                extracted = ''.join(r_chars)
                for base_r, attr in reading_attribs.items():
                    is_cand = (
                        attr['type'] == 'on' or
                        (word == literal and attr['is_full']) or
                        (word != literal and attr['is_stem'])
                    )
                    if not is_cand:
                        continue
                    for variant in get_variants(base_r):
                        if variant in extracted:
                            total_score[base_r] += weight
                            if word == literal:
                                standalone_score[base_r] += weight
                            info = word_to_jmdict_info[word]
                            reading_to_words[base_r].append(
                                {'w': word, 'r': info['r'], 'm': info['m'], 'rank': rank})
                            break

        for r in reading_to_words:
            reading_to_words[r].sort(key=lambda x: x['rank'])

        attested     = [r for r in total_score if total_score[r] > 0]
        ranked_stems = sorted(attested,
                              key=lambda r: (standalone_score[r] > 0, total_score[r]),
                              reverse=True)
        if not ranked_stems:
            continue

        final_examples: list = []
        used_words: set = set()

        def add_ex(stem_idx: int, word_idx: int):
            if stem_idx >= len(ranked_stems):
                return
            stem  = ranked_stems[stem_idx]
            words = [w for w in reading_to_words[stem] if w['w'] not in used_words]
            if word_idx < len(words):
                ex = words[word_idx]
                final_examples.append({'w': ex['w'], 'r': ex['r'], 'm': ex['m']})
                used_words.add(ex['w'])

        if   len(ranked_stems) >= 3: add_ex(0,0); add_ex(1,0); add_ex(2,0)
        elif len(ranked_stems) == 2: add_ex(0,0); add_ex(0,1); add_ex(1,0)
        else:                        add_ex(0,0); add_ex(0,1); add_ex(0,2)

        final_readings = [
            hira_to_kata(r) if reading_attribs[r]['type'] == 'on' else r
            for r in ranked_stems
        ]
        comp_list = [
            {'c': c, **({'m': meaning_lookup[c]} if c in meaning_lookup else {})}
            for c in ids_map.get(literal, [])
        ]
        kanji_entries[literal] = {
            'character':  literal,
            'meanings':   meanings,
            'readings':   final_readings,
            'components': comp_list,
            'examples':   final_examples,
        }

    print(f"  {len(kanji_entries)} kanji entries built")
    return kanji_entries


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ensure_dirs()

    print("\n[1/5] Loading source files ...")
    jmdict_gz   = load_or_download('jmdict_e')
    kanjidic_gz = load_or_download('kanjidic')
    ids_bytes   = load_or_download('ids')
    freq_bytes  = load_or_download('frequency')
    ids_text    = ids_bytes.decode('utf-8', errors='replace')

    if not os.path.exists(DECONJUGATOR_PATH):
        print(f"ERROR: {DECONJUGATOR_PATH} not found.", file=sys.stderr)
        sys.exit(1)
    with open(DECONJUGATOR_PATH, 'r', encoding='utf-8') as f:
        deconjugator_rules = [r for r in json.load(f) if isinstance(r, dict)]
    print(f"  {len(deconjugator_rules)} deconjugator rules loaded")

    print("\n[2/5] Parsing frequency list ...")
    freq_map = load_freq_map(freq_bytes)

    print("\n[3/5] Parsing JMdict_e ...")
    t0 = time.time()
    jmdict_root = parse_jmdict_root(jmdict_gz)
    entries, lookup_map = build_jmdict_data(jmdict_root, freq_map)
    print(f"  Done in {time.time() - t0:.1f}s")

    print("\n[4/5] Building kanjidic data ...")
    t0 = time.time()
    kanji_entries = build_kanjidic_data(kanjidic_gz, ids_text, jmdict_root, freq_map)
    print(f"  Done in {time.time() - t0:.1f}s")

    print(f"\n[5/5] Saving dictionary to {OUTPUT_PATH} ...")
    t0 = time.time()
    payload = {
        'entries':            entries,
        'lookup_map':         dict(lookup_map),
        'kanji_entries':      kanji_entries,
        'deconjugator_rules': deconjugator_rules,
    }
    with open(OUTPUT_PATH, 'wb') as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = os.path.getsize(OUTPUT_PATH) / 1_048_576
    print(f"  Saved {size_mb:.1f} MB in {time.time() - t0:.1f}s")
    print("\nBuild complete.")


if __name__ == '__main__':
    main()
