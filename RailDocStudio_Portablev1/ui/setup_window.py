# ============================================================================
# RailDoc Studio - Setup & Analyse Modul
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
SetupAndRunWindow - Startfenster fuer Analyse-Konfiguration

Dieses Modul implementiert das Startfenster, in dem der Benutzer
PDF-/Bilddateien auswaehlt und die Analyse startet.

Hauptklassen:
    SetupAndRunWindow: QMainWindow fuer Setup und Analyse-Start

Funktionen:
    - PDF/Bild-Auswahl (Drag-and-Drop unterstuetzt)
    - YOLO-Modell-Auswahl
    - OCR-Engine-Auswahl (PaddleOCR/EasyOCR)
    - Vorschau der ersten Seite
    - Fortschrittsanzeige waehrend Verarbeitung
    - Laden gespeicherter Workspaces

Signale:
    processing_done: Analyse abgeschlossen (DataFrame, Pixmaps, etc.)
    started_processing: Analyse gestartet

Workflow:
    1. Benutzer waehlt PDF/Bild
    2. Benutzer waehlt YOLO-Modell
    3. Klick auf "Analyse starten"
    4. PipelineWorker verarbeitet im Hintergrund
    5. Signal processing_done -> AuditingWindow oeffnet

Abhaengigkeiten:
    PyQt5, pandas, core.pipelineworker
