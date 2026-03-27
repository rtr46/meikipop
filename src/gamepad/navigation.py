# src/gamepad/navigation.py
#
# Owns the navigation state for gamepad-driven dictionary lookup.
#
# Responsibilities:
#   • Maintains a flat character map derived from the last OCR result
#   • Tracks current selection (character index)
#   • Computes word-boundary indices from SudachiPy tokens
#   • Updates input_loop.virtual_mouse_pos so the existing hit-scan and
#     popup positioning code work without modification
#   • Pushes lookup strings directly to shared_state.lookup_queue
#   • Drives the selection-highlight and furigana overlays
#
# Data flow when user presses d-pad right:
#   step_char(+1)
#     → _char_index += 1
#     → _update_virtual_cursor()   (sets input_loop.virtual_mouse_pos)
#     → _trigger_lookup()           (puts lookup_string on lookup_queue)
#     → _update_selection_overlay() (repaints the highlight box)
#
# Thread Safety:
#   All public methods may be called from the GamepadController thread.
#   Qt widget operations are queued to the main thread via signals.

import logging
from typing import List, Optional, Tuple, Dict

from PyQt6.QtCore import QObject, pyqtSignal
from src.ocr.interface import Paragraph, Word

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

# A single slot in the flat character map.
# Fields: char, para_index, paragraph, word, char_in_para_fulltext, char_in_word
_CharEntry = Tuple[str, int, Paragraph, Word, int, int]


