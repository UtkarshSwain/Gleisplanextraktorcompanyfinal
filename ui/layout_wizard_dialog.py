# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Interactive Layout Configuration Wizard UI

Provides a simple step-by-step wizard for creating new layout profiles.
The user only needs to:
1. Drop in 3-5 sample PDFs
2. Click on examples of each element type
3. Review auto-detected elements
4. Done - profile is generated automatically!
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit, QTextEdit,
    QProgressBar, QCheckBox, QSpinBox, QComboBox, QFileDialog,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem,
    QMessageBox, QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFrame
)
from typing import List, Dict, Optional, Tuple
import numpy as np
from pathlib import Path
from utils.dpi_utils import get_adaptive_window_size, center_window, scale_value


class ClickableGraphicsView(QGraphicsView):
    """Graphics view that emits click coordinates."""

    clicked = pyqtSignal(float, float)  # x, y in scene coordinates
    box_drawn = pyqtSignal(float, float, float, float)  # x1, y1, x2, y2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.drawing_mode = "click"  # "click" or "box"
        self._start_point = None
        self._current_rect = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())

            if self.drawing_mode == "click":
                self.clicked.emit(scene_pos.x(), scene_pos.y())
            elif self.drawing_mode == "box":
                self._start_point = scene_pos

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing_mode == "box":
            if self._start_point:
                end_pos = self.mapToScene(event.pos())
                x1 = min(self._start_point.x(), end_pos.x())
                y1 = min(self._start_point.y(), end_pos.y())
                x2 = max(self._start_point.x(), end_pos.x())
                y2 = max(self._start_point.y(), end_pos.y())

                if (x2 - x1) > 10 and (y2 - y1) > 10:  # Min size
                    self.box_drawn.emit(x1, y1, x2, y2)

                self._start_point = None

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


