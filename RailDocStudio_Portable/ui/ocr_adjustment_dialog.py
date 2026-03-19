"""
OCR Adjustment Dialog with Visual Preview and Auto-Learning

Provides:
1. Visual before/after preview of OCR adjustment
2. Options to apply to: single instance, all in plan, or save to template
3. Auto-learning system that tracks adjustments and suggests patterns
"""

import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from PIL import Image
import numpy as np
from utils.dpi_utils import scale_value
from paths import get_ocr_adjustments_path


class OCRAdjustmentTracker:
    """Tracks OCR adjustments for auto-learning"""

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else get_ocr_adjustments_path()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.adjustments = self._load_adjustments()

    def _load_adjustments(self) -> Dict:
        """Load adjustment history from file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f" Could not load OCR adjustments: {e}")
        return {}

    def _save_adjustments(self):
        """Save adjustment history to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.adjustments, f, indent=2)
        except Exception as e:
            print(f" Could not save OCR adjustments: {e}")

    def record_adjustment(self, symbol_class: str, offset_x: int, offset_y: int,
                         width_delta: int, height_delta: int):
        """Record a user adjustment for learning"""
        if symbol_class not in self.adjustments:
            self.adjustments[symbol_class] = {
                "history": [],
                "learned_offset_x": 0,
                "learned_offset_y": 0,
                "learned_width_delta": 0,
                "learned_height_delta": 0,
                "confidence": 0.0,
                "sample_count": 0
            }

        # Add to history
        adjustment_data = {
            "offset_x": offset_x,
            "offset_y": offset_y,
            "width_delta": width_delta,
            "height_delta": height_delta,
            "timestamp": datetime.now().isoformat()
        }
        self.adjustments[symbol_class]["history"].append(adjustment_data)

        # Update learned values (simple average for now)
        history = self.adjustments[symbol_class]["history"]
        n = len(history)

        self.adjustments[symbol_class]["learned_offset_x"] = int(
            sum(h["offset_x"] for h in history) / n
        )
        self.adjustments[symbol_class]["learned_offset_y"] = int(
            sum(h["offset_y"] for h in history) / n
        )
        self.adjustments[symbol_class]["learned_width_delta"] = int(
            sum(h["width_delta"] for h in history) / n
        )
        self.adjustments[symbol_class]["learned_height_delta"] = int(
            sum(h["height_delta"] for h in history) / n
        )
        self.adjustments[symbol_class]["sample_count"] = n

        # Calculate confidence (higher with more samples, max 0.95)
        self.adjustments[symbol_class]["confidence"] = min(0.95, n / 10.0)

        self._save_adjustments()

        print(f"Recorded adjustment for {symbol_class}: offset_x={offset_x}, offset_y={offset_y}")
        print(f"Learned average: offset_x={self.adjustments[symbol_class]['learned_offset_x']}, "
              f"offset_y={self.adjustments[symbol_class]['learned_offset_y']} "
              f"(confidence={self.adjustments[symbol_class]['confidence']:.2f}, n={n})")

    def get_learned_adjustment(self, symbol_class: str) -> Optional[Dict]:
        """Get learned adjustment for a symbol class"""
        if symbol_class in self.adjustments:
            data = self.adjustments[symbol_class]
            if data["sample_count"] >= 3:  # Need at least 3 samples to suggest
                return {
                    "offset_x": data["learned_offset_x"],
                    "offset_y": data["learned_offset_y"],
                    "width_delta": data["learned_width_delta"],
                    "height_delta": data["learned_height_delta"],
                    "confidence": data["confidence"],
                    "sample_count": data["sample_count"]
                }
        return None

    def should_show_suggestion(self, symbol_class: str) -> bool:
        """Check if we should show auto-learning suggestion"""
        if symbol_class in self.adjustments:
            data = self.adjustments[symbol_class]
            # Show suggestion after 3rd adjustment, and every 5 adjustments after
            count = data["sample_count"]
            return count == 3 or (count > 3 and count % 5 == 0)
        return False

    def apply_learned_to_template(self, symbol_class: str) -> bool:
        """Mark that learned adjustment has been applied to template"""
        if symbol_class in self.adjustments:
            self.adjustments[symbol_class]["applied_to_template"] = True
            self._save_adjustments()
            return True
        return False


