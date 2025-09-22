# src/ocr/hit_scan.py
import logging
import threading
from typing import List

from src.gui.magpie_manager import magpie_manager
from src.ocr.interface import Paragraph

logger = logging.getLogger(__name__)  # Get the logger


class HitScanner(threading.Thread):
    def __init__(self, shared_state, input_loop, screen_manager):
        super().__init__(daemon=True, name="HitScanner")
        self.shared_state = shared_state
        self.input_loop = input_loop
        self.screen_manager = screen_manager
        self.last_ocr_result = None

    def run(self):
        logger.debug("HitScanner thread started.")
        while self.shared_state.running:
            try:
                is_ocr_result_updated, new_ocr_result = self.shared_state.hit_scan_queue.get()
                if not self.shared_state.running: break
                logger.debug("HitScanner: Triggered")

                if is_ocr_result_updated:
                    self.last_ocr_result = new_ocr_result

                hit_scan_result = self.hit_scan(self.last_ocr_result) if self.last_ocr_result else None

                # Trigger the lookup
                self.shared_state.lookup_queue.put(hit_scan_result)
            except:
                logger.exception("An unexpected error occurred in the hit scan loop. Continuing...")
        logger.debug("HitScanner thread stopped.")

    def hit_scan(self, paragraphs: List[Paragraph]):
        mouse_x, mouse_y = magpie_manager.transform_raw_to_visual(self.input_loop.get_mouse_pos(), 1)
        mouse_off_x, mouse_off_y, img_w, img_h = self.screen_manager.get_scan_geometry()
        relative_x = mouse_x - mouse_off_x
        relative_y = mouse_y - mouse_off_y
        norm_x, norm_y = relative_x / img_w, relative_y / img_h

        def is_in_box(point, box):
            if not box: return False
            px, py = point
            half_w, half_h = box.width / 2, box.height / 2
            return (box.center_x - half_w <= px <= box.center_x + half_w) and \
                (box.center_y - half_h <= py <= box.center_y + half_h)

        def is_in_box_ex(point, box_before, box, box_after, is_vertical_flag):
            if not box: return False
            left = box.center_x - box.width / 2
            right = box.center_x + box.width / 2
            top = box.center_y - box.height / 2
            bottom = box.center_y + box.height / 2
            if not is_vertical_flag and box_before: left = min(left, box_before.center_x + box_before.width / 2)
            if not is_vertical_flag and box_after: right = max(right, box_after.center_x - box_after.width / 2)
            if is_vertical_flag and box_before: top = min(top, box_before.center_y + box_before.height / 2)
            if is_vertical_flag and box_after: bottom = max(bottom, box_after.center_y - box_after.height / 2)
            px, py = point
            return (left <= px <= right) and (top <= py <= bottom)

        hit_scan_result = None
        lookup_string = None
        for para in paragraphs:
            if not is_in_box((norm_x, norm_y), para.box):
                continue

            target_word = None
            is_vertical = para.is_vertical or para.box.height > para.box.width
            words = list(para.words)

            for i, word in enumerate(words):
                box_before = words[i - 1].box if i > 0 else None
                box_after = words[i + 1].box if i < len(words) - 1 else None
                if is_in_box_ex((norm_x, norm_y), box_before, word.box, box_after, is_vertical):
                    target_word = word
                    break

            if not target_word:
                continue

            char_offset = 0

            if is_vertical:
                if target_word.box.height > 0:
                    top_edge = target_word.box.center_y - (target_word.box.height / 2)
                    relative_y_in_box = norm_y - top_edge
                    char_percent = max(0.0, min(relative_y_in_box / target_word.box.height, 1.0))
                    char_offset = int(char_percent * len(target_word.text))
            else:  # Horizontal
                if target_word.box.width > 0:
                    left_edge = target_word.box.center_x - (target_word.box.width / 2)
                    relative_x_in_box = norm_x - left_edge
                    char_percent = max(0.0, min(relative_x_in_box / target_word.box.width, 1.0))
                    char_offset = int(char_percent * len(target_word.text))

            char_offset = min(char_offset, len(target_word.text) - 1)

            word_start_index = 0
            for word in para.words:
                if word is target_word:
                    break
                word_start_index += len(word.text)

            final_char_index = word_start_index + char_offset
            full_text = para.full_text

            if final_char_index >= len(full_text):
                continue

            character = full_text[final_char_index]
            lookup_string = full_text[final_char_index:]
            hit_scan_result = (full_text, final_char_index, character,
                               lookup_string)  # this may be interesting for debugging, but only lookup_string is really relevant
            break

        if hit_scan_result:
            text, char_pos, char, lookup_string = hit_scan_result
            truncated_text = (text[:40] + '...') if len(text) > 40 else text
        #     config.user_log(f"  -> Looking up '{char}' at pos {char_pos} in text: \"{truncated_text}\"")
        # else:
        #     config.user_log("hit scan unsuccessful")

        return lookup_string
