# ui/new_symbol_dialog.py
"""
Dialog for defining new symbols without retraining.

User workflow:
1. Click on 3-5 examples of the new symbol
2. Configure parameters (has text, linking, etc.)
3. Save - symbol is immediately usable!
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsPixmapItem,
    QGraphicsTextItem, QMessageBox, QProgressBar, QTabWidget, QWidget, QSlider,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter
)
from typing import List, Dict, Optional, Tuple
import numpy as np
import cv2
from utils.dpi_utils import get_adaptive_window_size, center_window, scale_value


class ClickableImageView(QGraphicsView):
    """Graphics view that captures click positions with zoom controls."""

    clicked = pyqtSignal(float, float)  # x, y in scene coordinates
    rectangle_drawn = pyqtSignal(float, float, float, float)  # x1, y1, x2, y2
    zoom_changed = pyqtSignal(float)  # Emits zoom percentage
    delete_clicked = pyqtSignal(int)  # Emits index of example to delete

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.drawing_mode = False
        self._start_point = None
        self._current_rect = None
        self.setMouseTracking(True)
        self._zoom_factor = 1.0
        self._base_zoom = 1.0  # Set when image is loaded

    def set_drawing_mode(self, enabled: bool):
        self.drawing_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.ArrowCursor)

    def get_zoom_percentage(self) -> float:
        """Get current zoom as percentage (100% = actual pixels)."""
        transform = self.transform()
        return transform.m11() * 100  # m11 is horizontal scale

    def set_zoom(self, percentage: float):
        """Set zoom to specific percentage."""
        current = self.get_zoom_percentage()
        if current > 0:
            factor = percentage / current
            self.scale(factor, factor)
            self._zoom_factor = percentage / 100
            self.zoom_changed.emit(percentage)

    def zoom_to_100(self):
        """Zoom to 100% (1 pixel = 1 pixel)."""
        self.resetTransform()
        self._zoom_factor = 1.0
        self.zoom_changed.emit(100.0)

    def zoom_to_fit(self):
        """Fit entire image in view."""
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = self.get_zoom_percentage() / 100
        self.zoom_changed.emit(self.get_zoom_percentage())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if we clicked on a delete button ()
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())

            # Check if clicked item is a text item with delete data
            if item and hasattr(item, 'toPlainText') and item.toPlainText() == "":
                index = item.data(0)
                if index is not None:
                    self.delete_clicked.emit(index)
                    event.accept()
                    return

            # Otherwise, start drawing if in drawing mode
            if self.drawing_mode:
                self._start_point = self.mapToScene(event.pos())
                # Create preview rectangle
                self._current_rect = QGraphicsRectItem()
                self._current_rect.setPen(QtGui.QPen(Qt.green, 2, Qt.DashLine))
                self._current_rect.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 50)))
                self.scene().addItem(self._current_rect)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start_point and self._current_rect:
            current = self.mapToScene(event.pos())
            x1 = min(self._start_point.x(), current.x())
            y1 = min(self._start_point.y(), current.y())
            x2 = max(self._start_point.x(), current.x())
            y2 = max(self._start_point.y(), current.y())
            self._current_rect.setRect(x1, y1, x2 - x1, y2 - y1)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._start_point and self.drawing_mode:
            end_point = self.mapToScene(event.pos())
            x1 = min(self._start_point.x(), end_point.x())
            y1 = min(self._start_point.y(), end_point.y())
            x2 = max(self._start_point.x(), end_point.x())
            y2 = max(self._start_point.y(), end_point.y())

            # Remove preview rectangle
            if self._current_rect:
                self.scene().removeItem(self._current_rect)
                self._current_rect = None

            # Emit if rectangle is valid size
            if (x2 - x1) > 10 and (y2 - y1) > 10:
                self.rectangle_drawn.emit(x1, y1, x2, y2)

            self._start_point = None

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """
        Mouse wheel behavior (same as auditing window):
        - Ctrl + wheel: Zoom in/out
        - Shift + wheel: Horizontal scroll
        - Normal wheel: Vertical scroll (default)
        """
        modifiers = event.modifiers()

        if modifiers == Qt.ControlModifier:
            # Ctrl + wheel = zoom (like auditing window)
            delta = event.angleDelta().y()
            factor = 1.25 if delta > 0 else 1 / 1.25
            self.scale(factor, factor)
            self._zoom_factor *= factor
            self.zoom_changed.emit(self.get_zoom_percentage())
            event.accept()
        elif modifiers == Qt.ShiftModifier:
            # Shift + wheel = horizontal scroll (like auditing window)
            delta = event.angleDelta().y()
            h_bar = self.horizontalScrollBar()
            h_bar.setValue(int(h_bar.value() - delta))
            event.accept()
        else:
            # Normal wheel = vertical scroll (default behavior)
            super().wheelEvent(event)


class NewSymbolDialog(QDialog):
    """
    Dialog for defining a new symbol type.

    Workflow:
    1. User draws rectangles around 3-5 examples
    2. User configures symbol properties
    3. System saves and enables detection
    """

    symbol_defined = pyqtSignal(str)  # Emits symbol name when saved

    def __init__(self, image: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Neues Symbol definieren")

        # Adaptive sizing for different DPI settings
        w, h = get_adaptive_window_size(1200, 800, max_screen_pct=0.85)
        self.setMinimumSize(w, h)
        center_window(self)

        # Enable maximize/minimize buttons
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )

        # Make non-modal so pop-out window is accessible
        self.setModal(False)

        self.image = image
        self.images: List[np.ndarray] = [image]  # List of all loaded images
        self.current_image_index = 0
        self.examples: List[Tuple[int, int, int, int]] = []  # List of (x1, y1, x2, y2) for CURRENT image
        self.all_crops: List[np.ndarray] = []  # Crops from ALL images
        self.example_items: List[List] = []  # List of [rect, number_text, delete_btn] for each example
        self.text_region: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2) for text area
        self.text_region_item: Optional[QGraphicsRectItem] = None
        self._drawing_text_region = False  # Flag for text region drawing mode

        # For pop-out graphics window (Auskoppeln/Einkoppeln)
        self.graphics_window = None
        self.graphics_placeholder = None
        self.left_layout = None  # Will be set in _build_ui

        self._build_ui()
        self._display_image()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "<b>Schritt 1:</b> Zeichnen Sie Rechtecke um 3-5 Beispiele des neuen Symbols.<br>"
            "<b>Schritt 2:</b> Konfigurieren Sie die Symbol-Eigenschaften.<br>"
            "<b>Schritt 3:</b> Klicken Sie auf 'Speichern'."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Main content: splitter with image and settings
        splitter = QSplitter(Qt.Horizontal)

        # Left: Image view
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Toolbar Row 1: Drawing tools
        toolbar = QHBoxLayout()
        self.btn_draw = QPushButton(" Beispiel markieren")
        self.btn_draw.setCheckable(True)
        self.btn_draw.setChecked(True)
        self.btn_draw.toggled.connect(self._on_draw_toggled)
        toolbar.addWidget(self.btn_draw)

        self.btn_undo = QPushButton("↩ Rückgängig")
        self.btn_undo.clicked.connect(self._undo_last)
        toolbar.addWidget(self.btn_undo)

        self.btn_clear = QPushButton(" Alle löschen")
        self.btn_clear.clicked.connect(self._clear_all)
        toolbar.addWidget(self.btn_clear)

        toolbar.addWidget(QLabel("|"))

        # Button to load another image (for collecting examples from multiple plans)
        self.btn_load_image = QPushButton(" Weiteres Bild laden")
        self.btn_load_image.setToolTip("Laden Sie ein weiteres Bild, um mehr Beispiele zu sammeln")
        self.btn_load_image.clicked.connect(self._load_another_image)
        toolbar.addWidget(self.btn_load_image)

        toolbar.addStretch()

        self.example_count_label = QLabel("Beispiele: 0 / 3-5 (Bild 1/1)")
        toolbar.addWidget(self.example_count_label)

        left_layout.addLayout(toolbar)

        # Toolbar Row 2: Zoom controls
        zoom_toolbar = QHBoxLayout()

        self.btn_zoom_fit = QPushButton("⊡ Anpassen")
        self.btn_zoom_fit.setToolTip("Gesamtes Bild anzeigen (Fit)")
        self.btn_zoom_fit.clicked.connect(self._zoom_fit)
        zoom_toolbar.addWidget(self.btn_zoom_fit)

        self.btn_zoom_100 = QPushButton("1:1 (100%)")
        self.btn_zoom_100.setToolTip("Originalgröße (1 Pixel = 1 Pixel)")
        self.btn_zoom_100.clicked.connect(self._zoom_100)
        zoom_toolbar.addWidget(self.btn_zoom_100)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setToolTip("Vergrößern")
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        zoom_toolbar.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setToolTip("Verkleinern")
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        zoom_toolbar.addWidget(self.btn_zoom_out)

        zoom_toolbar.addWidget(QLabel("|"))

        # Zoom percentage display
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setMinimumWidth(100)
        zoom_toolbar.addWidget(self.zoom_label)

        zoom_toolbar.addWidget(QLabel("|"))

        # Pop-out button (Auskoppeln)
        self.btn_pop_out = QPushButton(" Auskoppeln")
        self.btn_pop_out.setToolTip("Bild in separatem Fenster öffnen")
        self.btn_pop_out.clicked.connect(self._pop_out_graphics)
        zoom_toolbar.addWidget(self.btn_pop_out)

        zoom_toolbar.addStretch()

        # Image info
        self.image_info_label = QLabel("")
        zoom_toolbar.addWidget(self.image_info_label)

        left_layout.addLayout(zoom_toolbar)
        self.left_layout = left_layout  # Save reference for pop-out

        # Help text for navigation (same as auditing window)
        nav_help = QLabel(
            "<small> Mausrad=Scrollen | Strg+Mausrad=Zoom | "
            "Shift+Mausrad=Horizontal scrollen</small>"
        )
        nav_help.setStyleSheet("color: gray;")
        left_layout.addWidget(nav_help)

        # Graphics view
        self.view = ClickableImageView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.set_drawing_mode(True)
        self.view.rectangle_drawn.connect(self._on_rectangle_drawn)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.delete_clicked.connect(self._delete_example)
        left_layout.addWidget(self.view)

        splitter.addWidget(left_widget)

        # Right: Settings
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_widget.setMaximumWidth(400)

        # Symbol name
        name_group = QGroupBox("Symbol-Name")
        name_layout = QFormLayout(name_group)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("z.B. spezialsignal_typ_a")
        self.name_input.textChanged.connect(self._update_ui_state)  # Enable save button when name changes
        name_layout.addRow("Name:", self.name_input)
        right_layout.addWidget(name_group)

        # Detection settings
        det_group = QGroupBox("Erkennung")
        det_layout = QFormLayout(det_group)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(50, 95)
        self.threshold_slider.setValue(75)
        self.threshold_label = QLabel("75%")
        self.threshold_slider.valueChanged.connect(
            lambda v: self.threshold_label.setText(f"{v}%")
        )
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self.threshold_slider)
        threshold_row.addWidget(self.threshold_label)
        det_layout.addRow("Ähnlichkeit:", threshold_row)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Automatisch", "Template", "Kontur", "Kreis"])
        det_layout.addRow("Methode:", self.method_combo)

        right_layout.addWidget(det_group)

        # OCR settings
        ocr_group = QGroupBox("Text-Erkennung (OCR)")
        ocr_layout = QFormLayout(ocr_group)

        self.has_text_check = QCheckBox()
        self.has_text_check.toggled.connect(self._on_has_text_changed)
        ocr_layout.addRow("Hat Text/ID:", self.has_text_check)

        # Multi-select text positions with checkboxes
        text_pos_group = QGroupBox("Text-Position (mehrere möglich)")
        text_pos_layout = QVBoxLayout(text_pos_group)
        text_pos_layout.setSpacing(2)

        # Inside option (for text inside symbol like speed signs)
        self.text_pos_inside = QCheckBox("innen (im Symbol)")
        text_pos_layout.addWidget(self.text_pos_inside)

        # Cardinal directions row
        text_cardinal_layout = QHBoxLayout()
        self.text_pos_above = QCheckBox("oben")
        self.text_pos_below = QCheckBox("unten")
        self.text_pos_left = QCheckBox("links")
        self.text_pos_right = QCheckBox("rechts")
        text_cardinal_layout.addWidget(self.text_pos_above)
        text_cardinal_layout.addWidget(self.text_pos_below)
        text_cardinal_layout.addWidget(self.text_pos_left)
        text_cardinal_layout.addWidget(self.text_pos_right)
        text_pos_layout.addLayout(text_cardinal_layout)

        # Diagonal directions row
        text_diagonal_layout = QHBoxLayout()
        self.text_pos_above_left = QCheckBox("oben-links")
        self.text_pos_above_right = QCheckBox("oben-rechts")
        self.text_pos_below_left = QCheckBox("unten-links")
        self.text_pos_below_right = QCheckBox("unten-rechts")
        text_diagonal_layout.addWidget(self.text_pos_above_left)
        text_diagonal_layout.addWidget(self.text_pos_above_right)
        text_diagonal_layout.addWidget(self.text_pos_below_left)
        text_diagonal_layout.addWidget(self.text_pos_below_right)
        text_pos_layout.addLayout(text_diagonal_layout)

        # Store all text position checkboxes
        self.text_position_checks = [
            self.text_pos_inside,
            self.text_pos_above, self.text_pos_below,
            self.text_pos_left, self.text_pos_right,
            self.text_pos_above_left, self.text_pos_above_right,
            self.text_pos_below_left, self.text_pos_below_right
        ]

        for cb in self.text_position_checks:
            cb.setEnabled(False)

        text_pos_group.setEnabled(False)
        self.text_pos_group = text_pos_group
        ocr_layout.addRow(text_pos_group)

        # Button to draw text region (more precise than direction)
        text_region_btn_layout = QHBoxLayout()
        self.btn_draw_text_region = QPushButton(" Text-Bereich markieren")
        self.btn_draw_text_region.setToolTip(
            "Zeichnen Sie ein Rechteck um den Text-Bereich.\n"
            "Dies ist genauer als nur die Richtung anzugeben."
        )
        self.btn_draw_text_region.setEnabled(False)
        self.btn_draw_text_region.clicked.connect(self._start_text_region_drawing)
        text_region_btn_layout.addWidget(self.btn_draw_text_region)

        # Delete text region button
        self.btn_delete_text_region = QPushButton("")
        self.btn_delete_text_region.setFixedWidth(30)
        self.btn_delete_text_region.setToolTip("Text-Bereich löschen und neu zeichnen")
        self.btn_delete_text_region.setEnabled(False)
        self.btn_delete_text_region.clicked.connect(self._delete_text_region)
        text_region_btn_layout.addWidget(self.btn_delete_text_region)
        ocr_layout.addRow("", text_region_btn_layout)

        # Label showing text region status
        self.text_region_label = QLabel("Kein Text-Bereich definiert")
        self.text_region_label.setStyleSheet("color: gray; font-style: italic;")
        ocr_layout.addRow("", self.text_region_label)

        # Text pattern presets (user-friendly, no regex knowledge needed)
        self.text_pattern_combo = QComboBox()
        self.text_pattern_combo.addItems([
            "Kein Muster (alle akzeptieren)",
            "Koordinate (z.B. 12+345)",
            "Buchstaben + Zahlen (z.B. FB160)",
            "Nur Zahlen (z.B. 1554)",
            "Signal-ID (z.B. A3, B12)",
            "Nur Buchstaben (z.B. GM, PB)",
            "Benutzerdefiniert..."
        ])
        self.text_pattern_combo.setEnabled(False)
        self.text_pattern_combo.currentIndexChanged.connect(self._on_pattern_changed)
        ocr_layout.addRow("Text-Muster:", self.text_pattern_combo)

        # Custom regex input (hidden by default)
        self.text_pattern_input = QLineEdit()
        self.text_pattern_input.setPlaceholderText("Regex eingeben...")
        self.text_pattern_input.setEnabled(False)
        self.text_pattern_input.setVisible(False)
        ocr_layout.addRow("Regex:", self.text_pattern_input)

        right_layout.addWidget(ocr_group)

        # Linking settings
        link_group = QGroupBox("Koordinaten-Verknüpfung")
        link_layout = QFormLayout(link_group)

        self.links_coord_check = QCheckBox()
        self.links_coord_check.toggled.connect(self._on_links_coord_changed)
        link_layout.addRow("Mit Koordinate verknüpfen:", self.links_coord_check)

        # Multi-select coordinate positions with checkboxes
        coord_pos_group = QGroupBox("Koordinaten-Position")
        coord_pos_layout = QVBoxLayout(coord_pos_group)
        coord_pos_layout.setSpacing(2)

        # "Any" checkbox (exclusive - unchecks others when selected)
        self.coord_pos_any = QCheckBox("beliebig (alle Richtungen)")
        self.coord_pos_any.setChecked(True)
        self.coord_pos_any.toggled.connect(self._on_coord_any_toggled)
        coord_pos_layout.addWidget(self.coord_pos_any)

        # Separator
        sep_line = QLabel("─" * 20)
        sep_line.setStyleSheet("color: gray;")
        coord_pos_layout.addWidget(sep_line)

        # Cardinal directions row
        cardinal_layout = QHBoxLayout()
        self.coord_pos_above = QCheckBox("oben")
        self.coord_pos_below = QCheckBox("unten")
        self.coord_pos_left = QCheckBox("links")
        self.coord_pos_right = QCheckBox("rechts")
        cardinal_layout.addWidget(self.coord_pos_above)
        cardinal_layout.addWidget(self.coord_pos_below)
        cardinal_layout.addWidget(self.coord_pos_left)
        cardinal_layout.addWidget(self.coord_pos_right)
        coord_pos_layout.addLayout(cardinal_layout)

        # Diagonal directions row
        diagonal_layout = QHBoxLayout()
        self.coord_pos_above_left = QCheckBox("oben-links")
        self.coord_pos_above_right = QCheckBox("oben-rechts")
        self.coord_pos_below_left = QCheckBox("unten-links")
        self.coord_pos_below_right = QCheckBox("unten-rechts")
        diagonal_layout.addWidget(self.coord_pos_above_left)
        diagonal_layout.addWidget(self.coord_pos_above_right)
        diagonal_layout.addWidget(self.coord_pos_below_left)
        diagonal_layout.addWidget(self.coord_pos_below_right)
        coord_pos_layout.addLayout(diagonal_layout)

        # Store all position checkboxes for easy access
        self.coord_position_checks = [
            self.coord_pos_above, self.coord_pos_below,
            self.coord_pos_left, self.coord_pos_right,
            self.coord_pos_above_left, self.coord_pos_above_right,
            self.coord_pos_below_left, self.coord_pos_below_right
        ]

        # Connect all checkboxes to uncheck "any" when selected
        for cb in self.coord_position_checks:
            cb.toggled.connect(self._on_coord_specific_toggled)
            cb.setEnabled(False)
        self.coord_pos_any.setEnabled(False)

        coord_pos_group.setEnabled(False)
        self.coord_pos_group = coord_pos_group
        link_layout.addRow(coord_pos_group)

        # User-friendly distance selector with presets
        self.distance_combo = QComboBox()
        self.distance_combo.addItems([
            "nah (≈ 1-2 cm auf Papier)",
            "mittel (≈ 3-5 cm auf Papier)",
            "weit (≈ 5-10 cm auf Papier)",
            "sehr weit (≈ 10+ cm auf Papier)",
            "benutzerdefiniert..."
        ])
        self.distance_combo.setEnabled(False)
        self.distance_combo.currentIndexChanged.connect(self._on_distance_preset_changed)
        self.distance_combo.setToolTip(
            "Wie weit kann die Koordinate vom Symbol entfernt sein?\n"
            "Die Werte sind Schätzungen basierend auf typischen Gleisplänen."
        )
        link_layout.addRow("Suchbereich:", self.distance_combo)

        # Custom distance input (hidden by default)
        self.max_distance_spin = QSpinBox()
        self.max_distance_spin.setRange(50, 1000)
        self.max_distance_spin.setValue(200)
        self.max_distance_spin.setSuffix(" Pixel")
        self.max_distance_spin.setEnabled(False)
        self.max_distance_spin.setVisible(False)
        link_layout.addRow("Pixel-Abstand:", self.max_distance_spin)

        right_layout.addWidget(link_group)

        # Preview of collected examples
        preview_group = QGroupBox("Gesammelte Beispiele")
        preview_layout = QVBoxLayout(preview_group)

        # Use a scroll area with custom widgets for delete buttons
        from PyQt5.QtWidgets import QScrollArea, QFrame
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMaximumHeight(180)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.preview_container = QWidget()
        self.preview_flow_layout = QHBoxLayout(self.preview_container)
        self.preview_flow_layout.setAlignment(Qt.AlignLeft)
        self.preview_flow_layout.setSpacing(5)
        self.preview_scroll.setWidget(self.preview_container)

        preview_layout.addWidget(self.preview_scroll)

        # Size warning label
        self.size_warning_label = QLabel("")
        self.size_warning_label.setWordWrap(True)
        self.size_warning_label.hide()  # Hidden by default
        preview_layout.addWidget(self.size_warning_label)

        right_layout.addWidget(preview_group)

        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setSizes([800, 400])

        layout.addWidget(splitter)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(" Speichern")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_symbol)
        button_layout.addWidget(self.btn_save)

        layout.addLayout(button_layout)

    def _display_image(self):
        """Display the image in the graphics view."""
        # Convert numpy to QPixmap
        if len(self.image.shape) == 3:
            h, w, c = self.image.shape
            bytes_per_line = 3 * w
            # Convert BGR to RGB
            rgb = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)
            q_img = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        else:
            h, w = self.image.shape
            bytes_per_line = w
            q_img = QtGui.QImage(self.image.data, w, h, bytes_per_line, QtGui.QImage.Format_Grayscale8)

        pixmap = QtGui.QPixmap.fromImage(q_img)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QtCore.QRectF(pixmap.rect()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

        # Update image info
        h, w = self.image.shape[:2]
        self.image_info_label.setText(f"Bild: {w} x {h} px")

        # Update zoom label after fit
        self._on_zoom_changed(self.view.get_zoom_percentage())

    def _on_draw_toggled(self, checked: bool):
        self.view.set_drawing_mode(checked)

    # ========== ZOOM METHODS ==========
    def _zoom_fit(self):
        """Fit image to view."""
        self.view.zoom_to_fit()

    def _zoom_100(self):
        """Zoom to 100% (actual pixels)."""
        self.view.zoom_to_100()

    def _zoom_in(self):
        """Zoom in by 25%."""
        current = self.view.get_zoom_percentage()
        self.view.set_zoom(current * 1.25)

    def _zoom_out(self):
        """Zoom out by 25%."""
        current = self.view.get_zoom_percentage()
        self.view.set_zoom(current / 1.25)

    def _on_zoom_changed(self, percentage: float):
        """Update zoom label when zoom changes."""
        self.zoom_label.setText(f"Zoom: {percentage:.1f}%")

    def _on_rectangle_drawn(self, x1: float, y1: float, x2: float, y2: float):
        """Handle new rectangle - either symbol example or text region."""
        # Check if we're drawing text region
        if self._drawing_text_region:
            self._on_text_region_drawn(x1, y1, x2, y2)
            return

        # Otherwise it's a symbol example
        # Store coordinates for current image
        bbox = (int(x1), int(y1), int(x2), int(y2))
        self.examples.append(bbox)

        # Also save the crop to all_crops (for multi-image support)
        x1_i, y1_i, x2_i, y2_i = int(x1), int(y1), int(x2), int(y2)
        crop = self.image[y1_i:y2_i, x1_i:x2_i].copy()
        self.all_crops.append(crop)

        example_index = len(self.all_crops) - 1  # Index of this example

        # Draw permanent rectangle
        rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
        rect.setPen(QtGui.QPen(Qt.green, 3))
        rect.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 0, 30)))
        self.scene.addItem(rect)

        # Add number label
        num_text = self.scene.addText(str(len(self.all_crops)))
        num_text.setPos(x1, y1 - 25)
        num_text.setDefaultTextColor(Qt.green)
        font = num_text.font()
        font.setPointSize(14)
        font.setBold(True)
        num_text.setFont(font)

        # Add delete button (X) at top-right corner
        delete_btn = self.scene.addText("")
        delete_btn.setPos(x2 - 20, y1 - 25)
        delete_btn.setDefaultTextColor(Qt.red)
        delete_font = delete_btn.font()
        delete_font.setPointSize(16)
        delete_font.setBold(True)
        delete_btn.setFont(delete_font)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setToolTip("Beispiel löschen")
        # Store index for deletion
        delete_btn.setData(0, example_index)

        # Store all items together
        self.example_items.append([rect, num_text, delete_btn])

        # Update preview
        self._update_preview()
        self._update_ui_state()

        # Enable text region button if has_text is checked
        if self.has_text_check.isChecked():
            self.btn_draw_text_region.setEnabled(True)

    def _update_preview(self):
        """Update the preview list with ALL example crops (from all images)."""
        # Clear existing preview widgets
        while self.preview_flow_layout.count():
            child = self.preview_flow_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for i, crop in enumerate(self.all_crops):
            h_px, w_px = crop.shape[:2]

            # Create a container widget for each example
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(2, 2, 2, 2)
            item_layout.setSpacing(2)

            # Convert crop to QPixmap
            if len(crop.shape) == 3:
                h, w, c = crop.shape
                rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                q_img = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
            else:
                h, w = crop.shape
                q_img = QtGui.QImage(crop.data, w, h, w, QtGui.QImage.Format_Grayscale8)

            pixmap = QtGui.QPixmap.fromImage(q_img).scaled(
                60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

            # Image label
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setStyleSheet("border: 1px solid #ccc; background: white;")
            item_layout.addWidget(img_label)

            # Info and delete button row
            info_row = QHBoxLayout()
            info_row.setSpacing(2)

            # Number label
            num_label = QLabel(f"#{i+1}")
            num_label.setStyleSheet("font-size: 10px; color: green; font-weight: bold;")
            info_row.addWidget(num_label)

            # Delete button - bright red background with white X for visibility
            delete_btn = QPushButton("X")
            delete_btn.setFixedSize(18, 18)
            delete_btn.setStyleSheet(
                "QPushButton { color: white; font-weight: bold; font-size: 12px; "
                "border: 1px solid #cc0000; border-radius: 9px; background: #ff4444; }"
                "QPushButton:hover { background: #ff0000; }"
            )
            delete_btn.setToolTip("Beispiel löschen")
            delete_btn.setCursor(Qt.PointingHandCursor)
            # Connect with lambda to capture index
            delete_btn.clicked.connect(lambda checked, idx=i: self._delete_example(idx))
            info_row.addWidget(delete_btn)

            item_layout.addLayout(info_row)

            # Size label
            size_label = QLabel(f"{w_px}x{h_px}")
            size_label.setStyleSheet("font-size: 9px; color: gray;")
            size_label.setAlignment(Qt.AlignCenter)
            item_layout.addWidget(size_label)

            item_widget.setFixedWidth(75)
            self.preview_flow_layout.addWidget(item_widget)

    def _update_ui_state(self):
        """Update UI based on current state."""
        total_count = len(self.all_crops)  # Total from ALL images
        current_count = len(self.examples)  # Current image only
        num_images = len(self.images)
        current_img = self.current_image_index + 1

        self.example_count_label.setText(
            f"Beispiele: {total_count} / 3-5 (Bild {current_img}/{num_images}, {current_count} hier)"
        )

        if total_count >= 3:
            self.example_count_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.example_count_label.setStyleSheet("color: orange;")

        # Check for size warnings using all_crops
        warnings = []
        for i, crop in enumerate(self.all_crops):
            h, w = crop.shape[:2]
            if w < 20 or h < 20:
                warnings.append(f"Beispiel #{i+1} ist sehr klein ({w}x{h}px)")
            elif w > 300 or h > 300:
                warnings.append(f"Beispiel #{i+1} ist sehr groß ({w}x{h}px)")

        # Show size warning if any
        if hasattr(self, 'size_warning_label'):
            if warnings:
                self.size_warning_label.setText(" " + "; ".join(warnings))
                self.size_warning_label.setStyleSheet("color: orange;")
                self.size_warning_label.show()
            else:
                self.size_warning_label.hide()

        # Enable save only if we have enough examples (from ALL images) and a name
        has_name = len(self.name_input.text().strip()) > 0
        self.btn_save.setEnabled(total_count >= 3 and has_name)

    def _undo_last(self):
        """Remove last example from current image."""
        if self.examples:
            self.examples.pop()
            if self.all_crops:
                self.all_crops.pop()
            if self.example_items:
                items = self.example_items.pop()
                # Remove all items (rect, number, delete button)
                for item in items:
                    self.scene.removeItem(item)
            self._update_preview()
            self._update_ui_state()
            self._renumber_examples()

    def _clear_all(self):
        """Clear all examples from ALL images."""
        self.examples.clear()
        self.all_crops.clear()
        for items in self.example_items:
            # Each entry is a list of [rect, number, delete_btn]
            for item in items:
                self.scene.removeItem(item)
        self.example_items.clear()
        self._update_preview()
        self._update_ui_state()

    def _delete_example(self, index: int):
        """Delete a specific example by index."""
        if index < 0 or index >= len(self.all_crops):
            return

        # Remove from all_crops
        self.all_crops.pop(index)

        # Remove from examples if it's from current image
        # Note: We track which examples belong to current image
        current_img_count = len(self.examples)
        items_before_current = len(self.all_crops) - current_img_count + 1

        if index >= items_before_current:
            local_index = index - items_before_current
            if local_index < len(self.examples):
                self.examples.pop(local_index)

        # Remove graphics items if they exist for this index
        if index < len(self.example_items):
            items = self.example_items.pop(index)
            for item in items:
                self.scene.removeItem(item)

        # Update numbers on remaining items
        self._renumber_examples()
        self._update_preview()
        self._update_ui_state()

    def _renumber_examples(self):
        """Renumber all example labels after deletion."""
        for i, items in enumerate(self.example_items):
            if len(items) >= 2:
                # items[1] is the number text
                num_text = items[1]
                num_text.setPlainText(str(i + 1))
                # Update delete button data
                if len(items) >= 3:
                    items[2].setData(0, i)

    def _load_another_image(self):
        """Load another Gleisplan image to collect more symbol examples."""
        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Weiteren Gleisplan laden",
            "",
            "Alle Gleispläne (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.pdf);;"
            "Bilder (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
            "PDF Dateien (*.pdf);;"
            "Alle Dateien (*.*)"
        )

        if not file_path:
            return

        new_image = None

        # Check if PDF
        if file_path.lower().endswith('.pdf'):
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                if len(doc) == 0:
                    QMessageBox.warning(self, "Fehler", "Dokument enthält keine Seiten.")
                    return

                # If multiple pages, ask which one
                page_num = 0
                if len(doc) > 1:
                    from PyQt5.QtWidgets import QInputDialog
                    page_num, ok = QInputDialog.getInt(
                        self, "Seite wählen",
                        f"Dokument hat {len(doc)} Seiten. Welche Seite? (1-{len(doc)})",
                        1, 1, len(doc)
                    )
                    if not ok:
                        return
                    page_num -= 1  # Convert to 0-indexed

                # Render at 500 DPI (same as main pipeline)
                page = doc[page_num]
                dpi = 500
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Convert to numpy array
                import numpy as np
                new_image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

                # Convert RGB to BGR for OpenCV
                if pix.n == 4:  # RGBA
                    new_image = cv2.cvtColor(new_image, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3:  # RGB
                    new_image = cv2.cvtColor(new_image, cv2.COLOR_RGB2BGR)

                doc.close()
                print(f"[DEBUG] Loaded PDF page {page_num + 1} at {dpi} DPI: {new_image.shape}")

            except ImportError:
                QMessageBox.warning(
                    self, "Fehler",
                    "PyMuPDF (fitz) ist nicht installiert.\n"
                    "Bitte installieren Sie es mit: pip install pymupdf"
                )
                return
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Konnte Datei nicht laden:\n{str(e)}")
                return
        else:
            # Load regular image
            new_image = cv2.imread(file_path)

        if new_image is None:
            QMessageBox.warning(self, "Fehler", f"Konnte Datei nicht laden:\n{file_path}")
            return

        # Save current image's examples are already in all_crops
        # Clear current image state (graphics items only, keep all_crops)
        self.examples.clear()
        for items in self.example_items:
            # Each entry is a list of [rect, number, delete_btn]
            for item in items:
                self.scene.removeItem(item)
        self.example_items.clear()

        # Add new image
        self.images.append(new_image)
        self.current_image_index = len(self.images) - 1
        self.image = new_image

        # Display the new image
        self._display_image()
        self._update_ui_state()

    def _pop_out_graphics(self):
        """Pop out the graphics view into a separate window (Auskoppeln)."""
        if self.graphics_window is not None:
            # Already popped out
            self.graphics_window.raise_()
            self.graphics_window.activateWindow()
            return

        from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QPushButton, QSizePolicy

        # Store view's current size and stretch for restoring later
        self._view_size = self.view.size()
        self._view_index = self.left_layout.indexOf(self.view)
        self._view_stretch = self.left_layout.stretch(self._view_index)

        # Create a new window for the graphics view
        self.graphics_window = QMainWindow(self)  # Parent to dialog so it stays accessible
        self.graphics_window.setWindowTitle("Symbol-Bild (Auskoppeln)")
        w, h = get_adaptive_window_size(800, 600, max_screen_pct=0.70)
        self.graphics_window.setMinimumSize(w, h)

        # Create central widget with layout
        central = QWidget()
        win_layout = QVBoxLayout(central)

        # Create placeholder in original location - match the view's size exactly
        self.graphics_placeholder = QLabel(" Bild wurde ausgekoppelt\n\nKlicken Sie auf 'Einkoppeln' im separaten Fenster")
        self.graphics_placeholder.setAlignment(Qt.AlignCenter)
        self.graphics_placeholder.setStyleSheet("background-color: #f0f0f0; border: 2px dashed #aaa; padding: 20px;")
        # Use same size policy as view to prevent layout shift
        self.graphics_placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graphics_placeholder.setMinimumSize(self._view_size)

        # Remove view from original layout
        self.left_layout.removeWidget(self.view)

        # Add placeholder at same position with same stretch
        self.left_layout.insertWidget(self._view_index, self.graphics_placeholder, self._view_stretch)

        # Add view to new window
        win_layout.addWidget(self.view)

        # Add redock button
        redock_btn = QPushButton("⬅ Einkoppeln (zurück ins Hauptfenster)")
        redock_btn.clicked.connect(self._redock_graphics)
        win_layout.addWidget(redock_btn)

        self.graphics_window.setCentralWidget(central)
        self.graphics_window.show()

        # Update button text
        self.btn_pop_out.setText(" Ausgekoppelt")
        self.btn_pop_out.setEnabled(False)

        # Handle window close
        self.graphics_window.closeEvent = lambda e: self._on_graphics_window_closed(e)

    def _redock_graphics(self):
        """Redock the graphics view back into the main window (Einkoppeln)."""
        if self.graphics_window is None:
            return

        self.graphics_window.close()

    def _on_graphics_window_closed(self, event):
        """Called when the pop-out graphics window is closed."""
        if self.graphics_window is None:
            return

        # Remove placeholder and re-insert view
        if self.graphics_placeholder:
            self.left_layout.removeWidget(self.graphics_placeholder)
            self.graphics_placeholder.deleteLater()
            self.graphics_placeholder = None

        # Re-insert view at original position with original stretch
        self.view.setParent(None)
        self.left_layout.insertWidget(self._view_index, self.view, self._view_stretch)

        self.graphics_window = None

        # Update button
        self.btn_pop_out.setText(" Auskoppeln")
        self.btn_pop_out.setEnabled(True)

        event.accept()

    def _on_has_text_changed(self, checked: bool):
        # Enable/disable text position checkboxes
        self.text_pos_group.setEnabled(checked)
        for cb in self.text_position_checks:
            cb.setEnabled(checked)
        self.text_pattern_combo.setEnabled(checked)
        self.btn_draw_text_region.setEnabled(checked and len(self.examples) > 0)
        # Only show custom regex input if "Benutzerdefiniert" is selected
        if checked and self.text_pattern_combo.currentText() == "Benutzerdefiniert...":
            self.text_pattern_input.setEnabled(True)
            self.text_pattern_input.setVisible(True)
        else:
            self.text_pattern_input.setEnabled(False)
            self.text_pattern_input.setVisible(False)

    def _start_text_region_drawing(self):
        """Start drawing mode for text region."""
        if len(self.examples) == 0:
            QMessageBox.warning(
                self,
                "Hinweis",
                "Bitte markieren Sie zuerst mindestens ein Symbol-Beispiel."
            )
            return

        self._drawing_text_region = True
        self.btn_draw.setChecked(False)  # Disable symbol drawing
        self.view.set_drawing_mode(True)
        self.btn_draw_text_region.setText(" Zeichnen... (Klicken + Ziehen)")
        self.btn_draw_text_region.setStyleSheet("background-color: #4CAF50; color: white;")

        QMessageBox.information(
            self,
            "Text-Bereich markieren",
            "Zeichnen Sie jetzt ein Rechteck um den Text-Bereich,\n"
            "der zum ERSTEN Symbol-Beispiel gehört.\n\n"
            "Das System lernt den relativen Abstand und die Größe."
        )

    def _on_text_region_drawn(self, x1: float, y1: float, x2: float, y2: float):
        """Handle text region rectangle."""
        # Remove old text region if exists
        if self.text_region_item:
            self.scene.removeItem(self.text_region_item)
            self.text_region_item = None

        # Store new text region
        self.text_region = (int(x1), int(y1), int(x2), int(y2))

        # Draw blue rectangle for text region
        rect = QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
        rect.setPen(QtGui.QPen(QtGui.QColor(0, 100, 255), 3))  # Blue
        rect.setBrush(QtGui.QBrush(QtGui.QColor(0, 100, 255, 40)))
        self.scene.addItem(rect)
        self.text_region_item = rect

        # Add "TEXT" label
        text_label = self.scene.addText("TEXT")
        text_label.setPos(x1, y1 - 25)
        text_label.setDefaultTextColor(QtGui.QColor(0, 100, 255))
        font = text_label.font()
        font.setPointSize(12)
        font.setBold(True)
        text_label.setFont(font)

        # Calculate offset relative to first symbol
        if self.examples:
            sym_x1, sym_y1, sym_x2, sym_y2 = self.examples[0]
            sym_cx = (sym_x1 + sym_x2) / 2
            sym_cy = (sym_y1 + sym_y2) / 2
            txt_cx = (x1 + x2) / 2
            txt_cy = (y1 + y2) / 2

            dx = int(txt_cx - sym_cx)
            dy = int(txt_cy - sym_cy)
            tw = int(x2 - x1)
            th = int(y2 - y1)

            self.text_region_label.setText(
                f" Text-Bereich: Offset ({dx:+d}, {dy:+d}), Größe {tw}x{th}px"
            )
            self.text_region_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.text_region_label.setText(f" Text-Bereich: {int(x2-x1)}x{int(y2-y1)}px")
            self.text_region_label.setStyleSheet("color: green;")

        # Reset drawing mode
        self._drawing_text_region = False
        self.btn_draw_text_region.setText(" Text-Bereich markieren")
        self.btn_draw_text_region.setStyleSheet("")
        self.btn_draw.setChecked(True)  # Re-enable symbol drawing
        self.btn_delete_text_region.setEnabled(True)  # Enable delete button

    def _on_pattern_changed(self, index: int):
        """Show/hide custom regex input based on selection."""
        is_custom = self.text_pattern_combo.currentText() == "Benutzerdefiniert..."
        self.text_pattern_input.setVisible(is_custom)
        self.text_pattern_input.setEnabled(is_custom and self.has_text_check.isChecked())

    def _get_pattern_regex(self) -> Optional[str]:
        """Get the regex pattern from the selected preset."""
        # Pattern presets mapping
        pattern_map = {
            "Kein Muster (alle akzeptieren)": None,
            "Koordinate (z.B. 12+345)": r"^\d+\+\d+$",
            "Buchstaben + Zahlen (z.B. FB160)": r"^[A-Za-z]+\d+$",
            "Nur Zahlen (z.B. 1554)": r"^\d+$",
            "Signal-ID (z.B. A3, B12)": r"^[A-Z]\d{1,3}$",
            "Nur Buchstaben (z.B. GM, PB)": r"^[A-Za-z]+$",
            "Benutzerdefiniert...": self.text_pattern_input.text().strip() or None,
        }
        selected = self.text_pattern_combo.currentText()
        return pattern_map.get(selected, None)

    def _on_links_coord_changed(self, checked: bool):
        # Enable/disable coordinate position checkboxes
        self.coord_pos_group.setEnabled(checked)
        self.coord_pos_any.setEnabled(checked)
        for cb in self.coord_position_checks:
            cb.setEnabled(checked)
        self.distance_combo.setEnabled(checked)
        # Only show custom spin if "benutzerdefiniert" is selected
        is_custom = self.distance_combo.currentText() == "benutzerdefiniert..."
        self.max_distance_spin.setEnabled(checked and is_custom)
        self.max_distance_spin.setVisible(checked and is_custom)

    def _on_coord_any_toggled(self, checked: bool):
        """When 'any' is checked, uncheck all specific positions."""
        if checked:
            for cb in self.coord_position_checks:
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _on_coord_specific_toggled(self, checked: bool):
        """When any specific position is checked, uncheck 'any'."""
        if checked:
            self.coord_pos_any.blockSignals(True)
            self.coord_pos_any.setChecked(False)
            self.coord_pos_any.blockSignals(False)

    def _get_selected_text_positions(self) -> list:
        """Get list of selected text positions."""
        position_map = {
            self.text_pos_inside: "inside",
            self.text_pos_above: "above",
            self.text_pos_below: "below",
            self.text_pos_left: "left",
            self.text_pos_right: "right",
            self.text_pos_above_left: "above_left",
            self.text_pos_above_right: "above_right",
            self.text_pos_below_left: "below_left",
            self.text_pos_below_right: "below_right",
        }
        selected = [pos for cb, pos in position_map.items() if cb.isChecked()]
        return selected if selected else ["below"]  # Default to "below" if none selected

    def _get_selected_coord_positions(self) -> list:
        """Get list of selected coordinate positions."""
        if self.coord_pos_any.isChecked():
            return ["any"]

        position_map = {
            self.coord_pos_above: "above",
            self.coord_pos_below: "below",
            self.coord_pos_left: "left",
            self.coord_pos_right: "right",
            self.coord_pos_above_left: "above_left",
            self.coord_pos_above_right: "above_right",
            self.coord_pos_below_left: "below_left",
            self.coord_pos_below_right: "below_right",
        }
        selected = [pos for cb, pos in position_map.items() if cb.isChecked()]
        return selected if selected else ["any"]  # Default to "any" if none selected

    def _on_distance_preset_changed(self, index: int):
        """Handle distance preset selection."""
        preset = self.distance_combo.currentText()
        is_custom = "benutzerdefiniert" in preset

        self.max_distance_spin.setVisible(is_custom)
        self.max_distance_spin.setEnabled(is_custom and self.links_coord_check.isChecked())

        # Set pixel values for presets (based on typical 300 DPI scans)
        preset_values = {
            "nah": 100,       # ~1-2 cm
            "mittel": 200,    # ~3-5 cm
            "weit": 350,      # ~5-10 cm
            "sehr weit": 500  # ~10+ cm
        }

        for key, value in preset_values.items():
            if key in preset:
                self.max_distance_spin.setValue(value)
                break

    def _delete_text_region(self):
        """Delete the current text region and allow redrawing."""
        # Remove graphics item
        if self.text_region_item:
            self.scene.removeItem(self.text_region_item)
            self.text_region_item = None

        # Remove the text label if it exists
        for item in self.scene.items():
            if isinstance(item, QGraphicsTextItem):
                if item.toPlainText() == "TEXT":
                    self.scene.removeItem(item)
                    break

        # Reset text region data
        self.text_region = None
        self.text_region_offset = None

        # Update UI
        self.text_region_label.setText("Kein Text-Bereich definiert")
        self.text_region_label.setStyleSheet("color: gray; font-style: italic;")
        self.btn_delete_text_region.setEnabled(False)

    def _save_symbol(self):
        """Save the symbol definition."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Bitte geben Sie einen Namen ein.")
            return

        if len(self.all_crops) < 3:
            QMessageBox.warning(self, "Fehler", "Bitte markieren Sie mindestens 3 Beispiele (können aus mehreren Bildern stammen).")
            return

        try:
            # Use all_crops collected from all images
            crops = self.all_crops
            print(f"[DEBUG] Using {len(crops)} crops from {len(self.images)} image(s)")

            # Get settings
            method_map = {
                "Automatisch": "auto",
                "Template": "template",
                "Kontur": "contour",
                "Kreis": "circle",
            }
            position_map = {
                "unten": "below",
                "oben": "above",
                "links": "left",
                "rechts": "right",
                "innen": "inside",
                "beliebig (alle Richtungen)": "any",
                "unten-rechts": "below_right",
                "unten-links": "below_left",
                "oben-rechts": "above_right",
                "oben-links": "above_left",
            }

            selected_method = self.method_combo.currentText()
            print(f"[DEBUG] Selected method: {selected_method}")

            # Calculate text region offset if defined
            text_region_offset = None
            if self.text_region and self.examples:
                # Calculate offset relative to first symbol's center
                sym_x1, sym_y1, sym_x2, sym_y2 = self.examples[0]
                sym_cx = (sym_x1 + sym_x2) / 2
                sym_cy = (sym_y1 + sym_y2) / 2

                txt_x1, txt_y1, txt_x2, txt_y2 = self.text_region
                txt_cx = (txt_x1 + txt_x2) / 2
                txt_cy = (txt_y1 + txt_y2) / 2

                # Offset from symbol center to text region center
                dx = int(txt_cx - sym_cx)
                dy = int(txt_cy - sym_cy)
                tw = int(txt_x2 - txt_x1)
                th = int(txt_y2 - txt_y1)

                text_region_offset = {
                    "dx": dx,  # X offset from symbol center
                    "dy": dy,  # Y offset from symbol center
                    "width": tw,  # Width of text region
                    "height": th,  # Height of text region
                }
                print(f"[DEBUG] Text region offset: {text_region_offset}")

            # Create symbol using detector
            from core.symbol_detector import NewSymbolDetector

            print("[DEBUG] Creating NewSymbolDetector...")
            detector = NewSymbolDetector()

            print("[DEBUG] Adding symbol from examples...")
            # Get selected positions (now supports multi-select)
            text_positions = self._get_selected_text_positions()
            coord_positions = self._get_selected_coord_positions()
            print(f"[DEBUG] Text positions: {text_positions}")
            print(f"[DEBUG] Coord positions: {coord_positions}")

            detector.add_symbol_from_examples(
                name=name,
                example_crops=crops,
                has_text=self.has_text_check.isChecked(),
                text_position=text_positions,  # Now a list
                text_region_offset=text_region_offset,
                links_to_coordinate=self.links_coord_check.isChecked(),
                coordinate_position=coord_positions,  # Now a list
                similarity_threshold=self.threshold_slider.value() / 100.0,
            )

            print(f"[DEBUG] Symbol '{name}' saved successfully!")

            QMessageBox.information(
                self,
                "Erfolg",
                f"Symbol '{name}' wurde gespeichert!\n\n"
                f"Es wird ab dem nächsten Durchlauf erkannt."
            )

            self.symbol_defined.emit(name)
            self.accept()

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"[ERROR] Save failed: {error_details}")
            QMessageBox.critical(
                self,
                "Fehler beim Speichern",
                f"Symbol konnte nicht gespeichert werden:\n\n{str(e)}\n\nDetails in der Konsole."
            )


