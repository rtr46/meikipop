# src/gui/settings_dialog.py
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QIcon, QFontDatabase, QDesktopServices
from PyQt6.QtWidgets import (QWidget, QDialog, QFormLayout, QComboBox,
                             QSpinBox, QCheckBox, QPushButton, QColorDialog, QVBoxLayout, QHBoxLayout,
                             QGroupBox, QDialogButtonBox, QLabel, QSlider, QDoubleSpinBox,
                             QTabWidget, QSizePolicy, QFontComboBox)

from src.dictionary.lookup import Lookup
from src.config.config import config, APP_NAME, IS_WINDOWS
from src.gui.input import InputLoop
from src.gui.popup import Popup
from src.ocr.ocr import OcrProcessor

THEMES = {
    "Nazeka": {
        "color_background": "#2E2E2E", "color_foreground": "#F0F0F0",
        "color_highlight_word": "#88D8FF", "color_highlight_reading": "#90EE90",
        "background_opacity": 245,
    },
    "Celestial Indigo": {
        "color_background": "#281E50", "color_foreground": "#EAEFF5",
        "color_highlight_word": "#D4C58A", "color_highlight_reading": "#B5A2D4",
        "background_opacity": 245,
    },
    "Neutral Slate": {
        "color_background": "#5D5C5B", "color_foreground": "#EFEBE8",
        "color_highlight_word": "#A3B8A3", "color_highlight_reading": "#A3B8A3",
        "background_opacity": 245,
    },
    "Academic": {
        "color_background": "#FDFBF7", "color_foreground": "#212121",
        "color_highlight_word": "#8C2121", "color_highlight_reading": "#005A9C",
        "background_opacity": 245,
    },
    "Custom": {}
}

# Xbox-style button labels for the combo boxes in the Gamepad tab
_BUTTON_OPTIONS = [
    ("A (0)", 0), ("B (1)", 1), ("X (2)", 2), ("Y (3)", 3),
    ("LB (4)", 4), ("RB (5)", 5), ("Back (6)", 6), ("Start (7)", 7),
    ("L3 (8)", 8), ("R3 (9)", 9),
]


