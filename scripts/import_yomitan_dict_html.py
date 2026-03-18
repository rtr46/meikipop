"""
import_yomitan_dict_html.py
Imports one or more Yomitan/Yomichan dictionary zip files and produces a
dictionary.pkl in the same format as build_dictionary.py.

Usage:
    python import_yomitan.py dict1.zip [dict2.zip ...] [-o output.pkl]

Multiple zips are merged into one pickle.  Entry IDs are namespaced by
dictionary index to avoid collisions.

Structured-content definitions are converted to Qt-compatible HTML at import
time so the popup can render lists, tables, bold/italic, colour, and ruby
annotations
"""

import argparse
import json
import os
import pickle
import re
import sys
import time
import zipfile
from collections import defaultdict
from typing import Optional

DATA_DIR = 'data'
DEFAULT_OUTPUT = 'dictionary.pkl'
DECONJUGATOR_PATH = os.path.join(DATA_DIR, 'deconjugator.json')
DEFAULT_FREQ = 999_999

# Each dictionary's entry IDs start at this multiple of its index (0-based).
# Allows up to 10 million entries per dictionary before collision.
ID_NAMESPACE = 10_000_000

# ── Structured-content -> Qt HTML conversion ──────────────────────────────────

# Yomitan style object keys -> CSS property names.
# Only properties Qt's rich-text engine honours are included.
_STYLE_MAP = {
    'fontWeight': 'font-weight',
    'fontStyle': 'font-style',
    'fontSize': 'font-size',
    'color': 'color',
    'textDecorationLine': 'text-decoration',
    'verticalAlign': 'vertical-align',
    'textAlign': 'text-align',
    'marginTop': 'margin-top',
    'marginBottom': 'margin-bottom',
    'listStyleType': 'list-style-type',
}

# Tags Qt's QLabel renders natively; passed through with style conversion.
_BLOCK_TAGS = {'div', 'ol', 'ul', 'li', 'table', 'thead', 'tbody', 'tfoot',
               'tr', 'details', 'summary'}
_INLINE_TAGS = {'span', 'td', 'th'}


def _style_to_css(style_obj: dict) -> str:
    """Convert a yomitan style dict to an inline CSS string for Qt."""
    parts = []
    for k, v in style_obj.items():
        css_prop = _STYLE_MAP.get(k)
        if css_prop and isinstance(v, str):
            parts.append(f'{css_prop}:{v}')
    return ';'.join(parts)


