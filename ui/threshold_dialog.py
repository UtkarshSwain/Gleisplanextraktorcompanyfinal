# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Dialog for adjusting YOLO class confidence thresholds.
Allows users to fine-tune detection sensitivity per class without editing code.
"""

from PyQt5 import QtWidgets, QtCore


class ThresholdDialog(QtWidgets.QDialog):
    """Dialog with sliders for adjusting confidence thresholds per class."""

    # Store original defaults for reset functionality
    _original_defaults = None

    @staticmethod
    def _to_slider_value(threshold: float) -> int:
        """Convert threshold (0.0-1.0) to slider value (1-100) with clamping."""
        return max(1, min(100, int(threshold * 100)))

    @staticmethod
    def _to_threshold(slider_value: int) -> float:
        """Convert slider value (1-100) to threshold (0.01-1.0)."""
        return slider_value / 100.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Konfidenz-Schwellenwerte")
        self.setMinimumWidth(450)
        self.setModal(True)

        # Store original values for reset
        import config
        if ThresholdDialog._original_defaults is None:
            ThresholdDialog._original_defaults = dict(config.CLASS_THRESH)

        self.sliders = {}  # class_name -> slider widget
        self.value_labels = {}  # class_name -> value label
        self._setup_ui()

    def _setup_ui(self):
        """Build the dialog UI."""
        import config

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # Title
        title = QtWidgets.QLabel("Konfidenz-Schwellenwerte pro Klasse")
        title.setStyleSheet("font-size: 13pt; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        # Info text
        info = QtWidgets.QLabel(
            "Niedrigere Werte = mehr Erkennungen (evtl. mehr Fehler)\n"
            "Höhere Werte = weniger Erkennungen (nur sichere)"
        )
        info.setStyleSheet("color: #666; font-size: 9pt; margin-bottom: 12px;")
        layout.addWidget(info)

        # Scroll area for sliders
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(6)

        # Create slider for each class
        for class_name in sorted(config.CLASSES):
            current_value = config.CLASS_THRESH.get(class_name, 0.25)
            row = self._create_slider_row(class_name, current_value)
            scroll_layout.addLayout(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # Reset button
        reset_btn = QtWidgets.QPushButton("Auf Standard zurücksetzen")
        reset_btn.setToolTip("Setzt alle Schwellenwerte auf die Standardwerte zurück")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)

        # Button row
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QtWidgets.QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QtWidgets.QPushButton("Anwenden")
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet("font-weight: bold;")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _create_slider_row(self, class_name: str, current_value: float) -> QtWidgets.QHBoxLayout:
        """Create a row with label, slider, and value display for one class."""
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)

        # Class name label (fixed width for alignment)
        label = QtWidgets.QLabel(class_name)
        label.setFixedWidth(140)
        label.setStyleSheet("font-size: 10pt;")
        row.addWidget(label)

        # Slider (0.01 to 1.00, step 0.01)
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setMinimum(1)  # 0.01
        slider.setMaximum(100)  # 1.00
        slider_value = self._to_slider_value(current_value)
        slider.setValue(slider_value)
        slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        slider.setTickInterval(10)
        row.addWidget(slider, 1)

        # Value label - use clamped value to match slider position
        value_label = QtWidgets.QLabel(f"{self._to_threshold(slider_value):.2f}")
        value_label.setFixedWidth(40)
        value_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        value_label.setStyleSheet("font-size: 10pt; font-family: monospace;")
        row.addWidget(value_label)

        # Connect slider to update label
        slider.valueChanged.connect(
            lambda val, lbl=value_label: lbl.setText(f"{ThresholdDialog._to_threshold(val):.2f}")
        )

        self.sliders[class_name] = slider
        self.value_labels[class_name] = value_label

        return row

    def _on_reset(self):
        """Reset all sliders to original default values."""
        if ThresholdDialog._original_defaults:
            for class_name, slider in self.sliders.items():
                default_val = ThresholdDialog._original_defaults.get(class_name, 0.25)
                slider.setValue(self._to_slider_value(default_val))

    def _on_apply(self):
        """Apply the new threshold values to config and close dialog."""
        import config

        # Update config.CLASS_THRESH with new values
        for class_name, slider in self.sliders.items():
            config.CLASS_THRESH[class_name] = self._to_threshold(slider.value())

        self.accept()

    def get_thresholds(self) -> dict:
        """Get current slider values as a dict."""
        return {
            class_name: self._to_threshold(slider.value())
            for class_name, slider in self.sliders.items()
        }
