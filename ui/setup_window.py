from PyQt5 import QtCore, QtGui, QtWidgets
from ui.graphics_view import InteractiveGraphicsView
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
import pandas as pd
import os
from ui.dialogs import HelpDialog
from core.pipelineworker import PipelineWorker
import time
import cv2
from core.image_processing import qpolygonf_from_pts
# -------- Setup & Run (connects to REAL PipelineWorker signals) --------
class SetupAndRunWindow(QtWidgets.QMainWindow):
    processing_done = QtCore.pyqtSignal(pd.DataFrame, object, object, object, object, object)  # df_all, page_base_pix, page_dfs, page_bgr_arrays, exception    started_processing = QtCore.pyqtSignal()
    started_processing = QtCore.pyqtSignal()
    def __init__(self, main_app_ref: 'MainWindow'):
        from main import MainWindow
        super().__init__()
        self.main_app_ref = main_app_ref
        self.setWindowTitle("Gleisplan Datenextraktion - Setup & Run")
        self.resize(1000, 800)
        self.pdf_path = None; self.model_path = None; self.ocr_engine = "paddleocr"
        self.view = InteractiveGraphicsView(self)
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
        
    def _build_ui(self):
        # DON'T create menus/toolbar yet - widgets don't exist
        
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)

        top = QtWidgets.QHBoxLayout()
        
        # PDF
        pdf_v = QtWidgets.QVBoxLayout()
        self.btn_pdf = QtWidgets.QPushButton("PDF Hochladen")
        self.lbl_pdf = QtWidgets.QLabel("(Kein PDF ausgewählt)")
        pdf_v.addWidget(self.btn_pdf)
        pdf_v.addWidget(self.lbl_pdf)
        top.addLayout(pdf_v)
        
        # Model
        mdl_v = QtWidgets.QVBoxLayout()
        self.btn_model = QtWidgets.QPushButton("YOLO .pt auswählen")
        self.lbl_model = QtWidgets.QLabel("(Kein Model ausgewählt)")
        mdl_v.addWidget(self.btn_model)
        mdl_v.addWidget(self.lbl_model)
        top.addLayout(mdl_v)
        top.addStretch(1)
        
        # OCR + Run
        ocr_run = QtWidgets.QVBoxLayout()
        ocr_row = QtWidgets.QHBoxLayout()
        ocr_row.addWidget(QtWidgets.QLabel("OCR Engine:"))
        self.combo_ocr = QtWidgets.QComboBox()
        self.combo_ocr.addItems(["paddleocr", "easyocr", "tesseract"])
        self.combo_ocr.setCurrentText(self.ocr_engine)
        ocr_row.addWidget(self.combo_ocr)
        ocr_run.addLayout(ocr_row)
        self.btn_run = QtWidgets.QPushButton("Run")
        ocr_run.addWidget(self.btn_run)
        top.addLayout(ocr_run)
        self.check_force_rerun = QtWidgets.QCheckBox("Neu-Analyse erzwingen")
        self.check_force_rerun.setToolTip("Ignoriert den gespeicherten Arbeitsbereich und führt die YOLO/OCR-Analyse erneut aus.")
        ocr_run.addWidget(self.check_force_rerun)
        self.check_detect_tracks = QtWidgets.QCheckBox("🛤️ Gleise erkennen")
        self.check_detect_tracks.setToolTip("Erkennt und markiert die Hauptgleise im Gleisplan (dauert ~30s extra)")
        ocr_run.addWidget(self.check_detect_tracks)
        main_layout.addLayout(top)
        main_layout.addWidget(self.view, 1)
        
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        main_layout.addWidget(self.progress)
        
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.log.setMaximumBlockCount(5000)
        main_layout.addWidget(self.log)

        # Connect button signals
        self.btn_pdf.clicked.connect(self.on_open_pdf)
        self.btn_model.clicked.connect(self.on_select_model)
        self.combo_ocr.currentTextChanged.connect(self.on_ocr_changed)
        self.btn_run.clicked.connect(self.on_run)
        
        # ✅ NOW create menus and toolbar AFTER all widgets exist
        self._create_menus()
        self._create_toolbar()
        
        # Update initial button state
        self._update_run_button_state()

    # drag & drop
    def dragEnterEvent(self, e: QtGui.QDragEnterEvent):
        e.acceptProposedAction() if e.mimeData().hasUrls() else e.ignore()
    def dropEvent(self, e: QtGui.QDropEvent):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            p_lower = p.lower()
            if p_lower.endswith(".pdf"):
                self.pdf_path = p
                self.lbl_pdf.setText(os.path.basename(self.pdf_path))
                self.on_status(f"PDF geladen: {os.path.basename(self.pdf_path)}")
                self._display_placeholder("PDF geladen")
                self._add_recent_pdf(p)  # ✅ Track recent file
                self._update_run_button_state()  # ✅ Update button state
            elif p_lower.endswith(".pt"):
                self.model_path = p
                self.lbl_model.setText(os.path.basename(self.model_path))
                self.on_status(f"Modell geladen: {os.path.basename(self.model_path)}")
                self._add_recent_model(p)  # ✅ Track recent file
                self._update_run_button_state()  # ✅ Update button state
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
    
    def on_open_pdf(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "PDF Hochladen", "", "PDF Files (*.pdf)")
        if fn:
            self.pdf_path = fn
            self.lbl_pdf.setText(os.path.basename(fn))
            self.on_status(f"PDF geladen: {os.path.basename(fn)}")
            self._display_placeholder("PDF geladen")
            self._add_recent_pdf(fn) 
            self._update_run_button_state()  
    def on_select_model(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Auswählen von YOLO .pt", "", "PyTorch Weights (*.pt)")
        if fn:
            self.model_path = fn
            self.lbl_model.setText(os.path.basename(fn))
            self.on_status(f"Modell geladen: {os.path.basename(fn)}")
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
            settings = QtCore.QSettings("GleisplanExtractor", "SetupAndRun")
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
            settings = QtCore.QSettings("GleisplanExtractor", "SetupAndRun")
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
        """Open a recent PDF file"""
        if os.path.exists(filepath):
            self.pdf_path = filepath
            self.lbl_pdf.setText(os.path.basename(filepath))
            self.on_status(f"PDF geladen: {os.path.basename(filepath)}")
            self._display_placeholder("PDF geladen")
            self._update_run_button_state()
        else:
            QtWidgets.QMessageBox.warning(self, "Datei nicht gefunden", 
                                        f"Die Datei wurde nicht gefunden:\n{filepath}")
            self.recent_pdfs.remove(filepath)
            self._save_recent_files()
            self._update_recent_files_menu()
    # REAL worker wiring (page_ready + done(df_all, overlays))
    def on_run(self):
        if not self.pdf_path:
            QtWidgets.QMessageBox.warning(self, "Fehler: Kein PDF", "Bitte ein PDF auswählen.")
            return
        if not self.model_path:
            QtWidgets.QMessageBox.warning(self, "Fehler: Kein YOLO Model", "Bitte ein YOLO .pt Model auswählen.")
            return
        
        layout_name = self.pdf_path  # Use full path as layout name
        force_rerun = self.check_force_rerun.isChecked()
        
        # Check if saved data exists
        saved_data = None
        try:
            from database3 import get_workspace_data
            saved_data = get_workspace_data(layout_name)
        except Exception as e:
            self.on_status(f"DB-Fehler beim Laden: {e}")
        
        # Decide whether to load from DB or run full analysis
        if saved_data and not force_rerun:
            # ✅ LOAD FROM DATABASE (FAST PATH)
            self.on_status("✅ Gespeicherter Arbeitsbereich gefunden!")
            self.on_status("Lade Daten aus Datenbank (schnell)...")
            
            QtWidgets.QApplication.instance().setOverrideCursor(QtCore.Qt.WaitCursor)
            self.btn_run.setEnabled(False)
            self.act_run.setEnabled(False)
            self.menu_act_run.setEnabled(False)
            
            try:
                saved_data, saved_track_skeleton = saved_data  # Unpack tuple
                
                # Convert saved data to DataFrame
                df_all = pd.DataFrame(saved_data)
                
                # Load PDF images (needed for visualization)
                self.on_status("Rendere PDF-Seiten...")
                from pdf2image import convert_from_path
                import cv2
                
                dpi = 500
                pages = convert_from_path(self.pdf_path, dpi=dpi)
                
                self._page_base_pix.clear()
                self._page_dfs.clear()
                self._page_bgr_arrays.clear()
                
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
                    self._page_base_pix[page_num] = QtGui.QPixmap.fromImage(qimg)
                    
                    # Convert to BGR array for OCR operations
                    self._page_bgr_arrays[page_num] = cv2.cvtColor(
                        np.array(pil_img), 
                        cv2.COLOR_RGB2BGR
                    )
                    
                    self.on_status(f"Seite {page_num}/{len(pages)} geladen")
                
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
        detect_tracks = self.check_detect_tracks.isChecked()
        
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
        """Create toolbar for Setup & Run window"""
        toolbar = self.addToolBar("Hauptwerkzeuge")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(24, 24))
        
        # File Actions
        act_open_pdf = QtWidgets.QAction("📄 PDF öffnen", self)
        act_open_pdf.setToolTip("PDF-Datei auswählen (Strg+O)")
        act_open_pdf.setShortcut("Ctrl+O")
        act_open_pdf.triggered.connect(self.on_open_pdf)
        toolbar.addAction(act_open_pdf)
        
        act_open_model = QtWidgets.QAction("🤖 Modell laden", self)
        act_open_model.setToolTip("YOLO-Modell auswählen (Strg+M)")
        act_open_model.setShortcut("Ctrl+M")
        act_open_model.triggered.connect(self.on_select_model)
        toolbar.addAction(act_open_model)
        
        toolbar.addSeparator()
        
        # Run Action
        self.act_run = QtWidgets.QAction("▶ Analyse starten", self)
        self.act_run.setToolTip("Analyse starten (F5)")
        self.act_run.setShortcut("F5")
        self.act_run.setEnabled(False)
        self.act_run.triggered.connect(self.on_run)
        toolbar.addAction(self.act_run)
        
        self.act_stop = QtWidgets.QAction("⏹ Stoppen", self)
        self.act_stop.setToolTip("Analyse stoppen (Esc)")
        self.act_stop.setShortcut("Esc")
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self.on_stop)
        toolbar.addAction(self.act_stop)
        
        toolbar.addSeparator()
        
        # View Actions
        act_zoom_in = QtWidgets.QAction("🔍+ Zoom In", self)
        act_zoom_in.setToolTip("Vergrößern (Strg++)")
        act_zoom_in.triggered.connect(self.view.zoom_in)
        toolbar.addAction(act_zoom_in)
        
        act_zoom_out = QtWidgets.QAction("🔍− Zoom Out", self)
        act_zoom_out.setToolTip("Verkleinern (Strg+-)")
        act_zoom_out.triggered.connect(self.view.zoom_out)
        toolbar.addAction(act_zoom_out)
        
        act_fit = QtWidgets.QAction("⊡ Anpassen", self)
        act_fit.setToolTip("An Ansicht anpassen (Strg+0)")
        act_fit.triggered.connect(self.view.fit_to_view)
        toolbar.addAction(act_fit)
        
        toolbar.addSeparator()
        
        # Settings Action
        act_settings = QtWidgets.QAction("⚙ Einstellungen", self)
        act_settings.setToolTip("Erweiterte Einstellungen")
        act_settings.triggered.connect(self.on_show_settings)
        toolbar.addAction(act_settings)
        
        # Clear Log
        act_clear_log = QtWidgets.QAction("🗑 Log löschen", self)
        act_clear_log.setToolTip("Ausgabeprotokoll löschen")
        act_clear_log.triggered.connect(self.log.clear)
        toolbar.addAction(act_clear_log)
        return toolbar  
    
    def _create_menus(self):
        """Create menu bar"""
        mb = self.menuBar()
        
        # File Menu
        file_menu = mb.addMenu("Datei")
        
        act_open_pdf = file_menu.addAction("📄 PDF öffnen...")
        act_open_pdf.setShortcut("Ctrl+O")
        act_open_pdf.triggered.connect(self.on_open_pdf)
        
        act_open_model = file_menu.addAction("🤖 YOLO-Modell laden...")
        act_open_model.setShortcut("Ctrl+M")
        act_open_model.triggered.connect(self.on_select_model)
        
        file_menu.addSeparator()
        
        act_recent_pdfs = file_menu.addMenu("📋 Kürzlich verwendet")
        self.recent_pdfs_menu = act_recent_pdfs
        self._update_recent_files_menu()
        
        file_menu.addSeparator()
        
        act_exit = file_menu.addAction("🚪 Beenden")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        
        # Process Menu
        process_menu = mb.addMenu("Verarbeitung")
        
        self.menu_act_run = process_menu.addAction("▶ Analyse starten")
        self.menu_act_run.setShortcut("F5")
        self.menu_act_run.setEnabled(False)
        self.menu_act_run.triggered.connect(self.on_run)
        
        self.menu_act_stop = process_menu.addAction("⏹ Stoppen")
        self.menu_act_stop.setShortcut("Esc")
        self.menu_act_stop.setEnabled(False)
        self.menu_act_stop.triggered.connect(self.on_stop)
        
        process_menu.addSeparator()
        
        act_settings = process_menu.addAction("⚙ Einstellungen...")
        act_settings.triggered.connect(self.on_show_settings)
        
        # View Menu
        view_menu = mb.addMenu("Ansicht")
        view_menu.addAction("Dunkles Thema", lambda: self.main_app_ref._set_theme("dark"))
        view_menu.addAction("Helles Thema", lambda: self.main_app_ref._set_theme("light"))
        view_menu.addSeparator()
        
        act_clear_log = view_menu.addAction("🗑 Log löschen")
        act_clear_log.triggered.connect(self.log.clear)
        
        act_toggle_log = view_menu.addAction("📜 Log ein-/ausblenden")
        act_toggle_log.setCheckable(True)
        act_toggle_log.setChecked(True)
        act_toggle_log.triggered.connect(lambda checked: self.log.setVisible(checked))
        
        # --- HILFE-MENÜ HINZUFÜGEN ---
        help_menu = mb.addMenu("Hilfe")
        help_menu.addAction("📖 Bedienungsanleitung", self._show_help_guide)
        help_menu.addAction("⌨ Tastenkombinationen", self._show_keyboard_shortcuts)
        help_menu.addSeparator()
        help_menu.addAction("ℹ Über", self._show_about)
        
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
        
        <h3>📄 PDF laden</h3>
        <ul>
            <li>Klicken Sie auf "PDF Hochladen" oder drücken Sie <b>Strg+O</b></li>
            <li>Oder ziehen Sie eine PDF-Datei per Drag & Drop ins Fenster</li>
            <li>Kürzlich verwendete Dateien finden Sie unter Datei → Kürzlich verwendet</li>
        </ul>
        
        <h3>🤖 YOLO-Modell laden</h3>
        <ul>
            <li>Klicken Sie auf "YOLO .pt auswählen" oder drücken Sie <b>Strg+M</b></li>
            <li>Wählen Sie Ihre trainierte .pt-Modelldatei</li>
        </ul>
        
        <h3>⚙ OCR Engine & Optionen</h3>
        <ul>
            <li><b>OCR Engine:</b> Wählen Sie zwischen PaddleOCR, EasyOCR oder Tesseract</li>
            <li><b>Neu-Analyse erzwingen:</b> Ignoriert gespeicherte Daten und startet eine frische Analyse.</li>
            <li><b>Gleise erkennen:</b> Aktiviert die Erkennung der Hauptgleise (dauert länger).</li>
            <li><b>Erweiterte Einstellungen:</b> Über "Verarbeitung → Einstellungen" können Sie Konfidenz-Schwellenwerte und Bildverbesserung anpassen.</li>
        </ul>
        
        <h3>▶ Analyse starten & stoppen</h3>
        <ul>
            <li>Drücken Sie <b>F5</b> oder klicken Sie auf "Run"</li>
            <li>Der Fortschritt wird in Echtzeit angezeigt</li>
            <li>Mit <b>Esc</b> oder "Stoppen" können Sie die Analyse abbrechen</li>
        </ul>
        
        <h3>🔍 Vorschau</h3>
        <ul>
            <li>Während der Verarbeitung sehen Sie eine Live-Vorschau der aktuellen Seite.</li>
            <li>Zoomen mit <b>Strg+Mausrad</b> oder Toolbar-Buttons.</li>
            <li>Verschieben durch Ziehen mit der Maus.</li>
        </ul>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Bedienungsanleitung - Setup & Run", help_text, self)
        help_dialog.exec_()

    def _show_keyboard_shortcuts(self):
        """Show keyboard shortcuts for Setup & Run window"""
        shortcuts_text = """
        <h2>⌨ Tastenkombinationen - Setup & Run</h2>
        
        <table border="1" cellpadding="5">
            <tr><th>Aktion</th><th>Tastenkombination</th></tr>
            <tr><td>PDF öffnen</td><td><b>Strg+O</b></td></tr>
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
        <h2>Gleisplan Datenextraktion</h2>
        <h3>Setup & Run Modul</h3>
        <p><b>Version:</b> 1.0</p>
        
        <p>Dieses Modul ermöglicht das Laden und Verarbeiten von Gleisplan-PDFs
        mit YOLO-basierter Objekterkennung und Multi-Engine OCR.</p>
        
        <p><i>© 2025 - Siemens AG</i></p>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Über - Setup & Run", about_text, self)
        help_dialog.exec_()