# meikipop/gui/tray.py
import os

from PyQt6.QtGui import QIcon, QAction, QActionGroup
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from meikipop.config.config import APP_NAME, config, IS_WINDOWS
from meikipop.gui.settings_dialog import SettingsDialog
from meikipop.gui.ocr_toggle import OcrToggle
from meikipop.ocr.ocr import OcrProcessor
from meikipop.utils.paths import paths
from meikipop.utils.console import console_manager


class TrayIcon(QSystemTrayIcon):
    def __init__(self, screen_manager, ocr_processor: OcrProcessor, popup_window, input_loop, lookup, parent=None):
        # Resolve icon paths using
        icon_path = paths.get_resource_path('icon.ico')
        icon_inactive_path = paths.get_resource_path('icon.inactive.ico')

        if os.path.exists(icon_path):
            self.icon = QIcon(icon_path)
            self.icon_inactive = QIcon(icon_inactive_path)
        else:
            # print(f"Warning: Custom icon not found at '{icon_path}'. Using default.")
            from PyQt6.QtWidgets import QStyle
            self.icon = QIcon(QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            ))
            self.icon_inactive = self.icon
        super().__init__(self.icon, parent)

        self.screen_manager = screen_manager
        self.ocr_processor = ocr_processor
        self.popup_window = popup_window
        self.input_loop = input_loop
        self.lookup = lookup
        self.scan_area_actions = []

        self.menu = QMenu()

        # Settings Action
        self.menu.addAction("Settings").triggered.connect(self.show_settings)

        self.menu.addSeparator()

        # OCR Provider Selection
        ocr_menu = self.menu.addMenu("OCR Provider")
        self.ocr_action_group = QActionGroup(self)
        self.ocr_action_group.setExclusive(True)
        self.ocr_action_group.triggered.connect(self._on_ocr_provider_selected)

        for provider_name in self.ocr_processor.available_providers.keys():
            action = ocr_menu.addAction(provider_name)
            action.setCheckable(True)
            if provider_name == config.ocr_provider:
                action.setChecked(True)
            self.ocr_action_group.addAction(action)

        self.menu.addSeparator()

        # Scan Mode Selection
        scan_mode_menu = self.menu.addMenu("Scan Mode")
        self.scan_mode_action_group = QActionGroup(self)
        self.scan_mode_action_group.setExclusive(True)
        self.scan_mode_action_group.triggered.connect(self._on_scan_mode_selected)

        manual_action = scan_mode_menu.addAction("Manual")
        manual_action.setCheckable(True)
        manual_action.setChecked(not config.auto_scan_mode)
        self.scan_mode_action_group.addAction(manual_action)

        auto_action = scan_mode_menu.addAction("Auto")
        auto_action.setCheckable(True)
        auto_action.setChecked(config.auto_scan_mode)
        self.scan_mode_action_group.addAction(auto_action)

        # Scan Area Selection
        scan_area_menu = self.menu.addMenu("Scan Area")
        self.scan_area_action_group = QActionGroup(self)
        self.scan_area_action_group.setExclusive(True)
        self.scan_area_action_group.triggered.connect(self._on_scan_area_selected)

        region_action = scan_area_menu.addAction("Custom Region")
        region_action.setCheckable(True)
        region_action.setData('region')
        self.scan_area_action_group.addAction(region_action)
        self.scan_area_actions.append(region_action)

        mouse_action = scan_area_menu.addAction("Screen Under Mouse")
        mouse_action.setCheckable(True)
        mouse_action.setData('mouse')
        mouse_action.setToolTip("Only scans the screen the mouse is on. Each screen keeps its last result.")
        self.scan_area_action_group.addAction(mouse_action)
        self.scan_area_actions.append(mouse_action)

        for i, res in enumerate(self.screen_manager.get_screens()):
            action = scan_area_menu.addAction(f"Screen {i} ({res['width']}x{res['height']})")
            action.setCheckable(True)
            action.setData(i)
            self.scan_area_action_group.addAction(action)
            self.scan_area_actions.append(action)

        self.update_scan_area_check()

        # Furigana Mode toggle
        self.furigana_action = self.menu.addAction("Furigana Mode")
        self.furigana_action.setCheckable(True)
        self.furigana_action.setChecked(config.furigana_mode)
        self.furigana_action.triggered.connect(self._on_furigana_mode_toggled)

        self.menu.addSeparator()

        self.enable_action = self.menu.addAction("Pause meikipop")
        self.enable_action.setCheckable(True)
        self.enable_action.triggered.connect(self.toggle_enabled_state)
        self.activated.connect(self.on_tray_activated)

        self.menu.addSeparator()

        # Console window toggle (only when meikipop owns its console, i.e. it wasn't started from a terminal)
        self.console_action = None
        if console_manager.can_toggle:
            self.console_action = self.menu.addAction("Show Console")
            self.console_action.setCheckable(True)
            self.console_action.setChecked(console_manager.is_visible())
            self.console_action.triggered.connect(self._on_console_toggled)
            self.menu.aboutToShow.connect(self._sync_console_action)

        self.menu.addAction("Quit").triggered.connect(QApplication.instance().quit)

        self.setContextMenu(self.menu)
        self.setToolTip(APP_NAME)

        self.ocr_toggle = OcrToggle(self.ocr_processor, on_switched=self.reapply_settings)

        self.prevent_ghost_icon_on_win()

        self.show()

    def on_tray_activated(self, reason):
        """Handles clicks on the tray icon."""
        # QSystemTrayIcon.ActivationReason.Trigger is the enum for a normal left-click.
        if reason == self.ActivationReason.Trigger:
            self.toggle_enabled_state()

    def toggle_enabled_state(self):
        """Toggles the enabled/paused state of the application."""
        self.enable_action.setChecked(config.is_enabled)
        config.is_enabled = not config.is_enabled
        if config.is_enabled:
            # App is active/unpaused
            self.setIcon(self.icon)
        else:
            # App is inactive/paused
            self.setIcon(self.icon_inactive)

    def update_scan_area_check(self):
        current_region = config.scan_region
        action_to_check = None
        for action in self.scan_area_actions:
            if str(action.data()) == str(current_region):
                action_to_check = action
                break

        if not action_to_check:
            # If no specific match is found, default to checking the 'Custom Region' action.
            action_to_check = self.scan_area_actions[0]

        action_to_check.setChecked(True)

    def _on_scan_mode_selected(self, action: QAction):
        is_auto = action.text() == "Auto"
        if is_auto != config.auto_scan_mode:
            config.auto_scan_mode = is_auto
            config.save()

    def _on_scan_area_selected(self, action: QAction):
        selected_id = action.data()
        if selected_id == 'region':
            if self.screen_manager.set_scan_region():
                if config.scan_region != 'region':
                    config.scan_region = 'region'
                    config.save()
            else:
                self.update_scan_area_check()
        elif selected_id == 'mouse':
            if config.scan_region != 'mouse':
                config.scan_region = 'mouse'
                self.screen_manager.set_scan_follow_mouse()
                config.save()
        else:  # It's a screen index
            index = int(selected_id)
            if str(index) != config.scan_region:
                self.screen_manager.set_scan_screen(index)
                config.scan_region = str(index)
                config.save()

    def _on_furigana_mode_toggled(self, checked):
        if checked != config.furigana_mode:
            config.furigana_mode = checked
            config.save()

    def _on_console_toggled(self, checked):
        if checked:
            console_manager.show()
        else:
            console_manager.hide()

    def _sync_console_action(self):
        if self.console_action:
            self.console_action.setChecked(console_manager.is_visible())

    def _on_ocr_provider_selected(self, action):
        provider_name = action.text()
        if provider_name != config.ocr_provider:
            self.ocr_processor.switch_provider(provider_name)

    def reapply_settings(self):
        """Updates the tray menu's checkmarks to reflect the current config."""
        # Update OCR Provider selection
        for action in self.ocr_action_group.actions():
            if action.text() == config.ocr_provider:
                action.setChecked(True)
                break

        if hasattr(self, 'ocr_toggle'):
            self.ocr_toggle.reapply_settings()

        self.furigana_action.setChecked(config.furigana_mode)

        # Update Scan Mode selection
        for action in self.scan_mode_action_group.actions():
            is_auto_action = action.text() == "Auto"
            if is_auto_action == config.auto_scan_mode:
                action.setChecked(True)
                break

    def show_settings(self):
        settings_dialog = SettingsDialog(self.ocr_processor, self.popup_window, self.input_loop, self.lookup, self)
        settings_dialog.exec()

    def prevent_ghost_icon_on_win(self):
        if IS_WINDOWS:
            import ctypes
            from ctypes import wintypes
            def win_console_handler(ctrl_type):
                # 2 = CTRL_CLOSE_EVENT (Closing the console window)
                if ctrl_type == 2:
                    try:
                        self.hide()
                    except:
                        pass
                    return False
                return False

            HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
            self._win_handler_ref = HandlerRoutine(win_console_handler)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(self._win_handler_ref, True)
