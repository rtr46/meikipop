# src/ocr/hitdetector.py
import threading

from src.ocr.lens_betterproto import WritingDirection

class HitDetector(threading.Thread):
    def __init__(self, shared_state):
        super().__init__(daemon=True, name="HitDetector")
        self.shared_state = shared_state

    def run(self):
        # print("HitDetector thread started.")
        while self.shared_state.running:
            if self.shared_state.lock.acquire(blocking=False):
                try:
                    self.shared_state.cv_hit_detector.wait_for(lambda: self.shared_state.trigger_hit_detection)
                    if not self.shared_state.running: break

                    #print("hitdetection started")

                    self.hit_detection()

                    # Trigger the lookup
                    self.shared_state.trigger_lookup = True
                    self.shared_state.cv_lookup.notify()
                finally:  # todo add exception logging in all threads
                    self.shared_state.trigger_hit_detection = False
                    self.shared_state.lock.release()
        # print("HitDetector thread stopped.")


    def hit_detection(self):
        paragraphs = self.shared_state.ocr_results
        image = self.shared_state.screenshot_data
        if not paragraphs or not image:
            return

        img_w, img_h = self.shared_state.screenshot_data.size
        mouse_x, mouse_y = self.shared_state.mouse_pos
        mouse_off_x, mouse_off_y = self.shared_state.mouse_offset
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

        hit_detection_result = None
        for para in paragraphs:
            if not is_in_box((norm_x, norm_y), para.bounding_box):
                continue

            target_word = None
            is_vertical = para.writing_direction == WritingDirection.TOP_TO_BOTTOM
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
                word_start_index += len(word.text) + len(word.separator)

            final_char_index = word_start_index + char_offset
            full_text = para.full_text

            if final_char_index >= len(full_text):
                continue

            character = full_text[final_char_index]
            lookup_string = full_text[final_char_index:]
            hit_detection_result = (full_text, final_char_index, character, lookup_string)
            break

        self.shared_state.hit_result = hit_detection_result

        if hit_detection_result:
            text, char_pos, char, lookup_string = hit_detection_result
            truncated_text = (text[:40] + '...') if len(text) > 40 else text
        #     config.user_log(f"  -> Looking up '{char}' at pos {char_pos} in text: \"{truncated_text}\"")
        # else:
        #     config.user_log("hit detection unsuccessful")