class UnknownSymbolsDialog(QDialog):
    """
    Dialog showing automatically detected unknown symbols.
    User can confirm and name them.
    """

    def __init__(self, unknown_clusters: List[Dict], image: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unbekannte Symbole gefunden")
        w, h = get_adaptive_window_size(800, 600, max_screen_pct=0.70)
        self.setMinimumSize(w, h)
        center_window(self)

        self.clusters = unknown_clusters
        self.image = image

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"<b> {len(self.clusters)} mögliche unbekannte Symbol-Typen gefunden!</b><br><br>"
            "Das System hat Objekte gefunden, die wie Symbole aussehen, "
            "aber von YOLO nicht erkannt wurden."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Table of unknown symbols
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Vorschau", "Anzahl", "Aktion", "Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setRowCount(len(self.clusters))

        for i, cluster in enumerate(self.clusters):
            # Preview image
            rep = cluster["representative"]
            crop = rep.get("crop")
            if crop is not None:
                h, w = crop.shape[:2]
                if len(crop.shape) == 2:
                    q_img = QtGui.QImage(crop.data, w, h, w, QtGui.QImage.Format_Grayscale8)
                else:
                    q_img = QtGui.QImage(crop.data, w, h, 3*w, QtGui.QImage.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(q_img).scaled(50, 50, Qt.KeepAspectRatio)
                label = QLabel()
                label.setPixmap(pixmap)
                self.table.setCellWidget(i, 0, label)

            # Count
            count = len(cluster["instances"])
            self.table.setItem(i, 1, QTableWidgetItem(f"{count}x"))

            # Action combo
            action_combo = QComboBox()
            action_combo.addItems(["Ignorieren", "Als Symbol definieren"])
            self.table.setCellWidget(i, 2, action_combo)

            # Name input
            name_input = QLineEdit()
            name_input.setPlaceholderText("Symbol-Name")
            name_input.setEnabled(False)
            action_combo.currentTextChanged.connect(
                lambda text, inp=name_input: inp.setEnabled(text == "Als Symbol definieren")
            )
            self.table.setCellWidget(i, 3, name_input)

        layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        btn_cancel = QPushButton("Später")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Ausgewählte speichern")
        btn_save.clicked.connect(self._save_selected)
        button_layout.addWidget(btn_save)

        layout.addLayout(button_layout)

    def _save_selected(self):
        """Save selected symbols."""
        from core.symbol_detector import NewSymbolDetector

        detector = NewSymbolDetector()
        saved_count = 0

        for i, cluster in enumerate(self.clusters):
            action_combo = self.table.cellWidget(i, 2)
            name_input = self.table.cellWidget(i, 3)

            if action_combo.currentText() == "Als Symbol definieren":
                name = name_input.text().strip()
                if name:
                    # Collect crops from cluster instances
                    crops = []
                    for instance in cluster["instances"][:5]:  # Max 5 examples
                        crop = instance.get("crop")
                        if crop is not None:
                            crops.append(crop)

                    if crops:
                        detector.add_symbol_from_examples(
                            name=name,
                            example_crops=crops,
                        )
                        saved_count += 1

        if saved_count > 0:
            QMessageBox.information(
                self,
                "Erfolg",
                f"{saved_count} Symbol(e) wurden gespeichert!"
            )

        self.accept()


class RetrainingDialog(QDialog):
    """
    Dialog for fine-tuning YOLO with new symbols (CPU supported).
    """

    def __init__(self, model_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YOLO Fine-Tuning")
        w, h = get_adaptive_window_size(500, 400, max_screen_pct=0.50)
        self.setMinimumSize(w, h)
        center_window(self)

        self.model_path = model_path

        self._build_ui()
        self._update_stats()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            "<b>YOLO Fine-Tuning</b><br><br>"
            "Trainieren Sie das YOLO-Modell mit neuen Symbolen für höhere Genauigkeit.<br>"
            " CPU-Training ist langsam (2-4 Stunden), aber funktioniert!"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Stats
        stats_group = QGroupBox("Training-Daten")
        stats_layout = QFormLayout(stats_group)
        self.stats_label = QLabel("Lade...")
        stats_layout.addRow("Beispiele:", self.stats_label)
        layout.addWidget(stats_group)

        # Settings
        settings_group = QGroupBox("Einstellungen")
        settings_layout = QFormLayout(settings_group)

        self.device_combo = QComboBox()
        self.device_combo.addItems(["CPU", "GPU (CUDA)"])
        self.device_combo.currentTextChanged.connect(self._update_time_estimate)
        settings_layout.addRow("Gerät:", self.device_combo)

        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(5, 100)
        self.epochs_spin.setValue(20)
        self.epochs_spin.valueChanged.connect(self._update_time_estimate)
        settings_layout.addRow("Epochen:", self.epochs_spin)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 32)
        self.batch_spin.setValue(4)
        settings_layout.addRow("Batch-Größe:", self.batch_spin)

        self.time_estimate_label = QLabel("")
        settings_layout.addRow("Geschätzte Zeit:", self.time_estimate_label)

        layout.addWidget(settings_group)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)

        self.btn_start = QPushButton(" Training starten")
        self.btn_start.clicked.connect(self._start_training)
        button_layout.addWidget(self.btn_start)

        layout.addLayout(button_layout)

    def _update_stats(self):
        from core.symbol_detector import SymbolRetrainer

        retrainer = SymbolRetrainer(self.model_path)
        stats = retrainer.get_training_stats()
        self.stats_label.setText(f"{stats.get('examples', 0)} Bilder")
        self._update_time_estimate()

    def _update_time_estimate(self):
        from core.symbol_detector import SymbolRetrainer

        device = "cpu" if self.device_combo.currentText() == "CPU" else "cuda"
        epochs = self.epochs_spin.value()

        retrainer = SymbolRetrainer(self.model_path)
        estimate = retrainer.estimate_training_time(epochs, device)
        self.time_estimate_label.setText(estimate)

    def _start_training(self):
        """Start the fine-tuning process."""
        # This would run in a separate thread in production
        QMessageBox.information(
            self,
            "Training",
            "Training würde jetzt starten.\n\n"
            "In einer vollständigen Implementierung würde dies "
            "in einem Hintergrund-Thread laufen."
        )