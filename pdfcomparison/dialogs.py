# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Dialog windows for PDF comparison functionality.
"""
from PyQt5 import QtCore, QtGui, QtWidgets
from ui.workspace_widget import WorkspaceWidget
from ui.graphics_view import InteractiveGraphicsView
from ui.auditing_window import AuditingWindow
from ui.tree_widget import AuditingTreeWidget
import pandas as pd
import math
from typing import List, Dict, Tuple, Optional, Any
import os
from pdfcomparison.comparison_engine import LayoutComparisonEngine, ElementChange, ChangeType


class GraphicsWindow(QtWidgets.QMainWindow):
    def __init__(self, main_window: 'WorkspaceWidget', graphics_view: 'InteractiveGraphicsView'):
        super().__init__()
        self.setWindowTitle("Grafikansicht")
        self.resize(1000, 800)
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(graphics_view)
        graphics_view.setParent(central)
        self._on_close = main_window._on_graphics_window_closed

    def closeEvent(self, e: QtGui.QCloseEvent):
        try: self._on_close()
        finally: super().closeEvent(e)

class HelpDialog(QtWidgets.QDialog):
    def __init__(self, title: str, content_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)

        # Window flags
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )

        main_layout = QtWidgets.QVBoxLayout(self)

        # Text display area
        self.text_edit = QtWidgets.QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setHtml(content_html)
        self.text_edit.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        main_layout.addWidget(self.text_edit)

        # Close button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)


class TreeWindow(QtWidgets.QMainWindow):
    """Replaces TableWindow"""
    def __init__(self, main_window: 'WorkspaceWidget', tree_view: 'AuditingTreeWidget'):
        super().__init__()
        self.setWindowTitle("Detections Tree")
        self.resize(900, 700)
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(tree_view); tree_view.setParent(central)
        self.tree_view = tree_view 

        tree_view.itemSelectionChanged.connect(main_window.on_tree_selection_changed)
        self._on_close = main_window._on_tree_window_closed
    
    def closeEvent(self, e: QtGui.QCloseEvent):
        try: self._on_close()
        finally: super().closeEvent(e)

class WorkspaceWindow(QtWidgets.QMainWindow):
    """Separate window for a popped-out workspace - for multi-monitor comparison"""
    
    closed = QtCore.pyqtSignal()
    
    def __init__(self, parent_auditing: 'AuditingWindow', workspace_widget: 'WorkspaceWidget', tab_index: int):
        super().__init__()
        
        self.parent_auditing = parent_auditing
        self.workspace_widget = workspace_widget
        self.tab_index = tab_index
        
        # Set window title
        short_name = os.path.basename(workspace_widget.layout_name)
        self.setWindowTitle(f"Workspace: {short_name}")
        
        # Set size (same as main window)
        self.resize(1400, 900)
        
        #  FIX: Create central widget properly
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)  #  Small margins
        main_layout.setSpacing(5)
        
        redock_btn = QtWidgets.QPushButton("⬅ Zurück ins Hauptfenster")
        redock_btn.setToolTip("Workspace zurück in Tab-Ansicht verschieben")
        redock_btn.setMaximumHeight(30)
        redock_btn.clicked.connect(self.redock_workspace)
        main_layout.addWidget(redock_btn)

        workspace_widget.setParent(central)
        main_layout.addWidget(workspace_widget)
        workspace_widget.setVisible(True)
        workspace_widget.show()

        self._on_close = parent_auditing._on_workspace_window_closed
    
    def redock_workspace(self):
        """Redock workspace back into main window"""
        print(f"[WORKSPACE_WINDOW] Redocking workspace")
        self.close()
    
    def closeEvent(self, e: QtGui.QCloseEvent):
        """Handle window close"""
        try:
            self._on_close(self.tab_index)
        finally:
            super().closeEvent(e)
# ============================================================================
# MODIFIED: SimplePDFCompareDialog - Focus on meaningful changes
# ============================================================================
class SimplePDFCompareDialog(QtWidgets.QDialog):
    """Compare two open Gleisplan tabs - for user-managed versions"""

    def __init__(self, parent: AuditingWindow):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Gleispläne vergleichen")
        self.resize(900, 700)

        # Store comparison results for export
        self._comparison_results = None
        self._layout_name1 = None
        self._layout_name2 = None

        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        info_label = QtWidgets.QLabel(
            " Wählen Sie zwei geöffnete Gleispläne zum Vergleichen:\n"
            "(z.B. 'layout_v1' und 'layout_v2')\n\n"
            " Vergleicht: Klassen, Koordinatenwerte, hinzugefügte/gelöschte Elemente"
        )
        info_label.setObjectName("compareInfoLabel")
        layout.addWidget(info_label)

        help_button = QtWidgets.QPushButton("?")
        help_button.setFixedSize(24, 24)
        help_button.setToolTip("Hilfe zu diesem Dialog")
        help_button.clicked.connect(self._show_help)

        info_layout = QtWidgets.QHBoxLayout()
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        info_layout.addWidget(help_button)
        layout.addLayout(info_layout)
        
        # Gleisplan selectors (side by side)
        selector_layout = QtWidgets.QHBoxLayout()

        # Left Gleisplan
        left_box = QtWidgets.QGroupBox("Gleisplan 1 (Alt)")
        left_layout = QtWidgets.QVBoxLayout(left_box)
        self.pdf1_combo = QtWidgets.QComboBox()
        left_layout.addWidget(self.pdf1_combo)
        selector_layout.addWidget(left_box)

        # Right Gleisplan
        right_box = QtWidgets.QGroupBox("Gleisplan 2 (Neu)")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        self.pdf2_combo = QtWidgets.QComboBox()
        right_layout.addWidget(self.pdf2_combo)
        selector_layout.addWidget(right_box)
        
        layout.addLayout(selector_layout)
        
        # Compare button
        self.btn_compare = QtWidgets.QPushButton(" Vergleichen")
        self.btn_compare.clicked.connect(self.on_compare)
        layout.addWidget(self.btn_compare)
        
        # Results area (tabbed view)
        self.results_tabs = QtWidgets.QTabWidget()
        
        # Summary tab
        self.summary_text = QtWidgets.QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.results_tabs.addTab(self.summary_text, " Zusammenfassung")
        
        # Added tab
        self.added_table = QtWidgets.QTableWidget()
        self.added_table.setColumnCount(5)
        self.added_table.setHorizontalHeaderLabels(["Klasse", "Text", "Koordinate", "Koordinatenwert", "Seite"])
        self.added_table.horizontalHeader().setStretchLastSection(False)
        self.added_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.added_table.itemSelectionChanged.connect(self._on_table_selection_changed)  
        self.results_tabs.addTab(self.added_table, " Hinzugefügt")
        
        # Deleted tab
        self.deleted_table = QtWidgets.QTableWidget()
        self.deleted_table.setColumnCount(5)
        self.deleted_table.setHorizontalHeaderLabels(["Klasse", "Text", "Koordinate", "Koordinatenwert", "Seite"])
        self.deleted_table.horizontalHeader().setStretchLastSection(False)
        self.deleted_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.deleted_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_tabs.addTab(self.deleted_table, " Gelöscht")

        # Moved tab (FA-011: Verschoben - coord_value changed = element moved along track)
        self.moved_table = QtWidgets.QTableWidget()
        self.moved_table.setColumnCount(5)
        self.moved_table.setHorizontalHeaderLabels(["Klasse", "Kennung", "Alte km-Position", "Neue km-Position", "Seite"])
        self.moved_table.horizontalHeader().setStretchLastSection(False)
        self.moved_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.moved_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_tabs.addTab(self.moved_table, "↔ Verschoben")

        layout.addWidget(self.results_tabs)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()

        # Export button
        self.export_btn = QtWidgets.QPushButton(" Exportieren")
        self.export_btn.setToolTip("Vergleichsergebnisse als Excel exportieren")
        self.export_btn.setEnabled(False)  # Disabled until comparison is run
        self.export_btn.clicked.connect(self._export_results)
        button_layout.addWidget(self.export_btn)

        button_layout.addStretch()

        # Close button
        close_btn = QtWidgets.QPushButton("Schließen")
        close_btn.clicked.connect(self.reject)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        # Load available Gleispläne
        self._load_pdfs()

    def _on_table_selection_changed(self):
        """Handle table row selection - highlight in layout view"""
        sender = self.sender()
        
        if not sender:
            return
        
        selected_items = sender.selectedItems()
        if not selected_items:
            return
        
        # Get the first column item (contains the change object)
        row = selected_items[0].row()
        first_col_item = sender.item(row, 0)
        
        if not first_col_item:
            return
        
        # Retrieve the stored ElementChange object
        change = first_col_item.data(QtCore.Qt.UserRole)
        
        if not change:
            return
        
        # Determine which workspace to highlight in
        current_tab = self.results_tabs.currentIndex()

        if current_tab == 1:  # Added tab
            self._highlight_in_workspace(change, is_new=True)
        elif current_tab == 2:  # Deleted tab
            self._highlight_in_workspace(change, is_new=False)
        elif current_tab == 3:  # Moved tab (FA-011: Verschoben)
            # Check which column was clicked to determine primary workspace
            clicked_col = selected_items[0].column() if selected_items else 0
            # Column 2 = "Alte km-Position" → go to OLD workspace first
            # Column 3 = "Neue km-Position" → go to NEW workspace first
            is_new_primary = (clicked_col != 2)  # Default to new, unless "Alte" column clicked
            self._highlight_in_workspace(change, is_new=is_new_primary, show_both=True)

    def _highlight_in_workspace(self, change: ElementChange, is_new: bool, show_both: bool = False):
        """
        Highlight the changed element in the appropriate workspace.
        
        Args:
            change: The ElementChange object
            is_new: True to highlight in new workspace, False for old
            show_both: If True, highlight in both workspaces (for modified elements)
        """
        # Get the appropriate workspace
        if is_new:
            workspace = self.pdf2_combo.currentData()
            data = change.new_data
        else:
            workspace = self.pdf1_combo.currentData()
            data = change.old_data
        
        if not workspace or not data:
            print(f"[DIALOG] No workspace or data for {'new' if is_new else 'old'}")
            return
        
        # Get the page number and row_id
        page = data.get('page', 1)
        row_id = data.get('row_id')
        
        if row_id is None:
            print(f"[DIALOG] No row_id in data")
            return
        
        print(f"[DIALOG] Highlighting row_id {row_id} on page {page} in {'new' if is_new else 'old'} workspace")
        
        #  CRITICAL: Switch to the correct workspace tab first
        parent_window = self.parent_window
        
        if hasattr(parent_window, 'tab_widget'):
            # Find the workspace tab index
            workspace_index = -1
            
            for i in range(parent_window.tab_widget.count()):
                if parent_window.tab_widget.widget(i) == workspace:
                    workspace_index = i
                    break
            
            if workspace_index >= 0:
                # Switch to this workspace tab
                parent_window.tab_widget.setCurrentIndex(workspace_index)
                print(f"[DIALOG] Switched to workspace tab {workspace_index}")
            else:
                print(f"[DIALOG] WARNING: Could not find workspace in tabs")
        
        #  Switch to the correct page within the workspace
        if hasattr(workspace, 'switch_to_page'):
            workspace.switch_to_page(page)
        elif hasattr(workspace, 'page_spin'):
            # Manual page switching if switch_to_page doesn't exist
            workspace.page_spin.setValue(page)
            print(f"[DIALOG] Switched to page {page}")
        
        # Small delay to ensure page has loaded
        # CRITICAL: Use default arguments to capture values by VALUE, not reference
        QtCore.QTimer.singleShot(100, lambda ws=workspace, rid=row_id: self._do_highlight(ws, rid))
        
        #  If show_both, also highlight in the other workspace
        if show_both:
            other_workspace = self.pdf1_combo.currentData() if is_new else self.pdf2_combo.currentData()
            other_data = change.old_data if is_new else change.new_data
            
            if other_workspace and other_data:
                other_row_id = other_data.get('row_id')
                other_page = other_data.get('page', 1)
                
                if other_row_id is not None:
                    # Switch to other workspace tab
                    if hasattr(parent_window, 'tab_widget'):
                        for i in range(parent_window.tab_widget.count()):
                            if parent_window.tab_widget.widget(i) == other_workspace:
                                # Don't switch tabs for "other" workspace, just highlight
                                # User can manually switch to see it
                                pass
                    
                    # Switch page
                    if hasattr(other_workspace, 'switch_to_page'):
                        other_workspace.switch_to_page(other_page)
                    elif hasattr(other_workspace, 'page_spin'):
                        other_workspace.page_spin.setValue(other_page)
                    
                    # Highlight with delay
                    # CRITICAL: Use default arguments to capture values by VALUE, not reference
                    QtCore.QTimer.singleShot(150, lambda ws=other_workspace, rid=other_row_id: self._do_highlight(ws, rid))

    def _do_highlight(self, workspace, row_id: int):
        """
        Actually perform the highlight after workspace/page switching.
        
        Args:
            workspace: The workspace widget
            row_id: The row_id to highlight
        """
        # Highlight in the tree view
        if hasattr(workspace, 'tree') and workspace.tree:
            workspace.tree.highlight_row(row_id)
        
        # Highlight in the graphics view
        if hasattr(workspace, 'view') and workspace.view:
            workspace.view.highlight_detection(row_id)


    def _show_help(self):
        """Show help for the SimplePDFCompareDialog"""
        help_text = """
        <h2>Gleispläne vergleichen - Hilfe</h2>

        <h3>Zweck</h3>
        <p>Dieser Dialog ermöglicht es Ihnen, die Analyseergebnisse von zwei geöffneten Gleisplänen gegenüberzustellen und Änderungen zwischen ihnen zu identifizieren.</p>

        <h3>Verwendung</h3>
        <ol>
            <li>Wählen Sie im Feld <b>"Gleisplan 1 (Alt)"</b> den älteren oder Referenz-Gleisplan aus.</li>
            <li>Wählen Sie im Feld <b>"Gleisplan 2 (Neu)"</b> den neueren oder zu vergleichenden Gleisplan aus.</li>
            <li>Klicken Sie auf <b>" Vergleichen"</b>.</li>
        </ol>

        <h3>Vergleichsergebnisse</h3>
        <p>Die Ergebnisse werden in verschiedenen Tabs angezeigt:</p>
        <ul>
            <li><b> Zusammenfassung:</b> Ein Überblick über die Anzahl der Änderungen.</li>
            <li><b> Hinzugefügt:</b> Elemente, die in Gleisplan 2 (Neu) vorhanden sind, aber nicht in Gleisplan 1 (Alt).</li>
            <li><b> Gelöscht:</b> Elemente, die in Gleisplan 1 (Alt) vorhanden waren, aber in Gleisplan 2 (Neu) fehlen.</li>
            <li><b>↔ Verschoben:</b> Elemente mit gleicher Kennung, aber unterschiedlicher Position.</li>
        </ul>

        <h3>Wichtige Hinweise</h3>
        <ul>
            <li>Es werden nur <b>bedeutsame Änderungen</b> verglichen (z.B. Text, Klasse, Koordinatenwert). Konfidenzwerte, Notizen oder interne IDs werden ignoriert.</li>
            <li>Stellen Sie sicher, dass Sie mindestens zwei Gleisplan-Analysen im Hauptfenster geöffnet haben, um diese Funktion nutzen zu können.</li>
        </ul>
        """

        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Hilfe - Gleispläne vergleichen", help_text, self)
        help_dialog.exec_()
           
    def _load_pdfs(self):
        """Load list of open Gleispläne"""
        self.pdf1_combo.clear()
        self.pdf2_combo.clear()
        
        for workspace in self.parent_window.workspaces.values():
            self.pdf1_combo.addItem(workspace.layout_name, workspace)
            self.pdf2_combo.addItem(workspace.layout_name, workspace)
        
        # Auto-select first two if available
        if self.pdf1_combo.count() >= 2:
            self.pdf1_combo.setCurrentIndex(0)
            self.pdf2_combo.setCurrentIndex(1)

    def on_compare(self):
        """Perform comparison using enhanced engine"""
        ws1 = self.pdf1_combo.currentData()
        ws2 = self.pdf2_combo.currentData()
        
        if not ws1 or not ws2:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte beide Gleispläne auswählen")
            return

        if ws1 == ws2:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte unterschiedliche Gleispläne wählen")
            return

        try:
            engine = LayoutComparisonEngine()
            result = engine.compare(ws1.df_all, ws2.df_all)

            # Store results for export
            self._comparison_results = result
            self._layout_name1 = ws1.layout_name
            self._layout_name2 = ws2.layout_name

            # Enable export button
            self.export_btn.setEnabled(True)

            # Display enhanced results
            self._display_enhanced_results(result, ws1.layout_name, ws2.layout_name)

        except Exception as e:
            import traceback
            error_msg = f"Fehler beim Vergleich:\n{str(e)}\n\n{traceback.format_exc()}"
            QtWidgets.QMessageBox.critical(self, "Vergleichsfehler", error_msg)
            print(error_msg)

    def _display_enhanced_results(self, result: Dict, name1: str, name2: str):
        """Display enhanced comparison results"""
        summary = result['summary']
        
        summary_text = f"""Vergleich: {os.path.basename(name1)} ↔ {os.path.basename(name2)}

    ═══════════════════════════════════════════════════════

     ZUSAMMENFASSUNG:

     HINZUGEFÜGT: {summary['total_added']} Element(e)
    Neue Elemente in PDF 2, die in PDF 1 nicht vorhanden waren

     GELÖSCHT: {summary['total_deleted']} Element(e)
    Elemente aus PDF 1, die in PDF 2 fehlen

    ↔ VERSCHOBEN: {summary.get('total_moved', 0)} Element(e)
    Gleiche Kennung, aber unterschiedliche Position

     UNVERÄNDERT: {summary['total_unchanged']} Element(e)

    ═══════════════════════════════════════════════════════

     ÄNDERUNGEN NACH KLASSE:

    """
        
        # Add class breakdown
        if summary['by_class']:
            for cls, counts in sorted(summary['by_class'].items()):
                added = counts.get('added', 0)
                deleted = counts.get('deleted', 0)
                moved = counts.get('moved', 0)

                if added or deleted or moved:
                    summary_text += f"\n{cls}:\n"
                    if added:
                        summary_text += f"    {added} hinzugefügt\n"
                    if deleted:
                        summary_text += f"    {deleted} gelöscht\n"
                    if moved:
                        summary_text += f"   ↔ {moved} verschoben\n"
        else:
            summary_text += "\n(Keine Änderungen nach Klasse)\n"
        
        summary_text += "\n═══════════════════════════════════════════════════════\n"
        
        # Add page breakdown
        if summary.get('by_page'):
            summary_text += "\n ÄNDERUNGEN NACH SEITE:\n\n"
            for page, counts in sorted(summary['by_page'].items()):
                added = counts.get('added', 0)
                deleted = counts.get('deleted', 0)
                moved = counts.get('moved', 0)

                if added or deleted or moved:
                    summary_text += f"Seite {page}:\n"
                    if added:
                        summary_text += f"    {added} hinzugefügt\n"
                    if deleted:
                        summary_text += f"    {deleted} gelöscht\n"
                    if moved:
                        summary_text += f"   ↔ {moved} verschoben\n"
                    summary_text += "\n"
        
        summary_text += "\n Tipp: Klicken Sie auf eine Zeile, um das Element im Layout zu sehen.\n"
        
        self.summary_text.setPlainText(summary_text)
        
        # Populate tables
        self._populate_added_deleted_table(self.added_table, result['added'], is_added=True)
        self._populate_added_deleted_table(self.deleted_table, result['deleted'], is_added=False)
        self._populate_moved_table(self.moved_table, result.get('moved', []))
    
    def _is_empty(self, value) -> bool:
        """Check if value is empty/None (but 0.0 is NOT empty - it's a valid coordinate)"""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        return False
    
    def _coords_equal(self, val1, val2, tolerance: float = 0.001) -> bool:
        """
        Compare coordinate values with tolerance.
        
        Args:
            val1, val2: Values to compare
            tolerance: Acceptable difference (default 1mm = 0.001km)
        """
        # Both empty
        if self._is_empty(val1) and self._is_empty(val2):
            return True
        
        # One empty, one not
        if self._is_empty(val1) or self._is_empty(val2):
            return False
        
        # Try numeric comparison
        try:
            v1 = float(val1)
            v2 = float(val2)
            return abs(v1 - v2) < tolerance
        except (ValueError, TypeError):
            # Fallback to string comparison
            return str(val1).strip() == str(val2).strip()
    
    def _format_value(self, value) -> str:
        """Format value for display"""
        if value is None:
            return "(leer)"
        if isinstance(value, float):
            if math.isnan(value):
                return "(leer)"
            # Format coordinate values nicely
            return f"{value:.4f}"
        return str(value).strip() if str(value).strip() else "(leer)"

    def _populate_added_deleted_table(self, table: QtWidgets.QTableWidget, changes: List, is_added: bool):
        """Populate added or deleted table with ElementChange objects"""
        table.setRowCount(len(changes))
        
        for i, change in enumerate(changes):
            # Get data from the appropriate version
            data = change.new_data if is_added else change.old_data
            
            if not data:
                continue
            
            # Column 0: Class with indicator
            indicator = " " if is_added else " "
            class_text = f"{indicator}{data.get('cls', '')}"
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(class_text))
            
            # Column 1: Anchor text
            table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(data.get('anchor_text', ''))))
            
            # Column 2: Coordinate text
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(data.get('coord_text', ''))))
            
            # Column 3: Coordinate value (formatted)
            coord_val = data.get('coord_value')
            if coord_val is not None and not (isinstance(coord_val, float) and math.isnan(coord_val)):
                try:
                    coord_val_str = f"{float(coord_val):.4f}"
                except (ValueError, TypeError):
                    coord_val_str = str(coord_val)
            else:
                coord_val_str = ""
            table.setItem(i, 3, QtWidgets.QTableWidgetItem(coord_val_str))
            
            # Column 4: Page
            table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(data.get('page', ''))))
            
            # Store the change object for later use (click-to-highlight)
            table.item(i, 0).setData(QtCore.Qt.UserRole, change)

    def _populate_moved_table(self, table: QtWidgets.QTableWidget, changes: List):
        """Populate moved table with coord_value changes (FA-011: Verschoben - element moved along track)"""
        table.setRowCount(len(changes))

        for i, change in enumerate(changes):
            old_data = change.old_data or {}
            new_data = change.new_data or {}
            spatial = change.spatial_change or {}

            # Column 0: Class with indicator
            class_text = f"↔ {new_data.get('cls', '')}"
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(class_text))

            # Column 1: Identifier (anchor_text or coord_text)
            identifier = new_data.get('anchor_text', '') or new_data.get('coord_text', '')
            table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(identifier)))

            # Column 2: Old km position (coord_value)
            old_coord = spatial.get('old_coord')
            old_str = self._format_value(old_coord) if old_coord is not None else ""
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(old_str))

            # Column 3: New km position with delta (+ = forward, - = backward)
            new_coord = spatial.get('new_coord')
            delta_m = spatial.get('delta_meters')
            new_str = self._format_value(new_coord) if new_coord is not None else ""
            if delta_m is not None:
                new_str += f" ({delta_m:+.1f}m)"  # +50.0m or -50.0m
            table.setItem(i, 3, QtWidgets.QTableWidgetItem(new_str))

            # Column 4: Page
            table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(new_data.get('page', ''))))

            # Store the change object for later use (click-to-highlight)
            table.item(i, 0).setData(QtCore.Qt.UserRole, change)

    def _pop_out_workspace(self, is_new: bool):
        """
        Pop out a workspace to a separate window for multi-monitor comparison.

        Args:
            is_new: True to pop out Gleisplan 2 (new), False for Gleisplan 1 (old)
        """
        workspace = self.pdf2_combo.currentData() if is_new else self.pdf1_combo.currentData()

        if not workspace:
            QtWidgets.QMessageBox.warning(
                self,
                "Kein Gleisplan ausgewählt",
                f"Bitte wählen Sie zuerst {'Gleisplan 2' if is_new else 'Gleisplan 1'} aus."
            )
            return

        # Find the tab index in parent window
        parent_window = self.parent_window
        tab_index = -1

        for i in range(parent_window.tab_widget.count()):
            if parent_window.tab_widget.widget(i) == workspace:
                tab_index = i
                break

        if tab_index < 0:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                "Workspace nicht in Tabs gefunden."
            )
            return

        # Pop out the workspace
        parent_window.pop_out_workspace_tab(tab_index)

        # Update status
        gleisplan_name = "Gleisplan 2 (Neu)" if is_new else "Gleisplan 1 (Alt)"
        if hasattr(parent_window, '_set_status'):
            parent_window._set_status(f" {gleisplan_name} ausgekoppelt - Verschieben Sie es auf Ihren zweiten Monitor")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Clear highlights when dialog is closed"""
        self._clear_all_highlights()
        super().closeEvent(event)

    def reject(self):
        """Clear highlights when dialog is rejected (Close button or Escape)"""
        self._clear_all_highlights()
        super().reject()

    def _clear_all_highlights(self):
        """Clear all highlights from both workspaces"""
        # Clear highlights from workspace 1
        ws1 = self.pdf1_combo.currentData()
        if ws1:
            if hasattr(ws1, 'view') and ws1.view:
                ws1.view._clear_highlight()
            if hasattr(ws1, 'tree') and ws1.tree:
                ws1.tree.clearSelection()

        # Clear highlights from workspace 2
        ws2 = self.pdf2_combo.currentData()
        if ws2:
            if hasattr(ws2, 'view') and ws2.view:
                ws2.view._clear_highlight()
            if hasattr(ws2, 'tree') and ws2.tree:
                ws2.tree.clearSelection()

        print("[DIALOG] Cleared all comparison highlights")

    def _export_results(self):
        """Export comparison results to Excel, CSV, or JSON"""
        if not self._comparison_results:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Ergebnisse",
                "Bitte führen Sie zuerst einen Vergleich durch."
            )
            return

        from export_utils import (
            comparison_results_to_dataframes,
            export_to_excel_multi_sheet,
            export_to_csv,
            export_to_json_grouped
        )

        # Convert results to DataFrames
        dataframes = comparison_results_to_dataframes(self._comparison_results)

        if not dataframes:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Daten",
                "Keine Vergleichsdaten zum Exportieren vorhanden."
            )
            return

        # Get save file path with multiple format options
        name1 = os.path.basename(self._layout_name1 or 'layout1').replace('.pdf', '')
        name2 = os.path.basename(self._layout_name2 or 'layout2').replace('.pdf', '')
        default_name = f"Vergleich_{name1}_vs_{name2}"

        file_filter = "Excel-Dateien (*.xlsx);;CSV-Dateien (*.csv);;JSON-Dateien (*.json)"

        file_path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Vergleichsergebnisse exportieren",
            default_name,
            file_filter
        )

        if not file_path:
            return  # User cancelled

        try:
            # Determine format from file extension or selected filter
            if file_path.endswith('.csv') or 'csv' in selected_filter.lower():
                # CSV: Export each category to separate files
                if not file_path.endswith('.csv'):
                    file_path += '.csv'

                base_path = file_path.rsplit('.csv', 1)[0]
                exported_files = []

                for sheet_name, df in dataframes.items():
                    if not df.empty:
                        csv_path = f"{base_path}_{sheet_name}.csv"
                        export_to_csv(df, csv_path)
                        exported_files.append(csv_path)

                QtWidgets.QMessageBox.information(
                    self,
                    "Export erfolgreich",
                    f"Vergleichsergebnisse wurden exportiert:\n" +
                    "\n".join(exported_files)
                )

            elif file_path.endswith('.json') or 'json' in selected_filter.lower():
                # JSON: Export all categories to one grouped file
                if not file_path.endswith('.json'):
                    file_path += '.json'

                export_to_json_grouped(dataframes, file_path)

                QtWidgets.QMessageBox.information(
                    self,
                    "Export erfolgreich",
                    f"Vergleichsergebnisse wurden exportiert nach:\n{file_path}"
                )

            else:
                # Excel (default): Export with multiple sheets
                if not file_path.endswith('.xlsx'):
                    file_path += '.xlsx'

                export_to_excel_multi_sheet(dataframes, file_path)

                QtWidgets.QMessageBox.information(
                    self,
                    "Export erfolgreich",
                    f"Vergleichsergebnisse wurden exportiert nach:\n{file_path}"
                )

            # Open the file location
            import subprocess
            import platform
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', '/select,', file_path])
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', '-R', file_path])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(file_path)])

        except Exception as e:
            import traceback
            QtWidgets.QMessageBox.critical(
                self,
                "Export fehlgeschlagen",
                f"Fehler beim Exportieren:\n{str(e)}\n\n{traceback.format_exc()}"
            )