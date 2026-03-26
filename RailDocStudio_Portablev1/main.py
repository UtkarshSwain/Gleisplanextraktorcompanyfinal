# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v2.0 (Modular)
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
# PIL CONFIGURATION - MUST BE BEFORE OTHER IMPORTS
# ============================================================================
import os
from PIL import Image, ImageFile

# Disable decompression bomb check for large railway plans
Image.MAX_IMAGE_PIXELS = None  #  Allow unlimited size
ImageFile.LOAD_TRUNCATED_IMAGES = True  #  Handle corrupted images
from PyQt5 import QtCore, QtWidgets
from ui.setup_window import SetupAndRunWindow
from typing import Optional
from ui.auditing_window import AuditingWindow
from utils.dpi_utils import get_adaptive_window_size, center_window
from utils.helpers import _is_deleted
from ui.themes import DARK_QSS, LIGHT_QSS
import sys
from database_sqlite import init_db

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RailDoc Studio - Gleisplan-Modul")

        # Adaptive window sizing for different DPI settings
        w, h = get_adaptive_window_size(300, 200, min_width=300, min_height=200)
        self.resize(w, h)
        center_window(self)

        self.setCentralWidget(QtWidgets.QWidget())
        self.setup_window: Optional[SetupAndRunWindow] = None
        self.auditing_window: Optional[AuditingWindow] = None
        self._current_theme = "dark"
        self._create_menus()
        self._set_theme(self._current_theme)
        self._show_setup_window()

    def _create_menus(self):
        mb = self.menuBar(); view = mb.addMenu("Ansicht")
        view.addAction("Dunkles Thema", lambda: self._set_theme("dark"))
        view.addAction("Helles Thema", lambda: self._set_theme("light"))

    def _set_theme(self, theme: str):
            self._current_theme = theme
            if theme == "dark": QtWidgets.QApplication.instance().setStyleSheet(DARK_QSS)
            elif theme == "light": QtWidgets.QApplication.instance().setStyleSheet(LIGHT_QSS)
            if self.setup_window and self.setup_window.isVisible():
                self.setup_window.scene.clear()
                self.setup_window._display_placeholder(f"Gleisplan geladen (Seite {self.setup_window.current_page or 1})")

            if self.auditing_window and self.auditing_window.isVisible():
                        # Loop through all open workspace tabs and update each one
                        for workspace in self.auditing_window.workspaces.values():
                            workspace._update_graphics_theme()
                            
                            # --- THIS IS THE FIX ---
                            # Force the tree and its header to re-read the new
                            # application-wide stylesheet.
                            
                            # Un-apply the old style
                            workspace.tree.style().unpolish(workspace.tree)
                            workspace.tree.header().style().unpolish(workspace.tree.header())
                            
                            # Apply the new style
                            workspace.tree.style().polish(workspace.tree)
                            workspace.tree.header().style().polish(workspace.tree.header())
                            
                            # Ask the header to repaint
                            workspace.tree.header().update()
                            # --- END FIX ---

    def _get_theme_colors(self):
        """Return theme colors for UI elements."""
        from PyQt5 import QtGui
        if self._current_theme == "dark":
            return (QtGui.QColor("#00cc00"), QtGui.QColor("#cc0000"),
                    QtGui.QColor("#00ffff"), QtGui.QColor("#ffffff"),
                    QtGui.QColor("#333333"))
        else:
            return (QtGui.QColor("#008000"), QtGui.QColor("#ff0000"),
                    QtGui.QColor("#0000ff"), QtGui.QColor("#000000"),
                    QtGui.QColor("#f8f8f8"))

    def _show_setup_window(self):
        if self.setup_window is None:
            self.setup_window = SetupAndRunWindow(self)
            self.setup_window.processing_done.connect(self._handle_processing_done)
            self.setup_window.started_processing.connect(lambda: None)
        self.setup_window.show(); self.hide()


    def _handle_processing_done(self, df_all, page_base_pix, page_dfs, page_bgr_arrays, track_skeleton, exception, from_database=False, uncertain_detections=None, learned_patterns=None):
            """Handle processing completion"""

            # Hide progress window
            if hasattr(self, 'progress_window') and self.progress_window:
                self.progress_window.close()
                self.progress_window = None

            # Handle exceptions
            if exception:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Verarbeitungsfehler",
                    f"Fehler bei der Verarbeitung:\n{str(exception)}"
                )
                return

            # Check if we got data
            if df_all is None or df_all.empty:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Keine Daten",
                    "Keine Detektionen gefunden."
                )
                return

            # Get layout name from PDF path (just filename, not full path)
            layout_name = os.path.basename(self.setup_window.pdf_path)

            # Check if the auditing window is None or has been closed by the user
            if self.auditing_window is None or _is_deleted(self.auditing_window):
                self.auditing_window = AuditingWindow(self)

            # Always make sure the window is visible and brought to the front
            self.auditing_window.show()
            self.auditing_window.raise_()
            self.auditing_window.activateWindow()

            # Add as new tab (NOT replacing!) - SINGLE CALL WITH TRACK SKELETON
            self.auditing_window.add_workspace(
                layout_name,
                df_all,
                page_base_pix,
                page_dfs,
                page_bgr_arrays,
                track_skeleton,
                from_database,
                uncertain_detections or [],
                learned_patterns
            )
            
            # Keep setup window open for processing more PDFs
            self.setup_window.show()
            self.setup_window.raise_()

def main():
    # ============================================================================
    # HIGH DPI SUPPORT - Must be set BEFORE QApplication creation
    # ============================================================================

    # Enable High DPI scaling (Qt 5.6+) - allows automatic DPI adaptation
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

    # Use high DPI pixmaps for crisp icons/images (Qt 5.6+)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # Enable fractional scaling for 125%, 150% DPI (Qt 5.14+)
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    # Set rounding policy for fractional scaling (Qt 5.14+)
    # PassThrough prevents rounding fractional scales to nearest integer
    if hasattr(QtWidgets.QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QtWidgets.QApplication(sys.argv)

    # Fusion style scales better than native OS styles
    app.setStyle('Fusion')

    # --- ADD THIS HERE ---
    # Set the password in your environment before running
    # In Windows: set DB_PASSWORD="your_strong_password_here"
    try:
        init_db() # <-- Initialize database tables on startup
    except Exception as e:
        print(f"CRITICAL: Failed to initialize database: {e}")
        # Optionally show an error message box here
        return # Exit if DB connection fails
    # --- END OF CHANGE ---
    
    w = MainWindow()
    # w.show() is handled by your _show_setup_window()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
