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
        # Initialize status bar labels FIRST (before creating menus/toolbar)
        self.status_label = None
        self.row_count_label = None
        self.selection_label = None
        # Initialize data structures
        self.workspaces = {}
        self.tree_window = None
        # Tab widget
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.tabCloseRequested.connect(self.on_close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tab_widget)
        # Create UI elements IN THIS ORDER
        self._create_status_bar()  # Create status bar FIRST
        self._create_menus()       # Then menus (which reference status_label)
        self._create_toolbar()     # Then toolbar
        # Track open workspaces
        self.workspaces: Dict[int, WorkspaceWidget] = {}
        self.tab_widget.currentChanged.connect(self.update_status_bar)
        
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
        # Bulk operations
        act_bulk = edit_menu.addAction("✏️ Massenbearbeitung...")
        act_bulk.triggered.connect(self.on_bulk_edit)
        
        act_clear = edit_menu.addAction("🗑️ Zelleninhalt löschen")
        act_clear.setShortcut("Delete")
        act_clear.triggered.connect(self.on_clear_cells)
        
        edit_menu.addSeparator()
        # Column management
        act_edit_headers = edit_menu.addAction("✏️ Spaltenüberschriften bearbeiten")
        act_edit_headers.triggered.connect(self.on_edit_headers)

        act_manage_columns = edit_menu.addAction("📊 Spalten verwalten")
        act_manage_columns.triggered.connect(self.on_manage_columns)
        # Insert Menu
        insert_menu = mb.addMenu("Einfügen")

        act_add_row = insert_menu.addAction("➕ Zeile hinzufügen")
        act_add_row.setShortcut("Ctrl+Shift+N")
        act_add_row.triggered.connect(self.on_add_row)

        act_add_col = insert_menu.addAction("➕ Spalte hinzufügen")
        act_add_col.triggered.connect(self.on_add_column)
        # DELETE MENU
        delete_menu = mb.addMenu("🗑️ Löschen")
        
        act_del_rows = delete_menu.addAction("📝 Zeilen löschen")
        act_del_rows.setShortcut("Ctrl+D")
        act_del_rows.triggered.connect(self.on_delete_selected_table_rows)
        
        act_del_col = delete_menu.addAction("📊 Spalte löschen...")
        act_del_col.triggered.connect(self.on_delete_column)
        # Data Menu
        data_menu = mb.addMenu("Daten")

        act_sort = data_menu.addAction("🔀 Sortieren")
        act_sort.triggered.connect(self.on_sort)

        act_filter = data_menu.addAction("🔍 Filter")
        act_filter.triggered.connect(self.on_filter)

        data_menu.addSeparator()

        act_stats = data_menu.addAction("📈 Statistik")
        act_stats.triggered.connect(self.on_statistics)
        # Compare Menu
        compare_menu = mb.addMenu("Vergleichen")
        
        act_compare = compare_menu.addAction("🔍 Zwei PDFs vergleichen")
        act_compare.triggered.connect(self.on_compare_pdfs)
        
        # View Menu
        view_menu = mb.addMenu("Ansicht")
        act_resize = view_menu.addAction("📏 Spaltenbreite anpassen")
        act_resize.triggered.connect(self.on_resize_columns)
        
        view_menu.addSeparator()
        
        act_expand_all = view_menu.addAction("📂 Alle ausklappen")
        act_expand_all.triggered.connect(self.on_expand_all)
        
        act_collapse_all = view_menu.addAction("📁 Alle einklappen")
        act_collapse_all.triggered.connect(self.on_collapse_all)
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
        # CLIPBOARD SECTION
        act_copy = QtWidgets.QAction("📋", self)
        act_copy.setToolTip("Kopieren (Ctrl+C)")
        act_copy.triggered.connect(self.on_copy)
        toolbar.addAction(act_copy)
        
        act_cut = QtWidgets.QAction("✂️", self)
        act_cut.setToolTip("Ausschneiden (Ctrl+X)")
        act_cut.triggered.connect(self.on_cut)
        toolbar.addAction(act_cut)
        
        act_paste = QtWidgets.QAction("📌", self)
        act_paste.setToolTip("Einfügen (Ctrl+V)")
        act_paste.triggered.connect(self.on_paste)
        toolbar.addAction(act_paste)
        
        toolbar.addSeparator()
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
        # EDIT SECTION
        act_find = QtWidgets.QAction("🔍", self)
        act_find.setToolTip("Suchen und Ersetzen (Ctrl+F)")
        act_find.triggered.connect(self.on_find_replace)
        toolbar.addAction(act_find)
        
        act_bulk = QtWidgets.QAction("✏️", self)
        act_bulk.setToolTip("Massenbearbeitung")
        act_bulk.triggered.connect(self.on_bulk_edit)
        toolbar.addAction(act_bulk)
        
        toolbar.addSeparator()
        # DATA SECTION
        act_sort = QtWidgets.QAction("🔀", self)
        act_sort.setToolTip("Sortieren")
        act_sort.triggered.connect(self.on_sort)
        toolbar.addAction(act_sort)
        
        act_filter = QtWidgets.QAction("🔍", self)
        act_filter.setToolTip("Filter (Ctrl+Shift+F)")
        act_filter.triggered.connect(self.on_filter)
        toolbar.addAction(act_filter)
        
        act_stats = QtWidgets.QAction("📊", self)
        act_stats.setToolTip("Statistik anzeigen")
        act_stats.triggered.connect(self.on_statistics)
        toolbar.addAction(act_stats)
        
        toolbar.addSeparator()
        
        # COLUMN SECTION
        act_headers = QtWidgets.QAction("📝", self)
        act_headers.setToolTip("Spaltenüberschriften bearbeiten")
        act_headers.triggered.connect(self.on_edit_headers)
        toolbar.addAction(act_headers)
        
        act_columns = QtWidgets.QAction("📊", self)
        act_columns.setToolTip("Spalten verwalten")
        act_columns.triggered.connect(self.on_manage_columns)
        toolbar.addAction(act_columns)
        
        toolbar.addSeparator()
        # Export actions
        act_excel = QtWidgets.QAction("📊 Excel", self)
        act_excel.triggered.connect(self.on_export_excel)
        toolbar.addAction(act_excel)
        
        act_json = QtWidgets.QAction("📄 JSON", self)
        act_json.triggered.connect(self.on_export_json)
        toolbar.addAction(act_json)
        
        toolbar.addSeparator()
        # INSERT/DELETE SECTION
        act_add_row = QtWidgets.QAction("➕📝", self)
        act_add_row.setToolTip("Zeile hinzufügen (Ctrl+Shift+N)")
        act_add_row.triggered.connect(self.on_add_row)
        toolbar.addAction(act_add_row)
        
        act_del_row = QtWidgets.QAction("🗑️📝", self)
        act_del_row.setToolTip("Zeilen löschen (Ctrl+D)")
        act_del_row.triggered.connect(self.on_delete_selected_table_rows)
        toolbar.addAction(act_del_row)
        
        toolbar.addSeparator()
        # Compare action
        act_compare = QtWidgets.QAction("🔍 Vergleichen", self)
        act_compare.triggered.connect(self.on_compare_pdfs)
        toolbar.addAction(act_compare)
    
    def _create_status_bar(self):
        """Create status bar with info"""
        self.status_bar = self.statusBar()
        
        # Create labels
        self.status_label = QtWidgets.QLabel("Bereit")
        self.row_count_label = QtWidgets.QLabel("Zeilen: 0")
        self.selection_label = QtWidgets.QLabel("Auswahl: 0")
        
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