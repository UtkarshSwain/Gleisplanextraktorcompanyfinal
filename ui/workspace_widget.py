from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Dict, Tuple, Optional, Any
import pandas as pd
from ui.themes import LIGHT_QSS, DARK_QSS
from utils.dpi_utils import scale_value, get_scaled_font
from core.linking import parse_coord, detect_fahrtrichtung, detect_fahrtrichtung_gks_relaxed, detect_fahrtrichtung_gks_nearest
import os
import numpy as np
from uservalidation.ultimate_validator import validate_everything
from uservalidation.validation_dialog_helper import ValidationDialogWithJump
from uservalidation.validation_dialog2 import EnhancedValidationResultsDialog
from uservalidation.validation_dialog2 import EnhancedDataValidator
from ui.quality_inspector import QualityInspectorDialog
import json
from core.pipelineworker import NO_OCR_CLASSES
import math
import re
from core.ocr_engine import manual_angular_ocr, ocr_coordinate_horizontal, ocr_coordinate_angular, ocr_signal_name
import cv2
from ui.graphics_view import InteractiveGraphicsView
from ui.resizable_bbox import ResizableBBoxItem, ResizablePolygonBBoxItem
from core.ocr_engine import paddleocr_recognize, ocr_numeric_cardinal_box, ocr_numeric_tilted_box, ocr_generic_name, NUMERIC_OK
from ui.ocr_adjustment_dialog import OCRAdjustmentDialog, OCRAdjustmentTracker, AutoLearningSuggestionDialog
from config import ZOOM_SIZE
from utils.helpers import _is_deleted
from core.image_processing import qpolygonf_from_pts
from PIL import Image, ImageFile
from typing import TYPE_CHECKING

# Import shared validation config for consistent risk calculation
from validation_config import (
    CLASSES_REQUIRING_COORDINATES,
    CLASSES_REQUIRING_TEXT,
    CLASSES_EXCLUDED,
    RISK_WEIGHTS,
    RISK_THRESHOLDS,
    RISK_LABELS,
    RISK_FACTOR_LABELS,
    get_confidence_threshold,
    needs_coordinate as config_needs_coordinate,
    needs_text as config_needs_text,
    is_excluded as config_is_excluded,
    get_risk_level,
    get_risk_label,
)
if TYPE_CHECKING:
    from ui.auditing_window import AuditingWindow

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def bbox_to_rotated_poly(x1, y1, x2, y2, angle_deg):
    """
    Convert axis-aligned bbox + angle to rotated polygon (4 corner points).

    Args:
        x1, y1, x2, y2: Axis-aligned bounding box coordinates
        angle_deg: Rotation angle in degrees (YOLO angle format)

    Returns:
        np.ndarray: 4x2 array of corner points
    """
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    w = x2 - x1
    h = y2 - y1

    # Convert angle to radians
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Four corners relative to center
    corners = np.array([
        [-w/2, -h/2],  # Top-left
        [w/2, -h/2],   # Top-right
        [w/2, h/2],    # Bottom-right
        [-w/2, h/2]    # Bottom-left
    ])

    # Rotate corners
    rotated = np.zeros_like(corners)
    rotated[:, 0] = corners[:, 0] * cos_a - corners[:, 1] * sin_a
    rotated[:, 1] = corners[:, 0] * sin_a + corners[:, 1] * cos_a

    # Translate to center position
    rotated[:, 0] += cx
    rotated[:, 1] += cy

    return rotated.astype(np.float32)

# ============================================================================
# RISK SCORE HELPERS - Using shared validation_config.py
# ============================================================================
def calculate_row_risk_score(row: pd.Series, custom_symbol_config: dict = None) -> tuple:
    """
    Calculate risk score for a single row using shared validation config.

    Uses weights and thresholds from validation_config.py for consistency
    across all validation systems (Erkennungsqualität, Datenvalidierung, Counter Bar).

    Args:
        row: DataFrame row
        custom_symbol_config: Optional dict of custom symbol configurations

    Returns:
        tuple of (risk_score, risk_factors_list)
    """
    risk = 0.0
    factors = []

    if custom_symbol_config is None:
        custom_symbol_config = {}

    cls = row.get('cls', '')
    is_custom = row.get('is_custom_symbol', False) == True or row.get('is_new_symbol', False) == True

    # Determine requirements based on symbol type
    if is_custom and cls in custom_symbol_config:
        sym_config = custom_symbol_config[cls]
        requires_coord = sym_config.get('links_to_coordinate', False)
        requires_text = sym_config.get('has_text', False)
    else:
        # Use shared config
        requires_coord = config_needs_coordinate(cls)
        requires_text = config_needs_text(cls)

    # Factor 1: Confidence Risk (uses per-class thresholds from shared config)
    conf = row.get('conf', 1.0)
    if pd.notna(conf):
        threshold = get_confidence_threshold(cls)
        if float(conf) < threshold:
            conf_risk = (1.0 - float(conf)) * RISK_WEIGHTS['low_confidence']
            risk += conf_risk
            factors.append(RISK_FACTOR_LABELS['low_confidence'])

    # Factor 2: Missing Required Coordinate
    if requires_coord:
        if pd.isna(row.get('coord_text')) or not str(row.get('coord_text', '')).strip():
            risk += RISK_WEIGHTS['missing_coordinate']
            factors.append(RISK_FACTOR_LABELS['missing_coordinate'])

    # Factor 3: Missing Required Text
    if requires_text:
        if pd.isna(row.get('anchor_text')) or not str(row.get('anchor_text', '')).strip():
            risk += RISK_WEIGHTS['missing_text']
            factors.append(RISK_FACTOR_LABELS['missing_text'])

    # Factor 4: Invalid Coordinate Start
    if cls != 'coordinate' and pd.notna(row.get('coord_text')):
        coord_text_val = str(row.get('coord_text', '')).strip()
        if coord_text_val and not (coord_text_val[0].isdigit() or coord_text_val[0] == '-'):
            risk += RISK_WEIGHTS['invalid_coordinate']
            factors.append(RISK_FACTOR_LABELS['invalid_coordinate'])

    # Factor 5: GKS Contains Letters
    if cls in ['gks_gesteuert', 'gks_festkodiert']:
        gks_text = str(row.get('anchor_text', '')).strip()
        if gks_text:
            cleaned = gks_text.replace(' ', '').replace('-', '')
            if cleaned and not cleaned.isdigit():
                risk += RISK_WEIGHTS['gks_letters']
                factors.append(RISK_FACTOR_LABELS['gks_letters'])

    # Factor 6: Size Anomaly
    if 'w' in row.index and 'h' in row.index:
        w, h = row.get('w'), row.get('h')
        if pd.notna(w) and pd.notna(h):
            area = float(w) * float(h)
            if area < 100 or area > 50000:
                risk += RISK_WEIGHTS['size_anomaly']
                factors.append(RISK_FACTOR_LABELS['size_anomaly'])

    # Factor 7: Formatting Errors (multiple spaces)
    anchor_text = str(row.get('anchor_text', ''))
    coord_text_val = str(row.get('coord_text', '')) if cls != 'coordinate' else ''
    if '  ' in coord_text_val or '  ' in anchor_text:
        risk += RISK_WEIGHTS['formatting_error']
        factors.append(RISK_FACTOR_LABELS['formatting_error'])

    return (min(risk, 1.0), factors)


def get_risk_status(risk_score: float) -> dict:
    """
    Get user-friendly risk status using shared validation config thresholds.

    Args:
        risk_score: Risk score (0.0 to 1.0)

    Returns:
        dict with 'label', 'color', 'bg_color', 'icon', 'priority', 'category'
    """
    risk_level = get_risk_level(risk_score)

    if risk_level == 'high_risk':
        return {
            'label': RISK_LABELS['high_risk'],
            'color': '#ff6b6b',
            'bg_color': '#5c1a1a',
            'icon': '',
            'priority': 2,
            'category': 'high_risk'
        }
    elif risk_level == 'medium_risk':
        return {
            'label': RISK_LABELS['medium_risk'],
            'color': '#ffd93d',
            'bg_color': '#4a4020',
            'icon': '',
            'priority': 1,
            'category': 'medium_risk'
        }
    else:
        return {
            'label': RISK_LABELS['low_risk'],
            'color': '#6bcf6b',
            'bg_color': '#1a4a1a',
            'icon': '',
            'priority': 0,
            'category': 'low_risk'
        }


def count_risk_categories(df: pd.DataFrame, custom_symbol_config: dict = None) -> dict:
    """
    Count items in each risk category using shared validation config.

    Args:
        df: DataFrame with detection data
        custom_symbol_config: Optional dict of custom symbol configurations

    Returns:
        dict with counts for 'high_risk', 'medium_risk', 'low_risk', 'total'
    """
    if df is None or df.empty:
        return {'high_risk': 0, 'medium_risk': 0, 'low_risk': 0, 'total': 0}

    # Filter out hidden rows and excluded classes (using shared config)
    df_filtered = df.copy()
    if '_hidden' in df_filtered.columns:
        df_filtered = df_filtered[~df_filtered['_hidden'].fillna(False)]

    # Use shared config for excluded classes
    if 'cls' in df_filtered.columns:
        df_filtered = df_filtered[~df_filtered['cls'].apply(lambda x: config_is_excluded(str(x)))]

    high_risk = 0
    medium_risk = 0
    low_risk = 0

    for _, row in df_filtered.iterrows():
        risk_score, _ = calculate_row_risk_score(row, custom_symbol_config)
        risk_level = get_risk_level(risk_score)
        if risk_level == 'high_risk':
            high_risk += 1
        elif risk_level == 'medium_risk':
            medium_risk += 1
        else:
            low_risk += 1

    return {
        'high_risk': high_risk,
        'medium_risk': medium_risk,
        'low_risk': low_risk,
        'total': high_risk + medium_risk + low_risk
    }


# Keep old function for backwards compatibility (used in tree population)
def get_confidence_status(conf: float) -> dict:
    """Legacy function - converts confidence to risk and returns status."""
    # Simple approximation: conf -> risk_score
    risk_score = (1.0 - conf) * RISK_WEIGHTS['low_confidence']
    return get_risk_status(risk_score)

