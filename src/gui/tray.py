# src/gui/tray.py
import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from src.config.config import APP_NAME, config
from src.gui.settings_dialog import SettingsDialog


class TrayIcon(QSystemTrayIcon):
    def __init__(self, screen_manager, parent=None):
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

        self.menu = QMenu()
        
        # Settings Action
        self.menu.addAction("Settings").triggered.connect(self.show_settings)

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

        self.settings_dialog = None

    def show_settings(self):
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog()
        self.settings_dialog.exec()