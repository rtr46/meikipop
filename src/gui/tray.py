# src/gui/tray.py
import os

from PyQt6.QtGui import QIcon, QActionGroup
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from src.config.config import APP_NAME, config
from src.gui.settings_dialog import SettingsDialog
from src.ocr.ocr import OcrProcessor


class TrayIcon(QSystemTrayIcon):
    def __init__(self, screen_manager, ocr_processor: OcrProcessor, parent=None):
        base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, '..', 'resources', 'icon.ico')

        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            # print(f"Warning: Custom icon not found at '{icon_path}'. Using default.")
            from PyQt6.QtWidgets import QStyle
            icon = QIcon(QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            ))
        super().__init__(icon, parent)

        self.screen_manager = screen_manager
        self.ocr_processor = ocr_processor

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
        def set_auto_mode(arg):
            config.auto_scan_mode = arg

        self.menu.addAction("Set manual scan mode").triggered.connect(lambda: set_auto_mode(False))
        self.menu.addAction("Set auto scan mode").triggered.connect(lambda: set_auto_mode(True))

        self.menu.addSeparator()

        # Scan Region Selection
        self.menu.addAction("Reselect Region").triggered.connect(screen_manager.set_scan_region)
        for screen_index, resolution in enumerate(screen_manager.get_screens()):
            self.menu.addAction(f"Scan screen {screen_index} {resolution['width']}x{resolution['height']}").triggered.connect(lambda checked, index=screen_index: screen_manager.set_scan_screen(index))

        self.menu.addSeparator()

        # Quit Action
        self.menu.addAction("Quit").triggered.connect(QApplication.instance().quit)
        
        self.setContextMenu(self.menu)
        self.setToolTip(APP_NAME)
        self.show()

    def _on_ocr_provider_selected(self, action):
        """Slot to handle changing the OCR provider from the tray menu's action group."""
        provider_name = action.text()
        if provider_name != config.ocr_provider:
            self.ocr_processor.switch_provider(provider_name)
            config.ocr_provider = provider_name
            config.save()

    def show_settings(self):
        settings_dialog = SettingsDialog(self.ocr_processor)
        settings_dialog.exec()