class OCRAdjustmentDialog(QtWidgets.QDialog):
    """Dialog for previewing and applying OCR adjustments"""

    def __init__(self, parent, symbol_class: str, instance_count: int,
                 old_ocr_text: str, new_ocr_text: str,
                 offset_x: int, offset_y: int, width_delta: int, height_delta: int,
                 old_crop: Optional[np.ndarray] = None,
                 new_crop: Optional[np.ndarray] = None,
                 test_success_count: Optional[int] = None):
        super().__init__(parent)

        self.symbol_class = symbol_class
        self.instance_count = instance_count
        self.old_ocr_text = old_ocr_text
        self.new_ocr_text = new_ocr_text
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.width_delta = width_delta
        self.height_delta = height_delta
        self.old_crop = old_crop
        self.new_crop = new_crop
        self.test_success_count = test_success_count

        # Result options
        self.apply_to_current = False
        self.apply_to_all_in_plan = False
        self.save_to_template = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        self.setWindowTitle("OCR-Region anpassen (Adjust OCR Region)")
        self.setMinimumWidth(scale_value(600))

        layout = QtWidgets.QVBoxLayout(self)

        # Header
        header_label = QtWidgets.QLabel(
            f"<b>Symbol:</b> {self.symbol_class} &nbsp;&nbsp; "
            f"<b>Gefunden:</b> {self.instance_count} Instanzen"
        )
        header_label.setStyleSheet("font-size: 12pt; padding: 10px;")
        layout.addWidget(header_label)

        # Before/After preview section
        preview_layout = QtWidgets.QHBoxLayout()

        # Before preview
        before_group = self._create_preview_group(
            "VORHER (BEFORE)",
            self.old_ocr_text if self.old_ocr_text else "(leer / empty)",
            " Text nicht gefunden" if not self.old_ocr_text else " Text gefunden",
            self.old_crop,
            QtGui.QColor(220, 220, 220)
        )
        preview_layout.addWidget(before_group)

        # After preview
        after_group = self._create_preview_group(
            "NACHHER (AFTER)",
            self.new_ocr_text if self.new_ocr_text else "(leer / empty)",
            " Text richtig gefunden" if self.new_ocr_text else " Text nicht gefunden",
            self.new_crop,
            QtGui.QColor(230, 255, 230) if self.new_ocr_text else QtGui.QColor(255, 230, 230)
        )
        preview_layout.addWidget(after_group)

        layout.addLayout(preview_layout)

        # Adjustment info
        adjustment_text = self._format_adjustment_text()
        adjustment_label = QtWidgets.QLabel(adjustment_text)
        adjustment_label.setStyleSheet(
            "background-color: #f0f0f0; color: #000000; padding: 10px; border-radius: 5px; font-size: 11pt;"
        )
        adjustment_label.setWordWrap(True)
        layout.addWidget(adjustment_label)

        # Test results (if available)
        if self.test_success_count is not None:
            test_label = QtWidgets.QLabel(
                f" <b>Anpassung wird getestet...</b> {self.test_success_count} von {self.instance_count} erfolgreich<br>"
                f"(Testing adjustment... {self.test_success_count} of {self.instance_count} successful)"
            )
            test_label.setStyleSheet("padding: 5px; color: #0066cc;")
            layout.addWidget(test_label)

        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)

        # Options section
        options_label = QtWidgets.QLabel(
            "<b>Was möchten Sie tun? (What would you like to do?)</b>"
        )
        options_label.setStyleSheet("font-size: 11pt; padding-top: 10px;")
        layout.addWidget(options_label)

        # Radio buttons for scope
        self.radio_current = QtWidgets.QRadioButton(
            "Nur diese Instanz ändern\n(Only this instance)"
        )
        self.radio_all_plan = QtWidgets.QRadioButton(
            f"Alle {self.instance_count} Instanzen in diesem Plan ändern\n"
            f"(All {self.instance_count} instances in current plan)"
        )
        self.radio_all_plan.setChecked(True)  # Default

        layout.addWidget(self.radio_current)
        layout.addWidget(self.radio_all_plan)

        # Checkbox for saving to template
        self.checkbox_save_template = QtWidgets.QCheckBox(
            "Dauerhaft speichern für alle zukünftigen Pläne (Gilt auch für zukünftige Pläne)\n"
            "(Save permanently - applies to all future plans)"
        )
        self.checkbox_save_template.setChecked(True)  # Default
        self.checkbox_save_template.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.checkbox_save_template)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        btn_cancel = QtWidgets.QPushButton("Abbrechen (Cancel)")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        btn_apply = QtWidgets.QPushButton("Übernehmen (Apply)")
        btn_apply.setDefault(True)
        btn_apply.setStyleSheet(
            "QPushButton { background-color: #0066cc; color: white; "
            "font-weight: bold; padding: 8px 20px; }"
        )
        btn_apply.clicked.connect(self.accept)
        button_layout.addWidget(btn_apply)

        layout.addLayout(button_layout)

    def _create_preview_group(self, title: str, text: str, status: str,
                             crop_image: Optional[np.ndarray],
                             bg_color: QtGui.QColor) -> QtWidgets.QGroupBox:
        """Create a before/after preview group box"""
        group = QtWidgets.QGroupBox(title)
        group.setStyleSheet(f"QGroupBox {{ font-weight: bold; }}")

        layout = QtWidgets.QVBoxLayout()

        # Image preview (if available)
        if crop_image is not None:
            try:
                # Convert numpy array to QPixmap
                h, w = crop_image.shape[:2]
                if len(crop_image.shape) == 2:  # Grayscale
                    bytes_per_line = w
                    q_image = QtGui.QImage(crop_image.data, w, h, bytes_per_line, QtGui.QImage.Format_Grayscale8)
                else:  # RGB
                    bytes_per_line = 3 * w
                    q_image = QtGui.QImage(crop_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)

                pixmap = QtGui.QPixmap.fromImage(q_image)

                # Scale if too large
                max_size = 200
                if pixmap.width() > max_size or pixmap.height() > max_size:
                    pixmap = pixmap.scaled(max_size, max_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

                image_label = QtWidgets.QLabel()
                image_label.setPixmap(pixmap)
                image_label.setAlignment(QtCore.Qt.AlignCenter)
                layout.addWidget(image_label)
            except Exception as e:
                print(f" Could not display crop image: {e}")

        # Text label
        text_label = QtWidgets.QLabel(f"<b>{text}</b>")
        text_label.setAlignment(QtCore.Qt.AlignCenter)
        text_label.setStyleSheet(
            f"background-color: {bg_color.name()}; padding: 10px; "
            f"border-radius: 5px; font-size: 12pt;"
        )
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        # Status label
        status_label = QtWidgets.QLabel(status)
        status_label.setAlignment(QtCore.Qt.AlignCenter)
        status_label.setStyleSheet("padding: 5px;")
        layout.addWidget(status_label)

        group.setLayout(layout)
        return group

    def _format_adjustment_text(self) -> str:
        """Format adjustment information as readable text"""
        parts = []

        if self.offset_x != 0:
            direction = "links" if self.offset_x < 0 else "rechts"
            direction_en = "left" if self.offset_x < 0 else "right"
            arrow = "◀" if self.offset_x < 0 else "▶"
            parts.append(f"{arrow} {abs(self.offset_x)} Pixel nach {direction} ({direction_en})")

        if self.offset_y != 0:
            direction = "oben" if self.offset_y < 0 else "unten"
            direction_en = "up" if self.offset_y < 0 else "down"
            arrow = "▲" if self.offset_y < 0 else "▼"
            parts.append(f"{arrow} {abs(self.offset_y)} Pixel nach {direction} ({direction_en})")

        if self.width_delta != 0:
            change = "breiter" if self.width_delta > 0 else "schmaler"
            change_en = "wider" if self.width_delta > 0 else "narrower"
            parts.append(f"↔ {abs(self.width_delta)} Pixel {change} ({change_en})")

        if self.height_delta != 0:
            change = "höher" if self.height_delta > 0 else "niedriger"
            change_en = "taller" if self.height_delta > 0 else "shorter"
            parts.append(f"↕ {abs(self.height_delta)} Pixel {change} ({change_en})")

        if not parts:
            return " <b>Änderung:</b> Keine Änderung (No change)"

        return " <b>Änderung:</b><br>" + "<br>".join(parts)

    def get_options(self) -> Tuple[bool, bool, bool]:
        """Get user's choices"""
        apply_to_current = self.radio_current.isChecked()
        apply_to_all_in_plan = self.radio_all_plan.isChecked()
        save_to_template = self.checkbox_save_template.isChecked()

        return apply_to_current, apply_to_all_in_plan, save_to_template


class AutoLearningSuggestionDialog(QtWidgets.QDialog):
    """Dialog for suggesting learned OCR adjustments"""

    def __init__(self, parent, symbol_class: str, learned_data: Dict):
        super().__init__(parent)

        self.symbol_class = symbol_class
        self.learned_data = learned_data

        self._setup_ui()

    def _setup_ui(self):
        """Setup suggestion dialog UI"""
        self.setWindowTitle(" Verbesserungsvorschlag (Improvement Suggestion)")
        self.setMinimumWidth(scale_value(500))

        layout = QtWidgets.QVBoxLayout(self)

        # Icon and header
        header_layout = QtWidgets.QHBoxLayout()
        icon_label = QtWidgets.QLabel("")
        icon_label.setStyleSheet("font-size: 48pt;")
        header_layout.addWidget(icon_label)

        header_text = QtWidgets.QLabel(
            f"<h2>Verbesserungsvorschlag</h2>"
            f"<p style='color: #666;'>(Improvement Suggestion)</p>"
        )
        header_layout.addWidget(header_text)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Message
        message = QtWidgets.QLabel(
            f"Ich habe bemerkt, dass Sie OCR-Regionen für <b>\"{self.symbol_class}\"</b> "
            f"oft anpassen.<br><br>"
            f"<i>(I noticed you often adjust OCR regions for <b>\"{self.symbol_class}\"</b>)</i><br><br>"
            f"<b>Gelernte Anpassung aus {self.learned_data['sample_count']} Beispielen:</b><br>"
            f"<i>(Learned adjustment from {self.learned_data['sample_count']} examples:)</i>"
        )
        message.setWordWrap(True)
        message.setStyleSheet("padding: 10px; font-size: 11pt;")
        layout.addWidget(message)

        # Learned adjustment details
        adjustment_text = self._format_learned_adjustment()
        adjustment_label = QtWidgets.QLabel(adjustment_text)
        adjustment_label.setStyleSheet(
            "background-color: #e6f3ff; padding: 15px; border-radius: 5px; "
            "border: 2px solid #0066cc; font-size: 11pt;"
        )
        adjustment_label.setWordWrap(True)
        layout.addWidget(adjustment_label)

        # Confidence indicator
        confidence = self.learned_data['confidence']
        confidence_pct = int(confidence * 100)
        confidence_label = QtWidgets.QLabel(
            f"<b>Vertrauensstufe:</b> {confidence_pct}% "
            f"(Basiert auf {self.learned_data['sample_count']} Plänen)<br>"
            f"<i>Confidence Level: {confidence_pct}% "
            f"(Based on {self.learned_data['sample_count']} plans)</i>"
        )
        confidence_label.setStyleSheet("padding: 10px;")
        layout.addWidget(confidence_label)

        # Progress bar for confidence
        progress = QtWidgets.QProgressBar()
        progress.setValue(confidence_pct)
        progress.setStyleSheet(
            "QProgressBar { border: 1px solid #ccc; border-radius: 3px; text-align: center; }"
            "QProgressBar::chunk { background-color: #0066cc; }"
        )
        layout.addWidget(progress)

        # Question
        question_label = QtWidgets.QLabel(
            "<br><b>Soll ich dies automatisch für alle zukünftigen Pläne machen?</b><br>"
            "<i>(Should I do this automatically for all future plans?)</i>"
        )
        question_label.setStyleSheet("padding: 10px; font-size: 11pt;")
        layout.addWidget(question_label)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        btn_no = QtWidgets.QPushButton("Nein, nicht jetzt\n(No, not now)")
        btn_no.clicked.connect(self.reject)
        button_layout.addWidget(btn_no)

        btn_yes = QtWidgets.QPushButton("Ja, immer anwenden\n(Yes, always apply)")
        btn_yes.setDefault(True)
        btn_yes.setStyleSheet(
            "QPushButton { background-color: #0066cc; color: white; "
            "font-weight: bold; padding: 10px 20px; }"
        )
        btn_yes.clicked.connect(self.accept)
        button_layout.addWidget(btn_yes)

        layout.addLayout(button_layout)

    def _format_learned_adjustment(self) -> str:
        """Format learned adjustment as readable text"""
        parts = []

        offset_x = self.learned_data['offset_x']
        offset_y = self.learned_data['offset_y']
        width_delta = self.learned_data['width_delta']
        height_delta = self.learned_data['height_delta']

        if offset_x != 0:
            direction = "links" if offset_x < 0 else "rechts"
            arrow = "←" if offset_x < 0 else "→"
            parts.append(f"{arrow} {abs(offset_x)}px {direction}")

        if offset_y != 0:
            direction = "oben" if offset_y < 0 else "unten"
            arrow = "↑" if offset_y < 0 else "↓"
            parts.append(f"{arrow} {abs(offset_y)}px {direction}")

        if width_delta != 0:
            parts.append(f"↔ {abs(width_delta)}px breiter" if width_delta > 0 else f"↔ {abs(width_delta)}px schmaler")

        if height_delta != 0:
            parts.append(f"↕ {abs(height_delta)}px höher" if height_delta > 0 else f"↕ {abs(height_delta)}px niedriger")

        if not parts:
            return "Keine Anpassung"

        return " &nbsp;&nbsp; ".join(parts)
