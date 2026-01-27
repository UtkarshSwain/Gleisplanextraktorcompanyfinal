# ============================================================================
# RailDoc Studio - Setup & Analyse Modul
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2025
# ============================================================================
from PyQt5 import QtCore, QtGui, QtWidgets
from ui.graphics_view import InteractiveGraphicsView
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import pandas as pd
import os
from pdfcomparison.dialogs import HelpDialog
from core.pipelineworker import PipelineWorker
import time
import cv2
from core.image_processing import qpolygonf_from_pts

# ============================================================================
# IMPORT POPPLER PATH FROM CONFIG
# ============================================================================
from config import POPPLER_PATH, TESSERACT_PATH

# -------- Setup & Run (connects to REAL PipelineWorker signals) --------
class SetupAndRunWindow(QtWidgets.QMainWindow):
    processing_done = QtCore.pyqtSignal(pd.DataFrame, object, object, object, object, object)  # df_all, page_base_pix, page_dfs, page_bgr_arrays, exception    started_processing = QtCore.pyqtSignal()
    started_processing = QtCore.pyqtSignal()
    def __init__(self, main_app_ref: 'MainWindow'):
        from main import MainWindow
        super().__init__()
        self.main_app_ref = main_app_ref
        self.setWindowTitle("RailDoc Studio - Setup & Analyse")
        self.resize(1000, 800)
        self.pdf_path = None; self.model_path = None; self.ocr_engine = "paddleocr"
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

                # Update step header color
                if hasattr(frame, 'step_header'):
                    frame.step_header.setStyleSheet(f"""
                        font-size: 10pt;
                        font-weight: normal;
                        color: {self.theme_colors['text_secondary']};
                        padding: 0px;
                    """)

                # Update step title color
                if hasattr(frame, 'step_title'):
                    frame.step_title.setStyleSheet(f"""
                        font-size: 11pt;
                        font-weight: 700;
                        letter-spacing: 0.5px;
                        color: {self.theme_colors['text_primary']};
                    """)

        # Update info banner (compact with Siemens blue accent)
        if hasattr(self, 'analysis_info'):
            self.analysis_info.setStyleSheet(f"""
                background: {self.theme_colors['info_bg']};
                color: {self.theme_colors['text_primary']};
                padding: 10px 16px;
                border-radius: 8px;
                font-size: 9pt;
                font-weight: 600;
                letter-spacing: 0.5px;
                border: 1px solid {self.theme_colors['border']};
                border-left: 3px solid {self.theme_colors['siemens_blue']};
            """)

        # Update status labels if they haven't been set yet (muted style)
        if hasattr(self, 'lbl_pdf') and "Keine Datei" in self.lbl_pdf.text():
            self.lbl_pdf.setStyleSheet(f"""
                color: {self.theme_colors['text_secondary']};
                font-size: 8pt;
                font-weight: normal;
                padding: 8px 0px;
            """)

        if hasattr(self, 'lbl_model') and "Kein Modell" in self.lbl_model.text():
            self.lbl_model.setStyleSheet(f"""
                color: {self.theme_colors['text_secondary']};
                font-size: 8pt;
                font-weight: normal;
                padding: 8px 0px;
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
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ========== COMPACT PROFESSIONAL HEADER ==========
        self.module_header = QtWidgets.QFrame()
        header_layout = QtWidgets.QHBoxLayout(self.module_header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

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
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)

        # Step 1: Gleisplan - Compact professional design
        self.pdf_frame = self._create_step_frame_compact(
            step_num="01",
            title="GLEISPLAN"
        )
        pdf_layout = self.pdf_frame.layout()

        self.btn_pdf = QtWidgets.QPushButton("DURCHSUCHEN")
        self.btn_pdf.setMinimumHeight(36)
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
        self.lbl_pdf.setStyleSheet("font-size: 8pt; font-weight: normal; color: #a0a4b8; padding: 8px 0px;")
        self.lbl_pdf.setAlignment(QtCore.Qt.AlignCenter)
        pdf_layout.addWidget(self.lbl_pdf)

        # Resolution warning for image files
        self.lbl_resolution_hint = QtWidgets.QLabel("⚠ Bilder: min. 300 DPI empfohlen")
        self.lbl_resolution_hint.setStyleSheet("""
            font-size: 7pt;
            color: #f0a030;
            padding: 2px 0px;
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

        top.addWidget(self.pdf_frame)

        # Step 2: Model - Compact
        self.model_frame = self._create_step_frame_compact(
            step_num="02",
            title="KI-MODELL"
        )
        model_layout = self.model_frame.layout()

        self.btn_model = QtWidgets.QPushButton("DURCHSUCHEN")
        self.btn_model.setMinimumHeight(36)
        self.btn_model.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.btn_model.setStyleSheet("""
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
        self.btn_model.setToolTip("Wählen Sie das KI-Modell (.pt Datei)")
        model_layout.addWidget(self.btn_model)

        # Compact status
        self.lbl_model = QtWidgets.QLabel("Kein Modell")
        self.lbl_model.setStyleSheet("font-size: 8pt; font-weight: normal; color: #a0a4b8; padding: 8px 0px;")
        self.lbl_model.setAlignment(QtCore.Qt.AlignCenter)
        model_layout.addWidget(self.lbl_model)

        top.addWidget(self.model_frame)

        # Step 3: Run - Compact
        self.run_frame = self._create_step_frame_compact(
            step_num="03",
            title="AUSFÜHREN"
        )
        run_layout = self.run_frame.layout()

        # OCR is hardcoded to paddleocr (set in __init__) - no UI selector needed

        self.btn_run = QtWidgets.QPushButton("ANALYSE STARTEN")
        self.btn_run.setMinimumHeight(40)
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

        top.addWidget(self.run_frame)

        main_layout.addLayout(top)

        # Compact info banner - no emoji
        self.analysis_info = QtWidgets.QLabel(
            "AUTOMATISCH: Symbol-Erkennung | Texterkennung | Gleiserkennung"
        )
        self.analysis_info.setStyleSheet("padding: 8px; border-radius: 2px; font-size: 9pt; font-weight: 600; letter-spacing: 0.5px;")
        self.analysis_info.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(self.analysis_info)

        # Graphics view - very small compact preview so step cards dominate the layout
        self.view.setMaximumHeight(150)
        self.view.setMinimumHeight(120)
        main_layout.addWidget(self.view)

        # Enhanced progress bar (Siemens blue) - increased height for better visibility
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(50)
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
        self.log.setMinimumHeight(150)
        self.log.setStyleSheet("""
            QPlainTextEdit {
                background: #2c3e50;
                color: #ecf0f1;
                border: 2px solid #1a252f;
                border-radius: 6px;
                padding: 8px;
                font-size: 9pt;
            }
        """)
        main_layout.addWidget(self.log)

        # Connect button signals
        self.btn_pdf.clicked.connect(self.on_open_pdf)
        self.btn_model.clicked.connect(self.on_select_model)
        self.btn_run.clicked.connect(self.on_run)

        # ✅ NOW create menus and toolbar AFTER all widgets exist
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

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header: Badge + Title on same line
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(8)

        # Small badge on left
        step_badge = QtWidgets.QLabel(step_num)
        step_badge.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                       stop:0 #009999, stop:1 #00adef);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 8pt;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        header_layout.addWidget(step_badge)

        # Title next to badge
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet("font-size: 11pt; font-weight: 700; letter-spacing: 0.5px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        frame.step_title = title_label  # Store reference for theming

        layout.addLayout(header_layout)

        return frame

    def _create_step_frame(self, step_num: str, title: str, icon: str) -> QtWidgets.QFrame:
        """Create a styled frame for each step - colors applied by _apply_theme()"""
        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.StyledPanel | QtWidgets.QFrame.Raised)
        # Don't set colors here - will be set by _apply_theme()

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setSpacing(12)

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
        dialog.setMinimumWidth(650)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Title with branding
        title = QtWidgets.QLabel("RailDoc Studio")
        title.setStyleSheet("font-size: 18pt; font-weight: bold;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QtWidgets.QLabel("Gleisplan-Modul v1.0")
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
        Siemens Mobility GmbH | © 2025
        </p>

        <p><i>Hinweis: Die erste Analyse kann einige Minuten dauern. Danach werden die Ergebnisse gespeichert und sind beim nächsten Öffnen sofort verfügbar.</i></p>
        """)
        desc.setMinimumHeight(400)
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
                self.lbl_pdf.setText(f"✓ {os.path.basename(self.pdf_path)}")
                self.lbl_pdf.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
                self.on_status(f"Gleisplan geladen: {os.path.basename(self.pdf_path)}")
                self._display_placeholder("Gleisplan geladen")
                self._add_recent_pdf(p)
                self._update_run_button_state()
                self._update_resolution_warning(p)
            elif p_lower.endswith(".pt"):
                self.model_path = p
                self.lbl_model.setText(f"✓ {os.path.basename(self.model_path)}")
                self.lbl_model.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
                self.on_status(f"Modell geladen: {os.path.basename(self.model_path)}")
                self._add_recent_model(p)
                self._update_run_button_state()
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
            self.lbl_pdf.setText(f"✓ {os.path.basename(fn)}")
            self.lbl_pdf.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
            self.on_status(f"✓ Gleisplan geladen: {os.path.basename(fn)}")
            self._display_placeholder("Gleisplan geladen")
            self._add_recent_pdf(fn)
            self._update_run_button_state()
            self._update_resolution_warning(fn)
    def on_select_model(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Auswählen von YOLO .pt", "", "PyTorch Weights (*.pt)")
        if fn:
            self.model_path = fn
            self.lbl_model.setText(f"✓ {os.path.basename(fn)}")
            self.lbl_model.setStyleSheet("color: #00a8b0; font-weight: 600; font-size: 9pt;")
            self.on_status(f"✓ Modell geladen: {os.path.basename(fn)}")
            self._add_recent_model(fn)  # ✅ Track recent file
            self._update_run_button_state()  # ✅ Update button state
    def on_ocr_changed(self, txt:str): self.ocr_engine = txt; self.on_status(f"OCR-Engine geändert zu: {txt}")
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
        
        # ✅ Add defensive check
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
            self.lbl_resolution_hint.setText("⚠ Bild: min. 300 DPI für optimale Erkennung")
            self.lbl_resolution_hint.setStyleSheet("""
                font-size: 7pt;
                color: #f0a030;
                padding: 2px 0px;
            """)
            self.lbl_resolution_hint.show()
        else:
            # Hide warning for PDFs (they are rendered at 500 DPI automatically)
            self.lbl_resolution_hint.setText("✓ PDF wird bei 500 DPI gerendert")
            self.lbl_resolution_hint.setStyleSheet("""
                font-size: 7pt;
                color: #60a060;
                padding: 2px 0px;
            """)
            self.lbl_resolution_hint.show()
    
    # ============================================================================
    # REAL WORKER WIRING - WITH POPPLER PATH FIX
    # ============================================================================
    def on_run(self):
        if not self.pdf_path:
            QtWidgets.QMessageBox.warning(self, "Fehler: Kein Gleisplan", "Bitte einen Gleisplan auswählen (PDF oder Bild).")
            return
        if not self.model_path:
            QtWidgets.QMessageBox.warning(self, "Fehler: Kein YOLO Model", "Bitte ein YOLO .pt Model auswählen.")
            return
        
        layout_name = self.pdf_path  # Use full path as layout name
        force_rerun = self.check_force_rerun.isChecked()
        
        # Check if saved data exists
        saved_result = None
        try:
            from database3 import get_workspace_data
            saved_result = get_workspace_data(layout_name)
        except Exception as e:
            self.on_status(f"DB-Fehler beim Laden: {e}")
        
        # Decide whether to load from DB or run full analysis
        if saved_result and not force_rerun:
            # ✅ LOAD FROM DATABASE (FAST PATH)
            self.on_status("✅ Gespeicherter Arbeitsbereich gefunden!")
            self.on_status("Lade Daten aus Datenbank (schnell)...")
            
            QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
            self.btn_run.setEnabled(False)
            self.act_run.setEnabled(False)
            self.menu_act_run.setEnabled(False)
            
            try:
                # ✅ FIX: Unpack 3 values instead of 2
                saved_data, saved_track_skeleton, saved_dimensions = saved_result
                
                # Convert saved data to DataFrame
                df_all = pd.DataFrame(saved_data)

                # Load Gleisplan images (needed for visualization)
                self.on_status("Lade Gleisplan...")
                from PIL import Image
                import cv2

                dpi = 500

                # Check if it's an image file or PDF
                image_extensions = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')
                if self.pdf_path.lower().endswith(image_extensions):
                    # Load image directly
                    pil_img = Image.open(self.pdf_path)
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    pages = [pil_img]
                else:
                    # ✅ FIXED: Load PDF with Poppler path
                    from pdf2image import convert_from_path
                    
                    self.on_status(f"Verwende Poppler: {POPPLER_PATH}")
                    
                    pages = convert_from_path(
                        self.pdf_path,
                        dpi=dpi,
                        poppler_path=POPPLER_PATH  # ← Pass Poppler path explicitly
                    )
                
                self._page_base_pix.clear()
                self._page_dfs.clear()
                self._page_bgr_arrays.clear()
                
                # ✅ Build current dimensions for validation
                current_dimensions = {}
                
                for page_num, pil_img in enumerate(pages, start=1):
                    # Convert to QPixmap
                    img_rgb = pil_img.convert("RGB")
                    img_bytes = img_rgb.tobytes("raw", "RGB")
                    qimg = QtGui.QImage(
                        img_bytes,
                        pil_img.width,
                        pil_img.height,
                        pil_img.width * 3,
                        QtGui.QImage.Format_RGB888
                    )
                    pixmap = QtGui.QPixmap.fromImage(qimg)
                    self._page_base_pix[page_num] = pixmap
                    
                    # Store current dimensions
                    current_dimensions[page_num] = {
                        'width': pixmap.width(),
                        'height': pixmap.height()
                    }
                    
                    # Convert to BGR array for OCR operations
                    self._page_bgr_arrays[page_num] = cv2.cvtColor(
                        np.array(pil_img), 
                        cv2.COLOR_RGB2BGR
                    )
                    
                    self.on_status(f"Seite {page_num}/{len(pages)} geladen")
                
                # ✅ Validate dimensions match
                dimensions_match = True
                if saved_dimensions:
                    for page_num, saved_dims in saved_dimensions.items():
                        page_num_int = int(page_num)
                        if page_num_int in current_dimensions:
                            current_dims = current_dimensions[page_num_int]
                            if (current_dims['width'] != saved_dims['width'] or 
                                current_dims['height'] != saved_dims['height']):
                                dimensions_match = False
                                self.on_status(
                                    f"⚠️ Seite {page_num_int}: Dimensionen stimmen nicht überein "
                                    f"(Gespeichert: {saved_dims['width']}x{saved_dims['height']}, "
                                    f"Aktuell: {current_dims['width']}x{current_dims['height']})"
                                )
                
                if not dimensions_match:
                    QtWidgets.QApplication.restoreOverrideCursor()
                    
                    reply = QtWidgets.QMessageBox.warning(
                        self,
                        "Dimensionskonflikt",
                        "Die gespeicherten Daten haben andere Bilddimensionen als der aktuelle Gleisplan.\n\n"
                        "Dies kann zu verschobenen Overlays führen.\n\n"
                        "Möchten Sie trotzdem die gespeicherten Daten laden?\n\n"
                        "'Ja' = Gespeicherte Daten laden (Overlays könnten verschoben sein)\n"
                        "'Nein' = Vollständige Neuanalyse durchführen",
                        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                        QtWidgets.QMessageBox.No
                    )
                    
                    if reply == QtWidgets.QMessageBox.No:
                        self.on_status("Benutzer wählte Neuanalyse")
                        self._run_full_analysis()
                        return
                    
                    QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
                
                # Split df_all into page_dfs
                for page_num in df_all['page'].unique():
                    self._page_dfs[int(page_num)] = df_all[df_all['page'] == page_num].copy()
                
                QtWidgets.QApplication.restoreOverrideCursor()
                self.btn_run.setEnabled(True)
                self.act_run.setEnabled(True)
                self.menu_act_run.setEnabled(True)
                
                self.on_status("✅ Erfolgreich aus Datenbank geladen!")

                # Display last page as preview
                if self._page_base_pix:
                    last_page = max(self._page_base_pix.keys())
                    self._display_page_preview(last_page)

                # Enable "New Symbol" button now that we have images
                if hasattr(self, 'act_new_symbol'):
                    self.act_new_symbol.setEnabled(True)
                if hasattr(self, 'menu_act_new_symbol'):
                    self.menu_act_new_symbol.setEnabled(True)

                # Emit to main window (with saved track skeleton)
                self.processing_done.emit(
                    df_all, 
                    self._page_base_pix, 
                    self._page_dfs, 
                    self._page_bgr_arrays, 
                    saved_track_skeleton,  # Use saved track skeleton
                    None  # No exception
                )
                
                self.statusBar().showMessage("✅ Aus Datenbank geladen - Keine Analyse nötig!", 8000)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                
                QtWidgets.QApplication.restoreOverrideCursor()
                self.btn_run.setEnabled(True)
                self.act_run.setEnabled(True)
                self.menu_act_run.setEnabled(True)
                
                QtWidgets.QMessageBox.critical(
                    self, 
                    "Ladefehler",
                    f"Fehler beim Laden aus Datenbank:\n{str(e)}\n\nStarte vollständige Analyse..."
                )
                
                self.on_status(f"Fehler beim Laden: {e}")
                self.on_status("Fallback: Starte vollständige Analyse...")
                
                # Fall back to full analysis
                self._run_full_analysis()
        
        else:
            # ✅ RUN FULL ANALYSIS (SLOW PATH)
            if force_rerun:
                self.on_status("🔄 Neu-Analyse erzwungen")
            else:
                self.on_status("Keine gespeicherten Daten gefunden")
            
            self._run_full_analysis()

    def _run_full_analysis(self):
        """Run full YOLO + OCR analysis"""
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
        # Track detection is now always enabled for better user experience
        detect_tracks = True  # Always detect tracks automatically

        self.worker = PipelineWorker(
            self.pdf_path,
            self.model_path,
            self.ocr_engine,
            run_analysis=True,
            detect_tracks=detect_tracks
        )
        
        self.worker.progress.connect(self.progress.setValue)
        self.worker.status.connect(self.on_status)
        self.worker.page_processed.connect(self._on_worker_page_ready)
        self.worker.done.connect(self._on_worker_done)
        self.worker.track_detection_progress.connect(self.on_status)
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
                            track_skeleton: Optional[np.ndarray], exception: Optional[Exception]):
            self.on_status("Analyse abgeschlossen.")
            QtWidgets.QApplication.instance().restoreOverrideCursor()
            self.btn_run.setEnabled(True)
            self.act_run.setEnabled(True)
            self.menu_act_run.setEnabled(True)
            self.act_stop.setEnabled(False)
            self.menu_act_stop.setEnabled(False)

            # Pass all dictionaries, track_skeleton, and the exception to the next window
            self.processing_done.emit(df_all, self._page_base_pix, page_dfs, self._page_bgr_arrays, track_skeleton, exception)

    def closeEvent(self, e: QtGui.QCloseEvent):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.requestInterruption(); self.worker.quit(); self.worker.wait(2000)
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

        act_open_model = QtWidgets.QAction("Modell laden", self)
        act_open_model.setToolTip("Modell laden\n\nWählen Sie das trainierte KI-Modell (.pt Datei)\n\nTastenkürzel: Strg+M")
        act_open_model.setShortcut("Ctrl+M")
        act_open_model.triggered.connect(self.on_select_model)
        toolbar.addAction(act_open_model)

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

        act_open_model = file_menu.addAction("YOLO-Modell laden...")
        act_open_model.setShortcut("Ctrl+M")
        act_open_model.triggered.connect(self.on_select_model)

        file_menu.addSeparator()

        act_recent_pdfs = file_menu.addMenu("Kürzlich verwendet")
        self.recent_pdfs_menu = act_recent_pdfs
        self._update_recent_files_menu()

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

        # Symbol Manager
        act_symbol_manager = tools_menu.addAction("Symbol-Manager...")
        act_symbol_manager.setToolTip("Symbole und Vorlagen verwalten")
        act_symbol_manager.triggered.connect(self._show_symbol_manager)

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
        dialog.setMinimumWidth(400)
        
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
            
            # Store other settings (you can add instance variables for these)
            self.yolo_conf_threshold = conf_spin.value()
            self.yolo_iou_threshold = iou_spin.value()
            self.enable_enhancement = check_enhance.isChecked()
            self.enable_parallel = check_parallel.isChecked()
            self.save_debug_images = check_save_debug.isChecked()
            
            self.on_status(f"Einstellungen aktualisiert: OCR={self.ocr_engine}, Conf={self.yolo_conf_threshold:.2f}")
            
    def on_stop(self):
        """Stop the running analysis"""
        if hasattr(self, "worker") and self.worker.isRunning():
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
                
                QtWidgets.QApplication.restoreOverrideCursor()
                self.btn_run.setEnabled(True)
                self.act_run.setEnabled(True)
                self.menu_act_run.setEnabled(True)
                self.act_stop.setEnabled(False)
                self.menu_act_stop.setEnabled(False)
                
                self.on_status("Analyse abgebrochen")
                self.statusBar().showMessage("Analyse wurde abgebrochen")
    def _update_run_button_state(self):
        """Enable/disable run button based on whether PDF and model are loaded"""
        can_run = self.pdf_path is not None and self.model_path is not None
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

            <li><b>Symbol-Manager:</b> Verwalten Sie erkannte Symbole und Vorlagen.</li>
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
            <p><b>Version:</b> 1.0</p>
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
        <i>© 2025 - Siemens Mobility GmbH</i>
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

    def _show_symbol_manager(self):
        """Show symbol manager dialog"""
        try:
            from ui.symbol_manager import SymbolManagerDialog

            dialog = SymbolManagerDialog(self)
            dialog.exec_()

        except ImportError as e:
            # If symbol manager doesn't exist, show new symbol dialog instead
            QtWidgets.QMessageBox.information(
                self,
                "Symbol-Manager",
                "Verwenden Sie 'Neues Symbol definieren...' im Menü 'Verarbeitung', um neue Symbole zu erstellen.\n\n"
                "Ein vollständiger Symbol-Manager wird in einer zukünftigen Version verfügbar sein."
            )
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Symbol-Managers:\n{str(e)}"
            )

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
                    from pdf2image import convert_from_path
                    
                    pages = convert_from_path(
                        file_path,
                        dpi=500,
                        poppler_path=POPPLER_PATH  # ← Use Poppler path
                    )
                    
                    if pages:
                        pil_img = pages[0]
                        current_page_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                except Exception as e:
                    QtWidgets.QMessageBox.warning(self, "Fehler", f"PDF konnte nicht geladen werden:\n{e}")
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