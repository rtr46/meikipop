# gui.py
import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QDialog, QFormLayout, QComboBox, 
                             QSpinBox, QCheckBox, QPushButton, QColorDialog, QVBoxLayout, QHBoxLayout,
                             QGroupBox, QMessageBox, QDialogButtonBox, QLabel, QSlider)
from PyQt6.QtCore import QRect, Qt, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor, QMouseEvent, QKeyEvent, QIcon

from settings import settings, APP_NAME

THEMES = {
    "Nazeka": {
        "color_background": "#2E2E2E", "color_foreground": "#F0F0F0",
        "color_highlight_word": "#88D8FF", "color_highlight_reading": "#90EE90",
        "color_separator_line": "#444444", "background_opacity": 245,
    },
    "Celestial Indigo": {
        "color_background": "#281E50", "color_foreground": "#EAEFF5",
        "color_highlight_word": "#D4C58A", "color_highlight_reading": "#B5A2D4",
        "color_separator_line": "#444444", "background_opacity": 245,
    },
    "Neutral Slate": {
        "color_background": "#5D5C5B", "color_foreground": "#EFEBE8",
        "color_highlight_word": "#A3B8A3", "color_highlight_reading": "#A3B8A3",
        "color_separator_line": "#444444", "background_opacity": 245,
    },
    "Academic": {
        "color_background": "#FDFBF7", "color_foreground": "#212121",
        "color_highlight_word": "#8C2121", "color_highlight_reading": "#005A9C",
        "color_separator_line": "#D3D3D3", "background_opacity": 245,
    },
    "Custom": {}
}

class RegionSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.begin = QPoint()
        self.end = QPoint()
        self.selection_rect = None
    def paintEvent(self, event):
        painter = QPainter(self); painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if not self.begin.isNull() and not self.end.isNull():
            rect = QRect(self.begin, self.end).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(30, 200, 255), 2, Qt.PenStyle.SolidLine)); painter.drawRect(rect)
    def mousePressEvent(self, event: QMouseEvent):
        self.begin = event.position().toPoint(); self.end = self.begin; self.update()
    def mouseMoveEvent(self, event: QMouseEvent):
        self.end = event.position().toPoint(); self.update()
    def mouseReleaseEvent(self, event: QMouseEvent):
        self.selection_rect = QRect(self.begin, self.end).normalized(); self.accept()
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.selection_rect = None; self.reject()
    @staticmethod
    def get_region():
        settings.user_log("Awaiting region selection...")
        selector = RegionSelector()
        selector.exec()
        return selector.selection_rect

class SettingsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # --- MODIFIED: Use the correctly imported APP_NAME variable ---
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setWindowIcon(QIcon("icon.ico"))
        layout = QVBoxLayout(self)
        general_group = QGroupBox("General")
        general_layout = QFormLayout()
        self.hotkey_combo = QComboBox(); self.hotkey_combo.addItems(['shift', 'ctrl', 'alt']); self.hotkey_combo.setCurrentText(settings.hotkey)
        general_layout.addRow("Hotkey:", self.hotkey_combo)
        self.quality_combo = QComboBox(); self.quality_combo.addItems(['fast', 'balanced', 'quality']); self.quality_combo.setCurrentText(settings.quality_mode)
        general_layout.addRow("Quality Mode:", self.quality_combo)
        self.max_lookup_spin = QSpinBox(); self.max_lookup_spin.setRange(5, 100); self.max_lookup_spin.setValue(settings.max_lookup_length)
        general_layout.addRow("Max Lookup Length:", self.max_lookup_spin)
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setCurrentText(settings.theme_name if settings.theme_name in THEMES else "Custom")
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        theme_layout.addRow("Theme:", self.theme_combo)
        self.opacity_slider_container = QWidget()
        opacity_layout = QHBoxLayout(self.opacity_slider_container)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(settings.background_opacity)
        self.opacity_label = QLabel(f"{settings.background_opacity}")
        self.opacity_label.setMinimumWidth(30)
        self.opacity_slider.valueChanged.connect(lambda val: self.opacity_label.setText(str(val)))
        self.opacity_slider.valueChanged.connect(self._mark_as_custom)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        theme_layout.addRow("Background Opacity:", self.opacity_slider_container)
        theme_layout.addRow(QLabel("Customize Colors:"))
        self.color_widgets = {}
        color_settings_map = {"Background": "color_background", "Foreground": "color_foreground", "Highlight Word": "color_highlight_word", "Highlight Reading": "color_highlight_reading", "Separator": "color_separator_line"}
        for name, key in color_settings_map.items():
            btn = QPushButton(getattr(settings, key))
            btn.clicked.connect(lambda _, k=key, b=btn: self.pick_color(k, b))
            self.color_widgets[key] = btn
            theme_layout.addRow(f"  {name}:", btn)
        theme_layout.addRow(QLabel("Customize Layout:"))
        self.popup_width_spin = QSpinBox(); self.popup_width_spin.setRange(300, 2000); self.popup_width_spin.setValue(settings.popup_width)
        theme_layout.addRow("  Popup Width:", self.popup_width_spin)
        self.compact_check = QCheckBox(); self.compact_check.setChecked(settings.compact_mode)
        theme_layout.addRow("  Compact Mode:", self.compact_check)
        self.hide_deconj_check = QCheckBox(); self.hide_deconj_check.setChecked(settings.hide_deconjugation)
        theme_layout.addRow("  Hide Deconjugation:", self.hide_deconj_check)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_color_buttons()
    def _mark_as_custom(self):
        if self.theme_combo.currentText() != "Custom":
            self.theme_combo.setCurrentText("Custom")
    def _apply_theme(self, theme_name):
        if theme_name in THEMES and theme_name != "Custom":
            theme_data = THEMES[theme_name]
            for key, value in theme_data.items():
                setattr(settings, key, value)
            self._update_color_buttons()
            self.opacity_slider.setValue(settings.background_opacity)
    def _update_color_buttons(self):
        for key, btn in self.color_widgets.items():
            color_hex = getattr(settings, key)
            btn.setText(color_hex)
            q_color = QColor(color_hex)
            text_color = "#000000" if q_color.lightness() > 127 else "#FFFFFF"
            btn.setStyleSheet(f"background-color: {color_hex}; color: {text_color};")
    def pick_color(self, key, btn):
        color = QColorDialog.getColor(QColor(getattr(settings, key)), self)
        if color.isValid():
            setattr(settings, key, color.name())
            self._update_color_buttons()
            self._mark_as_custom()
    def save_and_accept(self):
        settings.hotkey = self.hotkey_combo.currentText()
        settings.quality_mode = self.quality_combo.currentText()
        settings.max_lookup_length = self.max_lookup_spin.value()
        settings.popup_width = self.popup_width_spin.value()
        settings.compact_mode = self.compact_check.isChecked()
        settings.hide_deconjugation = self.hide_deconj_check.isChecked()
        settings.theme_name = self.theme_combo.currentText()
        settings.background_opacity = self.opacity_slider.value()
        settings.save()
        QMessageBox.information(self, "Settings Saved", "Settings have been saved.\nPlease restart the application for all changes to take effect.")
        self.accept()