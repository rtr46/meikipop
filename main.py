# main.py
import sys
import threading
import time
import signal
import os
from multiprocessing import freeze_support
from typing import Optional, List
import math

from pynput import keyboard, mouse
from PIL import Image
import mss

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox, QLabel
from PyQt6.QtCore import pyqtSignal, QObject, QRect, Qt
from PyQt6.QtGui import QIcon, QCursor

from settings import settings, APP_NAME
from glens import GoogleLensOcr, ProcessedParagraph, WritingDirection
from lookup import Lookup, DictionaryEntry
from popup import Popup
from gui import RegionSelector, SettingsWindow

class MainApp(QObject):
    popup_update_signal = pyqtSignal(list)
    popup_move_signal = pyqtSignal(int, int)

    def __init__(self, scan_rect_physical: QRect | None):
        super().__init__()
        self.scan_rect = scan_rect_physical
        self.is_processing_update = threading.Lock()
        self.last_lookup_result = None
        self.last_displayed_entries = None
        self._stop_event = threading.Event()
        
        self.cached_paragraphs: Optional[List[ProcessedParagraph]] = None
        self.cached_image_dims: Optional[tuple[int, int]] = None
        
        self.lookup = Lookup()
        self.ocr_engine = GoogleLensOcr()
        
        self.popup1 = Popup()
        self.popup2 = Popup()
        self.front_popup = self.popup1
        self.back_popup = self.popup2
        
        self.popup_update_signal.connect(self._update_popup_slot)
        self.popup_move_signal.connect(self._move_popup_slot)
        
        self.setup_listeners()

	# warmup qt
        self.popup_update_signal.emit([DictionaryEntry(1,'見','み',[['see']],'')])
        self.popup_update_signal.emit([DictionaryEntry(2,'見','み',[['see']],'')])
        self.popup_update_signal.emit([])
    
    def setup_listeners(self):
        self.hotkey_pressed = False
        self.target_hotkey_set = {
            'shift': {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
            'ctrl': {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
            'alt': {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r},
        }.get(settings.hotkey)
        
        if hasattr(self, 'mouse_listener') and self.mouse_listener.is_alive():
            self.mouse_listener.stop()
        if hasattr(self, 'keyboard_listener') and self.keyboard_listener.is_alive():
            self.keyboard_listener.stop()
            
        self.mouse_listener = mouse.Listener(on_move=self.on_mouse_move)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
    
    def stop(self):
        self._stop_event.set()
        if hasattr(self, 'mouse_listener'): self.mouse_listener.stop()
        if hasattr(self, 'keyboard_listener'): self.keyboard_listener.stop()

    def _update_popup_slot(self, entries):
        if not self.hotkey_pressed and not entries:
            self.front_popup.hide(); self.back_popup.hide()
            return
        
        pos = QCursor.pos()
        logical_x, logical_y = pos.x(), pos.y()

        if not entries:
            self.front_popup.hide()
        else:
            self.back_popup.update_content(entries)
            self.back_popup.move_to(logical_x, logical_y)
            self.front_popup.hide()
            self.back_popup.show()
            self.front_popup, self.back_popup = self.back_popup, self.front_popup
    
    def _move_popup_slot(self, logical_x, logical_y):
        if self.front_popup.isVisible():
            self.front_popup.move_to(logical_x, logical_y)

    def _perform_lookup_at_position(self, x_physical, y_physical):
        if not self.is_processing_update.acquire(blocking=False): return
        try:
            if not self.cached_paragraphs or not self.cached_image_dims:
                return

            img_w, img_h = self.cached_image_dims
            relative_x = x_physical - self.scan_rect.x() if self.scan_rect else x_physical
            relative_y = y_physical - self.scan_rect.y() if self.scan_rect else y_physical
            norm_x, norm_y = relative_x / img_w, relative_y / img_h

            def is_in_box(point, box):
                if not box: return False
                px, py = point
                half_w, half_h = box.width / 2, box.height / 2
                return (box.center_x - half_w <= px <= box.center_x + half_w) and \
                       (box.center_y - half_h <= py <= box.center_y + half_h)

            ocr_result = None
            for para in self.cached_paragraphs:
                if not is_in_box((norm_x, norm_y), para.bounding_box):
                    continue

                target_word = None
                for word in para.words:
                    if is_in_box((norm_x, norm_y), word.box):
                        target_word = word
                        break
                
                if not target_word:
                    continue

                char_offset = 0
                is_vertical = para.writing_direction == WritingDirection.TOP_TO_BOTTOM
                
                if is_vertical:
                    if target_word.box.height > 0:
                        top_edge = target_word.box.center_y - (target_word.box.height / 2)
                        relative_y_in_box = norm_y - top_edge
                        char_percent = max(0.0, min(relative_y_in_box / target_word.box.height, 1.0))
                        char_offset = int(char_percent * len(target_word.text))
                else: # Horizontal
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
                ocr_result = (full_text, final_char_index, character, lookup_string)
                break 

            if ocr_result and ocr_result == self.last_lookup_result:
                pos = QCursor.pos()
                self.popup_move_signal.emit(pos.x(), pos.y())
                return
            
            self.last_lookup_result = ocr_result
            if not ocr_result:
                self.last_displayed_entries = None
                self.popup_update_signal.emit([])
                return
            
            text, char_pos, char, lookup_string = ocr_result

            truncated_text = (text[:40] + '...') if len(text) > 40 else text
            settings.user_log(f"  -> Looking up '{char}' in text: \"{truncated_text}\"")

            entries = self.lookup.generate_entries(text, char_pos, char, lookup_string)
            
            if entries == self.last_displayed_entries:
                pos = QCursor.pos()
                self.popup_move_signal.emit(pos.x(), pos.y())
                return
                
            self.last_displayed_entries = entries
            self.popup_update_signal.emit(entries)
        finally:
            if self.is_processing_update.locked():
                self.is_processing_update.release()

    def _scan_and_process_ocr(self, screenshot, x_physical, y_physical):
        processed_paragraphs = self.ocr_engine.scan_and_process(screenshot)
        self.cached_paragraphs = processed_paragraphs
        self.cached_image_dims = (screenshot.width, screenshot.height)
        if processed_paragraphs and self.hotkey_pressed:
            self._perform_lookup_at_position(x_physical, y_physical)

    def on_key_press(self, key):
        if key in self.target_hotkey_set and not self.hotkey_pressed:
            settings.user_log(f"Hotkey '{settings.hotkey}' pressed.")
            self.hotkey_pressed = True
            self.cached_paragraphs = None
            screenshot = self.take_screenshot()
            if not screenshot:
                self.hotkey_pressed = False
                return
            x_physical, y_physical = mouse.Controller().position
            
            threading.Thread(
                target=self._scan_and_process_ocr, 
                args=(screenshot, x_physical, y_physical), 
                daemon=True
            ).start()
            
    def on_key_release(self, key):
        if key in self.target_hotkey_set and self.hotkey_pressed:
            settings.user_log(f"Hotkey '{settings.hotkey}' released.")
            self.hotkey_pressed = False
            self.last_lookup_result = None
            self.last_displayed_entries = None
            self.cached_paragraphs = None
            self.cached_image_dims = None
            self.popup_update_signal.emit([])
            
    def on_mouse_move(self, x_physical, y_physical):
        if self.hotkey_pressed:
            threading.Thread(
                target=self._perform_lookup_at_position,
                args=(x_physical, y_physical),
                daemon=True
            ).start()
            
    def take_screenshot(self) -> Image.Image | None:
        with mss.mss() as sct:
            if self.scan_rect:
                monitor = {"top": self.scan_rect.y(), "left": self.scan_rect.x(), "width": self.scan_rect.width(), "height": self.scan_rect.height()}
                if monitor["width"] <= 0 or monitor["height"] <= 0: return None
            else:
                monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    
    def reselect_scan_region(self):
        logical_rect = RegionSelector.get_region()
        if logical_rect:
            app = QApplication.instance()
            screen = app.screenAt(logical_rect.center())
            scale = screen.devicePixelRatio() if screen else app.primaryScreen().devicePixelRatio()
            
            self.scan_rect = QRect(
                int(logical_rect.x() * scale), int(logical_rect.y() * scale),
                int(logical_rect.width() * scale), int(logical_rect.height() * scale)
            )
            settings.scan_region = 'region'
        else:
            settings.user_log("Region reselection cancelled.")
            
    def switch_to_fullscreen(self):
        self.scan_rect = None
        settings.scan_region = 'screen'
        settings.user_log("Switched to full-screen scan mode.")

    def show_settings(self):
        settings.user_log("Opening Settings window...")
        dialog = SettingsWindow()
        dialog.exec()
        self.setup_listeners()

if __name__ == '__main__':
    freeze_support()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main_app_instance = None
    try:
        settings.user_log(f"{APP_NAME} is starting...")
        qt_app = QApplication(sys.argv)
        qt_app.setQuitOnLastWindowClosed(False)

        if not os.path.exists("icon.ico"):
            QMessageBox.critical(None, "Error", f"{APP_NAME} requires 'icon.ico' to be in the same directory."); sys.exit(1)
            
        scan_rect_physical = None
        if settings.scan_region == 'region':
            logical_rect = RegionSelector.get_region()
            if not logical_rect:
                sys.exit(0)
            
            screen = qt_app.screenAt(logical_rect.center())
            scale = screen.devicePixelRatio() if screen else qt_app.primaryScreen().devicePixelRatio()
            scan_rect_physical = QRect(
                int(logical_rect.x() * scale), int(logical_rect.y() * scale),
                int(logical_rect.width() * scale), int(logical_rect.height() * scale)
            )
        
        main_app_instance = MainApp(scan_rect_physical=scan_rect_physical)
        
        tray_icon = QSystemTrayIcon(QIcon("icon.ico"), parent=qt_app)
        tray_icon.setToolTip(f"{APP_NAME}")
        
        menu = QMenu()
        menu.addAction("Settings").triggered.connect(main_app_instance.show_settings)
        menu.addAction("Reselect Region").triggered.connect(main_app_instance.reselect_scan_region)
        menu.addAction("Use Full Screen Scan").triggered.connect(main_app_instance.switch_to_fullscreen)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(lambda: (settings.user_log("Exiting..."), qt_app.quit()))
        
        tray_icon.setContextMenu(menu)
        tray_icon.show()
        
        hotkey_name = settings.hotkey.upper()
        ready_message = f"""
--------------------------------------------------
{APP_NAME} is running in the background.

  - To use: Press and hold '{hotkey_name}' over Japanese text.
  - To configure: Right-click the icon in your system tray.
  - To exit: Press Ctrl+C in this terminal.

--------------------------------------------------
"""
        print(ready_message)
        
        sys.exit(qt_app.exec())
        
    except Exception as e:
        settings.user_log(f"An unhandled exception occurred: {e}")
        QMessageBox.critical(None, "Critical Error", f"An unhandled exception occurred:\n{e}\n\nPlease check the console for details.")
    finally:
        if main_app_instance: main_app_instance.stop()