class SettingsDialog(QDialog):
    def __init__(self, ocr_processor: OcrProcessor, popup_window: Popup, input_loop: InputLoop, lookup: Lookup,
                 tray_icon, gamepad_controller=None, parent=None):
        super().__init__(parent)
        self.ocr_processor = ocr_processor
        self.popup_window = popup_window
        self.input_loop = input_loop
        self.tray_icon = tray_icon
        self.lookup = lookup
        self.gamepad_controller = gamepad_controller

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setWindowIcon(QIcon("icon.ico"))
        self.setMinimumWidth(420)

        # Keep track of all form layouts to unify their spacing later
        self.form_layouts = []

        # Main vertical layout for the Dialog
        main_layout = QVBoxLayout(self)

        # Create the Tab Widget
        self.tabs = QTabWidget()

        # ==========================================
        # TAB 1: General
        # ==========================================
        self.tab_general = QWidget()
        self.tab_general_layout = QVBoxLayout(self.tab_general)

        # --- Group 1: Core Settings ---
        core_group = QGroupBox("Core Settings")
        core_layout = QFormLayout()
        self.form_layouts.append(core_layout)

        self.hotkey_combo = QComboBox()
        self.hotkey_combo.addItems(['ctrl', 'shift', 'alt', 'ctrl+shift', 'ctrl+alt', 'shift+alt', 'ctrl+shift+alt'])
        self.hotkey_combo.setCurrentText(config.hotkey)
        self._set_expanding(self.hotkey_combo)
        core_layout.addRow("Hotkey:", self.hotkey_combo)

        self.ocr_provider_combo = QComboBox()
        self.ocr_provider_combo.addItems(self.ocr_processor.available_providers.keys())
        self.ocr_provider_combo.setCurrentText(config.ocr_provider)
        self.ocr_provider_combo.currentTextChanged.connect(self._update_glens_state)
        self._set_expanding(self.ocr_provider_combo)
        core_layout.addRow("OCR Provider:", self.ocr_provider_combo)

        # Google Lens specific option
        self.glens_compression_check_label = QLabel("Google Lens Compression:")
        self.glens_compression_check = QCheckBox()
        self.glens_compression_check.setChecked(config.glens_low_bandwidth)
        self.glens_compression_check.setToolTip(
            "Compresses screenshots before sending them to Google Lens\nSignificantly improves ocr latency on slow internet connections, but slightly worsens ocr accuracy and system load"
        )
        core_layout.addRow(self.glens_compression_check_label, self.glens_compression_check)

        self.max_lookup_spin = QSpinBox()
        self.max_lookup_spin.setRange(5, 100)
        self.max_lookup_spin.setValue(config.max_lookup_length)
        core_layout.addRow("Max Lookup Length:", self.max_lookup_spin)

        if IS_WINDOWS:
            self.magpie_check = QCheckBox()
            self.magpie_check.setChecked(config.magpie_compatibility)
            self.magpie_check.setToolTip("Enable transformations for compatibility with Magpie game scaler.")
            core_layout.addRow("Magpie Compatibility:", self.magpie_check)

        core_group.setLayout(core_layout)
        self.tab_general_layout.addWidget(core_group)

        # --- Group 2: Auto Scan Mode ---
        auto_group = QGroupBox("Auto Scan Mode")
        auto_layout = QFormLayout()
        self.form_layouts.append(auto_layout)

        self.auto_scan_check = QCheckBox()
        self.auto_scan_check.setChecked(config.auto_scan_mode)
        self.auto_scan_check.setToolTip(
            "Permanently ocr screen region\nImproves perceived latency, but worsens system load")
        self.auto_scan_check.toggled.connect(self._update_auto_scan_state)
        auto_layout.addRow("Enable Auto Scan:", self.auto_scan_check)

        self.auto_scan_mouse_move_check_label = QLabel("Only Scan on Mouse Move:")
        self.auto_scan_mouse_move_check = QCheckBox()
        self.auto_scan_mouse_move_check.setChecked(config.auto_scan_on_mouse_move)
        self.auto_scan_mouse_move_check.setToolTip(
            "Prevents auto ocr to occur, if mouse is not moved\nCan reduce system load, but worsen perceived latency")
        auto_layout.addRow(self.auto_scan_mouse_move_check_label, self.auto_scan_mouse_move_check)

        self.auto_scan_interval_spin_label = QLabel("Scan Interval (Cooldown):")
        self.auto_scan_interval_spin = QDoubleSpinBox()
        self.auto_scan_interval_spin.setRange(0.0, 60.0)
        self.auto_scan_interval_spin.setDecimals(1)
        self.auto_scan_interval_spin.setSingleStep(0.1)
        self.auto_scan_interval_spin.setValue(config.auto_scan_interval_seconds)
        self.auto_scan_interval_spin.setSuffix(" s")
        self.auto_scan_interval_spin.setToolTip(
            "Prevents auto ocr to occur with a high frequency\nCan reduce system load, but worsens perceived latency")
        auto_layout.addRow(self.auto_scan_interval_spin_label, self.auto_scan_interval_spin)

        self.auto_scan_no_hotkey_check_label = QLabel("Show Popup without Hotkey:")
        self.auto_scan_no_hotkey_check = QCheckBox()
        self.auto_scan_no_hotkey_check.setChecked(config.auto_scan_mode_lookups_without_hotkey)
        auto_layout.addRow(self.auto_scan_no_hotkey_check_label, self.auto_scan_no_hotkey_check)

        auto_group.setLayout(auto_layout)
        self.tab_general_layout.addWidget(auto_group)

        # --- Group 3: Popup Behavior ---
        behavior_group = QGroupBox("Popup Behavior")
        behavior_layout = QFormLayout()
        self.form_layouts.append(behavior_layout)

        self.popup_position_combo = QComboBox()
        self.popup_position_combo.addItems(["Flip Both", "Flip Vertically", "Flip Horizontally", "Visual Novel Mode"])
        self.popup_mode_map = {
            "Flip Both": "flip_both",
            "Flip Vertically": "flip_vertically",
            "Flip Horizontally": "flip_horizontally",
            "Visual Novel Mode": "visual_novel_mode"
        }
        current_friendly_name = next(
            (k for k, v in self.popup_mode_map.items() if v == config.popup_position_mode), "Flip Vertically"
        )
        self.popup_position_combo.setCurrentText(current_friendly_name)
        self._set_expanding(self.popup_position_combo)
        behavior_layout.addRow("Position Mode:", self.popup_position_combo)

        self.compact_check = QCheckBox()
        self.compact_check.setChecked(config.compact_mode)
        behavior_layout.addRow("Compact Mode:", self.compact_check)

        behavior_group.setLayout(behavior_layout)
        self.tab_general_layout.addWidget(behavior_group)
        self.tab_general_layout.addStretch()

        # ==========================================
        # TAB 2: Popup Content
        # ==========================================
        self.tab_content = QWidget()
        self.tab_content_layout = QVBoxLayout(self.tab_content)

        # --- Group 1: Vocab Entry Content ---
        vocab_group = QGroupBox("Vocab Entry Content")
        vocab_layout = QFormLayout()
        self.form_layouts.append(vocab_layout)

        self.show_glosses_check = QCheckBox()
        self.show_glosses_check.setChecked(config.show_all_glosses)
        vocab_layout.addRow("Show All Glosses:", self.show_glosses_check)

        self.show_deconj_check = QCheckBox()
        self.show_deconj_check.setChecked(config.show_deconjugation)
        vocab_layout.addRow("Show Deconjugation:", self.show_deconj_check)

        self.show_pos_check = QCheckBox()
        self.show_pos_check.setChecked(config.show_pos)
        vocab_layout.addRow("Show Part of Speech:", self.show_pos_check)

        self.show_tags_check = QCheckBox()
        self.show_tags_check.setChecked(config.show_tags)
        vocab_layout.addRow("Show Tags:", self.show_tags_check)

        self.show_frequency_check = QCheckBox()
        self.show_frequency_check.setChecked(config.show_frequency)
        vocab_layout.addRow("Show Frequency:", self.show_frequency_check)

        vocab_group.setLayout(vocab_layout)
        self.tab_content_layout.addWidget(vocab_group)

        # --- Group 2: Kanji Entry Content ---
        kanji_group = QGroupBox("Kanji Entry Content")
        kanji_layout = QFormLayout()
        self.form_layouts.append(kanji_layout)

        self.show_kanji_check = QCheckBox()
        self.show_kanji_check.setChecked(config.show_kanji)
        self.show_kanji_check.toggled.connect(self._update_kanji_options_state)
        kanji_layout.addRow("Show Kanji Entries:", self.show_kanji_check)

        self.show_examples_check = QCheckBox()
        self.show_examples_check.setChecked(config.show_examples)
        kanji_layout.addRow("Show Examples:", self.show_examples_check)

        self.show_components_check = QCheckBox()
        self.show_components_check.setChecked(config.show_components)
        kanji_layout.addRow("Show Components:", self.show_components_check)

        kanji_group.setLayout(kanji_layout)
        self.tab_content_layout.addWidget(kanji_group)
        self.tab_content_layout.addStretch()

        # ==========================================
        # TAB 3: Popup Appearance
        # ==========================================
        self.tab_appearance = QWidget()
        self.tab_appearance_layout = QVBoxLayout(self.tab_appearance)

        # --- Group 1: Theme ---
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout()
        self.form_layouts.append(theme_layout)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.setCurrentText(config.theme_name if config.theme_name in THEMES else "Custom")
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        self._set_expanding(self.theme_combo)
        theme_layout.addRow("Preset:", self.theme_combo)

        self.opacity_slider_container = QWidget()
        opacity_layout = QHBoxLayout(self.opacity_slider_container)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(config.background_opacity)
        self.opacity_label = QLabel(f"{config.background_opacity}")
        self.opacity_label.setMinimumWidth(30)
        self.opacity_slider.valueChanged.connect(lambda val: self.opacity_label.setText(str(val)))
        self.opacity_slider.valueChanged.connect(self._mark_as_custom)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        theme_layout.addRow("Background Opacity:", self.opacity_slider_container)

        theme_group.setLayout(theme_layout)
        self.tab_appearance_layout.addWidget(theme_group)

        # --- Group 2: Typography ---
        typo_group = QGroupBox("Typography")
        typo_layout = QFormLayout()
        self.form_layouts.append(typo_layout)

        self.font_family_combo = QFontComboBox()
        self.font_family_combo.setWritingSystem(QFontDatabase.WritingSystem.Japanese)
        self._set_expanding(self.font_family_combo)
        default_font_name = self.font().family()
        if self.font_family_combo.findText(default_font_name) == -1:
            self.font_family_combo.insertItem(0, default_font_name)
        target_font_name = config.font_family if config.font_family else default_font_name
        index = self.font_family_combo.findText(target_font_name)
        if index != -1:
            self.font_family_combo.setCurrentIndex(index)
        else:
            self.font_family_combo.setCurrentText(default_font_name)
        typo_layout.addRow("Font Family:", self.font_family_combo)

        self.font_size_header_spin = QSpinBox()
        self.font_size_header_spin.setRange(8, 72)
        self.font_size_header_spin.setValue(config.font_size_header)
        typo_layout.addRow("Font Size (Header):", self.font_size_header_spin)

        self.font_size_def_spin = QSpinBox()
        self.font_size_def_spin.setRange(8, 72)
        self.font_size_def_spin.setValue(config.font_size_definitions)
        typo_layout.addRow("Font Size (Definitions):", self.font_size_def_spin)

        typo_group.setLayout(typo_layout)
        self.tab_appearance_layout.addWidget(typo_group)

        # --- Group 3: Colors ---
        color_group = QGroupBox("Colors")
        color_layout = QFormLayout()
        self.form_layouts.append(color_layout)

        self.color_widgets = {}
        color_settings_map = {"Background": "color_background", "Foreground": "color_foreground",
                              "Highlight Word": "color_highlight_word", "Highlight Reading": "color_highlight_reading"}
        for name, key in color_settings_map.items():
            btn = QPushButton(getattr(config, key))
            btn.clicked.connect(lambda _, k=key, b=btn: self.pick_color(k, b))
            self.color_widgets[key] = btn
            color_layout.addRow(f"{name}:", btn)

        color_group.setLayout(color_layout)
        self.tab_appearance_layout.addWidget(color_group)
        self.tab_appearance_layout.addStretch()

        # ==========================================
        # TAB 4: Gamepad
        # ==========================================
        self.tab_gamepad = QWidget()
        self.tab_gamepad_layout = QVBoxLayout(self.tab_gamepad)
        self._build_gamepad_tab()

        # ---- Add all tabs ---
        self.tabs.addTab(self.tab_general, "General")
        self.tabs.addTab(self.tab_content, "Popup Content")
        self.tabs.addTab(self.tab_appearance, "Popup Appearance")
        self.tabs.addTab(self.tab_gamepad, "Gamepad")
        main_layout.addWidget(self.tabs)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        # Calculate Layout Alignment
        self._finalize_layout_styling()

        # Initialize UI States
        self._update_color_buttons()
        self._update_auto_scan_state(self.auto_scan_check.isChecked())
        self._update_glens_state(self.ocr_provider_combo.currentText())
        self._update_kanji_options_state(self.show_kanji_check.isChecked())
        self._update_gamepad_state(self.gamepad_enabled_check.isChecked())

    # ------------------------------------------------------------------
    # Gamepad tab builder
    # ------------------------------------------------------------------

    def _build_gamepad_tab(self):
        layout = self.tab_gamepad_layout

        # --- Group 1: Enable + Dependencies ---
        deps_group = QGroupBox("Gamepad Support")
        deps_layout = QFormLayout()
        self.form_layouts.append(deps_layout)

        self.gamepad_enabled_check = QCheckBox()
        self.gamepad_enabled_check.setChecked(config.gamepad_enabled)
        self.gamepad_enabled_check.toggled.connect(self._update_gamepad_state)
        deps_layout.addRow("Enable Gamepad Support:", self.gamepad_enabled_check)

        self.gamepad_joystick_spin = QSpinBox()
        self.gamepad_joystick_spin.setRange(0, 7)
        self.gamepad_joystick_spin.setValue(config.gamepad_joystick_index)
        self.gamepad_joystick_spin.setToolTip(
            "Index of the physical gamepad to use (0 = first detected).\n"
            "Change this if you have multiple controllers and the wrong one is being used.")
        deps_layout.addRow("Controller Index:", self.gamepad_joystick_spin)

        deps_group.setLayout(deps_layout)
        layout.addWidget(deps_group)

        # --- Group 2: Dependency Status ---
        status_group = QGroupBox("Required Packages")
        status_layout = QVBoxLayout()

        self._pygame_status_label = self._make_status_label(
            "pygame  (gamepad reading)",
            self._check_pygame(),
            install_cmd="pip install pygame",
        )
        self._vgamepad_status_label = self._make_status_label(
            "vgamepad  (pass-through driver)",
            self._check_vgamepad(),
            install_cmd="pip install vgamepad",
            extra_link=("ViGEmBus driver →",
                        "https://github.com/nefarius/ViGEmBus/releases/latest"),
        )
        status_layout.addWidget(self._pygame_status_label)
        status_layout.addWidget(self._vgamepad_status_label)

        status_note = QLabel(
            "<small>After installing packages, restart meikipop for changes to take effect.</small>"
        )
        status_note.setTextFormat(Qt.TextFormat.RichText)
        status_note.setWordWrap(True)
        status_layout.addWidget(status_note)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # --- Group 3: Button Mapping ---
        mapping_group = QGroupBox("Button Mapping")
        mapping_layout = QFormLayout()
        self.form_layouts.append(mapping_layout)

        note = QLabel(
            "<small>Default mapping assumes an Xbox-layout controller.<br>"
            "D-pad left/right always steps one character; up/down also step characters.<br>"
            "LB / RB jump one parsed word (requires parser, see Furigana tab).</small>"
        )
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setWordWrap(True)
        mapping_layout.addRow(note)

        self.gamepad_toggle_combo = self._make_button_combo(config.gamepad_toggle_button)
        self.gamepad_exit_combo = self._make_button_combo(config.gamepad_exit_button)
        self.gamepad_furigana_combo = self._make_button_combo(config.gamepad_furigana_button)
        self.gamepad_wordprev_combo = self._make_button_combo(config.gamepad_word_prev_button)
        self.gamepad_wordnext_combo = self._make_button_combo(config.gamepad_word_next_button)

        mapping_layout.addRow("Toggle Nav Mode:", self.gamepad_toggle_combo)
        mapping_layout.addRow("Exit Nav Mode:", self.gamepad_exit_combo)
        mapping_layout.addRow("Toggle Furigana:", self.gamepad_furigana_combo)
        mapping_layout.addRow("Prev Word (jump):", self.gamepad_wordprev_combo)
        mapping_layout.addRow("Next Word (jump):", self.gamepad_wordnext_combo)

        mapping_group.setLayout(mapping_layout)
        layout.addWidget(mapping_group)

        layout.addStretch()

        # Furigana section appended after the stretch placeholder
        # (insertWidget in _build_furigana_section places it before the stretch)
        self._build_furigana_section()

    # --- Furigana sub-tab is built as part of Tab 4 for coherence ---
    # (It's a second group inside the Gamepad tab so that both features
    #  are discoverable together.)

    def _build_furigana_section(self):
        """Called at the end of _build_gamepad_tab to append the furigana group."""
        furi_group = QGroupBox("Furigana Overlay")
        furi_layout = QFormLayout()
        self.form_layouts.append(furi_layout)

        # Parser status
        parser_status_widget = self._make_status_label(
            "sudachipy + sudachidict-full  (Japanese parser)",
            self._check_sudachi(),
            install_cmd="pip install sudachipy sudachidict-full",
        )
        furi_layout.addRow(parser_status_widget)

        self.furigana_enabled_check = QCheckBox()
        self.furigana_enabled_check.setChecked(config.furigana_enabled)
        self.furigana_enabled_check.setToolTip(
            "Show hiragana readings above OCR words while the popup is visible.\n"
            "Requires sudachipy + sudachidict-full to be installed.")
        furi_layout.addRow("Show Furigana:", self.furigana_enabled_check)

        self.furigana_font_spin = QSpinBox()
        self.furigana_font_spin.setRange(6, 24)
        self.furigana_font_spin.setValue(config.furigana_font_size)
        furi_layout.addRow("Furigana Font Size:", self.furigana_font_spin)

        self.furigana_color_btn = QPushButton(config.furigana_color)
        self.furigana_color_btn.clicked.connect(
            lambda: self._pick_simple_color('furigana_color', self.furigana_color_btn))
        self._apply_color_btn_style(self.furigana_color_btn, config.furigana_color)
        furi_layout.addRow("Furigana Colour:", self.furigana_color_btn)

        self.selection_color_btn = QPushButton(config.selection_color)
        self.selection_color_btn.clicked.connect(
            lambda: self._pick_simple_color('selection_color', self.selection_color_btn))
        self._apply_color_btn_style(self.selection_color_btn, config.selection_color)
        furi_layout.addRow("Selection Colour:", self.selection_color_btn)

        self.selection_opacity_spin = QSpinBox()
        self.selection_opacity_spin.setRange(0, 255)
        self.selection_opacity_spin.setValue(config.selection_opacity)
        furi_layout.addRow("Selection Opacity:", self.selection_opacity_spin)

        furi_group.setLayout(furi_layout)
        self.tab_gamepad_layout.insertWidget(
            self.tab_gamepad_layout.count() - 1,  # before the trailing stretch
            furi_group
        )

    # ------------------------------------------------------------------
    # Helper widget factories
    # ------------------------------------------------------------------

    def _make_button_combo(self, current_value: int) -> QComboBox:
        combo = QComboBox()
        self._set_expanding(combo)
        for label, val in _BUTTON_OPTIONS:
            combo.addItem(label, userData=val)
        # Select the entry whose userData matches current_value
        idx = next((i for i, (_, v) in enumerate(_BUTTON_OPTIONS) if v == current_value), 0)
        combo.setCurrentIndex(idx)
        return combo

    def _make_status_label(self, feature_name: str, ok: bool,
                           install_cmd: str = "",
                           extra_link: tuple = None) -> QWidget:
        """
        Build a one-row widget showing ✓/✗ + feature name + optional install hint.
        """
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 2, 0, 2)

        icon = "✓" if ok else "✗"
        color = "green" if ok else "#cc0000"
        status = QLabel(f'<span style="color:{color}; font-weight:bold;">{icon}</span> {feature_name}')
        status.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(status)
        row.addStretch()

        if not ok and install_cmd:
            hint = QLabel(f'<small><code>{install_cmd}</code></small>')
            hint.setTextFormat(Qt.TextFormat.RichText)
            hint.setToolTip(f"Run this in your terminal:\n  {install_cmd}")
            row.addWidget(hint)

        if extra_link:
            link_text, link_url = extra_link
            link_btn = QPushButton(link_text)
            link_btn.setFlat(True)
            link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(link_url)))
            link_btn.setStyleSheet("color: #4477aa; text-decoration: underline;")
            row.addWidget(link_btn)

        return widget

    # ------------------------------------------------------------------
    # Dependency checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_pygame() -> bool:
        try:
            import pygame  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _check_vgamepad() -> bool:
        try:
            import vgamepad
            pad = vgamepad.VX360Gamepad()
            del pad
            return True
        except Exception:
            return False

    @staticmethod
    def _check_sudachi() -> bool:
        try:
            import sudachipy  # noqa: F401
            import sudachidict_full  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Shared helpers (unchanged from original)
    # ------------------------------------------------------------------

    def _set_expanding(self, widget):
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _finalize_layout_styling(self):
        max_label_width = 0
        for layout in self.form_layouts:
            for i in range(layout.rowCount()):
                item = layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                if item and item.widget():
                    max_label_width = max(max_label_width, item.widget().sizeHint().width())
        max_label_width += 5
        for layout in self.form_layouts:
            layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.setHorizontalSpacing(15)
            for i in range(layout.rowCount()):
                item = layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
                if item and item.widget():
                    item.widget().setMinimumWidth(max_label_width)

    def _update_auto_scan_state(self, is_checked):
        self.auto_scan_interval_spin.setEnabled(is_checked)
        self.auto_scan_no_hotkey_check.setEnabled(is_checked)
        self.auto_scan_mouse_move_check.setEnabled(is_checked)
        self.auto_scan_interval_spin_label.setEnabled(is_checked)
        self.auto_scan_no_hotkey_check_label.setEnabled(is_checked)
        self.auto_scan_mouse_move_check_label.setEnabled(is_checked)

    def _update_glens_state(self, current_provider):
        is_glens = "Google Lens (remote)" in current_provider
        self.glens_compression_check.setEnabled(is_glens)
        self.glens_compression_check_label.setEnabled(is_glens)

    def _update_kanji_options_state(self, is_checked):
        self.show_examples_check.setEnabled(is_checked)
        self.show_components_check.setEnabled(is_checked)
        self.lookup.clear_cache()

    def _update_gamepad_state(self, is_checked):
        """Enable/disable gamepad sub-options based on master toggle."""
        for widget in [self.gamepad_joystick_spin,
                       self.gamepad_toggle_combo, self.gamepad_exit_combo,
                       self.gamepad_furigana_combo,
                       self.gamepad_wordprev_combo, self.gamepad_wordnext_combo]:
            widget.setEnabled(is_checked)

    def _mark_as_custom(self):
        if self.theme_combo.currentText() != "Custom":
            self.theme_combo.setCurrentText("Custom")

    def _apply_theme(self, theme_name):
        if theme_name in THEMES and theme_name != "Custom":
            theme_data = THEMES[theme_name]
            for key, value in theme_data.items():
                setattr(config, key, value)
            self._update_color_buttons()
            self.opacity_slider.setValue(config.background_opacity)

    def _update_color_buttons(self):
        for key, btn in self.color_widgets.items():
            color_hex = getattr(config, key)
            btn.setText(color_hex)
            q_color = QColor(color_hex)
            text_color = "#000000" if q_color.lightness() > 127 else "#FFFFFF"
            btn.setStyleSheet(f"background-color: {color_hex}; color: {text_color};")

    def pick_color(self, key, btn):
        color = QColorDialog.getColor(QColor(getattr(config, key)), self)
        if color.isValid():
            setattr(config, key, color.name())
            self._update_color_buttons()
            self._mark_as_custom()

    def _pick_simple_color(self, config_key: str, btn: QPushButton):
        color = QColorDialog.getColor(QColor(getattr(config, config_key)), self)
        if color.isValid():
            setattr(config, config_key, color.name())
            self._apply_color_btn_style(btn, color.name())
            btn.setText(color.name())

    @staticmethod
    def _apply_color_btn_style(btn: QPushButton, color_hex: str):
        q_color = QColor(color_hex)
        text_color = "#000000" if q_color.lightness() > 127 else "#FFFFFF"
        btn.setStyleSheet(f"background-color: {color_hex}; color: {text_color};")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_and_accept(self):
        # Update OCR Provider
        selected_provider = self.ocr_provider_combo.currentText()
        if selected_provider != config.ocr_provider:
            self.ocr_processor.switch_provider(selected_provider)

        # Update all other config values
        config.hotkey = self.hotkey_combo.currentText()
        config.glens_low_bandwidth = self.glens_compression_check.isChecked()
        config.max_lookup_length = self.max_lookup_spin.value()
        config.auto_scan_mode = self.auto_scan_check.isChecked()
        config.auto_scan_interval_seconds = self.auto_scan_interval_spin.value()
        config.auto_scan_mode_lookups_without_hotkey = self.auto_scan_no_hotkey_check.isChecked()
        config.auto_scan_on_mouse_move = self.auto_scan_mouse_move_check.isChecked()

        if IS_WINDOWS:
            config.magpie_compatibility = self.magpie_check.isChecked()
        config.compact_mode = self.compact_check.isChecked()
        config.show_all_glosses = self.show_glosses_check.isChecked()
        config.show_deconjugation = self.show_deconj_check.isChecked()
        config.show_pos = self.show_pos_check.isChecked()
        config.show_tags = self.show_tags_check.isChecked()
        config.show_frequency = self.show_frequency_check.isChecked()
        config.show_kanji = self.show_kanji_check.isChecked()
        config.show_examples = self.show_examples_check.isChecked()
        config.show_components = self.show_components_check.isChecked()

        selected_friendly_name = self.popup_position_combo.currentText()
        config.popup_position_mode = self.popup_mode_map.get(selected_friendly_name, "flip_vertically")
        config.theme_name = self.theme_combo.currentText()
        config.background_opacity = self.opacity_slider.value()
        config.font_family = self.font_family_combo.currentFont().family()
        config.font_size_header = self.font_size_header_spin.value()
        config.font_size_definitions = self.font_size_def_spin.value()

        # ---- Gamepad settings ----
        config.gamepad_enabled = self.gamepad_enabled_check.isChecked()
        config.gamepad_joystick_index = self.gamepad_joystick_spin.value()
        config.gamepad_toggle_button = self.gamepad_toggle_combo.currentData()
        config.gamepad_exit_button = self.gamepad_exit_combo.currentData()
        config.gamepad_furigana_button = self.gamepad_furigana_combo.currentData()
        config.gamepad_word_prev_button = self.gamepad_wordprev_combo.currentData()
        config.gamepad_word_next_button = self.gamepad_wordnext_combo.currentData()

        # ---- Furigana settings (only if section was built) ----
        if hasattr(self, 'furigana_enabled_check'):
            config.furigana_enabled = self.furigana_enabled_check.isChecked()
            config.furigana_font_size = self.furigana_font_spin.value()

        config.save()

        # Tell the live components to re-apply settings
        self.input_loop.reapply_settings()
        self.popup_window.reapply_settings()
        self.tray_icon.reapply_settings()
        if self.gamepad_controller:
            self.gamepad_controller.reapply_settings()
        self.ocr_processor.shared_state.screenshot_trigger_event.set()

        self.accept()
