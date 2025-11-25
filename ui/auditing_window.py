from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Dict, Tuple, Optional, Any
import os 
from ui.themes import DARK_QSS,LIGHT_QSS
import pandas as pd
import numpy as np
class AuditingWindow(QtWidgets.QMainWindow):

    """Main window that holds multiple workspace tabs - NO VERSIONING"""

    def __init__(self, main_app_ref: 'MainWindow'):
        from main import MainWindow

        from ui.workspace_widget import WorkspaceWidget

        super().__init__()
        self.main_app_ref = main_app_ref
        self.setWindowTitle("Gleisplan Auditing - Multi-PDF")
        self.resize(1400, 900)
        
        # Tab widget
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.on_close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tab_widget)
        
        # Track open workspaces
        self.workspaces: Dict[int, WorkspaceWidget] = {}
        
        # Build menus and toolbars
        self._create_menus()
        self._create_toolbar()
        
        self.statusBar().showMessage("Bereit - Öffnen Sie mehrere PDFs")
    
    def add_workspace(self, layout_name: str, df_all: pd.DataFrame,
                    page_base_pix: Dict, page_dfs: Dict, page_bgr_arrays: Dict, 
                    track_skeleton: Optional[np.ndarray] = None):
        """Add a new PDF workspace as a tab"""
        from ui.workspace_widget import WorkspaceWidget

        # Check if already open
        for idx, ws in self.workspaces.items():
            if ws.layout_name == layout_name:
                self.tab_widget.setCurrentIndex(idx)
                self.statusBar().showMessage(f"{layout_name} bereits geöffnet")
                return
        
        # Create workspace widget
        workspace = WorkspaceWidget(self, layout_name)
        workspace.load_data(df_all, page_base_pix, page_dfs, page_bgr_arrays, track_skeleton)
        
        # Add as tab (use short filename for tab label)
        tab_label = os.path.basename(layout_name)
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
            self.statusBar().showMessage("Alle Tabs geschlossen - Öffnen Sie ein PDF")
    
    def on_tab_changed(self, index: int):
            """Update UI when switching tabs"""
            if index < 0:
                # --- ADD THIS ---
                self.statusBar().showMessage("Bereit - Öffnen Sie ein PDF")
                # --- END ADD ---
                return
            
            workspace = self.workspaces.get(index)
            if workspace:
                # --- UPDATE THIS LINE ---
                self.statusBar().showMessage(f"Bereit: {os.path.basename(workspace.layout_name)}")
    
    def _create_menus(self):
        """Create menu bar"""
        mb = self.menuBar()
        
        # File Menu
        file_menu = mb.addMenu("Datei")
        
        act_save = file_menu.addAction("💾 Aktuelle speichern")
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.on_save_current)
        
        act_save_all = file_menu.addAction("💾 Alle speichern")
        act_save_all.setShortcut("Ctrl+Shift+S")
        act_save_all.triggered.connect(self.on_save_all)
        
        file_menu.addSeparator()
        
        act_export_excel = file_menu.addAction("📊 Excel Export")
        act_export_excel.setShortcut("Ctrl+E")
        act_export_excel.triggered.connect(self.on_export_excel)
        
        act_export_json = file_menu.addAction("📄 JSON Export")
        act_export_json.setShortcut("Ctrl+J")
        act_export_json.triggered.connect(self.on_export_json)
        
        file_menu.addSeparator()
        
        act_close_tab = file_menu.addAction("❌ Tab schließen")
        act_close_tab.setShortcut("Ctrl+W")
        act_close_tab.triggered.connect(lambda: self.on_close_tab(self.tab_widget.currentIndex()))
        # Edit Menu
        edit_menu = mb.addMenu("Bearbeiten")

        act_find = edit_menu.addAction("🔍 Suchen und Ersetzen")
        act_find.setShortcut("Ctrl+F")
        act_find.triggered.connect(self.on_find_replace)

        act_copy = edit_menu.addAction("📋 Kopieren")
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.on_copy)

        act_paste = edit_menu.addAction("📌 Einfügen")
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.on_paste)

        edit_menu.addSeparator()

        act_edit_headers = edit_menu.addAction("✏️ Spaltenüberschriften bearbeiten")
        act_edit_headers.triggered.connect(self.on_edit_headers)

        act_manage_columns = edit_menu.addAction("📊 Spalten verwalten")
        act_manage_columns.triggered.connect(self.on_manage_columns)
        # Compare Menu
        compare_menu = mb.addMenu("Vergleichen")
        
        act_compare = compare_menu.addAction("🔍 Zwei PDFs vergleichen")
        act_compare.triggered.connect(self.on_compare_pdfs)
        
        # View Menu
        view_menu = mb.addMenu("Ansicht")
        view_menu.addAction("Dunkles Thema", lambda: self.main_app_ref._set_theme("dark"))
        view_menu.addAction("Helles Thema", lambda: self.main_app_ref._set_theme("light"))

        # --- HILFE-MENÜ HINZUFÜGEN ---
        help_menu = mb.addMenu("Hilfe")
        help_menu.addAction("📖 Bedienungsanleitung", self._show_help_guide)
        help_menu.addSeparator()
        help_menu.addAction("ℹ Über", self._show_about)
    
    def _create_toolbar(self):
        """Create toolbar"""
        toolbar = self.addToolBar("Hauptwerkzeuge")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(24, 24))
        
        # Save actions
        act_save = QtWidgets.QAction("💾 Speichern", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.on_save_current)
        toolbar.addAction(act_save)
        
        act_save_all = QtWidgets.QAction("💾 Alle speichern", self)
        act_save_all.setShortcut("Ctrl+Shift+S")
        act_save_all.triggered.connect(self.on_save_all)
        toolbar.addAction(act_save_all)
        
        toolbar.addSeparator()
        # Edit actions
        act_find = QtWidgets.QAction("🔍 Suchen", self)
        act_find.setShortcut("Ctrl+F")
        act_find.setToolTip("Suchen und Ersetzen (Ctrl+F)")
        act_find.triggered.connect(self.on_find_replace)
        toolbar.addAction(act_find)

        act_headers = QtWidgets.QAction("✏️ Überschriften", self)
        act_headers.setToolTip("Spaltenüberschriften bearbeiten")
        act_headers.triggered.connect(self.on_edit_headers)
        toolbar.addAction(act_headers)

        act_columns = QtWidgets.QAction("📊 Spalten", self)
        act_columns.setToolTip("Spalten ein-/ausblenden")
        act_columns.triggered.connect(self.on_manage_columns)
        toolbar.addAction(act_columns)
        # Export actions
        act_excel = QtWidgets.QAction("📊 Excel", self)
        act_excel.triggered.connect(self.on_export_excel)
        toolbar.addAction(act_excel)
        
        act_json = QtWidgets.QAction("📄 JSON", self)
        act_json.triggered.connect(self.on_export_json)
        toolbar.addAction(act_json)
        
        toolbar.addSeparator()
        
        # Compare action
        act_compare = QtWidgets.QAction("🔍 Vergleichen", self)
        act_compare.triggered.connect(self.on_compare_pdfs)
        toolbar.addAction(act_compare)
    
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
        from ui.dialogs import SimplePDFCompareDialog

        """Compare two open PDFs"""
        if len(self.workspaces) < 2:
            QtWidgets.QMessageBox.information(
                self,
                "Nicht genug PDFs",
                "Bitte öffnen Sie mindestens 2 PDFs zum Vergleichen.\n\n"
                "Tipp: Öffnen Sie z.B. 'layout_v1.pdf' und 'layout_v2.pdf'"
            )
            return
        
        # Show comparison dialog
        dialog = SimplePDFCompareDialog(self)
        
        # --- ADD THIS BLOCK ---
        # Apply the current theme to the new dialog
        if self.main_app_ref._current_theme == "dark":
            dialog.setStyleSheet(DARK_QSS)
        else:
            dialog.setStyleSheet(LIGHT_QSS)
        # --- END ADD ---
        
        dialog.exec_()
    
    def closeEvent(self, e: QtGui.QCloseEvent):
        """Ask to save all workspaces before closing"""
        if not self.workspaces:
            e.accept()
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Alle Workspaces speichern?",
            f"Es sind {len(self.workspaces)} PDF(s) geöffnet.\n\n"
            "Möchten Sie alle vor dem Schließen speichern?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )
        
        if reply == QtWidgets.QMessageBox.Cancel:
            e.ignore()
            return
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.on_save_all()
        
        e.accept()

    def _show_help_guide(self):
        from ui.dialogs import HelpDialog

        """Show help guide for AuditingWindow and WorkspaceWidget"""
        help_text = """
        <h2>Auditing - Bedienungsanleitung</h2>
        
        <h3>Übersicht</h3>
        <p>Dieses Fenster ist Ihr Hauptarbeitsbereich zur Überprüfung und Korrektur der extrahierten Daten. Jedes analysierte PDF wird in einem eigenen Tab dargestellt.</p>
        
        <h3>Tab-Navigation</h3>
        <ul>
            <li>Klicken Sie auf die Tab-Namen, um zwischen verschiedenen PDF-Analysen zu wechseln.</li>
            <li>Sie können Tabs ziehen, um ihre Reihenfolge zu ändern.</li>
            <li>Klicken Sie auf das 'X' neben einem Tab oder drücken Sie <b>Strg+W</b>, um ihn zu schließen. Sie werden gefragt, ob Sie Änderungen speichern möchten.</li>
        </ul>
        
        <h3>Workspace-Bereich (In jedem Tab)</h3>
        <p>Jeder Tab enthält einen detaillierten Workspace für ein einzelnes PDF. Hier können Sie:</p>
        <ul>
            <li><b>Seiten wechseln:</b> Verwenden Sie die Pfeile oder geben Sie eine Seitenzahl ein.</li>
            <li><b>Grafikansicht:</b> Zeigt die PDF-Seite mit allen erkannten Objekten an. Zoomen, verschieben und Elemente anklicken.</li>
            <li><b>Detektions-Baum:</b> Eine Tabelle aller erkannten Elemente, gruppiert nach Klassen. Hier können Sie Texte bearbeiten, filtern und Elemente löschen.</li>
            <li><b>Manuelle Korrekturen:</b> Nutzen Sie "Manuelles OCR" zum Korrigieren von Texten oder "Koordinate manuell verknüpfen" zum Verbinden von Elementen.</li>
            <li><b>Notizen:</b> Fügen Sie detaillierte Notizen zu jedem Element hinzu.</li>
            <li><b>Auskoppeln:</b> Rechtsklicken Sie auf die Grafikansicht oder den Detektions-Baum, um sie in ein separates Fenster zu verschieben.</li>
        </ul>
        
        <h3>Menü & Symbolleiste</h3>
        <ul>
            <li><b>Speichern:</b> Speichern Sie den aktuellen oder alle Workspaces in der Datenbank.</li>
            <li><b>Export:</b> Exportieren Sie Daten nach Excel (<b>Strg+E</b>) oder JSON (<b>Strg+J</b>).</li>
            <li><b>Vergleichen:</b> Starten Sie einen Vergleich zwischen zwei geöffneten PDFs (siehe "PDFs vergleichen" Hilfe).</li>
            <li><b>Ansicht:</b> Wechseln Sie zwischen dunklem und hellem Thema.</li>
        </ul>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Bedienungsanleitung - Auditing", help_text, self)
        help_dialog.exec_()

    def _show_about(self):
        from ui.dialogs import HelpDialog

        """Show about dialog for AuditingWindow"""
        about_text = """
        <h2>Gleisplan Datenextraktion</h2>
        <h3>Auditing Modul</h3>
        <p><b>Version:</b> 1.0</p>
        
        <p>Dieses Modul bietet eine umfassende Oberfläche zur Überprüfung, Korrektur und Verwaltung
        der aus Gleisplan-PDFs extrahierten Daten.</p>
        
        <p><i>© 2025 - Siemens AG</i></p>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Über - Auditing", about_text, self)
        help_dialog.exec_()

    # Add these methods to AuditingWindow:
    def on_find_replace(self):
        """Show find/replace dialog for current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.find_replace()

    def on_copy(self):
        """Copy selection in current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.copy_selection()

    def on_paste(self):
        """Paste in current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.paste_from_clipboard()

    def on_edit_headers(self):
        """Edit column headers for current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.edit_headers()

    def on_manage_columns(self):
        """Manage column visibility for current workspace"""
        idx = self.tab_widget.currentIndex()
        workspace = self.workspaces.get(idx)
        if workspace:
            workspace.tree.manage_columns()
