"""
import_yomitan_dict_html.py
Imports one or more Yomitan/Yomichan dictionary zip files and produces a
dictionary.pkl in the same format as build_dictionary.py.

Usage:
    python import_yomitan_dict_html.py dict1.zip [dict2.zip ...] [-o output.pkl] [--no-ruby]

Multiple zips are merged into one pickle. Entry IDs are namespaced by dictionary
index to avoid collisions.

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
ID_NAMESPACE = 10_000_000

# ── Qt CSS property support map ───────────────────────────────────────────────
#
# Derived from https://doc.qt.io/qt-6/richtext-html-subset.html
#
# Qt applies CSS to two distinct formatting layers:
#   QTextCharFormat  — character-level, works on ANY element including span
#   QTextBlockFormat — block-level, only meaningful on block elements (div, p…)
#
# A third category covers border properties which Qt ONLY supports on table
# and table-cell elements. On spans/divs they are silently ignored by Qt, so
# we handle them separately with a bracket fallback.

# Character-level: valid on any element
_CHAR_MAP = {
    'fontWeight': 'font-weight',
    'fontStyle': 'font-style',
    'fontSize': 'font-size',
    'color': 'color',
    'backgroundColor': 'background-color',
    'textDecorationLine': 'text-decoration',
    'fontFamily': 'font-family',
    'textTransform': 'text-transform',
    'fontVariant': 'font-variant',
    'whiteSpace': 'white-space',
    'lineHeight': 'line-height',
    'wordSpacing': 'word-spacing',
}

# vertical-align: Qt only supports these values; others (text-bottom, text-top)
# are silently ignored, so we filter to the supported set.
_VERTICAL_ALIGN_SUPPORTED = {
    'baseline', 'sub', 'super', 'middle', 'top', 'bottom'
}

# Block-level: only meaningful on block elements (div, p, li, etc.)
# Qt ignores these when set on a span.
_BLOCK_MAP = {
    'marginTop': 'margin-top',
    'marginBottom': 'margin-bottom',
    'marginLeft': 'margin-left',
    'marginRight': 'margin-right',
    'padding': 'padding',
    'paddingTop': 'padding-top',
    'paddingBottom': 'padding-bottom',
    'paddingLeft': 'padding-left',
    'paddingRight': 'padding-right',
    'textAlign': 'text-align',
    'textIndent': 'text-indent',
}

# Border properties: Qt only supports these on table / td / th.
# On any other element we fall back to [bracket] notation.
_BORDER_KEYS = {'borderStyle', 'borderWidth', 'borderColor'}

# Tags that carry block formatting
_BLOCK_TAGS = {
    'div', 'ol', 'ul', 'li', 'details', 'summary',
    'table', 'thead', 'tbody', 'tfoot', 'tr',
}
# Tags that carry inline/character formatting
_INLINE_TAGS = {'span'}
# Table cell tags — can have Qt borders
_CELL_TAGS = {'td', 'th'}
# All tags we render (unknown tags get their wrapper dropped)
_RENDERED_TAGS = _BLOCK_TAGS | _INLINE_TAGS | _CELL_TAGS


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ── CSS builder ────────────────────────────────────────────────────────────────

def _style_to_props(style_obj: dict) -> tuple[dict, dict, bool]:
    """
    Split a yomitan style object into:
      char_props  — character-level CSS {prop: value}
      block_props — block-level CSS {prop: value}
      has_border  — True if any border sub-property is present
    """
    char_props: dict = {}
    block_props: dict = {}
    has_border = False

    for k, v in style_obj.items():
        if not isinstance(v, str):
            continue
        if k in _CHAR_MAP:
            css_prop = _CHAR_MAP[k]
            if css_prop == 'vertical-align':
                if v in _VERTICAL_ALIGN_SUPPORTED:
                    char_props[css_prop] = v
            else:
                char_props[css_prop] = v
        elif k in _BLOCK_MAP:
            block_props[_BLOCK_MAP[k]] = v
        elif k in _BORDER_KEYS:
            has_border = True
        # anything else (border-radius, cursor, display, flex, …) → silently dropped

    return char_props, block_props, has_border


def _synthesize_border(style_obj: dict) -> str:
    """
    Build a `border: width style color` shorthand from individual sub-properties.
    Returns an empty string if none are present.
    """
    width = style_obj.get('borderWidth', '1px')
    style = style_obj.get('borderStyle', 'solid')
    color = style_obj.get('borderColor', '')
    if style_obj.get('borderStyle') or style_obj.get('borderWidth'):
        return f'border:{width} {style} {color}'.rstrip()
    return ''


def _props_to_css(props: dict) -> str:
    return ';'.join(f'{k}:{v}' for k, v in props.items())


# ── Structured-content → Qt HTML converter ────────────────────────────────────

class StructuredContentConverter:
    """
    Converts a yomitan structured-content tree to Qt-compatible HTML.

    Design principles:
      - Only emit CSS Qt can actually render (see maps above)
      - Collapse no-op wrappers aggressively to keep HTML small
      - Border on non-table elements → [bracket] fallback
      - Ruby: configurable via use_ruby flag
    """

    def __init__(self, use_ruby: bool = True):
        self.use_ruby = use_ruby

    # ── Ruby ──────────────────────────────────────────────────────────────

    def _ruby_to_html(self, content) -> str:
        """
        Option 4: collect base text and all rt text, produce base（rt）.
        When use_ruby is False, only the base text is returned.
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
                if self.use_ruby:
                    rt_parts.append(self._node_to_html(child.get('content')))
            elif tag == 'rp':
                pass
            else:
                base_parts.append(self._node_to_html(child))

        base = ''.join(base_parts)
        if self.use_ruby:
            rt = ''.join(rt_parts).strip()
            return f'{base}（{rt}）' if rt else base
        return base

    # ── Anchor ────────────────────────────────────────────────────────────

    def _anchor_to_html(self, node: dict) -> str:
        """
        Cross-reference links: extract data.alt text if present (e.g. ［例］,
        ［対］), otherwise render inner content. Qt cannot follow
        dictionary-internal hrefs so we never emit a live <a> tag.
        """
        content = node.get('content')

        def find_alt(n) -> str:
            if isinstance(n, list):
                for child in n:
                    r = find_alt(child)
                    if r:
                        return r
            elif isinstance(n, dict):
                data = n.get('data', {})
                alt = data.get('alt', '') if isinstance(data, dict) else ''
                if alt:
                    return alt
                return find_alt(n.get('content'))
            return ''

        alt = find_alt(content)
        if alt:
            return _esc(alt)
        return self._node_to_html(content)

    # ── Main converter ────────────────────────────────────────────────────

    def _node_to_html(self, node) -> str:  # noqa: C901
        if node is None:
            return ''
        if isinstance(node, str):
            return _esc(node)
        if isinstance(node, list):
            return ''.join(self._node_to_html(child) for child in node)
        if not isinstance(node, dict):
            return ''

        tag = node.get('tag', '')
        content = node.get('content')
        style = node.get('style', {})

        # ── Special tags handled before style resolution ─────────────────

        if tag == 'img':
            alt = node.get('alt') or node.get('title') or ''
            return f'<i>{_esc(alt)}</i>' if alt else ''

        if tag == 'ruby':
            return self._ruby_to_html(content)

        if tag in ('rt', 'rp'):
            return ''  # consumed inside _ruby_to_html

        if tag == 'br':
            return '<br>'

        if tag == 'a':
            return self._anchor_to_html(node)

        # ── Render inner content first ────────────────────────────────────
        inner = self._node_to_html(content)

        # ── No-op wrapper collapsing ──────────────────────────────────────
        # If a span or div carries no style and no data, it is a structural
        # no-op. Drop the wrapper entirely to keep the HTML lean.
        # We still process the children above so inner is always correct.
        if not style and tag in ('span', 'div'):
            data = node.get('data', {})
            if not (isinstance(data, dict) and data):
                return inner

        # ── Style resolution ─────────────────────────────────────────────
        char_props, block_props, has_border = _style_to_props(style)

        if tag in _CELL_TAGS:
            # Table cells: synthesize border shorthand (Qt supports it here)
            border_css = _synthesize_border(style)
            if not border_css:
                border_css = 'border:1px solid'  # default so table is legible
            cell_props = {**char_props, **block_props}
            cell_props['border'] = border_css.split(':', 1)[1]  # just the value
            # Rebuild properly
            all_props = {**char_props, **block_props, 'border': border_css.split(':', 1)[1]}
            css = _props_to_css(all_props)

        elif tag == 'table':
            border_css = _synthesize_border(style)
            all_props = {**char_props, **block_props}
            if border_css:
                all_props['border'] = border_css.split(':', 1)[1]
            css = _props_to_css(all_props)

        elif tag in _BLOCK_TAGS:
            css = _props_to_css({**char_props, **block_props})

        else:
            # span and unknown inline tags: only char-level
            css = _props_to_css(char_props)

        # ── Border fallback for non-table elements ────────────────────────
        # Qt ignores border-* on spans/divs. Signal the border visually by
        # wrapping the content in square brackets instead.
        if has_border and tag not in _CELL_TAGS and tag != 'table':
            inner = f'[{inner}]'

        style_attr = f' style="{css}"' if css else ''

        if tag in _RENDERED_TAGS:
            return f'<{tag}{style_attr}>{inner}</{tag}>'

        # Unknown tag: drop wrapper, keep content
        return inner

    # ── Public API ────────────────────────────────────────────────────────

    def to_html(self, definition: dict) -> str:
        """
        Convert a {type:'structured-content', content:...} object to
        Qt-compatible HTML. Collapses runs of spaces left by block elements.
        """
        html = self._node_to_html(definition.get('content'))
        html = re.sub(r' {2,}', ' ', html)
        return html.strip()

    def extract_glosses(self, definitions: list) -> list:
        """
        Convert a yomitan definitions array to gloss strings.
          plain string / {type:'text'}     → HTML-escaped plain text
          {type:'structured-content'}      → Qt HTML
          {type:'image'} / deinflection    → skipped
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
                    html = self.to_html(defn)
                    if html:
                        glosses.append(html)
            # deinflection arrays and image-only entries: skip
        return glosses


# ── Frequency parsing ──────────────────────────────────────────────────────────

def parse_freq_value(freq_data) -> Optional[int]:
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
    """Build {(term, reading_or_empty): rank} from term_meta_bank_*.json files."""
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


def build_from_zip(
        zf: zipfile.ZipFile,
        dict_index: int,
        freq_override: dict,
        converter: StructuredContentConverter,
) -> tuple:
    """
    Process one zip and return (entries, lookup_map_additions).

    entries:              {entry_id: [sense, ...]}
    lookup_map_additions: {surface: [(written_form, reading, freq, entry_id), ...]}
    """
    freq_map = load_freq_map_from_zip(zf)
    for k, v in freq_override.items():
        if k not in freq_map or v < freq_map[k]:
            freq_map[k] = v

    rows = load_term_banks_from_zip(zf)
    print(f"    {len(rows)} term rows loaded")

    # Group rows by sequence number.
    # sequence > 0 → rows sharing a number form one entry.
    # sequence == 0 → each row is its own standalone entry.
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
        canon_read = first_row[1]

        senses = []
        for row in group_rows:
            def_tags_str = row[2] if len(row) > 2 else ''
            rules_str = row[3] if len(row) > 3 else ''
            definitions = row[5] if len(row) > 5 else []
            term_tags_str = row[7] if len(row) > 7 else ''

            glosses = converter.extract_glosses(definitions)
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
            reading = row[1]

            if _has_kanji(term) and term not in seen_terms:
                seen_terms.add(term)
                display_read = reading if reading else canon_read
                freq = get_freq(term, display_read)
                lookup_map[term].append((canon_term, display_read, freq, entry_id))

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
    parser.add_argument('--no-ruby', dest='ruby', action='store_false', default=True,
                        help='Strip furigana (ruby) annotations from definitions')
    args = parser.parse_args()

    if not os.path.exists(DECONJUGATOR_PATH):
        print(f"ERROR: {DECONJUGATOR_PATH} not found. "
              f"Please place deconjugator.json in the data/ folder.", file=sys.stderr)
        sys.exit(1)
    with open(DECONJUGATOR_PATH, 'r', encoding='utf-8') as f:
        deconjugator_rules = [r for r in json.load(f) if isinstance(r, dict)]
    print(f"Loaded {len(deconjugator_rules)} deconjugator rules")
    if not args.ruby:
        print("Ruby annotations disabled (--no-ruby)")

    converter = StructuredContentConverter(use_ruby=args.ruby)

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

            entries, lookup_additions = build_from_zip(
                zf, dict_index=i, freq_override={}, converter=converter)

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