def _esc(text: str) -> str:
    """Minimal HTML escaping for plain text nodes."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _ruby_to_html(content) -> str:
    """
    Convert a <ruby> node to Qt HTML using option 4:
    collect all base (rb/span) text and all <rt> text, then produce:
        base_text（rt_text）
    The reading is appended only when rt text is present.
    Works well at small font sizes because it avoids superscript layout.
    """
    base_parts: list = []
    rt_parts: list = []

    nodes = content if isinstance(content, list) else ([content] if content else [])
    for child in nodes:
        if not isinstance(child, dict):
            if child:
                base_parts.append(_esc(str(child)))
            continue
        tag = child.get('tag', '')
        if tag == 'rt':
            rt_parts.append(_node_to_html(child.get('content')))
        elif tag == 'rp':
            pass  # skip — we supply our own brackets
        else:
            base_parts.append(_node_to_html(child))

    base = ''.join(base_parts)
    rt = ''.join(rt_parts).strip()
    return f'{base}（{rt}）' if rt else base


def _node_to_html(node) -> str:
    """
    Recursively convert a structured-content node to Qt-compatible HTML.

    Supported:
      plain strings           -> HTML-escaped text
      arrays                  -> children concatenated
      br                      -> <br>
      ruby/rt/rp              -> base（reading） via _ruby_to_html
      span, div, ol, ul, li   -> passed through with inline CSS
      table, tr, td, th etc.  -> passed through (Qt supports basic tables)
      details, summary        -> passed through (Qt renders text, ignores state)
      img                     -> replaced with italicised alt text if available
      unknown tags            -> content rendered, tag wrapper dropped
    """
    if node is None:
        return ''
    if isinstance(node, str):
        return _esc(node)
    if isinstance(node, list):
        return ''.join(_node_to_html(child) for child in node)
    if not isinstance(node, dict):
        return ''

    tag = node.get('tag', '')
    content = node.get('content')
    style = node.get('style', {})

    if tag == 'img':
        alt = node.get('alt') or node.get('title') or ''
        return f'<i>{_esc(alt)}</i>' if alt else ''

    if tag == 'ruby':
        return _ruby_to_html(content)

    if tag in ('rt', 'rp'):
        return ''

    if tag == 'br':
        return '<br>'

    inner = _node_to_html(content)
    css = _style_to_css(style) if style else ''
    style_attr = f' style="{css}"' if css else ''

    if tag in _BLOCK_TAGS or tag in _INLINE_TAGS:
        return f'<{tag}{style_attr}>{inner}</{tag}>'

    # Unknown tag: drop wrapper, keep content
    return inner


def to_html(definition: dict) -> str:
    """
    Convert a single {type:'structured-content', content:...} definition
    object to a Qt-compatible HTML string.
    """
    html = _node_to_html(definition.get('content'))
    # Collapse runs of spaces introduced by adjacent block elements
    html = re.sub(r' {2,}', ' ', html)
    return html.strip()


def extract_glosses(definitions: list) -> list:
    """
    Convert a yomitan definitions array to a list of gloss strings.

    - Plain strings and {type:'text'}      -> HTML-escaped plain text
    - {type:'structured-content'}          -> Qt HTML string
    - {type:'image'} and deinflection arrays -> skipped

    Each definition object produces exactly one gloss string so that
    popup.py's glosses[0] always yields the full content of that definition.
    In show_all_glosses mode the strings are joined with '; ' which degrades
    gracefully since Qt renders block elements correctly either way.
    """
    glosses = []
    for defn in definitions:
        if isinstance(defn, str):
            text = defn.strip()
            if text:
                glosses.append(_esc(text))
        elif isinstance(defn, dict):
            t = defn.get('type')
            if t == 'text':
                text = defn.get('text', '').strip()
                if text:
                    glosses.append(_esc(text))
            elif t == 'structured-content':
                html = to_html(defn)
                if html:
                    glosses.append(html)
            # type == 'image': not renderable outside the zip, skip silently
        elif isinstance(defn, list):
            # Deinflection entry [uninflected_term, [rules]] -- skip
            pass
    return glosses


# ── Frequency parsing ──────────────────────────────────────────────────────────

def parse_freq_value(freq_data) -> Optional[int]:
    """
    Extract a numeric frequency rank from a yomitan freq meta value.
    Returns None if the value cannot be interpreted as a rank.
    """
    if isinstance(freq_data, (int, float)):
        return int(freq_data)
    if isinstance(freq_data, str):
        try:
            return int(freq_data)
        except ValueError:
            return None
    if isinstance(freq_data, dict):
        if 'value' in freq_data:
            return int(freq_data['value'])
        inner = freq_data.get('frequency')
        if inner is not None:
            return parse_freq_value(inner)
    return None


def load_freq_map_from_zip(zf: zipfile.ZipFile) -> dict:
    """
    Read all term_meta_bank_*.json files and build:
      {(term, reading_or_empty): freq_rank}
    Takes the minimum (best) rank seen for each key.
    """
    freq: dict = {}
    for name in sorted(zf.namelist()):
        if not re.match(r'term_meta_bank_\d+\.json', os.path.basename(name)):
            continue
        with zf.open(name) as f:
            rows = json.load(f)
        for row in rows:
            if len(row) < 3 or row[1] != 'freq':
                continue
            term = row[0]
            raw = row[2]
            reading = ''
            if isinstance(raw, dict) and 'reading' in raw:
                reading = raw['reading']
                rank_val = parse_freq_value(raw.get('frequency'))
            else:
                rank_val = parse_freq_value(raw)
            if rank_val is None:
                continue
            key = (term, reading)
            if key not in freq or rank_val < freq[key]:
                freq[key] = rank_val
    return freq


# ── Term bank loading ──────────────────────────────────────────────────────────

def load_term_banks_from_zip(zf: zipfile.ZipFile) -> list:
    """Return all rows from term_bank_*.json files, preserving order."""
    rows = []
    for name in sorted(zf.namelist()):
        if not re.match(r'term_bank_\d+\.json', os.path.basename(name)):
            continue
        with zf.open(name) as f:
            rows.extend(json.load(f))
    return rows


# ── Building the internal structures ──────────────────────────────────────────

def _has_kanji(text: str) -> bool:
    return any(0x4E00 <= ord(c) <= 0x9FFF for c in text)


def build_from_zip(zf: zipfile.ZipFile, dict_index: int, freq_override: dict) -> tuple:
    """
    Process one zip file and return (entries, lookup_map_additions).

    entries:              {entry_id: [sense, ...]}
    lookup_map_additions: {surface: [(written_form, reading, freq, entry_id), ...]}

    dict_index namespaces entry IDs: entry_id = dict_index * ID_NAMESPACE + sequence.
    freq_override is merged in (unused in standalone mode, kept for future additive use).
    """
    freq_map = load_freq_map_from_zip(zf)
    for k, v in freq_override.items():
        if k not in freq_map or v < freq_map[k]:
            freq_map[k] = v

    rows = load_term_banks_from_zip(zf)
    print(f"    {len(rows)} term rows loaded")

    # Group rows by sequence number.
    # sequence > 0: rows sharing a number form one entry.
    # sequence == 0: each row is its own standalone entry.
    seq_groups: dict = defaultdict(list)
    standalone_counter = -1
    for row in rows:
        if len(row) < 6:
            continue
        seq = row[6] if len(row) > 6 else 0
        if seq == 0:
            seq_groups[standalone_counter].append(row)
            standalone_counter -= 1
        else:
            seq_groups[seq].append(row)

    entries = {}
    lookup_map = defaultdict(list)
    id_base = dict_index * ID_NAMESPACE

    for seq, group_rows in seq_groups.items():
        entry_id = id_base + (ID_NAMESPACE + seq) if seq < 0 else id_base + seq

        first_row = group_rows[0]
        canon_term = first_row[0]
        canon_read = first_row[1]  # empty string if kana-only

        senses = []
        for row in group_rows:
            def_tags_str = row[2] if len(row) > 2 else ''
            rules_str = row[3] if len(row) > 3 else ''
            definitions = row[5] if len(row) > 5 else []
            term_tags_str = row[7] if len(row) > 7 else ''

            glosses = extract_glosses(definitions)
            if not glosses:
                continue

            all_tag_strings = (def_tags_str + ' ' + term_tags_str).split()
            tags = [t for t in all_tag_strings if t]
            pos = [r for r in rules_str.split() if r]

            senses.append({'glosses': glosses, 'pos': pos, 'tags': tags})

        if not senses:
            continue

        entries[entry_id] = senses

        def get_freq(term: str, reading: str) -> int:
            return freq_map.get((term, reading),
                                freq_map.get((term, ''), DEFAULT_FREQ))

        seen_terms: set = set()
        seen_readings: set = set()

        for row in group_rows:
            term = row[0]
            reading = row[1]  # '' means kana-only

            # Kanji-path entry
            if _has_kanji(term) and term not in seen_terms:
                seen_terms.add(term)
                display_read = reading if reading else canon_read
                freq = get_freq(term, display_read)
                lookup_map[term].append((canon_term, display_read, freq, entry_id))

            # Kana-path entry
            surface_kana = reading if reading else term
            if surface_kana not in seen_readings:
                seen_readings.add(surface_kana)
                if reading:
                    freq = get_freq(surface_kana, reading)
                    lookup_map[surface_kana].append((canon_term, reading, freq, entry_id))
                else:
                    freq = get_freq(term, '')
                    lookup_map[term].append((term, None, freq, entry_id))

    n_refs = sum(len(v) for v in lookup_map.values())
    print(f"    {len(entries)} entries | {n_refs} lookup refs")
    return entries, lookup_map


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Import Yomitan dictionary zip(s) into dictionary.pkl')
    parser.add_argument('zips', nargs='+', help='Path(s) to Yomitan .zip files')
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT,
                        help=f'Output pickle path (default: {DEFAULT_OUTPUT})')
    args = parser.parse_args()

    if not os.path.exists(DECONJUGATOR_PATH):
        print(f"ERROR: {DECONJUGATOR_PATH} not found. "
              f"Please place deconjugator.json in the data/ folder.", file=sys.stderr)
        sys.exit(1)
    with open(DECONJUGATOR_PATH, 'r', encoding='utf-8') as f:
        deconjugator_rules = [r for r in json.load(f) if isinstance(r, dict)]
    print(f"Loaded {len(deconjugator_rules)} deconjugator rules")

    all_entries: dict = {}
    all_lookup_map: dict = defaultdict(list)

    for i, zip_path in enumerate(args.zips):
        if not os.path.isfile(zip_path):
            print(f"ERROR: File not found: {zip_path}", file=sys.stderr)
            sys.exit(1)

        print(f"\n[{i + 1}/{len(args.zips)}] Importing {os.path.basename(zip_path)} ...")
        t0 = time.time()

        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'index.json' in zf.namelist():
                with zf.open('index.json') as f:
                    idx = json.load(f)
                print(f"    Title:    {idx.get('title', '(unknown)')}")
                print(f"    Revision: {idx.get('revision', '(unknown)')}")
                print(f"    Author:   {idx.get('author', '(unknown)')}")

            entries, lookup_additions = build_from_zip(zf, dict_index=i, freq_override={})

        all_entries.update(entries)
        for surface, me_list in lookup_additions.items():
            all_lookup_map[surface].extend(me_list)

        print(f"    Done in {time.time() - t0:.1f}s")

    print(f"\nTotal: {len(all_entries)} entries, "
          f"{sum(len(v) for v in all_lookup_map.values())} lookup refs")

    print(f"\nSaving to {args.output} ...")
    t0 = time.time()
    payload = {
        'entries': all_entries,
        'lookup_map': dict(all_lookup_map),
        'kanji_entries': {},
        'deconjugator_rules': deconjugator_rules,
    }
    with open(args.output, 'wb') as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    size_mb = os.path.getsize(args.output) / 1_048_576
    print(f"Saved {size_mb:.1f} MB in {time.time() - t0:.1f}s")
    print("\nImport complete.")


if __name__ == '__main__':
    main()