"""
from PyQt5 import QtCore, QtGui, QtWidgets
from ui.graphics_view import InteractiveGraphicsView
from ui.database_dialogs import SavedWorkspacesDialog, DatabaseManagerDialog
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import pandas as pd
import os
from utils.dpi_utils import get_adaptive_window_size, center_window, scale_value
from pdfcomparison.dialogs import HelpDialog
from core.pipelineworker import PipelineWorker
from core.profile_manager import ProfileManager
import time
import cv2
from core.image_processing import qpolygonf_from_pts
# -------- Setup & Run (connects to REAL PipelineWorker signals) --------
class SetupAndRunWindow(QtWidgets.QMainWindow):
    processing_done = QtCore.pyqtSignal(pd.DataFrame, object, object, object, object, object, bool, list, object)  # df_all, page_base_pix, page_dfs, page_bgr_arrays, track_skeleton, exception, from_database, uncertain_detections, learned_patterns
    started_processing = QtCore.pyqtSignal()

    def __init__(self, main_app_ref: 'MainWindow'):
        from main import MainWindow
        super().__init__()
        self.main_app_ref = main_app_ref
        self.setWindowTitle("RailDoc Studio - Setup & Analyse")

        # Adaptive window sizing for different DPI settings
        w, h = get_adaptive_window_size(1000, 800, max_screen_pct=0.85)
        self.resize(w, h)
        center_window(self)
        from paths import get_model_path, get_profile_path
        self.pdf_path = None; self.model_path = str(get_model_path("wienschwarz.pt")); self.ocr_engine = "paddleocr"
        self.profile_path = str(get_profile_path("wien_track_plans.yaml"))  # Default profile
        self.layout_config = None  # Will be loaded when analysis starts
        self.view = InteractiveGraphicsView(self)
        self.view.setStyleSheet("""
            QGraphicsView {
                background: white;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
            }
        """)
        self.scene = QtWidgets.QGraphicsScene(); self.view.setScene(self.scene)
        self.current_page_pixmap_item = None
        self.current_page = 0
        # accumulate pages from real worker
        self._page_base_pix: Dict[int, QtGui.QPixmap] = {}
        self._page_dfs: Dict[int, pd.DataFrame] = {}
        self._build_ui(); self.setAcceptDrops(True)
        self._page_bgr_arrays: Dict[int, np.ndarray] = {}
        self.recent_pdfs: List[str] = []
        self.recent_models: List[str] = []
        self.max_recent = 5
        self._pending_workspace_data: Optional[Dict] = None  # For loading saved workspace after PDF load

        self._load_recent_files()

    def _apply_theme(self):
        """Apply theme-specific styling - adapts to both dark and light themes"""
        is_dark = self.main_app_ref._current_theme == "dark"

        # Theme color palettes - Siemens Blue Style
        if is_dark:
            self.theme_colors = {
                'bg_main': "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2230, stop:1 #1a1d2e)",
                'bg_frame': "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2f42, stop:1 #242837)",
                'bg_header': "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f3447, stop:1 #2c3142)",
                'text_primary': "#e8eaf0",
                'text_secondary': "#a0a4b8",
                'border': "#3a4255",
                'border_hover': "#009999",
                'log_bg': "#242837",
                'log_text': "#e8eaf0",
                'view_bg': "#2c3142",
                'view_border': "#3a4255",
                'info_bg': "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f3447, stop:1 #2c3142)",
                'siemens_blue': "#009999",
                'siemens_blue_light': "#00adef",
                'siemens_success': "#00a8b0"
            }
        else:
            self.theme_colors = {
                'bg_main': "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5f7fa, stop:1 #e8edf2)",
                'bg_frame': "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f8f9fa)",
                'bg_header': "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f0f2f5, stop:1 #e8edf2)",
                'text_primary': "#2c3e50",
                'text_secondary': "#5a6c7d",
                'border': "#cbd5e0",
                'border_hover': "#009999",
                'log_bg': "#ffffff",
                'log_text': "#2c3e50",
                'view_bg': "#ffffff",
                'view_border': "#cbd5e0",
                'info_bg': "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f0f2f5, stop:1 #e8edf2)",
                'siemens_blue': "#009999",
                'siemens_blue_light': "#00adef",
                'siemens_success': "#00a8b0"
            }

        # Apply theme to all widgets
        self.centralWidget().setStyleSheet(f"""
            QWidget {{
                background: {self.theme_colors['bg_main']};
            }}
        """)

        if hasattr(self, 'module_header'):
            self.module_header.setStyleSheet(f"""
                QFrame {{
                    background: {self.theme_colors['bg_header']};
                    border: 1px solid {self.theme_colors['border']};
                    border-radius: 12px;
                    padding: 12px 8px;
                }}
            """)
            self.module_title.setStyleSheet(f"""
                font-size: 13pt;
                font-weight: 600;
                color: {self.theme_colors['text_primary']};
            """)
            # Only update module_desc if it exists (old layout)
            if hasattr(self, 'module_desc'):
                self.module_desc.setStyleSheet(f"""
                    font-size: 9pt;
                    color: {self.theme_colors['text_secondary']};
                """)
            # Update status indicator colors
            if hasattr(self, 'status_indicator'):
                # Status indicator colors don't change with theme - always green
                pass

        # Update frame styles and their labels (compact design with Siemens blue)
        for frame in [getattr(self, name, None) for name in ['pdf_frame', 'model_frame', 'run_frame']]:
            if frame:
                frame.setStyleSheet(f"""
                    QFrame {{
                        background: {self.theme_colors['bg_frame']};
                        border: 1px solid {self.theme_colors['border']};
                        border-radius: 12px;
                        padding: 16px;
                    }}
                    QFrame:hover {{
                        border: 1px solid {self.theme_colors['border_hover']};
                    }}
                """)

                # Update step header color (old layout)
                if hasattr(frame, 'step_header'):
                    frame.step_header.setStyleSheet(f"""
                        font-size: 10pt;
                        font-weight: normal;
                        color: {self.theme_colors['text_secondary']};
                        padding: 0px;
                    """)

                # Update step badge (compact layout)
                if hasattr(frame, 'step_badge'):
                    frame.step_badge.setStyleSheet(f"""
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #009999, stop:1 #00adef);
                        color: white;
                        padding: {scale_value(4)}px {scale_value(10)}px;
                        border-radius: {scale_value(4)}px;
                        font-size: 9pt;
                        font-weight: bold;
                    """)

                # Update step title color
                if hasattr(frame, 'step_title'):
                    frame.step_title.setStyleSheet(f"""
                        font-size: 12pt;
                        font-weight: 700;
                        letter-spacing: 0.5px;
                        color: {self.theme_colors['text_primary']};
                        padding: 0px;
                    """)

        # Update status labels if they haven't been set yet (muted style)
        if hasattr(self, 'lbl_pdf') and "Keine Datei" in self.lbl_pdf.text():
            self.lbl_pdf.setStyleSheet(f"""
                color: {self.theme_colors['text_secondary']};
                font-size: 8pt;
                font-weight: normal;
                padding: {scale_value(6)}px 0px;
            """)


        # Update log
        if hasattr(self, 'log'):
            self.log.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {self.theme_colors['log_bg']};
                    color: {self.theme_colors['log_text']};
                    border: 1px solid {self.theme_colors['border']};
                    border-radius: 12px;
                    padding: 12px;
                    font-size: 9pt;
                }}
            """)

        # Update view
        if hasattr(self, 'view'):
            self.view.setStyleSheet(f"""
                QGraphicsView {{
                    background: {self.theme_colors['view_bg']};
                    border: 1px solid {self.theme_colors['view_border']};
                    border-radius: 12px;
                }}
            """)

        # Update OCR label
        if hasattr(self, 'ocr_label'):
            self.ocr_label.setStyleSheet(f"""
                font-size: 11pt;
                font-weight: 600;
                color: {self.theme_colors['text_primary']};
            """)

        # Update checkbox (Siemens blue)
        if hasattr(self, 'check_force_rerun'):
            self.check_force_rerun.setStyleSheet(f"""
                QCheckBox {{
                    color: {self.theme_colors['text_primary']};
                    font-size: 10pt;
                    font-weight: 500;
                    spacing: 8px;
                }}
                QCheckBox::indicator {{
                    width: 18px;
                    height: 18px;
                    border: 2px solid {self.theme_colors['border']};
                    border-radius: 4px;
                    background: white;
                }}
                QCheckBox::indicator:checked {{
                    background: {self.theme_colors['siemens_success']};
                    border: 2px solid {self.theme_colors['siemens_success']};
                }}
                QCheckBox::indicator:hover {{
                    border: 2px solid {self.theme_colors['siemens_blue']};
                }}
            """)

    def _build_ui(self):
        # DON'T create menus/toolbar yet - widgets don't exist

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setSpacing(scale_value(8))
        main_layout.setContentsMargins(scale_value(10), scale_value(10), scale_value(10), scale_value(10))

        # ========== COMPACT PROFESSIONAL HEADER ==========
        self.module_header = QtWidgets.QFrame()
        header_layout = QtWidgets.QHBoxLayout(self.module_header)
        header_layout.setContentsMargins(scale_value(12), scale_value(8), scale_value(12), scale_value(8))
        header_layout.setSpacing(scale_value(12))

        # Professional module badge (Siemens blue)
        badge_label = QtWidgets.QLabel("MODUL")
        badge_label.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #009999, stop:1 #00adef);
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 8pt;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        header_layout.addWidget(badge_label)

        # Module title - compact
        self.module_title = QtWidgets.QLabel("Gleisplan-Datenextraktion")
        self.module_title.setStyleSheet("font-size: 13pt; font-weight: 600;")
        header_layout.addWidget(self.module_title)

        header_layout.addStretch()

        # Status indicator (Siemens turquoise)
        self.status_indicator = QtWidgets.QLabel("BEREIT")
        self.status_indicator.setStyleSheet("""
            background: #00a8b0;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 7pt;
            font-weight: bold;
            letter-spacing: 1px;
        """)
        header_layout.addWidget(self.status_indicator)

        main_layout.addWidget(self.module_header)

        # ========== COMPACT STEPS - NO EMOJIS ==========
        # Wrapper to center the step cards
        top_wrapper = QtWidgets.QHBoxLayout()
        top_wrapper.addStretch()  # Push cards to center

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(scale_value(12))  # Compact spacing between step cards

        # Step 1: Gleisplan - Compact professional design
        self.pdf_frame = self._create_step_frame_compact(
            step_num="01",
            title="GLEISPLAN"
        )
        pdf_layout = self.pdf_frame.layout()

        self.btn_pdf = QtWidgets.QPushButton("DURCHSUCHEN")
        self.btn_pdf.setMinimumHeight(scale_value(36))
        self.btn_pdf.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_pdf.setStyleSheet("""
            QPushButton {
                font-size: 9pt;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 8px 16px;
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #009999, stop:1 #00adef);
                color: white;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #00b3b3, stop:1 #33c1ff);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #007f7f, stop:1 #0088cc);
            }
        """)
        self.btn_pdf.setToolTip("Wählen Sie Ihren Gleisplan aus (PDF oder Bild)")
        pdf_layout.addWidget(self.btn_pdf)

        # Compact status display
        self.lbl_pdf = QtWidgets.QLabel("Keine Datei")
        self.lbl_pdf.setStyleSheet(f"font-size: 8pt; font-weight: normal; color: #a0a4b8; padding: {scale_value(6)}px 0px;")
        self.lbl_pdf.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_pdf.setMinimumHeight(scale_value(24))
        self.lbl_pdf.setWordWrap(True)  # Allow long filenames to wrap
        pdf_layout.addWidget(self.lbl_pdf)

        # Resolution warning for image files
        self.lbl_resolution_hint = QtWidgets.QLabel(" Bilder: min. 300 DPI empfohlen")
        self.lbl_resolution_hint.setStyleSheet(f"""
            font-size: 7pt;
            color: #f0a030;
            padding: {scale_value(2)}px 0px;
        """)
        self.lbl_resolution_hint.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_resolution_hint.setToolTip(
            "Für optimale Erkennung:\n"
            "• PDF: Wird automatisch bei 500 DPI gerendert\n"
            "• Bilder: Sollten mind. 300 DPI haben\n"
            "• A0-Gleisplan: ca. 10000 x 14000 Pixel\n"
            "• A1-Gleisplan: ca. 7000 x 10000 Pixel"
        )
        pdf_layout.addWidget(self.lbl_resolution_hint)
        pdf_layout.addStretch()  # Anchor widgets to top, prevent vertical shift on resize

        top.addWidget(self.pdf_frame)

        # Step 2: Profile Selection - Compact
        self.profile_frame = self._create_step_frame_compact(
            step_num="02",
            title="PROFIL"
        )
        profile_layout = self.profile_frame.layout()

        self.combo_profile = QtWidgets.QComboBox()
        self.combo_profile.addItems([
            "Wien Schwarz",
            "Wien Farbig",
            "Antwerp"
        ])
        self.combo_profile.setMinimumHeight(scale_value(36))
        self.combo_profile.setStyleSheet("""
            QComboBox {
                font-size: 9pt;
                font-weight: 600;
                padding: 8px 12px;
                border-radius: 8px;
                background: #2c2f3f;
                color: white;
                border: 1px solid #4a4e69;
            }
            QComboBox:hover {
                border-color: #00adef;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #2c2f3f;
                color: white;
                selection-background-color: #00adef;
            }
        """)
        self.combo_profile.setToolTip("Wählen Sie das Erkennungsprofil")
        self.combo_profile.currentIndexChanged.connect(self.on_profile_changed)
        profile_layout.addWidget(self.combo_profile)

        self.lbl_profile = QtWidgets.QLabel("Wien Gleispläne")
        self.lbl_profile.setStyleSheet(f"font-size: 8pt; font-weight: normal; color: #a0a4b8; padding: {scale_value(6)}px 0px;")
        self.lbl_profile.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_profile.setMinimumHeight(scale_value(24))
        self.lbl_profile.setWordWrap(True)
        profile_layout.addWidget(self.lbl_profile)
        profile_layout.addStretch()

        top.addWidget(self.profile_frame)

        # Step 3: Run - Compact
        self.run_frame = self._create_step_frame_compact(
            step_num="03",
            title="AUSFÜHREN"
        )
        run_layout = self.run_frame.layout()

        # OCR is hardcoded to paddleocr (set in __init__) - no UI selector needed

        self.btn_run = QtWidgets.QPushButton("ANALYSE STARTEN")
        self.btn_run.setMinimumHeight(scale_value(40))
        self.btn_run.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_run.setStyleSheet("""
            QPushButton {
                font-size: 10pt;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 10px 16px;
                border-radius: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #00a8b0, stop:1 #009999);
                color: white;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #00c8d0, stop:1 #00b3b3);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #008f97, stop:1 #007f7f);
            }
            QPushButton:disabled { background: #7f8c8d; color: #bdc3c7; }
        """)
        self.btn_run.setToolTip("Startet die automatische Analyse")
        run_layout.addWidget(self.btn_run)

        self.check_force_rerun = QtWidgets.QCheckBox("Vollständige Neuanalyse")
        self.check_force_rerun.setStyleSheet("""
            QCheckBox {
                font-size: 9pt;
                font-weight: 500;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #95a5a6;
                border-radius: 3px;
                background: white;
            }
            QCheckBox::indicator:checked { background: #00a8b0; border: 1px solid #00a8b0; }
            QCheckBox::indicator:hover { border: 1px solid #009999; }
        """)
        self.check_force_rerun.setToolTip("Ignoriert Cache, führt vollständige Neuanalyse durch")
        run_layout.addWidget(self.check_force_rerun)
        run_layout.addStretch()  # Anchor widgets to top, prevent vertical shift on resize

        top.addWidget(self.run_frame)

        # Complete the wrapper layout to center cards
        top_wrapper.addLayout(top)
        top_wrapper.addStretch()  # Push cards to center from right side too

        main_layout.addLayout(top_wrapper)

        # Graphics view - compact preview
        self.view.setMaximumHeight(scale_value(100))
        self.view.setMinimumHeight(60)
        main_layout.addWidget(self.view)

        # Enhanced progress bar (Siemens blue) - visible height, small minimum
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(32)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #cbd5e0;
                border-radius: 12px;
                text-align: center;
                background: white;
                font-size: 10pt;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #009999, stop:1 #00adef);
                border-radius: 10px;
            }
        """)
        main_layout.addWidget(self.progress)

        # Enhanced log output
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.log.setMaximumBlockCount(5000)
        self.log.setMinimumHeight(100)
        self.log.setStyleSheet("""
            QPlainTextEdit {
                background: #2c3e50;
                color: #ecf0f1;
                border: 2px solid #1a252f;
                border-radius: 6px;
                padding: 8px;
                font-size: 18pt;
            }
        """)
        main_layout.addWidget(self.log)

        # Connect button signals
        self.btn_pdf.clicked.connect(self.on_open_pdf)
        self.btn_run.clicked.connect(self.on_run)

        #  NOW create menus and toolbar AFTER all widgets exist
        self._create_menus()
        self._create_toolbar()

        # Update initial button state
        self._update_run_button_state()

        # Apply theme colors to all elements
        self._apply_theme()

        # Show welcome dialog on first launch
        self._maybe_show_welcome_dialog()

    def _create_step_frame_compact(self, step_num: str, title: str) -> QtWidgets.QFrame:
        """Create a compact professional step frame - NO EMOJIS"""
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)

        # Set size policy: expanding horizontally to fill available space
        frame.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Preferred
        )
        # Step cards (DPI-scaled)
        frame.setMinimumWidth(scale_value(250))
        frame.setMaximumWidth(scale_value(450))
        frame.setMinimumHeight(scale_value(160))

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setSpacing(scale_value(10))
        layout.setContentsMargins(scale_value(16), scale_value(16), scale_value(16), scale_value(16))

        # Header: Badge + Title as separate widgets (more reliable than HTML)
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(scale_value(8))
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Badge label (step number)
        badge_label = QtWidgets.QLabel(step_num)
        badge_label.setAlignment(QtCore.Qt.AlignCenter)
        badge_label.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #009999, stop:1 #00adef);
            color: white;
            padding: {scale_value(4)}px {scale_value(10)}px;
            border-radius: {scale_value(4)}px;
            font-size: 9pt;
            font-weight: bold;
        """)
        badge_label.setFixedHeight(scale_value(24))
        header_layout.addWidget(badge_label)

        # Title label
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: 12pt;
            font-weight: bold;
            color: #e8eaf0;
            padding: 0px;
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Add small spacer after header for visual separation
        layout.addSpacing(scale_value(4))

        # Store references for theming
        frame.step_badge = badge_label
        frame.step_title = title_label

        return frame

    def _create_step_frame(self, step_num: str, title: str, icon: str) -> QtWidgets.QFrame:
        """Create a styled frame for each step - colors applied by _apply_theme()"""
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        # Don't set colors here - will be set by _apply_theme()

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setSpacing(scale_value(12))

        # Step number badge
        badge = QtWidgets.QLabel(f"{icon}")
        badge.setStyleSheet("font-size: 32pt; color: #3498db; padding: 5px;")
        badge.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(badge)

        # Step header - store reference for theming
        header = QtWidgets.QLabel(f"Schritt {step_num}")
        header.setStyleSheet("font-size: 10pt; font-weight: normal; padding: 0px;")
        header.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header)
        frame.step_header = header  # Store reference

        # Title - store reference for theming
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 13pt; font-weight: bold; padding: 5px;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title_label)
        frame.step_title = title_label  # Store reference

        # Add separator line - store reference for theming
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("max-height: 1px; margin: 5px 0px;")
        layout.addWidget(line)
        frame.separator_line = line  # Store reference

        return frame

    def _maybe_show_welcome_dialog(self):
        """Show welcome dialog on first launch"""
        settings = QtCore.QSettings("RailDocStudio", "SetupAndRun")
        shown = settings.value("welcome_dialog_shown", False, type=bool)

        if not shown:
            self._show_full_welcome_dialog()
            settings.setValue("welcome_dialog_shown", True)

    def _show_full_welcome_dialog(self):
        """Show detailed welcome dialog"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Willkommen bei RailDoc Studio")
        dialog.setMinimumWidth(scale_value(650))

        layout = QtWidgets.QVBoxLayout(dialog)

        # Title with branding
        title = QtWidgets.QLabel("RailDoc Studio")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel("Gleisplan-Modul v2.0 (Modular)")
        subtitle.setStyleSheet("font-size: 11pt; color: gray; font-style: italic;")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Description
        desc = QtWidgets.QTextEdit()
        desc.setReadOnly(True)
        desc.setHtml("""
        <h3>Was ist RailDoc Studio?</h3>
        <p><b>RailDoc Studio</b> ist eine intelligente Software-Suite zur Analyse von Eisenbahndokumenten.
        Das aktuelle <b>Gleisplan-Modul</b> hilft Ihnen, technische Eisenbahnpläne automatisch zu analysieren:</p>
        <ul>
            <li><b>Symbol-Erkennung:</b> Erkennt automatisch Eisenbahnsymbole wie Weichen, Signale, Kreuzungen usw.</li>
            <li><b>Texterkennung (OCR):</b> Liest Beschriftungen, Koordinaten und andere Textinformationen aus dem Plan</li>
            <li><b>Gleiserkennung:</b> Findet und markiert automatisch die Hauptgleise im Plan</li>
        </ul>

        <h3>Wie verwende ich das Tool?</h3>
        <ol>
            <li><b>Gleisplan laden:</b> Wählen Sie Ihren Gleisplan (PDF oder Bild)</li>
            <li><b>KI-Modell laden:</b> Wählen Sie das trainierte Erkennungsmodell (.pt Datei)</li>
            <li><b>Analyse starten:</b> Klicken Sie auf "Analyse starten" und warten Sie auf die Ergebnisse</li>
        </ol>

        <h3>Nach der Analyse</h3>
        <p>Nach der Analyse öffnet sich automatisch das Bearbeitungsfenster, in dem Sie:</p>
        <ul>
            <li>Erkannte Symbole überprüfen und korrigieren können</li>
            <li>Texte bearbeiten und anpassen können</li>
            <li>Die Daten als Excel exportieren können</li>
            <li>Neue Symbole hinzufügen können (ohne das Modell neu zu trainieren)</li>
        </ul>

        <h3>Zukunft von RailDoc Studio</h3>
        <p><i>Dieses Tool ist modular aufgebaut und kann in Zukunft um weitere Module erweitert werden,
        wie z.B. Signalplan-Analyse, Schaltplan-Erkennung, automatische Routenplanung und mehr.</i></p>

        <hr>
        <p style="text-align: center; font-size: 9pt; color: gray;">
        <b>Entwickelt von:</b> Utkarsh Swain<br>
        Siemens Mobility GmbH | © 2026
        </p>

        <p><i>Hinweis: Die erste Analyse kann einige Minuten dauern. Danach werden die Ergebnisse gespeichert und sind beim nächsten Öffnen sofort verfügbar.</i></p>
        """)
        desc.setMinimumHeight(scale_value(400))
        layout.addWidget(desc)

        # Checkbox to not show again
        dont_show = QtWidgets.QCheckBox("Diese Nachricht nicht mehr anzeigen")
        layout.addWidget(dont_show)

        # OK button
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn_box.accepted.connect(dialog.accept)
        layout.addWidget(btn_box)

        dialog.exec_()

    # drag & drop
    def dragEnterEvent(self, e: QtGui.QDragEnterEvent):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e: QtGui.QDropEvent):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            p_lower = p.lower()
            # Check for Gleisplan files (PDF or images)
            if p_lower.endswith(self.GLEISPLAN_EXTENSIONS):
                self.pdf_path = p
                self.lbl_pdf.setText(f" {os.path.basename(self.pdf_path)}")
                self.lbl_pdf.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
                self.on_status(f"Gleisplan geladen: {os.path.basename(self.pdf_path)}")
                self._display_placeholder("Gleisplan geladen")
                self._add_recent_pdf(p)
                self._update_run_button_state()
                self._update_resolution_warning(p)
        e.acceptProposedAction()

    def _display_placeholder(self, text: str):
        self.scene.clear(); self.current_page_pixmap_item = None
        _, _, _, _, scene_bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(scene_bg))
        pm = QtGui.QPixmap(800, 600); pm.fill(QtGui.QColor(100,100,100))
        self.current_page_pixmap_item = self.scene.addPixmap(pm)
        self.scene.setSceneRect(QtCore.QRectF(pm.rect()))
        t = QtWidgets.QGraphicsSimpleTextItem(text); t.setFont(QtGui.QFont("Arial", 24))
        t.setBrush(QtGui.QBrush(QtGui.QColor("white")))
        t.setPos(pm.width()/2 - t.boundingRect().width()/2, pm.height()/2 - t.boundingRect().height()/2)
        self.scene.addItem(t); self.view.fit_to_view()
    
    # Supported image formats for Gleisplan files
    GLEISPLAN_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')

    def on_open_pdf(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Gleisplan laden", "",
            "Alle Gleispläne (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
            "PDF Dateien (*.pdf);;"
            "Bilder (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;"
            "Alle Dateien (*.*)"
        )
        if fn:
            self.pdf_path = fn
            self.lbl_pdf.setText(f" {os.path.basename(fn)}")
            self.lbl_pdf.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
            self.on_status(f" Gleisplan geladen: {os.path.basename(fn)}")
            self._display_placeholder("Gleisplan geladen")
            self._add_recent_pdf(fn)
            self._update_run_button_state()
            self._update_resolution_warning(fn)

    def on_ocr_changed(self, txt:str): self.ocr_engine = txt; self.on_status(f"OCR-Engine geändert zu: {txt}")

    def on_profile_changed(self, index: int):
        """Handle profile/layout type selection change - also sets the YOLO model automatically."""
        from paths import get_model_path, get_profile_path
        # Each layout type has its own profile and corresponding YOLO model
        profile_map = {
            0: (str(get_profile_path("wien_track_plans.yaml")), "Wien Schwarz", str(get_model_path("wienschwarz.pt"))),
            1: (str(get_profile_path("wien_track_plans.yaml")), "Wien Farbig", str(get_model_path("wienfarbig.pt"))),
            2: (str(get_profile_path("antwerp_track_plans.yaml")), "Antwerp", str(get_model_path("antwerp.pt"))),
        }
        self.profile_path, description, self.model_path = profile_map.get(index, profile_map[0])
        self.lbl_profile.setText(description)
        self.on_status(f"Layout-Typ: {description} (Modell: {os.path.basename(self.model_path)})")

    def _load_profile(self) -> bool:
        """Load the selected profile configuration."""
        try:
            self.layout_config = ProfileManager.load_profile(self.profile_path)
            self.on_status(f"Profil geladen: {self.layout_config.profile_name}")
            return True
        except Exception as e:
            self.on_status(f"Fehler beim Laden des Profils: {e}")
            self.layout_config = None
            return False

    def on_status(self, msg:str):
        ts = time.strftime("%H:%M:%S"); self.log.appendPlainText(f"[{ts}] {msg}")

    def _get_theme_colors(self):
        return self.main_app_ref._get_theme_colors()
    def _load_recent_files(self):
        """Load recent files from settings"""
        try:
            settings = QtCore.QSettings("RailDocStudio", "SetupAndRun")
            self.recent_pdfs = settings.value("recent_pdfs", [])
            self.recent_models = settings.value("recent_models", [])

            # Ensure lists
            if not isinstance(self.recent_pdfs, list):
                self.recent_pdfs = []
            if not isinstance(self.recent_models, list):
                self.recent_models = []
        except Exception:
            self.recent_pdfs = []
            self.recent_models = []

    def _save_recent_files(self):
        """Save recent files to settings"""
        try:
            settings = QtCore.QSettings("RailDocStudio", "SetupAndRun")
            settings.setValue("recent_pdfs", self.recent_pdfs)
            settings.setValue("recent_models", self.recent_models)
        except Exception:
            pass

    def _add_recent_pdf(self, filepath: str):
        """Add PDF to recent files list"""
        if filepath in self.recent_pdfs:
            self.recent_pdfs.remove(filepath)
        self.recent_pdfs.insert(0, filepath)
        self.recent_pdfs = self.recent_pdfs[:self.max_recent]
        self._save_recent_files()
        self._update_recent_files_menu()

    def _add_recent_model(self, filepath: str):
        """Add model to recent files list"""
        if filepath in self.recent_models:
            self.recent_models.remove(filepath)
        self.recent_models.insert(0, filepath)
        self.recent_models = self.recent_models[:self.max_recent]
        self._save_recent_files()

    def _update_recent_files_menu(self):
        """Update recent files menu"""
        if not hasattr(self, 'recent_pdfs_menu'):
            return
        
        self.recent_pdfs_menu.clear()
        
        #  Add defensive check
        if not hasattr(self, 'recent_pdfs') or not self.recent_pdfs:
            act = self.recent_pdfs_menu.addAction("(Keine kürzlich verwendeten Dateien)")
            act.setEnabled(False)
            return
        
        for pdf_path in self.recent_pdfs:
            if os.path.exists(pdf_path):
                act = self.recent_pdfs_menu.addAction(os.path.basename(pdf_path))
                act.setToolTip(pdf_path)
                act.triggered.connect(lambda checked, p=pdf_path: self._open_recent_pdf(p))

    def _open_recent_pdf(self, filepath: str):
        """Open a recent Gleisplan file (PDF or image)"""
        if os.path.exists(filepath):
            self.pdf_path = filepath
            self.lbl_pdf.setText(os.path.basename(filepath))
            self.on_status(f"Gleisplan geladen: {os.path.basename(filepath)}")
            self._display_placeholder("Gleisplan geladen")
            self._update_run_button_state()
            self._update_resolution_warning(filepath)
        else:
            QtWidgets.QMessageBox.warning(self, "Datei nicht gefunden",
                                        f"Die Datei wurde nicht gefunden:\n{filepath}")
            self.recent_pdfs.remove(filepath)
            self._save_recent_files()
            self._update_recent_files_menu()

    def _update_resolution_warning(self, filepath: str):
        """Show/hide resolution warning based on file type"""
        image_extensions = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')
        is_image = filepath.lower().endswith(image_extensions)

        if is_image:
            # Show warning for image files
            self.lbl_resolution_hint.setText(" Bild: min. 300 DPI für optimale Erkennung")
            self.lbl_resolution_hint.setStyleSheet("""
                font-size: 7pt;
                color: #f0a030;
                padding: 2px 0px;
            """)
            self.lbl_resolution_hint.show()
        else:
            # Hide warning for PDFs (they are rendered at 500 DPI automatically)
            self.lbl_resolution_hint.setText(" PDF wird bei 500 DPI gerendert")
            self.lbl_resolution_hint.setStyleSheet("""
                font-size: 7pt;
                color: #60a060;
                padding: 2px 0px;
            """)
            self.lbl_resolution_hint.show()
    # REAL worker wiring (page_ready + done(df_all, overlays))
    def on_run(self):
        if not self.pdf_path:
            QtWidgets.QMessageBox.warning(self, "Fehler: Kein Gleisplan", "Bitte einen Gleisplan auswählen (PDF oder Bild).")
            return

        layout_name = os.path.basename(self.pdf_path)  # Use just filename as layout name
        force_rerun = self.check_force_rerun.isChecked()

        if force_rerun:
            # Force rerun requires model
            if not self.model_path:
                QtWidgets.QMessageBox.warning(self, "Fehler: Kein YOLO Model", "Bitte ein YOLO .pt Model auswählen.")
                return
            self.on_status(" Neu-Analyse erzwungen")
            # Delete existing saved data to start fresh
            try:
                from database_sqlite import delete_workspace_data
                delete_workspace_data(layout_name)
                self.on_status("Alte gespeicherte Daten gelöscht")
            except Exception as e:
                print(f"Could not delete old workspace data: {e}")
            self._run_full_analysis()
        else:
            # Check if saved workspace exists - load from database if so
            try:
                from database_sqlite import get_workspace_data
                result = get_workspace_data(layout_name)
                if result is not None:
                    # Loading from database - no model needed
                    self.on_status(f"Gespeicherte Daten gefunden, rendere Seiten...")
                    # Store workspace data for loading after pages are rendered
                    # Handle old format (3), mid format (5), and new format (6 with profile_name)
                    if len(result) == 3:
                        workspace_data, track_skeleton, image_dimensions = result
                        learned_patterns, uncertain_detections, saved_profile_name = None, [], None
                    elif len(result) == 5:
                        workspace_data, track_skeleton, image_dimensions, learned_patterns, uncertain_detections = result
                        saved_profile_name = None
                    else:
                        workspace_data, track_skeleton, image_dimensions, learned_patterns, uncertain_detections, saved_profile_name = result

                    # Auto-load correct profile for DPI if needed
                    current_profile = getattr(self.layout_config, 'profile_name', None) if self.layout_config else None

                    # If saved profile is different or not loaded, try to auto-load it
                    if saved_profile_name and saved_profile_name != current_profile:
                        try:
                            profile_path = str(get_profile_path(f"{saved_profile_name}.yaml"))
                            if os.path.exists(profile_path):
                                self.layout_config = ProfileManager.load_profile(profile_path)
                                self.on_status(f"Profil '{saved_profile_name}' automatisch geladen für korrekte DPI.")
                                if getattr(self.layout_config, 'debug_database', False):
                                    print(f"DEBUG: Auto-loaded profile '{saved_profile_name}' for correct DPI rendering")
                            else:
                                # Profile file doesn't exist - warn user
                                reply = QtWidgets.QMessageBox.warning(
                                    self,
                                    "Profil-Warnung",
                                    f"Der gespeicherte Arbeitsbereich wurde mit Profil '{saved_profile_name}' erstellt,\n"
                                    f"aber das Profil-Datei konnte nicht gefunden werden.\n"
                                    f"Aktuelles Profil: '{current_profile or 'Keins'}'\n\n"
                                    "Die Bounding-Boxes könnten verschoben sein.\n"
                                    "Möchten Sie trotzdem fortfahren?",
                                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                    QtWidgets.QMessageBox.No
                                )
                                if reply != QtWidgets.QMessageBox.Yes:
                                    return
                        except Exception as e:
                            print(f"Warning: Could not auto-load profile '{saved_profile_name}': {e}")
                            # Show warning but continue
                            reply = QtWidgets.QMessageBox.warning(
                                self,
                                "Profil-Warnung",
                                f"Der gespeicherte Arbeitsbereich wurde mit Profil '{saved_profile_name}' erstellt,\n"
                                f"aber das Profil konnte nicht geladen werden: {e}\n\n"
                                "Die Bounding-Boxes könnten verschoben sein.\n"
                                "Möchten Sie trotzdem fortfahren?",
                                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                QtWidgets.QMessageBox.No
                            )
                            if reply != QtWidgets.QMessageBox.Yes:
                                return

                    self._pending_workspace_data = {
                        'layout_name': layout_name,
                        'data': workspace_data,
                        'track_skeleton': track_skeleton,
                        'image_dimensions': image_dimensions,
                        'learned_patterns': learned_patterns,
                        'uncertain_detections': uncertain_detections or [],
                        'saved_profile_name': saved_profile_name
                    }
                    # Render pages without running analysis
                    self._run_page_rendering_only()
                else:
                    # No saved data - need model for analysis
                    if not self.model_path:
                        QtWidgets.QMessageBox.warning(self, "Fehler: Kein YOLO Model",
                            "Keine gespeicherten Daten gefunden.\nBitte ein YOLO .pt Model auswählen für die Analyse.")
                        return
                    self.on_status("Keine gespeicherten Daten gefunden, starte Analyse...")
                    self._run_full_analysis()
            except Exception as e:
                print(f"Error checking for saved workspace: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to analysis - need model
                if not self.model_path:
                    QtWidgets.QMessageBox.warning(self, "Fehler: Kein YOLO Model", "Bitte ein YOLO .pt Model auswählen.")
                    return
                self._run_full_analysis()

    def _cleanup_worker(self):
        """Clean up worker and disconnect signals to prevent memory leaks and duplicate callbacks"""
        if hasattr(self, 'worker') and self.worker is not None:
            # CRITICAL: Wait for thread to finish before disconnecting signals
            if self.worker.isRunning():
                self.worker.requestInterruption()
                self.worker.quit()
                self.worker.wait(3000)  # Wait up to 3 seconds

            try:
                self.worker.progress.disconnect()
                self.worker.status.disconnect()
                self.worker.page_processed.disconnect()
                self.worker.done.disconnect()
                self.worker.track_detection_progress.disconnect()
            except Exception:
                pass  # Signals may not be connected
            self.worker = None

    def _run_full_analysis(self):
        """Run full YOLO + OCR analysis"""
        # Clean up any previous worker to prevent memory leaks
        self._cleanup_worker()

        self.on_status("Starte vollständige Analyse (YOLO + OCR)...")

        self.started_processing.emit()
        QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
        self.btn_run.setEnabled(False)
        self.act_run.setEnabled(False)
        self.menu_act_run.setEnabled(False)
        self.act_stop.setEnabled(True)
        self.menu_act_stop.setEnabled(True)
        
        self.progress.setValue(0)
        self.log.clear()
        self.scene.clear()
        
        self._page_base_pix.clear()
        self._page_dfs.clear()
        self._page_bgr_arrays.clear()

        # Create and start worker
        # Load the selected profile configuration (required for YOLO detection)
        if not self._load_profile():
            self.on_status("Fehler: Profil konnte nicht geladen werden - Analyse abgebrochen")
            QtWidgets.QMessageBox.critical(
                self, "Profil-Fehler",
                f"Das Profil '{self.profile_path}' konnte nicht geladen werden.\n\n"
                "Die Analyse kann ohne gültiges Profil nicht gestartet werden."
            )
            return

        # Track detection can be disabled per-profile (e.g., Antwerp doesn't need it)
        detect_tracks = self.layout_config.spatial.enable_track_detection if self.layout_config else True

        self.worker = PipelineWorker(
            self.pdf_path,
            self.model_path,
            self.ocr_engine,
            run_analysis=True,
            detect_tracks=detect_tracks,
            config=self.layout_config
        )

        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.on_status)
        self.worker.page_processed.connect(self._on_worker_page_ready)
        self.worker.done.connect(self._on_worker_done)
        self.worker.track_detection_progress.connect(self.on_status)
        self.worker.start()

    def _run_page_rendering_only(self):
        """Render PDF pages without running YOLO analysis (for loading from database)."""
        self._cleanup_worker()

        self.on_status("Rendere Seiten...")

        self.started_processing.emit()
        QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
        self.btn_run.setEnabled(False)
        self.act_run.setEnabled(False)
        self.menu_act_run.setEnabled(False)
        self.act_stop.setEnabled(True)
        self.menu_act_stop.setEnabled(True)

        self.progress.setValue(0)
        self.scene.clear()

        self._page_base_pix.clear()
        self._page_dfs.clear()
        self._page_bgr_arrays.clear()

        # Create worker with run_analysis=False to only render pages
        self.worker = PipelineWorker(
            self.pdf_path,
            self.model_path or "",  # Model not needed for rendering only
            self.ocr_engine,
            run_analysis=False,  # Key: don't run YOLO
            detect_tracks=False,
            config=self.layout_config  # Pass config for DPI and other settings
        )

        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.on_status)
        self.worker.page_processed.connect(self._on_worker_page_ready)
        self.worker.done.connect(self._on_worker_done)
        self.worker.start()

    def _display_page_preview(self, page_num: int):
        """Display a page preview with bounding boxes"""
        if page_num not in self._page_base_pix or page_num not in self._page_dfs:
            return
        
        base_pix = self._page_base_pix[page_num]
        df_page = self._page_dfs[page_num]
        
        self.current_page = page_num
        self.scene.blockSignals(True)
        self.scene.clear()
        
        _, _, _, _, scene_bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(scene_bg))
        self.scene.addPixmap(base_pix)
        self.scene.setSceneRect(QtCore.QRectF(base_pix.rect()))
        
        pen = QtGui.QPen(QtCore.Qt.green, 2)
        text_brush = QtGui.QBrush(QtCore.Qt.black)
        
        for _, row in df_page.iterrows():
            try:
                label = f"{row['cls']} {row.get('conf','')}"
                if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                    label += f" | {row['anchor_text']}"
                
                if isinstance(row.get("poly"), (list, tuple)) and len(row["poly"]) == 4:
                    pts = np.array(row["poly"], dtype=np.float32).reshape(4, 2)
                    it = QtWidgets.QGraphicsPolygonItem(qpolygonf_from_pts(pts))
                    it.setPen(pen)
                    it.setBrush(QtCore.Qt.NoBrush)
                    it.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                    it.setData(0, int(row['row_id']))
                    self.scene.addItem(it)
                    ti = QtWidgets.QGraphicsSimpleTextItem(label)
                    ti.setBrush(text_brush)
                    ti.setPos(float(pts[:, 0].min()), float(pts[:, 1].min()) - 20)
                    ti.setData(0, int(row['row_id']))
                    ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                    self.scene.addItem(ti)
                    continue
                
                if row['cls'] == 'coordinate':
                    x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
                else:
                    x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']
                
                if pd.isna(x1) or x1 is None:
                    continue
                
                r = QtWidgets.QGraphicsRectItem(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                r.setPen(pen)
                r.setBrush(QtCore.Qt.NoBrush)
                r.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                r.setData(0, int(row['row_id']))
                self.scene.addItem(r)
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(int(x1), int(y1) - 20)
                ti.setData(0, int(row['row_id']))
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                self.scene.addItem(ti)
            except Exception:
                continue
        
        self.scene.blockSignals(False)
        self.view.fit_to_view()

    def _on_worker_page_ready(self, pidx: int, bgr_color: np.ndarray, df_page: pd.DataFrame):
        # This function now receives the raw np.ndarray

        # 1. Store the raw array for the AuditingWindow
        self._page_bgr_arrays[pidx] = bgr_color

        # 2. Convert to QPixmap for this window's preview
        rgb = cv2.cvtColor(bgr_color, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        base_img = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888).copy()
        base_pix = QtGui.QPixmap.fromImage(base_img)

        # 3. Store the QPixmap and DataFrame for the AuditingWindow
        self._page_base_pix[pidx] = base_pix
        self._page_dfs[pidx] = df_page.copy()

        # 4. Update this window's live preview (using the QPixmap)
        self.current_page = pidx
        self.scene.blockSignals(True)
        self.scene.clear()
        _, _, _, _, scene_bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(scene_bg))
        self.scene.addPixmap(base_pix)
        self.scene.setSceneRect(QtCore.QRectF(base_pix.rect()))

        pen = QtGui.QPen(QtCore.Qt.green, 2)
        text_brush = QtGui.QBrush(QtCore.Qt.black)

        for _, row in df_page.iterrows():
            try:
                label = f"{row['cls']} {row.get('conf','')}"
                if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                    label += f" | {row['anchor_text']}"

                if isinstance(row.get("poly"), (list, tuple)) and len(row["poly"]) == 4:
                    pts = np.array(row["poly"], dtype=np.float32).reshape(4, 2)
                    it = QtWidgets.QGraphicsPolygonItem(qpolygonf_from_pts(pts))
                    it.setPen(pen)
                    it.setBrush(QtCore.Qt.NoBrush)
                    it.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                    it.setData(0, int(row['row_id']))
                    self.scene.addItem(it)
                    ti = QtWidgets.QGraphicsSimpleTextItem(label)
                    ti.setBrush(text_brush)
                    ti.setPos(float(pts[:, 0].min()), float(pts[:, 1].min()) - 20)
                    ti.setData(0, int(row['row_id']))
                    ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                    self.scene.addItem(ti)
                    continue

                if row['cls'] == 'coordinate':
                    x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
                else:
                    x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']
                if pd.isna(x1) or x1 is None:
                    continue

                r = QtWidgets.QGraphicsRectItem(int(x1), int(y1), int(x2 - x1), int(y2 - y1))
                r.setPen(pen)
                r.setBrush(QtCore.Qt.NoBrush)
                r.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                r.setData(0, int(row['row_id']))
                self.scene.addItem(r)
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(int(x1), int(y1) - 20)
                ti.setData(0, int(row['row_id']))
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                self.scene.addItem(ti)
            except Exception:
                continue

        self.scene.blockSignals(False)
        self.view.fit_to_view()

        # Enable "New Symbol" button now that we have an image
        if hasattr(self, 'act_new_symbol'):
            self.act_new_symbol.setEnabled(True)
        if hasattr(self, 'menu_act_new_symbol'):
            self.menu_act_new_symbol.setEnabled(True)

    def _on_worker_done(self, df_all: pd.DataFrame, page_dfs: Dict[int, pd.DataFrame],
                        track_skeleton: Optional[np.ndarray], exception: Optional[Exception],
                        uncertain_detections: list = None):
        # Guard against race condition: if worker was stopped, ignore this callback
        if not hasattr(self, 'worker') or self.worker is None:
            return

        QtWidgets.QApplication.instance().restoreOverrideCursor()
        self.btn_run.setEnabled(True)
        self.act_run.setEnabled(True)
        self.menu_act_run.setEnabled(True)
        self.act_stop.setEnabled(False)
        self.menu_act_stop.setEnabled(False)

        # Check if we were loading from database (pages rendered, now load saved data)
        if self._pending_workspace_data is not None:
            self.on_status("Lade gespeicherte Daten...")
            pending = self._pending_workspace_data
            self._pending_workspace_data = None  # Clear pending data

            # Convert saved data to DataFrame
            import pandas as pd
            saved_df = pd.DataFrame(pending['data'])

            # DEBUG: Print sample coordinate values from database
            debug_db = getattr(self.layout_config, 'debug_database', False)
            if debug_db and not saved_df.empty:
                sample = saved_df.iloc[0]
                print(f"DEBUG DB LOAD: First row coords - ax1={sample.get('ax1')}, ay1={sample.get('ay1')}, ax2={sample.get('ax2')}, ay2={sample.get('ay2')}")

            # DEBUG: Print image dimensions from re-rendered pages vs saved dimensions
            if debug_db:
                saved_dims = pending.get('image_dimensions', {})
                for page_num, pix in self._page_base_pix.items():
                    re_rendered_w, re_rendered_h = pix.width(), pix.height()
                    saved_w = saved_dims.get(page_num, {}).get('width', 'N/A')
                    saved_h = saved_dims.get(page_num, {}).get('height', 'N/A')
                    print(f"DEBUG DB LOAD: Page {page_num} - Re-rendered: {re_rendered_w}x{re_rendered_h}, Saved: {saved_w}x{saved_h}")
                    if saved_w != 'N/A' and (re_rendered_w != saved_w or re_rendered_h != saved_h):
                        print(f"  WARNING: DIMENSION MISMATCH! This will cause bbox displacement!")

            self.on_status(f"Arbeitsbereich '{pending['layout_name']}' mit {len(saved_df)} Erkennungen geladen!")

            # Copy arrays to prevent reference sharing between workspaces
            page_base_pix_copy = dict(self._page_base_pix) if self._page_base_pix else {}
            page_bgr_arrays_copy = {k: v.copy() if hasattr(v, 'copy') else v
                                    for k, v in self._page_bgr_arrays.items()} if self._page_bgr_arrays else {}

            # Emit with saved data, from_database=True
            self.processing_done.emit(
                saved_df,
                page_base_pix_copy,
                {},  # page_dfs will be rebuilt in workspace widget
                page_bgr_arrays_copy,
                pending['track_skeleton'],
                None,  # No exception
                True,  # from_database=True
                pending.get('uncertain_detections', []),
                pending.get('learned_patterns', None)
            )
        else:
            # Normal analysis completed
            self.on_status("Analyse abgeschlossen.")

            # Copy arrays to prevent reference sharing between workspaces
            page_base_pix_copy = dict(self._page_base_pix) if self._page_base_pix else {}
            page_bgr_arrays_copy = {k: v.copy() if hasattr(v, 'copy') else v
                                    for k, v in self._page_bgr_arrays.items()} if self._page_bgr_arrays else {}

            self.processing_done.emit(df_all, page_base_pix_copy, page_dfs, page_bgr_arrays_copy, track_skeleton, exception, False, uncertain_detections or [], None)  # from_database=False, no learned_patterns for fresh analysis

        # Clean up worker after processing is done to allow running another analysis
        self._cleanup_worker()

    def closeEvent(self, e: QtGui.QCloseEvent):
        if hasattr(self, "worker") and self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.quit()
            self.worker.wait(2000)
        self._cleanup_worker()
        e.accept()
    def _create_toolbar(self):
        """Create streamlined toolbar for Setup window - only essential actions"""
        toolbar = self.addToolBar("Hauptwerkzeuge")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(32, 32))

        # Apply modern toolbar styling (Siemens blue)
        toolbar.setStyleSheet("""
            QToolBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #2f3447, stop:1 #2c3142);
                border-bottom: 2px solid #1a1d2e;
                spacing: 10px;
                padding: 10px;
            }
            QToolButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #3a4255, stop:1 #2f3447);
                border: 1px solid #3a4255;
                border-radius: 8px;
                padding: 8px 16px;
                color: #e8eaf0;
                font-size: 11pt;
                font-weight: 600;
                min-width: 120px;
            }
            QToolButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #454d62, stop:1 #3a4255);
                border: 1px solid #009999;
            }
            QToolButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 #2c3142, stop:1 #242837);
            }
            QToolButton:disabled {
                background: #7f8c8d;
                color: #bdc3c7;
                border: 1px solid #95a5a6;
            }
            QToolBar::separator {
                background: #3a4255;
                width: 3px;
                margin: 8px 10px;
            }
        """)

        # File Actions - Essential for setup
        act_open_pdf = QtWidgets.QAction("Gleisplan öffnen", self)
        act_open_pdf.setToolTip("Gleisplan öffnen\n\nWählen Sie eine Gleisplan-Datei aus (PDF oder Bild)\n\nTastenkürzel: Strg+O")
        act_open_pdf.setShortcut("Ctrl+O")
        act_open_pdf.triggered.connect(self.on_open_pdf)
        toolbar.addAction(act_open_pdf)

        toolbar.addSeparator()

        # Run Action - Main action
        self.act_run = QtWidgets.QAction("Analyse starten", self)
        self.act_run.setToolTip("Analyse starten\n\nStartet die automatische Analyse\ndes Gleisplans\n\nTastenkürzel: F5")
        self.act_run.setShortcut("F5")
        self.act_run.setEnabled(False)
        self.act_run.triggered.connect(self.on_run)
        toolbar.addAction(self.act_run)

        self.act_stop = QtWidgets.QAction("Stoppen", self)
        self.act_stop.setToolTip("Stoppen\n\nStoppt die laufende Analyse\n\nTastenkürzel: Esc")
        self.act_stop.setShortcut("Esc")
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self.on_stop)
        toolbar.addAction(self.act_stop)

        toolbar.addSeparator()

        # Threshold adjustment button
        self.act_thresholds = QtWidgets.QAction("Schwellenwerte", self)
        self.act_thresholds.setToolTip("Schwellenwerte\n\nKonfidenz-Schwellenwerte pro Klasse anpassen\nfür die YOLO-Erkennung")
        self.act_thresholds.triggered.connect(self.on_open_thresholds)
        toolbar.addAction(self.act_thresholds)

        # Add spacer to push next button to the right
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # New Symbol Action - positioned on the right
        self.act_new_symbol = QtWidgets.QAction("Neues Symbol definieren", self)
        self.act_new_symbol.setToolTip("Neues Symbol definieren\n\nDefinieren Sie ein neues Symbol ohne\nYOLO-Modell neu zu trainieren")
        self.act_new_symbol.setEnabled(True)
        self.act_new_symbol.triggered.connect(self.on_add_new_symbol)
        toolbar.addAction(self.act_new_symbol)

        return toolbar  
    
    def _create_menus(self):
        """Create menu bar"""
        mb = self.menuBar()
        
        # File Menu
        file_menu = mb.addMenu("Datei")

        act_open_pdf = file_menu.addAction("Gleisplan öffnen...")
        act_open_pdf.setShortcut("Ctrl+O")
        act_open_pdf.triggered.connect(self.on_open_pdf)

        file_menu.addSeparator()

        act_recent_pdfs = file_menu.addMenu("Kürzlich verwendet")
        self.recent_pdfs_menu = act_recent_pdfs
        self._update_recent_files_menu()

        file_menu.addSeparator()

        act_load_saved = file_menu.addAction("Gespeicherte Arbeit laden...")
        act_load_saved.setShortcut("Ctrl+Shift+O")
        act_load_saved.setToolTip("Einen gespeicherten Arbeitsbereich aus der Datenbank laden")
        act_load_saved.triggered.connect(self._show_saved_workspaces)

        file_menu.addSeparator()

        act_exit = file_menu.addAction("Beenden")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        
        # Process Menu
        process_menu = mb.addMenu("Verarbeitung")

        self.menu_act_run = process_menu.addAction("Analyse starten")
        self.menu_act_run.setShortcut("F5")
        self.menu_act_run.setEnabled(False)
        self.menu_act_run.triggered.connect(self.on_run)

        self.menu_act_stop = process_menu.addAction("Stoppen")
        self.menu_act_stop.setShortcut("Esc")
        self.menu_act_stop.setEnabled(False)
        self.menu_act_stop.triggered.connect(self.on_stop)

        process_menu.addSeparator()

        # NEW: Add New Symbol menu item
        self.menu_act_new_symbol = process_menu.addAction("Neues Symbol definieren...")
        self.menu_act_new_symbol.setToolTip("Neues Symbol ohne Retraining definieren")
        self.menu_act_new_symbol.setEnabled(True)  # Always enabled - can load image in dialog
        self.menu_act_new_symbol.triggered.connect(self.on_add_new_symbol)

        process_menu.addSeparator()

        act_settings = process_menu.addAction("Einstellungen...")
        act_settings.triggered.connect(self.on_show_settings)

        # Tools Menu (Werkzeuge)
        tools_menu = mb.addMenu("Werkzeuge")

        # Confidence Inspector
        act_confidence_inspector = tools_menu.addAction("Konfidenz-Inspektor...")
        act_confidence_inspector.setToolTip("Überprüfung der Erkennungsgenauigkeit")
        act_confidence_inspector.triggered.connect(self._show_confidence_inspector)

        # Quality Inspector
        act_quality_inspector = tools_menu.addAction("Qualitäts-Inspektor...")
        act_quality_inspector.setToolTip("Qualitätskontrolle der erkannten Daten")
        act_quality_inspector.triggered.connect(self._show_quality_inspector)

        tools_menu.addSeparator()

        # Gleisplan Comparison
        act_pdf_compare = tools_menu.addAction("Gleispläne vergleichen...")
        act_pdf_compare.setToolTip("Zwei Gleispläne vergleichen")
        act_pdf_compare.triggered.connect(self._show_pdf_comparison)

        tools_menu.addSeparator()

        # OCR Adjustment
        act_ocr_adjust = tools_menu.addAction("OCR-Anpassung...")
        act_ocr_adjust.setToolTip("Manuelle OCR-Texterkennung anpassen")
        act_ocr_adjust.triggered.connect(self._show_ocr_adjustment)

        tools_menu.addSeparator()

        # Database Manager
        act_db_manager = tools_menu.addAction("Datenbank-Manager...")
        act_db_manager.setToolTip("Gespeicherte Daten und Arbeitsbereiche verwalten")
        act_db_manager.triggered.connect(self._show_database_manager)

        # View Menu
        view_menu = mb.addMenu("Ansicht")
        view_menu.addAction("Dunkles Thema", lambda: self.main_app_ref._set_theme("dark"))
        view_menu.addAction("Helles Thema", lambda: self.main_app_ref._set_theme("light"))
        view_menu.addSeparator()

        act_clear_log = view_menu.addAction("Log löschen")
        act_clear_log.triggered.connect(self.log.clear)

        act_toggle_log = view_menu.addAction("Log ein-/ausblenden")
        act_toggle_log.setCheckable(True)
        act_toggle_log.setChecked(True)
        act_toggle_log.triggered.connect(lambda checked: self.log.setVisible(checked))

        # Help Menu
        help_menu = mb.addMenu("Hilfe")
        help_menu.addAction("Bedienungsanleitung", self._show_help_guide)
        help_menu.addAction("Tastenkombinationen", self._show_keyboard_shortcuts)
        help_menu.addSeparator()
        help_menu.addAction("Über", self._show_about)
        
    def on_show_settings(self):
        """Show advanced settings dialog"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Erweiterte Einstellungen")
        dialog.setMinimumWidth(scale_value(400))
        
        layout = QtWidgets.QFormLayout(dialog)
        
        # OCR Engine Selection
        ocr_label = QtWidgets.QLabel("OCR Engine:")
        ocr_combo = QtWidgets.QComboBox()
        ocr_combo.addItems(["paddleocr", "easyocr", "tesseract"])
        ocr_combo.setCurrentText(self.ocr_engine)
        layout.addRow(ocr_label, ocr_combo)
        
        # Confidence Threshold
        conf_label = QtWidgets.QLabel("Minimale Konfidenz (YOLO):")
        conf_spin = QtWidgets.QDoubleSpinBox()
        conf_spin.setRange(0.0, 1.0)
        conf_spin.setSingleStep(0.05)
        conf_spin.setValue(0.25)  # Default YOLO confidence
        conf_spin.setToolTip("YOLO-Erkennungen unter diesem Schwellenwert werden verworfen")
        layout.addRow(conf_label, conf_spin)
        
        # IOU Threshold
        iou_label = QtWidgets.QLabel("IOU-Schwellenwert (NMS):")
        iou_spin = QtWidgets.QDoubleSpinBox()
        iou_spin.setRange(0.0, 1.0)
        iou_spin.setSingleStep(0.05)
        iou_spin.setValue(0.45)  # Default NMS IOU
        iou_spin.setToolTip("Überlappungsschwelle für Non-Maximum Suppression")
        layout.addRow(iou_label, iou_spin)
        
        # Processing Options
        group_box = QtWidgets.QGroupBox("Verarbeitungsoptionen")
        group_layout = QtWidgets.QVBoxLayout(group_box)
        
        check_enhance = QtWidgets.QCheckBox("Bildverbesserung aktivieren")
        check_enhance.setChecked(True)
        check_enhance.setToolTip("Kontrast und Helligkeit vor OCR optimieren")
        group_layout.addWidget(check_enhance)
        
        check_parallel = QtWidgets.QCheckBox("Parallele Verarbeitung (experimentell)")
        check_parallel.setChecked(False)
        check_parallel.setToolTip("Mehrere Seiten gleichzeitig verarbeiten")
        group_layout.addWidget(check_parallel)
        
        check_save_debug = QtWidgets.QCheckBox("Debug-Bilder speichern")
        check_save_debug.setChecked(False)
        check_save_debug.setToolTip("Zwischenschritte als Bilder speichern")
        group_layout.addWidget(check_save_debug)
        
        layout.addRow(group_box)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)
        
        # Show dialog
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Apply settings
            self.ocr_engine = ocr_combo.currentText()
            self.combo_ocr.setCurrentText(self.ocr_engine)
            
            # Store other settings (you can add instance variables for these)
            self.yolo_conf_threshold = conf_spin.value()
            self.yolo_iou_threshold = iou_spin.value()
            self.enable_enhancement = check_enhance.isChecked()
            self.enable_parallel = check_parallel.isChecked()
            self.save_debug_images = check_save_debug.isChecked()
            
            self.on_status(f"Einstellungen aktualisiert: OCR={self.ocr_engine}, Conf={self.yolo_conf_threshold:.2f}")
            
    def on_stop(self):
        """Stop the running analysis"""
        if hasattr(self, "worker") and self.worker is not None and self.worker.isRunning():
            reply = QtWidgets.QMessageBox.question(
                self,
                "Analyse stoppen",
                "Möchten Sie die laufende Analyse wirklich abbrechen?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.Yes:
                self.worker.requestInterruption()
                self.worker.quit()
                self.worker.wait(2000)

                # Clean up worker and disconnect signals
                self._cleanup_worker()

                # Clear partial data from interrupted analysis
                self._page_base_pix.clear()
                self._page_dfs.clear()
                self._page_bgr_arrays.clear()

                # Reset page state
                self.current_page = 0

                # Clear scene
                self.scene.clear()

                QtWidgets.QApplication.restoreOverrideCursor()
                self.btn_run.setEnabled(True)
                self.act_run.setEnabled(True)
                self.menu_act_run.setEnabled(True)
                self.act_stop.setEnabled(False)
                self.menu_act_stop.setEnabled(False)

                self.on_status("Analyse abgebrochen")
                self.statusBar().showMessage("Analyse wurde abgebrochen")
    def _update_run_button_state(self):
        """Enable/disable run button based on whether PDF is loaded.

        Model is optional - if no model but saved data exists in database,
        the workspace can still be loaded without running analysis.
        """
        can_run = self.pdf_path is not None
        self.btn_run.setEnabled(can_run)
        if hasattr(self, 'act_run'):
            self.act_run.setEnabled(can_run)
        if hasattr(self, 'menu_act_run'):
            self.menu_act_run.setEnabled(can_run)
            
    def _show_help_guide(self):
        """Show help guide for Setup & Run window"""
        help_text = """
        <h2>Setup & Run - Bedienungsanleitung</h2>

        <h3>Übersicht</h3>
        <p>Dieses Tool analysiert automatisch Ihre Gleispläne und extrahiert wichtige Informationen.
        Die Analyse umfasst Symbol-Erkennung, Texterkennung (OCR) und automatische Gleiserkennung.</p>

        <h3>Schritt 1: Gleisplan laden</h3>
        <ul>
            <li>Klicken Sie auf "Gleisplan öffnen" oder drücken Sie <b>Strg+O</b></li>
            <li>Oder ziehen Sie eine Gleisplan-Datei (PDF oder Bild) per Drag & Drop ins Fenster</li>
            <li>Unterstützte Formate: PDF, PNG, JPEG, TIFF, BMP</li>
            <li>Kürzlich verwendete Dateien finden Sie unter Datei → Kürzlich verwendet</li>
        </ul>

        <h3>Schritt 2: KI-Modell laden</h3>
        <ul>
            <li>Klicken Sie auf "Modell laden" oder drücken Sie <b>Strg+M</b></li>
            <li>Wählen Sie Ihre trainierte .pt-Modelldatei</li>
            <li>Dieses Modell wurde trainiert, um Eisenbahnsymbole zu erkennen</li>
        </ul>

        <h3>Schritt 3: Analyse starten</h3>
        <ul>
            <li><b>Texterkennung (OCR):</b> Verwendet automatisch PaddleOCR für beste Ergebnisse</li>
            <li><b>Vollständige Neu-Analyse:</b> Aktivieren Sie diese Option, um gespeicherte Daten zu ignorieren</li>
            <li>Drücken Sie <b>F5</b> oder klicken Sie auf "Analyse starten"</li>
            <li>Der Fortschritt wird in Echtzeit angezeigt</li>
        </ul>

        <h3>Automatische Funktionen</h3>
        <ul>
            <li><b>Symbol-Erkennung:</b> Erkennt automatisch Weichen, Signale, Kreuzungen usw.</li>
            <li><b>Texterkennung:</b> Liest Beschriftungen und Koordinaten aus dem Plan</li>
            <li><b>Gleiserkennung:</b> Findet und markiert automatisch die Hauptgleise (immer aktiviert)</li>
        </ul>

        <h3>Analyse stoppen</h3>
        <ul>
            <li>Mit <b>Esc</b> oder "Stoppen" können Sie die Analyse jederzeit abbrechen</li>
        </ul>

        <h3>Vorschau & Navigation</h3>
        <ul>
            <li>Während der Verarbeitung sehen Sie eine Live-Vorschau der aktuellen Seite</li>
            <li>Zoomen mit <b>Strg+Mausrad</b> oder den Toolbar-Buttons</li>
            <li>Verschieben durch Ziehen mit der Maus</li>
        </ul>

        <h3>Erweiterte Einstellungen</h3>
        <p>Über "Verarbeitung → Einstellungen" können Sie:</p>
        <ul>
            <li>Konfidenz-Schwellenwerte für die Symbol-Erkennung anpassen</li>
            <li>Bildverbesserung aktivieren/deaktivieren</li>
            <li>Debug-Optionen einstellen</li>
        </ul>

        <h3>Qualitätskontrolle & Werkzeuge</h3>
        <p>Im Menü <b>"Werkzeuge"</b> finden Sie nützliche Analyse-Tools:</p>
        <ul>
            <li><b>Konfidenz-Inspektor:</b> Überprüfen Sie die Erkennungsgenauigkeit aller Objekte.
            Zeigt Statistiken über Confidence-Werte und hilft, problematische Erkennungen zu identifizieren.</li>

            <li><b>Qualitäts-Inspektor:</b> Umfassende Qualitätsanalyse der erkannten Daten.
            Identifiziert potenzielle Fehler, fehlende Daten und Inkonsistenzen.</li>

            <li><b>Gleispläne vergleichen:</b> Vergleichen Sie zwei Gleispläne, um Unterschiede zu identifizieren.
            Nützlich für Versionskontrolle und Change-Management.</li>

            <li><b>OCR-Anpassung:</b> Manuelle Korrektur von OCR-Erkennungen für bessere Textqualität.</li>
        </ul>

        <h3>Nach der Analyse</h3>
        <p>Nach erfolgreicher Analyse öffnet sich das Bearbeitungsfenster, in dem Sie die erkannten Daten
        überprüfen, korrigieren und als Excel exportieren können.</p>

        <p><b>Tipp:</b> Nutzen Sie die Qualitätskontroll-Werkzeuge, um die Analyse-Ergebnisse zu überprüfen,
        bevor Sie mit der manuellen Bearbeitung beginnen.</p>
        """

        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Bedienungsanleitung - Setup & Run", help_text, self)
        help_dialog.exec_()

    def _show_keyboard_shortcuts(self):
        """Show keyboard shortcuts for Setup & Run window"""
        shortcuts_text = """
        <h2>Tastenkombinationen - Setup & Run</h2>
        
        <table border="1" cellpadding="5">
            <tr><th>Aktion</th><th>Tastenkombination</th></tr>
            <tr><td>Gleisplan öffnen</td><td><b>Strg+O</b></td></tr>
            <tr><td>Modell laden</td><td><b>Strg+M</b></td></tr>
            <tr><td>Analyse starten</td><td><b>F5</b></td></tr>
            <tr><td>Analyse stoppen</td><td><b>Esc</b></td></tr>
            <tr><td>Beenden</td><td><b>Strg+Q</b></td></tr>
            <tr><td>Zoom In</td><td><b>Strg++</b></td></tr>
            <tr><td>Zoom Out</td><td><b>Strg+-</b></td></tr>
            <tr><td>An Ansicht anpassen</td><td><b>Strg+0</b></td></tr>
        </table>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Tastenkombinationen - Setup & Run", shortcuts_text, self)
        help_dialog.exec_()

    def _show_about(self):
        """Show about dialog for Setup & Run window"""
        about_text = """
        <div style="text-align: center;">
            <h2>RailDoc Studio</h2>
            <h3>Gleisplan-Modul</h3>
            <p><b>Version:</b> 2.0 (Modular)</p>
        </div>

        <hr>

        <p><b>Über dieses Modul:</b></p>
        <p>Das Gleisplan-Modul ermöglicht das Laden und Verarbeiten von Gleisplänen (PDF und Bilder)
        mit KI-basierter Objekterkennung (YOLO), Multi-Engine OCR und automatischer Gleiserkennung.</p>

        <p><b>Technologien:</b></p>
        <ul>
            <li>YOLO v8/v11 für Symbol-Erkennung</li>
            <li>PaddleOCR / EasyOCR / Tesseract für Texterkennung</li>
            <li>Computer Vision für Gleiserkennung</li>
            <li>PyQt5 für die Benutzeroberfläche</li>
        </ul>

        <hr>

        <p style="text-align: center;">
        <b>Entwickelt von:</b> Utkarsh Swain<br>
        <b>Organisation:</b> Siemens Mobility GmbH<br>
        <i>© 2026 - Siemens Mobility GmbH</i>
        </p>

        <p style="text-align: center; font-size: 9pt; color: gray;">
        <i>RailDoc Studio ist eine erweiterbare Software-Suite zur<br>
        intelligenten Analyse von Eisenbahndokumenten.</i>
        </p>
        """

        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Über RailDoc Studio", about_text, self)
        help_dialog.exec_()

    def _show_confidence_inspector(self):
        """Show confidence inspector dialog"""
        if not self._page_dfs:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Bitte führen Sie zuerst eine Analyse durch."
            )
            return

        try:
            from ui.confidence_inspector import ConfidenceInspectorDialog

            # Combine all page dataframes
            all_data = []
            for df in self._page_dfs.values():
                all_data.append(df)

            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                dialog = ConfidenceInspectorDialog(combined_df, self)
                dialog.exec_()
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine Daten",
                    "Keine Erkennungsdaten gefunden."
                )

        except ImportError as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Modul nicht gefunden",
                f"Konfidenz-Inspektor konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Konfidenz-Inspektors:\n{str(e)}"
            )

    def _show_quality_inspector(self):
        """Show quality inspector dialog"""
        if not self._page_dfs:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Bitte führen Sie zuerst eine Analyse durch."
            )
            return

        try:
            from ui.quality_inspector import QualityInspectorDialog

            # Combine all page dataframes
            all_data = []
            for df in self._page_dfs.values():
                all_data.append(df)

            if all_data:
                combined_df = pd.concat(all_data, ignore_index=True)
                dialog = QualityInspectorDialog(combined_df, self)
                dialog.exec_()
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine Daten",
                    "Keine Erkennungsdaten gefunden."
                )

        except ImportError as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Modul nicht gefunden",
                f"Qualitäts-Inspektor konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Qualitäts-Inspektors:\n{str(e)}"
            )

    def _show_pdf_comparison(self):
        """Show Gleisplan comparison dialog"""
        try:
            from pdfcomparison.dialogs import PDFComparisonDialog

            dialog = PDFComparisonDialog(self)
            dialog.exec_()

        except ImportError as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Modul nicht gefunden",
                f"Gleisplan-Vergleich konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Gleisplan-Vergleichs:\n{str(e)}"
            )

    def _show_ocr_adjustment(self):
        """Show OCR adjustment dialog"""
        if not self._page_bgr_arrays or not self._page_dfs:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Bitte führen Sie zuerst eine Analyse durch."
            )
            return

        try:
            from ui.ocr_adjustment_dialog import OCRAdjustmentDialog

            # Use current page
            current_page = self.current_page if self.current_page in self._page_bgr_arrays else list(self._page_bgr_arrays.keys())[0]

            dialog = OCRAdjustmentDialog(
                self._page_bgr_arrays[current_page],
                self._page_dfs[current_page],
                self
            )

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Update the dataframe with adjusted text
                self._page_dfs[current_page] = dialog.get_adjusted_dataframe()
                self.on_status("OCR-Anpassungen übernommen")

        except ImportError as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Modul nicht gefunden",
                f"OCR-Anpassung konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen der OCR-Anpassung:\n{str(e)}"
            )

    def _show_saved_workspaces(self):
        """Show dialog to load a saved workspace from database."""
        try:
            dialog = SavedWorkspacesDialog(self)
            dialog.workspace_selected.connect(self._on_load_saved_workspace)
            dialog.exec_()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen der gespeicherten Arbeitsbereiche:\n{str(e)}"
            )

    def _show_database_manager(self):
        """Show full database manager dialog."""
        try:
            dialog = DatabaseManagerDialog(self)
            dialog.workspace_selected.connect(self._on_load_saved_workspace)
            dialog.exec_()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Datenbank-Managers:\n{str(e)}"
            )

    def _on_load_saved_workspace(self, layout_name: str):
        """Handle loading a saved workspace from database."""
        # Check if analysis is currently running
        if hasattr(self, 'worker') and self.worker is not None and self.worker.isRunning():
            QtWidgets.QMessageBox.warning(
                self,
                "Analyse läuft",
                "Bitte stoppen Sie zuerst die laufende Analyse."
            )
            return

        try:
            from database_sqlite import get_workspace_data

            self.on_status(f"Lade gespeicherten Arbeitsbereich: {layout_name}")

            result = get_workspace_data(layout_name)
            if result is None:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Nicht gefunden",
                    f"Arbeitsbereich '{layout_name}' nicht in der Datenbank gefunden."
                )
                return

            # Handle old format (3 values), mid format (5 values), and new format (6 with profile_name)
            if len(result) == 3:
                workspace_data, track_skeleton, image_dimensions = result
                learned_patterns, uncertain_detections, saved_profile_name = None, [], None
            elif len(result) == 5:
                workspace_data, track_skeleton, image_dimensions, learned_patterns, uncertain_detections = result
                uncertain_detections = uncertain_detections or []
                saved_profile_name = None
            else:
                workspace_data, track_skeleton, image_dimensions, learned_patterns, uncertain_detections, saved_profile_name = result
                uncertain_detections = uncertain_detections or []

            # Check for profile mismatch and auto-load correct profile for DPI
            current_profile = getattr(self.layout_config, 'profile_name', None) if self.layout_config else None

            # If saved profile is different or not loaded, try to load the correct profile
            if saved_profile_name and saved_profile_name != current_profile:
                try:
                    profile_path = str(get_profile_path(f"{saved_profile_name}.yaml"))
                    if os.path.exists(profile_path):
                        self.layout_config = ProfileManager.load_profile(profile_path)
                        self.on_status(f"Profil '{saved_profile_name}' automatisch geladen für korrekte DPI.")
                        if getattr(self.layout_config, 'debug_database', False):
                            print(f"DEBUG: Auto-loaded profile '{saved_profile_name}' for correct DPI rendering")
                    else:
                        # Show warning only if profile file doesn't exist
                        reply = QtWidgets.QMessageBox.warning(
                            self,
                            "Profil-Warnung",
                            f"Der Arbeitsbereich wurde mit Profil '{saved_profile_name}' erstellt,\n"
                            f"aber das Profil konnte nicht geladen werden.\n"
                            f"Aktuelles Profil: '{current_profile or 'Keins'}'\n\n"
                            "Die Bounding-Boxes könnten verschoben sein.\n"
                            "Möchten Sie trotzdem fortfahren?",
                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                            QtWidgets.QMessageBox.No
                        )
                        if reply != QtWidgets.QMessageBox.Yes:
                            return
                except Exception as e:
                    print(f"Warning: Could not auto-load profile '{saved_profile_name}': {e}")
                    # Show warning about potential mismatch
                    reply = QtWidgets.QMessageBox.warning(
                        self,
                        "Profil-Warnung",
                        f"Der Arbeitsbereich wurde mit Profil '{saved_profile_name}' erstellt,\n"
                        f"aber das Profil konnte nicht geladen werden: {e}\n\n"
                        "Die Bounding-Boxes könnten verschoben sein.\n"
                        "Möchten Sie trotzdem fortfahren?",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.No
                    )
                    if reply != QtWidgets.QMessageBox.Yes:
                        return

            # ALWAYS store pending data and re-render to ensure correct cropping
            # This is necessary because existing pages may have been rendered
            # with a different profile's crop settings
            self._pending_workspace_data = {
                'layout_name': layout_name,
                'data': workspace_data,
                'track_skeleton': track_skeleton,
                'image_dimensions': image_dimensions,
                'learned_patterns': learned_patterns,
                'uncertain_detections': uncertain_detections,
                'saved_profile_name': saved_profile_name
            }

            # Check if the correct PDF is already loaded
            if not self.pdf_path or os.path.basename(self.pdf_path) != layout_name:
                QtWidgets.QMessageBox.information(
                    self,
                    "PDF erforderlich",
                    f"Bitte laden Sie zuerst die zugehörige PDF-Datei:\n\n{layout_name}\n\n"
                    "Die gespeicherten Daten werden dann automatisch geladen."
                )
                return

            # Re-render pages to ensure correct cropping is applied
            self.on_status("Rendere Seiten mit korrektem Zuschnitt...")
            self._run_page_rendering_only()

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Laden des Arbeitsbereichs:\n{str(e)}"
            )

    def on_open_thresholds(self):
        """Open the Threshold Dialog to adjust confidence thresholds per class."""
        from ui.threshold_dialog import ThresholdDialog

        dialog = ThresholdDialog(self)
        dialog.exec_()

    def on_add_new_symbol(self):
        """Open the New Symbol Dialog to define a new symbol without retraining YOLO."""
        import cv2

        current_page_bgr = None

        # Check if we have an image loaded
        if self._page_bgr_arrays:
            # Get the current page's BGR array
            current_page_bgr = self._page_bgr_arrays.get(self.current_page)
            if current_page_bgr is None and self._page_bgr_arrays:
                current_page_bgr = list(self._page_bgr_arrays.values())[0]

        # If no image available, offer to load one directly
        if current_page_bgr is None:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Kein Bild geladen",
                "Kein Bild verfügbar. Möchten Sie ein Bild direkt laden?\n\n"
                "(Sie können später weitere Bilder im Dialog hinzufügen)",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.No:
                return

            # Open file dialog to load an image
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Bild für Symbol-Definition laden",
                "",
                "Bilder (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;PDF Dateien (*.pdf);;Alle Dateien (*.*)"
            )

            if not file_path:
                return

            # Load the image
            if file_path.lower().endswith('.pdf'):
                # For PDF, load the first page
                try:
                    import fitz
                    doc = fitz.open(file_path)
                    page = doc[0]
                    pix = page.get_pixmap(dpi=500)  # Match main pipeline DPI
                    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    if pix.n == 4:  # RGBA
                        current_page_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
                    else:  # RGB
                        current_page_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                    doc.close()
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Fehler", f"Datei konnte nicht geladen werden:\n{e}")
                    return
            else:
                current_page_bgr = cv2.imread(file_path)

            if current_page_bgr is None:
                QtWidgets.QMessageBox.warning(self, "Fehler", f"Bild konnte nicht geladen werden:\n{file_path}")
                return

        try:
            from ui.new_symbol_dialog import NewSymbolDialog

            dialog = NewSymbolDialog(current_page_bgr, self)
            result = dialog.exec_()

            if result == QtWidgets.QDialog.Accepted:
                self.on_status("Neues Symbol erfolgreich definiert!")
                self.on_status("Das Symbol wird bei der nächsten Analyse automatisch erkannt.")
            else:
                self.on_status("Symbol-Definition abgebrochen.")

        except ImportError as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Modul nicht gefunden",
                f"Das Modul 'new_symbol_dialog' konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Symbol-Dialogs:\n{str(e)}"
            )