# ============================================================================
# WORKSPACE WIDGET - Single PDF workspace
# ============================================================================
class WorkspaceWidget(QtWidgets.QWidget):

    """Single PDF workspace - contains all UI for one document"""

    def __init__(self, parent_auditing: 'AuditingWindow', layout_name: str):
        from pdfcomparison.dialogs import TreeWindow, GraphicsWindow
        super().__init__()
        self.parent_auditing = parent_auditing
        self.layout_name = layout_name
        self.workspace_window = None  # Reference to popped-out window
        self.workspace_placeholder = None  # Placeholder widget in tab
        self.tree_window: Optional[TreeWindow] = None
        # Copy ALL instance variables from original AuditingWindow
        self.df_all = pd.DataFrame()
        self.all_page_row_specs: Dict[int, Dict[int, Dict[str, object]]] = {}
        self.current_row_items: Dict[int, List[QtWidgets.QGraphicsItem]] = {}
        self.row_id_to_tree_item: Dict[int, QtWidgets.QTreeWidgetItem] = {}
        self.current_page = 1
        self.page_spin = None  # Page control removed - always single page view
        self._class_confidence_thresholds: Dict[str, float] = {'__all__': 0.0}
        self._active_class_for_threshold_setting: str = '__all__'
        self.page_base_pix: Dict[int, QtGui.QPixmap] = {}
        self.page_dfs: Dict[int, pd.DataFrame] = {}
        self._last_hovered_row_id: Optional[int] = None
        self._is_selecting_from_scene = False
        self.page_bgr_arrays: Dict[int, np.ndarray] = {}
        self.current_page_bgr_array: Optional[np.ndarray] = None
        self.is_drawing_mode = False
        self.draw_ocr_target_item: Optional[QtWidgets.QTreeWidgetItem] = None
        self.draw_ocr_target_column: Optional[int] = None
        self.draw_ocr_mode: str = 'horizontal'
        self.is_manual_linking_mode = False
        self.link_source_row_id = None
        self.link_drag_line = None

        # Undo/Redo stacks
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        self.max_undo_steps = 50
        self._is_undoing_or_redoing = False
        self._is_loading_data = False

        # OCR adjustment tracking for auto-learning
        self.ocr_adjustment_tracker = OCRAdjustmentTracker()

        self.graphics_window: Optional[GraphicsWindow] = None
        
        # Placeholder widgets
        self.tree_placeholder: Optional[QtWidgets.QWidget] = None
        self.graphics_placeholder: Optional[QtWidgets.QWidget] = None
        # Track overlay
        self.track_skeleton = None
        self.track_overlay_items = []
        # Add missing detection overlay storage
        self.missing_detection_overlays = []
        #  NEW: Confidence visualization flag
        self.show_confidence_colors = False
        #  NEW: Error rows storage
        self.error_rows = set()
        self.show_missing_detections = False  # Toggle state

        # Storage for uncertain (low-confidence) detections for user review
        self.uncertain_detections = []

        # Storage for learned OCR patterns (for adaptive linking)
        self.learned_patterns = None

        # OCR engine for processing confirmed uncertain detections
        self.ocr_engine = "paddleocr"

        #  NEW: Delayed OCR adjustment dialog timer
        # Waits 1.5s after last resize before showing dialog
        self._ocr_resize_timer = QtCore.QTimer()
        self._ocr_resize_timer.setSingleShot(True)
        self._ocr_resize_timer.timeout.connect(self._on_ocr_resize_timer_fired)
        self._pending_ocr_resize = None  # Stores (row_id, x, y, w, h) for pending resize

        self._build_ui()


    def _set_status(self, message: str):
        """Safely update status bar"""
        try:
            if self.parent_auditing and hasattr(self.parent_auditing, 'statusBar'):
                self.parent_auditing.statusBar().showMessage(message)
            else:
                print(f"[STATUS] {message}")
        except Exception as e:
            print(f"[STATUS ERROR] {message} ({e})")

    def _on_ocr_resize_timer_fired(self):
        """
        Called when the OCR resize timer fires after user stops resizing.
        Processes the pending OCR region resize.
        """
        if self._pending_ocr_resize is not None:
            row_id, x, y, w, h = self._pending_ocr_resize
            self._pending_ocr_resize = None
            self.on_ocr_bbox_resized(row_id, x, y, w, h)

    def cancel_pending_ocr_resize(self):
        """
        Cancel any pending OCR resize timer.
        Called when user starts a new resize operation.
        """
        if self._ocr_resize_timer.isActive():
            self._ocr_resize_timer.stop()
            self._pending_ocr_resize = None

    def queue_ocr_bbox_resize(self, row_id: int, x: float, y: float, w: float, h: float):
        """
        Queue an OCR bbox resize with a delay to allow multiple edge adjustments.

        Restarts the 1.5s timer each time, so the OCR only runs after the user
        stops resizing for 1.5 seconds.

        Args:
            row_id: Row ID of the detection
            x, y, w, h: New OCR region bounding box coordinates
        """
        if self._ocr_resize_timer.isActive():
            self._ocr_resize_timer.stop()

        self._pending_ocr_resize = (row_id, x, y, w, h)
        self._ocr_resize_timer.start(1500)

    def _perform_auto_quality_check(self):
        """Perform quick quality check on loaded data and show warning if issues found"""
        if self.df_all is None or self.df_all.empty:
            return

        try:
            # Quick risk assessment
            issues = []
            high_risk_count = 0
            medium_risk_count = 0

            df_with_conf = self.df_all[self.df_all['conf'].notna()].copy()
            if df_with_conf.empty:
                return

            for _, row in df_with_conf.iterrows():
                conf = float(row['conf'])
                cls = row.get('cls', '')

                # Factor 1: Confidence Risk
                conf_risk = (1.0 - conf) * 0.4

                # Factor 2: Missing Required Data
                missing_risk = 0.0
                if cls in ['signal', 'gks_gesteuert', 'gks_nicht_gesteuert', 'weiche', 'sverbinder']:
                    if pd.isna(row.get('coord_text')) or not row.get('coord_text'):
                        missing_risk = 0.3

                # Calculate total risk
                total_risk = conf_risk + missing_risk

                if total_risk >= 0.5:  # High risk (50%+)
                    high_risk_count += 1
                elif total_risk >= 0.3:  # Medium risk (30-50%)
                    medium_risk_count += 1

            # Log warning if significant issues found
            if high_risk_count > 0 or medium_risk_count > 5:
                total_issues = high_risk_count + medium_risk_count
                print(f"Qualitätsprüfung: {high_risk_count} hochriskante, {medium_risk_count} mittelriskante Erkennungen gefunden ({total_issues} gesamt)")

        except Exception as e:
            print(f"Error in auto quality check: {e}")

    def _build_ui(self):
        from ui.tree_widget import AuditingTreeWidget

        """Build the workspace UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(scale_value(5), scale_value(5), scale_value(5), scale_value(5))

        # Top controls with modern styling
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(scale_value(12))

        # ADD UNDO/REDO BUTTONS with enhanced styling
        self.btn_undo = QtWidgets.QPushButton("↶ Rückgängig")
        self.btn_undo.setMinimumHeight(scale_value(35))
        self.btn_undo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_undo.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #5a6a7a, stop:1 #4a5a6a);
                color: white;
                border: 1px solid #3a4a5a;
                border-radius: 5px;
                padding: 6px 15px;
                font-size: 10pt;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #6a7a8a, stop:1 #5a6a7a);
                border: 1px solid #3498db;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #3a4a5a, stop:1 #2c3e50);
            }
            QPushButton:disabled {
                background: #7f8c8d;
                color: #bdc3c7;
                border: 1px solid #95a5a6;
            }
        """)
        self.btn_undo.setToolTip("↶ Rückgängig\n\nMacht die letzte Änderung rückgängig\n\n Tipp: Sie können bis zu 50 Schritte\n    rückgängig machen\n\nTastenkürzel: Strg+Z")
        self.btn_undo.clicked.connect(self.undo)
        top_layout.addWidget(self.btn_undo)

        self.btn_redo = QtWidgets.QPushButton("↷ Wiederholen")
        self.btn_redo.setMinimumHeight(scale_value(35))
        self.btn_redo.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_redo.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #5a6a7a, stop:1 #4a5a6a);
                color: white;
                border: 1px solid #3a4a5a;
                border-radius: 5px;
                padding: 6px 15px;
                font-size: 10pt;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #6a7a8a, stop:1 #5a6a7a);
                border: 1px solid #3498db;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #3a4a5a, stop:1 #2c3e50);
            }
            QPushButton:disabled {
                background: #7f8c8d;
                color: #bdc3c7;
                border: 1px solid #95a5a6;
            }
        """)
        self.btn_redo.setToolTip("↷ Wiederholen\n\nStellt eine rückgängig gemachte\nÄnderung wieder her\n\nTastenkürzel: Strg+Y")
        self.btn_redo.clicked.connect(self.redo)
        top_layout.addWidget(self.btn_redo)

        top_layout.addStretch(1)

        # Layout name label with icon
        short_name = os.path.basename(self.layout_name)
        self.layout_label = QtWidgets.QLabel(f" {short_name}")
        self.layout_label.setStyleSheet("""
            font-weight: bold;
            color: #2980b9;
            font-size: 11pt;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #ecf0f1, stop:1 #bdc3c7);
            padding: 8px 15px;
            border-radius: 5px;
            border: 1px solid #95a5a6;
        """)
        top_layout.addWidget(self.layout_label)

        layout.addLayout(top_layout)

        # ====================================================================
        # RISK COUNTER BAR - Matching Erkennungsqualität criteria
        # ====================================================================
        self.problem_counter_bar = QtWidgets.QFrame()
        self.problem_counter_bar.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.problem_counter_bar.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
            }
        """)

        counter_layout = QtWidgets.QHBoxLayout(self.problem_counter_bar)
        counter_layout.setContentsMargins(scale_value(10), scale_value(6), scale_value(10), scale_value(6))
        counter_layout.setSpacing(scale_value(12))

        # High risk (red) - "Sofort prüfen" - dark theme
        self.high_risk_btn = QtWidgets.QPushButton("0 Sofort prüfen")
        self.high_risk_btn.setStyleSheet("""
            QPushButton {
                background-color: #5c1a1a;
                color: #ff6b6b;
                border: 2px solid #ff6b6b;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7a2020;
                border-color: #ff8585;
            }
            QPushButton:checked {
                background-color: #ff6b6b;
                color: #1a1a1a;
            }
        """)
        self.high_risk_btn.setCheckable(True)
        self.high_risk_btn.setToolTip("Elemente mit hohem Risiko (>20%)\nTexterkennung unsicher oder Daten fehlen")
        self.high_risk_btn.clicked.connect(lambda: self._filter_by_risk('high_risk'))
        counter_layout.addWidget(self.high_risk_btn)

        # Medium risk (yellow) - "Bald prüfen" - dark theme
        self.medium_risk_btn = QtWidgets.QPushButton("0 Bald prüfen")
        self.medium_risk_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4020;
                color: #ffd93d;
                border: 2px solid #ffd93d;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5030;
                border-color: #ffe066;
            }
            QPushButton:checked {
                background-color: #ffd93d;
                color: #1a1a1a;
            }
        """)
        self.medium_risk_btn.setCheckable(True)
        self.medium_risk_btn.setToolTip("Elemente mit mittlerem Risiko (10-20%)\nBei Gelegenheit kontrollieren")
        self.medium_risk_btn.clicked.connect(lambda: self._filter_by_risk('medium_risk'))
        counter_layout.addWidget(self.medium_risk_btn)

        # Low risk (green) - "Gut erkannt" - dark theme
        self.low_risk_btn = QtWidgets.QPushButton("0 Gut erkannt")
        self.low_risk_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a4a1a;
                color: #6bcf6b;
                border: 2px solid #6bcf6b;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2a5a2a;
                border-color: #85e085;
            }
            QPushButton:checked {
                background-color: #6bcf6b;
                color: #1a1a1a;
            }
        """)
        self.low_risk_btn.setCheckable(True)
        self.low_risk_btn.setToolTip("Elemente mit niedrigem Risiko (<10%)\nHohe Qualität - normalerweise OK")
        self.low_risk_btn.clicked.connect(lambda: self._filter_by_risk('low_risk'))
        counter_layout.addWidget(self.low_risk_btn)

        counter_layout.addStretch(1)

        # Show all button - dark theme
        self.show_all_btn = QtWidgets.QPushButton("Alle anzeigen")
        self.show_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                color: #cccccc;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: white;
            }
        """)
        self.show_all_btn.setToolTip("Alle Elemente anzeigen (Filter zurücksetzen)")
        self.show_all_btn.clicked.connect(self._clear_risk_filter)
        counter_layout.addWidget(self.show_all_btn)

        # Next problem button - dark theme
        self.next_problem_btn = QtWidgets.QPushButton("→ Nächstes")
        self.next_problem_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b0000;
                color: #ff6b6b;
                border: 2px solid #ff6b6b;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #a52a2a;
                color: white;
            }
            QPushButton:disabled {
                background-color: #3d3d3d;
                color: #666666;
                border-color: #555555;
            }
        """)
        self.next_problem_btn.setToolTip("Springt zum nächsten Element mit hohem Risiko")
        self.next_problem_btn.clicked.connect(self._jump_to_next_risk_item)
        counter_layout.addWidget(self.next_problem_btn)

        layout.addWidget(self.problem_counter_bar)

        # Track current risk filter
        self._current_risk_filter = None

        # Warning banner removed for cleaner UI

        # Confidence controls
        conf = QtWidgets.QHBoxLayout()
        class_label = QtWidgets.QLabel("Klasse auswählen:")
        class_label.setStyleSheet("font-size: 11pt;")
        conf.addWidget(class_label)
        self.class_selector_combo = QtWidgets.QComboBox()
        self.class_selector_combo.setStyleSheet("""
            QComboBox {
                font-size: 11pt;
                padding: 4px 8px;
                min-height: 26px;
            }
        """)
        self.class_selector_combo.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        self.class_selector_combo.currentTextChanged.connect(self.on_class_selector_changed)
        conf.addWidget(self.class_selector_combo)

        # Threshold adjustment button - right of class selector
        self.btn_thresholds = QtWidgets.QPushButton("Schwellenwerte")
        self.btn_thresholds.setToolTip("Konfidenz-Schwellenwerte pro Klasse anpassen\n\nNiedrigere Werte = mehr Erkennungen\nHöhere Werte = nur sichere Erkennungen")
        self.btn_thresholds.setStyleSheet("""
            QPushButton {
                font-size: 11pt;
                padding: 6px 12px;
                min-height: 28px;
            }
        """)
        self.btn_thresholds.clicked.connect(self._open_threshold_dialog)
        conf.addWidget(self.btn_thresholds)

        conf.addStretch(1)

        # Common toolbar button style - larger font and padding
        toolbar_btn_style = """
            QPushButton {
                font-size: 11pt;
                padding: 6px 12px;
                min-height: 28px;
            }
        """

        # Validation button - clearer label
        self.btn_validate = QtWidgets.QPushButton(" Daten prüfen")
        self.btn_validate.setToolTip("Automatische Prüfung aller Daten\n\nFindet fehlende oder fehlerhafte Einträge")
        self.btn_validate.setStyleSheet(toolbar_btn_style)
        self.btn_validate.clicked.connect(self._run_validation)
        conf.addWidget(self.btn_validate)

        # Quality Inspector button - clearer label
        self.btn_quality_inspector = QtWidgets.QPushButton(" Qualität anzeigen")
        self.btn_quality_inspector.setCheckable(True)
        self.btn_quality_inspector.setChecked(False)
        self.btn_quality_inspector.setStyleSheet(toolbar_btn_style)
        self.btn_quality_inspector.setToolTip(
            "Zeigt die Erkennungsqualität im Gleisplan:\n\n"
            " Grün = Sicher erkannt (OK)\n"
            " Gelb = Bitte überprüfen\n"
            " Rot = Problem - bitte korrigieren"
        )
        self.btn_quality_inspector.toggled.connect(self.on_toggle_quality_inspector)
        conf.addWidget(self.btn_quality_inspector)

        # Manual linking button - clearer label
        self.btn_manual_link = QtWidgets.QPushButton(" Koordinate zuweisen")
        self.btn_manual_link.setCheckable(True)
        self.btn_manual_link.setStyleSheet(toolbar_btn_style)
        self.btn_manual_link.setToolTip("Koordinate manuell einem Element zuweisen\n\n1. Klicken Sie auf ein Element\n2. Dann auf die zugehörige Koordinate")
        self.btn_manual_link.toggled.connect(self.on_manual_link_toggled)
        conf.addWidget(self.btn_manual_link)

        # Manual OCR buttons - clearer German labels
        self.btn_manual_ocr = QtWidgets.QPushButton(" Text erkennen")
        self.btn_manual_ocr.setCheckable(True)
        self.btn_manual_ocr.setStyleSheet(toolbar_btn_style)
        self.btn_manual_ocr.setToolTip("Text manuell erkennen (für horizontale Texte)\n\nZeichnen Sie ein Rechteck um den Text")
        self.btn_manual_ocr.toggled.connect(lambda checked: self.on_manual_ocr_toggled(checked, 'horizontal'))
        conf.addWidget(self.btn_manual_ocr)

        self.btn_manual_ocr_angular = QtWidgets.QPushButton(" Schräger Text")
        self.btn_manual_ocr_angular.setCheckable(True)
        self.btn_manual_ocr_angular.setStyleSheet(toolbar_btn_style)
        self.btn_manual_ocr_angular.setToolTip("Schrägen/gedrehten Text erkennen\n\nFür Texte die nicht horizontal sind")
        self.btn_manual_ocr_angular.toggled.connect(lambda checked: self.on_manual_ocr_toggled(checked, 'angular'))
        conf.addWidget(self.btn_manual_ocr_angular)

        # Track overlay toggle button
        self.btn_toggle_tracks = QtWidgets.QPushButton(" Gleise anzeigen")
        self.btn_toggle_tracks.setCheckable(True)
        self.btn_toggle_tracks.setEnabled(False)
        self.btn_toggle_tracks.setStyleSheet(toolbar_btn_style)
        self.btn_toggle_tracks.setToolTip("Zeigt die erkannten Hauptgleise als rote Linie")
        self.btn_toggle_tracks.toggled.connect(self.on_toggle_track_overlay)
        conf.addWidget(self.btn_toggle_tracks)

        layout.addLayout(conf)
        
        # Graphics view
        self.view = InteractiveGraphicsView(self)
        self.scene = QtWidgets.QGraphicsScene()
        self.view.setScene(self.scene)
        
        # Item details
        self.item_details_notes = QtWidgets.QPlainTextEdit()
        self.item_details_notes.setPlaceholderText("Details zum ausgewählten Element / Notizen...")
        self.item_details_notes.setMaximumHeight(scale_value(150)) 
        self.item_details_notes.textChanged.connect(self.on_item_notes_changed)
        
        # Filter inputs
        self.filter_class_input = QtWidgets.QLineEdit()
        self.filter_class_input.setPlaceholderText("Filter Klasse (Regex)")
        self.filter_text_input = QtWidgets.QLineEdit()
        self.filter_text_input.setPlaceholderText("Filter Text (Regex)")
        table_filter = QtWidgets.QHBoxLayout()
        table_filter.addWidget(self.filter_class_input)
        table_filter.addWidget(self.filter_text_input)
        
        # Tree widget - bigger font and row height for better readability
        self.tree = AuditingTreeWidget(self)
        self.tree.setHeaderLabels(["Text/Nummer", "Koordinatentext", "Fahrtrichtung", "Seite"])
        self.tree.setSortingEnabled(True)

        # Make tree bigger with larger font (DPI-aware)
        tree_font = get_scaled_font(12)
        self.tree.setFont(tree_font)
        self.tree.header().setFont(tree_font)

        # Increase row height for better readability
        self.tree.setStyleSheet("""
            QTreeWidget {
                font-size: 12pt;
            }
            QTreeWidget::item {
                padding: 6px 4px;
                min-height: 28px;
            }
            QHeaderView::section {
                font-size: 12pt;
                font-weight: bold;
                padding: 8px 4px;
            }
        """)

        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
        # DPI-aware column widths
        self.tree.header().resizeSection(0, scale_value(220))
        self.tree.header().resizeSection(1, scale_value(170))
        self.tree.header().resizeSection(2, scale_value(120))
        self.tree.header().resizeSection(3, scale_value(90))
        self.tree.header().setStretchLastSection(True)
        self.tree.setMouseTracking(True)
        self.tree.itemEntered.connect(self.on_tree_item_hovered)
        self.tree.viewport().installEventFilter(self)
        # Setup keyboard shortcuts for table editing
        self._setup_table_shortcuts()
        # Splitter layout
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        self.graphics_original_layout = left_layout 
        left_layout.addWidget(self.view)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)

        # Quick Correction Panel removed - edit directly in tree

        right_layout.addLayout(table_filter)
        self.tree_original_layout = right_layout
        right_layout.addWidget(self.tree)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([800, 500])
        
        layout.addWidget(splitter)
        
        # Connect signals
        self.filter_class_input.textChanged.connect(self._apply_all_filters)
        self.filter_text_input.textChanged.connect(self._apply_all_filters)
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        self.view.rect_drawn.connect(self.on_rect_drawn)
        self.view.rotated_rect_drawn.connect(self.on_rotated_rect_drawn)
        self.scene.selectionChanged.connect(self.on_scene_selection)
        self._setup_undo_redo_shortcuts()

    def _setup_table_shortcuts(self):
        """Setup keyboard shortcuts for table editing"""
        # Copy
        copy_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+C"), self.tree)
        copy_shortcut.activated.connect(self.tree.copy_selection)
        
        # Paste
        paste_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+V"), self.tree)
        paste_shortcut.activated.connect(self.tree.paste_from_clipboard)
        
        # Find
        find_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self.tree)
        find_shortcut.activated.connect(self.tree.find_replace)

    def on_pop_out_tree(self):
        from pdfcomparison.dialogs import TreeWindow
        """Pop out the tree widget into its own window."""
        if self.tree_window is not None:
            return
        # CREATE PLACEHOLDER before removing tree
        self.tree_placeholder = QtWidgets.QWidget()
        self.tree_placeholder.setMinimumHeight(self.tree.height())

        # Get the tree's current index in the layout
        tree_index = self.tree_original_layout.indexOf(self.tree)
        
        # Replace tree with placeholder
        self.tree_original_layout.removeWidget(self.tree)
        self.tree_original_layout.insertWidget(tree_index, self.tree_placeholder)

        # Create the new window. The TreeWindow constructor will reparent self.tree
        self.tree_window = TreeWindow(self, self.tree)
        
        # Apply the current theme to the new window
        if self.parent_auditing.main_app_ref._current_theme == "dark":
            self.tree_window.setStyleSheet(DARK_QSS)
        else:
            self.tree_window.setStyleSheet(LIGHT_QSS)
            
        self.tree_window.show()

    def on_pop_out_graphics(self):
        from pdfcomparison.dialogs import GraphicsWindow
        """Pop out the graphics view into its own window."""
        if self.graphics_window is not None:
            return
        
        #  CREATE PLACEHOLDER before removing view
        self.graphics_placeholder = QtWidgets.QWidget()
        self.graphics_placeholder.setMinimumSize(self.view.size())
        
        # Get the view's current index in the layout
        view_index = self.graphics_original_layout.indexOf(self.view)
        
        # Replace view with placeholder
        self.graphics_original_layout.removeWidget(self.view)
        self.graphics_original_layout.insertWidget(view_index, self.graphics_placeholder)
        
        # Create the new window (this will reparent self.view)
        self.graphics_window = GraphicsWindow(self, self.view)
        
        # Apply theme
        if self.parent_auditing.main_app_ref._current_theme == "dark":
            self.graphics_window.setStyleSheet(DARK_QSS)
        else:
            self.graphics_window.setStyleSheet(LIGHT_QSS)
        
        self.graphics_window.show()

    def on_redock_graphics(self):
        """Redock the graphics view back into the main view."""
        if self.graphics_window is None:
            return
        
        # Closing the window will trigger the _on_graphics_window_closed callback
        self.graphics_window.close()

    def _on_graphics_window_closed(self):
        """Callback when the popped-out graphics window is closed."""
        if self.graphics_window is None:
            return
        
        #  REPLACE PLACEHOLDER with view
        if self.graphics_placeholder:
            placeholder_index = self.graphics_original_layout.indexOf(self.graphics_placeholder)
            
            # Remove placeholder
            self.graphics_original_layout.removeWidget(self.graphics_placeholder)
            self.graphics_placeholder.deleteLater()
            self.graphics_placeholder = None
            
            # Re-insert view at same position
            self.view.setParent(None)
            self.graphics_original_layout.insertWidget(placeholder_index, self.view)
        else:
            # Fallback: just add at end
            self.view.setParent(None)
            self.graphics_original_layout.addWidget(self.view)
        
        self.graphics_window = None

    def on_redock_tree(self):
        """Redock the tree widget back into the main view."""
        if self.tree_window is None:
            return
        
        # Closing the window will trigger the _on_tree_window_closed callback
        self.tree_window.close()

    def _on_tree_window_closed(self):
        """Callback when the popped-out tree window is closed."""
        if self.tree_window is None:
            return
        
        #  REPLACE PLACEHOLDER with tree
        if self.tree_placeholder:
            placeholder_index = self.tree_original_layout.indexOf(self.tree_placeholder)
            
            # Remove placeholder
            self.tree_original_layout.removeWidget(self.tree_placeholder)
            self.tree_placeholder.deleteLater()
            self.tree_placeholder = None
            
            # Re-insert tree at same position
            self.tree.setParent(None)
            self.tree_original_layout.insertWidget(placeholder_index, self.tree)
        else:
            # Fallback: just add at end
            self.tree.setParent(None)
            self.tree_original_layout.addWidget(self.tree)
        
        # Reconnect signals
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.tree_window = None

    def on_delete_selected_table_rows(self):
        """
        Deletes the currently selected rows from the tree and dataframes.
        (This is the fix for the 'Delete' action)
        """
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Zeilen löschen",
            f"Möchten Sie die {len(selected_items)} ausgewählten Zeilen wirklich löschen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return
            
        self.tree.blockSignals(True)
        
        row_ids_to_delete = []
        items_to_remove = []

        for item in selected_items:
            # Collect child items if a parent is selected
            if item.childCount() > 0:
                for i in range(item.childCount()):
                    child = item.child(i)
                    row_id = child.data(0, QtCore.Qt.UserRole)
                    if row_id is not None:
                        row_ids_to_delete.append(row_id)
                        items_to_remove.append(child)
            else:
                # Collect single child item
                row_id = item.data(0, QtCore.Qt.UserRole)
                if row_id is not None:
                    row_ids_to_delete.append(row_id)
                    items_to_remove.append(item)

        if not row_ids_to_delete:
            self.tree.blockSignals(False)
            return
        
        #  SAVE STATE WITH SPECIAL DELETION MARKER
        self._save_deletion_state(row_ids_to_delete)

        try:
            # 1. Remove from DataFrames
            if self.df_all is not None and not self.df_all.empty:
                self.df_all.drop(
                    self.df_all[self.df_all['row_id'].isin(row_ids_to_delete)].index, 
                    inplace=True
                )
            
            df_page = self.page_dfs.get(self.current_page)
            if df_page is not None and not df_page.empty:
                df_page.drop(
                    df_page[df_page['row_id'].isin(row_ids_to_delete)].index, 
                    inplace=True
                )
            
            # 2. Remove from helper dictionaries and scene
            for row_id in row_ids_to_delete:
                if row_id in self.row_id_to_tree_item:
                    del self.row_id_to_tree_item[row_id]
                
                graphics_items = self.current_row_items.pop(row_id, [])
                for g_item in graphics_items:
                    if g_item and g_item.scene():
                        self.scene.removeItem(g_item)

            # 3. Remove from Tree widget
            for item in items_to_remove:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
            
            # Use the parent's status bar
            self._set_status(f"{len(row_ids_to_delete)} Zeilen gelöscht.")
            self.tree._update_row_count()
            self.tree._update_selection_count()
            
            #  Update button states
            self._update_undo_redo_buttons()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler beim Löschen", str(e))
        finally:
            self.tree.blockSignals(False)
            self.item_details_notes.clear()

    def load_data(self, df_all: pd.DataFrame, page_base_pix: Dict,
                page_dfs: Dict, page_bgr_arrays: Dict,
                track_skeleton: Optional[np.ndarray] = None,
                from_database: bool = False,
                uncertain_detections: list = None,
                learned_patterns: dict = None):
        """Load data into workspace - with database check

        Args:
            from_database: If True, skip database check (data already loaded from DB)
            uncertain_detections: List of low-confidence detections for user review
            learned_patterns: Optional dict of learned OCR patterns for adaptive linking
        """

        #  SET FLAG TO PREVENT STATE SAVING DURING LOAD
        self._is_loading_data = True

        # Store uncertain detections for validation dialog
        self.uncertain_detections = uncertain_detections or []
        if self.uncertain_detections:
            print(f"  Received {len(self.uncertain_detections)} uncertain detections for review")

        # Store learned patterns for OCR adjustment tracking
        self.learned_patterns = learned_patterns
        if self.learned_patterns:
            print(f"  Received {len(self.learned_patterns)} learned OCR patterns")

        try:
            #  VERIFY DATA ISOLATION
            print(f" Loading data for workspace: {self.layout_name}")
            print(f"  Incoming df_all: {len(df_all)} rows")
            print(f"  from_database: {from_database}")
            
            # Check for duplicate row_ids in incoming data
            if 'row_id' in df_all.columns:
                duplicate_check = df_all['row_id'].duplicated().sum()
                if duplicate_check > 0:
                    print(f"WARNING: Incoming data has {duplicate_check} duplicate row_ids!")
                    df_all = df_all.drop_duplicates(subset='row_id', keep='first')
                    print(f"   After deduplication: {len(df_all)} rows")

            # Database loading is now only done via Database Manager (from_database=True)
            # No automatic DB check or prompt here anymore

            #  CLEAR UNDO/REDO STACKS ON NEW LOAD
            self.undo_stack.clear()
            self.redo_stack.clear()

            # Load data into workspace
            self.df_all = self._ensure_hidden_column(df_all.copy())

            #  FIX: Ensure link_coord_row_id column exists in loaded data
            if 'link_coord_row_id' not in self.df_all.columns:
                self.df_all['link_coord_row_id'] = None
                print("   Added missing link_coord_row_id column to loaded data")

            #  FIX: Ensure OCR region columns exist in loaded data (for backward compatibility)
            ocr_columns = ['ocr_x1', 'ocr_y1', 'ocr_x2', 'ocr_y2', 'ocr_region_source']
            missing_ocr_cols = [col for col in ocr_columns if col not in self.df_all.columns]
            if missing_ocr_cols:
                for col in missing_ocr_cols:
                    self.df_all[col] = None
                print(f"   Added missing OCR columns to loaded data: {missing_ocr_cols}")

            # IMPORTANT: Deep copy all data structures to avoid sharing references with setup_window
            # Without these copies, setup_window operations would affect this workspace's data
            self.page_base_pix = {k: v.copy() for k, v in page_base_pix.items()}  # QPixmap.copy()
            self.page_dfs = {k: self._ensure_hidden_column(v.copy()) for k, v in page_dfs.items()}
            self.page_bgr_arrays = {k: np.copy(v) for k, v in page_bgr_arrays.items()}  # Deep copy numpy arrays

            # FIX: Rebuild page_dfs from df_all when loading from database
            if from_database and not self.page_dfs and not self.df_all.empty:
                print("  Rebuilding page_dfs from df_all (loaded from database)...")
                if 'page' in self.df_all.columns:
                    for page_num in self.df_all['page'].unique():
                        page_num_int = int(page_num)
                        self.page_dfs[page_num_int] = self._ensure_hidden_column(
                            self.df_all[self.df_all['page'] == page_num].copy()
                        )
                    print(f"  Rebuilt page_dfs for {len(self.page_dfs)} pages")

            #  FIX: Ensure link_coord_row_id column exists in page_dfs too
            for page_num, page_df in self.page_dfs.items():
                if 'link_coord_row_id' not in page_df.columns:
                    page_df['link_coord_row_id'] = None

                #  FIX: Ensure OCR region columns exist in page_dfs too
                for col in ocr_columns:
                    if col not in page_df.columns:
                        page_df[col] = None

            print(f"  Loaded into workspace: {len(self.df_all)} rows")

            #  ADD DEBUG: Check _hidden column
            if '_hidden' in self.df_all.columns:
                hidden_count = self.df_all['_hidden'].sum()
                print(f"  Hidden rows in df_all: {hidden_count}")
            else:
                print(f"WARNING: _hidden column not found in df_all!")

            # Fill class selector
            self.class_selector_combo.clear()
            self.class_selector_combo.addItem("Alle Klassen")
            all_classes = sorted(self.df_all['cls'].unique().tolist()) if 'cls' in self.df_all.columns else []
            for cls in all_classes:
                self.class_selector_combo.addItem(cls)
                self._class_confidence_thresholds.setdefault(cls, 0.0)
            self._class_confidence_thresholds.setdefault('__all__', 0.0)
            self.class_selector_combo.setCurrentText("Alle Klassen")
            self.on_class_selector_changed("Alle Klassen")

            # Build row specs per page
            self.all_page_row_specs.clear()
            for pidx, df_page in self.page_dfs.items():
                
                #  ADD DEBUG: Check _hidden column in page df (disabled for performance)
                # if '_hidden' in df_page.columns:
                #     page_hidden_count = df_page['_hidden'].sum()
                #     print(f"  Page {pidx}: {page_hidden_count} hidden rows out of {len(df_page)}")
                # else:
                #     print(f"WARNING: Page {pidx} missing _hidden column!")
                
                specs = {}
                for _, row in df_page.iterrows():
                    label = f"{row['cls']} {row.get('conf', 0.0):.2f}"
                    if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                        label += f" | {row['anchor_text']}"
                    if pd.notna(row.get('coord_text')) and row['coord_text']:
                        label += f" | {row['coord_text']}"
                    if 'angle' in df_page.columns and pd.notna(row.get('angle')):
                        try:
                            label += f" θ={float(row['angle']):.1f}°"
                        except Exception:
                            pass
                    
                    spec = {"label": label, "is_poly": False}
                    poly = row.get("poly", None)

                    # Priority 1: Use pre-computed poly if available
                    if isinstance(poly, (list, tuple)) and len(poly) == 4:
                        try:
                            pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                            spec.update({"is_poly": True, "pts": pts})
                            specs[int(row['row_id'])] = spec
                            continue
                        except Exception:
                            pass

                    # Get bbox coordinates
                    if row['cls'] == 'coordinate':
                        x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
                    else:
                        x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']

                    if pd.isna(x1) or x1 is None:
                        continue

                    # Priority 2: Check if rotated (has significant angle)
                    angle = row.get('angle', 0.0)
                    angle_raw = row.get('angle_raw', angle)

                    # Debug output for angle detection (disabled for performance)
                    # if pd.notna(angle) or pd.notna(angle_raw):
                    #     print(f"Row {row['row_id']} ({row['cls']}): angle={angle}, angle_raw={angle_raw}")

                    # Try angle first, then angle_raw
                    use_angle = angle if pd.notna(angle) and angle != 0.0 else angle_raw

                    if pd.notna(use_angle) and abs(float(use_angle)) > 5.0:  # Significant rotation
                        try:
                            pts = bbox_to_rotated_poly(x1, y1, x2, y2, float(use_angle))
                            spec.update({"is_poly": True, "pts": pts})
                            specs[int(row['row_id'])] = spec
                            # print(f"Created ROTATED polygon for row {row['row_id']}, angle={use_angle:.1f}°")  # Disabled for performance
                            continue
                        except Exception as e:
                            print(f"Failed to create rotated poly: {e}")
                            pass

                    # Priority 3: Fall back to axis-aligned rectangle
                    w = int(x2 - x1)
                    h = int(y2 - y1)
                    spec.update({"rect": (int(x1), int(y1), w, h)})
                    specs[int(row['row_id'])] = spec
                
                self.all_page_row_specs[pidx] = specs

                #  DEBUG: Show what was built (disabled for performance - uncomment for debugging)
                # print(f" Page {pidx}: Built {len(specs)} row specs")
                # print(f"Classes: {df_page['cls'].value_counts().to_dict()}")

            max_page = max(self.page_dfs.keys()) if self.page_dfs else 1
            # Page control removed - single page view only
            # self.page_spin.setMaximum(max_page)
            # self.page_spin.setValue(1)
            
            # Store track skeleton (copy to avoid shared reference with setup_window)
            self.track_skeleton = np.copy(track_skeleton) if track_skeleton is not None else None
            if self.track_skeleton is not None:
                self.btn_toggle_tracks.setEnabled(True)
                self._set_status(f" Track detection verfügbar: {self.layout_name}")

            #  FIX: Clear old overlay items before changing page
            # This ensures old non-resizable items are replaced with new resizable ones
            for items in self.current_row_items.values():
                for item in items:
                    if item and item.scene():
                        self.scene.removeItem(item)
            self.current_row_items.clear()

            self.on_page_changed(1)
            
            #  UPDATE UNDO/REDO BUTTON STATES
            if hasattr(self, '_update_undo_redo_buttons'):
                self._update_undo_redo_buttons()

            #  PERFORM AUTO QUALITY CHECK
            if hasattr(self, '_perform_auto_quality_check'):
                self._perform_auto_quality_check()

        except Exception as e:
            import traceback
            print(f"Error in load_data: {e}")
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self,
                "Ladefehler",
                f"Fehler beim Laden der Daten:\n{str(e)}"
            )
        
        finally:
            # ALWAYS CLEAR FLAG AFTER LOADING
            self._is_loading_data = False

    def on_toggle_confidence_colors(self, checked: bool):
        """ NEW: Toggle confidence-based bbox coloring"""
        print(f"\n CONFIDENCE COLOR TOGGLE: checked={checked}")
        self.show_confidence_colors = checked
        print(f"show_confidence_colors set to: {self.show_confidence_colors}")
        self._refresh_page_graphics()

        if checked:
            self._set_status(" Konfidenz-Farben aktiviert (>80% 60-80% <60%)")
        else:
            self._set_status(" Konfidenz-Farben deaktiviert")

    def on_toggle_track_overlay(self, checked: bool):
        """Toggle track centerline overlay (7px thick FLASHY RED line)"""
        # Clear existing overlay
        for item in self.track_overlay_items:
            if item and item.scene():
                self.scene.removeItem(item)
        self.track_overlay_items.clear()
        
        if not checked or self.track_skeleton is None:
            self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
            return
        
        try:
            h, w = self.track_skeleton.shape
            
            # Thicken skeleton to 7px
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            thick_skel = cv2.dilate(self.track_skeleton, kernel, iterations=1)
            
            # Create FLASHY RED overlay with full opacity
            overlay = np.zeros((h, w, 4), dtype=np.uint8)
            overlay[thick_skel > 0] = (255, 0, 0, 255)  # BRIGHT RED, fully opaque
            
            # Convert to QPixmap
            qimg = QtGui.QImage(overlay.data, w, h, w * 4, QtGui.QImage.Format_RGBA8888).copy()
            overlay_pix = QtGui.QPixmap.fromImage(qimg)
            
            # Add to scene above everything else
            overlay_item = self.scene.addPixmap(overlay_pix)
            overlay_item.setZValue(1000)  # Above all other items
            overlay_item.setOpacity(1.0)  # FULL OPACITY - NO TRANSPARENCY
            self.track_overlay_items.append(overlay_item)
            
            self._set_status(" Gleise sichtbar (7px FLASHY ROT)")
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Overlay-Fehler", f"Konnte Gleis-Overlay nicht erstellen:\n{e}")
            self.btn_toggle_tracks.setChecked(False)
    
    def save_to_db(self):
        """Save this workspace to database (including track skeleton AND image dimensions)"""
        if self.df_all is None or self.df_all.empty:
            return
        
        try:
            #  Clean DataFrame - convert numpy types to Python types
            df_cleaned = self.df_all.copy()
            
            # Replace NaN/NaT with None
            df_cleaned = df_cleaned.replace({np.nan: None, pd.NaT: None})
            
            #  Convert numpy arrays in 'poly' column to lists
            if 'poly' in df_cleaned.columns:
                df_cleaned['poly'] = df_cleaned['poly'].apply(
                    lambda x: x.tolist() if isinstance(x, np.ndarray) else x
                )
            
            #  Convert all numpy numeric types to Python types
            for col in df_cleaned.columns:
                if df_cleaned[col].dtype == np.int64:
                    df_cleaned[col] = df_cleaned[col].astype(object).where(df_cleaned[col].notna(), None)
                    df_cleaned[col] = df_cleaned[col].apply(lambda x: int(x) if x is not None else None)
                elif df_cleaned[col].dtype == np.float64:
                    df_cleaned[col] = df_cleaned[col].astype(object).where(df_cleaned[col].notna(), None)
                    df_cleaned[col] = df_cleaned[col].apply(lambda x: float(x) if x is not None else None)

            # Ensure _hidden is boolean (not NaN/None) - persists merged/deleted state
            if '_hidden' in df_cleaned.columns:
                # Handle both NaN and None values (NaN was converted to None earlier)
                df_cleaned['_hidden'] = df_cleaned['_hidden'].apply(
                    lambda x: bool(x) if x is not None and not pd.isna(x) else False
                )

            # Serialize _signal_positions dict to JSON string for persistence
            if '_signal_positions' in df_cleaned.columns:
                df_cleaned['_signal_positions'] = df_cleaned['_signal_positions'].apply(
                    lambda x: json.dumps(x) if isinstance(x, dict) else x
                )

            # Ensure weichen_coordinates is list (not numpy array)
            if 'weichen_coordinates' in df_cleaned.columns:
                df_cleaned['weichen_coordinates'] = df_cleaned['weichen_coordinates'].apply(
                    lambda x: x.tolist() if isinstance(x, np.ndarray) else (x if x is not None else [])
                )

            data_list = df_cleaned.to_dict("records")
            #  Collect image dimensions (ensure they're Python ints, not numpy)
            image_dimensions = {}
            for page_num, pix in self.page_base_pix.items():
                image_dimensions[int(page_num)] = {  #  Ensure key is Python int
                    'width': int(pix.width()),        #  Ensure value is Python int
                    'height': int(pix.height())       #  Ensure value is Python int
                }
            
            from database_sqlite import save_workspace_data
            save_workspace_data(
                self.layout_name,
                data_list,
                self.track_skeleton,
                image_dimensions,
                learned_patterns=getattr(self, 'learned_patterns', None),
                uncertain_detections=getattr(self, 'uncertain_detections', None)
            )

            print(f"Saved {self.layout_name} with dimensions: {image_dimensions}")
            
        except Exception as e:
            print(f"Save failed: {e}")
            import traceback
            traceback.print_exc()  #  Print full error trace for debugging
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))

    
    def _get_theme_colors(self):
        """Get theme colors from parent"""
        return self.parent_auditing.main_app_ref._get_theme_colors()
    
    def _update_graphics_theme(self):
        """Update graphics theme"""
        if self.scene is None:
            return
        
        # --- ADD THIS BLOCK ---
        # Repopulate the tree to update item-level styles
        # (like the dark category backgrounds)
        if self.current_page in self.page_dfs:
            self.tree.clearSelection() # Clear selection before rebuilding
            self.item_details_notes.clear()
            self._populate_tree(self.current_page)
        # --- END ADD ---
        _, _, _, _, bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(bg))
        if self.current_page in self.page_base_pix:
            for it in list(self.scene.items()):
                if not isinstance(it, QtWidgets.QGraphicsPixmapItem):
                    self.scene.removeItem(it)
            self.current_row_items.clear()
            self._create_items_for_page(self.current_page)
    
    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source == self.tree.viewport() and event.type() == QtCore.QEvent.Leave:
            self.on_table_leave()
        return super().eventFilter(source, event)
    
    def on_page_changed(self, pidx: int):
        """Handle page change - optimized to preserve overlays"""
        if pidx not in self.page_base_pix:
            return

        # Cancel any pending OCR resize from previous page
        self.cancel_pending_ocr_resize()

        # Check if we're actually changing pages
        is_same_page = (pidx == self.current_page)
        
        self.current_page = pidx
        self.current_page_bgr_array = self.page_bgr_arrays.get(pidx, None)
        
        # Repopulate tree
        self._populate_tree(pidx)
        
        if not is_same_page:
            # Full rebuild when changing pages
            self.scene.clear()
            _, _, _, _, bg = self._get_theme_colors()
            self.scene.setBackgroundBrush(QtGui.QBrush(bg))
            self.scene.addPixmap(self.page_base_pix[pidx])
            self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[pidx].rect()))
            self._create_items_for_page(pidx)
        else:
            # Same page - just update overlays (keep background)
            print(f"Same page refresh - updating overlays incrementally")
            
            #  FIX: Ensure background pixmap exists
            has_background = False
            for item in self.scene.items():
                if isinstance(item, QtWidgets.QGraphicsPixmapItem):
                    has_background = True
                    break
            
            if not has_background:
                # Background was removed - add it back
                print(f"Background missing - restoring...")
                _, _, _, _, bg = self._get_theme_colors()
                self.scene.setBackgroundBrush(QtGui.QBrush(bg))
                
                # Add pixmap at the BOTTOM (z-order = -1)
                pixmap_item = self.scene.addPixmap(self.page_base_pix[pidx])
                pixmap_item.setZValue(-1)  #  Ensure it's behind overlays
                
                self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[pidx].rect()))
            
            # Now update overlays
            self._update_existing_overlays(pidx)
        
        # Update missing detection overlays for new page
        if hasattr(self, 'validation_result') and self.show_missing_detections:
            self._add_missing_detection_overlays(self.validation_result)


    def _populate_tree(self, pidx: int):
        """Populate tree widget for given page"""
        # Block signals to prevent on_tree_item_changed from firing for every item
        # This dramatically improves performance (913 items = 2-3 sec → instant)
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            self.row_id_to_tree_item.clear()

            df_page = self.page_dfs.get(pidx)
            if df_page is None:
                return
            # Filter out hidden rows
            if '_hidden' in df_page.columns:
                df_page = df_page[~df_page['_hidden'].fillna(False)].copy()
            # Get and sort class list
            classes = sorted(df_page['cls'].unique())
            if 'coordinate' in classes:
                classes.remove('coordinate')
                classes.append('coordinate')

            for cls_name in classes:
                parent_item = QtWidgets.QTreeWidgetItem(self.tree)
                parent_item.setText(0, cls_name)
                parent_item.setExpanded(True)

                # Style parent
                font = parent_item.font(0)
                font.setBold(True)
                parent_item.setFont(0, font)
                parent_item.setFlags(parent_item.flags() & ~QtCore.Qt.ItemIsSelectable)
                bg_brush = self.palette().window().color().lighter(115)
                for col in range(4):
                    parent_item.setBackground(col, bg_brush)

                df_class = df_page[df_page['cls'] == cls_name]
                item_counter = 1
                is_no_ocr_class = cls_name in NO_OCR_CLASSES

                for _, row in df_class.iterrows():
                    row_id = int(row['row_id'])

                    # Determine primary and secondary text
                    if cls_name == 'coordinate':
                        primary_text = str(row.get('coord_text', ''))
                        secondary_text = ""
                        fahrtrichtung_text = ""
                    elif is_no_ocr_class:
                        # Check if anchor_text was already populated by the pipeline
                        # (e.g., for haltepunkt or weichenende)
                        existing_anchor_text = row.get('anchor_text', '')

                        if existing_anchor_text:
                            # Use the pre-formatted text from the pipeline
                            primary_text = str(existing_anchor_text)
                        else:
                            # Fallback for other NO_OCR_CLASSES (like isolierstoß)
                            primary_text = f"{cls_name} {item_counter}"
                            item_counter += 1  # Only increment if we use the counter

                        secondary_text = str(row.get('coord_text', ''))
                        fahrtrichtung_text = ""
                    else:
                        primary_text = str(row.get('anchor_text', ''))
                        secondary_text = str(row.get('coord_text', ''))

                        if cls_name == "signal" and pd.notna(row.get('fahrtrichtung')):
                            fahrtrichtung_text = str(row['fahrtrichtung'])
                        else:
                            fahrtrichtung_text = ""

                    page_str = str(row.get('page', ''))
                    child_item = QtWidgets.QTreeWidgetItem(parent_item)

                    # Get confidence status for color coding
                    conf = float(row.get('conf', 0.0))
                    status = get_confidence_status(conf)

                    # Set text WITHOUT emoji icons (clean text only)
                    child_item.setText(0, primary_text)
                    child_item.setText(1, secondary_text)
                    child_item.setText(2, fahrtrichtung_text)
                    child_item.setText(3, page_str)

                    # No colored backgrounds - user prefers clean dark theme

                    child_item.setFlags(child_item.flags() | QtCore.Qt.ItemIsEditable)
                    child_item.setData(0, QtCore.Qt.UserRole, row_id)
                    # Store confidence for filtering
                    child_item.setData(0, QtCore.Qt.UserRole + 1, conf)
                    self.row_id_to_tree_item[row_id] = child_item

            self._apply_all_filters()
            self._update_problem_counts()  # Update counter bar
            self.tree._update_row_count()
            self.tree._update_selection_count()
        finally:
            self.tree.blockSignals(False)


    def _apply_all_filters(self):
        """Apply all filters to tree"""
        self.tree.blockSignals(True)
        
        class_filter_re = None
        text_filter_re = None
        
        try:
            class_filter_re = re.compile(self.filter_class_input.text(), re.IGNORECASE)
        except re.error:
            pass
        
        try:
            text_filter_re = re.compile(self.filter_text_input.text(), re.IGNORECASE)
        except re.error:
            pass
        
        selected_class = self._active_class_for_threshold_setting
        show_all_classes = (selected_class == "Alle Klassen")
        
        for i in range(self.tree.topLevelItemCount()):
            parent_item = self.tree.topLevelItem(i)
            class_name = parent_item.text(0)
            
            # Class selector filter
            if not show_all_classes and class_name != selected_class:
                parent_item.setHidden(True)
                continue
            
            # Class name filter
            class_visible = True
            if class_filter_re:
                if not class_filter_re.search(class_name):
                    class_visible = False
            
            visible_child_count = 0
            for j in range(parent_item.childCount()):
                child_item = parent_item.child(j)
                row_id = child_item.data(0, QtCore.Qt.UserRole)
                
                if row_id is None:
                    child_item.setHidden(True)
                    continue
                
                row_data_list = self.df_all[self.df_all['row_id'] == row_id]
                if row_data_list.empty:
                    child_item.setHidden(True)
                    continue
                
                row = row_data_list.iloc[0]
                
                #  Initialize child_visible immediately
                child_visible = True
                
                # Confidence filter
                conf = row.get('conf', 0.0)
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(class_name, 0.0)
                if conf < g or conf < c:
                    child_visible = False
                
                # Text filter
                if child_visible and text_filter_re:
                    text_col0 = child_item.text(0)
                    text_col1 = child_item.text(1)
                    text_col2 = child_item.text(2)
                    
                    if not (text_filter_re.search(text_col0) or 
                            text_filter_re.search(text_col1) or 
                            text_filter_re.search(text_col2)):
                        child_visible = False
                
                child_item.setHidden(not child_visible)
                if child_visible:
                    visible_child_count += 1
            
            parent_item.setHidden(visible_child_count == 0 or not class_visible)
        
        self.tree.blockSignals(False)
        self.clear_hover_highlight()

    # ========================================================================
    # RISK FILTERING AND COUNTER METHODS - Matching Erkennungsqualität
    # ========================================================================

    def _filter_by_risk(self, level: str):
        """
        Filter tree items by risk level (matching Erkennungsqualität criteria).

        Args:
            level: 'high_risk' (>20%), 'medium_risk' (10-20%), or 'low_risk' (<10%)
        """
        # Toggle behavior - if same filter clicked, clear it
        if self._current_risk_filter == level:
            self._clear_risk_filter()
            return

        # Uncheck other buttons
        self.high_risk_btn.setChecked(level == 'high_risk')
        self.medium_risk_btn.setChecked(level == 'medium_risk')
        self.low_risk_btn.setChecked(level == 'low_risk')

        self._current_risk_filter = level

        # Apply filter to tree
        self.tree.blockSignals(True)

        for i in range(self.tree.topLevelItemCount()):
            parent_item = self.tree.topLevelItem(i)
            visible_child_count = 0

            for j in range(parent_item.childCount()):
                child_item = parent_item.child(j)
                row_id = child_item.data(0, QtCore.Qt.UserRole)

                if row_id is None:
                    child_item.setHidden(True)
                    continue

                # Get row from dataframe
                row_data = self.df_all[self.df_all['row_id'] == row_id]
                if row_data.empty:
                    child_item.setHidden(True)
                    continue

                row = row_data.iloc[0]
                risk_score, _ = calculate_row_risk_score(row)

                # Determine visibility based on risk level
                show = False
                if level == 'high_risk' and risk_score > 0.20:
                    show = True
                elif level == 'medium_risk' and 0.10 <= risk_score <= 0.20:
                    show = True
                elif level == 'low_risk' and risk_score < 0.10:
                    show = True

                child_item.setHidden(not show)
                if show:
                    visible_child_count += 1

            parent_item.setHidden(visible_child_count == 0)

        self.tree.blockSignals(False)

        level_labels = {
            'high_risk': 'Sofort prüfen',
            'medium_risk': 'Bald prüfen',
            'low_risk': 'Gut erkannt'
        }
        self._set_status(f"Filter: {level_labels.get(level, level)} - {self._count_visible_items()} Elemente")

    def _clear_risk_filter(self):
        """Clear risk filter and show all items."""
        self._current_risk_filter = None
        self.high_risk_btn.setChecked(False)
        self.medium_risk_btn.setChecked(False)
        self.low_risk_btn.setChecked(False)

        # Re-apply standard filters (class/text)
        self._apply_all_filters()
        self._set_status("Filter zurückgesetzt - Alle Elemente angezeigt")

    def _count_visible_items(self) -> int:
        """Count currently visible tree items."""
        count = 0
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            if not parent.isHidden():
                for j in range(parent.childCount()):
                    if not parent.child(j).isHidden():
                        count += 1
        return count

    def _jump_to_next_risk_item(self):
        """Jump to the next high-risk item (risk > 20%)."""
        if self.df_all is None or self.df_all.empty:
            return

        # Get current selection
        selected = self.tree.selectedItems()
        current_row_id = None
        if selected:
            current_row_id = selected[0].data(0, QtCore.Qt.UserRole)

        # Find high-risk items
        high_risk_row_ids = []
        for _, row in self.df_all.iterrows():
            # Skip coordinate and weichen_block (same as Erkennungsqualität)
            if row.get('cls') in ['coordinate', 'weichen_block']:
                continue
            risk_score, _ = calculate_row_risk_score(row)
            if risk_score > 0.20:
                high_risk_row_ids.append(row['row_id'])

        if not high_risk_row_ids:
            self._set_status("Keine Elemente zum Prüfen gefunden!")
            return

        # Sort for consistent ordering
        high_risk_row_ids.sort()

        # Find next problem after current selection
        next_row_id = None
        if current_row_id is not None and current_row_id in high_risk_row_ids:
            idx = high_risk_row_ids.index(current_row_id)
            if idx + 1 < len(high_risk_row_ids):
                next_row_id = high_risk_row_ids[idx + 1]
            else:
                next_row_id = high_risk_row_ids[0]  # Wrap to first
        else:
            next_row_id = high_risk_row_ids[0]  # Start from first

        # Select the item in tree
        if next_row_id in self.row_id_to_tree_item:
            tree_item = self.row_id_to_tree_item[next_row_id]

            # Clear filter first if item is hidden
            if tree_item.isHidden():
                self._clear_risk_filter()

            self.tree.clearSelection()
            tree_item.setSelected(True)
            self.tree.scrollToItem(tree_item)
            self._set_status(f"Prüfen: {high_risk_row_ids.index(next_row_id) + 1}/{len(high_risk_row_ids)}")

    def _update_problem_counts(self):
        """Update the risk counter bar with current counts using Erkennungsqualität criteria."""
        if self.df_all is None or self.df_all.empty:
            self.high_risk_btn.setText("0 Sofort prüfen")
            self.medium_risk_btn.setText("0 Bald prüfen")
            self.low_risk_btn.setText("0 Gut erkannt")
            self.next_problem_btn.setEnabled(False)
            return

        counts = count_risk_categories(self.df_all)

        self.high_risk_btn.setText(f"{counts['high_risk']} Sofort prüfen")
        self.medium_risk_btn.setText(f"{counts['medium_risk']} Bald prüfen")
        self.low_risk_btn.setText(f"{counts['low_risk']} Gut erkannt")

        # Enable/disable next problem button
        self.next_problem_btn.setEnabled(counts['high_risk'] > 0)

    # Quick Correction Panel removed - edit directly in tree

    def _create_items_for_page(self, pidx: int):
        """Create graphics items for page"""
        self.current_row_items.clear()
        
        text_brush = QtGui.QBrush(QtCore.Qt.black)
        normal, highlight, hover, _, _ = self._get_theme_colors()
        pen = QtGui.QPen(normal, 2)
        specs = self.all_page_row_specs.get(pidx, {})
        
        # Debug summary (reduced output)
        print(f"\n Creating overlays for page {pidx}, {len(specs)} specs")
        df_page = self.page_dfs.get(pidx)
        # Count custom symbols
        if df_page is not None and 'is_custom_symbol' in df_page.columns:
            custom_count = (df_page['is_custom_symbol'] == True).sum()
            if custom_count > 0:
                print(f" {custom_count} custom symbols in page_dfs")

        selected_class = self._active_class_for_threshold_setting
        show_all_classes = (selected_class == "Alle Klassen")
        
        created_count = 0
        skipped_hidden = 0
        skipped_filter = 0
        
        for row_id, spec in specs.items():
            dfp = self.page_dfs.get(pidx)
            if dfp is not None:
                m = dfp[dfp['row_id'] == row_id]
                if m.empty:
                    continue
                
                # Skip hidden rows (haltepunkt-connected signals)
                # Note: Must use == True to avoid NaN being treated as truthy
                hidden_val = m.iloc[0].get('_hidden', False)
                if hidden_val == True:
                    skipped_hidden += 1
                    continue
                
                conf = m['conf'].iloc[0]
                cls = m['cls'].iloc[0]
                
                if not show_all_classes and cls != selected_class:
                    skipped_filter += 1
                    continue
                
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(cls, 0.0)
                if conf < g or conf < c:
                    skipped_filter += 1
                    continue
            
            label = spec["label"]
            
            # Check if this row has multiple bounding boxes (merged signal)
            row_data = dfp[dfp['row_id'] == row_id].iloc[0] if dfp is not None and not m.empty else None
            all_bboxes = row_data.get('_all_bboxes') if row_data is not None else None

            #  Priority 1: Check if spec OR dataframe row has polygon data
            has_poly_in_spec = spec.get("is_poly", False)
            has_poly_in_row = False
            if row_data is not None:
                poly_field = row_data.get('poly')
                # Check if poly is a valid polygon (list/array of 4 points)
                if isinstance(poly_field, (list, tuple, np.ndarray)):
                    try:
                        poly_arr = np.array(poly_field, dtype=np.float32)
                        if poly_arr.size == 8:  # 4 points x 2 coords = 8 values
                            has_poly_in_row = True
                    except Exception:
                        pass

            if has_poly_in_spec or has_poly_in_row:
                # Has pre-computed polygon - use spec rendering (preserves rotation)
                # If spec doesn't have it but row does, copy polygon from row to spec
                if not has_poly_in_spec and has_poly_in_row:
                    try:
                        pts = np.array(row_data['poly'], dtype=np.float32).reshape(4, 2)
                        spec = dict(spec)  # Copy spec to avoid modifying original
                        spec["is_poly"] = True
                        spec["pts"] = pts
                    except Exception:
                        pass  # Silently skip if polygon copy fails
                # Fall through to normal rendering with polygon data
            elif all_bboxes is not None and isinstance(all_bboxes, (list, tuple)) and len(all_bboxes) > 0:
                # Use first bbox (coordinate overlay) only if no poly data
                first_bbox = all_bboxes[0]
                self._create_single_overlay_from_bbox(row_id, first_bbox, pen, text_brush)
                created_count += 1
                continue  # Skip the normal rendering below

            # Normal rendering (including merged signals with poly data)
            #  Get confidence and determine pen color
            pen_color = normal  # Default theme color
            pen_width = 2

            if dfp is not None and not m.empty:
                # Priority 0: Custom symbols (magenta/purple) - NEW SYMBOLS!
                # Note: Must use == True to avoid NaN being treated as truthy
                is_custom_val = row_data.get('is_custom_symbol', False) if row_data is not None else False
                is_custom = (is_custom_val == True)  # Explicit check, NaN != True so this is False
                if is_custom:
                    pen_color = QtGui.QColor(255, 0, 255)  # Magenta for custom symbols
                    pen_width = 3
                    print(f" Row {row_id} ({cls}): CUSTOM SYMBOL detected, drawing in Magenta")

                # Priority 1: Error rows (red)
                elif hasattr(self, 'error_rows') and row_id in self.error_rows:
                    pen_color = QtGui.QColor(255, 0, 0)  # Red
                    pen_width = 3
                    print(f"Row {row_id} ({cls}): ERROR ROW - Red")

                # Priority 2: Confidence-based coloring (if enabled)
                elif hasattr(self, 'show_confidence_colors') and self.show_confidence_colors:
                    pen_width = 4  # Bolder lines for confidence colors
                    if conf >= 0.8:
                        pen_color = QtGui.QColor(0, 255, 0)  # Bright green
                    elif conf >= 0.6:
                        pen_color = QtGui.QColor(255, 255, 0)  # Bright yellow
                    else:
                        pen_color = QtGui.QColor(255, 50, 0)  # Bright red-orange (low confidence)
                # else: Normal theme color (no debug spam)

            # Create pen with determined color
            item_pen = QtGui.QPen(pen_color, pen_width)

            if spec.get("is_poly", False):
                pts = spec["pts"]
                # Get angle from row data if available
                angle = 0.0
                if dfp is not None and not m.empty:
                    angle = m.iloc[0].get('angle', 0.0)

                # Create resizable polygon bbox
                poly_item = ResizablePolygonBBoxItem(
                    qpolygonf_from_pts(pts),
                    int(row_id),
                    self,
                    angle
                )
                poly_item.setPen(item_pen)  # Use confidence-based pen
                poly_item.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                poly_item.setData(0, int(row_id))

                x_pos, y_pos = float(pts[:, 0].min()), float(pts[:, 1].min())
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x_pos, y_pos - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                self.scene.addItem(poly_item)
                self.scene.addItem(ti)

                # Check for OCR region bbox and create cyan dashed box
                items_list = [poly_item, ti]
                # Debug: Check if OCR columns exist
                if row_data is not None:
                    has_ocr_col = 'ocr_x1' in row_data.index if hasattr(row_data, 'index') else 'ocr_x1' in row_data
                    ocr_val = row_data.get('ocr_x1') if has_ocr_col else None
                    if has_ocr_col and ocr_val is not None:
                        print(f"DEBUG: Polygon Row {row_id} has OCR data: ocr_x1={ocr_val}")
                if row_data is not None and pd.notna(row_data.get('ocr_x1')):
                    ocr_x1 = float(row_data['ocr_x1'])
                    ocr_y1 = float(row_data['ocr_y1'])
                    ocr_x2 = float(row_data['ocr_x2'])
                    ocr_y2 = float(row_data['ocr_y2'])
                    ocr_w = ocr_x2 - ocr_x1
                    ocr_h = ocr_y2 - ocr_y1

                    # Import OCR bbox class
                    from ui.resizable_bbox import ResizableOCRBBoxItem

                    # Create OCR region box
                    ocr_rect = ResizableOCRBBoxItem(ocr_x1, ocr_y1, ocr_w, ocr_h, int(row_id), self)

                    # Style: Use same color as symbol bbox
                    ocr_pen = QtGui.QPen(pen_color)  # Match symbol color
                    ocr_pen.setStyle(QtCore.Qt.DashLine)  # Dashed
                    ocr_pen.setWidth(2)
                    ocr_rect.setPen(ocr_pen)
                    ocr_rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                    ocr_rect.setData(0, int(row_id))
                    ocr_rect.setZValue(5)  # Above symbol bbox but below handles

                    # Add label showing OCR text and confidence
                    # Use black text (same as main symbol labels)
                    ocr_text = row_data.get('anchor_text', '')
                    if ocr_text:
                        ocr_conf = row_data.get('anchor_conf', None)
                        if pd.notna(ocr_conf):
                            ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text} {ocr_conf:.2f}")
                        else:
                            ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text}")
                        ocr_label.setBrush(text_brush)  # Black text like main labels
                        ocr_label.setPos(ocr_x1, ocr_y1 - 40)
                        ocr_label.setData(0, int(row_id))
                        ocr_label.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                        ocr_label.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        self.scene.addItem(ocr_label)
                        items_list.append(ocr_label)

                    self.scene.addItem(ocr_rect)
                    items_list.append(ocr_rect)

                self.current_row_items[int(row_id)] = items_list
                created_count += 1
            else:
                x1, y1, w, h = spec["rect"]
                # Create resizable rect bbox with auto-OCR on resize
                rect = ResizableBBoxItem(x1, y1, w, h, int(row_id), self)
                rect.setPen(item_pen)  # Use confidence-based pen
                rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                rect.setData(0, int(row_id))

                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x1, y1 - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                self.scene.addItem(rect)
                self.scene.addItem(ti)

                # Check for OCR region bbox and create cyan dashed box
                items_list = [rect, ti]
                # Debug: Check if OCR columns exist
                if row_data is not None:
                    has_ocr_col = 'ocr_x1' in row_data.index if hasattr(row_data, 'index') else 'ocr_x1' in row_data
                    ocr_val = row_data.get('ocr_x1') if has_ocr_col else None
                    if has_ocr_col and ocr_val is not None:
                        print(f"DEBUG: Row {row_id} has OCR data: ocr_x1={ocr_val}")
                if row_data is not None and pd.notna(row_data.get('ocr_x1')):
                    ocr_x1 = float(row_data['ocr_x1'])
                    ocr_y1 = float(row_data['ocr_y1'])
                    ocr_x2 = float(row_data['ocr_x2'])
                    ocr_y2 = float(row_data['ocr_y2'])
                    ocr_w = ocr_x2 - ocr_x1
                    ocr_h = ocr_y2 - ocr_y1

                    # Import OCR bbox class
                    from ui.resizable_bbox import ResizableOCRBBoxItem

                    # Create OCR region box
                    ocr_rect = ResizableOCRBBoxItem(ocr_x1, ocr_y1, ocr_w, ocr_h, int(row_id), self)

                    # Style: Use same color as symbol bbox
                    ocr_pen = QtGui.QPen(pen_color)  # Match symbol color
                    ocr_pen.setStyle(QtCore.Qt.DashLine)  # Dashed
                    ocr_pen.setWidth(2)
                    ocr_rect.setPen(ocr_pen)
                    ocr_rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                    ocr_rect.setData(0, int(row_id))
                    ocr_rect.setZValue(5)  # Above symbol bbox but below handles

                    # Add label showing OCR text and confidence
                    # Use black text (same as main symbol labels)
                    ocr_text = row_data.get('anchor_text', '')
                    if ocr_text:
                        ocr_conf = row_data.get('anchor_conf', None)
                        if pd.notna(ocr_conf):
                            ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text} {ocr_conf:.2f}")
                        else:
                            ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text}")
                        ocr_label.setBrush(text_brush)  # Black text like main labels
                        ocr_label.setPos(ocr_x1, ocr_y1 - 40)
                        ocr_label.setData(0, int(row_id))
                        ocr_label.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                        ocr_label.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        self.scene.addItem(ocr_label)
                        items_list.append(ocr_label)

                    self.scene.addItem(ocr_rect)
                    items_list.append(ocr_rect)

                self.current_row_items[int(row_id)] = items_list
                created_count += 1

        #  ADD THIS SUMMARY
        print(f"\n   Summary:")
        print(f"Created: {created_count}")
        print(f"Skipped (hidden): {skipped_hidden}")
        print(f"Skipped (filters): {skipped_filter}")
        print(f"Total in current_row_items: {len(self.current_row_items)}\n")

    def highlight_row_graphics(self, row_id: int, highlight: bool = True, hover: bool = False):
        """Highlight graphics for row"""
        items = self.current_row_items.get(row_id)
        if not items:
            return
        normal, hi, hov, _, _ = self._get_theme_colors()
        color = hov if hover else (hi if highlight else normal)
        pen = QtGui.QPen(color, 3 if (highlight or hover) else 2)
        for it in list(items):
            try:
                if isinstance(it, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem)):
                    it.setPen(pen)
            except RuntimeError:
                try:
                    items.remove(it)
                except Exception:
                    pass
    
    def zoom_to_row(self, row_id: int):
        """Zoom to row in graphics"""
        if row_id not in self.current_row_items:
            return
        item = next((i for i in self.current_row_items[row_id] 
                    if isinstance(i, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem))), None)
        if not item:
            return
        srect = item.sceneBoundingRect()
        c = srect.center()
        zr = QtCore.QRectF(c.x() - ZOOM_SIZE/2, c.y() - ZOOM_SIZE/2, ZOOM_SIZE, ZOOM_SIZE).intersected(self.scene.sceneRect())
        self.view.setTransform(QtGui.QTransform())
        self.view.fitInView(zr, QtCore.Qt.KeepAspectRatioByExpanding)
        self.view.centerOn(c)


    def on_tree_selection_changed(self):
        """Handle tree selection change - with overlay cycling on repeated clicks"""
        if self._is_selecting_from_scene:
            return
        if self._is_selecting_from_scene:
            return

        items = self.tree.selectedItems()
        if not items:
            self.item_details_notes.clear()
            return

        self.clear_hover_highlight()

        for rid in self.current_row_items.keys():
            self.highlight_row_graphics(rid, highlight=False)

        selected_item = items[0]

        if selected_item.childCount() > 0:
            self.item_details_notes.clear()
            return

        row_id = selected_item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            self.item_details_notes.clear()
            return

        # Highlight and zoom
        self.highlight_row_graphics(row_id, True)
        self.zoom_to_row(row_id)
        
        row_data_list = self.df_all[self.df_all['row_id'] == row_id]
        if row_data_list.empty:
            return
        row = row_data_list.iloc[0]
        
        details = (
            f"Klasse: {row.get('cls','')}\n"
            f"Konfidenz: {row.get('conf','')}\n"
            f"Anker Text: {row.get('anchor_text','')}\n"
            f"Koord Text: {row.get('coord_text','')}\n"
        )
        
        if row.get('cls') == 'signal' and pd.notna(row.get('fahrtrichtung')):
            details += f"Fahrtrichtung: {row.get('fahrtrichtung','')}\n"
        
        details += f"Seite: {row.get('page','')}\n"
        details += f"--- Notizen ---\n{row.get('notes','')}"
        
        self.item_details_notes.blockSignals(True)
        self.item_details_notes.setPlainText(details)
        self.item_details_notes.blockSignals(False)


    def on_tree_item_hovered(self, item, column):
        """Handle tree item hover"""
        self.clear_hover_highlight()
        
        if item is None or item.childCount() > 0:
            return
        
        row_id = item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            return
        
        if not item.isSelected():
            self.highlight_row_graphics(row_id, highlight=False, hover=True)
            self._last_hovered_row_id = row_id
    
    def on_table_leave(self):
        """Handle mouse leaving table"""
        self.clear_hover_highlight()
    
    def clear_hover_highlight(self):
        """Clear hover highlight"""
        if self._last_hovered_row_id is not None:
            item = self.row_id_to_tree_item.get(self._last_hovered_row_id)
            is_sel = item.isSelected() if item else False
            
            if not is_sel:
                self.highlight_row_graphics(self._last_hovered_row_id, highlight=False)
            self._last_hovered_row_id = None
    
    def on_scene_selection(self):
        """Handle scene selection"""
        if _is_deleted(self.scene):
            return
        try:
            sel = [it for it in self.scene.selectedItems() if it is not None]
        except RuntimeError:
            return
        
        for rid in list(self.current_row_items.keys()):
            self.highlight_row_graphics(rid, False)
        
        if not sel:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.blockSignals(False)
            self.item_details_notes.clear()
            return
        
        rid = None
        for it in sel:
            try:
                data = it.data(0)
                if data is not None:
                    rid = int(data)
                    break
            except Exception:
                continue
        
        if rid is None:
            return
        
        self.highlight_row_graphics(rid, True)
        
        self._is_selecting_from_scene = True
        item = self.row_id_to_tree_item.get(rid)
        if item:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            item.setSelected(True)
            self.tree.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
            self.tree.blockSignals(False)
        self._is_selecting_from_scene = False
        
        row_data_list = self.df_all[self.df_all['row_id'] == rid]
        if row_data_list.empty:
            return
        row = row_data_list.iloc[0]
        
        details = (
            f"Klasse: {row.get('cls','')}\n"
            f"Konfidenz: {row.get('conf','')}\n"
            f"Anker Text: {row.get('anchor_text','')}\n"
            f"Koord Text: {row.get('coord_text','')}\n"
        )
        
        if row.get('cls') == 'signal' and pd.notna(row.get('fahrtrichtung')):
            details += f"Fahrtrichtung: {row.get('fahrtrichtung','')}\n"
        
        details += f"Seite: {row.get('page','')}\n"
        details += f"--- Notizen ---\n{row.get('notes','')}"
        
        self.item_details_notes.blockSignals(True)
        self.item_details_notes.setPlainText(details)
        self.item_details_notes.blockSignals(False)
    
    def on_item_notes_changed(self):
        """Handle notes change"""
        sel = self.tree.selectedItems()
        if not sel:
            return
        
        item = sel[0]
        if item.childCount() > 0:
            return
        
        row_id = item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            return
        
        full_text = self.item_details_notes.toPlainText()
        notes_marker = "--- Notizen ---\n"
        notes_only = ""
        if notes_marker in full_text:
            try:
                notes_only = full_text.split(notes_marker, 1)[1]
            except Exception:
                pass
        
        idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
        if idx_list:
            idx = idx_list[0]
            if self.df_all.at[idx, 'notes'] != notes_only:
                self.df_all.at[idx, 'notes'] = notes_only
    
    def on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handle tree item edit"""
        self.tree.blockSignals(True)
        
        try:
            if not item or item.childCount() > 0:
                self.tree.blockSignals(False)
                return
            
            row_id = item.data(0, QtCore.Qt.UserRole)
            if row_id is None:
                self.tree.blockSignals(False)
                return

            new_text = item.text(column)
            cls = self.get_class_for_row_id(row_id)
            if cls is None:
                # Row not found in df_all - shouldn't happen but handle gracefully
                print(f"Warning: row_id {row_id} not found in df_all, skipping edit")
                return
            is_coord_class = (cls == 'coordinate')

            # Determine what column is being updated FIRST (needed for precise undo collection)
            col_to_update = None
            is_coord_update = False

            if is_coord_class:
                if column == 0:
                    col_to_update = 'coord_text'
                    is_coord_update = True
            else:
                if column == 0:
                    col_to_update = 'anchor_text'
                elif column == 1:
                    col_to_update = 'coord_text'
                    is_coord_update = True
                elif column == 2 and cls == 'signal':
                    col_to_update = 'fahrtrichtung'

            # Collect all affected row_ids for undo (including linked anchors/coordinates)
            # Only collect linked items when we'll actually propagate to them
            affected_row_ids = [row_id]
            if is_coord_class and is_coord_update and 'link_coord_row_id' in self.df_all.columns:
                # Coordinate coord_text edit → collect linked anchors (forward propagation)
                linked_anchors = self.df_all[self.df_all['link_coord_row_id'] == row_id]
                if not linked_anchors.empty:
                    affected_row_ids.extend(linked_anchors['row_id'].tolist())
            elif not is_coord_class and is_coord_update and 'link_coord_row_id' in self.df_all.columns:
                # Anchor coord_text edit → collect linked coordinate (reverse propagation)
                row_mask = self.df_all['row_id'] == row_id
                if row_mask.any():
                    link_coord_id = self.df_all.loc[row_mask, 'link_coord_row_id'].iloc[0]
                    if pd.notna(link_coord_id):
                        affected_row_ids.append(int(link_coord_id))

            self._save_state("Zelle bearbeitet", affected_row_ids)

            if col_to_update:
                # Parse coordinate once if needed (reuse for df_all, page_dfs, and propagation)
                parsed_val, parsed_gi = None, None
                if is_coord_update:
                    parsed_val, parsed_gi = parse_coord(new_text)

                # Initialize old_anchor_text before the if block (in case idx_list is empty)
                old_anchor_text = None

                idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
                if idx_list:
                    idx = idx_list[0]
                    # Save old anchor_text before update (for name-change detection)
                    if col_to_update == 'anchor_text':
                        old_anchor_text = self.df_all.loc[idx, 'anchor_text']
                    self.df_all.loc[idx, col_to_update] = new_text

                    if is_coord_update:
                        self.df_all.loc[idx, 'coord_value'] = parsed_val
                        self.df_all.loc[idx, 'gi_gl'] = parsed_gi

                df_page = self.page_dfs.get(self.current_page)
                if df_page is not None:
                    idx_list_page = df_page.index[df_page['row_id'] == row_id].tolist()
                    if idx_list_page:
                        idx_p = idx_list_page[0]
                        df_page.loc[idx_p, col_to_update] = new_text
                        if is_coord_update:
                            df_page.loc[idx_p, 'coord_value'] = parsed_val
                            df_page.loc[idx_p, 'gi_gl'] = parsed_gi

                # Auto-merge and recalculate Fahrtrichtung when signal name (anchor_text) changes
                if col_to_update == 'anchor_text' and cls == 'signal':
                    # Only recalculate if name actually changed (fix: prevent unnecessary recalc)
                    old_name_upper = str(old_anchor_text or '').upper().strip()
                    new_name_upper = str(new_text or '').upper().strip()
                    if new_name_upper != old_name_upper:
                        self._merge_and_recalculate_fahrtrichtung(row_id, new_text, item)
                    else:
                        print(f"Skipping Fahrtrichtung recalc: name unchanged ('{new_text}')")

                # Update overlay label to reflect the change
                items = self.current_row_items.get(row_id)
                row_mask = self.df_all['row_id'] == row_id
                if items and row_mask.any():
                    updated_row = self.df_all[row_mask].iloc[0]

                    # Rebuild label: {cls} {conf} | {anchor_text} | {coord_text} θ={angle}°
                    label = f"{updated_row['cls']} {updated_row.get('conf', '')}"
                    if pd.notna(updated_row.get('anchor_text')) and updated_row['anchor_text']:
                        label += f" | {updated_row['anchor_text']}"
                    if pd.notna(updated_row.get('coord_text')) and updated_row['coord_text']:
                        label += f" | {updated_row['coord_text']}"
                    if pd.notna(updated_row.get('angle')):
                        try:
                            label += f" θ={float(updated_row['angle']):.1f}°"
                        except Exception:
                            pass

                    # Update the text label item
                    for it in items:
                        if isinstance(it, QtWidgets.QGraphicsSimpleTextItem):
                            it.setText(label)
                            break

                    # Update spec for persistence
                    specs = self.all_page_row_specs.get(self.current_page, {})
                    if row_id in specs:
                        specs[row_id]['label'] = label

                # Propagate coordinate changes to linked anchors
                # Only propagate if is_coord_update is True (so parsed_val/parsed_gi are defined)
                if is_coord_class and is_coord_update and 'link_coord_row_id' in self.df_all.columns:
                    linked_anchors = self.df_all[self.df_all['link_coord_row_id'] == row_id]
                    if not linked_anchors.empty:
                        # Reuse parsed_val/parsed_gi from earlier (already parsed at line 2526)
                        for linked_idx in linked_anchors.index:
                            linked_row_id = self.df_all.loc[linked_idx, 'row_id']
                            linked_page = int(self.df_all.loc[linked_idx, 'page'])

                            # Update coord_text in df_all
                            self.df_all.loc[linked_idx, 'coord_text'] = new_text
                            self.df_all.loc[linked_idx, 'coord_value'] = parsed_val
                            self.df_all.loc[linked_idx, 'gi_gl'] = parsed_gi

                            # Update in page_dfs
                            if linked_page in self.page_dfs:
                                page_row_mask = self.page_dfs[linked_page]['row_id'] == linked_row_id
                                if page_row_mask.any():
                                    page_row_idx = self.page_dfs[linked_page][page_row_mask].index[0]
                                    self.page_dfs[linked_page].loc[page_row_idx, 'coord_text'] = new_text
                                    self.page_dfs[linked_page].loc[page_row_idx, 'coord_value'] = parsed_val
                                    self.page_dfs[linked_page].loc[page_row_idx, 'gi_gl'] = parsed_gi

                            # Update tree item (signals already blocked at function start)
                            linked_tree_item = self.row_id_to_tree_item.get(linked_row_id)
                            if linked_tree_item:
                                linked_tree_item.setText(1, new_text)  # coord_text in column 1

                            # Update graphics label (only if on current page)
                            if linked_page == self.current_page:
                                linked_items = self.current_row_items.get(linked_row_id)
                                if linked_items:
                                    linked_row = self.df_all.loc[linked_idx]
                                    linked_label = f"{linked_row['cls']} {linked_row.get('conf', '')}"
                                    if pd.notna(linked_row.get('anchor_text')) and linked_row['anchor_text']:
                                        linked_label += f" | {linked_row['anchor_text']}"
                                    if pd.notna(linked_row.get('coord_text')) and linked_row['coord_text']:
                                        linked_label += f" | {linked_row['coord_text']}"
                                    if pd.notna(linked_row.get('angle')):
                                        try:
                                            linked_label += f" θ={float(linked_row['angle']):.1f}°"
                                        except Exception:
                                            pass

                                    for linked_it in linked_items:
                                        if isinstance(linked_it, QtWidgets.QGraphicsSimpleTextItem):
                                            linked_it.setText(linked_label)
                                            break

                                    # Update linked anchor spec for persistence
                                    linked_specs = self.all_page_row_specs.get(linked_page, {})
                                    if linked_row_id in linked_specs:
                                        linked_specs[linked_row_id]['label'] = linked_label

                # Reverse propagation: Anchor coord_text → linked Coordinate
                if not is_coord_class and is_coord_update and 'link_coord_row_id' in self.df_all.columns:
                    # Get the linked coordinate row_id from this anchor
                    anchor_mask = self.df_all['row_id'] == row_id
                    if anchor_mask.any():
                        link_coord_id = self.df_all.loc[anchor_mask, 'link_coord_row_id'].iloc[0]
                        if pd.notna(link_coord_id):
                            link_coord_id = int(link_coord_id)
                            coord_mask = self.df_all['row_id'] == link_coord_id
                            if coord_mask.any():
                                coord_idx = self.df_all[coord_mask].index[0]
                                coord_page = int(self.df_all.loc[coord_idx, 'page'])

                                # Reuse parsed_val/parsed_gi (already parsed earlier)

                                # Update coordinate in df_all
                                self.df_all.loc[coord_idx, 'coord_text'] = new_text
                                self.df_all.loc[coord_idx, 'coord_value'] = parsed_val
                                self.df_all.loc[coord_idx, 'gi_gl'] = parsed_gi

                                # Update in page_dfs
                                if coord_page in self.page_dfs:
                                    coord_page_mask = self.page_dfs[coord_page]['row_id'] == link_coord_id
                                    if coord_page_mask.any():
                                        coord_page_idx = self.page_dfs[coord_page][coord_page_mask].index[0]
                                        self.page_dfs[coord_page].loc[coord_page_idx, 'coord_text'] = new_text
                                        self.page_dfs[coord_page].loc[coord_page_idx, 'coord_value'] = parsed_val
                                        self.page_dfs[coord_page].loc[coord_page_idx, 'gi_gl'] = parsed_gi

                                # Update coordinate's tree item
                                coord_tree_item = self.row_id_to_tree_item.get(link_coord_id)
                                if coord_tree_item:
                                    coord_tree_item.setText(0, new_text)  # coord_text in column 0 for coordinates

                                # Update coordinate's graphics label (only if on current page)
                                if coord_page == self.current_page:
                                    coord_items = self.current_row_items.get(link_coord_id)
                                    if coord_items:
                                        coord_row = self.df_all.loc[coord_idx]
                                        coord_label = f"{coord_row['cls']} {coord_row.get('conf', '')}"
                                        if pd.notna(coord_row.get('coord_text')) and coord_row['coord_text']:
                                            coord_label += f" | {coord_row['coord_text']}"
                                        if pd.notna(coord_row.get('angle')):
                                            try:
                                                coord_label += f" θ={float(coord_row['angle']):.1f}°"
                                            except Exception:
                                                pass

                                        for coord_it in coord_items:
                                            if isinstance(coord_it, QtWidgets.QGraphicsSimpleTextItem):
                                                coord_it.setText(coord_label)
                                                break

                                        # Update coordinate spec for persistence
                                        coord_specs = self.all_page_row_specs.get(coord_page, {})
                                        if link_coord_id in coord_specs:
                                            coord_specs[link_coord_id]['label'] = coord_label

            # Note: Removed on_tree_selection_changed() call to prevent unwanted zoom on edit

        except Exception as e:
            import traceback
            # Use locals().get() to safely access variables that might not be defined yet
            print(f"Error in on_tree_item_changed (row_id={locals().get('row_id')}, column={column}, cls={locals().get('cls')}): {e}")
            traceback.print_exc()
        finally:
            self.tree.blockSignals(False)

    def _is_vsignal_or_exempt(self, signal_name: str) -> bool:
        """
        Check if signal name is a V-signal or exempt pattern.
        These signal types don't need Fahrtrichtung.

        Exempt patterns:
        - V-signals: Start with 'V' (e.g., V1, V2, VA1)
        - Single letter + 3+ digits: e.g., A123, U456, B789
        """
        if not signal_name:
            return False

        name = signal_name.upper().strip()

        # V-signal check
        if name.startswith("V"):
            return True

        # Single letter + 3+ digits pattern (e.g., A123, U456)
        if (len(name) >= 4 and
            name[0].isalpha() and
            name[1:].isdigit() and
            len(name[1:]) >= 3):
            return True

        return False

    def _get_gks_detections_for_page(self, page: int) -> list:
        """
        Get all GKS detections for a page as detection dicts.
        Returns list of dicts with cx, cy, x1, y1, x2, y2, angle, text.
        """
        gks_dets = []

        df_page = self.page_dfs.get(page)
        if df_page is None:
            return gks_dets

        # Build hidden mask
        if '_hidden' in df_page.columns:
            not_hidden = ~df_page['_hidden'].fillna(False)
        else:
            not_hidden = pd.Series([True] * len(df_page), index=df_page.index)

        gks_rows = df_page[
            df_page['cls'].isin(['gks_gesteuert', 'gks_festkodiert']) &
            not_hidden
        ]

        for _, row in gks_rows.iterrows():
            det = {
                'x1': row.get('ax1'),
                'y1': row.get('ay1'),
                'x2': row.get('ax2'),
                'y2': row.get('ay2'),
                'cx': row.get('xc'),
                'cy': row.get('yc'),
                'angle': row.get('angle', 0.0),
                'text': row.get('anchor_text', ''),
                'row_id': row.get('row_id'),
            }
            gks_dets.append(det)

        return gks_dets

    def _recalculate_fahrtrichtung_for_signal(self, row_id: int, new_signal_name: str) -> Optional[str]:
        """
        Recalculate Fahrtrichtung when signal name is changed.

        3-step logic:
        1. V-signal/exempt check: If name is V-signal or exempt pattern → clear Fahrtrichtung
        2. Unanimous inheritance: Look for other signals with same name, inherit if ALL have same Fahrtrichtung
        3. GKS detection: Run 4-tier GKS detection system

        Returns: New Fahrtrichtung value ('A', 'B', or None)
        """
        print(f"\n{'='*60}")
        print(f"FAHRTRICHTUNG RECALC: Signal name changed to '{new_signal_name}'")
        print(f"{'='*60}")

        # STEP 1: V-signal / Exempt check
        if self._is_vsignal_or_exempt(new_signal_name):
            print(f"Step 1: '{new_signal_name}' is V-signal or exempt → Fahrtrichtung = None")
            return None

        print(f"Step 1: '{new_signal_name}' is not exempt, continuing...")

        # STEP 2: Unanimous inheritance from same-named signals
        if self.df_all is not None:
            # Build hidden mask (exclude hidden/merged rows)
            if '_hidden' in self.df_all.columns:
                not_hidden = ~self.df_all['_hidden'].fillna(False)
            else:
                not_hidden = pd.Series([True] * len(self.df_all), index=self.df_all.index)

            # Handle NaN in anchor_text for comparison
            anchor_upper = self.df_all['anchor_text'].fillna('').str.upper().str.strip()

            # Find other signals with the same name (excluding current row and hidden rows)
            same_name_signals = self.df_all[
                (self.df_all['cls'] == 'signal') &
                (anchor_upper == new_signal_name.upper().strip()) &
                (self.df_all['row_id'] != row_id) &
                (self.df_all['fahrtrichtung'].notna()) &
                (self.df_all['fahrtrichtung'].isin(['A', 'B'])) &
                not_hidden
            ]

            if not same_name_signals.empty:
                # Get unique Fahrtrichtung values
                unique_fahrt = same_name_signals['fahrtrichtung'].unique()

                if len(unique_fahrt) == 1:
                    # Unanimous - all same-named signals have the same Fahrtrichtung
                    inherited_fahrt = unique_fahrt[0]
                    print(f"Step 2: Found {len(same_name_signals)} signals with name '{new_signal_name}', all have Fahrtrichtung '{inherited_fahrt}'")
                    print(f"→ Inheriting Fahrtrichtung = '{inherited_fahrt}'")
                    return inherited_fahrt
                else:
                    # Mixed - different Fahrtrichtung values exist
                    print(f"Step 2: Found {len(same_name_signals)} signals with name '{new_signal_name}', but Fahrtrichtung is mixed: {list(unique_fahrt)}")
                    print(f"→ Cannot inherit, proceeding to GKS detection...")
            else:
                print(f"Step 2: No other signals with name '{new_signal_name}' have Fahrtrichtung set")

        # STEP 3: GKS-based detection (4-tier system)
        print(f"Step 3: Running GKS detection...")

        # Get current row data
        row_list = self.df_all[self.df_all['row_id'] == row_id]
        if row_list.empty:
            print(f"Error: Row {row_id} not found")
            return None

        row = row_list.iloc[0]
        page = row.get('page')

        # Build signal detection dict
        signal_det = self._reconstruct_det_from_row(row)
        signal_det['text'] = new_signal_name  # Use the new name

        # FIX: If merged row has fahrtrichtung_signal position, use those coordinates for GKS detection
        # This ensures recalculation uses the position where fahrtrichtung was originally detected
        signal_positions = row.get('_signal_positions')
        if isinstance(signal_positions, dict) and 'fahrtrichtung_signal' in signal_positions:
            fahr_pos = signal_positions['fahrtrichtung_signal']
            if fahr_pos.get('ax1') is not None:
                print(f"Using fahrtrichtung_signal position for recalculation")
                signal_det['x1'] = fahr_pos.get('ax1')
                signal_det['y1'] = fahr_pos.get('ay1')
                signal_det['x2'] = fahr_pos.get('ax2')
                signal_det['y2'] = fahr_pos.get('ay2')
                # Update center coordinates
                if signal_det['x1'] is not None and signal_det['x2'] is not None:
                    signal_det['cx'] = (signal_det['x1'] + signal_det['x2']) / 2
                    signal_det['cy'] = (signal_det['y1'] + signal_det['y2']) / 2

        # Get GKS detections for the page
        gks_dets = self._get_gks_detections_for_page(page)

        if not gks_dets:
            print(f"No GKS detections on page {page}, cannot determine Fahrtrichtung")
            return None

        print(f"Found {len(gks_dets)} GKS detections on page {page}")

        # TIER 1: Strict GKS detection
        fahrtrichtung = detect_fahrtrichtung(
            signal_det,
            gks_dets,
            track_skeleton=None,
            track_bounds=None,
            max_distance=250
        )

        if fahrtrichtung:
            print(f"Tier 1 (strict GKS): Fahrtrichtung = '{fahrtrichtung}'")
            return fahrtrichtung

        # TIER 3: Relaxed GKS column search (skip Tier 2 track skeleton)
        fahrtrichtung, _ = detect_fahrtrichtung_gks_relaxed(
            signal_det,
            gks_dets,
            used_gks_ids=set()
        )

        if fahrtrichtung:
            print(f"Tier 3 (relaxed GKS): Fahrtrichtung = '{fahrtrichtung}'")
            return fahrtrichtung

        # TIER 4: Nearest GKS fallback
        fahrtrichtung, _ = detect_fahrtrichtung_gks_nearest(
            signal_det,
            gks_dets,
            used_gks_ids=set()
        )

        if fahrtrichtung:
            print(f"Tier 4 (nearest GKS): Fahrtrichtung = '{fahrtrichtung}'")
            return fahrtrichtung

        print(f"All tiers failed, Fahrtrichtung = None")
        return None

    def _merge_and_recalculate_fahrtrichtung(self, row_id: int, new_signal_name: str,
                                              tree_item: QtWidgets.QTreeWidgetItem = None):
        """
        Handle signal name change with merge detection and Fahrtrichtung recalculation.

        Flow:
        1. Check for duplicate signals with same name on same page (with spatial clustering)
        2. If duplicates exist within spatial threshold, merge them (copy data, hide duplicates)
        3. Recalculate Fahrtrichtung for the merged signal
        4. Update UI (tree, graphics)

        Args:
            row_id: The row_id of the signal being edited
            new_signal_name: The new signal name
            tree_item: The tree widget item being edited (optional, will be retrieved if not provided)
        """
        # Get tree_item from dictionary if not provided
        if tree_item is None:
            tree_item = self.row_id_to_tree_item.get(row_id)
        print(f"\n{'='*60}")
        print(f"MERGE + FAHRTRICHTUNG: Signal name changed to '{new_signal_name}'")
        print(f"{'='*60}")

        if self.df_all is None:
            return

        # Get the current row
        idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
        if not idx_list:
            print(f"Error: Row {row_id} not found")
            return

        idx = idx_list[0]
        current_row = self.df_all.loc[idx]
        page = current_row.get('page')

        # Get current signal center
        current_cx = current_row.get('xc') or current_row.get('cx') or (
            (current_row.get('ax1', 0) + current_row.get('ax2', 0)) / 2
        )
        current_cy = current_row.get('yc') or current_row.get('cy') or (
            (current_row.get('ay1', 0) + current_row.get('ay2', 0)) / 2
        )

        # DEBUG: Show current signal info
        print(f"Current signal: row_id={row_id}, page={page}, name='{new_signal_name}'")
        print(f"Current signal center: ({current_cx:.0f}, {current_cy:.0f})")

        # =====================================================================
        # STEP 1: Find duplicate signals with same name on same page
        # =====================================================================
        # Build hidden mask
        if '_hidden' in self.df_all.columns:
            not_hidden = ~self.df_all['_hidden'].fillna(False)
            hidden_count = (~not_hidden).sum()
            print(f"Hidden rows in df_all: {hidden_count}")
        else:
            not_hidden = pd.Series([True] * len(self.df_all), index=self.df_all.index)
            print("No '_hidden' column in df_all")

        # Handle NaN in anchor_text for comparison
        anchor_upper = self.df_all['anchor_text'].fillna('').str.upper().str.strip()
        target_name = new_signal_name.upper().strip()
        print(f"Looking for signals with anchor_text = '{target_name}'")

        # DEBUG: Show all signals on this page
        signals_on_page = self.df_all[
            (self.df_all['cls'] == 'signal') &
            (self.df_all['page'] == page) &
            not_hidden
        ]
        print(f"Total visible signals on page {page}: {len(signals_on_page)}")
        for _, sig in signals_on_page.iterrows():
            sig_name = str(sig.get('anchor_text', '')).upper().strip()
            sig_id = sig.get('row_id')
            match_marker = " <-- MATCH" if sig_name == target_name and sig_id != row_id else ""
            print(f"  - row_id={sig_id}, name='{sig.get('anchor_text', '')}' -> upper='{sig_name}'{match_marker}")

        all_duplicates = self.df_all[
            (self.df_all['cls'] == 'signal') &
            (anchor_upper == target_name) &
            (self.df_all['page'] == page) &
            (self.df_all['row_id'] != row_id) &
            not_hidden
        ]
        print(f"Duplicates found (same name, same page, not hidden, not self): {len(all_duplicates)}")

        # =====================================================================
        # STEP 1B: Spatial clustering - only merge duplicates within threshold
        # =====================================================================
        # Use same default threshold as the pipeline (1500px for few signals)
        SPATIAL_THRESHOLD = 1500  # pixels

        # Filter duplicates by spatial proximity
        nearby_duplicates = []
        for dup_idx, dup_row in all_duplicates.iterrows():
            dup_cx = dup_row.get('xc') or dup_row.get('cx') or (
                (dup_row.get('ax1', 0) + dup_row.get('ax2', 0)) / 2
            )
            dup_cy = dup_row.get('yc') or dup_row.get('cy') or (
                (dup_row.get('ay1', 0) + dup_row.get('ay2', 0)) / 2
            )

            # Calculate 2D Euclidean distance
            distance = ((current_cx - dup_cx) ** 2 + (current_cy - dup_cy) ** 2) ** 0.5

            if distance <= SPATIAL_THRESHOLD:
                nearby_duplicates.append((dup_idx, dup_row, distance))
                print(f"  Nearby duplicate: row_id={dup_row['row_id']}, distance={distance:.0f}px")
            else:
                print(f"  Far duplicate (skip): row_id={dup_row['row_id']}, distance={distance:.0f}px > {SPATIAL_THRESHOLD}px")

        if not nearby_duplicates:
            if all_duplicates.empty:
                print(f"No duplicates found for '{new_signal_name}' on page {page}")
            else:
                print(f"Found {len(all_duplicates)} duplicate(s) but none within spatial threshold ({SPATIAL_THRESHOLD}px)")
        else:
            print(f"Found {len(nearby_duplicates)} nearby duplicate(s) for '{new_signal_name}' on page {page}")

            # =====================================================================
            # STEP 1C: Select best primary instance based on data quality
            # =====================================================================
            # Priority: Instance WITH coordinate > Instance WITHOUT coordinate
            # Tie-breaker: Higher confidence

            def _calculate_primary_score(row_data):
                """Calculate quality score for selecting primary instance."""
                score = 0
                # Coordinate presence is most important (1000 points)
                coord_val = row_data.get('coord_text')
                if pd.notna(coord_val) and coord_val:
                    score += 1000
                # Confidence as tie-breaker (0-10 points)
                score += (row_data.get('conf') or 0) * 10
                # Fahrtrichtung is nice to have (50 points)
                fahrt_val = row_data.get('fahrtrichtung')
                if pd.notna(fahrt_val) and fahrt_val:
                    score += 50
                return score

            # Calculate score for current row (the one being renamed)
            current_score = _calculate_primary_score(current_row)
            current_has_coord = pd.notna(current_row.get('coord_text')) and current_row.get('coord_text')
            print(f"\nPrimary selection - Current row_id={row_id}: score={current_score}, has_coord={current_has_coord}")

            # Find if any duplicate has higher score
            best_primary_idx = idx
            best_primary_row_id = row_id
            best_primary_score = current_score
            best_primary_dup_info = None  # (dup_idx, dup_row, distance) if swap needed

            for dup_idx, dup_row, distance in nearby_duplicates:
                dup_score = _calculate_primary_score(dup_row)
                dup_row_id = int(dup_row['row_id'])
                dup_has_coord = pd.notna(dup_row.get('coord_text')) and dup_row.get('coord_text')
                print(f"  Duplicate row_id={dup_row_id}: score={dup_score}, has_coord={dup_has_coord}")

                if dup_score > best_primary_score:
                    best_primary_score = dup_score
                    best_primary_idx = dup_idx
                    best_primary_row_id = dup_row_id
                    best_primary_dup_info = (dup_idx, dup_row, distance)
                    print(f"    -> Better candidate for primary!")

            # Check if we need to swap primary
            swap_primary = (best_primary_dup_info is not None)

            if swap_primary:
                # =====================================================================
                # STEP 2A: SWAP PRIMARY - Duplicate has better data
                # =====================================================================
                dup_idx, dup_row, distance = best_primary_dup_info
                dup_row_id = int(dup_row['row_id'])
                print(f"\n*** PRIMARY SWAP: row_id={dup_row_id} (score={best_primary_score}) becomes primary instead of row_id={row_id} (score={current_score})")

                # 1. Update duplicate to use the new name (it becomes the primary)
                self.df_all.loc[dup_idx, 'anchor_text'] = new_signal_name
                print(f"  Updated duplicate's anchor_text to '{new_signal_name}'")

                # 2. Copy Fahrtrichtung from current if current has better source (GKS > track)
                SOURCE_PRIORITY = {
                    'gks': 4, 'gks_relaxed': 3, 'gks_nearest': 2, 'gks_confirmed': 2,
                    'track': 1, 'merged': 0, 'none': 0, '': 0,
                }
                dup_fahrt = dup_row.get('fahrtrichtung')
                dup_source = dup_row.get('_fahrtrichtung_source', 'none')
                current_fahrt = current_row.get('fahrtrichtung')
                current_source = current_row.get('_fahrtrichtung_source', 'none')
                if pd.isna(dup_source): dup_source = 'none'
                if pd.isna(current_source): current_source = 'none'

                dup_priority = SOURCE_PRIORITY.get(str(dup_source), 0)
                current_priority = SOURCE_PRIORITY.get(str(current_source), 0)

                if current_fahrt and (not dup_fahrt or current_priority > dup_priority):
                    self.df_all.loc[dup_idx, 'fahrtrichtung'] = current_fahrt
                    self.df_all.loc[dup_idx, '_fahrtrichtung_source'] = current_source
                    print(f"  Copied Fahrtrichtung '{current_fahrt}' (source: {current_source}) from current to new primary")

                # 3. Store current row's position in _signal_positions of new primary
                signal_positions = self.df_all.loc[dup_idx, '_signal_positions'] if '_signal_positions' in self.df_all.columns else None
                if signal_positions is None or (isinstance(signal_positions, float) and pd.isna(signal_positions)):
                    signal_positions = {}
                position_key = f"merged_{row_id}"
                signal_positions[position_key] = {
                    'ax1': current_row.get('ax1'), 'ay1': current_row.get('ay1'),
                    'ax2': current_row.get('ax2'), 'ay2': current_row.get('ay2'),
                    'row_id': row_id
                }
                self.df_all.at[dup_idx, '_signal_positions'] = signal_positions
                print(f"  Stored current row's position in new primary's _signal_positions")

                # 4. Hide current row (the one being renamed, which has no coordinate)
                self.df_all.loc[idx, '_hidden'] = True
                print(f"  Hidden current row_id={row_id}")

                # 5. Remove current row from tree widget
                current_tree_item = self.row_id_to_tree_item.get(row_id)
                if current_tree_item:
                    parent = current_tree_item.parent()
                    if parent:
                        parent.removeChild(current_tree_item)
                    else:
                        index_in_tree = self.tree.indexOfTopLevelItem(current_tree_item)
                        if index_in_tree >= 0:
                            self.tree.takeTopLevelItem(index_in_tree)
                    del self.row_id_to_tree_item[row_id]
                    print(f"  Removed current row from tree")

                # 6. Remove current row from graphics
                if row_id in self.current_row_items:
                    graphics_items = self.current_row_items.pop(row_id, [])
                    for item in graphics_items:
                        if item.scene():
                            item.scene().removeItem(item)
                    print(f"  Removed {len(graphics_items)} graphics items from current row")

                # 7. Update tree widget for new primary (duplicate)
                dup_tree_item = self.row_id_to_tree_item.get(dup_row_id)
                if dup_tree_item:
                    self.tree.blockSignals(True)
                    dup_tree_item.setText(0, new_signal_name)  # Update name column
                    self.tree.blockSignals(False)
                    print(f"  Updated new primary's tree item name")
                    # Update tree_item reference for Fahrtrichtung update later
                    tree_item = dup_tree_item

                # 8. Update idx and row_id for Fahrtrichtung recalculation
                idx = dup_idx
                row_id = dup_row_id

                # 9. Update page_dfs for both rows
                df_page = self.page_dfs.get(page)
                if df_page is not None:
                    # Update new primary in page_dfs
                    dup_page_idx_list = df_page.index[df_page['row_id'] == dup_row_id].tolist()
                    if dup_page_idx_list:
                        dup_page_idx = dup_page_idx_list[0]
                        df_page.loc[dup_page_idx, 'anchor_text'] = new_signal_name
                        if current_fahrt and (not dup_fahrt or current_priority > dup_priority):
                            df_page.loc[dup_page_idx, 'fahrtrichtung'] = current_fahrt
                            df_page.loc[dup_page_idx, '_fahrtrichtung_source'] = current_source

                    # Hide old current in page_dfs
                    old_page_idx_list = df_page.index[df_page['row_id'] == current_row['row_id']].tolist()
                    if old_page_idx_list:
                        df_page.loc[old_page_idx_list[0], '_hidden'] = True

                # 10. Handle any OTHER nearby duplicates (besides the one that became primary)
                merged_row_ids = []
                for other_dup_idx, other_dup_row, other_distance in nearby_duplicates:
                    other_dup_row_id = int(other_dup_row['row_id'])
                    if other_dup_row_id == dup_row_id:
                        continue  # Skip the one that became primary

                    print(f"\nMerging other duplicate row_id={other_dup_row_id} into new primary:")

                    # Store position
                    position_key = f"merged_{other_dup_row_id}"
                    signal_positions[position_key] = {
                        'ax1': other_dup_row.get('ax1'), 'ay1': other_dup_row.get('ay1'),
                        'ax2': other_dup_row.get('ax2'), 'ay2': other_dup_row.get('ay2'),
                        'row_id': other_dup_row_id
                    }
                    self.df_all.at[idx, '_signal_positions'] = signal_positions

                    # Hide
                    self.df_all.loc[other_dup_idx, '_hidden'] = True
                    merged_row_ids.append(other_dup_row_id)

                    # Remove from tree
                    other_tree_item = self.row_id_to_tree_item.get(other_dup_row_id)
                    if other_tree_item:
                        parent = other_tree_item.parent()
                        if parent:
                            parent.removeChild(other_tree_item)
                        else:
                            index_in_tree = self.tree.indexOfTopLevelItem(other_tree_item)
                            if index_in_tree >= 0:
                                self.tree.takeTopLevelItem(index_in_tree)
                        del self.row_id_to_tree_item[other_dup_row_id]

                    # Remove from graphics
                    if other_dup_row_id in self.current_row_items:
                        graphics_items = self.current_row_items.pop(other_dup_row_id, [])
                        for item in graphics_items:
                            if item.scene():
                                item.scene().removeItem(item)

                    print(f"  Hidden and removed other duplicate row_id={other_dup_row_id}")

            else:
                # =====================================================================
                # STEP 2B: Normal merge - Current row stays as primary
                # =====================================================================
                print(f"\nKeeping row_id={row_id} as primary (highest score={current_score})")
                merged_row_ids = []

                for dup_idx, dup_row, distance in nearby_duplicates:
                    dup_row_id = int(dup_row['row_id'])  # Ensure Python int, not numpy int64
                    print(f"\nMerging duplicate row_id={dup_row_id} (distance={distance:.0f}px):")

                    # Get CURRENT values from df_all (not stale current_row)
                    current_coord_text = self.df_all.loc[idx, 'coord_text'] if 'coord_text' in self.df_all.columns else None
                    current_fahrt = self.df_all.loc[idx, 'fahrtrichtung'] if 'fahrtrichtung' in self.df_all.columns else None

                    # Copy coordinate if current doesn't have one
                    if pd.isna(current_coord_text) or not current_coord_text:
                        if pd.notna(dup_row.get('coord_text')) and dup_row.get('coord_text'):
                            self.df_all.loc[idx, 'coord_text'] = dup_row['coord_text']
                            self.df_all.loc[idx, 'coord_value'] = dup_row.get('coord_value')
                            self.df_all.loc[idx, 'gi_gl'] = dup_row.get('gi_gl')
                            self.df_all.loc[idx, 'link_coord_row_id'] = dup_row.get('link_coord_row_id')
                            print(f"  Copied coordinate: '{dup_row['coord_text']}'")

                            # Update tree item column 1 (coord_text)
                            if tree_item:
                                self.tree.blockSignals(True)
                                tree_item.setText(1, str(dup_row['coord_text']))
                                self.tree.blockSignals(False)

                    # Copy Fahrtrichtung if current doesn't have one (prefer GKS source)
                    if pd.isna(current_fahrt) or not current_fahrt:
                        if pd.notna(dup_row.get('fahrtrichtung')) and dup_row.get('fahrtrichtung'):
                            self.df_all.loc[idx, 'fahrtrichtung'] = dup_row['fahrtrichtung']
                            self.df_all.loc[idx, '_fahrtrichtung_source'] = dup_row.get('_fahrtrichtung_source', 'merged')
                            print(f"  Copied Fahrtrichtung: '{dup_row['fahrtrichtung']}'")

                    # Store duplicate position in _signal_positions
                    signal_positions = self.df_all.loc[idx, '_signal_positions'] if '_signal_positions' in self.df_all.columns else None
                    if signal_positions is None or (isinstance(signal_positions, float) and pd.isna(signal_positions)):
                        signal_positions = {}

                    position_key = f"merged_{dup_row_id}"
                    signal_positions[position_key] = {
                        'ax1': dup_row.get('ax1'),
                        'ay1': dup_row.get('ay1'),
                        'ax2': dup_row.get('ax2'),
                        'ay2': dup_row.get('ay2'),
                        'row_id': dup_row_id
                    }
                    self.df_all.at[idx, '_signal_positions'] = signal_positions  # Use .at for dict values
                    print(f"  Stored position: {position_key}")

                    # Hide the duplicate row
                    self.df_all.loc[dup_idx, '_hidden'] = True
                    print(f"  Hidden duplicate row_id={dup_row_id}")
                    merged_row_ids.append(dup_row_id)

                    # Remove duplicate from tree widget
                    dup_tree_item = self.row_id_to_tree_item.get(dup_row_id)
                    if dup_tree_item:
                        parent = dup_tree_item.parent()
                        if parent:
                            parent.removeChild(dup_tree_item)
                        else:
                            index = self.tree.indexOfTopLevelItem(dup_tree_item)
                            if index >= 0:
                                self.tree.takeTopLevelItem(index)
                        del self.row_id_to_tree_item[dup_row_id]
                        print(f"  Removed from tree")

                    # Remove duplicate from graphics scene
                    if dup_row_id in self.current_row_items:
                        graphics_items = self.current_row_items.pop(dup_row_id, [])
                        for item in graphics_items:
                            if item.scene():
                                item.scene().removeItem(item)
                        print(f"  Removed {len(graphics_items)} graphics items")

                # Update page_dfs as well (inside else block, after for loop)
                df_page = self.page_dfs.get(page)
                if df_page is not None:
                    # Update current row in page_dfs
                    page_idx_list = df_page.index[df_page['row_id'] == row_id].tolist()
                    if page_idx_list:
                        page_idx = page_idx_list[0]
                        # Copy updated values from df_all
                        # Use .at for complex objects (dicts), .loc for simple scalar values
                        for col in ['coord_text', 'coord_value', 'gi_gl', 'link_coord_row_id',
                                   'fahrtrichtung', '_fahrtrichtung_source']:
                            if col in self.df_all.columns:
                                value = self.df_all.loc[idx, col]
                                if col not in df_page.columns:
                                    df_page[col] = None
                                df_page.loc[page_idx, col] = value
                        # Handle _signal_positions separately (dict value needs .at)
                        if '_signal_positions' in self.df_all.columns:
                            if '_signal_positions' not in df_page.columns:
                                df_page['_signal_positions'] = None
                            df_page.at[page_idx, '_signal_positions'] = self.df_all.at[idx, '_signal_positions']

                    # Hide merged duplicates in page_dfs
                    for merged_row_id in merged_row_ids:
                        dup_page_idx_list = df_page.index[df_page['row_id'] == merged_row_id].tolist()
                        if dup_page_idx_list:
                            df_page.loc[dup_page_idx_list[0], '_hidden'] = True

        # =====================================================================
        # STEP 3: Recalculate Fahrtrichtung
        # =====================================================================
        # Reload current row after merge updates
        current_row = self.df_all.loc[idx]

        new_fahrt = self._recalculate_fahrtrichtung_for_signal(row_id, new_signal_name)

        # Update Fahrtrichtung in dataframes
        self.df_all.loc[idx, 'fahrtrichtung'] = new_fahrt

        df_page = self.page_dfs.get(page)
        if df_page is not None:
            page_idx_list = df_page.index[df_page['row_id'] == row_id].tolist()
            if page_idx_list:
                df_page.loc[page_idx_list[0], 'fahrtrichtung'] = new_fahrt

        # Update tree widget column 2 (Fahrtrichtung)
        fahrt_display = str(new_fahrt) if new_fahrt else ""
        if tree_item:
            self.tree.blockSignals(True)
            tree_item.setText(2, fahrt_display)
            self.tree.blockSignals(False)
        print(f"Updated Fahrtrichtung in tree: '{fahrt_display}'")

        print(f"{'='*60}\n")

    def on_class_selector_changed(self, class_name: str):
        """Handle class selector change"""
        self._active_class_for_threshold_setting = class_name
        
        self._apply_all_filters()
        if self.current_page in self.page_base_pix:
            self._create_items_for_page(self.current_page)
        
        self.clear_hover_highlight()
    
    def get_class_for_row_id(self, row_id: int) -> Optional[str]:
        """Get class for row ID"""
        if self.df_all is None:
            return None
        row_list = self.df_all[self.df_all['row_id'] == row_id]
        if not row_list.empty:
            return row_list.iloc[0].get('cls')
        return None
    
    def _reconstruct_det_from_row(self, row: pd.Series) -> dict:
        """Rebuild detection dict from row"""
        if row.get("cls") == "coordinate":
            x1, y1, x2, y2 = row.get("cx1"), row.get("cy1"), row.get("cx2"), row.get("cy2")
        else:
            x1, y1, x2, y2 = row.get("ax1"), row.get("ay1"), row.get("ax2"), row.get("ay2")
        
        return {
            "cls": row.get("cls"),
            "name": row.get("cls"),
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "angle": row.get("angle"),
            "angle_raw": row.get("angle_raw", row.get("angle")),
            "obb_cx": row.get("obb_cx"),
            "obb_cy": row.get("obb_cy"),
            "obb_w": row.get("obb_w"),
            "obb_h": row.get("obb_h"),
            "poly": np.array(row.get("poly")) if isinstance(row.get("poly"), (list, tuple)) else None,
        }
    
    def on_rerun_ocr(self, row_id: int, ocr_type: str):
        """Re-run OCR on detection"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            if self.current_page_bgr_array is None:
                raise Exception("BGR array not found")
            
            row_list = self.df_all[self.df_all['row_id'] == row_id]
            if row_list.empty:
                raise Exception(f"Row {row_id} not found")
            
            row = row_list.iloc[0]
            det = self._reconstruct_det_from_row(row)
            cls = det.get("cls")
            
            new_text = ""
            is_coord = False
            
            if cls == "coordinate":
                is_coord = True
                if ocr_type == 'horizontal':
                    new_text = ocr_coordinate_horizontal(det, self.current_page_bgr_array, "paddleocr")
                else:
                    new_text = ocr_coordinate_angular(det, self.current_page_bgr_array, "paddleocr")
            elif cls == "signal":
                new_text = ocr_signal_name(det, self.current_page_bgr_array, "paddleocr")
            elif cls in {"gks_gesteuert", "gks_festkodiert"}:
                if ocr_type == 'horizontal':
                    new_text = ocr_numeric_cardinal_box(det, self.current_page_bgr_array)
                else:
                    new_text = ocr_numeric_tilted_box(det, self.current_page_bgr_array)
            else:
                new_text = ocr_generic_name(det, self.current_page_bgr_array, "paddleocr",
                                           allow_numeric=(cls in NUMERIC_OK), cls_name=cls)
            
            item = self.row_id_to_tree_item.get(row_id)
            if item:
                col_to_update = 0
                if is_coord and cls != 'coordinate':
                    col_to_update = 1
                item.setText(col_to_update, new_text)
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Re-OCR Error", str(e))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def on_bbox_resized(self, row_id: int, x: float, y: float, w: float, h: float,
                       is_rotated: bool = False, angle: float = 0.0, poly_points: list = None):
        """
        Called when user resizes a bbox - updates coordinates and runs OCR automatically.

        Args:
            row_id: Row ID of the detection
            x, y, w, h: New bounding box coordinates
            is_rotated: Whether this is a rotated bbox
            angle: Rotation angle (if rotated)
            poly_points: Actual polygon points [(x1,y1), (x2,y2), (x3,y3), (x4,y4)] for rotated bboxes
        """
        print("=" * 80)
        print(" DEBUG: on_bbox_resized() FUNCTION WAS CALLED - YOU SHOULD SEE THIS!")
        print("=" * 80)

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        try:
            print(f" Bbox resized for row_id {row_id}: ({x:.1f}, {y:.1f}, {w:.1f}, {h:.1f})")
            if poly_points:
                print(f"Polygon points: {poly_points}")

            # Find the row in df_all
            row_mask = self.df_all['row_id'] == row_id
            if not row_mask.any():
                raise Exception(f"Row {row_id} not found")

            row_idx = self.df_all[row_mask].index[0]
            row = self.df_all.loc[row_idx]
            cls = row.get('cls')
            page = int(row.get('page', self.current_page))

            # Capture old signal name for merge detection (handle NaN properly)
            if cls == 'signal':
                old_anchor = row.get('anchor_text')
                old_signal_name = str(old_anchor).strip() if pd.notna(old_anchor) else ''
            else:
                old_signal_name = ''

            print(f" Row data: cls='{cls}', page={page}, row_id={row_id}")
            print(f" Row columns: {list(row.index)}")
            if 'link_coord_row_id' in row.index:
                print(f" Row link_coord_row_id value: {row.get('link_coord_row_id')}")

            #  UNDO/REDO: Collect all affected row IDs BEFORE making changes
            affected_row_ids = [row_id]

            # If this is a coordinate, also include all linked anchors
            if cls == 'coordinate' and 'link_coord_row_id' in self.df_all.columns:
                linked_anchors = self.df_all[self.df_all['link_coord_row_id'] == row_id]
                if not linked_anchors.empty:
                    affected_row_ids.extend(linked_anchors['row_id'].tolist())
                    print(f" Found {len(linked_anchors)} linked anchors that will be affected")

            # Save state for undo/redo
            self._save_state("Bbox geändert", affected_row_ids)
            print(f" Saved state for undo/redo ({len(affected_row_ids)} rows affected)")

            # Update coordinates based on class
            x2, y2 = x + w, y + h
            if cls == 'coordinate':
                self.df_all.loc[row_idx, 'cx1'] = x
                self.df_all.loc[row_idx, 'cy1'] = y
                self.df_all.loc[row_idx, 'cx2'] = x2
                self.df_all.loc[row_idx, 'cy2'] = y2
            else:
                self.df_all.loc[row_idx, 'ax1'] = x
                self.df_all.loc[row_idx, 'ay1'] = y
                self.df_all.loc[row_idx, 'ax2'] = x2
                self.df_all.loc[row_idx, 'ay2'] = y2

            # Update page_dfs
            if page in self.page_dfs:
                page_mask = self.page_dfs[page]['row_id'] == row_id
                if page_mask.any():
                    page_idx = self.page_dfs[page][page_mask].index[0]
                    if cls == 'coordinate':
                        self.page_dfs[page].loc[page_idx, 'cx1'] = x
                        self.page_dfs[page].loc[page_idx, 'cy1'] = y
                        self.page_dfs[page].loc[page_idx, 'cx2'] = x2
                        self.page_dfs[page].loc[page_idx, 'cy2'] = y2
                    else:
                        self.page_dfs[page].loc[page_idx, 'ax1'] = x
                        self.page_dfs[page].loc[page_idx, 'ay1'] = y
                        self.page_dfs[page].loc[page_idx, 'ax2'] = x2
                        self.page_dfs[page].loc[page_idx, 'ay2'] = y2

            # Get BGR array for current page
            bgr_array = self.page_bgr_arrays.get(page)
            if bgr_array is None:
                raise Exception(f"BGR array not found for page {page}")

            # Reconstruct detection dict using the standard method (includes all fields)
            # First, get the updated row after coordinate changes
            row = self.df_all.loc[row_idx]
            det = self._reconstruct_det_from_row(row)

            # Update coordinates in det with new values
            det["x1"] = x
            det["y1"] = y
            det["x2"] = x2
            det["y2"] = y2

            # Update angle if provided
            if is_rotated and angle != 0.0:
                det["angle"] = angle
                det["angle_raw"] = angle

            # Update polygon points if provided (critical for rotated bbox OCR!)
            if poly_points:
                # Convert to numpy array format expected by OCR functions
                poly_array = np.array(poly_points, dtype=np.float32).flatten()  # [x1, y1, x2, y2, x3, y3, x4, y4]
                det["poly"] = poly_array
                print(f"Updated poly field with new polygon points")

                #  CRITICAL: Save the new poly back to dataframe for undo/redo!
                self.df_all.at[row_idx, 'poly'] = poly_array
                if page in self.page_dfs and page_mask.any():
                    self.page_dfs[page].at[page_idx, 'poly'] = poly_array
                print(f"Saved new poly to dataframe for undo/redo")

                # Also update obb_* fields for consistency
                det["obb_cx"] = (x + x2) / 2
                det["obb_cy"] = (y + y2) / 2
                det["obb_w"] = w
                det["obb_h"] = h

            # Determine OCR mode: cardinal (horizontal/vertical) vs angular (tilted)
            # Use normalized angle with standard helpers from helpers.py
            from utils.helpers import _is_angular, _dist_to_cardinal

            normalized_angle = det.get('angle', 0.0)  # Normalized angle (cardinals → ~0°)
            raw_angle = det.get('angle_raw', normalized_angle)  # Raw angle from YOLO

            # Use standard helper: checks if > ANGLE_TOL (~12°) from cardinal directions
            # Cardinal (horizontal/vertical): use paddleocr_recognize
            # Angular (tilted): use manual_angular_ocr
            ocr_mode = 'angular' if _is_angular(normalized_angle) else 'horizontal'

            dist_cardinal = _dist_to_cardinal(raw_angle)
            print(f" Angle analysis: raw={raw_angle:.2f}° norm={normalized_angle:.2f}° dist_to_cardinal={dist_cardinal:.2f}°")
            print(f"Detected OCR mode: {ocr_mode}")

            # Use class-specific OCR functions (same as Re-OCR feature)
            # These functions handle their own cropping and preprocessing
            from core.ocr_engine import (
                ocr_coordinate_horizontal, ocr_coordinate_angular,
                ocr_signal_name, ocr_numeric_cardinal_box, ocr_numeric_tilted_box,
                ocr_weichen_block, ocr_generic_name
            )

            new_text = ""

            # Use the same logic as on_rerun_ocr for consistency
            if cls == "coordinate":
                if ocr_mode == 'horizontal':
                    new_text = ocr_coordinate_horizontal(det, bgr_array, "paddleocr")
                    print(f" Coordinate horizontal OCR: '{new_text}'")
                else:
                    new_text = ocr_coordinate_angular(det, bgr_array, "paddleocr")
                    print(f" Coordinate angular OCR: '{new_text}'")
            elif cls == "signal":
                new_text = ocr_signal_name(det, bgr_array, "paddleocr")
                print(f" Signal OCR: '{new_text}'")
            elif cls in {"gks_gesteuert", "gks_festkodiert"}:
                if ocr_mode == 'horizontal':
                    new_text = ocr_numeric_cardinal_box(det, bgr_array)
                    print(f" GKS cardinal OCR: '{new_text}'")
                else:
                    new_text = ocr_numeric_tilted_box(det, bgr_array)
                    print(f" GKS tilted OCR: '{new_text}'")
            elif cls == "weichen_block":
                #  Use specialized multi-line OCR for weichen_block
                new_text = ocr_weichen_block(det, bgr_array)
                print(f" Weichen block OCR (multi-line): '{new_text}'")
            #  NEW: Handle template-matched symbols
            elif row.get('is_new_symbol', False):
                print(f" Template symbol '{cls}' bbox resized - re-extracting text")

                # Get symbol definition to know text_position
                try:
                    from core.symbol_detector import NewSymbolDetector
                    detector = NewSymbolDetector()
                    symbol_name = row.get('name', '')

                    if symbol_name in detector.symbols:
                        symbol_def = detector.symbols[symbol_name]

                        if symbol_def.has_text:
                            # Compute NEW text region based on RESIZED symbol bbox
                            from core.pipeline_integration import compute_text_region

                            text_bbox = compute_text_region(
                                det,  # Uses updated x1, y1, x2, y2
                                symbol_def.text_position,
                                symbol_def.text_region_offset
                            )

                            # Extract text from computed region
                            x1_text, y1_text, x2_text, y2_text = text_bbox
                            text_crop = bgr_array[y1_text:y2_text, x1_text:x2_text]

                            # Determine if text is horizontal or angular
                            # Template symbols usually have horizontal text
                            text_angle = det.get('angle', 0.0)
                            if _is_angular(text_angle):
                                # Use angular OCR for tilted text
                                from core.ocr_engine import ocr_generic_name
                                new_text = ocr_generic_name({'x1': x1_text, 'y1': y1_text,
                                                             'x2': x2_text, 'y2': y2_text,
                                                             'angle': text_angle},
                                                           bgr_array, "paddleocr")
                            else:
                                # Use horizontal OCR (most common for template symbols)
                                from core.ocr_engine import paddleocr_recognize
                                new_text, _ = paddleocr_recognize(text_crop)

                            print(f" Template text OCR: '{new_text}'")
                        else:
                            new_text = ""  # Symbol doesn't need text
                            print(f" Template symbol has no text requirement")
                    else:
                        print(f"Symbol definition '{symbol_name}' not found")
                        new_text = ""

                except Exception as e:
                    print(f"Error during template OCR: {e}")
                    import traceback
                    traceback.print_exc()
                    new_text = ""
            else:
                # NUMERIC_OK already imported at top from core.ocr_engine
                new_text = ocr_generic_name(det, bgr_array, "paddleocr",
                                           allow_numeric=(cls in NUMERIC_OK), cls_name=cls)
                print(f" Generic OCR ({cls}): '{new_text}'")

            print(f"Final OCR result: '{new_text}'")

            # Update text in dataframe
            print(f" Updating dataframe for cls='{cls}', row_id={row_id}")

            if cls == 'coordinate':
                print(f"This is a COORDINATE - updating coord_text and checking for linked anchors")
                self.df_all.loc[row_idx, 'coord_text'] = new_text
                if page in self.page_dfs and page_mask.any():
                    self.page_dfs[page].loc[page_idx, 'coord_text'] = new_text

                # Update all linked anchors with the new coordinate text
                print(f"Checking for link_coord_row_id column...")
                print(f"Columns in df_all: {list(self.df_all.columns)}")

                if 'link_coord_row_id' in self.df_all.columns:
                    print(f"link_coord_row_id column EXISTS")

                    # Show all link_coord_row_id values for debugging
                    all_links = self.df_all[self.df_all['link_coord_row_id'].notna()][['row_id', 'cls', 'link_coord_row_id', 'anchor_text', 'coord_text']]
                    if not all_links.empty:
                        print(f"All linked rows in dataframe (total {len(all_links)}):")
                        for idx in all_links.index:
                            link_id = self.df_all.loc[idx, 'link_coord_row_id']
                            anchor_row_id = self.df_all.loc[idx, 'row_id']
                            anchor_cls = self.df_all.loc[idx, 'cls']
                            anchor_coord_text = self.df_all.loc[idx, 'coord_text']
                            print(f"- Anchor row_id={anchor_row_id} (cls={anchor_cls}) -> links to coord row_id={link_id}, current coord_text='{anchor_coord_text}'")
                    else:
                        print(f"NO linked rows found in entire dataframe!")

                    print(f"Searching for anchors with link_coord_row_id == {row_id}")
                    linked_anchors = self.df_all[self.df_all['link_coord_row_id'] == row_id]
                    print(f"Query returned {len(linked_anchors)} rows")

                    if len(linked_anchors) == 0:
                        print(f"NO LINKED ANCHORS FOUND for coordinate row_id={row_id}")
                        print(f" This coordinate might not be linked to any anchors yet")
                    if len(linked_anchors) > 0:
                        print(f" Linked anchor details:")
                        for idx in linked_anchors.index:
                            print(f"- row_id={self.df_all.loc[idx, 'row_id']}, cls={self.df_all.loc[idx, 'cls']}, anchor_text={self.df_all.loc[idx, 'anchor_text']}")
                    if not linked_anchors.empty:
                        print(f" Found {len(linked_anchors)} linked anchors for coordinate row_id={row_id}")
                        for linked_idx in linked_anchors.index:
                            linked_row_id = self.df_all.loc[linked_idx, 'row_id']
                            linked_page = int(self.df_all.loc[linked_idx, 'page'])
                            linked_cls = self.df_all.loc[linked_idx, 'cls']

                            print(f"→ Updating linked {linked_cls} row_id={linked_row_id} (page {linked_page})")

                            # Update dataframe
                            self.df_all.loc[linked_idx, 'coord_text'] = new_text

                            # Update in page_dfs
                            if linked_page in self.page_dfs:
                                page_row_mask = self.page_dfs[linked_page]['row_id'] == linked_row_id
                                if page_row_mask.any():
                                    page_row_idx = self.page_dfs[linked_page][page_row_mask].index[0]
                                    self.page_dfs[linked_page].loc[page_row_idx, 'coord_text'] = new_text
                                    print(f" Updated page_dfs for page {linked_page}")

                            # Update tree item
                            linked_tree_item = self.row_id_to_tree_item.get(linked_row_id)
                            if linked_tree_item:
                                # Debug: show current values before update
                                current_col0 = linked_tree_item.text(0)
                                current_col1 = linked_tree_item.text(1)
                                print(f" BEFORE tree update:")
                                print(f"Column 0 (anchor_text): '{current_col0}'")
                                print(f"Column 1 (coord_text): '{current_col1}'")

                                self.tree.blockSignals(True)
                                linked_tree_item.setText(1, new_text)  # coord_text in column 1
                                self.tree.blockSignals(False)

                                # Debug: verify update
                                after_col1 = linked_tree_item.text(1)
                                print(f" AFTER tree update:")
                                print(f"Column 1 (coord_text): '{after_col1}'")
                                print(f" Updated tree item column 1: '{current_col1}' → '{new_text}'")
                            else:
                                print(f"No tree item found for linked_row_id={linked_row_id}")
                                print(f"Available tree items: {list(self.row_id_to_tree_item.keys())[:10]}...")

                            # Update graphics label (only if on current page)
                            if linked_page == self.current_page:
                                linked_items = self.current_row_items.get(linked_row_id)
                                if linked_items:
                                    # Rebuild label with full format for linked anchor
                                    linked_row = self.df_all.loc[linked_idx]
                                    linked_label = f"{linked_row['cls']} {linked_row.get('conf', '')}"
                                    if pd.notna(linked_row.get('anchor_text')) and linked_row['anchor_text']:
                                        linked_label += f" | {linked_row['anchor_text']}"
                                    if pd.notna(linked_row.get('coord_text')) and linked_row['coord_text']:
                                        linked_label += f" | {linked_row['coord_text']}"
                                    if pd.notna(linked_row.get('angle')):
                                        try:
                                            linked_label += f" θ={float(linked_row['angle']):.1f}°"
                                        except Exception:
                                            pass

                                    for linked_it in linked_items:
                                        if isinstance(linked_it, QtWidgets.QGraphicsSimpleTextItem):
                                            linked_it.setText(linked_label)
                                            print(f" Updated graphics label: '{linked_label}'")
                                            break

                                    #  Update linked anchor spec for persistence
                                    linked_specs = self.all_page_row_specs.get(linked_page, {})
                                    if linked_row_id in linked_specs:
                                        linked_specs[linked_row_id]['label'] = linked_label
                                        print(f" Updated linked anchor spec label")
                                else:
                                    print(f"Linked anchor not found in current_row_items")
                            else:
                                print(f"Linked anchor on different page ({linked_page} vs {self.current_page}), graphics will update when page is viewed")
                    else:
                        print(f"No linked anchors found for this coordinate")
                else:
                    print(f"No 'link_coord_row_id' column in dataframe")

            else:
                # Non-coordinate classes: update anchor_text

                #  Special handling for weichen_block: parse FIRST, then set anchor_text to block ID only
                if cls == 'weichen_block':
                    print(f"DEBUG: Raw OCR text for weichen_block:")
                    print(f"Value: '{new_text}'")
                    print(f"Repr: {repr(new_text)}")
                    print(f"Length: {len(new_text)} chars")
                    print(f"Line count: {len(new_text.split(chr(10)))} lines (using \\n)")
                    print(f"Lines: {new_text.split(chr(10))}")

                    from core.image_processing import parse_weichen_block
                    parsed = parse_weichen_block(new_text)
                    weichen_block_id = parsed.get('id', '')
                    weichen_coords = parsed.get('coordinates', [])
                    coord_text_combined = " | ".join(weichen_coords) if weichen_coords else None

                    print(f" Parsed weichen_block:")
                    print(f"Block ID: '{weichen_block_id}'")
                    print(f"Coordinates: {weichen_coords}")
                    print(f"Combined coord_text: '{coord_text_combined}'")

                    #  Set anchor_text to ONLY the block ID (not full OCR text)
                    self.df_all.loc[row_idx, 'anchor_text'] = weichen_block_id
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].loc[page_idx, 'anchor_text'] = weichen_block_id

                    # Update coord_text in dataframes
                    self.df_all.loc[row_idx, 'coord_text'] = coord_text_combined
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].loc[page_idx, 'coord_text'] = coord_text_combined

                    # Update weichen_coordinates field (use .at for list values)
                    self.df_all.at[row_idx, 'weichen_coordinates'] = weichen_coords
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].at[page_idx, 'weichen_coordinates'] = weichen_coords
                #  NEW: Template symbols use 'text' field, not 'anchor_text'
                elif row.get('is_new_symbol', False):
                    print(f" Updating template symbol text field")
                    # Template symbols store text in 'text' field
                    text_field = 'text' if 'text' in self.df_all.columns else 'anchor_text'
                    self.df_all.loc[row_idx, text_field] = new_text
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].loc[page_idx, text_field] = new_text
                    print(f" Updated {text_field} to '{new_text}'")
                else:
                    # Other non-coordinate classes: update anchor_text normally
                    self.df_all.loc[row_idx, 'anchor_text'] = new_text
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].loc[page_idx, 'anchor_text'] = new_text

            # SIGNAL MERGE + FAHRTRICHTUNG: Trigger when signal name changes via bbox resize OCR
            if cls == 'signal':
                new_signal_name = str(new_text).strip()
                if new_signal_name and new_signal_name.upper() != old_signal_name.upper():
                    print(f"\n Signal name changed via bbox resize: '{old_signal_name}' → '{new_signal_name}'")
                    print(f" Triggering merge + Fahrtrichtung recalculation...")
                    self._merge_and_recalculate_fahrtrichtung(row_id, new_signal_name)

            # Update tree widget for this item
            item = self.row_id_to_tree_item.get(row_id)
            if item:
                self.tree.blockSignals(True)
                if cls == 'coordinate':
                    item.setText(0, new_text)  # coord_text goes in column 0 for coordinates
                elif cls == 'weichen_block':
                    # For weichen_block: column 0 = block ID, column 1 = coordinates
                    updated_anchor_text = self.df_all.loc[row_idx, 'anchor_text']
                    updated_coord_text = self.df_all.loc[row_idx, 'coord_text']
                    updated_anchor_text = updated_anchor_text if pd.notna(updated_anchor_text) else ''
                    updated_coord_text = updated_coord_text if pd.notna(updated_coord_text) else ''
                    item.setText(0, updated_anchor_text)  # Block ID in column 0
                    item.setText(1, updated_coord_text)   # Coordinates in column 1
                    print(f" Updated tree column 0 (anchor_text): '{updated_anchor_text}'")
                    print(f" Updated tree column 1 (coord_text): '{updated_coord_text}'")
                else:
                    item.setText(0, new_text)  # anchor_text goes in column 0 for other non-coordinates

                self.tree.blockSignals(False)

            # ISSUE 3 FIX: Fast update - only update this specific item's label, not entire page
            items = self.current_row_items.get(row_id)
            if items:
                # Get the updated row data to rebuild the label with full metadata
                updated_row = self.df_all.loc[row_idx]

                # Rebuild label with full format: {cls} {conf} | {anchor_text} | {coord_text} θ={angle}°
                label = f"{updated_row['cls']} {updated_row.get('conf', '')}"
                if pd.notna(updated_row.get('anchor_text')) and updated_row['anchor_text']:
                    label += f" | {updated_row['anchor_text']}"
                if pd.notna(updated_row.get('coord_text')) and updated_row['coord_text']:
                    label += f" | {updated_row['coord_text']}"
                if pd.notna(updated_row.get('angle')):
                    try:
                        label += f" θ={float(updated_row['angle']):.1f}°"
                    except Exception:
                        pass

                # Update the text label item with full format
                for it in items:
                    if isinstance(it, QtWidgets.QGraphicsSimpleTextItem):
                        it.setText(label)
                        print(f"Updated label to: '{label}'")
                        break

                #  Also update the spec so label persists on page re-render
                specs = self.all_page_row_specs.get(page, {})
                if row_id in specs:
                    specs[row_id]['label'] = label
                    print(f" Updated spec label for persistence")

            #  FIX: Deselect the graphics item to hide resize handles and return to normal appearance
            items = self.current_row_items.get(row_id)
            if items:
                for it in items:
                    # Deselect bbox items (ResizableBBoxItem or QGraphicsRectItem/QGraphicsPolygonItem)
                    # This triggers itemChange() which hides the resize handles
                    if hasattr(it, 'setSelected'):
                        it.setSelected(False)
                        print(f" Deselected graphics item for row_id {row_id}")

            self._set_status(f" Bbox aktualisiert & OCR ({ocr_mode}) durchgeführt: '{new_text}'")

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self,
                "Bbox Resize Error",
                f"Fehler beim Aktualisieren der Bbox:\n{str(e)}"
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def on_ocr_bbox_resized(self, row_id: int, x: float, y: float, w: float, h: float):
        """
        Called when user resizes an OCR region bbox - shows dialog and applies adjustment.

        Args:
            row_id: Row ID of the detection
            x, y, w, h: New OCR region bounding box coordinates
        """
        print("=" * 80)
        print(" OCR REGION RESIZED - Showing adjustment dialog")
        print("=" * 80)

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        try:
            print(f" OCR region resized for row_id {row_id}: ({x:.1f}, {y:.1f}, {w:.1f}, {h:.1f})")

            # Find the row in df_all
            row_mask = self.df_all['row_id'] == row_id
            if not row_mask.any():
                raise Exception(f"Row {row_id} not found")

            row_idx = self.df_all[row_mask].index[0]
            row = self.df_all.loc[row_idx]
            cls = row.get('cls')
            page = int(row.get('page', self.current_page))
            old_ocr_text = row.get('anchor_text', '')

            # Get old OCR region coordinates
            old_ocr_x1 = row.get('ocr_x1')
            old_ocr_y1 = row.get('ocr_y1')
            old_ocr_x2 = row.get('ocr_x2')
            old_ocr_y2 = row.get('ocr_y2')

            # Calculate adjustment delta - use EDGE-SPECIFIC deltas for rotation-aware adjustment
            x2, y2 = x + w, y + h

            # Calculate how much each edge moved (not offset + width_delta!)
            delta_x1 = int(x - old_ocr_x1) if pd.notna(old_ocr_x1) else 0
            delta_y1 = int(y - old_ocr_y1) if pd.notna(old_ocr_y1) else 0
            delta_x2 = int(x2 - old_ocr_x2) if pd.notna(old_ocr_x2) else 0
            delta_y2 = int(y2 - old_ocr_y2) if pd.notna(old_ocr_y2) else 0

            # Also compute old-style deltas for display/dialog
            offset_x = delta_x1  # Left/top edge movement
            offset_y = delta_y1
            width_delta = delta_x2 - delta_x1  # Difference between right and left edge movements
            height_delta = delta_y2 - delta_y1

            print(f" Row data: cls='{cls}', page={page}, row_id={row_id}")
            print(f" Edge deltas: x1={delta_x1:+d}, y1={delta_y1:+d}, x2={delta_x2:+d}, y2={delta_y2:+d}")
            print(f" Display: offset=({offset_x:+d}, {offset_y:+d}), size_delta=({width_delta:+d}, {height_delta:+d})")

            # Get BGR array for current page
            bgr_array = self.page_bgr_arrays.get(page)
            if bgr_array is None:
                raise Exception(f"BGR array not found for page {page}")

            # Run OCR on NEW region
            import cv2
            from PIL import Image
            from core.ocr_engine import _upscale_if_tiny

            crop_x1, crop_y1 = int(x), int(y)
            crop_x2, crop_y2 = int(x2), int(y2)

            # Validate crop bounds
            img_h, img_w = bgr_array.shape[:2]
            crop_x1 = max(0, min(crop_x1, img_w))
            crop_y1 = max(0, min(crop_y1, img_h))
            crop_x2 = max(crop_x1 + 10, min(crop_x2, img_w))
            crop_y2 = max(crop_y1 + 10, min(crop_y2, img_h))

            new_crop_bgr = bgr_array[crop_y1:crop_y2, crop_x1:crop_x2]
            new_crop_rgb = cv2.cvtColor(new_crop_bgr, cv2.COLOR_BGR2RGB)
            pil_new_crop = Image.fromarray(new_crop_rgb)
            pil_new_crop = _upscale_if_tiny(pil_new_crop, min_side=80, scale=2)

            # Run OCR on new region
            new_text, ocr_confidence = paddleocr_recognize(pil_new_crop)
            print(f"New OCR result: '{new_text}' (conf={ocr_confidence:.3f})")

            # Get old crop for preview (if available)
            old_crop_rgb = None
            if pd.notna(old_ocr_x1):
                old_cx1 = max(0, min(int(old_ocr_x1), img_w))
                old_cy1 = max(0, min(int(old_ocr_y1), img_h))
                old_cx2 = max(old_cx1 + 10, min(int(old_ocr_x2), img_w))
                old_cy2 = max(old_cy1 + 10, min(int(old_ocr_y2), img_h))
                old_crop_bgr = bgr_array[old_cy1:old_cy2, old_cx1:old_cx2]
                old_crop_rgb = cv2.cvtColor(old_crop_bgr, cv2.COLOR_BGR2RGB)

            # Count instances of this symbol class
            instance_count = (self.df_all['cls'] == cls).sum()

            QtWidgets.QApplication.restoreOverrideCursor()

            # Show adjustment dialog
            dialog = OCRAdjustmentDialog(
                self, cls, instance_count,
                old_ocr_text, new_text,
                offset_x, offset_y, width_delta, height_delta,
                old_crop_rgb, new_crop_rgb
            )

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

                apply_to_current, apply_to_all_in_plan, save_to_template = dialog.get_options()

                print(f" User choices: current={apply_to_current}, all_in_plan={apply_to_all_in_plan}, "
                      f"save_to_template={save_to_template}")

                # Determine which row_ids to update
                row_ids_to_update = [row_id]  # Always include current row

                if apply_to_all_in_plan:
                    # Find all instances of this symbol class
                    same_class_mask = self.df_all['cls'] == cls
                    row_ids_to_update = self.df_all[same_class_mask]['row_id'].tolist()
                    print(f"Applying to {len(row_ids_to_update)} instances of '{cls}'")

                # Save state for undo/redo
                print(f" Saving state before OCR adjustment:")
                print(f"Row {row_id}: ocr_x1={old_ocr_x1}, ocr_y1={old_ocr_y1}, ocr_x2={old_ocr_x2}, ocr_y2={old_ocr_y2}")
                self._save_state("OCR-Region geändert", row_ids_to_update)

                # Apply adjustment to selected rows (using edge-specific deltas)
                # Pass the current row_id and new absolute coordinates so we don't double-apply to it
                self._apply_ocr_adjustment_to_rows(
                    row_ids_to_update, delta_x1, delta_y1, delta_x2, delta_y2,
                    current_row_id=row_id, new_x=x, new_y=y, new_x2=x2, new_y2=y2
                )

                # Record adjustment for auto-learning
                self.ocr_adjustment_tracker.record_adjustment(
                    cls, offset_x, offset_y, width_delta, height_delta
                )

                # Save to template if requested
                if save_to_template:
                    # Need to calculate absolute offset from symbol center and final size
                    # Get the adjusted OCR region from the first row as reference
                    ref_row_mask = self.df_all['row_id'] == row_ids_to_update[0]
                    if ref_row_mask.any():
                        ref_row_idx = self.df_all[ref_row_mask].index[0]
                        ref_row = self.df_all.loc[ref_row_idx]

                        # Get symbol angle (for rotation-aware offset calculation)
                        sym_angle = ref_row.get('angle', 0.0)
                        if pd.isna(sym_angle):
                            sym_angle = 0.0

                        # Get symbol center
                        sym_x1 = ref_row.get('x1', 0)
                        sym_y1 = ref_row.get('y1', 0)
                        sym_x2 = ref_row.get('x2', 0)
                        sym_y2 = ref_row.get('y2', 0)
                        sym_cx = (sym_x1 + sym_x2) / 2
                        sym_cy = (sym_y1 + sym_y2) / 2

                        # Get NEW OCR region after adjustment
                        new_ocr_x1 = ref_row.get('ocr_x1')
                        new_ocr_y1 = ref_row.get('ocr_y1')
                        new_ocr_x2 = ref_row.get('ocr_x2')
                        new_ocr_y2 = ref_row.get('ocr_y2')

                        if pd.notna(new_ocr_x1):
                            # Calculate OCR region center
                            ocr_cx = (new_ocr_x1 + new_ocr_x2) / 2
                            ocr_cy = (new_ocr_y1 + new_ocr_y2) / 2

                            # Calculate offset from symbol center IN CURRENT ROTATION
                            current_dx = int(ocr_cx - sym_cx)
                            current_dy = int(ocr_cy - sym_cy)

                            # Calculate final width and height IN CURRENT ROTATION
                            current_width = int(new_ocr_x2 - new_ocr_x1)
                            current_height = int(new_ocr_y2 - new_ocr_y1)

                            # CRITICAL: Transform offset back to 0° reference frame
                            # The template stores offsets for 0° rotation, so we need to
                            # reverse the rotation that was applied to the detected symbol
                            from utils.rotation_utils import transform_offset_reverse

                            absolute_dx, absolute_dy, final_width, final_height = transform_offset_reverse(
                                current_dx, current_dy, current_width, current_height, sym_angle
                            )

                            print(f" Rotation transform: angle={sym_angle:.1f}°")
                            print(f"Current frame: dx={current_dx}, dy={current_dy}, w={current_width}, h={current_height}")
                            print(f"Template (0°): dx={absolute_dx}, dy={absolute_dy}, w={final_width}, h={final_height}")

                            print(f" Saving to template: dx={absolute_dx}, dy={absolute_dy}, "
                                  f"width={final_width}, height={final_height}")

                            self._save_ocr_adjustment_to_template(
                                cls, absolute_dx, absolute_dy, final_width, final_height
                            )
                        else:
                            print(f"Cannot save to template: No OCR region data")
                    else:
                        print(f"Cannot save to template: Reference row not found")

                # Check if we should show auto-learning suggestion
                # TODO: Auto-learning needs redesign to work with absolute offsets
                # Currently disabled until we can convert deltas to absolutes
                # if self.ocr_adjustment_tracker.should_show_suggestion(cls):
                #     self._show_auto_learning_suggestion(cls)

                self._set_status(f" OCR-Region aktualisiert für {len(row_ids_to_update)} Instanz(en)")
                print(f"OCR region resize complete!")

            else:
                print(f"User cancelled adjustment")
                # Revert the visual change (reload the page)
                self._refresh_page_graphics()

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self,
                "OCR Region Resize Error",
                f"Fehler beim Aktualisieren der OCR-Region:\n{str(e)}"
            )
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def on_manual_ocr_toggled(self, checked: bool, mode: str = 'horizontal'):
            """Toggle manual OCR mode"""
            if checked:
                if mode == 'horizontal' and self.btn_manual_ocr_angular.isChecked():
                    self.btn_manual_ocr_angular.setChecked(False)
                elif mode == 'angular' and self.btn_manual_ocr.isChecked():
                    self.btn_manual_ocr.setChecked(False)
                
                if self.current_page_bgr_array is None:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Kein BGR-Bild geladen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                item = self.tree.currentItem()
                col = self.tree.currentColumn()
                
                if not item or item.childCount() > 0:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte Zelle auswählen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                if col not in [0, 1]:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte Spalte 'Text/Nummer' oder 'Koordinatentext' auswählen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                self.draw_ocr_target_item = item
                self.draw_ocr_target_column = col
                self.draw_ocr_mode = mode
                
                self.is_drawing_mode = True
                is_rotated = (mode == 'angular')
                self.view.toggle_drawing_mode(True, rotated=is_rotated)

                # --- ADD THIS (logic for different messages) ---
                if mode == 'angular':
                    self._set_status(
                        " Manuelles OCR (Angular): 1. Zelle auswählen. 2. Klicken Sie Start- & Endpunkt der Text-Basislinie. 3. Klicken Sie ein drittes Mal, um die Höhe festzulegen."
                    )
                else:
                    self._set_status(
                        " Manuelles OCR (Horizontal): 1. Zelle in Tabelle auswählen. 2. Ziehen Sie ein horizontales Rechteck auf dem Bild."
                    )
                # --- END ADD ---

            else:
                # --- ADD THIS (for toggling off) ---
                self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                # --- END ADD ---

                self.is_drawing_mode = False
                self.view.toggle_drawing_mode(False)
                self.draw_ocr_target_item = None
                self.draw_ocr_target_column = None
                self.draw_ocr_mode = 'horizontal'
    
    def on_rect_drawn(self, rect: QtCore.QRectF):
        """Handle rectangle drawn for manual OCR"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        item_to_update = self.draw_ocr_target_item
        col_to_update = self.draw_ocr_target_column
        original_mode = self.draw_ocr_mode

        self.draw_ocr_target_item = None
        self.draw_ocr_target_column = None
        self.draw_ocr_mode = 'horizontal'

        try:
            if not item_to_update or col_to_update is None:
                raise Exception("No target element")
            
            row_id = item_to_update.data(0, QtCore.Qt.UserRole)
            
            cls = self.get_class_for_row_id(row_id)
            if cls is None:
                raise Exception("Class not found")
            
            x1 = int(rect.left())
            y1 = int(rect.top())
            x2 = int(rect.right())
            y2 = int(rect.bottom())
            
            if x2 <= x1 or y2 <= y1 or self.current_page_bgr_array is None:
                raise Exception("Invalid rectangle")
            
            h, w = self.current_page_bgr_array.shape[:2]
            box_w = x2 - x1
            box_h = y2 - y1
            box_min_side = min(box_w, box_h)
            
            if original_mode == 'angular':
                if box_min_side < 70:
                    pad = 18
                elif box_min_side < 100:
                    pad = 16
                else:
                    pad = 14
            else:
                pad = max(10, min(16, int(box_min_side * 0.15)))
            
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)
            
            crop_bgr = self.current_page_bgr_array[y1:y2, x1:x2]
            
            if original_mode == 'angular':
                new_text, conf = manual_angular_ocr(crop_bgr, cls)
            else:
                crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
                new_text, conf = paddleocr_recognize(crop_pil, cls_name=cls, whitelist=None)
            
            QtWidgets.QApplication.restoreOverrideCursor()
            
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("OCR Ergebnis")
            msg.setIcon(QtWidgets.QMessageBox.Question)
            msg.setText(f"OCR Ergebnis:\n\n'{new_text}'\n\nKonfidenz: {conf:.2f}\n\nÜbernehmen?")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            
            result = msg.exec_()
            
            if result == QtWidgets.QMessageBox.Yes:
                row_id = item_to_update.data(0, QtCore.Qt.UserRole)
        
                if row_id:
                    self._save_state("Manuelles OCR", [row_id])
                item_to_update.setText(col_to_update, new_text)
        
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Manual OCR Error", str(e))
        finally:
            self.btn_manual_ocr.setChecked(False)
            self.btn_manual_ocr_angular.setChecked(False)
            self.view.toggle_drawing_mode(False)
    
    def on_rotated_rect_drawn(self, rect: QtCore.QRectF, angle: float):
        """Handle rotated rectangle for angular OCR"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        item_to_update = self.draw_ocr_target_item
        col_to_update = self.draw_ocr_target_column
        
        self.draw_ocr_target_item = None
        self.draw_ocr_target_column = None
        self.draw_ocr_mode = 'horizontal'
        
        try:
            if not item_to_update or col_to_update is None:
                raise Exception("No target")
            
            row_id = item_to_update.data(0, QtCore.Qt.UserRole)
            cls = self.get_class_for_row_id(row_id)
            if cls is None:
                raise Exception("Class not found")
            
            h, w = self.current_page_bgr_array.shape[:2]
            
            center_x = rect.center().x()
            center_y = rect.center().y()
            width = int(rect.width())
            height = int(rect.height())
            
            if width < 10 or height < 10:
                raise Exception("Rectangle too small")
            
            MAX_DIM = 5000
            if width > MAX_DIM or height > MAX_DIM:
                raise Exception(f"Rectangle too large ({width}x{height})")
            
            box_min_side = min(width, height)
            if box_min_side < 70:
                pad = 30
            elif box_min_side < 100:
                pad = 25
            else:
                pad = 20
            
            width_pad = max(pad, int(width * 0.15))
            height_pad = max(pad, int(height * 0.25))
            
            expanded_width = width + 2 * width_pad
            expanded_height = height + 2 * height_pad
            
            angle_rad = math.radians(angle)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            
            half_w = expanded_width / 2
            half_h = expanded_height / 2
            
            corners = [
                (center_x + (-half_w * cos_a - -half_h * sin_a), 
                 center_y + (-half_w * sin_a + -half_h * cos_a)),
                (center_x + (half_w * cos_a - -half_h * sin_a), 
                 center_y + (half_w * sin_a + -half_h * cos_a)),
                (center_x + (half_w * cos_a - half_h * sin_a), 
                 center_y + (half_w * sin_a + half_h * cos_a)),
                (center_x + (-half_w * cos_a - half_h * sin_a), 
                 center_y + (-half_w * sin_a + half_h * cos_a)),
            ]
            
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            bbox_x1 = max(0, int(min(xs)))
            bbox_y1 = max(0, int(min(ys)))
            bbox_x2 = min(w, int(max(xs)))
            bbox_y2 = min(h, int(max(ys)))
            
            if bbox_x2 <= bbox_x1 or bbox_y2 <= bbox_y1:
                raise Exception("Rectangle outside image")
            
            cropped = self.current_page_bgr_array[bbox_y1:bbox_y2, bbox_x1:bbox_x2]
            
            if cropped.size == 0:
                raise Exception("Empty crop")
            
            adjusted_center_x = center_x - bbox_x1
            adjusted_center_y = center_y - bbox_y1
            
            M = cv2.getRotationMatrix2D((adjusted_center_x, adjusted_center_y), angle, 1.0)
            
            crop_h, crop_w = cropped.shape[:2]
            rotated = cv2.warpAffine(cropped, M, (crop_w, crop_h),
                                    flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REPLICATE)
            
            x1 = int(adjusted_center_x - expanded_width / 2)
            y1 = int(adjusted_center_y - expanded_height / 2)
            x2 = int(adjusted_center_x + expanded_width / 2)
            y2 = int(adjusted_center_y + expanded_height / 2)
            
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(crop_w, x2)
            y2 = min(crop_h, y2)
            
            final_crop = rotated[y1:y2, x1:x2]
            
            if final_crop.size == 0:
                raise Exception("Final crop empty")
            
            new_text, conf = manual_angular_ocr(final_crop, cls)
            
            QtWidgets.QApplication.restoreOverrideCursor()
            
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("OCR Ergebnis")
            msg.setIcon(QtWidgets.QMessageBox.Question)
            msg.setText(f"OCR Ergebnis:\n\n'{new_text}'\n\nKonfidenz: {conf:.2f}\n\nÜbernehmen?")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            
            result = msg.exec_()
            
            if result == QtWidgets.QMessageBox.Yes:
                row_id = item_to_update.data(0, QtCore.Qt.UserRole)
        
            if row_id:
                self._save_state("Manuelles OCR", [row_id])
            item_to_update.setText(col_to_update, new_text)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Manual OCR Error", str(e))
        finally:
            self.btn_manual_ocr.setChecked(False)
            self.btn_manual_ocr_angular.setChecked(False)
            self.view.toggle_drawing_mode(False)
    
    def on_manual_link_toggled(self, checked: bool):
            """Toggle manual linking mode"""
            self.is_manual_linking_mode = checked
            
            if checked:
                # --- ADD THIS ---
                self._set_status(
                    "Verknüpfungsmodus: 1. Klicken Sie auf ein Ankerelement (z.B. Signal). 2. Klicken Sie auf die zugehörige Koordinate."
                )
                # --- END ADD ---

                if self.btn_manual_ocr.isChecked():
                    self.btn_manual_ocr.setChecked(False)
                if self.btn_manual_ocr_angular.isChecked():
                    self.btn_manual_ocr_angular.setChecked(False)
                
                self.view.setCursor(QtCore.Qt.CrossCursor)
                self.link_source_row_id = None
                if self.link_drag_line and self.link_drag_line.scene():
                    self.scene.removeItem(self.link_drag_line)
                self.link_drag_line = None
            else:
                # --- ADD THIS ---
                self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                # --- END ADD ---
                
                self.view.setCursor(QtCore.Qt.ArrowCursor)
                self.link_source_row_id = None
                if self.link_drag_line and self.link_drag_line.scene():
                    self.scene.removeItem(self.link_drag_line)
                self.link_drag_line = None

    def on_linking_click(self, scene_pos: QtCore.QPointF):
        """Handle click during linking mode"""
        clicked_items = self.scene.items(scene_pos)
        
        clicked_row_id = None
        for item in clicked_items:
            try:
                data = item.data(0)
                if data is not None:
                    clicked_row_id = int(data)
                    break
            except:
                continue
        
        if clicked_row_id is None:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte auf ein Element klicken")
            return
        
        row_list = self.df_all[self.df_all['row_id'] == clicked_row_id]
        if row_list.empty:
            return
        
        clicked_class = row_list.iloc[0].get('cls')
        
        if self.link_source_row_id is None:
            if clicked_class == 'coordinate':
                QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte zuerst Ankerelement klicken")
                return
            
            self.link_source_row_id = clicked_row_id
            
            items = self.current_row_items.get(clicked_row_id)
            if items:
                pen = QtGui.QPen(QtGui.QColor("#ffff00"), 4)
                for it in items:
                    if isinstance(it, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem)):
                        it.setPen(pen)
        else:
            if clicked_class != 'coordinate':
                QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte auf Koordinate klicken")
                return
            
            coord_row_id = clicked_row_id
            anchor_row_id = self.link_source_row_id
            
            self._link_anchor_to_coordinate(anchor_row_id, coord_row_id)

            self.link_source_row_id = None
            # Note: _link_anchor_to_coordinate() already updates the anchor overlay
            # via _update_single_row_overlay(), so no need for full page refresh
            self.btn_manual_link.setChecked(False)
    
    def _link_anchor_to_coordinate(self, anchor_row_id: int, coord_row_id: int):
        """Link anchor to coordinate"""
        anchor_rows = self.df_all[self.df_all['row_id'] == anchor_row_id]
        if anchor_rows.empty:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Anchor not found")
            return
        
        anchor_row = anchor_rows.iloc[0]
        anchor_class = anchor_row.get('cls')
        anchor_text = anchor_row.get('anchor_text', '')
        
        coord_rows = self.df_all[self.df_all['row_id'] == coord_row_id]
        if coord_rows.empty:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Coordinate not found")
            return
        
        coord_row = coord_rows.iloc[0]
        coord_text = coord_row.get('coord_text', '')
        coord_value = coord_row.get('coord_value')
        gi_gl = coord_row.get('gi_gl')
        cx1, cy1 = coord_row.get('cx1'), coord_row.get('cy1')
        cx2, cy2 = coord_row.get('cx2'), coord_row.get('cy2')
        
        if not coord_text:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Coordinate has no text")
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Verknüpfung bestätigen",
            f"Verknüpfen?\n\nAnker: {anchor_class} '{anchor_text}'\nKoordinate: {coord_text}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._save_state("Koordinate verknüpft", [anchor_row_id])

        #  FIX: Ensure link_coord_row_id column exists
        if 'link_coord_row_id' not in self.df_all.columns:
            print(f" Creating link_coord_row_id column in df_all")
            self.df_all['link_coord_row_id'] = None

        anchor_idx_list = self.df_all.index[self.df_all['row_id'] == anchor_row_id].tolist()
        if anchor_idx_list:
            idx = anchor_idx_list[0]
            #  FIX: Store the coordinate row_id to track the link
            self.df_all.at[idx, 'link_coord_row_id'] = coord_row_id
            self.df_all.at[idx, 'coord_text'] = coord_text
            self.df_all.at[idx, 'coord_value'] = coord_value
            self.df_all.at[idx, 'gi_gl'] = gi_gl
            self.df_all.at[idx, 'cx1'] = cx1
            self.df_all.at[idx, 'cy1'] = cy1
            self.df_all.at[idx, 'cx2'] = cx2
            self.df_all.at[idx, 'cy2'] = cy2
            print(f"Linked anchor row_id={anchor_row_id} to coordinate row_id={coord_row_id}")
        
        df_page = self.page_dfs.get(self.current_page)
        if df_page is not None:
            #  FIX: Ensure link_coord_row_id column exists in page_dfs too
            if 'link_coord_row_id' not in df_page.columns:
                df_page['link_coord_row_id'] = None

            page_idx_list = df_page.index[df_page['row_id'] == anchor_row_id].tolist()
            if page_idx_list:
                idx_p = page_idx_list[0]
                #  FIX: Store the link in page_dfs too
                df_page.at[idx_p, 'link_coord_row_id'] = coord_row_id
                df_page.at[idx_p, 'coord_text'] = coord_text
                df_page.at[idx_p, 'coord_value'] = coord_value
                df_page.at[idx_p, 'gi_gl'] = gi_gl
                df_page.at[idx_p, 'cx1'] = cx1
                df_page.at[idx_p, 'cy1'] = cy1
                df_page.at[idx_p, 'cx2'] = cx2
                df_page.at[idx_p, 'cy2'] = cy2
        
        anchor_tree_item = self.row_id_to_tree_item.get(anchor_row_id)
        if anchor_tree_item:
            anchor_tree_item.setText(1, coord_text)

        #  OPTIMIZED: Only update the single affected row (not full page rebuild)
        self._update_single_row_overlay(anchor_row_id)
    
    def _refresh_page_graphics(self):
        """Refresh graphics overlays"""
        if self.current_page not in self.page_base_pix:
            return

        for items in self.current_row_items.values():
            for item in items:
                if item.scene():
                    self.scene.removeItem(item)

        self.current_row_items.clear()
        self._create_items_for_page(self.current_page)

    def _update_single_row_overlay(self, row_id: int):
        """
        Update overlay for a single row only (optimized - no full page rebuild).

        Args:
            row_id: The row ID to update
        """
        print(f"   Incremental update for row {row_id}")

        # 1. Remove existing overlay items for this row
        if row_id in self.current_row_items:
            items = self.current_row_items.pop(row_id)
            for item in items:
                if item and item.scene():
                    self.scene.removeItem(item)
            print(f"Removed {len(items)} old overlay items")

        # 2. Rebuild spec for this single row
        df_page = self.page_dfs.get(self.current_page)
        if df_page is None:
            return

        row_data = df_page[df_page['row_id'] == row_id]
        if row_data.empty:
            print(f"Row {row_id} not found in page_dfs")
            return

        row = row_data.iloc[0]

        # Build label (same logic as _rebuild_row_specs_for_page)
        label = f"{row['cls']} {row.get('conf', 0.0):.2f}"
        if pd.notna(row.get('anchor_text')) and row['anchor_text']:
            label += f" | {row['anchor_text']}"
        if pd.notna(row.get('coord_text')) and row['coord_text']:
            label += f" | {row['coord_text']}"
        if 'angle' in df_page.columns and pd.notna(row.get('angle')):
            try:
                label += f" θ={float(row['angle']):.1f}°"
            except Exception:
                pass

        spec = {"label": label, "is_poly": False}
        poly = row.get("poly", None)

        # Priority 1: Use pre-computed poly if available
        if poly is not None and isinstance(poly, (list, tuple, np.ndarray)):
            try:
                pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                spec.update({"is_poly": True, "pts": pts})
            except Exception:
                pass

        if not spec.get("is_poly", False):
            # Get bbox coordinates
            if row['cls'] == 'coordinate':
                x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
            else:
                x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']

            if pd.isna(x1) or x1 is None:
                return

            # Priority 2: Check if rotated (has significant angle)
            angle = row.get('angle', 0.0)
            angle_raw = row.get('angle_raw', angle)
            use_angle = angle if pd.notna(angle) and angle != 0.0 else angle_raw

            if pd.notna(use_angle) and abs(float(use_angle)) > 5.0:
                try:
                    pts = bbox_to_rotated_poly(x1, y1, x2, y2, float(use_angle))
                    spec.update({"is_poly": True, "pts": pts})
                except Exception:
                    pass

            if not spec.get("is_poly", False):
                # Priority 3: Fall back to axis-aligned rectangle
                w = int(x2 - x1)
                h = int(y2 - y1)
                spec.update({"rect": (int(x1), int(y1), w, h)})

        # 3. Update the spec in all_page_row_specs
        if self.current_page not in self.all_page_row_specs:
            self.all_page_row_specs[self.current_page] = {}
        self.all_page_row_specs[self.current_page][row_id] = spec

        # 4. Add the new overlay using existing method
        specs = {row_id: spec}
        self._add_overlays_for_rows(self.current_page, {row_id}, specs)

        print(f"Overlay updated with label: {label[:50]}...")

    def on_export_excel(self):
        """Export to Excel with advanced user configuration"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(self, "Keine Daten", "Nichts zu exportieren")
            return
        
        # Import the dialog
        from excelexport import SimpleExcelExportDialog

        # Show advanced configuration dialog
        dialog = SimpleExcelExportDialog(self)
        
        # Apply theme if you have one (FIXED VERSION)
        try:
            # Try to apply theme if available
            if hasattr(self, 'parent_auditing') and self.parent_auditing is not None:
                if hasattr(self.parent_auditing, 'main_app_ref') and self.parent_auditing.main_app_ref is not None:
                    if hasattr(self.parent_auditing.main_app_ref, '_current_theme'):
                        current_theme = self.parent_auditing.main_app_ref._current_theme
                        
                        # Check if you have DARK_QSS and LIGHT_QSS defined in your main file
                        if current_theme == "dark" and 'DARK_QSS' in globals():
                            dialog.setStyleSheet(DARK_QSS)
                        elif current_theme == "light" and 'LIGHT_QSS' in globals():
                            dialog.setStyleSheet(LIGHT_QSS)
        except Exception as e:
            # If theme application fails, just continue without theme
            print(f"Could not apply theme: {e}")
        
        # Show dialog
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return  # User cancelled
        
        # Get export configuration
        export_config = dialog.get_export_config()
        
        if not export_config['classes']:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Auswahl",
                "Bitte wählen Sie mindestens eine Klasse mit Spalten aus."
            )
            return
        
        # Ask for save location
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Excel speichern",
            f"{os.path.splitext(self.layout_name)[0]}_export.xlsx",
            "Excel (*.xlsx)"
        )
        
        if not fn:
            return
        
        try:
            # Perform export
            self._execute_excel_export(fn, export_config)
            
            QtWidgets.QMessageBox.information(
                self,
                "Gespeichert",
                f"Excel erfolgreich exportiert nach:\n{fn}"
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "Export-Fehler", str(e))

    def _execute_excel_export(self, filename: str, config: dict):
        """Execute the Excel export with given configuration"""
        
        # Get base DataFrame (with or without filters)
        if config['options']['apply_filters']:
            df_base = self._get_filtered_dataframe()
        else:
            df_base = self.df_all.copy()
        
        if df_base.empty:
            raise Exception("Keine Daten zum Exportieren (möglicherweise alle gefiltert)")
        
        # Apply sorting
        sort_by = config['options']['sort_by']
        if sort_by == "Nach Klasse":
            df_base = df_base.sort_values('cls')
        elif sort_by == "Nach Seite":
            df_base = df_base.sort_values('page')
        elif sort_by == "Nach Koordinatenwert":
            df_base = df_base.sort_values('coord_value', na_position='last')
        elif sort_by == "Nach Text/Nummer":
            df_base = df_base.sort_values('anchor_text', na_position='last')
        
        # Create Excel writer
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            
            if config['options']['separate_sheets']:
                # Separate sheet per class
                for cls_name, cls_config in config['classes'].items():
                    self._export_class_to_sheet(
                        writer,
                        df_base,
                        cls_name,
                        cls_config,
                        config['options']
                    )
            else:
                # Single sheet with all classes
                all_data = []
                
                for cls_name, cls_config in config['classes'].items():
                    df_class = df_base[df_base['cls'] == cls_name].copy()
                    
                    if df_class.empty:
                        continue
                    
                    # Select and rename columns
                    df_export = self._prepare_dataframe_for_export(
                        df_class,
                        cls_config,
                        config['options']['include_empty']
                    )
                    
                    if not df_export.empty:
                        all_data.append(df_export)
                
                if all_data:
                    df_combined = pd.concat(all_data, ignore_index=True)
                    df_combined.to_excel(writer, index=False, sheet_name='Alle Klassen')
                    
                    if config['options']['auto_width']:
                        self._auto_adjust_columns(writer, 'Alle Klassen', df_combined)
                    
                    if config['options']['freeze_header']:
                        self._freeze_header(writer, 'Alle Klassen')

    def _export_class_to_sheet(self, writer, df_base: pd.DataFrame, cls_name: str,
                            cls_config: dict, options: dict):
        """Export a single class to its own sheet"""
        df_class = df_base[df_base['cls'] == cls_name].copy()
        
        if df_class.empty:
            return
        
        # Prepare DataFrame
        df_export = self._prepare_dataframe_for_export(
            df_class,
            cls_config,
            options['include_empty']
        )
        
        if df_export.empty:
            return
        
        # Write to Excel
        sheet_name = cls_name[:31]  # Excel sheet name limit
        df_export.to_excel(writer, index=False, sheet_name=sheet_name)
        
        # Apply formatting
        if options['auto_width']:
            self._auto_adjust_columns(writer, sheet_name, df_export)
        
        if options['freeze_header']:
            self._freeze_header(writer, sheet_name)

    def _prepare_dataframe_for_export(self, df: pd.DataFrame, cls_config: dict,
                                    include_empty: bool) -> pd.DataFrame:
        """Prepare DataFrame for export with user-defined columns and names"""
        
        # Get columns in user-defined order
        columns = cls_config['columns']
        display_names = cls_config['display_names']
        
        # Filter to only existing columns
        available_cols = [c for c in columns if c in df.columns]
        
        if not available_cols:
            return pd.DataFrame()
        
        # Select columns
        df_export = df[available_cols].copy()
        
        # Rename to display names
        rename_map = {col: display_names.get(col, col) for col in available_cols}
        df_export = df_export.rename(columns=rename_map)
        
        # Handle empty cells
        if not include_empty:
            # Replace NaN/None with empty string for better readability
            df_export = df_export.fillna('')
        
        return df_export

    def _get_filtered_dataframe(self) -> pd.DataFrame:
        """Get DataFrame with current filters applied"""
        df_filtered = self.df_all.copy()
        
        # Apply confidence thresholds
        keep_rows = []
        for _, row in df_filtered.iterrows():
            conf = row.get('conf', 0.0)
            cls = row.get('cls', '')
            g = self._class_confidence_thresholds.get('__all__', 0.0)
            c = self._class_confidence_thresholds.get(cls, 0.0)
            if conf >= g and conf >= c:
                keep_rows.append(row)
        
        return pd.DataFrame(keep_rows) if keep_rows else pd.DataFrame()

    def _auto_adjust_columns(self, writer, sheet_name: str, df: pd.DataFrame):
        """Auto-adjust column widths in Excel"""
        try:
            from openpyxl.utils import get_column_letter
            
            worksheet = writer.sheets[sheet_name]
            
            for idx, col in enumerate(df.columns):
                # Calculate max length
                max_length = max(
                    df[col].astype(str).map(len).max(),  # Max in data
                    len(str(col))  # Column name length
                )
                
                # Add padding and cap
                adjusted_width = min(max_length + 2, 50)
                
                # Set width
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = adjusted_width
        
        except Exception as e:
            print(f"Warning: Could not auto-adjust columns: {e}")

    def _freeze_header(self, writer, sheet_name: str):
        """Freeze the header row"""
        try:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = 'A2'  # Freeze first row
        except Exception as e:
            print(f"Warning: Could not freeze header: {e}")

    def on_export_json(self):
        """Export to JSON"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(self, "Keine Daten", "Nichts zu exportieren")
            return
        
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "JSON speichern",
            f"{os.path.splitext(self.layout_name)[0]}_export.json",
            "JSON (*.json)"
        )
        if not fn:
            return
        
        try:
            df_base = self.df_all.copy()
            keep = []
            for _, row in df_base.iterrows():
                conf = row.get('conf', 0.0)
                cls = row.get('cls', '')
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(cls, 0.0)
                if conf >= g and conf >= c:
                    keep.append(row)
            
            if not keep:
                QtWidgets.QMessageBox.information(self, "Keine Daten", "Keine Daten nach Filter")
                return
            
            df_out = pd.DataFrame(keep)
            
            output_data = {}
            classes = sorted(df_out['cls'].unique())
            if 'coordinate' in classes:
                classes.remove('coordinate')
                classes.append('coordinate')
            
            for cls_name in classes:
                df_class = df_out[df_out['cls'] == cls_name].copy()
                
                if cls_name == 'coordinate':
                    cols_to_keep = ['coord_text', 'coord_value', 'gi_gl', 'page', 'notes', 'conf']
                    col_rename = {
                        'coord_text': 'Text',
                        'coord_value': 'Wert',
                        'gi_gl': 'GI/GL',
                        'page': 'Seite',
                        'notes': 'Notizen',
                        'conf': 'Konfidenz'
                    }
                else:
                    cols_to_keep = ['anchor_text', 'coord_text', 'coord_value', 'gi_gl', 'page', 'notes', 'conf']
                    col_rename = {
                        'anchor_text': 'Text/Nummer',
                        'coord_text': 'Koordinatentext',
                        'coord_value': 'Koordinatenwert',
                        'gi_gl': 'GI/GL',
                        'page': 'Seite',
                        'notes': 'Notizen',
                        'conf': 'Konfidenz'
                    }
                    if cls_name == 'signal':
                        cols_to_keep.append('fahrtrichtung')
                        col_rename['fahrtrichtung'] = 'Fahrtrichtung'
                
                cols_to_keep = [c for c in cols_to_keep if c in df_class.columns]
                if not cols_to_keep:
                    continue
                
                df_sheet = df_class[cols_to_keep].copy()
                df_sheet.rename(columns=col_rename, inplace=True)
                output_data[cls_name] = df_sheet.to_dict('records')
            
            import json
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            QtWidgets.QMessageBox.information(self, "Gespeichert", f"JSON exportiert nach:\n{fn}")
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler", str(e))

    def _save_edit_state(self, row_ids: List[int], action: str):
        """
        Alias for _save_state with different parameter order.
        Called from context menus and external components.

        Args:
            row_ids: List of row IDs that were modified
            action: Description of the action
        """
        self._save_state(action, row_ids)

    def _save_state(self, action_name: str, affected_row_ids: List[int]):
        """
        Save current state to undo stack

        Args:
            action_name: Description of the action
            affected_row_ids: List of row IDs that were modified
        """

        if self._is_undoing_or_redoing:
            return
        
        if self._is_loading_data:
            return
        
        if not affected_row_ids:
            return        
        
        # Get current state of affected rows
        state = {
            'action': action_name,
            'timestamp': pd.Timestamp.now(),
            'rows': {}
        }
        
        for row_id in affected_row_ids:
            row_data = self.df_all[self.df_all['row_id'] == row_id]
            if not row_data.empty:
                # Store complete row as dict
                row_dict = row_data.iloc[0].to_dict()
                
                # Filter out numpy arrays (convert to lists)
                filtered_dict = {}
                for col, value in row_dict.items():
                    if isinstance(value, np.ndarray):
                        try:
                            filtered_dict[col] = value.tolist()
                        except:
                            continue
                    else:
                        filtered_dict[col] = value
                
                state['rows'][row_id] = filtered_dict
        
        # Add to undo stack
        self.undo_stack.append(state)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        
        # Clear redo stack (new action invalidates redo history)
        self.redo_stack.clear()
        
        self._set_status(f" {action_name} - Rückgängig: Strg+Z")
        
        # Update button states
        if hasattr(self, '_update_undo_redo_buttons'):
            self._update_undo_redo_buttons()

    def undo(self):
        """Undo last action"""

        print(f"UNDO called - Stack size: {len(self.undo_stack)}")

        if not self.undo_stack:
            self._set_status(" Nichts rückgängig zu machen")
            print(f"Undo stack is empty!")
            QtWidgets.QMessageBox.information(
                self,
                "Rückgängig",
                "Keine Aktionen zum Rückgängigmachen vorhanden."
            )
            return

        self._is_undoing_or_redoing = True
        self.cancel_pending_ocr_resize()

        try:
            state = self.undo_stack.pop()
            print(f"Undoing action: {state['action']}")
            print(f"State contains {len(state['rows'])} rows")
            print(f"Row IDs in state: {list(state['rows'].keys())}")
            
            is_deletion = state.get('is_deletion', False)
            
            if is_deletion:
                print(f"Restoring {len(state['rows'])} deleted rows")
                
                redo_state = {
                    'action': f"Redo: {state['action']}",
                    'timestamp': pd.Timestamp.now(),
                    'is_deletion': True,
                    'rows': state['rows'].copy()
                }
                self.redo_stack.append(redo_state)
                
                rows_to_add = []
                row_ids_to_restore = []
                
                for row_id, row_dict in state['rows'].items():
                    print(f"   Restoring row {row_id}: cls={row_dict.get('cls')}, page={row_dict.get('page')}")
                    
                    row_ids_to_restore.append(row_id)
                    
                    # Convert lists back to numpy arrays
                    restored_dict = {}
                    for col, value in row_dict.items():
                        if col == 'poly' and isinstance(value, list):
                            restored_dict[col] = np.array(value)
                        else:
                            restored_dict[col] = value
                    
                    rows_to_add.append(restored_dict)
                
                if rows_to_add:
                    print(f"  Adding {len(rows_to_add)} rows back to df_all")
                    
                    # Remove duplicates FIRST
                    print(f"   Removing any existing duplicates of row_ids: {row_ids_to_restore}")
                    self.df_all = self.df_all[~self.df_all['row_id'].isin(row_ids_to_restore)]
                    print(f"  df_all after cleanup: {len(self.df_all)} rows")
                    
                    # Add rows back
                    new_rows_df = pd.DataFrame(rows_to_add)
                    self.df_all = pd.concat([self.df_all, new_rows_df], ignore_index=True)
                    
                    print(f"  df_all after restore: {len(self.df_all)} rows")
                    
                    # Verify no duplicates
                    duplicate_check = self.df_all['row_id'].duplicated().sum()
                    if duplicate_check > 0:
                        print(f"WARNING: {duplicate_check} duplicate row_ids found!")
                        self.df_all = self.df_all.drop_duplicates(subset='row_id', keep='last')
                        print(f"   After deduplication: {len(self.df_all)} rows")
                    
                    #  FIX: Rebuild page_dfs for ALL pages that were affected
                    affected_pages = set(row_dict.get('page') for row_dict in state['rows'].values())
                    print(f"   Rebuilding page_dfs for affected pages: {affected_pages}")
                    
                    for page_num in affected_pages:
                        if page_num is not None:
                            page_num_int = int(page_num)
                            self.page_dfs[page_num_int] = self.df_all[self.df_all['page'] == page_num].copy()
                            print(f"Page {page_num_int}: {len(self.page_dfs[page_num_int])} rows")
                    
                    #  FIX: Rebuild row specs for affected pages ONLY
                    print(f"   Rebuilding row specs for affected pages...")
                    for page_num in affected_pages:
                        if page_num is not None:
                            page_num_int = int(page_num)
                            self._rebuild_row_specs_for_page(page_num_int)
                    
                    #  FIX: Only refresh if current page was affected
                    if self.current_page in affected_pages:
                        print(f"   Refreshing current page {self.current_page}...")
                        # Guard against missing page pixmap
                        if self.current_page not in self.page_base_pix:
                            print(f"WARNING: page_base_pix missing for page {self.current_page}, skipping graphics refresh")
                        else:
                            # Force full graphics rebuild
                            self.scene.clear()
                            _, _, _, _, bg = self._get_theme_colors()
                            self.scene.setBackgroundBrush(QtGui.QBrush(bg))
                            self.scene.addPixmap(self.page_base_pix[self.current_page])
                            self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[self.current_page].rect()))
                            self._create_items_for_page(self.current_page)
                            self._populate_tree(self.current_page)

                    print(f"  Deletion undo complete!")
            
            else:
                # Normal undo (edit) - restore previous values
                print(f"Restoring previous state for {len(state['rows'])} rows")

                # Save current state to redo stack BEFORE restoring
                redo_state = {
                    'action': f"Redo: {state['action']}",
                    'timestamp': pd.Timestamp.now(),
                    'rows': {}
                }

                affected_pages = set()

                for row_id, old_row_dict in state['rows'].items():
                    # Get current state for redo
                    current_row = self.df_all[self.df_all['row_id'] == row_id]
                    if not current_row.empty:
                        current_dict = current_row.iloc[0].to_dict()

                        # Filter out numpy arrays
                        filtered_dict = {}
                        for col, value in current_dict.items():
                            if isinstance(value, np.ndarray):
                                try:
                                    filtered_dict[col] = value.tolist()
                                except:
                                    continue
                            else:
                                filtered_dict[col] = value

                        redo_state['rows'][row_id] = filtered_dict

                        # Restore old values
                        mask = self.df_all['row_id'] == row_id
                        if mask.any():
                            idx = self.df_all[mask].index[0]

                            # Restore all columns, handling lists and numpy arrays properly
                            for col, value in old_row_dict.items():
                                if col == 'poly' and isinstance(value, list):
                                    # Convert list back to numpy array for poly field
                                    self.df_all.at[idx, col] = np.array(value)
                                else:
                                    # Always use .at for all assignments to avoid pandas indexing errors
                                    # .at works correctly with scalars, lists, arrays, and any other type
                                    self.df_all.at[idx, col] = value

                            page_num = int(old_row_dict.get('page', self.current_page))
                            affected_pages.add(page_num)

                            # Debug: Show restored coordinates
                            cls = old_row_dict.get('cls')
                            ocr_x1 = old_row_dict.get('ocr_x1')
                            ocr_y1 = old_row_dict.get('ocr_y1')
                            ocr_x2 = old_row_dict.get('ocr_x2')
                            ocr_y2 = old_row_dict.get('ocr_y2')
                            print(f"   Restoring row {row_id} ({cls}):")
                            print(f"OCR region: ocr_x1={ocr_x1}, ocr_y1={ocr_y1}, ocr_x2={ocr_x2}, ocr_y2={ocr_y2}")
                            if cls == 'coordinate':
                                print(f"Coords: cx1={old_row_dict.get('cx1')}, cy1={old_row_dict.get('cy1')}, cx2={old_row_dict.get('cx2')}, cy2={old_row_dict.get('cy2')}")
                            else:
                                print(f"Anchor: ax1={old_row_dict.get('ax1')}, ay1={old_row_dict.get('ay1')}, ax2={old_row_dict.get('ax2')}, ay2={old_row_dict.get('ay2')}")

                self.redo_stack.append(redo_state)

                # Rebuild page_dfs for affected pages
                for page_num in affected_pages:
                    self.page_dfs[page_num] = self.df_all[self.df_all['page'] == page_num].copy()
                    print(f"   Rebuilt page_dfs for page {page_num}")

                    # Debug: Verify coordinates in page_dfs
                    for row_id in state['rows'].keys():
                        row_in_page = self.page_dfs[page_num][self.page_dfs[page_num]['row_id'] == row_id]
                        if not row_in_page.empty:
                            r = row_in_page.iloc[0]
                            if r['cls'] == 'coordinate':
                                print(f"Page_dfs row {row_id}: cx1={r.get('cx1')}, cy1={r.get('cy1')}, cx2={r.get('cx2')}, cy2={r.get('cy2')}")
                            else:
                                print(f"Page_dfs row {row_id}: ax1={r.get('ax1')}, ay1={r.get('ay1')}, ax2={r.get('ax2')}, ay2={r.get('ay2')}")

                # Rebuild row specs for affected pages
                for page_num in affected_pages:
                    self._rebuild_row_specs_for_page(page_num)
                    print(f"   Rebuilt row specs for page {page_num}")

                    # Debug: Show specs
                    for row_id in state['rows'].keys():
                        if row_id in self.all_page_row_specs.get(page_num, {}):
                            spec = self.all_page_row_specs[page_num][row_id]
                            print(f"Spec for row {row_id}: {spec}")

                # Refresh display if current page affected
                if self.current_page in affected_pages:
                    print(f"   Refreshing current page {self.current_page}")

                    #  OPTIMIZATION: Only update affected items instead of full rebuild
                    # This is much faster than clearing the entire scene
                    affected_on_current_page = [rid for rid in state['rows'].keys()
                                                if rid in self.all_page_row_specs.get(self.current_page, {})]

                    use_incremental = len(affected_on_current_page) < 50

                    if use_incremental:
                        print(f"Using incremental update for {len(affected_on_current_page)} items")

                        try:
                            # Remove only affected items
                            for row_id in affected_on_current_page:
                                items = self.current_row_items.get(row_id, [])
                                for item in items:
                                    if item and item.scene():
                                        self.scene.removeItem(item)
                                self.current_row_items.pop(row_id, None)

                            # Rebuild specs for affected rows
                            for page_num in affected_pages:
                                self._rebuild_row_specs_for_page(page_num)

                            # Re-add only affected items
                            specs = self.all_page_row_specs.get(self.current_page, {})
                            self._add_overlays_for_rows(self.current_page, set(affected_on_current_page), specs)

                            # Update only affected tree items
                            for row_id in affected_on_current_page:
                                tree_item = self.row_id_to_tree_item.get(row_id)
                                if tree_item:
                                    row = self.df_all[self.df_all['row_id'] == row_id]
                                    if not row.empty:
                                        r = row.iloc[0]
                                        self.tree.blockSignals(True)
                                        if r['cls'] == 'coordinate':
                                            tree_item.setText(0, str(r.get('coord_text', '')))
                                        else:
                                            tree_item.setText(0, str(r.get('anchor_text', '')))
                                            tree_item.setText(1, str(r.get('coord_text', '')))
                                        self.tree.blockSignals(False)

                            print(f"Incremental update complete")

                        except Exception as e:
                            # Fallback to full rebuild if anything goes wrong
                            print(f"Incremental update failed: {e}")
                            print(f"Falling back to full rebuild")
                            use_incremental = False

                    if not use_incremental:
                        # Many items affected or incremental failed - do full rebuild
                        print(f"Using full rebuild for {len(affected_on_current_page)} items")
                        if self.current_page not in self.page_base_pix:
                            print(f"WARNING: page_base_pix missing for page {self.current_page}, skipping graphics refresh")
                        else:
                            self.scene.clear()
                            _, _, _, _, bg = self._get_theme_colors()
                            self.scene.setBackgroundBrush(QtGui.QBrush(bg))
                            self.scene.addPixmap(self.page_base_pix[self.current_page])
                            self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[self.current_page].rect()))
                            self._create_items_for_page(self.current_page)
                            self._populate_tree(self.current_page)
                            print(f"Full rebuild complete")

                print(f"  Edit undo complete!")

            self._set_status(f"↶ Rückgängig: {state['action']} - Wiederholen: Strg+Y")
            self._update_undo_redo_buttons()

        except Exception as e:
            print(f"ERROR during undo: {e}")
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "Undo Error", f"Error during undo: {str(e)}")

        finally:
            self._is_undoing_or_redoing = False

    def redo(self):
        """Redo last undone action"""        
        if not self.redo_stack:
            self._set_status(" Nichts wiederherzustellen")
            QtWidgets.QMessageBox.information(
                self,
                "Wiederholen",
                "Keine Aktionen zum Wiederherstellen vorhanden."
            )
            return
        
        #  SET FLAG TO PREVENT STATE SAVING
        self._is_undoing_or_redoing = True
        self.cancel_pending_ocr_resize()

        try:
            # Pop from redo stack
            state = self.redo_stack.pop()
            print(f"Redoing action: {state['action']}")
            
            is_deletion = state.get('is_deletion', False)
            
            if is_deletion:
                #  RE-DELETE ROWS
                row_ids_to_delete = list(state['rows'].keys())
                print(f"Re-deleting {len(row_ids_to_delete)} rows: {row_ids_to_delete}")
                
                # Save to undo stack
                undo_state = {
                    'action': state['action'].replace('Redo: ', ''),
                    'timestamp': pd.Timestamp.now(),
                    'is_deletion': True,
                    'rows': state['rows'].copy()
                }
                self.undo_stack.append(undo_state)
                
                # Delete from df_all
                if self.df_all is not None and not self.df_all.empty:
                    self.df_all.drop(
                        self.df_all[self.df_all['row_id'].isin(row_ids_to_delete)].index, 
                        inplace=True
                    )
                
                # Rebuild page_dfs
                self.page_dfs.clear()
                for page_num in sorted(self.df_all['page'].unique()):
                    page_num_int = int(page_num)
                    self.page_dfs[page_num_int] = self.df_all[self.df_all['page'] == page_num].copy()
                
                # Rebuild ALL page specs
                self.all_page_row_specs.clear()
                for pidx, df_page in self.page_dfs.items():
                    specs = {}
                    for _, row in df_page.iterrows():
                        label = f"{row['cls']} {row.get('conf', 0.0):.2f}"
                        if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                            label += f" | {row['anchor_text']}"
                        if pd.notna(row.get('coord_text')) and row['coord_text']:
                            label += f" | {row['coord_text']}"
                        
                        spec = {"label": label, "is_poly": False}
                        poly = row.get("poly", None)

                        # Priority 1: Use pre-computed poly if available
                        if isinstance(poly, (list, tuple)) and len(poly) == 4:
                            try:
                                pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                                spec.update({"is_poly": True, "pts": pts})
                                specs[int(row['row_id'])] = spec
                                continue
                            except Exception:
                                pass

                        # Get bbox coordinates
                        if row['cls'] == 'coordinate':
                            x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
                        else:
                            x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']

                        if pd.isna(x1) or x1 is None:
                            continue

                        # Priority 2: Check if rotated (has significant angle)
                        angle = row.get('angle', 0.0)
                        angle_raw = row.get('angle_raw', angle)

                        # Try angle first, then angle_raw
                        use_angle = angle if pd.notna(angle) and angle != 0.0 else angle_raw

                        if pd.notna(use_angle) and abs(float(use_angle)) > 5.0:  # Significant rotation
                            try:
                                pts = bbox_to_rotated_poly(x1, y1, x2, y2, float(use_angle))
                                spec.update({"is_poly": True, "pts": pts})
                                specs[int(row['row_id'])] = spec
                                continue
                            except Exception:
                                pass

                        # Priority 3: Fall back to axis-aligned rectangle
                        w = int(x2 - x1)
                        h = int(y2 - y1)
                        spec.update({"rect": (int(x1), int(y1), w, h)})
                        specs[int(row['row_id'])] = spec
                    
                    self.all_page_row_specs[pidx] = specs

                # Refresh display - force full rebuild
                print(f"   Forcing full graphics rebuild for deletion redo")
                if self.current_page not in self.page_base_pix:
                    print(f"WARNING: page_base_pix missing for page {self.current_page}, skipping graphics refresh")
                else:
                    self.scene.clear()
                    _, _, _, _, bg = self._get_theme_colors()
                    self.scene.setBackgroundBrush(QtGui.QBrush(bg))
                    self.scene.addPixmap(self.page_base_pix[self.current_page])
                    self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[self.current_page].rect()))
                    self._create_items_for_page(self.current_page)
                    self._populate_tree(self.current_page)

            else:
                #  NORMAL REDO (EDIT)
                # Save current state to undo stack
                undo_state = {
                    'action': state['action'].replace('Redo: ', ''),
                    'timestamp': pd.Timestamp.now(),
                    'rows': {}
                }
                
                for row_id in state['rows'].keys():
                    row_data = self.df_all[self.df_all['row_id'] == row_id]
                    if not row_data.empty:
                        row_dict = row_data.iloc[0].to_dict()
                        
                        # Filter out numpy arrays
                        filtered_dict = {}
                        for col, value in row_dict.items():
                            if isinstance(value, np.ndarray):
                                try:
                                    filtered_dict[col] = value.tolist()
                                except:
                                    continue
                            else:
                                filtered_dict[col] = value
                        
                        undo_state['rows'][row_id] = filtered_dict
                
                self.undo_stack.append(undo_state)

                # Collect affected pages
                affected_pages = set()

                # Restore redo state to df_all
                for row_id, row_dict in state['rows'].items():
                    # Update df_all
                    mask = self.df_all['row_id'] == row_id
                    if mask.any():
                        idx = self.df_all[mask].index[0]

                        for col, value in row_dict.items():
                            if col not in self.df_all.columns:
                                continue

                            try:
                                # Convert lists back to numpy arrays if needed
                                if col == 'poly' and isinstance(value, list):
                                    value = np.array(value)
                                elif isinstance(value, list):
                                    # Use .at for list values to avoid pandas iteration error
                                    self.df_all.at[idx, col] = value
                                    continue

                                self.df_all.at[idx, col] = value
                            except Exception as e:
                                print(f" Could not restore column '{col}': {e}")

                        page = int(row_dict.get('page', self.current_page))
                        affected_pages.add(page)

                # Rebuild page_dfs for all affected pages (like undo does)
                for page_num in affected_pages:
                    self.page_dfs[page_num] = self.df_all[self.df_all['page'] == page_num].copy()
                    print(f"   Rebuilt page_dfs for page {page_num}")

                # Rebuild row specs for affected pages
                for page_num in affected_pages:
                    self._rebuild_row_specs_for_page(page_num)
                    print(f"   Rebuilt row specs for page {page_num}")

                # Update tree widget
                for row_id, row_dict in state['rows'].items():
                    tree_item = self.row_id_to_tree_item.get(row_id)
                    if tree_item:
                        self.tree.blockSignals(True)
                        
                        cls = row_dict.get('cls')
                        
                        if cls == 'coordinate':
                            tree_item.setText(0, str(row_dict.get('coord_text', '')))
                        else:
                            tree_item.setText(0, str(row_dict.get('anchor_text', '')))
                            tree_item.setText(1, str(row_dict.get('coord_text', '')))

                            if cls == 'signal' and pd.notna(row_dict.get('fahrtrichtung')):
                                tree_item.setText(2, str(row_dict.get('fahrtrichtung', '')))
                        
                        self.tree.blockSignals(False)

                # Rebuild graphics - optimize like undo
                # (Specs already rebuilt above for affected pages)
                if self.current_page in affected_pages:
                    print(f"   Refreshing graphics for redo")

                    #  OPTIMIZATION: Only update affected items instead of full rebuild
                    affected_on_current_page = [rid for rid in state['rows'].keys()
                                                if rid in self.all_page_row_specs.get(self.current_page, {})]

                    use_incremental = len(affected_on_current_page) < 50

                    if use_incremental:
                        print(f"Using incremental update for {len(affected_on_current_page)} items")

                        try:
                            # Remove only affected items
                            for row_id in affected_on_current_page:
                                items = self.current_row_items.get(row_id, [])
                                for item in items:
                                    if item and item.scene():
                                        self.scene.removeItem(item)
                                self.current_row_items.pop(row_id, None)

                            # Re-add only affected items with updated specs
                            specs = self.all_page_row_specs.get(self.current_page, {})
                            self._add_overlays_for_rows(self.current_page, set(affected_on_current_page), specs)

                            print(f"Incremental update complete")

                        except Exception as e:
                            # Fallback to full rebuild if anything goes wrong
                            print(f"Incremental update failed: {e}")
                            print(f"Falling back to full rebuild")
                            use_incremental = False

                    if not use_incremental:
                        # Many items affected or incremental failed - do full rebuild
                        print(f"Using full rebuild for {len(affected_on_current_page)} items")
                        if self.current_page not in self.page_base_pix:
                            print(f"WARNING: page_base_pix missing for page {self.current_page}, skipping graphics refresh")
                        else:
                            self.scene.clear()
                            _, _, _, _, bg = self._get_theme_colors()
                            self.scene.setBackgroundBrush(QtGui.QBrush(bg))
                            self.scene.addPixmap(self.page_base_pix[self.current_page])
                            self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[self.current_page].rect()))
                            self._create_items_for_page(self.current_page)
                            self._populate_tree(self.current_page)
                            print(f"Full rebuild complete")

            self._set_status(f"↷ Wiederhergestellt: {state['action']}")

            # Update button states
            self._update_undo_redo_buttons()

        except Exception as e:
            print(f"ERROR during redo: {e}")
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "Redo Error", f"Error during redo: {str(e)}")

        finally:
            #  ALWAYS CLEAR FLAG
            self._is_undoing_or_redoing = False


    def on_toggle_quality_inspector(self, checked: bool):
        """Toggle quality inspector dialog AND confidence color visualization"""
        if checked:
            # Enable confidence colors
            self.show_confidence_colors = True
            self._refresh_page_graphics()

            # Open the Quality Inspector dialog
            if self.df_all is None or self.df_all.empty:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine Daten",
                    "Keine Daten zur Anzeige vorhanden."
                )
                self.btn_quality_inspector.setChecked(False)
                return

            # Check if there are any detections with confidence scores
            df_with_conf = self.df_all[self.df_all['conf'].notna()]
            if df_with_conf.empty:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine Confidence-Daten",
                    "Es gibt keine Erkennungen mit Confidence-Werten."
                )
                self.btn_quality_inspector.setChecked(False)
                return

            try:
                # Open the Quality Inspector dialog
                dialog = QualityInspectorDialog(self, self)

                # When dialog is closed, uncheck the button
                result = dialog.exec_()
                self.btn_quality_inspector.setChecked(False)

            except Exception as e:
                import traceback
                traceback.print_exc()
                QtWidgets.QMessageBox.critical(
                    self,
                    "Fehler",
                    f"Fehler beim Öffnen des Qualitätsinspectors:\n{str(e)}"
                )
                self.btn_quality_inspector.setChecked(False)
        else:
            # Disable confidence colors
            self.show_confidence_colors = False
            self._refresh_page_graphics()
            self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")

    def _open_threshold_dialog(self):
        """Open the Threshold Dialog to adjust confidence thresholds per class."""
        from ui.threshold_dialog import ThresholdDialog
        import config

        # Store old thresholds to detect changes
        old_thresholds = dict(config.CLASS_THRESH)

        dialog = ThresholdDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Dialog applied changes → re-filter detections
            self._apply_threshold_changes(old_thresholds)

    def _apply_threshold_changes(self, old_thresholds: dict):
        """
        Apply threshold changes by re-filtering uncertain detections.

        When thresholds are lowered, some uncertain detections may now qualify
        as confirmed and need to be processed through OCR and linking.

        When thresholds are raised, some confirmed detections may need to be hidden.

        Args:
            old_thresholds: Dictionary of previous CLASS_THRESH values
        """
        import config

        newly_confirmed_count = 0
        hidden_count = 0

        # 1. Find detections that should now be confirmed (threshold lowered)
        if hasattr(self, 'uncertain_detections') and self.uncertain_detections:
            newly_confirmed = []
            for det in self.uncertain_detections:
                # Detection dict has 'name' (class name string) and 'cls' (class index int)
                # We need the string name for threshold lookup
                cls_name = det.get('name', '')
                new_thresh = config.CLASS_THRESH.get(cls_name, 0.25)
                conf = det.get('conf', 0)

                # Check if this detection now meets the new threshold
                if conf >= new_thresh:
                    # Mark for processing (needed by _add_confirmed_uncertain_detections)
                    det['user_confirmed'] = True
                    newly_confirmed.append(det)

            # 2. Process newly confirmed detections through OCR and linking
            if newly_confirmed:
                self._set_status(f"Verarbeite {len(newly_confirmed)} neue Erkennung(en)...")
                QtWidgets.QApplication.processEvents()

                # Use existing method that handles OCR, linking, signal merging, view refresh
                self._add_confirmed_uncertain_detections(newly_confirmed)
                newly_confirmed_count = len(newly_confirmed)

        # 3. Handle threshold changes on existing confirmed detections
        unhidden_count = 0
        if self.df_all is not None and not self.df_all.empty:
            for idx, row in self.df_all.iterrows():
                cls_name = row.get('cls', '')
                new_thresh = config.CLASS_THRESH.get(cls_name, 0.25)
                conf = row.get('conf', 1.0)

                # If confidence now below threshold, hide it
                if conf < new_thresh and not row.get('_hidden', False):
                    self.df_all.at[idx, '_hidden'] = True
                    self.df_all.at[idx, '_hidden_by_threshold'] = True
                    hidden_count += 1
                # If was hidden by threshold but now meets threshold, unhide it
                elif conf >= new_thresh and row.get('_hidden_by_threshold', False):
                    self.df_all.at[idx, '_hidden'] = False
                    self.df_all.at[idx, '_hidden_by_threshold'] = False
                    unhidden_count += 1

            if hidden_count > 0 or unhidden_count > 0:
                # Sync df_all changes to page_dfs (required for overlay display)
                for page_num in self.page_dfs.keys():
                    self.page_dfs[page_num] = self.df_all[self.df_all['page'] == page_num].copy()

                # Rebuild row specs and refresh display
                self._rebuild_row_specs_for_page(self.current_page)
                self.on_page_changed(self.current_page)

        # Show summary status
        status_parts = []
        if newly_confirmed_count > 0:
            status_parts.append(f"{newly_confirmed_count} hinzugefügt")
        if hidden_count > 0:
            status_parts.append(f"{hidden_count} ausgeblendet")
        if unhidden_count > 0:
            status_parts.append(f"{unhidden_count} wieder eingeblendet")

        if status_parts:
            self._set_status(", ".join(status_parts))
        else:
            self._set_status("Schwellenwerte aktualisiert")

    def _run_validation(self):
        """Run enhanced validation with auto-correction support"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Keine Daten zum Validieren vorhanden."
            )
            return
        
        # Show progress dialog
        progress = QtWidgets.QProgressDialog(
            "Validiere Daten...",
            "Abbrechen",
            0, 0,
            self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()
        
        try:
            # Run validation
            from uservalidation.ultimate_validator import validate_everything

            #  NEW: Save to database if layout_name is available
            result = validate_everything(
                self.df_all,
                auto_correct=False,
                layout_name=self.layout_name if hasattr(self, 'layout_name') else None,
                save_to_db=True if hasattr(self, 'layout_name') else False
            )

            progress.close()

            #  Store result for overlay toggling
            self.validation_result = result

            #  NEW: Update error notification in status/title
            self._update_error_notification(result)

            #  Add missing detection overlays
            self._add_missing_detection_overlays(result)

            # Show validation dialog (with uncertain detections if available)
            dialog = EnhancedValidationResultsDialog(result, self.uncertain_detections, self)
            dialog.setWindowFlags(
                QtCore.Qt.Window |  # Make it a separate window
                QtCore.Qt.WindowMinimizeButtonHint |  # Add minimize button
                QtCore.Qt.WindowMaximizeButtonHint |  # Add maximize button
                QtCore.Qt.WindowCloseButtonHint  # Add close button
            )
            # Connect handlers
            dialog.corrections_accepted.connect(self._apply_corrections)  #  Remove lambda
            dialog.jump_to_detection.connect(self._jump_to_detection)

            #  NEW: Connect tool activation signals
            dialog.activate_manual_ocr.connect(self._activate_manual_ocr_tool)
            dialog.activate_manual_link.connect(self._activate_manual_link_tool)
            dialog.activate_bbox_resize.connect(self._activate_bbox_resize_tool)
            dialog.delete_row.connect(self._delete_row_from_validation)

            # Connect uncertain detection signal for navigation
            dialog.jump_to_position.connect(self._jump_to_position)

            #  Add toggle button to dialog
            dialog.show()
            self._validation_dialog = dialog

            dialog.exec_()
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            progress.close()
            QtWidgets.QMessageBox.critical(
                self,
                "Validierungsfehler",
                f"Fehler bei der Validierung:\n{str(e)}\n\n{traceback.format_exc()}"
            )

    def _update_error_notification(self, validation_result):
        """
         NEW: Update UI to show validation error summary.

        Displays error count in status bar and highlights problematic rows.
        """
        try:
            stats = validation_result.get_summary()
            errors = stats['errors']
            warnings = stats['warnings']
            total = stats['total_issues']

            # Build notification message
            if total == 0:
                msg = " Keine Validierungsprobleme gefunden"
                color = "green"
            elif errors > 0:
                msg = f" {errors} Fehler, {warnings} Warnungen ({total} gesamt)"
                color = "red"
            else:
                msg = f" {warnings} Warnungen ({total} gesamt)"
                color = "orange"

            # Update status bar
            self._set_status(msg)

            # Optionally highlight rows with errors in the table
            if hasattr(self, 'table_model') and errors > 0:
                error_row_ids = [issue.row_id for issue in validation_result.issues
                                 if issue.severity == 'error' and issue.row_id >= 0]

                # Store error rows for highlighting
                if not hasattr(self, 'error_rows'):
                    self.error_rows = set()

                self.error_rows = set(error_row_ids)

        except Exception as e:
            print(f" Failed to update error notification: {e}")

    def _add_overlay_toggle_to_dialog(self, dialog):
        """Add toggle button for missing detection overlays to validation dialog"""
        pass

    def _jump_to_detection(self, row_id: int, position: tuple):
        """
        Jump to a detection in both the graphics view AND the tree.
        
        Args:
            row_id: Row ID to jump to (-1 for position-only jumps)
            position: (x, y) coordinates to center on
        """
        try:
            # ========================================
            # PART 1: Jump in Graphics View
            # ========================================
            x, y = position
            
            # Find which page this position is on
            if row_id >= 0 and 'page' in self.df_all.columns:
                page_row = self.df_all[self.df_all['row_id'] == row_id]
                if not page_row.empty:
                    target_page = int(page_row.iloc[0]['page'])
                    
                    # Switch page if needed
                    if target_page != self.current_page:
                        self.current_page = target_page
                        self.on_page_changed(target_page)  #  FIX: Use on_page_changed
            
            # Center view on position
            self.view.centerOn(x, y)  #  FIX: Use self.view, not self.graphics_view
            
            # Highlight the position
            self._highlight_position(x, y)
            
            # ========================================
            # PART 2: Jump in Tree
            # ========================================
            if row_id >= 0:
                self._jump_to_tree_row(row_id)  #  FIX: Renamed from _jump_to_table_row
            
            # Show status
            self._set_status(  #  FIX: Use _set_status instead of statusBar()
                f" Springe zu Position ({x:.0f}, {y:.0f})" + 
                (f" | Zeile {row_id}" if row_id >= 0 else "")
            )
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status(f" Fehler beim Springen: {str(e)}")  #  FIX

    def _jump_to_position(self, position: tuple):
        """
        Jump to a position in the graphics view (for uncertain detections).

        Args:
            position: (x, y) coordinates to center on
        """
        try:
            x, y = position
            self.view.centerOn(x, y)
            self._highlight_position(x, y)
            self._set_status(f" Springe zu Position ({x:.0f}, {y:.0f})")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_status(f" Fehler beim Springen: {str(e)}")

    def _get_page_coordinates_for_linking(self, page: int) -> list:
        """
        Get all coordinate detections from a specific page for linking.

        Args:
            page: Page number

        Returns:
            List of coordinate dicts compatible with link_anchor_to_coord()
        """
        if self.df_all is None or self.df_all.empty:
            return []

        coords_df = self.df_all[
            (self.df_all['page'] == page) &
            (self.df_all['cls'] == 'coordinate')
        ]

        # Convert to list of dicts for linking function
        coords = []
        for _, row in coords_df.iterrows():
            cx1 = row.get('cx1') if pd.notna(row.get('cx1')) else 0
            cy1 = row.get('cy1') if pd.notna(row.get('cy1')) else 0
            cx2 = row.get('cx2') if pd.notna(row.get('cx2')) else 0
            cy2 = row.get('cy2') if pd.notna(row.get('cy2')) else 0

            coords.append({
                'x1': cx1, 'y1': cy1,
                'x2': cx2, 'y2': cy2,
                'cx': (cx1 + cx2) / 2,
                'cy': (cy1 + cy2) / 2,
                'w': cx2 - cx1,
                'h': cy2 - cy1,
                'name': 'coordinate',
                'text': row.get('coord_text'),
                'row_id': row.get('row_id'),
                'angle': row.get('angle', 0),
            })
        return coords

    def _get_next_row_id(self) -> int:
        """Get next available row_id."""
        if self.df_all is None or self.df_all.empty or 'row_id' not in self.df_all.columns:
            return 0
        max_id = self.df_all['row_id'].max()
        return int(max_id) + 1 if pd.notna(max_id) else 0

    def _get_page_gks_with_coord_map(self, page: int) -> tuple:
        """
        Get all GKS detections and build coordinate map using SAME dict objects.

        CRITICAL: link_haltetafel_to_gks() uses id(gks_det) as keys,
        so the gks_coord_map MUST use id() of the SAME dict objects
        that are in the gks_dets list.

        Args:
            page: Page number

        Returns:
            Tuple of (gks_dets, gks_coord_map):
            - gks_dets: List of GKS detection dicts
            - gks_coord_map: Dict mapping id(gks_det) to linked coordinate dict
        """
        if self.df_all is None or self.df_all.empty:
            return [], {}

        gks_df = self.df_all[
            (self.df_all['page'] == page) &
            (self.df_all['cls'].isin(['gks_festkodiert', 'gks_gesteuert']))
        ]

        gks_dets = []
        gks_coord_map = {}

        for _, row in gks_df.iterrows():
            ax1 = row.get('ax1') if pd.notna(row.get('ax1')) else 0
            ay1 = row.get('ay1') if pd.notna(row.get('ay1')) else 0
            ax2 = row.get('ax2') if pd.notna(row.get('ax2')) else 0
            ay2 = row.get('ay2') if pd.notna(row.get('ay2')) else 0

            # Create GKS detection dict
            gks_det = {
                'x1': ax1, 'y1': ay1, 'x2': ax2, 'y2': ay2,
                'cx': (ax1 + ax2) / 2,
                'cy': (ay1 + ay2) / 2,
                'w': ax2 - ax1,
                'h': ay2 - ay1,
                'name': row.get('cls'),
                'text': row.get('anchor_text'),
                'angle': row.get('angle') if pd.notna(row.get('angle')) else 0,
                'angle_raw': row.get('angle_raw') if pd.notna(row.get('angle_raw')) else 0,
                'obb_cx': row.get('obb_cx'),
                'obb_cy': row.get('obb_cy'),
                'obb_w': row.get('obb_w'),
                'obb_h': row.get('obb_h'),
                'row_id': row.get('row_id'),
            }
            gks_dets.append(gks_det)

            # Build coord map using id() of the SAME gks_det object
            if pd.notna(row.get('cx1')) and pd.notna(row.get('coord_text')):
                cx1 = row.get('cx1')
                cy1 = row.get('cy1')
                cx2 = row.get('cx2')
                cy2 = row.get('cy2')
                gks_coord_map[id(gks_det)] = {
                    'x1': cx1, 'y1': cy1, 'x2': cx2, 'y2': cy2,
                    'cx': (cx1 + cx2) / 2 if cx1 and cx2 else 0,
                    'cy': (cy1 + cy2) / 2 if cy1 and cy2 else 0,
                    'text': row.get('coord_text'),
                }

        return gks_dets, gks_coord_map

    def _activate_manual_ocr_tool(self, mode: str):
        """
         NEW: Activate manual OCR tool (horizontal or angular)

        Args:
            mode: 'horizontal' or 'angular'
        """
        try:
            if mode == 'horizontal':
                self.btn_manual_ocr.setChecked(True)
            elif mode == 'angular':
                self.btn_manual_ocr_angular.setChecked(True)

            self._set_status(f" {mode.capitalize()} OCR aktiviert")
        except Exception as e:
            print(f" Failed to activate OCR tool: {e}")

    def _activate_manual_link_tool(self):
        """ NEW: Activate manual linking tool"""
        try:
            self.btn_manual_link.setChecked(True)
            self._set_status(" Manuelles Verknüpfen aktiviert")
        except Exception as e:
            print(f" Failed to activate manual link tool: {e}")

    def _activate_bbox_resize_tool(self):
        """ NEW: Activate bbox resize mode (just inform user, no specific tool)"""
        try:
            # Bbox resize is done by directly dragging detection edges in the view
            # No specific tool button needed, just inform user
            QtWidgets.QMessageBox.information(
                self,
                "Erkennungsbereich anpassen",
                "Ziehen Sie die Ecken oder Kanten des Erkennungsbereichs im Bild, um die Größe anzupassen."
            )
            self._set_status(" Bbox Resize: Ziehen Sie die Erkennungsbereich-Kanten")
        except Exception as e:
            print(f" Failed to activate bbox resize: {e}")

    def _delete_row_from_validation(self, row_id: int):
        """
         NEW: Delete a single row from validation dialog (no confirmation needed)

        Args:
            row_id: The row_id to delete
        """
        try:
            self.tree.blockSignals(True)

            # Find the tree item
            tree_item = self.row_id_to_tree_item.get(row_id)
            if not tree_item:
                print(f" Row ID {row_id} not found in tree")
                self.tree.blockSignals(False)
                return

            # Save state with deletion marker
            self._save_deletion_state([row_id])

            # 1. Remove from DataFrames
            if self.df_all is not None and not self.df_all.empty:
                self.df_all.drop(
                    self.df_all[self.df_all['row_id'] == row_id].index,
                    inplace=True
                )

            df_page = self.page_dfs.get(self.current_page)
            if df_page is not None and not df_page.empty:
                df_page.drop(
                    df_page[df_page['row_id'] == row_id].index,
                    inplace=True
                )

            # 2. Remove from helper dictionaries and scene
            if row_id in self.row_id_to_tree_item:
                del self.row_id_to_tree_item[row_id]

            graphics_items = self.current_row_items.pop(row_id, [])
            for g_item in graphics_items:
                if g_item and g_item.scene():
                    self.scene.removeItem(g_item)

            # 3. Remove from Tree widget
            parent = tree_item.parent()
            if parent:
                parent.removeChild(tree_item)

            # Update UI
            self._set_status(f"Element (Zeile {row_id}) gelöscht")
            self.tree._update_row_count()
            self.tree._update_selection_count()
            self._update_undo_redo_buttons()

        except Exception as e:
            print(f" Failed to delete row {row_id}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.tree.blockSignals(False)
            self.item_details_notes.clear()

    def _jump_to_tree_row(self, row_id: int):  #  FIX: Renamed from _jump_to_table_row
        """
        Jump to and highlight a specific row in the tree.
        
        Args:
            row_id: The row_id to jump to
        """
        # Find the tree item for this row_id
        tree_item = self.row_id_to_tree_item.get(row_id)
        
        if not tree_item:
            print(f" Row ID {row_id} not found in tree")
            return
        
        # Clear previous selection
        self.tree.clearSelection()
        
        # Select the item
        self.tree.setCurrentItem(tree_item)
        tree_item.setSelected(True)
        
        # Scroll to make it visible
        self.tree.scrollToItem(
            tree_item,
            QtWidgets.QAbstractItemView.PositionAtCenter
        )
        
        # Flash highlight effect
        self._flash_tree_item(tree_item)  #  FIX: Renamed from _flash_table_row
        
        # Also zoom in graphics view
        self.zoom_to_row(row_id)

    def _flash_tree_item(self, item: QtWidgets.QTreeWidgetItem):  #  FIX: Renamed
        """
        Flash a tree item to draw attention.
        
        Args:
            item: QTreeWidgetItem to flash
        """
        # Store original backgrounds for all columns
        original_colors = []
        for col in range(self.tree.columnCount()):
            original_colors.append(item.background(col))
    
        # Flash yellow 3 times
        def flash_step(step=0):
            if step >= 6:  # 3 flashes = 6 steps (on/off)
                # Restore original colors
                for col, color in enumerate(original_colors):
                    item.setBackground(col, color)
                return
            
            # Toggle between yellow and original
            if step % 2 == 0:
                color = QtGui.QBrush(QtGui.QColor(255, 255, 0, 100))  # Yellow
            else:
                color = original_colors[0]  # Original
            
            # Apply to all columns
            for col in range(self.tree.columnCount()):
                item.setBackground(col, color)
            
            # Schedule next flash
            QtCore.QTimer.singleShot(200, lambda: flash_step(step + 1))
        
        flash_step()

    def _highlight_position(self, x: float, y: float, size: float = 200):
        """
        Draw a temporary highlight circle at the given position.
        
        Args:
            x, y: Center coordinates
            size: Diameter of highlight circle
        """
        # Remove previous highlight if exists
        if hasattr(self, '_position_highlight'):
            self.scene.removeItem(self._position_highlight)
        
        # Create pulsing circle
        pen = QtGui.QPen(QtGui.QColor(255, 0, 0), 5)
        brush = QtGui.QBrush(QtGui.QColor(255, 0, 0, 50))
        
        self._position_highlight = self.scene.addEllipse(
            x - size/2, y - size/2, size, size,
            pen, brush
        )
        self._position_highlight.setZValue(1000)  # Draw on top
        
        # Animate pulsing effect
        self._animate_highlight()

    def _animate_highlight(self):
        """Animate the position highlight with pulsing effect"""
        if not hasattr(self, '_position_highlight'):
            return
        
        # Pulse 3 times then remove
        def pulse_step(step=0):
            if step >= 6 or not hasattr(self, '_position_highlight'):
                # Remove highlight
                if hasattr(self, '_position_highlight'):
                    self.scene.removeItem(self._position_highlight)
                    delattr(self, '_position_highlight')
                return
            
            # Scale between 1.0 and 1.3
            scale = 1.0 + (0.3 if step % 2 == 0 else 0.0)
            
            if hasattr(self, '_position_highlight'):
                self._position_highlight.setScale(scale)
            
            # Schedule next pulse
            QtCore.QTimer.singleShot(300, lambda: pulse_step(step + 1))
        
        pulse_step()
    
    def _select_row_in_tree(self, row_id):
        """Select and highlight a row in the tree widget."""
        
        #  FIX: Use self.tree directly (no need for workspace reference)
        if not hasattr(self, 'tree') or self.tree is None:
            return
        
        # Find the tree item with this row_id
        tree_item = self.row_id_to_tree_item.get(row_id)
        
        if tree_item:
            # Select and scroll to item
            self.tree.setCurrentItem(tree_item)
            self.tree.scrollToItem(tree_item, QtWidgets.QAbstractItemView.PositionAtCenter)
            
            # Optional: Flash yellow highlight
            original_bg = tree_item.background(0)

            tree_item.setBackground(0, QtGui.QColor(255, 255, 0))  # Yellow
            tree_item.setBackground(1, QtGui.QColor(255, 255, 0))
            tree_item.setBackground(2, QtGui.QColor(255, 255, 0))
            
            # Restore original background after 1 second
            QtCore.QTimer.singleShot(
                1000, 
                lambda: self._restore_tree_item_background(tree_item, original_bg)
            )
            
            # Also trigger zoom to graphics
            self.zoom_to_row(row_id)
        else:
            print(f" Row ID {row_id} not found in tree")

    def _restore_tree_item_background(self, item, original_bg):
        """Helper to restore tree item background color"""
        try:
            item.setBackground(0, original_bg)
            item.setBackground(1, original_bg)
            item.setBackground(2, original_bg)
        except RuntimeError:
            pass  # Item was deleted

    def _apply_corrections(self, corrections):
        """Apply selected corrections from validation dialog."""

        if not corrections:
            return

        #  UNDO/REDO: Pre-scan to find ALL affected rows (corrections + propagations)
        affected_row_ids = [issue.row_id for issue in corrections]

        # Pre-scan coordinate corrections to find propagation targets
        for issue in corrections:
            if issue.field == 'coord_text':
                mask = self.df_all['row_id'] == issue.row_id
                if mask.any():
                    idx = self.df_all[mask].index[0]
                    cls = self.df_all.at[idx, 'cls']

                    if cls == 'coordinate':
                        # This coordinate correction will propagate
                        old_value = self.df_all.at[idx, 'coord_text']
                        coord_page = self.df_all.at[idx, 'page']

                        # Find all elements on same page with matching coord_text
                        same_page_mask = (self.df_all['page'] == coord_page) & (self.df_all['cls'] != 'coordinate')
                        for _, row in self.df_all[same_page_mask].iterrows():
                            if str(row.get('coord_text', '')).strip() == old_value.strip():
                                if row['row_id'] not in affected_row_ids:
                                    affected_row_ids.append(row['row_id'])

        # Save state for ALL affected rows BEFORE making any changes
        self._save_state("Validierung korrigiert", affected_row_ids)
        print(f" Saved validation state for {len(affected_row_ids)} rows (corrections + propagations)")

        #  FIX: Use self directly
        coordinate_updates = {}  # Track coordinate changes for propagation

        for issue in corrections:
            mask = self.df_all['row_id'] == issue.row_id
            
            if mask.any():
                idx = self.df_all[mask].index[0]
                
                # Store old value for coordinate propagation
                if issue.field == 'coord_text':
                    old_value = self.df_all.at[idx, 'coord_text']
                    
                    # Parse new coordinate value
                    new_value, new_gi = parse_coord(issue.suggested_value)
                    
                    # Update all coordinate-related fields
                    self.df_all.at[idx, 'coord_text'] = issue.suggested_value
                    self.df_all.at[idx, 'coord_value'] = new_value
                    self.df_all.at[idx, 'gi_gl'] = new_gi
                    
                    # Track for propagation
                    if self.df_all.at[idx, 'cls'] == 'coordinate':
                        coordinate_updates[issue.row_id] = (
                            old_value,
                            issue.suggested_value,
                            new_value,
                            new_gi
                        )
                else:
                    # Normal field update
                    self.df_all.at[idx, issue.field] = issue.suggested_value
                
                # Update page_dfs
                page = self.df_all.at[idx, 'page']
                if page in self.page_dfs:
                    page_mask = self.page_dfs[page]['row_id'] == issue.row_id
                    if page_mask.any():
                        page_idx = self.page_dfs[page][page_mask].index[0]
                        
                        if issue.field == 'coord_text':
                            self.page_dfs[page].at[page_idx, 'coord_text'] = issue.suggested_value
                            self.page_dfs[page].at[page_idx, 'coord_value'] = new_value
                            self.page_dfs[page].at[page_idx, 'gi_gl'] = new_gi
                        else:
                            self.page_dfs[page].at[page_idx, issue.field] = issue.suggested_value
                
                # Update tree widget
                tree_item = self.row_id_to_tree_item.get(issue.row_id)
                if tree_item:
                    self.tree.blockSignals(True)

                    cls = self.df_all.at[idx, 'cls']

                    if issue.field == 'anchor_text':
                        tree_item.setText(0, issue.suggested_value)
                    elif issue.field == 'coord_text':
                        if cls == 'coordinate':
                            tree_item.setText(0, issue.suggested_value)
                        else:
                            tree_item.setText(1, issue.suggested_value)
                    elif issue.field == 'fahrtrichtung':
                        tree_item.setText(2, issue.suggested_value)
                    
                    self.tree.blockSignals(False)
        
        #  Propagate coordinate changes to linked elements
        if coordinate_updates:
            linked_count, propagated_row_ids = self._propagate_coordinate_changes(coordinate_updates)
            print(f"Propagated coordinate changes to {linked_count} linked elements")
        
        #  Rebuild graphics with updated data
        self._rebuild_row_specs_for_current_page()
        self.on_page_changed(self.current_page)
        
        QtWidgets.QMessageBox.information(
            self, 
            "Erfolg", 
            f"{len(corrections)} Korrekturen erfolgreich angewendet!"
        )

    def _propagate_coordinate_changes(self, coordinate_updates: Dict) -> tuple:
        """
        Propagate coordinate corrections to all linked elements.

        Args:
            coordinate_updates: Dict of {coord_row_id: (old_text, new_text, new_value, new_gi)}

        Returns:
            Tuple of (number of linked elements updated, list of affected row IDs)
        """
        updated_count = 0
        affected_row_ids = []
        
        for coord_row_id, (old_text, new_text, new_value, new_gi) in coordinate_updates.items():
            # Find the coordinate's bounding box
            coord_rows = self.df_all[self.df_all['row_id'] == coord_row_id]
            if coord_rows.empty:
                continue
            
            coord_row = coord_rows.iloc[0]
            coord_page = coord_row.get('page')
            
            # Get coordinate position
            cx1 = coord_row.get('cx1')
            cy1 = coord_row.get('cy1')
            cx2 = coord_row.get('cx2')
            cy2 = coord_row.get('cy2')
            
            if cx1 is None or cy1 is None:
                continue
            
            #  Find all elements on the same page that reference this OLD coordinate text
            same_page_mask = (self.df_all['page'] == coord_page) & (self.df_all['cls'] != 'coordinate')
            
            for idx, row in self.df_all[same_page_mask].iterrows():
                # Check if this element is linked to the corrected coordinate
                # Method 1: Check if coord_text matches the OLD value
                if str(row.get('coord_text', '')).strip() == old_text.strip():
                    # Track this row for undo/redo
                    element_row_id = row['row_id']
                    affected_row_ids.append(element_row_id)

                    # Update to new coordinate text
                    self.df_all.at[idx, 'coord_text'] = new_text
                    self.df_all.at[idx, 'coord_value'] = new_value
                    self.df_all.at[idx, 'gi_gl'] = new_gi

                    # Also update the bounding box reference
                    self.df_all.at[idx, 'cx1'] = cx1
                    self.df_all.at[idx, 'cy1'] = cy1
                    self.df_all.at[idx, 'cx2'] = cx2
                    self.df_all.at[idx, 'cy2'] = cy2

                    updated_count += 1
                    
                    # Update in page_dfs too
                    if coord_page in self.page_dfs:
                        element_row_id = row['row_id']
                        page_mask = self.page_dfs[coord_page]['row_id'] == element_row_id
                        
                        if page_mask.any():
                            self.page_dfs[coord_page].loc[page_mask, 'coord_text'] = new_text
                            self.page_dfs[coord_page].loc[page_mask, 'coord_value'] = new_value
                            self.page_dfs[coord_page].loc[page_mask, 'gi_gl'] = new_gi
                            self.page_dfs[coord_page].loc[page_mask, 'cx1'] = cx1
                            self.page_dfs[coord_page].loc[page_mask, 'cy1'] = cy1
                            self.page_dfs[coord_page].loc[page_mask, 'cx2'] = cx2
                            self.page_dfs[coord_page].loc[page_mask, 'cy2'] = cy2
                    
                    #  Update tree widget display
                    tree_item = self.row_id_to_tree_item.get(row['row_id'])
                    if tree_item:
                        tree_item.setText(1, new_text)  # Column 1 is coord_text
                    
                    print(f"Updated linked element: {row.get('cls')} '{row.get('anchor_text')}' → '{new_text}'")

        return updated_count, affected_row_ids

    def _rebuild_row_specs_for_current_page(self):
        """Rebuild row specs for the current page only."""
        self._rebuild_row_specs_for_page(self.current_page)

    def _setup_undo_redo_shortcuts(self):
        """Setup undo/redo keyboard shortcuts"""
        # Undo: Ctrl+Z
        self.undo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence.Undo, self)
        self.undo_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.undo_shortcut.activated.connect(self._on_undo_shortcut)
        
        # Redo: Ctrl+Y (Windows) and Ctrl+Shift+Z (Mac/Linux)
        self.redo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence.Redo, self)
        self.redo_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.redo_shortcut.activated.connect(self._on_redo_shortcut)
        
        # Alternative Redo: Ctrl+Shift+Z
        self.redo_shortcut2 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut2.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.redo_shortcut2.activated.connect(self._on_redo_shortcut)
        
        print("Undo/Redo shortcuts initialized")

    def _on_undo_shortcut(self):
        """Handle undo shortcut activation"""
        print("Undo shortcut triggered (Ctrl+Z)")
        self.undo()

    def _on_redo_shortcut(self):
        """Handle redo shortcut activation"""
        print("Redo shortcut triggered (Ctrl+Y)")
        self.redo()

    def _update_undo_redo_buttons(self):
        """Update undo/redo button states"""
        if hasattr(self, 'btn_undo'):
            has_undo = len(self.undo_stack) > 0
            self.btn_undo.setEnabled(has_undo)
            
            if has_undo:
                last_action = self.undo_stack[-1]['action']
                self.btn_undo.setToolTip(f"Rückgängig: {last_action} (Strg+Z)")
                self.btn_undo.setText(f"↶ Rückgängig ({len(self.undo_stack)})")
            else:
                self.btn_undo.setToolTip("Nichts rückgängig zu machen")
                self.btn_undo.setText("↶ Rückgängig")
        
        if hasattr(self, 'btn_redo'):
            has_redo = len(self.redo_stack) > 0
            self.btn_redo.setEnabled(has_redo)
            
            if has_redo:
                last_action = self.redo_stack[-1]['action']
                self.btn_redo.setToolTip(f"Wiederholen: {last_action} (Strg+Y)")
                self.btn_redo.setText(f"↷ Wiederholen ({len(self.redo_stack)})")
            else:
                self.btn_redo.setToolTip("Nichts wiederherzustellen")
                self.btn_redo.setText("↷ Wiederholen")

    def _ensure_validation_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure DataFrame has all columns required for validation.
        Adds missing columns with calculated values.
        
        Args:
            df: Input DataFrame
        
        Returns:
            DataFrame with all required columns
        """
        df = df.copy()
        
        # Add center coordinates (xc, yc) if missing
        if 'xc' not in df.columns:
            # For coordinates, use coordinate box center
            # For anchors, use anchor box center
            df['xc'] = df.apply(
                lambda row: (row['cx1'] + row['cx2']) / 2 if pd.notna(row.get('cx1')) 
                        else (row['ax1'] + row['ax2']) / 2 if pd.notna(row.get('ax1'))
                        else None,
                axis=1
            )
        
        if 'yc' not in df.columns:
            df['yc'] = df.apply(
                lambda row: (row['cy1'] + row['cy2']) / 2 if pd.notna(row.get('cy1'))
                        else (row['ay1'] + row['ay2']) / 2 if pd.notna(row.get('ay1'))
                        else None,
                axis=1
            )
        
        # Add width/height if missing
        if 'w' not in df.columns:
            df['w'] = df.apply(
                lambda row: row['cx2'] - row['cx1'] if pd.notna(row.get('cx1'))
                        else row['ax2'] - row['ax1'] if pd.notna(row.get('ax1'))
                        else None,
                axis=1
            )
        
        if 'h' not in df.columns:
            df['h'] = df.apply(
                lambda row: row['cy2'] - row['cy1'] if pd.notna(row.get('cy1'))
                        else row['ay2'] - row['ay1'] if pd.notna(row.get('ay1'))
                        else None,
                axis=1
            )
        
        # Ensure all required columns exist (add as None if missing)
        required_columns = [
            'row_id', 'cls', 'conf', 'page',
            'anchor_text', 'coord_text', 'coord_value', 'gi_gl',
            'ax1', 'ay1', 'ax2', 'ay2',
            'cx1', 'cy1', 'cx2', 'cy2',
            'xc', 'yc', 'w', 'h',
            'angle', 'fahrtrichtung', 'notes'
        ]
        
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        return df
    
    def _add_missing_detection_overlays(self, validation_result):
        """
        Add colored overlay rectangles for potential missing detections.
        
        Args:
            validation_result: ValidationResult with missing detection issues
        """
        # Clear existing overlays
        self._clear_missing_detection_overlays()
        
        # Filter for missing detection issues on current page
        missing_issues = [
            issue for issue in validation_result.issues
            if issue.context.get('is_missing_detection') and 
               issue.context.get('page') == self.current_page
        ]
        
        for issue in missing_issues:
            bbox = issue.context.get('bbox')
            if not bbox:
                continue
            
            x1, y1, x2, y2 = bbox
            confidence = issue.confidence
            
            #  Color based on confidence
            if confidence > 0.8:
                color = QtGui.QColor(255, 0, 0, 80)  # Red (high confidence)
                pen_color = QtGui.QColor(255, 0, 0, 200)
            elif confidence > 0.6:
                color = QtGui.QColor(255, 165, 0, 80)  # Orange (medium)
                pen_color = QtGui.QColor(255, 165, 0, 200)
            else:
                color = QtGui.QColor(255, 255, 0, 60)  # Yellow (low)
                pen_color = QtGui.QColor(255, 255, 0, 180)
            
            # Create rectangle
            rect = self.scene.addRect(
                x1, y1, x2 - x1, y2 - y1,
                QtGui.QPen(pen_color, 3, QtCore.Qt.DashLine),
                QtGui.QBrush(color)
            )
            rect.setZValue(500)  # Draw above detections but below highlights
            
            # Add label
            label_text = f" {issue.context.get('expected_class', 'Objekt')}\n{confidence:.0%} Konfidenz"
            label = self.scene.addText(label_text)
            label.setPos(x1, y1 - 40)
            label.setDefaultTextColor(pen_color)
            label.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
            label.setZValue(501)
            
            # Store for later removal
            self.missing_detection_overlays.append(rect)
            self.missing_detection_overlays.append(label)
            
            # Make clickable
            rect.setAcceptHoverEvents(True)
            rect.setToolTip(issue.message)
    
    def _clear_missing_detection_overlays(self):
        """Remove all missing detection overlays from scene"""
        for item in self.missing_detection_overlays:
            self.scene.removeItem(item)
        self.missing_detection_overlays.clear()
    
    def toggle_missing_detection_overlays(self, show: bool):
        """Toggle visibility of missing detection overlays"""
        self.show_missing_detections = show
        
        for item in self.missing_detection_overlays:
            item.setVisible(show)


    def _save_deletion_state(self, row_ids_to_delete: List[int]):
        """
        Save state before deletion - stores COMPLETE row data for restoration.
        
        Args:
            row_ids_to_delete: List of row IDs that will be deleted
        """
        if self._is_undoing_or_redoing or self._is_loading_data:
            return
        
        state = {
            'action': f"{len(row_ids_to_delete)} Zeilen gelöscht",
            'timestamp': pd.Timestamp.now(),
            'is_deletion': True,  #  Mark this as a deletion
            'rows': {}
        }
        
        for row_id in row_ids_to_delete:
            row_data = self.df_all[self.df_all['row_id'] == row_id]
            if not row_data.empty:
                # Store complete row as dict
                row_dict = row_data.iloc[0].to_dict()
                
                # Filter out numpy arrays (convert to lists)
                filtered_dict = {}
                for col, value in row_dict.items():
                    if isinstance(value, np.ndarray):
                        try:
                            filtered_dict[col] = value.tolist()
                        except:
                            continue
                    else:
                        filtered_dict[col] = value
                
                state['rows'][row_id] = filtered_dict
        
        # Add to undo stack
        self.undo_stack.append(state)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        
        # Clear redo stack
        self.redo_stack.clear()
        
        print(f" Saved deletion state: {len(row_ids_to_delete)} rows")

    def _rebuild_row_specs_for_page(self, page_num: int):
        """
        Rebuild row specs for a specific page.
        
        Args:
            page_num: Page number to rebuild specs for
        """
        print(f"   Rebuilding specs for page {page_num}")
        
        df_page = self.page_dfs.get(page_num)
        if df_page is None or df_page.empty:
            print(f"No data for page {page_num}")
            self.all_page_row_specs[page_num] = {}
            return

        # Filter out hidden rows - they should not have bounding box specs
        if '_hidden' in df_page.columns:
            df_page = df_page[~df_page['_hidden'].fillna(False)]

        #  Initialize specs dictionary
        specs = {}
        
        for _, row in df_page.iterrows():
            row_id = int(row['row_id'])
            
            # Build label
            label = f"{row['cls']} {row.get('conf', 0.0):.2f}"
            if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                label += f" | {row['anchor_text']}"
            if pd.notna(row.get('coord_text')) and row['coord_text']:
                label += f" | {row['coord_text']}"
            if 'angle' in df_page.columns and pd.notna(row.get('angle')):
                try:
                    label += f" θ={float(row['angle']):.1f}°"
                except Exception:
                    pass
            
            spec = {"label": label, "is_poly": False}
            poly = row.get("poly", None)

            # Priority 1: Use pre-computed poly if available
            # Poly can be: numpy array, flat list of 8 values, or list of 4 tuples
            if poly is not None and isinstance(poly, (list, tuple, np.ndarray)):
                try:
                    # Try to reshape to 4x2 (works for flat lists of 8, nested lists of 4, and numpy arrays)
                    pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                    spec.update({"is_poly": True, "pts": pts})
                    specs[row_id] = spec
                    continue
                except Exception as e:
                    # Reshape failed - poly is in wrong format, fall through to bbox-based rendering
                    pass

            # Get bbox coordinates
            if row['cls'] == 'coordinate':
                x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
            else:
                x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']

            if pd.isna(x1) or x1 is None:
                continue

            # Priority 2: Check if rotated (has significant angle)
            angle = row.get('angle', 0.0)
            angle_raw = row.get('angle_raw', angle)

            # Try angle first, then angle_raw
            use_angle = angle if pd.notna(angle) and angle != 0.0 else angle_raw

            if pd.notna(use_angle) and abs(float(use_angle)) > 5.0:  # Significant rotation
                try:
                    pts = bbox_to_rotated_poly(x1, y1, x2, y2, float(use_angle))
                    spec.update({"is_poly": True, "pts": pts})
                    specs[row_id] = spec
                    continue
                except Exception:
                    pass

            # Priority 3: Fall back to axis-aligned rectangle
            w = int(x2 - x1)
            h = int(y2 - y1)
            spec.update({"rect": (int(x1), int(y1), w, h)})
            specs[row_id] = spec
        
        #  Store the rebuilt specs
        self.all_page_row_specs[page_num] = specs
        
        print(f"Rebuilt {len(specs)} specs for page {page_num}")

    def _update_existing_overlays(self, pidx: int):
        """
        Update existing overlays without clearing the scene.
        Only adds/removes overlays that changed.
        """
        specs = self.all_page_row_specs.get(pidx, {})
        existing_row_ids = set(self.current_row_items.keys())
        new_row_ids = set(specs.keys())
        
        # Find what changed
        to_remove = existing_row_ids - new_row_ids
        to_add = new_row_ids - existing_row_ids
        to_update = existing_row_ids & new_row_ids
        
        print(f"   Overlay update: Remove {len(to_remove)}, Add {len(to_add)}, Update {len(to_update)}")
        
        # Remove deleted overlays
        for row_id in to_remove:
            items = self.current_row_items.pop(row_id, [])
            for item in items:
                if item and item.scene():
                    self.scene.removeItem(item)
        
        # Add new overlays
        if to_add:
            self._add_overlays_for_rows(pidx, to_add, specs)
        
        # Update existing overlays (labels might have changed)
        for row_id in to_update:
            items = self.current_row_items.get(row_id, [])
            spec = specs[row_id]
            
            # Update label text if it exists
            for item in items:
                if isinstance(item, QtWidgets.QGraphicsSimpleTextItem):
                    item.setText(spec['label'])
                    break

    def _add_overlays_for_rows(self, pidx: int, row_ids: set, specs: dict):
        """
        Add overlays for specific rows only.

        Args:
            pidx: Page index
            row_ids: Set of row IDs to add overlays for
            specs: Row specs dictionary
        """
        text_brush = QtGui.QBrush(QtCore.Qt.black)
        normal, _, _, _, _ = self._get_theme_colors()

        selected_class = self._active_class_for_threshold_setting
        show_all_classes = (selected_class == "Alle Klassen")

        for row_id in row_ids:
            if row_id not in specs:
                continue

            spec = specs[row_id]

            # Check filters and get row data
            dfp = self.page_dfs.get(pidx)
            conf = 1.0  # Default confidence
            cls = "unknown"

            if dfp is not None:
                m = dfp[dfp['row_id'] == row_id]
                if m.empty:
                    continue

                #  Skip hidden rows (use == True to handle NaN correctly)
                if m.iloc[0].get('_hidden', False) == True:
                    continue

                conf = m['conf'].iloc[0]
                cls = m['cls'].iloc[0]

                if not show_all_classes and cls != selected_class:
                    continue

                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(cls, 0.0)
                if conf < g or conf < c:
                    continue

            #  NEW: Determine pen color based on validation errors or confidence
            pen_color = normal  # Default theme color
            pen_width = 2

            # Priority 1: Error rows (red)
            if row_id in self.error_rows:
                pen_color = QtGui.QColor(255, 0, 0)  # Red for errors
                pen_width = 3

            # Priority 2: Confidence-based coloring (if enabled and not an error)
            elif self.show_confidence_colors:
                pen_width = 4  # Bolder lines for confidence colors
                if conf >= 0.8:
                    pen_color = QtGui.QColor(0, 255, 0)  # Bright green (high confidence)
                elif conf >= 0.6:
                    pen_color = QtGui.QColor(255, 255, 0)  # Bright yellow (medium confidence)
                else:
                    pen_color = QtGui.QColor(255, 50, 0)  # Bright red-orange (low confidence)

            pen = QtGui.QPen(pen_color, pen_width)

            label = spec["label"]

            items_list = []

            if spec.get("is_poly", False):
                pts = spec["pts"]
                # Get angle from row data if available
                angle = 0.0
                if dfp is not None:
                    m = dfp[dfp['row_id'] == row_id]
                    if not m.empty:
                        angle = m.iloc[0].get('angle', 0.0)

                poly_item = ResizablePolygonBBoxItem(
                    qpolygonf_from_pts(pts),
                    int(row_id),
                    self,
                    angle
                )
                poly_item.setPen(pen)
                poly_item.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                poly_item.setData(0, int(row_id))

                x_pos, y_pos = float(pts[:, 0].min()), float(pts[:, 1].min())
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x_pos, y_pos - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)

                self.scene.addItem(poly_item)
                self.scene.addItem(ti)
                items_list.extend([poly_item, ti])
            else:
                x1, y1, w, h = spec["rect"]
                rect = ResizableBBoxItem(x1, y1, w, h, int(row_id), self)
                rect.setPen(pen)
                rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                rect.setData(0, int(row_id))

                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x1, y1 - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)

                self.scene.addItem(rect)
                self.scene.addItem(ti)
                items_list.extend([rect, ti])

            #  Create OCR bbox if OCR data exists
            if dfp is not None:
                m = dfp[dfp['row_id'] == row_id]
                if not m.empty:
                    row_data = m.iloc[0]
                    if pd.notna(row_data.get('ocr_x1')):
                        ocr_x1 = float(row_data['ocr_x1'])
                        ocr_y1 = float(row_data['ocr_y1'])
                        ocr_x2 = float(row_data['ocr_x2'])
                        ocr_y2 = float(row_data['ocr_y2'])
                        ocr_w = ocr_x2 - ocr_x1
                        ocr_h = ocr_y2 - ocr_y1

                        # Import OCR bbox class
                        from ui.resizable_bbox import ResizableOCRBBoxItem

                        # Create OCR region box
                        ocr_rect = ResizableOCRBBoxItem(ocr_x1, ocr_y1, ocr_w, ocr_h, int(row_id), self)

                        # Style: Use same color as symbol bbox
                        ocr_pen = QtGui.QPen(pen_color)  # Match symbol color
                        ocr_pen.setStyle(QtCore.Qt.DashLine)  # Dashed
                        ocr_pen.setWidth(2)
                        ocr_rect.setPen(ocr_pen)
                        ocr_rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                        ocr_rect.setData(0, int(row_id))
                        ocr_rect.setZValue(5)  # Above symbol bbox but below handles

                        # Add label showing OCR text and confidence
                        ocr_text = row_data.get('anchor_text', '')
                        if ocr_text:
                            ocr_conf = row_data.get('anchor_conf', None)
                            if pd.notna(ocr_conf):
                                ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text} {ocr_conf:.2f}")
                            else:
                                ocr_label = QtWidgets.QGraphicsSimpleTextItem(f"{ocr_text}")
                            ocr_label.setBrush(text_brush)  # Black text like main labels
                            ocr_label.setPos(ocr_x1, ocr_y1 - 40)
                            ocr_label.setData(0, int(row_id))
                            ocr_label.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                            ocr_label.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                            self.scene.addItem(ocr_label)
                            items_list.append(ocr_label)

                        self.scene.addItem(ocr_rect)
                        items_list.append(ocr_rect)

            self.current_row_items[int(row_id)] = items_list

    def _ensure_hidden_column(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure DataFrame has _hidden column with default False values"""
        if '_hidden' not in df.columns:
            df['_hidden'] = False
        else:
            df['_hidden'] = df['_hidden'].fillna(False)
        return df
    
    def _create_single_overlay_from_bbox(self, row_id: int, bbox: dict, pen, text_brush):
        """
        Create a single overlay from a bbox dictionary (for merged signals).
        Shows ONLY the coordinate overlay (first bbox in _all_bboxes).
        """
        print(f"Creating single overlay for row {row_id}")

        items = []

        # Get signal bbox
        ax1 = bbox.get('ax1', 0)
        ay1 = bbox.get('ay1', 0)
        ax2 = bbox.get('ax2', 0)
        ay2 = bbox.get('ay2', 0)

        if ax1 == 0 and ay1 == 0 and ax2 == 0 and ay2 == 0:
            print(f"WARNING: Signal bbox has zero coordinates!")
            return

        #  Get confidence and angle for color determination and rotation
        conf = bbox.get('conf', 1.0)
        angle = bbox.get('angle', 0.0)
        angle_raw = bbox.get('angle_raw', angle)

        print(f"Merged signal bbox: angle={angle}, angle_raw={angle_raw}")

        #  Determine pen color based on confidence or errors
        pen_color = QtGui.QColor(0, 200, 0)  # Default green
        pen_width = 3

        # Priority 1: Check if this is an error row
        if hasattr(self, 'error_rows') and row_id in self.error_rows:
            pen_color = QtGui.QColor(255, 0, 0)  # Red for errors
            pen_width = 3
            print(f"MERGED SIGNAL Row {row_id}: ERROR ROW - Red")

        # Priority 2: Confidence-based coloring (if enabled)
        elif hasattr(self, 'show_confidence_colors') and self.show_confidence_colors:
            pen_width = 4  # Bolder lines for confidence colors
            if conf >= 0.8:
                pen_color = QtGui.QColor(0, 255, 0)  # Bright green (high confidence)
                color_name = "Green"
            elif conf >= 0.6:
                pen_color = QtGui.QColor(255, 255, 0)  # Bright yellow (medium confidence)
                color_name = "Yellow"
            else:
                pen_color = QtGui.QColor(255, 50, 0)  # Bright red-orange (low confidence)
                color_name = "Red"
            print(f" MERGED SIGNAL Row {row_id} (conf={conf:.2f}): {color_name}")
        else:
            print(f" MERGED SIGNAL Row {row_id} (conf={conf:.2f}): Default green (confidence colors disabled)")

        #  Check if rotated (use angle_raw preferably)
        use_angle = angle_raw if angle_raw != 0.0 else angle

        if abs(float(use_angle)) > 5.0:
            # Create ROTATED polygon for signal bbox
            print(f" Creating ROTATED signal bbox with angle={use_angle:.1f}°")
            try:
                pts = bbox_to_rotated_poly(ax1, ay1, ax2, ay2, float(use_angle))
                poly_item = ResizablePolygonBBoxItem(
                    qpolygonf_from_pts(pts),
                    int(row_id),
                    self,
                    float(use_angle)
                )
                signal_pen = QtGui.QPen(pen_color, pen_width)
                poly_item.setPen(signal_pen)
                poly_item.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                poly_item.setData(0, int(row_id))

                self.scene.addItem(poly_item)
                items.append(poly_item)
            except Exception as e:
                print(f"Failed to create rotated signal bbox: {e}")
                # Fall back to axis-aligned rectangle
                w, h = ax2 - ax1, ay2 - ay1
                rect = ResizableBBoxItem(ax1, ay1, w, h, int(row_id), self)
                signal_pen = QtGui.QPen(pen_color, pen_width)
                rect.setPen(signal_pen)
                rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                rect.setData(0, int(row_id))

                self.scene.addItem(rect)
                items.append(rect)
        else:
            # Create axis-aligned rectangle for signal bbox
            signal_pen = QtGui.QPen(pen_color, pen_width)
            w, h = ax2 - ax1, ay2 - ay1
            rect = ResizableBBoxItem(ax1, ay1, w, h, int(row_id), self)
            rect.setPen(signal_pen)
            rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
            rect.setData(0, int(row_id))

            self.scene.addItem(rect)
            items.append(rect)
        
        # Draw coordinate bbox if present
        if bbox.get('cx1') is not None and bbox.get('cy1') is not None:
            cx1 = bbox['cx1']
            cy1 = bbox['cy1']
            cx2 = bbox['cx2']
            cy2 = bbox['cy2']

            if not (cx1 == 0 and cy1 == 0 and cx2 == 0 and cy2 == 0):
                #  Check if coordinate bbox should also be rotated
                if abs(float(use_angle)) > 5.0:
                    # Create ROTATED polygon for coordinate bbox
                    print(f" Creating ROTATED coordinate bbox with angle={use_angle:.1f}°")
                    try:
                        pts = bbox_to_rotated_poly(cx1, cy1, cx2, cy2, float(use_angle))
                        coord_poly = QtWidgets.QGraphicsPolygonItem(qpolygonf_from_pts(pts))
                        coord_pen = QtGui.QPen(pen_color, pen_width)
                        coord_poly.setPen(coord_pen)
                        coord_poly.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                        coord_poly.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        coord_poly.setData(0, int(row_id))

                        self.scene.addItem(coord_poly)
                        items.append(coord_poly)
                        print(f"Added ROTATED coordinate bbox")
                    except Exception as e:
                        print(f"Failed to create rotated coordinate bbox: {e}")
                        # Fall back to axis-aligned rectangle
                        cw = cx2 - cx1
                        ch = cy2 - cy1
                        coord_rect = QtWidgets.QGraphicsRectItem(cx1, cy1, cw, ch)
                        coord_pen = QtGui.QPen(pen_color, pen_width)
                        coord_rect.setPen(coord_pen)
                        coord_rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                        coord_rect.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        coord_rect.setData(0, int(row_id))

                        self.scene.addItem(coord_rect)
                        items.append(coord_rect)
                        print(f"Added coordinate bbox (fallback)")
                else:
                    # Create axis-aligned rectangle for coordinate bbox
                    cw = cx2 - cx1
                    ch = cy2 - cy1
                    coord_rect = QtWidgets.QGraphicsRectItem(cx1, cy1, cw, ch)
                    coord_pen = QtGui.QPen(pen_color, pen_width)
                    coord_rect.setPen(coord_pen)
                    coord_rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                    coord_rect.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                    coord_rect.setData(0, int(row_id))

                    self.scene.addItem(coord_rect)
                    items.append(coord_rect)
                    print(f"Added coordinate bbox")
        
        # Create label
        label = bbox.get('label', 'Unknown')
        ti = QtWidgets.QGraphicsSimpleTextItem(label)
        ti.setBrush(text_brush)
        ti.setPos(ax1, ay1 - 20)
        ti.setData(0, int(row_id))
        ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
        ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        
        self.scene.addItem(ti)
        items.append(ti)
        
        # Store items
        self.current_row_items[row_id] = items
        
        print(f"Created single overlay for row {row_id}")

    def switch_to_page(self, page_number: int):
        """
        Switch to a specific page number.

        Args:
            page_number: The page number to switch to (1-indexed)
        """
        # Validate page number against available pages
        if not hasattr(self, 'page_dfs') or page_number not in self.page_dfs:
            print(f"[WORKSPACE] Page {page_number} not in page_dfs")
            return

        # Call on_page_changed directly (page_spin is deprecated)
        self.on_page_changed(page_number)
        print(f"[WORKSPACE] Switched to page {page_number}")
    def _apply_ocr_adjustment_to_rows(self, row_ids: List[int], delta_x1: int, delta_y1: int,
                                      delta_x2: int, delta_y2: int,
                                      current_row_id: int = None, new_x: float = None,
                                      new_y: float = None, new_x2: float = None, new_y2: float = None):
        """
        Apply OCR region adjustment to specified rows and re-run OCR.

        Uses edge-specific deltas for rotation-aware adjustment.

        Args:
            row_ids: List of row IDs to update
            delta_x1: Left edge delta (how much x1 moved)
            delta_y1: Top edge delta (how much y1 moved)
            delta_x2: Right edge delta (how much x2 moved)
            delta_y2: Bottom edge delta (how much y2 moved)
            current_row_id: Row ID of the currently adjusted symbol (uses absolute coords)
            new_x, new_y, new_x2, new_y2: Absolute coordinates for current_row_id
        """
        import cv2
        from PIL import Image
        from core.ocr_engine import _upscale_if_tiny

        # Track successfully updated rows for incremental overlay update
        updated_row_ids = []

        for rid in row_ids:
            try:
                row_mask = self.df_all['row_id'] == rid
                if not row_mask.any():
                    continue

                row_idx = self.df_all[row_mask].index[0]
                row = self.df_all.loc[row_idx]
                page = int(row.get('page', self.current_page))

                # Get old OCR region
                old_ocr_x1 = row.get('ocr_x1')
                old_ocr_y1 = row.get('ocr_y1')
                old_ocr_x2 = row.get('ocr_x2')
                old_ocr_y2 = row.get('ocr_y2')

                if pd.isna(old_ocr_x1):
                    continue

                #  SPECIAL HANDLING: For the current symbol being adjusted,
                # use absolute coordinates instead of applying deltas
                # This prevents double-adjustment since the user already dragged it to the desired position
                print(f"DEBUG: current_row_id={current_row_id}, rid={rid}, match={current_row_id is not None and rid == current_row_id}")
                if current_row_id is not None and rid == current_row_id:
                    print(f" Current symbol (row {rid}): Using absolute coordinates")
                    print(f"Absolute: x1={new_x}, y1={new_y}, x2={new_x2}, y2={new_y2}")
                    new_ocr_x1 = new_x
                    new_ocr_y1 = new_y
                    new_ocr_x2 = new_x2
                    new_ocr_y2 = new_y2
                else:
                    # For OTHER symbols: apply rotation-aware edge transformation
                    # Get symbol angle for rotation-aware edge adjustment
                    symbol_angle = row.get('angle', None)

                    # Check if angle exists and is valid
                    if symbol_angle is None or pd.isna(symbol_angle):
                        symbol_angle = 0.0
                        print(f"Row {rid}: No angle data, using 0°")
                    else:
                        symbol_angle = float(symbol_angle)
                        print(f" Row {rid}: Symbol angle = {symbol_angle:.1f}°")

                    # Transform edge deltas based on rotation
                    # The deltas were calculated for a reference symbol at a specific rotation
                    # We need to map which edges they apply to for this symbol's rotation
                    from utils.rotation_utils import get_rotation_quadrant

                    # For edge deltas, we need to handle them differently than offset transforms
                    # because we're mapping which physical edge moved, not rotating a vector
                    norm_angle = symbol_angle % 360

                    if 45 <= norm_angle < 135:  # ~90° rotation
                        # Edges map: x1→y2, x2→y1, y1→x1, y2→x2
                        final_dx1 = delta_y1
                        final_dy1 = -delta_x2
                        final_dx2 = delta_y2
                        final_dy2 = -delta_x1
                        print(f" 90° rotation: (x1={delta_x1}, x2={delta_x2}, y1={delta_y1}, y2={delta_y2}) "
                              f"→ (x1={final_dx1}, x2={final_dx2}, y1={final_dy1}, y2={final_dy2})")
                    elif 135 <= norm_angle < 225:  # ~180° rotation
                        # Edges map: x1→x2, x2→x1, y1→y2, y2→y1
                        final_dx1 = -delta_x2
                        final_dy1 = -delta_y2
                        final_dx2 = -delta_x1
                        final_dy2 = -delta_y1
                        print(f" 180° rotation: (x1={delta_x1}, x2={delta_x2}, y1={delta_y1}, y2={delta_y2}) "
                              f"→ (x1={final_dx1}, x2={final_dx2}, y1={final_dy1}, y2={final_dy2})")
                    elif 225 <= norm_angle < 315:  # ~270° rotation
                        # Edges map: x1→y1, x2→y2, y1→x2, y2→x1
                        final_dx1 = -delta_y2
                        final_dy1 = delta_x1
                        final_dx2 = -delta_y1
                        final_dy2 = delta_x2
                        print(f" 270° rotation: (x1={delta_x1}, x2={delta_x2}, y1={delta_y1}, y2={delta_y2}) "
                              f"→ (x1={final_dx1}, x2={final_dx2}, y1={final_dy1}, y2={final_dy2})")
                    else:  # ~0° rotation
                        # No transformation needed
                        final_dx1 = delta_x1
                        final_dy1 = delta_y1
                        final_dx2 = delta_x2
                        final_dy2 = delta_y2
                        print(f"0° rotation: no edge transformation needed")

                    # Apply edge-specific adjustments
                    new_ocr_x1 = old_ocr_x1 + final_dx1
                    new_ocr_y1 = old_ocr_y1 + final_dy1
                    new_ocr_x2 = old_ocr_x2 + final_dx2
                    new_ocr_y2 = old_ocr_y2 + final_dy2

                # Validate and clamp to image bounds
                bgr_array = self.page_bgr_arrays.get(page)
                if bgr_array is not None:
                    img_h, img_w = bgr_array.shape[:2]
                    from utils.rotation_utils import validate_region_bounds

                    new_ocr_x1, new_ocr_y1, new_ocr_x2, new_ocr_y2, is_valid = validate_region_bounds(
                        new_ocr_x1, new_ocr_y1, new_ocr_x2, new_ocr_y2, img_w, img_h
                    )

                    if not is_valid:
                        print(f"Row {rid}: Adjusted region is invalid (too small or out of bounds), skipping")
                        continue

                    print(f"Valid region: ({new_ocr_x1:.0f}, {new_ocr_y1:.0f}, {new_ocr_x2:.0f}, {new_ocr_y2:.0f})")

                # Update dataframe
                self.df_all.loc[row_idx, 'ocr_x1'] = new_ocr_x1
                self.df_all.loc[row_idx, 'ocr_y1'] = new_ocr_y1
                self.df_all.loc[row_idx, 'ocr_x2'] = new_ocr_x2
                self.df_all.loc[row_idx, 'ocr_y2'] = new_ocr_y2

                # Update page_dfs
                if page in self.page_dfs:
                    page_mask = self.page_dfs[page]['row_id'] == rid
                    if page_mask.any():
                        page_idx = self.page_dfs[page][page_mask].index[0]
                        self.page_dfs[page].loc[page_idx, 'ocr_x1'] = new_ocr_x1
                        self.page_dfs[page].loc[page_idx, 'ocr_y1'] = new_ocr_y1
                        self.page_dfs[page].loc[page_idx, 'ocr_x2'] = new_ocr_x2
                        self.page_dfs[page].loc[page_idx, 'ocr_y2'] = new_ocr_y2

                # Re-run OCR on new region (already validated above)
                if bgr_array is not None:
                    crop_x1, crop_y1 = int(new_ocr_x1), int(new_ocr_y1)
                    crop_x2, crop_y2 = int(new_ocr_x2), int(new_ocr_y2)

                    crop_bgr = bgr_array[crop_y1:crop_y2, crop_x1:crop_x2]
                    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                    pil_crop = Image.fromarray(crop_rgb)
                    pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=2)

                    new_text, ocr_conf = paddleocr_recognize(pil_crop)

                    # Update anchor_text
                    self.df_all.loc[row_idx, 'anchor_text'] = new_text
                    if page in self.page_dfs and page_mask.any():
                        self.page_dfs[page].loc[page_idx, 'anchor_text'] = new_text

                    # Update tree widget
                    item = self.row_id_to_tree_item.get(rid)
                    if item:
                        self.tree.blockSignals(True)
                        item.setText(0, new_text)
                        self.tree.blockSignals(False)

                    print(f"Updated row {rid}: '{new_text}' (conf={ocr_conf:.2f})")

                    # Track this row for incremental overlay update
                    updated_row_ids.append(rid)

            except Exception as e:
                print(f"Error updating row {rid}: {e}")

        #  OPTIMIZED: Only update overlays for affected rows (not full page rebuild)
        print(f" Updating overlays for {len(updated_row_ids)} rows...")
        for rid in updated_row_ids:
            self._update_single_row_overlay(rid)

    def _save_ocr_adjustment_to_template(self, symbol_class: str, dx: int, dy: int,
                                         width: int, height: int):
        """
        Save OCR region offset to symbol template definition.

        Args:
            symbol_class: Symbol class name
            dx: Absolute X offset from symbol center in pixels
            dy: Absolute Y offset from symbol center in pixels
            width: Absolute width of OCR region in pixels
            height: Absolute height of OCR region in pixels
        """
        try:
            from core.symbol_detector import NewSymbolDetector

            detector = NewSymbolDetector()

            # Check if symbol exists
            if symbol_class in detector.symbols:
                symbol = detector.symbols[symbol_class]

                # Update or create text_region_offset
                if symbol.text_region_offset is None:
                    symbol.text_region_offset = {}

                # Store absolute offset from symbol center and region size
                symbol.text_region_offset['dx'] = dx
                symbol.text_region_offset['dy'] = dy
                symbol.text_region_offset['width'] = width
                symbol.text_region_offset['height'] = height

                # Save to config
                detector._save_config()

                print(f" Saved OCR region to template '{symbol_class}'")
                print(f"dx={dx}, dy={dy}, width={width}, height={height}")

                QtWidgets.QMessageBox.information(
                    self,
                    "Template aktualisiert",
                    f"OCR-Anpassung wurde für Symbol '{symbol_class}' gespeichert.\n\n"
                    f"Diese Anpassung wird automatisch auf alle zukünftigen Pläne angewendet."
                )
            else:
                print(f"Symbol '{symbol_class}' not found in detector")

        except Exception as e:
            print(f"Error saving to template: {e}")
            import traceback
            traceback.print_exc()

    def _show_auto_learning_suggestion(self, symbol_class: str):
        """
        Show auto-learning suggestion dialog if pattern detected.

        Args:
            symbol_class: Symbol class name
        """
        try:
            learned_data = self.ocr_adjustment_tracker.get_learned_adjustment(symbol_class)

            if learned_data is None:
                return

            QtWidgets.QApplication.restoreOverrideCursor()

            dialog = AutoLearningSuggestionDialog(self, symbol_class, learned_data)

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                # User accepted - save to template
                self._save_ocr_adjustment_to_template(
                    symbol_class,
                    learned_data['offset_x'],
                    learned_data['offset_y'],
                    learned_data['width_delta'],
                    learned_data['height_delta']
                )

                # Mark as applied
                self.ocr_adjustment_tracker.apply_learned_to_template(symbol_class)

                print(f"Auto-learning suggestion accepted for '{symbol_class}'")

        except Exception as e:
            print(f"Error showing auto-learning suggestion: {e}")
            import traceback
            traceback.print_exc()