class NavigationState(QObject):
    """
    Coordinates between the gamepad controller and the rest of the app.

    Uses Qt signals to ensure all Qt widget operations happen on the main thread.
    """

    # Signals for thread-safe communication with overlays
    # Each carries the data needed by the respective overlay method
    selection_changed = pyqtSignal(object, int, int, int, int)  # box, off_x, off_y, img_w, img_h
    furigana_updated = pyqtSignal(list)  # list of furigana items
    furigana_hidden = pyqtSignal()
    selection_hidden = pyqtSignal()

    def __init__(self, shared_state, input_loop,
                 overlay_selection, overlay_furigana,
                 screen_manager):
        super().__init__()
        self.shared_state = shared_state
        self.input_loop = input_loop
        self.overlay_selection = overlay_selection
        self.overlay_furigana = overlay_furigana
        self.screen_manager = screen_manager

        # Connect signals to overlay slots for thread-safe communication
        self.selection_changed.connect(self._on_selection_changed)
        self.furigana_updated.connect(self._on_furigana_updated)
        self.furigana_hidden.connect(self._on_furigana_hidden)
        self.selection_hidden.connect(self._on_selection_hidden)

        # Set by HitScanner whenever a new OCR result arrives
        self._paragraphs: Optional[List[Paragraph]] = None

        # Flat list of character entries across all paragraphs
        self._char_map: List[_CharEntry] = []

        # Current position in _char_map
        self._char_index: int = 0

        # Sorted list of global char-map indices at which new tokens start
        self._word_boundaries: List[int] = []

        # Per-paragraph token lists from SudachiPy
        self._para_tokens: Dict[int, list] = {}  # para_idx → List[Token]

        # Whether the furigana overlay should be shown in nav mode
        self._furigana_active: bool = False

    # ------------------------------------------------------------------
    # Signal handlers (slots) - these run on the main thread
    # ------------------------------------------------------------------

    def _on_selection_changed(self, box, off_x, off_y, img_w, img_h):
        """Slot: handle selection change on main thread"""
        self.overlay_selection.set_selection(box, off_x, off_y, img_w, img_h)

    def _on_furigana_updated(self, items):
        """Slot: handle furigana update on main thread"""
        self.overlay_furigana.set_furigana(items)
        self.overlay_furigana.show_overlay()

    def _on_furigana_hidden(self):
        """Slot: handle furigana hide on main thread"""
        self.overlay_furigana.hide_overlay()

    def _on_selection_hidden(self):
        """Slot: handle selection hide on main thread"""
        self.overlay_selection.hide_overlay()

    # ------------------------------------------------------------------
    # Public interface called by GamepadController
    # ------------------------------------------------------------------

    def on_new_ocr_result(self, paragraphs: Optional[List[Paragraph]]):
        """
        Called by HitScanner whenever a fresh OCR result is available.
        Rebuilds the char map so subsequent navigation is up to date.
        """
        self._paragraphs = paragraphs
        self._build_char_map()

        # If already in nav mode and furigana is on, refresh the overlay
        if self.input_loop.gamepad_navigation_active and self._furigana_active:
            self._refresh_furigana_overlay()

    def on_enter(self):
        """
        Called by GamepadController when the user enters navigation mode.
        Snaps the selection to the character nearest to the current mouse pos.
        """
        if not self._char_map:
            logger.debug("NavigationState.on_enter: no OCR result yet – nothing to navigate.")
            return

        mouse_pos = self.input_loop.get_raw_mouse_pos()
        nearest = self._find_nearest_char_index(mouse_pos)
        self._char_index = nearest if nearest is not None else 0

        self._update_virtual_cursor()
        self._trigger_lookup()
        self._update_selection_overlay()

        if self._furigana_active:
            self._refresh_furigana_overlay()

    def on_exit(self):
        """Called by GamepadController when the user exits navigation mode."""
        # Emit signals for thread-safe Qt operations
        self.selection_hidden.emit()
        if self._furigana_active:
            self.furigana_hidden.emit()
        # Clear the virtual cursor so normal mouse control resumes
        self.input_loop.virtual_mouse_pos = None

    def step_char(self, delta: int):
        """Move the selection by *delta* characters (±1)."""
        if not self._char_map:
            return
        new_idx = max(0, min(len(self._char_map) - 1, self._char_index + delta))
        if new_idx == self._char_index:
            return
        self._char_index = new_idx
        self._update_virtual_cursor()
        self._trigger_lookup()
        self._update_selection_overlay()

    def step_word(self, delta: int):
        """
        Jump to the start of the next (+1) or previous (-1) parser token.
        Falls back to character stepping when the parser is unavailable.
        """
        if not self._word_boundaries:
            self.step_char(delta)
            return

        # Find which boundary bucket the current index sits in
        boundaries = self._word_boundaries
        current = self._char_index

        if delta > 0:
            # Jump to the first boundary strictly greater than current
            target = next((b for b in boundaries if b > current), boundaries[-1])
        else:
            # Jump to the last boundary strictly less than current
            preceding = [b for b in boundaries if b < current]
            target = preceding[-1] if preceding else boundaries[0]

        if target == self._char_index:
            return
        self._char_index = target
        self._update_virtual_cursor()
        self._trigger_lookup()
        self._update_selection_overlay()

    def toggle_furigana(self):
        """Toggle the furigana overlay on/off (called by gamepad Y button)."""
        self._furigana_active = not self._furigana_active
        if self._furigana_active:
            self._refresh_furigana_overlay()
        else:
            # Emit signal for thread-safe Qt operation
            self.furigana_hidden.emit()

    # ------------------------------------------------------------------
    # Internal: char map construction
    # ------------------------------------------------------------------

    def _build_char_map(self):
        """
        Rebuild the flat character map and word-boundary list from
        the current list of OCR paragraphs.
        """
        self._char_map = []
        self._para_tokens = {}
        self._word_boundaries = []

        if not self._paragraphs:
            return

        # ---- Build char map -------------------------------------------
        for para_idx, para in enumerate(self._paragraphs):
            char_pos_in_fulltext = 0
            for word in para.words:
                for i, ch in enumerate(word.text):
                    entry: _CharEntry = (
                        ch,
                        para_idx,
                        para,
                        word,
                        char_pos_in_fulltext + i,  # absolute offset in para.full_text
                        i,  # offset within this word's text
                    )
                    self._char_map.append(entry)
                # Advance past both word text and its separator so
                # char_pos_in_fulltext stays aligned with para.full_text
                char_pos_in_fulltext += len(word.text) + len(word.separator)

        # ---- Parse tokens for word boundaries -------------------------
        self._parse_all_paragraphs()

        # ---- Build (para_idx, char_in_para) → global_index lookup ----
        char_map_lookup: Dict[Tuple[int, int], int] = {}
        for global_i, entry in enumerate(self._char_map):
            _, para_idx, _, _, char_in_para, _ = entry
            char_map_lookup[(para_idx, char_in_para)] = global_i

        # ---- Map token starts to global indices -----------------------
        boundaries = []
        for para_idx, tokens in self._para_tokens.items():
            for token in tokens:
                key = (para_idx, token.char_start)
                if key in char_map_lookup:
                    boundaries.append(char_map_lookup[key])

        self._word_boundaries = sorted(set(boundaries))

        # Clamp current index in case the new result is shorter
        if self._char_map:
            self._char_index = min(self._char_index, len(self._char_map) - 1)

    def _parse_all_paragraphs(self):
        """Parse each paragraph with SudachiPy. Silently skips if unavailable."""
        try:
            from src.parser.furigana import get_tokens, is_available
            if not is_available():
                return
            for para_idx, para in enumerate(self._paragraphs):
                tokens = get_tokens(para.full_text)
                if tokens:
                    self._para_tokens[para_idx] = tokens
        except Exception as exc:
            logger.debug("_parse_all_paragraphs failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal: cursor + lookup
    # ------------------------------------------------------------------

    def _update_virtual_cursor(self):
        """
        Compute the screen pixel coordinates of the selected character
        and store them in input_loop.virtual_mouse_pos.  The popup and
        hit-scan code will use this position for all subsequent queries.
        """
        pos = self._char_index_to_screen_pos(self._char_index)
        if pos:
            self.input_loop.virtual_mouse_pos = pos

    def _trigger_lookup(self):
        """
        Slice the paragraph full_text from the selected character onwards
        and push it directly onto the lookup queue, bypassing HitScanner.
        """
        if not self._char_map or self._char_index >= len(self._char_map):
            return
        _, _, para, _, char_in_para, _ = self._char_map[self._char_index]
        lookup_string = para.full_text[char_in_para:]
        self.shared_state.lookup_queue.put(lookup_string)

    def _char_index_to_screen_pos(self, idx: int) -> Optional[Tuple[int, int]]:
        """
        Convert a char-map index to an absolute screen pixel coordinate
        by interpolating within the word's bounding box.
        """
        if not self._char_map or idx >= len(self._char_map):
            return None

        _, _, para, word, _, char_in_word = self._char_map[idx]
        off_x, off_y, img_w, img_h = self.screen_manager.get_scan_geometry()
        if img_w == 0 or img_h == 0:
            return None

        box = word.box
        n_chars = max(len(word.text), 1)
        frac = (char_in_word + 0.5) / n_chars  # fractional position within word

        if para.is_vertical:
            norm_x = box.center_x
            norm_y = box.center_y - box.height / 2 + frac * box.height
        else:
            norm_x = box.center_x - box.width / 2 + frac * box.width
            norm_y = box.center_y

        return (int(off_x + norm_x * img_w), int(off_y + norm_y * img_h))

    def _find_nearest_char_index(self, screen_pos: Tuple[int, int]) -> Optional[int]:
        """Return the index of the character closest to *screen_pos*."""
        if not self._char_map:
            return None

        off_x, off_y, img_w, img_h = self.screen_manager.get_scan_geometry()
        if img_w == 0 or img_h == 0:
            return 0

        norm_x = (screen_pos[0] - off_x) / img_w
        norm_y = (screen_pos[1] - off_y) / img_h

        best_idx, best_dist = 0, float('inf')
        for i, (_, _, para, word, _, char_in_word) in enumerate(self._char_map):
            box = word.box
            n_chars = max(len(word.text), 1)
            frac = (char_in_word + 0.5) / n_chars
            if para.is_vertical:
                cx = box.center_x
                cy = box.center_y - box.height / 2 + frac * box.height
            else:
                cx = box.center_x - box.width / 2 + frac * box.width
                cy = box.center_y
            dist = (norm_x - cx) ** 2 + (norm_y - cy) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        return best_idx

    # ------------------------------------------------------------------
    # Internal: overlay updates (thread-safe Qt invocation)
    # ------------------------------------------------------------------

    def _update_selection_overlay(self):
        """Tell the selection overlay which word box to highlight."""
        if not self._char_map or self._char_index >= len(self._char_map):
            return
        _, _, para, word, _, _ = self._char_map[self._char_index]
        off_x, off_y, img_w, img_h = self.screen_manager.get_scan_geometry()
        # Emit signal for thread-safe Qt operation
        self.selection_changed.emit(word.box, off_x, off_y, img_w, img_h)

    def _refresh_furigana_overlay(self):
        """
        Recompute furigana positions from current OCR result + parser tokens
        and push them to the overlay widget for repainting.
        """
        if not self._paragraphs:
            return

        off_x, off_y, img_w, img_h = self.screen_manager.get_scan_geometry()
        if img_w == 0 or img_h == 0:
            return

        furigana_items = []  # list of (sx, sy, sw, sh, reading, is_vertical)

        for para_idx, para in enumerate(self._paragraphs):
            tokens = self._para_tokens.get(para_idx)
            if not tokens:
                continue

            # Build word → global char start lookup for this paragraph
            word_char_starts: List[int] = []
            pos = 0
            for word in para.words:
                word_char_starts.append(pos)
                pos += len(word.text) + len(word.separator)

            word_list = list(para.words)

            for token in tokens:
                if token.is_kana or not token.reading:
                    continue

                # Find the first word that contains token.char_start
                for wi, word in enumerate(word_list):
                    w_start = word_char_starts[wi]
                    w_end = w_start + len(word.text)
                    if w_start <= token.char_start < w_end:
                        box = word.box
                        sx = int(off_x + (box.center_x - box.width / 2) * img_w)
                        sy = int(off_y + (box.center_y - box.height / 2) * img_h)
                        sw = int(box.width * img_w)
                        sh = int(box.height * img_h)
                        furigana_items.append(
                            (sx, sy, sw, sh, token.reading, para.is_vertical)
                        )
                        break

        # Emit signal for thread-safe Qt operation
        self.furigana_updated.emit(furigana_items)