class LayoutWizardDialog(QDialog):
    """
    Main wizard dialog for creating new layout profiles.

    Steps:
    1. Welcome & Name - Enter profile name
    2. Load Samples - Drag & drop sample PDFs
    3. Define Classes - Click on examples of each element type
    4. Auto-Detect - System finds more instances
    5. Review & Tune - Adjust thresholds
    6. Generate - Create profile file
    """

    profile_created = pyqtSignal(str)  # Emits path to created profile

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Layout Configuration Wizard")

        # Adaptive sizing for different DPI settings
        w, h = get_adaptive_window_size(1200, 800, max_screen_pct=0.85)
        self.setMinimumSize(w, h)
        center_window(self)

        # Wizard state
        self.wizard = None  # LayoutWizard instance
        self.current_step = 0
        self.profile_name = ""
        self.sample_paths: List[str] = []
        self.current_image_key = None
        self.defined_classes: Dict[str, List] = {}
        self.class_colors: Dict[str, QtGui.QColor] = {}

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header with step indicator
        self.header = self._create_header()
        layout.addWidget(self.header)

        # Main content area (stacked widget for steps)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Create step pages
        self.stack.addWidget(self._create_welcome_page())      # 0
        self.stack.addWidget(self._create_samples_page())      # 1
        self.stack.addWidget(self._create_classes_page())      # 2
        self.stack.addWidget(self._create_auto_detect_page())  # 3
        self.stack.addWidget(self._create_review_page())       # 4
        self.stack.addWidget(self._create_generate_page())     # 5

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Back")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_next = QPushButton("Next →")
        self.btn_next.clicked.connect(self._go_next)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_cancel)
        nav_layout.addWidget(self.btn_next)
        layout.addLayout(nav_layout)

        self._update_navigation()

    def _create_header(self) -> QFrame:
        """Create header with step indicator."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        layout = QHBoxLayout(frame)

        steps = [
            "1. Name",
            "2. Samples",
            "3. Define Classes",
            "4. Auto-Detect",
            "5. Review",
            "6. Generate"
        ]

        self.step_labels = []
        for i, step in enumerate(steps):
            label = QLabel(step)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("padding: 8px;")
            self.step_labels.append(label)
            layout.addWidget(label)

        return frame

    def _update_header(self):
        """Highlight current step in header."""
        for i, label in enumerate(self.step_labels):
            if i == self.current_step:
                label.setStyleSheet("padding: 8px; background: #4CAF50; color: white; border-radius: 4px;")
            elif i < self.current_step:
                label.setStyleSheet("padding: 8px; background: #8BC34A; color: white; border-radius: 4px;")
            else:
                label.setStyleSheet("padding: 8px; background: #E0E0E0; border-radius: 4px;")

    # =========================================================================
    # Step 1: Welcome & Name
    # =========================================================================

    def _create_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        # Title
        title = QLabel(" New Layout Configuration Wizard")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        # Description
        desc = QLabel("""
        This wizard will help you configure extraction for a new track layout type.

        You only need to:
        1. Provide 3-5 sample PDFs
        2. Click on a few examples of each element type
        3. Review the auto-detected elements

        The system will learn the rest automatically!
        """)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)

        layout.addSpacing(30)

        # Profile name input
        name_layout = QHBoxLayout()
        name_layout.addStretch()
        name_layout.addWidget(QLabel("Profile Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., layout_type_b")
        self.name_input.setMinimumWidth(scale_value(300))
        name_layout.addWidget(self.name_input)
        name_layout.addStretch()
        layout.addLayout(name_layout)

        layout.addStretch()

        return page

    # =========================================================================
    # Step 2: Load Samples
    # =========================================================================

    def _create_samples_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        # Instructions
        instructions = QLabel("""
        <b>Step 2: Load Sample Documents</b><br><br>
        Drag and drop 3-5 sample Gleisplan files from the new layout type.<br>
        Supported formats: PDF, PNG, JPEG, TIFF, BMP<br>
        These will be analyzed to auto-detect layout parameters.
        """)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Drop area
        self.drop_area = QLabel(" Drop Gleisplan files here\n\nor click to browse")
        self.drop_area.setAlignment(Qt.AlignCenter)
        self.drop_area.setStyleSheet("""
            QLabel {
                border: 2px dashed #BDBDBD;
                border-radius: 10px;
                padding: 40px;
                background: #FAFAFA;
                font-size: 16px;
            }
            QLabel:hover {
                border-color: #4CAF50;
                background: #E8F5E9;
            }
        """)
        self.drop_area.setMinimumHeight(scale_value(200))
        self.drop_area.mousePressEvent = self._browse_pdfs
        layout.addWidget(self.drop_area)

        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(scale_value(150))
        layout.addWidget(self.file_list)

        # Analysis results
        self.analysis_label = QLabel("")
        self.analysis_label.setWordWrap(True)
        layout.addWidget(self.analysis_label)

        layout.addStretch()

        # Enable drop
        page.setAcceptDrops(True)
        page.dragEnterEvent = self._drag_enter
        page.dropEvent = self._drop_files

        return page

    def _drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _drop_files(self, event):
        gleisplan_exts = ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(gleisplan_exts):
                self._add_sample_file(path)

    def _browse_pdfs(self, event):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Sample Gleispläne", "",
            "Alle Gleispläne (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
            "PDF Dateien (*.pdf);;"
            "Bilder (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
            "Alle Dateien (*.*)"
        )
        for f in files:
            self._add_sample_file(f)

    def _add_sample_file(self, path: str):
        if path not in self.sample_paths:
            self.sample_paths.append(path)
            self.file_list.addItem(Path(path).name)

    # =========================================================================
    # Step 3: Define Classes
    # =========================================================================

    def _create_classes_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)

        # Left panel - class list
        left_panel = QVBoxLayout()

        left_panel.addWidget(QLabel("<b>Element Classes</b>"))

        # Add class controls
        add_layout = QHBoxLayout()
        self.new_class_input = QLineEdit()
        self.new_class_input.setPlaceholderText("Class name (e.g., signal)")
        add_layout.addWidget(self.new_class_input)

        self.btn_add_class = QPushButton("+ Add")
        self.btn_add_class.clicked.connect(self._add_class)
        add_layout.addWidget(self.btn_add_class)
        left_panel.addLayout(add_layout)

        # Class list
        self.class_list = QListWidget()
        self.class_list.currentItemChanged.connect(self._on_class_selected)
        left_panel.addWidget(self.class_list)

        # Class options
        options_group = QGroupBox("Class Options")
        options_layout = QFormLayout(options_group)

        self.chk_has_text = QCheckBox()
        self.chk_has_text.setChecked(True)
        options_layout.addRow("Has Text (needs OCR):", self.chk_has_text)

        self.spin_box_width = QSpinBox()
        self.spin_box_width.setRange(20, 500)
        self.spin_box_width.setValue(100)
        options_layout.addRow("Approx. Width (px):", self.spin_box_width)

        self.spin_box_height = QSpinBox()
        self.spin_box_height.setRange(20, 500)
        self.spin_box_height.setValue(50)
        options_layout.addRow("Approx. Height (px):", self.spin_box_height)

        left_panel.addWidget(options_group)

        # Example count
        self.example_count_label = QLabel("Examples: 0")
        left_panel.addWidget(self.example_count_label)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMaximumWidth(scale_value(300))
        layout.addWidget(left_widget)

        # Right panel - image view
        right_panel = QVBoxLayout()

        right_panel.addWidget(QLabel("<b>Click on examples of the selected class</b>"))

        # Image selector
        img_select = QHBoxLayout()
        img_select.addWidget(QLabel("Sample:"))
        self.image_combo = QComboBox()
        self.image_combo.currentTextChanged.connect(self._on_image_selected)
        img_select.addWidget(self.image_combo, 1)
        right_panel.addLayout(img_select)

        # Graphics view for clicking
        self.class_view = ClickableGraphicsView()
        self.class_scene = QGraphicsScene()
        self.class_view.setScene(self.class_scene)
        self.class_view.clicked.connect(self._on_image_clicked)
        right_panel.addWidget(self.class_view, 1)

        # Undo button
        self.btn_undo_click = QPushButton("↩ Undo Last Click")
        self.btn_undo_click.clicked.connect(self._undo_last_click)
        right_panel.addWidget(self.btn_undo_click)

        layout.addLayout(right_panel, 1)

        return page

    def _add_class(self):
        name = self.new_class_input.text().strip()
        if name and name not in self.defined_classes:
            self.defined_classes[name] = []
            # Generate color
            color = QtGui.QColor.fromHsv(
                (len(self.defined_classes) * 137) % 360, 200, 255
            )
            self.class_colors[name] = color

            item = QListWidgetItem(name)
            item.setBackground(QtGui.QBrush(color.lighter(150)))
            self.class_list.addItem(item)
            self.new_class_input.clear()
            self.class_list.setCurrentItem(item)

    def _on_class_selected(self, current, previous):
        self._update_example_count()

    def _on_image_selected(self, image_key: str):
        self.current_image_key = image_key
        self._display_image(image_key)

    def _display_image(self, image_key: str):
        if not self.wizard or image_key not in self.wizard.sample_images:
            return

        self.class_scene.clear()

        # Convert numpy to QPixmap
        img = self.wizard.sample_images[image_key]
        if len(img.shape) == 3:
            h, w, c = img.shape
            bytes_per_line = 3 * w
            q_img = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        else:
            h, w = img.shape
            bytes_per_line = w
            q_img = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format_Grayscale8)

        pixmap = QtGui.QPixmap.fromImage(q_img)
        self.class_scene.addPixmap(pixmap)
        self.class_scene.setSceneRect(QtCore.QRectF(pixmap.rect()))

        # Draw existing annotations
        self._draw_annotations()

        # Fit to view
        self.class_view.fitInView(self.class_scene.sceneRect(), Qt.KeepAspectRatio)

    def _draw_annotations(self):
        """Draw all annotation boxes on the current image."""
        for class_name, examples in self.defined_classes.items():
            color = self.class_colors.get(class_name, QtGui.QColor(255, 0, 0))
            for (x, y, w, h) in examples:
                rect = QGraphicsRectItem(x - w/2, y - h/2, w, h)
                rect.setPen(QtGui.QPen(color, 3))
                rect.setBrush(QtGui.QBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 50)))
                self.class_scene.addItem(rect)

                # Add label
                text = self.class_scene.addText(class_name)
                text.setPos(x - w/2, y - h/2 - 20)
                text.setDefaultTextColor(color)

    def _on_image_clicked(self, x: float, y: float):
        current_item = self.class_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Class Selected", "Please select or create a class first.")
            return

        class_name = current_item.text()
        w = self.spin_box_width.value()
        h = self.spin_box_height.value()

        self.defined_classes[class_name].append((x, y, w, h))
        self._update_example_count()
        self._display_image(self.current_image_key)

    def _undo_last_click(self):
        current_item = self.class_list.currentItem()
        if current_item:
            class_name = current_item.text()
            if self.defined_classes[class_name]:
                self.defined_classes[class_name].pop()
                self._update_example_count()
                self._display_image(self.current_image_key)

    def _update_example_count(self):
        current_item = self.class_list.currentItem()
        if current_item:
            class_name = current_item.text()
            count = len(self.defined_classes.get(class_name, []))
            self.example_count_label.setText(f"Examples: {count}")
        else:
            self.example_count_label.setText("Examples: 0")

    # =========================================================================
    # Step 4: Auto-Detect
    # =========================================================================

    def _create_auto_detect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        instructions = QLabel("""
        <b>Step 4: Automatic Detection</b><br><br>
        The system will now find more instances of each element type
        based on your examples. This may take a few minutes.
        """)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Progress
        self.detect_progress = QProgressBar()
        layout.addWidget(self.detect_progress)

        self.detect_status = QLabel("")
        layout.addWidget(self.detect_status)

        # Results table
        self.detect_table = QTableWidget()
        self.detect_table.setColumnCount(3)
        self.detect_table.setHorizontalHeaderLabels(["Class", "Your Examples", "Auto-Detected"])
        self.detect_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.detect_table)

        # Option to use existing model
        model_group = QGroupBox("Use Existing Model (Optional)")
        model_layout = QHBoxLayout(model_group)
        self.model_path_input = QLineEdit()
        self.model_path_input.setPlaceholderText("Path to existing YOLO model (.pt)")
        model_layout.addWidget(self.model_path_input)
        btn_browse_model = QPushButton("Browse...")
        btn_browse_model.clicked.connect(self._browse_model)
        model_layout.addWidget(btn_browse_model)
        layout.addWidget(model_group)

        layout.addStretch()

        return page

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Model", "", "PyTorch Weights (*.pt)"
        )
        if path:
            self.model_path_input.setText(path)

    def _run_auto_detection(self):
        """Run auto-detection for all classes."""
        if not self.wizard:
            return

        self.detect_table.setRowCount(len(self.defined_classes))

        for i, (class_name, examples) in enumerate(self.defined_classes.items()):
            self.detect_status.setText(f"Detecting {class_name}...")
            self.detect_progress.setValue(int((i / len(self.defined_classes)) * 100))
            QtWidgets.QApplication.processEvents()

            # Convert our examples to wizard format
            for (x, y, w, h) in examples:
                # Get first image key
                if self.wizard.sample_images:
                    image_key = list(self.wizard.sample_images.keys())[0]
                    self.wizard.define_class_from_clicks(
                        class_name,
                        image_key,
                        [(int(x), int(y))],
                        box_size=(int(w), int(h)),
                        has_text=self.chk_has_text.isChecked()
                    )

            # Run auto-detection
            try:
                auto_detected = self.wizard.auto_detect_similar(class_name)
                auto_count = len(auto_detected)
            except Exception as e:
                auto_count = 0

            # Update table
            self.detect_table.setItem(i, 0, QTableWidgetItem(class_name))
            self.detect_table.setItem(i, 1, QTableWidgetItem(str(len(examples))))
            self.detect_table.setItem(i, 2, QTableWidgetItem(str(auto_count)))

        self.detect_progress.setValue(100)
        self.detect_status.setText("Detection complete!")

    # =========================================================================
    # Step 5: Review
    # =========================================================================

    def _create_review_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        instructions = QLabel("""
        <b>Step 5: Review & Adjust</b><br><br>
        Review the detected elements and adjust confidence thresholds.
        You can also correct any misdetections.
        """)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Threshold adjustments
        self.threshold_table = QTableWidget()
        self.threshold_table.setColumnCount(4)
        self.threshold_table.setHorizontalHeaderLabels([
            "Class", "Confidence", "Has OCR", "ID Pattern"
        ])
        self.threshold_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.threshold_table)

        # Preview view
        self.review_view = ClickableGraphicsView()
        self.review_scene = QGraphicsScene()
        self.review_view.setScene(self.review_scene)
        layout.addWidget(self.review_view, 1)

        return page

    def _populate_review_page(self):
        """Populate review page with detected classes."""
        self.threshold_table.setRowCount(len(self.defined_classes))

        for i, class_name in enumerate(self.defined_classes.keys()):
            self.threshold_table.setItem(i, 0, QTableWidgetItem(class_name))

            # Confidence spinbox
            conf_spin = QtWidgets.QDoubleSpinBox()
            conf_spin.setRange(0.1, 1.0)
            conf_spin.setSingleStep(0.05)
            conf_spin.setValue(0.5)
            self.threshold_table.setCellWidget(i, 1, conf_spin)

            # Has OCR checkbox
            ocr_check = QCheckBox()
            ocr_check.setChecked(True)
            self.threshold_table.setCellWidget(i, 2, ocr_check)

            # ID pattern
            pattern_edit = QLineEdit()
            pattern_edit.setPlaceholderText("e.g., ^[A-Z]\\d+$")
            self.threshold_table.setCellWidget(i, 3, pattern_edit)

    # =========================================================================
    # Step 6: Generate
    # =========================================================================

    def _create_generate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        instructions = QLabel("""
        <b>Step 6: Generate Profile</b><br><br>
        Your layout profile is ready to be generated!
        """)
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Summary
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)

        # Generate button
        self.btn_generate = QPushButton(" Generate Profile")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                padding: 15px;
                font-size: 18px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #388E3C;
            }
        """)
        self.btn_generate.clicked.connect(self._generate_profile)
        layout.addWidget(self.btn_generate)

        self.generate_status = QLabel("")
        self.generate_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.generate_status)

        layout.addStretch()

        return page

    def _update_summary(self):
        """Update the summary text."""
        summary = f"""
Profile Name: {self.profile_name}

Sample Documents: {len(self.sample_paths)}

Element Classes:
"""
        for class_name, examples in self.defined_classes.items():
            auto_count = len(self.wizard.auto_detected.get(class_name, [])) if self.wizard else 0
            summary += f"  • {class_name}: {len(examples)} examples, {auto_count} auto-detected\n"

        if self.wizard and self.wizard.analysis:
            summary += f"""
Detected Parameters:
  • DPI: {self.wizard.analysis.detected_dpi}
  • Color Scheme: {self.wizard.analysis.detected_color_scheme}
  • Coordinate Format: {self.wizard.analysis.coordinate_format or 'Unknown'}
  • Tile Size: {self.wizard.analysis.suggested_tile_size}
"""

        self.summary_text.setText(summary)

    def _generate_profile(self):
        """Generate the final profile."""
        if not self.wizard:
            return

        try:
            # Collect threshold settings from review table
            for i in range(self.threshold_table.rowCount()):
                class_name = self.threshold_table.item(i, 0).text()
                conf_widget = self.threshold_table.cellWidget(i, 1)
                # Would apply these settings to the wizard

            # Generate profile
            profile_dict = self.wizard.generate_profile(
                description=f"Auto-generated profile for {self.profile_name}",
                base_model_path=self.model_path_input.text() or None,
            )

            profile_path = Path("profiles") / f"{self.profile_name}.yaml"
            self.generate_status.setText(f" Profile saved to: {profile_path}")
            self.generate_status.setStyleSheet("color: green; font-size: 16px;")

            self.profile_created.emit(str(profile_path))

        except Exception as e:
            self.generate_status.setText(f" Error: {str(e)}")
            self.generate_status.setStyleSheet("color: red;")

    # =========================================================================
    # Navigation
    # =========================================================================

    def _go_back(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.stack.setCurrentIndex(self.current_step)
            self._update_navigation()

    def _go_next(self):
        # Validate current step
        if not self._validate_step():
            return

        # Process step transition
        self._process_step_transition()

        if self.current_step < 5:
            self.current_step += 1
            self.stack.setCurrentIndex(self.current_step)
            self._update_navigation()

    def _validate_step(self) -> bool:
        if self.current_step == 0:
            name = self.name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "Name Required", "Please enter a profile name.")
                return False
            self.profile_name = name

        elif self.current_step == 1:
            if len(self.sample_paths) < 1:
                QMessageBox.warning(self, "Samples Required", "Please add at least one sample Gleisplan.")
                return False

        elif self.current_step == 2:
            if not self.defined_classes:
                QMessageBox.warning(self, "Classes Required", "Please define at least one element class.")
                return False
            # Check that each class has at least one example
            for class_name, examples in self.defined_classes.items():
                if len(examples) < 1:
                    QMessageBox.warning(
                        self, "Examples Required",
                        f"Please click on at least one example for class '{class_name}'."
                    )
                    return False

        return True

    def _process_step_transition(self):
        """Process actions when moving to next step."""
        if self.current_step == 1:
            # After samples page - initialize wizard and analyze
            from core.layout_wizard import LayoutWizard
            self.wizard = LayoutWizard(self.profile_name)

            try:
                analysis = self.wizard.analyze_samples(self.sample_paths)
                self.analysis_label.setText(f"""
                    <b>Analysis Results:</b><br>
                    • DPI: {analysis.detected_dpi}<br>
                    • Color: {analysis.detected_color_scheme}<br>
                    • Orientation: {analysis.detected_orientation}<br>
                    • Coordinate Format: {analysis.coordinate_format or 'Unknown'}<br>
                    • Suggested Tile Size: {analysis.suggested_tile_size}
                """)

                # Populate image combo for class definition
                self.image_combo.clear()
                for key in self.wizard.sample_images.keys():
                    self.image_combo.addItem(key)

            except Exception as e:
                QMessageBox.critical(self, "Analysis Failed", str(e))

        elif self.current_step == 3:
            # Run auto-detection
            self._run_auto_detection()

        elif self.current_step == 4:
            # Populate review page
            self._populate_review_page()

        elif self.current_step == 5:
            # Update summary
            self._update_summary()

    def _update_navigation(self):
        """Update navigation button states."""
        self.btn_back.setEnabled(self.current_step > 0)
        self.btn_next.setText("Generate" if self.current_step == 4 else "Next →")
        self.btn_next.setVisible(self.current_step < 5)
        self._update_header()
