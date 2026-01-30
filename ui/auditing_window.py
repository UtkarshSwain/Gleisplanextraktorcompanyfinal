# ============================================================================
# RailDoc Studio - Bearbeitungsmodul
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2025
# ============================================================================
from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Dict, Tuple, Optional, Any
import os
import re
import math
from ui.themes import DARK_QSS,LIGHT_QSS
import pandas as pd
import numpy as np
from ui.draggable_tab_bar import DraggableTabWidget
from ui.database_dialogs import SavedWorkspacesDialog, DatabaseManagerDialog
from utils.uuid_utils import generate_deterministic_uuid, extract_base_layout_name
class AuditingWindow(QtWidgets.QMainWindow):

    """Main window that holds multiple workspace tabs - NO VERSIONING"""

    def __init__(self, main_app_ref: 'MainWindow'):
        from main import MainWindow

        from ui.workspace_widget import WorkspaceWidget

        super().__init__()
        self.main_app_ref = main_app_ref
        self.setWindowTitle("RailDoc Studio - Bearbeitung & Korrektur")
        self.resize(1400, 900)
        # Initialize status bar labels FIRST (before creating menus/toolbar)
        self.status_label = None
        self.row_count_label = None
        self.selection_label = None
        # Initialize data structures
        self.workspaces = {}
        self.tree_window = None
        # Tab widget (with drag-to-pop-out support)
        self.tab_widget = DraggableTabWidget(self)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.on_close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Enable text truncation for compact tabs
        self.tab_widget.tabBar().setElideMode(QtCore.Qt.ElideRight)

        # Use system default theme with compact tab sizing only
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                padding: 6px 16px;
                min-width: 80px;
                max-width: 150px;
            }
        """)

        self.setCentralWidget(self.tab_widget)
        # Create UI elements IN THIS ORDER
        self._create_status_bar()  # Create status bar FIRST
        self._create_menus()       # Then menus (which reference status_label)
        self._create_toolbar()     # Then toolbar
        # Track open workspaces
        self.workspaces: Dict[int, WorkspaceWidget] = {}
        self.tab_widget.currentChanged.connect(self.update_status_bar)
        
        self.statusBar().showMessage("✅ Analyse abgeschlossen - Sie können nun die Daten überprüfen und bearbeiten")
    
    def add_workspace(self, layout_name: str, df_all: pd.DataFrame,
                    page_base_pix: Dict, page_dfs: Dict, page_bgr_arrays: Dict,
                    track_skeleton: Optional[np.ndarray] = None,
                    from_database: bool = False):
        """Add a new PDF workspace as a tab

        Args:
            from_database: If True, data was loaded from database (skip DB check in workspace)
        """
        from ui.workspace_widget import WorkspaceWidget

        # Check if already open
        for idx, ws in self.workspaces.items():
            if ws.layout_name == layout_name:
                self.tab_widget.setCurrentIndex(idx)
                self.statusBar().showMessage(f"{layout_name} bereits geöffnet")
                return

        # Create workspace widget
        workspace = WorkspaceWidget(self, layout_name)
        workspace.load_data(df_all, page_base_pix, page_dfs, page_bgr_arrays, track_skeleton, from_database)
        
        # Add as tab (use filename without extension for cleaner look)
        tab_label = os.path.basename(layout_name)
        # Remove common Gleisplan extensions if present
        for ext in ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
            if tab_label.lower().endswith(ext):
                tab_label = tab_label[:-len(ext)]
                break
        tab_idx = self.tab_widget.addTab(workspace, tab_label)
        self.workspaces[tab_idx] = workspace
        self.tab_widget.setCurrentIndex(tab_idx)
        
        self.statusBar().showMessage(f"Bereit: {tab_label}")
    
    def on_close_tab(self, tab_index: int):
        """Close a workspace tab"""
        from ui.workspace_widget import WorkspaceWidget
    
        workspace = self.workspaces.get(tab_index)
        if not workspace:
            return
        
        # Ask to save
        reply = QtWidgets.QMessageBox.question(
            self,
            "Tab schließen",
            f"Möchten Sie '{workspace.layout_name}' vor dem Schließen speichern?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )
        
        if reply == QtWidgets.QMessageBox.Cancel:
            return
        
        if reply == QtWidgets.QMessageBox.Yes:
            workspace.save_to_db()
        
        # Remove tab
        self.tab_widget.removeTab(tab_index)
        del self.workspaces[tab_index]
        
        # Re-index remaining workspaces
        new_workspaces = {}
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, WorkspaceWidget):
                new_workspaces[i] = widget
        self.workspaces = new_workspaces
        
        if len(self.workspaces) == 0:
            self.statusBar().showMessage("Alle Tabs geschlossen - Öffnen Sie einen Gleisplan")
    
    def on_tab_changed(self, index: int):
            """Update UI when switching tabs"""
            if index < 0:
                self.statusBar().showMessage("Bereit - Öffnen Sie einen Gleisplan")
                return
            
            workspace = self.workspaces.get(index)
            if workspace:
                # --- UPDATE THIS LINE ---
                self.statusBar().showMessage(f"Bereit: {os.path.basename(workspace.layout_name)}")
    
    def _create_menus(self):
        """Create simplified menu bar for train technicians"""
        mb = self.menuBar()

        # File Menu - Essential save and export operations
        file_menu = mb.addMenu("Datei")

        act_save = file_menu.addAction("💾 Speichern")
        act_save.setShortcut("Ctrl+S")
        act_save.setToolTip("Speichert den aktuellen Plan")
        act_save.triggered.connect(self.on_save_current)

        act_save_all = file_menu.addAction("💾 Alle speichern")
        act_save_all.setShortcut("Ctrl+Shift+S")
        act_save_all.setToolTip("Speichert alle geöffneten Pläne")
        act_save_all.triggered.connect(self.on_save_all)

        file_menu.addSeparator()

        act_export_excel = file_menu.addAction("📊 Excel Export")
        act_export_excel.setShortcut("Ctrl+E")
        act_export_excel.setToolTip("Exportiert als Excel-Datei")
        act_export_excel.triggered.connect(self.on_export_excel)

        act_export_json = file_menu.addAction("📄 JSON Export")
        act_export_json.setShortcut("Ctrl+J")
        act_export_json.setToolTip("Exportiert als JSON-Datei")
        act_export_json.triggered.connect(self.on_export_json)

        file_menu.addSeparator()

        act_close_tab = file_menu.addAction("❌ Tab schließen")
        act_close_tab.setShortcut("Ctrl+W")
        act_close_tab.triggered.connect(lambda: self.on_close_tab(self.tab_widget.currentIndex()))

        # Edit Menu - Basic editing operations
        edit_menu = mb.addMenu("Bearbeiten")

        act_find = edit_menu.addAction("🔍 Suchen")
        act_find.setShortcut("Ctrl+F")
        act_find.triggered.connect(self.on_find_replace)

        edit_menu.addSeparator()

        act_copy = edit_menu.addAction("📋 Kopieren")
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.on_copy)

        act_paste = edit_menu.addAction("📌 Einfügen")
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.on_paste)

        edit_menu.addSeparator()

        act_add_row = edit_menu.addAction("➕ Zeile hinzufügen")
        act_add_row.setShortcut("Ctrl+Shift+N")
        act_add_row.triggered.connect(self.on_add_row)

        act_del_rows = edit_menu.addAction("🗑️ Zeilen löschen")
        act_del_rows.setShortcut("Ctrl+D")
        act_del_rows.triggered.connect(self.on_delete_selected_table_rows)

        edit_menu.addSeparator()

        act_bulk = edit_menu.addAction("✏️ Massenbearbeitung")
        act_bulk.setToolTip("Bearbeitet mehrere Zeilen gleichzeitig")
        act_bulk.triggered.connect(self.on_bulk_edit)

        # Data Menu - Sort and filter
        data_menu = mb.addMenu("Daten")

        act_sort = data_menu.addAction("🔀 Sortieren")
        act_sort.triggered.connect(self.on_sort)

        act_filter = data_menu.addAction("🔍 Filter")
        act_filter.triggered.connect(self.on_filter)

        data_menu.addSeparator()

        act_stats = data_menu.addAction("📈 Statistik")
        act_stats.setToolTip("Zeigt Statistiken über die Daten")
        act_stats.triggered.connect(self.on_statistics)

        data_menu.addSeparator()

        act_db_manager = data_menu.addAction("🗄️ Datenbank-Manager...")
        act_db_manager.setToolTip("Gespeicherte Daten und Arbeitsbereiche verwalten")
        act_db_manager.triggered.connect(self._show_database_manager)

        # Compare Menu - Gleisplan comparison (IMPORTANT FEATURE!)
        compare_menu = mb.addMenu("Vergleichen")

        act_compare = compare_menu.addAction("🔍 Zwei Gleispläne vergleichen")
        act_compare.setToolTip("Vergleicht zwei geöffnete Gleispläne um Unterschiede zu finden")
        act_compare.triggered.connect(self.on_compare_pdfs)

        # View Menu - Simple view options
        view_menu = mb.addMenu("Ansicht")

        act_expand_all = view_menu.addAction("📂 Alle ausklappen")
        act_expand_all.triggered.connect(self.on_expand_all)

        act_collapse_all = view_menu.addAction("📁 Alle einklappen")
        act_collapse_all.triggered.connect(self.on_collapse_all)

        view_menu.addSeparator()

        act_resize = view_menu.addAction("📏 Spaltenbreite anpassen")
        act_resize.triggered.connect(self.on_resize_columns)

        # Symbols Menu - Symbol management
        symbol_menu = mb.addMenu("Symbole")
        act_new_symbol = symbol_menu.addAction("➕ Neues Symbol definieren")
        act_new_symbol.setToolTip("Neues Symbol ohne Modell-Training definieren")
        act_new_symbol.triggered.connect(self.on_add_new_symbol)

        symbol_menu.addSeparator()

        act_run_template = symbol_menu.addAction("🔍 Template Matching")
        act_run_template.setToolTip("Sucht nach neu definierten Symbolen im Layout")
        act_run_template.triggered.connect(self.on_run_template_matching_only)

        # Help Menu
        help_menu = mb.addMenu("Hilfe")
        help_menu.addAction("📖 Bedienungsanleitung", self._show_help_guide)
        help_menu.addSeparator()
        help_menu.addAction("ℹ Über", self._show_about)
    
    def _create_toolbar(self):
        """Create streamlined toolbar with essential tools only"""
        toolbar = self.addToolBar("Hauptwerkzeuge")
        toolbar.setMovable(False)

        # Save Section - Most important actions first
        act_save = QtWidgets.QAction("💾 Speichern", self)
        act_save.setShortcut("Ctrl+S")
        act_save.setToolTip("Speichert alle Änderungen (Strg+S)")
        act_save.triggered.connect(self.on_save_current)
        toolbar.addAction(act_save)

        act_save_all = QtWidgets.QAction("💾 Alle", self)
        act_save_all.setShortcut("Ctrl+Shift+S")
        act_save_all.setToolTip("Speichert alle geöffneten Pläne (Strg+Shift+S)")
        act_save_all.triggered.connect(self.on_save_all)
        toolbar.addAction(act_save_all)

        toolbar.addSeparator()

        # Clipboard Section
        act_copy = QtWidgets.QAction("📋 Kopieren", self)
        act_copy.setToolTip("Kopiert ausgewählte Zellen (Strg+C)")
        act_copy.triggered.connect(self.on_copy)
        toolbar.addAction(act_copy)

        act_paste = QtWidgets.QAction("📌 Einfügen", self)
        act_paste.setToolTip("Fügt kopierte Daten ein (Strg+V)")
        act_paste.triggered.connect(self.on_paste)
        toolbar.addAction(act_paste)

        toolbar.addSeparator()

        # Search and Data Management
        act_find = QtWidgets.QAction("🔍 Suchen", self)
        act_find.setToolTip("Sucht und ersetzt Text (Strg+F)")
        act_find.triggered.connect(self.on_find_replace)
        toolbar.addAction(act_find)

        act_sort = QtWidgets.QAction("🔀 Sortieren", self)
        act_sort.setToolTip("Sortiert Daten nach Spalte")
        act_sort.triggered.connect(self.on_sort)
        toolbar.addAction(act_sort)

        act_filter = QtWidgets.QAction("🔍 Filter", self)
        act_filter.setToolTip("Filtert Daten nach Kriterien")
        act_filter.triggered.connect(self.on_filter)
        toolbar.addAction(act_filter)

        toolbar.addSeparator()

        # Export Section
        act_excel = QtWidgets.QAction("📊 Excel Export", self)
        act_excel.setToolTip("Exportiert als Excel-Datei (Strg+E)")
        act_excel.triggered.connect(self.on_export_excel)
        toolbar.addAction(act_excel)

        act_json = QtWidgets.QAction("📄 JSON", self)
        act_json.setToolTip("Exportiert als JSON (Strg+J)")
        act_json.triggered.connect(self.on_export_json)
        toolbar.addAction(act_json)

        toolbar.addSeparator()

        # Advanced Features
        act_bulk = QtWidgets.QAction("✏️ Massenbearbeitung", self)
        act_bulk.setToolTip("Bearbeitet mehrere Zeilen gleichzeitig")
        act_bulk.triggered.connect(self.on_bulk_edit)
        toolbar.addAction(act_bulk)

        act_compare = QtWidgets.QAction("🔍 Vergleichen", self)
        act_compare.setToolTip("Vergleicht zwei Gleispläne")
        act_compare.triggered.connect(self.on_compare_pdfs)
        toolbar.addAction(act_compare)

        toolbar.addSeparator()

        # Row Management
        act_add_row = QtWidgets.QAction("➕ Zeile", self)
        act_add_row.setToolTip("Fügt neue Zeile hinzu (Strg+Shift+N)")
        act_add_row.triggered.connect(self.on_add_row)
        toolbar.addAction(act_add_row)

        act_del_row = QtWidgets.QAction("🗑️ Löschen", self)
        act_del_row.setToolTip("Löscht ausgewählte Zeilen (Strg+D)")
        act_del_row.triggered.connect(self.on_delete_selected_table_rows)
        toolbar.addAction(act_del_row)

        toolbar.addSeparator()

        # Symbol Management
        self.act_new_symbol = QtWidgets.QAction("➕ Neues Symbol", self)
        self.act_new_symbol.setToolTip("Definiert neues Symbol ohne Modell-Training")
        self.act_new_symbol.triggered.connect(self.on_add_new_symbol)
        toolbar.addAction(self.act_new_symbol)

        self.act_run_template = QtWidgets.QAction("🔍 Template Matching", self)
        self.act_run_template.setToolTip("Sucht nach neu definierten Symbolen")
        self.act_run_template.triggered.connect(self.on_run_template_matching_only)
        toolbar.addAction(self.act_run_template)

    def _create_status_bar(self):
        """Create status bar with system default styling"""
        self.status_bar = self.statusBar()

        # Create labels with icons - no custom styling
        self.status_label = QtWidgets.QLabel("✅ Bereit")

        self.row_count_label = QtWidgets.QLabel("📊 Zeilen: 0")

        self.selection_label = QtWidgets.QLabel("🔍 Auswahl: 0")

        # Add to status bar
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.selection_label)
        self.status_bar.addPermanentWidget(self.row_count_label)

        # Update on selection change
        self.tab_widget.currentChanged.connect(self.update_status_bar)
    # ADD THIS NEW METHOD HERE (after _create_status_bar)
    def _set_status(self, message: str):
        """Safely set status bar message"""
        if self.status_label is not None:
            self.status_label.setText(message)
        else:
            print(f"[STATUS] {message}")  # Fallback to console
    def update_status_bar(self):
        """Update status bar information"""
        # Check if status bar widgets exist
        if self.row_count_label is None or self.selection_label is None:
            return
        
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        
        if workspace and hasattr(workspace, 'tree'):
            # Count total rows
            total_rows = 0
            for i in range(workspace.tree.topLevelItemCount()):
                total_rows += workspace.tree.topLevelItem(i).childCount()
            
            self.row_count_label.setText(f"Zeilen: {total_rows}")
            
            # Count selection (only child items)
            selected = workspace.tree.selectedItems()
            child_selected = len([item for item in selected if item.childCount() == 0])
            self.selection_label.setText(f"Auswahl: {child_selected}")
        else:
            self.row_count_label.setText("Zeilen: 0")
            self.selection_label.setText("Auswahl: 0")

    def on_save_current(self):
        """Save currently active workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.save_to_db()
            self.statusBar().showMessage(f"✅ {workspace.layout_name} gespeichert")
    
    def on_save_all(self):
        """Save all open workspaces"""
        for workspace in self.workspaces.values():
            workspace.save_to_db()
        self.statusBar().showMessage(f"✅ Alle {len(self.workspaces)} Workspaces gespeichert")
    
    def on_export_excel(self):
        """Export current workspace to Excel"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.on_export_excel()
    
    def on_export_json(self):
        """Export current workspace to JSON"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.on_export_json()
    
    def on_compare_pdfs(self):
        """Compare two open Gleispläne"""
        from pdfcomparison.dialogs import SimplePDFCompareDialog
        if len(self.workspaces) < 2:
            QtWidgets.QMessageBox.information(
                self,
                "Nicht genug Gleispläne",
                "Bitte öffnen Sie mindestens 2 Gleispläne zum Vergleichen.\n\n"
                "Tipp: Öffnen Sie z.B. 'layout_v1' und 'layout_v2'"
            )
            return
        
        # Show comparison dialog
        dialog = SimplePDFCompareDialog(self)
        
        #  MAKE IT A CHILD WINDOW (minimizes within app)
        dialog.setWindowFlags(
            QtCore.Qt.Dialog |  # ✅ Changed from Window to Dialog
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        dialog.setModal(False)  # ✅ Ensure it's non-modal

        # Apply theme
        if self.main_app_ref._current_theme == "dark":
            dialog.setStyleSheet(DARK_QSS)
        else:
            dialog.setStyleSheet(LIGHT_QSS)
        
        # ✅ SHOW NON-MODAL (not exec_())
        dialog.show()

    def on_add_new_symbol(self):
        """Open the New Symbol Dialog to define a new symbol without retraining YOLO."""
        import cv2

        current_page_bgr = None

        # Get the current workspace
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)

        # Try to get image from workspace if available
        if workspace and workspace.page_bgr_arrays:
            current_page_bgr = workspace.page_bgr_arrays.get(workspace.current_page)
            if current_page_bgr is None and workspace.page_bgr_arrays:
                current_page_bgr = list(workspace.page_bgr_arrays.values())[0]

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
                "Alle Gleispläne (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.pdf);;Bilder (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;PDF Dateien (*.pdf);;Alle Dateien (*.*)"
            )

            if not file_path:
                return

            # Load the image
            if file_path.lower().endswith('.pdf'):
                # For PDF, load the first page
                try:
                    import fitz
                    import numpy as np
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
                QtWidgets.QMessageBox.warning(self, "Fehler", f"Datei konnte nicht geladen werden:\n{file_path}")
                return

        try:
            from ui.new_symbol_dialog import NewSymbolDialog

            dialog = NewSymbolDialog(current_page_bgr, self)
            result = dialog.exec_()

            if result == QtWidgets.QDialog.Accepted:
                self.statusBar().showMessage("Neues Symbol erfolgreich definiert!", 5000)
            else:
                self.statusBar().showMessage("Symbol-Definition abgebrochen.", 3000)

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

    def on_run_template_matching_only(self):
        """
        Run template matching on already-analyzed layouts without re-running full analysis.

        This allows users to:
        1. Define new custom symbols
        2. Run template matching on existing workspaces
        3. Merge new detections with existing data

        Uses the SAME tiling strategy and NMS as the main pipeline:
        - Breaks page into 2048px tiles with overlap
        - Runs detection on each tile
        - Adjusts coordinates to page space
        - Applies NMS per symbol name
        """
        import time
        import sys
        print("\n" + "="*60, flush=True)
        print("🔍 TEMPLATE MATCHING ONLY - STARTED", flush=True)
        print("="*60, flush=True)

        # Get current workspace
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)

        if not workspace:
            QtWidgets.QMessageBox.warning(
                self,
                "Kein Workspace",
                "Bitte öffnen Sie zuerst ein analysiertes Layout."
            )
            return

        print(f"   workspace.page_bgr_arrays: {len(workspace.page_bgr_arrays)} pages", flush=True)
        print(f"   workspace.page_base_pix: {len(workspace.page_base_pix) if workspace.page_base_pix else 0} pages", flush=True)

        if not workspace.page_bgr_arrays:
            # Try to rebuild from page_base_pix if available
            if workspace.page_base_pix:
                print("   🔄 Rebuilding page_bgr_arrays from page_base_pix...")
                import cv2
                for pidx, pix in workspace.page_base_pix.items():
                    if pix is not None:
                        # Convert QPixmap to BGR numpy array
                        qimg = pix.toImage()
                        width = qimg.width()
                        height = qimg.height()
                        ptr = qimg.bits()
                        ptr.setsize(height * width * 4)
                        arr = np.array(ptr).reshape(height, width, 4)
                        bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
                        workspace.page_bgr_arrays[pidx] = bgr
                        print(f"      Page {pidx}: rebuilt {bgr.shape}")
                print(f"   ✅ Rebuilt {len(workspace.page_bgr_arrays)} pages")
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Keine Bilddaten",
                    "Keine Bilddaten im aktuellen Workspace verfügbar.\n"
                    "Bitte führen Sie zuerst eine vollständige Analyse durch."
                )
                return

        # Check if any custom symbols are defined
        try:
            from core.symbol_detector import NewSymbolDetector, DetectionResult
            from core.yolo_detection import tile_image, nms, TILE_SIZE, OVERLAP_PCT
            from config import TILE_SIZE

            detector = NewSymbolDetector()

            if not detector.symbols:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Keine Symbole definiert",
                    "Es sind keine benutzerdefinierten Symbole definiert.\n\n"
                    "Möchten Sie jetzt ein neues Symbol definieren?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if reply == QtWidgets.QMessageBox.Yes:
                    self.on_add_new_symbol()
                return

            symbol_names = list(detector.symbols.keys())

            # Check which custom symbol classes are already detected in the workspace
            # to avoid double detection
            already_detected_classes = set()
            existing_custom_centers = {}  # {page: [(cx, cy, cls), ...]}

            if workspace.df_all is not None and not workspace.df_all.empty:
                # Find all custom symbol detections by TWO methods:
                # 1. Check is_custom_symbol=True flag
                # 2. Check if class name matches any defined custom symbol name

                custom_mask = workspace.df_all.get('is_custom_symbol', pd.Series([False]*len(workspace.df_all)))
                custom_mask = custom_mask == True  # Handle NaN

                # Also check by class name matching custom symbol names
                cls_mask = workspace.df_all['cls'].isin(symbol_names)

                # Combine both checks
                combined_mask = custom_mask | cls_mask

                if combined_mask.any():
                    custom_df = workspace.df_all[combined_mask]
                    already_detected_classes = set(custom_df['cls'].unique())

                    # Store centers of existing custom symbols for position-based duplicate check
                    for _, row in custom_df.iterrows():
                        page = row['page'] if 'page' in row.index and pd.notna(row['page']) else 0

                        # Get bbox coordinates - use ax1/ay1/ax2/ay2 if x1/y1/x2/y2 not available
                        x1 = None
                        for col in ['x1', 'ax1']:
                            if col in row.index and pd.notna(row[col]):
                                x1 = float(row[col])
                                break
                        x2 = None
                        for col in ['x2', 'ax2']:
                            if col in row.index and pd.notna(row[col]):
                                x2 = float(row[col])
                                break
                        y1 = None
                        for col in ['y1', 'ay1']:
                            if col in row.index and pd.notna(row[col]):
                                y1 = float(row[col])
                                break
                        y2 = None
                        for col in ['y2', 'ay2']:
                            if col in row.index and pd.notna(row[col]):
                                y2 = float(row[col])
                                break

                        # Calculate center
                        if x1 is not None and x2 is not None:
                            cx = (x1 + x2) / 2
                        elif 'cx' in row.index and pd.notna(row['cx']):
                            cx = float(row['cx'])
                        else:
                            cx = 0

                        if y1 is not None and y2 is not None:
                            cy = (y1 + y2) / 2
                        elif 'cy' in row.index and pd.notna(row['cy']):
                            cy = float(row['cy'])
                        else:
                            cy = 0

                        cls = row['cls'] if 'cls' in row.index and pd.notna(row['cls']) else ''

                        if page not in existing_custom_centers:
                            existing_custom_centers[page] = []
                        existing_custom_centers[page].append((cx, cy, cls))

                    print(f"   ℹ️ Found {len(custom_df)} existing custom symbol detections", flush=True)

            if already_detected_classes:
                print(f"   ℹ️ Already detected custom symbol classes: {already_detected_classes}", flush=True)
                total_existing = sum(len(centers) for centers in existing_custom_centers.values())
                print(f"   ℹ️ Total existing positions to check: {total_existing}", flush=True)

            # Filter symbol_names to only detect symbols that aren't already fully detected
            # But still allow detection at NEW positions for partially detected symbols
            symbols_to_detect = symbol_names  # Detect all, but filter by position later

            # First pass: count total tiles for accurate progress
            total_tiles = 0
            page_tiles_info = {}
            for page_num, page_bgr in workspace.page_bgr_arrays.items():
                tiles = tile_image(page_bgr, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)
                page_tiles_info[page_num] = tiles
                total_tiles += len(tiles)

            # Detect available CPU cores for multi-threading
            import os
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = min(os.cpu_count() or 4, 8)  # Use up to 8 cores
            print(f"   ℹ️ Using {max_workers} CPU threads for template matching", flush=True)

            # Show progress dialog with accurate tile count
            progress = QtWidgets.QProgressDialog(
                f"Template Matching für {len(symbol_names)} Symbol(e)...\n"
                f"0/{total_tiles} Kacheln | {max_workers} Threads | Geschätzte Zeit: berechne...",
                "Abbrechen",
                0,
                total_tiles,
                self
            )
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setWindowTitle("Template Matching")
            progress.setMinimumDuration(0)
            progress.show()

            # Helper function to process a single tile (runs in thread)
            def process_tile(tile_info):
                """Process a single tile and return detections."""
                page_num, vx1, vy1, vx2, vy2, tile_crop, H, W = tile_info
                tile_dets = []

                try:
                    tile_results = detector.detect_all_symbols(tile_crop)
                except Exception:
                    return page_num, tile_dets

                for result in tile_results:
                    if isinstance(result, DetectionResult):
                        x1 = result.bbox[0] + vx1
                        y1 = result.bbox[1] + vy1
                        x2 = result.bbox[2] + vx1
                        y2 = result.bbox[3] + vy1
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0

                        # Only keep if center is within tile bounds
                        if not (vx1 <= cx <= vx2 and vy1 <= cy <= vy2):
                            continue

                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(W, x2)
                        y2 = min(H, y2)

                        if x2 <= x1 or y2 <= y1:
                            continue

                        # Check if this position already has a custom symbol of the same class
                        is_duplicate_position = False
                        if page_num in existing_custom_centers:
                            for (ex_cx, ex_cy, ex_cls) in existing_custom_centers[page_num]:
                                if ex_cls == result.class_name:
                                    dist = ((cx - ex_cx)**2 + (cy - ex_cy)**2) ** 0.5
                                    if dist < 100:
                                        is_duplicate_position = True
                                        break

                        if is_duplicate_position:
                            continue

                        det = {
                            'name': result.class_name,
                            'conf': result.confidence,
                            'x1': int(x1), 'y1': int(y1),
                            'x2': int(x2), 'y2': int(y2),
                            'w': int(x2 - x1), 'h': int(y2 - y1),
                            'cx': cx, 'cy': cy,
                            'angle': result.angle,
                            'detection_method': result.method,
                        }
                        tile_dets.append(det)

                return page_num, tile_dets

            # Prepare all tile tasks
            all_tile_tasks = []
            for page_num, tiles in page_tiles_info.items():
                page_bgr = workspace.page_bgr_arrays[page_num]
                H, W = page_bgr.shape[:2]
                for (vx1, vy1, vx2, vy2), tile_crop in tiles:
                    all_tile_tasks.append((page_num, vx1, vy1, vx2, vy2, tile_crop, H, W))

            # Track new detections and timing
            page_detections = {}  # page_num -> list of detections
            tiles_processed = 0
            start_time = time.time()
            cancelled = False

            # Get max existing row_id
            max_row_id = 0
            if workspace.df_all is not None and not workspace.df_all.empty:
                max_row_id = int(workspace.df_all['row_id'].max())

            # Process tiles in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_tile = {executor.submit(process_tile, task): task for task in all_tile_tasks}

                # Process results as they complete
                for future in as_completed(future_to_tile):
                    if progress.wasCanceled():
                        cancelled = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    try:
                        page_num, tile_dets = future.result()

                        # Collect detections by page
                        if page_num not in page_detections:
                            page_detections[page_num] = []
                        page_detections[page_num].extend(tile_dets)

                    except Exception as e:
                        print(f"   ⚠️ Tile processing error: {e}")

                    tiles_processed += 1

                    # Update progress
                    elapsed = time.time() - start_time
                    if tiles_processed > 0:
                        avg_time = elapsed / tiles_processed
                        remaining = total_tiles - tiles_processed
                        eta_seconds = remaining * avg_time / max_workers  # Adjust for parallelism

                        if eta_seconds < 60:
                            eta_str = f"{int(eta_seconds)}s"
                        else:
                            eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                    else:
                        eta_str = "berechne..."

                    progress.setValue(tiles_processed)
                    progress.setLabelText(
                        f"Template Matching | {tiles_processed}/{total_tiles} Kacheln\n"
                        f"{max_workers} Threads | Verbleibend: ~{eta_str}"
                    )
                    QtWidgets.QApplication.processEvents()

            if cancelled:
                progress.close()
                return

            # Apply NMS for each page's detections (same as full pipeline)
            all_new_detections = []
            for page_num, page_custom_dets in page_detections.items():
                if not page_custom_dets:
                    continue

                unique_names = set(d.get('name', '') for d in page_custom_dets)
                final_page_dets = []

                for name in unique_names:
                    ss = [d for d in page_custom_dets if d.get('name') == name]
                    if not ss:
                        continue
                    boxes = [(d['x1'], d['y1'], d['x2'], d['y2']) for d in ss]
                    scores = [d.get('conf', 0.5) for d in ss]
                    keep = nms(boxes, scores, thr=0.3)
                    kept_dets = [ss[i] for i in keep]

                    # Additional center-based + confidence duplicate removal (same as full pipeline)
                    # Sort by confidence (highest first)
                    kept_dets = sorted(kept_dets, key=lambda d: d.get('conf', 0), reverse=True)
                    filtered = []
                    for det in kept_dets:
                        det_cx = (det['x1'] + det['x2']) / 2
                        det_cy = (det['y1'] + det['y2']) / 2
                        is_dup = False
                        for kept in filtered:
                            kept_cx = (kept['x1'] + kept['x2']) / 2
                            kept_cy = (kept['y1'] + kept['y2']) / 2
                            dist = ((det_cx - kept_cx)**2 + (det_cy - kept_cy)**2) ** 0.5
                            conf_diff = kept.get('conf', 0) - det.get('conf', 0)
                            # If close and lower confidence, skip (same as full pipeline: 200px, 0.05 conf)
                            if dist < 200 and conf_diff > 0.05:
                                is_dup = True
                                break
                        if not is_dup:
                            filtered.append(det)
                    final_page_dets.extend(filtered)

                # Convert to DataFrame rows
                for det_dict in final_page_dets:
                    max_row_id += 1
                    new_row = {
                        'row_id': max_row_id,
                        'page': page_num,
                        'cls': det_dict.get('name', 'custom_symbol'),
                        'x1': det_dict.get('x1', 0),
                        'y1': det_dict.get('y1', 0),
                        'x2': det_dict.get('x2', 0),
                        'y2': det_dict.get('y2', 0),
                        'w': det_dict.get('w', 0),
                        'h': det_dict.get('h', 0),
                        'cx': det_dict.get('cx', 0),
                        'cy': det_dict.get('cy', 0),
                        'conf': det_dict.get('conf', 0.5),
                        'angle': det_dict.get('angle', 0.0),
                        'anchor_text': '',
                        'coord_text': '',
                        'ocr_x1': None,
                        'ocr_y1': None,
                        'ocr_x2': None,
                        'ocr_y2': None,
                        'ocr_region_source': None,
                        'is_new_symbol': True,
                        'is_custom_symbol': True,
                        '_hidden': False,  # Explicitly set to avoid NaN
                        'detection_source': 'CUSTOM',
                        'detection_method': det_dict.get('detection_method', 'template'),
                    }
                    all_new_detections.append(new_row)

            progress.setValue(total_tiles)
            total_time = time.time() - start_time
            progress.close()

            # Debug: Show detection counts
            print(f"\n📊 Detection Summary:")
            print(f"   Total pages processed: {len(page_detections)}")
            total_raw = sum(len(dets) for dets in page_detections.values())
            print(f"   Raw detections before NMS: {total_raw}")
            print(f"   Detections after NMS: {len(all_new_detections)}")

            if not all_new_detections:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine neuen Symbole",
                    f"Keine neuen Symbole gefunden.\n\n"
                    f"Raw detections: {total_raw}\n"
                    f"After NMS: {len(all_new_detections)}\n\n"
                    f"Überprüfen Sie die Schwellenwerte in der Symbol-Definition."
                )
                return

            # Convert to DataFrame
            new_df = pd.DataFrame(all_new_detections)

            # Check for duplicates (same center position within tolerance)
            duplicates_removed = 0
            if workspace.df_all is not None and not workspace.df_all.empty:
                existing_centers = set()
                for _, row in workspace.df_all.iterrows():
                    cx = row.get('cx', (row.get('x1', 0) + row.get('x2', 0)) / 2)
                    cy = row.get('cy', (row.get('y1', 0) + row.get('y2', 0)) / 2)
                    page = row.get('page', 0)
                    # Skip rows with NaN coordinates
                    if pd.isna(cx) or pd.isna(cy) or pd.isna(page):
                        continue
                    # Round to 10 pixels for tolerance
                    key = (page, round(float(cx) / 10), round(float(cy) / 10))
                    existing_centers.add(key)

                # Filter out duplicates
                keep_indices = []
                for idx, row in new_df.iterrows():
                    page = row.get('page', 0)
                    cx = row.get('cx', 0)
                    cy = row.get('cy', 0)
                    # Skip rows with NaN coordinates
                    if pd.isna(cx) or pd.isna(cy) or pd.isna(page):
                        continue
                    key = (page, round(float(cx) / 10), round(float(cy) / 10))
                    if key not in existing_centers:
                        keep_indices.append(idx)
                        existing_centers.add(key)  # Prevent self-duplicates
                    else:
                        duplicates_removed += 1

                new_df = new_df.loc[keep_indices]

            if new_df.empty:
                QtWidgets.QMessageBox.information(
                    self,
                    "Keine neuen Symbole",
                    f"Alle gefundenen Symbole ({duplicates_removed}) existieren bereits."
                )
                return

            # Add anchor bbox columns (ax1, ay1, ax2, ay2) - same as x1, y1, x2, y2 for custom symbols
            new_df['ax1'] = new_df['x1']
            new_df['ay1'] = new_df['y1']
            new_df['ax2'] = new_df['x2']
            new_df['ay2'] = new_df['y2']

            # ========================================================================
            # Link new custom symbols to nearby text (coordinates) from existing data
            # Uses symbol definition settings: links_to_coordinate, coordinate_position, max_link_distance
            # ========================================================================
            print(f"\n🔗 Linking new symbols to existing text...", flush=True)
            linked_count = 0

            for page_num in new_df['page'].unique():
                # Get existing coordinates for this page
                existing_df = workspace.page_dfs.get(page_num)
                if existing_df is None or existing_df.empty:
                    continue

                # Get coordinate detections
                coord_mask = existing_df['cls'] == 'coordinate'
                coords = existing_df[coord_mask]

                if coords.empty:
                    print(f"   Page {page_num}: No coordinates found for linking")
                    continue

                # Get set of coord_texts that are already linked to other anchors
                # A coordinate is "linked" if any non-coordinate element has it in coord_text
                already_linked_coords = set()
                non_coords = existing_df[existing_df['cls'] != 'coordinate']
                if 'coord_text' in non_coords.columns:
                    for _, nc in non_coords.iterrows():
                        ct = nc.get('coord_text', '')
                        if pd.notna(ct) and ct:
                            already_linked_coords.add(str(ct).strip())

                # Convert to list of dicts for linking (excluding already linked)
                coord_list = []
                # DEBUG: Show available columns
                print(f"   📋 Coordinate columns: {list(coords.columns)}")

                for _, c in coords.iterrows():
                    try:
                        # Get coordinates - try multiple column name patterns
                        x1 = None
                        y1 = None
                        x2 = None
                        y2 = None

                        # For coordinates, bbox is stored in cx1/cy1/cx2/cy2
                        # Try coordinate columns first, then anchor columns, then generic
                        for col in ['cx1', 'ax1', 'x1']:
                            if col in c.index and pd.notna(c[col]):
                                x1 = float(c[col])
                                break
                        for col in ['cy1', 'ay1', 'y1']:
                            if col in c.index and pd.notna(c[col]):
                                y1 = float(c[col])
                                break
                        for col in ['cx2', 'ax2', 'x2']:
                            if col in c.index and pd.notna(c[col]):
                                x2 = float(c[col])
                                break
                        for col in ['cy2', 'ay2', 'y2']:
                            if col in c.index and pd.notna(c[col]):
                                y2 = float(c[col])
                                break

                        # Get text - try multiple columns
                        text = ''
                        for col in ['anchor_text', 'coord_text', 'text']:
                            if col in c.index and pd.notna(c[col]) and c[col]:
                                text = str(c[col])
                                break

                        # Skip coordinates that are already linked to other anchors
                        if text.strip() in already_linked_coords:
                            continue

                        # Check all coordinates are valid (not None, not NaN)
                        if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
                            coord_list.append({
                                'cx': (x1 + x2) / 2,
                                'cy': (y1 + y2) / 2,
                                'x1': x1, 'y1': y1,
                                'x2': x2, 'y2': y2,
                                'w': x2 - x1,
                                'h': y2 - y1,
                                'text': text,
                                'name': 'coordinate'
                            })
                        else:
                            print(f"   ⚠️ Coord '{text}' missing position: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
                    except Exception as e:
                        print(f"   ⚠️ Error processing coordinate: {e}")
                        continue

                print(f"   Page {page_num}: {len(coord_list)} unlinked coordinates available")

                # Link each new detection on this page
                page_new = new_df[new_df['page'] == page_num]
                for idx, det in page_new.iterrows():
                    try:
                        det_cx = (det['x1'] + det['x2']) / 2
                        det_cy = (det['y1'] + det['y2']) / 2
                        symbol_name = det.get('cls', '')

                        # Get symbol definition for linking settings
                        symbol_def = detector.symbols.get(symbol_name)

                        # DEBUG: Print symbol definition settings
                        if symbol_def:
                            print(f"   🔍 Symbol '{symbol_name}': links_to_coordinate={symbol_def.links_to_coordinate}, "
                                  f"coord_position={symbol_def.coordinate_position}, max_dist={symbol_def.max_link_distance}")
                        else:
                            print(f"   ⚠️ No symbol definition found for '{symbol_name}'")

                        # ONLY link if symbol definition has links_to_coordinate=True
                        # Skip linking entirely for symbols without this setting
                        if not symbol_def or not symbol_def.links_to_coordinate:
                            print(f"      ⏭️ Skipping coordinate linking (links_to_coordinate=False)")
                            continue

                        max_link_dist = symbol_def.max_link_distance
                        coord_positions = symbol_def.coordinate_position

                        # Handle both string and list for backward compatibility
                        if isinstance(coord_positions, str):
                            coord_positions = [coord_positions]

                        # Find best coordinate based on position preference
                        # Use angle-aware direction checking (same as full pipeline)
                        best_coord = None
                        best_dist = float('inf')

                        # Get symbol's rotation angle (handle NaN)
                        symbol_angle = det.get('angle', 0.0)
                        if pd.isna(symbol_angle) or symbol_angle is None:
                            symbol_angle = 0.0
                        symbol_angle = float(symbol_angle)

                        # Check for NaN in detection coordinates
                        if pd.isna(det_cx) or pd.isna(det_cy):
                            print(f"      ⚠️ Symbol has NaN coordinates, skipping")
                            continue

                        # DEBUG: Show what we're looking for
                        print(f"      Looking for coords within {max_link_dist}px, positions={coord_positions}")

                        for coord in coord_list:
                            dx = coord['cx'] - det_cx
                            dy = coord['cy'] - det_cy
                            dist = (dx**2 + dy**2) ** 0.5

                            if dist > max_link_dist:
                                print(f"      ❌ Coord '{coord.get('text', '?')}' too far: {dist:.0f}px > {max_link_dist}px")
                                continue

                            # Check position constraint with angle-aware direction
                            # Transform dx/dy to symbol's local coordinate system
                            angle_rad = math.radians(symbol_angle)
                            # Inverse rotation to get local coordinates
                            dx_local = dx * math.cos(-angle_rad) - dy * math.sin(-angle_rad)
                            dy_local = dx * math.sin(-angle_rad) + dy * math.cos(-angle_rad)

                            # Check if coordinate is in ANY of the selected positions
                            position_ok = False
                            for pos in coord_positions:
                                if pos == "any":
                                    position_ok = True
                                    break
                                elif pos == "below" and dy_local > 0:
                                    position_ok = True
                                    break
                                elif pos == "above" and dy_local < 0:
                                    position_ok = True
                                    break
                                elif pos == "right" and dx_local > 0:
                                    position_ok = True
                                    break
                                elif pos == "left" and dx_local < 0:
                                    position_ok = True
                                    break
                                elif pos == "right_or_below" and (dx_local >= 0 or dy_local > 0):
                                    position_ok = True
                                    break
                                # Diagonal positions
                                elif pos == "below_right" and dy_local > 0 and dx_local > 0:
                                    position_ok = True
                                    break
                                elif pos == "below_left" and dy_local > 0 and dx_local < 0:
                                    position_ok = True
                                    break
                                elif pos == "above_right" and dy_local < 0 and dx_local > 0:
                                    position_ok = True
                                    break
                                elif pos == "above_left" and dy_local < 0 and dx_local < 0:
                                    position_ok = True
                                    break

                            # DEBUG: Show position check result
                            if not position_ok:
                                print(f"      ❌ Coord '{coord.get('text', '?')}' wrong position: dx={dx_local:.0f}, dy={dy_local:.0f}, need {coord_positions}")
                            else:
                                print(f"      ✓ Coord '{coord.get('text', '?')}' OK: dist={dist:.0f}px, dx={dx_local:.0f}, dy={dy_local:.0f}")

                            if position_ok and dist < best_dist:
                                best_dist = dist
                                best_coord = coord

                        if best_coord and best_coord.get('text'):
                            new_df.at[idx, 'coord_text'] = best_coord['text']
                            linked_count += 1
                            pos_info = f", pos={coord_positions}" if symbol_def else ""
                            print(f"   Linked row {det['row_id']} to coord '{best_coord['text']}' (dist={best_dist:.0f}px{pos_info})")
                            # Remove this coordinate from available pool so it's not linked again
                            coord_list = [c for c in coord_list if c.get('text') != best_coord.get('text')]
                    except Exception as e:
                        print(f"   ⚠️ Error linking detection: {e}")

            print(f"   ✅ Linked {linked_count} symbols to text", flush=True)

            # ========================================================================
            # Run OCR for symbols with has_text=True in their definition
            # Uses the same ocr_custom_symbol_text function as the full pipeline
            # ========================================================================
            print(f"\n📝 Running OCR for symbols with text regions...", flush=True)

            # DEBUG: Show all loaded symbol definitions
            print(f"\n🔍 DEBUG: Symbol definitions loaded in detector:")
            for sym_name, sym_def in detector.symbols.items():
                print(f"  - {sym_name}: has_text={sym_def.has_text}, text_position={sym_def.text_position}, text_region_offset={sym_def.text_region_offset}")

            # DEBUG: Show symbols in new_df
            print(f"\n🔍 DEBUG: Symbols in new_df:")
            for symbol_name in new_df['cls'].unique():
                count = len(new_df[new_df['cls'] == symbol_name])
                print(f"  - {symbol_name}: {count} instances")

            ocr_count = 0

            try:
                from core.ocr_engine import ocr_custom_symbol_text
            except ImportError as e:
                print(f"   ⚠️ OCR not available: {e}")
            else:
                for idx, det in new_df.iterrows():
                    try:
                        symbol_name = det.get('cls', '')
                        symbol_def = detector.symbols.get(symbol_name)

                        # DEBUG: Show why symbols are skipped
                        if not symbol_def:
                            print(f"   ⚠️ SKIP row {det['row_id']} ({symbol_name}): symbol_def is None")
                            continue
                        if not symbol_def.has_text:
                            print(f"   ⚠️ SKIP row {det['row_id']} ({symbol_name}): has_text=False")
                            continue

                        page_num = det['page']
                        page_bgr = workspace.page_bgr_arrays.get(page_num)
                        if page_bgr is None:
                            continue

                        # Build anchor dict for OCR function
                        angle = det.get('angle', 0.0)
                        if pd.isna(angle):
                            angle = 0.0

                        anchor = {
                            'x1': int(det['x1']),
                            'y1': int(det['y1']),
                            'x2': int(det['x2']),
                            'y2': int(det['y2']),
                            'angle': angle,
                            'name': symbol_name,
                        }

                        # DEBUG: Show what we're about to OCR
                        print(f"   🔍 Running OCR for row {det['row_id']} ({symbol_name}):")
                        print(f"      text_position={symbol_def.text_position}")
                        print(f"      text_region_offset={symbol_def.text_region_offset}")

                        # Use the same OCR function as the full pipeline
                        # This handles rotation properly for all angles (0°, 90°, 180°, 270°)
                        # Don't pass search_distance - let it use default 300px like full pipeline
                        # Function now returns (text, bbox, position, confidence)
                        ocr_text, ocr_bbox, ocr_position, ocr_conf = ocr_custom_symbol_text(
                            anchor=anchor,
                            bgr_color=page_bgr,
                            text_position=symbol_def.text_position,
                            engine="paddleocr",
                            text_region_offset=symbol_def.text_region_offset,
                            # search_distance defaults to 300px in the function
                            # search_width defaults to 80px in the function
                        )

                        # DEBUG: Show OCR result
                        print(f"      Result: text='{ocr_text}', ocr_bbox={ocr_bbox}, ocr_position={ocr_position}, ocr_conf={ocr_conf:.2f}")

                        if ocr_text:
                            new_df.at[idx, 'anchor_text'] = ocr_text
                            new_df.at[idx, 'anchor_conf'] = ocr_conf
                            # Store OCR bbox if available
                            if ocr_bbox:
                                new_df.at[idx, 'ocr_x1'] = ocr_bbox[0]
                                new_df.at[idx, 'ocr_y1'] = ocr_bbox[1]
                                new_df.at[idx, 'ocr_x2'] = ocr_bbox[2]
                                new_df.at[idx, 'ocr_y2'] = ocr_bbox[3]
                                new_df.at[idx, 'ocr_region_source'] = ocr_position
                                print(f"      ✅ Stored OCR bbox: ({ocr_bbox[0]:.0f}, {ocr_bbox[1]:.0f}, {ocr_bbox[2]:.0f}, {ocr_bbox[3]:.0f})")
                            ocr_count += 1
                            print(f"   OCR row {det['row_id']}: '{ocr_text}' (angle={angle:.0f}°, pos={ocr_position}, conf={ocr_conf:.2f})")
                        else:
                            # Even if no text found, store bbox if it exists
                            if ocr_bbox:
                                new_df.at[idx, 'ocr_x1'] = ocr_bbox[0]
                                new_df.at[idx, 'ocr_y1'] = ocr_bbox[1]
                                new_df.at[idx, 'ocr_x2'] = ocr_bbox[2]
                                new_df.at[idx, 'ocr_y2'] = ocr_bbox[3]
                                new_df.at[idx, 'ocr_region_source'] = ocr_position
                                print(f"      ⚠️ No text found but stored OCR bbox: ({ocr_bbox[0]:.0f}, {ocr_bbox[1]:.0f}, {ocr_bbox[2]:.0f}, {ocr_bbox[3]:.0f})")
                            else:
                                print(f"      ⚠️ No text found and no OCR bbox returned")

                    except Exception as e:
                        print(f"   ⚠️ OCR error for row {det.get('row_id', '?')}: {e}")

            print(f"   ✅ OCR completed for {ocr_count} symbols", flush=True)

            # ========================================================================
            # Assign fallback names for symbols without text (like YOLO classes do)
            # Format: "{class_name} {counter}" e.g., "Vorsignal 1", "Hauptsignal 2"
            # ========================================================================
            print(f"\n🏷️ Assigning fallback names for symbols without text...", flush=True)

            # First, count existing symbols of each class to get starting counters
            class_counters = {}
            if workspace.df_all is not None and not workspace.df_all.empty:
                for cls_name in new_df['cls'].unique():
                    # Count existing symbols of this class
                    existing_mask = workspace.df_all['cls'] == cls_name
                    existing_count = existing_mask.sum()

                    # Also check for existing numbered names to find highest counter
                    existing_texts = workspace.df_all.loc[existing_mask, 'anchor_text'].dropna()
                    max_counter = 0
                    for txt in existing_texts:
                        # Match pattern like "Vorsignal 5" to extract the number
                        match = re.match(rf'^{re.escape(cls_name)}\s+(\d+)$', str(txt))
                        if match:
                            num = int(match.group(1))
                            if num > max_counter:
                                max_counter = num

                    # Start from highest found counter + 1, or existing_count + 1
                    class_counters[cls_name] = max(max_counter, existing_count) + 1

            # Assign fallback names where anchor_text is empty
            # ⚠️ ONLY for symbols that DON'T need text (has_text=False)
            fallback_count = 0
            for idx, det in new_df.iterrows():
                anchor_text = det.get('anchor_text', '')
                if pd.isna(anchor_text) or str(anchor_text).strip() == '':
                    cls_name = det.get('cls', 'Unknown')

                    # ✅ FIX: Only assign fallback name if symbol doesn't need text
                    # Check if this symbol is defined as NOT needing text
                    symbol_needs_text = False
                    if cls_name in detector.symbols:
                        symbol_needs_text = detector.symbols[cls_name].has_text

                    # Only auto-name if symbol doesn't need text
                    if not symbol_needs_text:
                        # Initialize counter if not present
                        if cls_name not in class_counters:
                            class_counters[cls_name] = 1

                        fallback_name = f"{cls_name} {class_counters[cls_name]}"
                        new_df.at[idx, 'anchor_text'] = fallback_name
                        class_counters[cls_name] += 1
                        fallback_count += 1
                    # else: Leave empty so validation can detect missing text

            if fallback_count > 0:
                print(f"   ✅ Assigned {fallback_count} fallback names", flush=True)

            # ========================================================================
            # Generate detection_ids NOW (after all text fields are finalized)
            # This ensures anchor_text and coord_text are included in the UUID hash
            # ========================================================================
            print(f"\n🔑 Generating detection_ids for comparison support...", flush=True)
            base_layout_name = extract_base_layout_name(workspace.layout_name)
            detection_id_count = 0
            for idx, row in new_df.iterrows():
                element_for_uuid = {
                    'cls': row.get('cls', 'custom_symbol'),
                    'page': row.get('page', 0),
                    'obb_cx': row.get('obb_cx', row.get('cx', 0)),
                    'obb_cy': row.get('obb_cy', row.get('cy', 0)),
                    'anchor_text': row.get('anchor_text', '') or '',
                    'coord_text': row.get('coord_text', '') or '',
                }
                detection_id = generate_deterministic_uuid(element_for_uuid, base_layout_name)
                new_df.at[idx, 'detection_id'] = detection_id
                detection_id_count += 1
            print(f"   ✅ Generated {detection_id_count} detection_ids", flush=True)

            # Append to workspace data
            if workspace.df_all is None or workspace.df_all.empty:
                workspace.df_all = new_df
            else:
                workspace.df_all = pd.concat([workspace.df_all, new_df], ignore_index=True)

            # Update page_dfs AND build row_specs for graphics
            print(f"\n🔧 Updating workspace with {len(new_df)} new detections...", flush=True)

            for page_num in workspace.page_bgr_arrays.keys():
                page_new = new_df[new_df['page'] == page_num]

                if not page_new.empty:
                    # Update page DataFrame
                    if page_num in workspace.page_dfs and workspace.page_dfs[page_num] is not None:
                        workspace.page_dfs[page_num] = pd.concat(
                            [workspace.page_dfs[page_num], page_new],
                            ignore_index=True
                        )
                    else:
                        workspace.page_dfs[page_num] = page_new

                    # Build row_specs for the new detections (needed for graphics overlays)
                    if page_num not in workspace.all_page_row_specs:
                        workspace.all_page_row_specs[page_num] = {}

                    for _, row in page_new.iterrows():
                        row_id = int(row['row_id'])

                        # Build label
                        label = f"{row['cls']} {row.get('conf', 0.5):.2f}"
                        if row.get('anchor_text'):
                            label += f" | {row['anchor_text']}"

                        # Build spec with rectangle
                        x1, y1 = int(row['x1']), int(row['y1'])
                        x2, y2 = int(row['x2']), int(row['y2'])
                        w, h = x2 - x1, y2 - y1

                        angle = row.get('angle', 0.0)
                        if pd.notna(angle) and abs(float(angle)) > 5.0:
                            # Rotated polygon
                            from ui.workspace_widget import bbox_to_rotated_poly
                            pts = bbox_to_rotated_poly(x1, y1, x2, y2, float(angle))
                            spec = {"label": label, "is_poly": True, "pts": pts}
                        else:
                            # Axis-aligned rectangle
                            spec = {"label": label, "is_poly": False, "rect": (x1, y1, w, h)}

                        workspace.all_page_row_specs[page_num][row_id] = spec

            # Full refresh of tree and graphics
            try:
                print(f"\n🔄 Refreshing display...", flush=True)
                # 1. Clear tree selection and repopulate
                workspace.tree.clearSelection()
                if hasattr(workspace, 'item_details_notes'):
                    workspace.item_details_notes.clear()
                workspace._populate_tree(workspace.current_page)

                # 2. Remove existing overlay items from scene (keep only base pixmap)
                if workspace.scene is not None:
                    for item in list(workspace.scene.items()):
                        if not isinstance(item, QtWidgets.QGraphicsPixmapItem):
                            workspace.scene.removeItem(item)

                # 3. Clear and recreate graphics items
                workspace.current_row_items.clear()
                workspace._create_items_for_page(workspace.current_page)

                # 4. Update row count in tree
                if hasattr(workspace.tree, '_update_row_count'):
                    workspace.tree._update_row_count()

                print(f"   ✅ Refresh complete", flush=True)
            except Exception as refresh_err:
                import traceback
                print(f"   ❌ ERROR during refresh: {refresh_err}", flush=True)
                traceback.print_exc()

            # Show success message with timing
            if total_time < 60:
                time_str = f"{total_time:.1f} Sekunden"
            else:
                time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"

            message = f"✅ {len(new_df)} neue Symbol(e) gefunden!\n\n"
            message += f"Verarbeitet: {total_tiles} Kacheln in {time_str}"
            if duplicates_removed > 0:
                message += f"\n({duplicates_removed} Duplikate übersprungen)"

            QtWidgets.QMessageBox.information(
                self,
                "Template Matching abgeschlossen",
                message
            )

            self.statusBar().showMessage(
                f"Template Matching: {len(new_df)} neue Symbole in {time_str}",
                5000
            )

        except ImportError as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Modul nicht gefunden",
                f"Das Symbol-Detector Modul konnte nicht geladen werden:\n{str(e)}"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                f"Fehler beim Template Matching:\n{str(e)}"
            )

    def closeEvent(self, e: QtGui.QCloseEvent):
        """Ask to save all workspaces before closing"""
        if not self.workspaces:
            e.accept()
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Alle Workspaces speichern?",
            f"Es sind {len(self.workspaces)} Gleisplan(e) geöffnet.\n\n"
            "Möchten Sie alle vor dem Schließen speichern?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )
        
        if reply == QtWidgets.QMessageBox.Cancel:
            e.ignore()
            return
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.on_save_all()
        
        e.accept()

    def _show_database_manager(self):
        """Show full database manager dialog."""
        try:
            dialog = DatabaseManagerDialog(self)
            dialog.exec_()
        except Exception as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Öffnen des Datenbank-Managers:\n{str(e)}"
            )

    def _show_help_guide(self):
        from pdfcomparison.dialogs import HelpDialog

        """Show simplified help guide for train technicians"""
        help_text = """
        <h2>Anleitung für die Datenprüfung</h2>

        <h3>📋 Wofür ist dieses Fenster?</h3>
        <p>Hier prüfen und korrigieren Sie die erkannten Daten aus den Gleisplänen.<br>
        Das Programm hat automatisch Text und Symbole erkannt - Sie kontrollieren, ob alles richtig ist.</p>

        <h3>🖥️ Die Arbeitsoberfläche</h3>

        <h4>Links: Plan mit Markierungen</h4>
        <p>Sie sehen den Gleisplan mit bunten Rahmen um erkannte Objekte.</p>
        <ul>
            <li><b>Vergrößern/Verkleinern:</b> Drehen Sie am Mausrad</li>
            <li><b>Plan verschieben:</b> Ziehen Sie mit gedrückter linker Maustaste</li>
            <li><b>Markierung anklicken:</b> Zeigt das Element in der Tabelle rechts</li>
        </ul>

        <h4>Rechts: Datentabelle</h4>
        <p>Alle erkannten Daten als Tabelle - hier können Sie Änderungen vornehmen.</p>

        <h3>✏️ So korrigieren Sie Fehler</h3>

        <h4>Text korrigieren:</h4>
        <ol>
            <li>Doppelklicken Sie auf die fehlerhafte Zelle</li>
            <li>Tippen Sie den richtigen Text ein</li>
            <li>Drücken Sie <b>Enter</b></li>
            <li><b>Wichtig:</b> Speichern nicht vergessen! (siehe unten)</li>
        </ol>

        <h4>Falsche Einträge löschen:</h4>
        <ol>
            <li>Klicken Sie die Zeile an</li>
            <li>Drücken Sie die <b>Entf-Taste</b> auf Ihrer Tastatur</li>
        </ol>

        <h4>Fehlende Symbole nachtragen:</h4>
        <ol>
            <li>Klicken Sie oben auf <b>"➕ Neues Symbol"</b></li>
            <li>Zeichnen Sie ein Rechteck um das Symbol im Plan</li>
            <li>Geben Sie einen Namen ein (z.B. "Weiche_links")</li>
        </ol>

        <h3>💾 Speichern - SEHR WICHTIG!</h3>
        <p><b style="color: #e53e3e;">Speichern Sie regelmäßig Ihre Änderungen!</b></p>
        <ul>
            <li><b>Strg+S:</b> Speichert den aktuellen Plan</li>
            <li>Oder klicken Sie oben auf <b>"💾 Speichern"</b></li>
        </ul>

        <h3>📊 Daten als Excel-Datei exportieren</h3>
        <p>Wenn Sie fertig sind, können Sie die Daten exportieren:</p>
        <ol>
            <li>Drücken Sie <b>Strg+E</b> auf der Tastatur</li>
            <li>Oder klicken Sie oben auf <b>"📊 Excel Export"</b></li>
            <li>Wählen Sie, wo die Datei gespeichert werden soll</li>
            <li>Fertig - jetzt können Sie die Datei in Excel öffnen</li>
        </ol>

        <h3>🔍 Daten suchen und filtern</h3>
        <ul>
            <li><b>Suchen:</b> Klicken Sie auf <b>"🔍 Suchen"</b> und geben Sie ein Suchwort ein</li>
            <li><b>Sortieren:</b> Klicken Sie auf <b>"🔀 Sortieren"</b> - z.B. alphabetisch sortieren</li>
            <li><b>Filtern:</b> Klicken Sie auf <b>"🔍 Filter"</b> - zeigt nur bestimmte Einträge</li>
        </ul>

        <h3>⌨️ Die wichtigsten Tasten</h3>
        <table style="width:100%; border-collapse: collapse;">
            <tr style="background: #f7fafc;">
                <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>Strg+S</b></td>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">Speichern</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>Strg+E</b></td>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">Als Excel exportieren</td>
            </tr>
            <tr style="background: #f7fafc;">
                <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>Strg+F</b></td>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">Suchen</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>Strg+Z</b></td>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">Rückgängig machen</td>
            </tr>
            <tr style="background: #f7fafc;">
                <td style="padding: 8px; border: 1px solid #e2e8f0;"><b>Entf</b></td>
                <td style="padding: 8px; border: 1px solid #e2e8f0;">Zeile löschen</td>
            </tr>
        </table>

        <h3>💡 Wichtige Tipps</h3>
        <ul>
            <li><b>Speichern Sie oft!</b> Am besten nach jeder größeren Änderung</li>
            <li><b>Die Erkennung macht Fehler</b> - Kontrollieren Sie alles genau</li>
            <li><b>Strg+Z macht Fehler rückgängig</b> - Keine Angst vor Experimenten!</li>
            <li><b>Bei Problemen:</b> Fragen Sie einen Kollegen oder IT-Support</li>
        </ul>
        """

        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Bedienungsanleitung - Einfach erklärt", help_text, self)
        help_dialog.exec_()

    def _show_about(self):
        from pdfcomparison.dialogs import HelpDialog

        """Show simplified about dialog"""
        about_text = """
        <div style="text-align: center;">
            <h2>🚂 RailDoc Studio</h2>
            <h3>Datenprüfung und Korrektur</h3>
            <p><b>Version:</b> 1.0</p>
        </div>

        <hr>

        <p><b>Was macht dieses Programm?</b></p>
        <p>RailDoc Studio hilft Ihnen, Gleispläne automatisch zu analysieren und die Daten zu prüfen.<br>
        Sie können erkannte Daten korrigieren und als Excel-Datei exportieren.</p>

        <p><b>Hauptfunktionen:</b></p>
        <ul>
            <li>Automatische Erkennung von Text und Symbolen</li>
            <li>Einfache Korrektur von Fehlern</li>
            <li>Arbeit mit mehreren Plänen gleichzeitig</li>
            <li>Export nach Excel für Weiterverarbeitung</li>
        </ul>

        <hr>

        <p style="text-align: center;">
        <b>Entwickelt von:</b> Utkarsh Swain<br>
        <b>Siemens Mobility GmbH</b><br>
        <i>© 2025 Siemens Mobility GmbH</i>
        </p>
        """

        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Über RailDoc Studio", about_text, self)
        help_dialog.exec_()

    # Add these methods to AuditingWindow:
    def on_find_replace(self):
        """Show find/replace dialog for current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.find_replace()


    def _get_current_tree(self):
        """Helper to get current workspace tree"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        return workspace.tree if workspace else None
    
    # Clipboard operations
    def on_copy(self):
        tree = self._get_current_tree()
        if tree:
            tree.copy_selection()
            self._set_status("Kopiert")
    
    def on_cut(self):
        tree = self._get_current_tree()
        if tree:
            tree.cut_selection()
            self._set_status("Ausgeschnitten")
    
    def on_paste(self):
        tree = self._get_current_tree()
        if tree:
            tree.paste_from_clipboard()
            self._set_status("Eingefügt")
    
    
    # Bulk operations
    def on_bulk_edit(self):
        tree = self._get_current_tree()
        if tree:
            tree.bulk_edit()
    
    def on_clear_cells(self):
        tree = self._get_current_tree()
        if tree:
            tree.clear_cells()
            self._set_status("Zellen geleert")
    
    # Column management
    def on_edit_headers(self):
        tree = self._get_current_tree()
        if tree:
            if tree.edit_headers():
                self._set_status("Überschriften aktualisiert")
    
    def on_manage_columns(self):
        tree = self._get_current_tree()
        if tree:
            if tree.manage_columns():
                self._set_status("Spalten aktualisiert")
    
    # Insert operations
    def on_add_row(self):
        tree = self._get_current_tree()
        if tree:
            tree.add_row()
            self.update_status_bar()
    
    def on_add_column(self):
        tree = self._get_current_tree()
        if tree:
            tree.add_column()
    
    # Delete operations
    def on_delete_column(self):
        tree = self._get_current_tree()
        if tree:
            tree.delete_column()
    
    # Data operations
    def on_sort(self):
        tree = self._get_current_tree()
        if tree:
            tree.show_sort_dialog()
    
    def on_filter(self):
        tree = self._get_current_tree()
        if tree:
            tree.show_filter_dialog()
    
    def on_clear_filter(self):
        tree = self._get_current_tree()
        if tree:
            tree.clear_filter()
            self._set_status("Filter gelöscht")
    
    def on_statistics(self):
        tree = self._get_current_tree()
        if tree:
            tree.show_statistics()
    
    # View operations
    def on_resize_columns(self):
        tree = self._get_current_tree()
        if tree:
            tree.resize_columns_to_contents()
            self._set_status("Spaltenbreite angepasst")
    
    def on_expand_all(self):
        tree = self._get_current_tree()
        if tree:
            tree.expandAll()
    
    def on_collapse_all(self):
        tree = self._get_current_tree()
        if tree:
            tree.collapseAll()
    
    # HelpK
    def show_shortcuts(self):
        """Show keyboard shortcuts dialog"""
        shortcuts_text = """
        TASTENKOMBINATIONEN:
        
        Zwischenablage:
        • Ctrl+C         - Kopieren
        • Ctrl+X         - Ausschneiden
        • Ctrl+V         - Einfügen
        
        Bearbeiten:
        • Ctrl+F         - Suchen und Ersetzen
        • Delete         - Zelleninhalt löschen
        
        Einfügen/Löschen:
        • Ctrl+Shift+N   - Zeile hinzufügen
        • Ctrl+D         - Zeilen löschen
        
        Daten:
        • Ctrl+Shift+F   - Filter
        
        Datei:
        • Ctrl+E         - Exportieren
        • Ctrl+W         - Schließen
        """
        
        QtWidgets.QMessageBox.information(
            self,
            "Tastenkombinationen",
            shortcuts_text
        )
    
    def show_about(self):
        """Show about dialog"""
        QtWidgets.QMessageBox.about(
            self,
            "Über Auditing Window",
            "Auditing Window mit Excel-ähnlichen Funktionen\n\n"
            "Features:\n"
            "• Zeilen/Spalten hinzufügen und löschen\n"
            "• Kopieren, Ausschneiden, Einfügen\n"
            "• Suchen und Ersetzen\n"
            "• Sortieren und Filtern\n"
            "• Massenbearbeitung\n"
            "• Statistiken\n"
        )

    def on_delete_selected_table_rows(self):
        """Delete selected rows from current workspace"""
        tree = self._get_current_tree()
        if not tree:
            return
        
        selected = tree.selectedItems()
        if not selected:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Auswahl",
                "Bitte wählen Sie Zeilen zum Löschen aus."
            )
            return
        
        # Filter out parent items (categories), only delete child rows
        child_items = [item for item in selected if item.childCount() == 0]
        
        if not child_items:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Zeilen ausgewählt",
                "Bitte wählen Sie Datenzeilen (keine Kategorien) zum Löschen aus."
            )
            return
        
        # Confirm deletion
        reply = QtWidgets.QMessageBox.question(
            self,
            "Zeilen löschen",
            f"Möchten Sie {len(child_items)} Zeile(n) wirklich löschen?\n\n"
            "Diese Aktion kann nicht rückgängig gemacht werden.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Get current workspace
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if not workspace:
            return
        
        # Delete items
        row_ids_deleted = []
        for item in child_items:
            parent = item.parent()
            if parent:
                # Get row_id before removing
                row_id = item.data(0, QtCore.Qt.UserRole)
                if row_id is not None:
                    row_ids_deleted.append(row_id)
                
                # Remove from tree
                parent.removeChild(item)
        
        # Remove from workspace data
        if hasattr(workspace, 'df_all') and workspace.df_all is not None:
            workspace.df_all = workspace.df_all[~workspace.df_all['row_id'].isin(row_ids_deleted)]
        
        # Remove from current page df
        if hasattr(workspace, 'page_dfs') and hasattr(workspace, 'current_page'):
            df_page = workspace.page_dfs.get(workspace.current_page)
            if df_page is not None:
                workspace.page_dfs[workspace.current_page] = df_page[~df_page['row_id'].isin(row_ids_deleted)]
        
        # Update UI
        self.update_status_bar()
        self._set_status(f"{len(child_items)} Zeile(n) gelöscht")

    def pop_out_workspace_tab(self, tab_index: int, detach_pos: QtCore.QPoint = None):
        """
        Pop out a workspace tab to a separate window.
        
        Args:
            tab_index: Index of the tab to pop out
            detach_pos: Global position where tab was detached (for drag-out)
        """
        from pdfcomparison.dialogs import WorkspaceWindow
        
        workspace = self.workspaces.get(tab_index)
        if not workspace:
            print(f"[AUDITING] No workspace at tab {tab_index}")
            return
        
        # Check if already popped out
        if hasattr(workspace, 'workspace_window') and workspace.workspace_window is not None:
            # Just bring it to front
            workspace.workspace_window.raise_()
            workspace.workspace_window.activateWindow()
            return
        
        # Get tab name before removing
        tab_name = self.tab_widget.tabText(tab_index)
        
        # Create placeholder widget
        placeholder = QtWidgets.QWidget()
        placeholder.setMinimumSize(workspace.size())
        
        # Create placeholder layout with info
        placeholder_layout = QtWidgets.QVBoxLayout(placeholder)
        placeholder_layout.setAlignment(QtCore.Qt.AlignCenter)
        
        # Icon
        icon_label = QtWidgets.QLabel("📺")
        icon_label.setAlignment(QtCore.Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px;")
        placeholder_layout.addWidget(icon_label)
        
        # Message
        message_label = QtWidgets.QLabel(
            f"Workspace '{os.path.basename(workspace.layout_name)}'\n"
            f"ist in einem separaten Fenster geöffnet.\n\n"
            f"Schließen Sie das Fenster oder klicken Sie mit der\n"
            f"rechten Maustaste auf diesen Tab, um es zurückzuholen."
        )
        message_label.setAlignment(QtCore.Qt.AlignCenter)
        message_label.setStyleSheet("font-size: 14px; color: gray;")
        message_label.setWordWrap(True)
        placeholder_layout.addWidget(message_label)
        
        # Redock button
        redock_btn = QtWidgets.QPushButton("⬅️ Zurück ins Hauptfenster")
        redock_btn.setMaximumWidth(250)
        redock_btn.clicked.connect(lambda: self._redock_workspace(tab_index))
        placeholder_layout.addWidget(redock_btn, alignment=QtCore.Qt.AlignCenter)
        
        # Replace workspace with placeholder in tab
        self.tab_widget.removeTab(tab_index)
        self.tab_widget.insertTab(tab_index, placeholder, f"🪟 {tab_name}")
        
        # Create workspace window
        workspace_window = WorkspaceWindow(self, workspace, tab_index)
        
        # Apply theme
        if self.main_app_ref._current_theme == "dark":
            workspace_window.setStyleSheet(DARK_QSS)
        else:
            workspace_window.setStyleSheet(LIGHT_QSS)
        
        #  Position window on SAME monitor as main window
        if detach_pos:
            # Position near where it was dragged (slightly offset)
            workspace_window.move(detach_pos - QtCore.QPoint(700, 450))
        else:
            # ✅ Position relative to main window (not centered on screen)
            main_window_pos = self.pos()
            main_window_size = self.size()
            
            # Offset to the right of main window
            x = main_window_pos.x() + 50
            y = main_window_pos.y() + 50
            
            workspace_window.move(x, y)
        
        # Store references
        workspace.workspace_window = workspace_window
        workspace.workspace_placeholder = placeholder
        
        # Show window
        workspace_window.show()
        workspace_window.raise_()
        workspace_window.activateWindow()
        
        print(f"[AUDITING] Popped out workspace: {workspace.layout_name}")
        self._set_status(f"🪟 Workspace ausgekoppelt: {os.path.basename(workspace.layout_name)}")

    def _on_workspace_window_closed(self, tab_index: int):
        """
        Callback when a popped-out workspace window is closed.
        
        Args:
            tab_index: Index of the tab that was popped out
        """
        # Find the workspace by checking all workspaces
        workspace = None
        placeholder = None
        
        for idx, ws in self.workspaces.items():
            if hasattr(ws, 'workspace_window') and ws.workspace_window is not None:
                if hasattr(ws.workspace_window, 'tab_index') and ws.workspace_window.tab_index == tab_index:
                    workspace = ws
                    placeholder = ws.workspace_placeholder
                    break
        
        if not workspace:
            print(f"[AUDITING] No workspace found for tab {tab_index}")
            return
        
        print(f"[AUDITING] Redocking workspace: {workspace.layout_name}")
        
        # ✅ FIX: Get original tab name from workspace.layout_name (not from tab text)
        tab_name = os.path.basename(workspace.layout_name)
        
        # Remove placeholder
        if placeholder:
            self.tab_widget.removeTab(tab_index)
            placeholder.deleteLater()
        
        # Re-insert workspace at same position
        workspace.setParent(None)
        self.tab_widget.insertTab(tab_index, workspace, tab_name)
        
        # Clean up references
        workspace.workspace_window = None
        workspace.workspace_placeholder = None
        
        # Switch to the redocked tab
        self.tab_widget.setCurrentIndex(tab_index)
        
        self._set_status(f"✅ Workspace zurückgeholt: {tab_name}")

    def _show_tab_context_menu(self, position):
        """Show context menu for tab bar"""
        # Get the tab index at the clicked position
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(position)
        
        if tab_index < 0:
            return
        
        # Get the workspace
        workspace = self.workspaces.get(tab_index)
        if not workspace:
            return
        
        # Create context menu
        menu = QtWidgets.QMenu(self)
        
        # Check if already popped out
        is_popped_out = hasattr(workspace, 'workspace_window') and workspace.workspace_window is not None
        
        if is_popped_out:
            # Show "Redock" option
            action_redock = menu.addAction("⬅️ Zurück ins Hauptfenster")
            action_redock.triggered.connect(lambda: self._redock_workspace(tab_index))
            
            # Show "Bring to Front" option
            action_front = menu.addAction("🔼 Fenster in den Vordergrund")
            action_front.triggered.connect(lambda: self._bring_workspace_to_front(tab_index))
        else:
            # Show "Pop out" option
            action_popout = menu.addAction("🪟 In separates Fenster verschieben")
            action_popout.triggered.connect(lambda: self.pop_out_workspace_tab(tab_index))
        
        menu.addSeparator()
        
        # Save option
        action_save = menu.addAction("💾 Speichern")
        action_save.triggered.connect(lambda: workspace.save_to_db())
        
        menu.addSeparator()
        
        # Close tab option
        action_close = menu.addAction("❌ Tab schließen")
        action_close.triggered.connect(lambda: self.on_close_tab(tab_index))
        
        # Show menu at cursor position
        menu.exec_(tab_bar.mapToGlobal(position))

    def _redock_workspace(self, tab_index: int):
        """Redock a popped-out workspace"""
        workspace = self.workspaces.get(tab_index)
        if not workspace:
            return
        
        if hasattr(workspace, 'workspace_window') and workspace.workspace_window is not None:
            workspace.workspace_window.close()

    def _bring_workspace_to_front(self, tab_index: int):
        """Bring a popped-out workspace window to front"""
        workspace = self.workspaces.get(tab_index)
        if not workspace:
            return
        
        if hasattr(workspace, 'workspace_window') and workspace.workspace_window is not None:
            workspace.workspace_window.raise_()
            workspace.workspace_window.activateWindow()
            workspace.workspace_window.showNormal()  # Restore if minimized