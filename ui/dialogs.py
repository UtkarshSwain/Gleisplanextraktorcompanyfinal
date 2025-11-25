from PyQt5 import QtCore, QtGui, QtWidgets
from ui.workspace_widget import WorkspaceWidget
from ui.graphics_view import InteractiveGraphicsView
from ui.auditing_window import AuditingWindow
from ui.tree_widget import AuditingTreeWidget
import pandas as pd 
import math
from typing import List, Dict, Tuple, Optional, Any
import os
class GraphicsWindow(QtWidgets.QMainWindow):
    # --- THIS IS THE FIX ---
    def __init__(self, main_window: 'WorkspaceWidget', graphics_view: 'InteractiveGraphicsView'): # <-- Type hint updated
        super().__init__()
        self.setWindowTitle("Grafikansicht")
        self.resize(1000, 800)
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(graphics_view)
        graphics_view.setParent(central)
        
        # This line was hard-coded to a method on AuditingWindow. 
        # Now it correctly points to the method on WorkspaceWidget.
        self._on_close = main_window._on_graphics_window_closed 
    # --- END OF FIX ---

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

        # ✅ FIX: Apply theme correctly using tuple unpacking
        if parent and hasattr(parent, '_get_theme_colors'):
            try:
                # _get_theme_colors() returns a tuple: (normal, highlight, hover, text, bg)
                normal_color, highlight_color, hover_color, text_color, bg_color = parent._get_theme_colors()
                
                palette = self.palette()
                palette.setColor(QtGui.QPalette.Window, bg_color)
                palette.setColor(QtGui.QPalette.WindowText, text_color)
                palette.setColor(QtGui.QPalette.Base, bg_color)
                palette.setColor(QtGui.QPalette.Text, text_color)
                
                self.setPalette(palette)
                self.text_edit.setPalette(palette)
            except Exception as e:
                # If theme application fails, just continue without custom palette
                print(f"Could not apply theme to HelpDialog: {e}")

class TreeWindow(QtWidgets.QMainWindow):
    """Replaces TableWindow"""
    def __init__(self, main_window: 'WorkspaceWidget', tree_view: 'AuditingTreeWidget'): # <-- Type hint updated
        super().__init__()
        self.setWindowTitle("Detections Tree")
        self.resize(900, 700)
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        lay = QtWidgets.QVBoxLayout(central); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(tree_view); tree_view.setParent(central)
        
        # Store a reference to the tree view
        self.tree_view = tree_view 

        # Link selection signal
        tree_view.itemSelectionChanged.connect(main_window.on_tree_selection_changed)
        
        # --- THIS IS THE FIX ---
        # The error "AttributeError: ... _on_table_window_closed" happens here.
        # Change it to the new method name you added to WorkspaceWidget.
        self._on_close = main_window._on_tree_window_closed 
        # --- END OF FIX ---
    
    def closeEvent(self, e: QtGui.QCloseEvent):
        try: self._on_close()
        finally: super().closeEvent(e)

# ============================================================================
# MODIFIED: SimplePDFCompareDialog - Focus on meaningful changes
# ============================================================================
class SimplePDFCompareDialog(QtWidgets.QDialog):
    """Compare two open PDF tabs - for user-managed versions"""
    
    def __init__(self, parent: AuditingWindow):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("PDFs vergleichen")
        self.resize(900, 700)
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        info_label = QtWidgets.QLabel(
            "📋 Wählen Sie zwei geöffnete PDFs zum Vergleichen:\n"
            "(z.B. 'layout_v1.pdf' und 'layout_v2.pdf')\n\n"
            "ℹ️ Vergleicht: Klassen, Koordinatenwerte, hinzugefügte/gelöschte Elemente"
        )
        info_label.setObjectName("compareInfoLabel")
        layout.addWidget(info_label)

        # --- HILFE-BUTTON HINZUFÜGEN ---
        help_button = QtWidgets.QPushButton("?")
        help_button.setFixedSize(24, 24)
        help_button.setToolTip("Hilfe zu diesem Dialog")
        help_button.clicked.connect(self._show_help)
        
        # Layout für Info-Label und Hilfe-Button
        info_layout = QtWidgets.QHBoxLayout()
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        info_layout.addWidget(help_button)
        layout.addLayout(info_layout)
        # --- ENDE HILFE-BUTTON ---
        
        # PDF selectors (side by side)
        selector_layout = QtWidgets.QHBoxLayout()
        
        # Left PDF
        left_box = QtWidgets.QGroupBox("PDF 1 (Alt)")
        left_layout = QtWidgets.QVBoxLayout(left_box)
        self.pdf1_combo = QtWidgets.QComboBox()
        left_layout.addWidget(self.pdf1_combo)
        selector_layout.addWidget(left_box)
        
        # Right PDF
        right_box = QtWidgets.QGroupBox("PDF 2 (Neu)")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        self.pdf2_combo = QtWidgets.QComboBox()
        right_layout.addWidget(self.pdf2_combo)
        selector_layout.addWidget(right_box)
        
        layout.addLayout(selector_layout)
        
        # Compare button
        self.btn_compare = QtWidgets.QPushButton("🔍 Vergleichen")
        self.btn_compare.clicked.connect(self.on_compare)
        layout.addWidget(self.btn_compare)
        
        # Results area (tabbed view)
        self.results_tabs = QtWidgets.QTabWidget()
        
        # Summary tab
        self.summary_text = QtWidgets.QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.results_tabs.addTab(self.summary_text, "📊 Zusammenfassung")
        
        # Added tab
        self.added_table = QtWidgets.QTableWidget()
        self.added_table.setColumnCount(5)
        self.added_table.setHorizontalHeaderLabels(["Klasse", "Text", "Koordinate", "Koordinatenwert", "Seite"])
        self.added_table.horizontalHeader().setStretchLastSection(False)
        self.added_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.results_tabs.addTab(self.added_table, "➕ Hinzugefügt")
        
        # Deleted tab
        self.deleted_table = QtWidgets.QTableWidget()
        self.deleted_table.setColumnCount(5)
        self.deleted_table.setHorizontalHeaderLabels(["Klasse", "Text", "Koordinate", "Koordinatenwert", "Seite"])
        self.deleted_table.horizontalHeader().setStretchLastSection(False)
        self.deleted_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.results_tabs.addTab(self.deleted_table, "➖ Gelöscht")
        
        # Modified tab
        self.modified_table = QtWidgets.QTableWidget()
        self.modified_table.setColumnCount(6)
        self.modified_table.setHorizontalHeaderLabels(["Klasse", "Text", "Feld", "Alt", "Neu", "Seite"])
        self.modified_table.horizontalHeader().setStretchLastSection(False)
        self.modified_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.results_tabs.addTab(self.modified_table, "📝 Geändert")
        
        layout.addWidget(self.results_tabs)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Load available PDFs
        self._load_pdfs()

# Fügen Sie diese Methode in die Klasse SimplePDFCompareDialog ein

    def _show_help(self):
        """Show help for the SimplePDFCompareDialog"""
        help_text = """
        <h2>PDFs vergleichen - Hilfe</h2>
        
        <h3>Zweck</h3>
        <p>Dieser Dialog ermöglicht es Ihnen, die Analyseergebnisse von zwei geöffneten PDF-Dokumenten gegenüberzustellen und Änderungen zwischen ihnen zu identifizieren.</p>
        
        <h3>Verwendung</h3>
        <ol>
            <li>Wählen Sie im Feld <b>"PDF 1 (Alt)"</b> das ältere oder Referenz-PDF aus.</li>
            <li>Wählen Sie im Feld <b>"PDF 2 (Neu)"</b> das neuere oder zu vergleichende PDF aus.</li>
            <li>Klicken Sie auf <b>"🔍 Vergleichen"</b>.</li>
        </ol>
        
        <h3>Vergleichsergebnisse</h3>
        <p>Die Ergebnisse werden in verschiedenen Tabs angezeigt:</p>
        <ul>
            <li><b>📊 Zusammenfassung:</b> Ein Überblick über die Anzahl der Änderungen.</li>
            <li><b>➕ Hinzugefügt:</b> Elemente, die in PDF 2 (Neu) vorhanden sind, aber nicht in PDF 1 (Alt).</li>
            <li><b>➖ Gelöscht:</b> Elemente, die in PDF 1 (Alt) vorhanden waren, aber in PDF 2 (Neu) fehlen.</li>
            <li><b>📝 Geändert:</b> Elemente, die in beiden PDFs vorhanden sind, sich aber in wichtigen Eigenschaften (Klasse, Text, Koordinatenwert, Fahrtrichtung) unterscheiden.</li>
        </ul>
        
        <h3>Wichtige Hinweise</h3>
        <ul>
            <li>Es werden nur <b>bedeutsame Änderungen</b> verglichen (z.B. Text, Klasse, Koordinatenwert). Konfidenzwerte, Notizen oder interne IDs werden ignoriert.</li>
            <li>Stellen Sie sicher, dass Sie mindestens zwei PDF-Analysen im Hauptfenster geöffnet haben, um diese Funktion nutzen zu können.</li>
        </ul>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Hilfe - PDFs vergleichen", help_text, self)
        help_dialog.exec_()
           
    def _load_pdfs(self):
        """Load list of open PDFs"""
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
        """Perform comparison"""
        ws1 = self.pdf1_combo.currentData()
        ws2 = self.pdf2_combo.currentData()
        
        if not ws1 or not ws2:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte beide PDFs auswählen")
            return
        
        if ws1 == ws2:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte unterschiedliche PDFs wählen")
            return
        
        # Compare DataFrames directly
        changes = self._compare_dataframes(ws1.df_all, ws2.df_all)
        
        # Display results
        self._display_changes(changes, ws1.layout_name, ws2.layout_name)
    
    def _compare_dataframes(self, df1: pd.DataFrame, df2: pd.DataFrame) -> Dict:
        """
        Compare two DataFrames focusing on meaningful changes:
        - Class changes
        - Coordinate value changes
        - Added/deleted elements
        
        IGNORES: confidence, notes, internal IDs
        """
        # ✅ IMPROVED: Create unique keys based on position + class
        def make_key(row):
            """
            Create a unique key based on:
            - Class type
            - Spatial position (page + approximate coordinates)
            - Text identifier (if available)
            
            This allows us to track the SAME element across versions
            even if some attributes changed.
            """
            cls = row.get('cls', '')
            page = row.get('page', 0)
            
            # Use anchor text as primary identifier
            anchor = str(row.get('anchor_text', '')).strip()
            
            # For coordinates, use the coordinate text itself
            if cls == 'coordinate':
                coord_text = str(row.get('coord_text', '')).strip()
                # Use coordinate value for more precise matching
                coord_val = row.get('coord_value', '')
                return f"{cls}:{page}:{coord_text}:{coord_val}"
            
            # For elements with anchor text, use it
            if anchor:
                return f"{cls}:{page}:{anchor}"
            
            # Fallback: use approximate position (rounded to nearest 10 pixels)
            # This helps match elements that moved slightly
            if cls == 'coordinate':
                cx = row.get('cx1', 0)
                cy = row.get('cy1', 0)
            else:
                cx = row.get('ax1', 0)
                cy = row.get('ay1', 0)
            
            # Round to nearest 50 pixels to allow for small movements
            cx_rounded = round(cx / 50) * 50 if cx else 0
            cy_rounded = round(cy / 50) * 50 if cy else 0
            
            return f"{cls}:{page}:{cx_rounded}:{cy_rounded}"
        
        # Build dictionaries
        dict1 = {make_key(row): row.to_dict() for _, row in df1.iterrows()}
        dict2 = {make_key(row): row.to_dict() for _, row in df2.iterrows()}
        
        keys1 = set(dict1.keys())
        keys2 = set(dict2.keys())
        
        changes = {
            'added': [],
            'deleted': [],
            'modified': [],
            'unchanged': []
        }
        
        # ✅ Deleted elements
        for key in keys1 - keys2:
            changes['deleted'].append(dict1[key])
        
        # ✅ Added elements
        for key in keys2 - keys1:
            changes['added'].append(dict2[key])
        
        # ✅ IMPROVED: Modified elements - only meaningful changes
        for key in keys1 & keys2:
            row1 = dict1[key]
            row2 = dict2[key]
            
            diff_fields = {}
            
            # ✅ Fields to check for changes (EXCLUDING confidence, notes, IDs)
            check_fields = {
                'cls': 'Klasse',                    # Class type
                'anchor_text': 'Text/Nummer',       # Main text
                'coord_text': 'Koordinatentext',    # Coordinate text
                'coord_value': 'Koordinatenwert',   # Coordinate VALUE (important!)
                'gi_gl': 'GI/GL',                   # Track identifier
                'fahrtrichtung': 'Fahrtrichtung',   # Direction (for signals)
                'page': 'Seite',                    # Page number
            }
            
            for field, display_name in check_fields.items():
                val1 = row1.get(field)
                val2 = row2.get(field)
                
                # ✅ IMPROVED: Smart comparison
                # Skip if both are None/empty
                if self._is_empty(val1) and self._is_empty(val2):
                    continue
                
                # ✅ For numeric values (coord_value), use tolerance comparison
                if field == 'coord_value':
                    if not self._coords_equal(val1, val2):
                        diff_fields[field] = {
                            'old': self._format_value(val1),
                            'new': self._format_value(val2),
                            'display_name': display_name
                        }
                # ✅ For text values, use string comparison
                else:
                    if str(val1).strip() != str(val2).strip():
                        diff_fields[field] = {
                            'old': self._format_value(val1),
                            'new': self._format_value(val2),
                            'display_name': display_name
                        }
            
            # Only record if there are meaningful differences
            if diff_fields:
                changes['modified'].append({
                    'key': key,
                    'row_v1': row1,
                    'row_v2': row2,
                    'differences': diff_fields
                })
            else:
                changes['unchanged'].append(row2)
        
        return changes
    
    def _is_empty(self, value) -> bool:
        """Check if value is empty/None"""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, float) and (math.isnan(value) or value == 0.0):
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
    
    def _display_changes(self, changes: Dict, name1: str, name2: str):
        """Display comparison results"""
        # ✅ IMPROVED: Summary with better formatting
        summary = f"""Vergleich: {os.path.basename(name1)} ↔ {os.path.basename(name2)}

═══════════════════════════════════════════════════════

➕ HINZUGEFÜGT: {len(changes['added'])} Element(e)
   Neue Elemente in PDF 2, die in PDF 1 nicht vorhanden waren

➖ GELÖSCHT: {len(changes['deleted'])} Element(e)
   Elemente aus PDF 1, die in PDF 2 fehlen

📝 GEÄNDERT: {len(changes['modified'])} Element(e)
   Elemente mit geänderten Eigenschaften:
   • Klassenänderungen
   • Koordinatenwerte
   • Text/Nummern
   • Fahrtrichtung (bei Signalen)

✓ UNVERÄNDERT: {len(changes['unchanged'])} Element(e)

═══════════════════════════════════════════════════════

💡 Hinweis: Konfidenzwerte und Notizen werden nicht verglichen.
   Nur inhaltliche Änderungen werden angezeigt.

Details siehe Tabs →
"""
        self.summary_text.setPlainText(summary)
        
        # ✅ IMPROVED: Added table with coordinate values
        self.added_table.setRowCount(len(changes['added']))
        for i, row in enumerate(changes['added']):
            self.added_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(row.get('cls', ''))))
            self.added_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(row.get('anchor_text', ''))))
            self.added_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(row.get('coord_text', ''))))
            
            # ✅ Show coordinate VALUE
            coord_val = row.get('coord_value')
            coord_val_str = f"{coord_val:.4f}" if coord_val is not None else ""
            self.added_table.setItem(i, 3, QtWidgets.QTableWidgetItem(coord_val_str))
            
            self.added_table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(row.get('page', ''))))
            
            # ✅ Highlight new items in green
            for col in range(5):
                item = self.added_table.item(i, col)
                if item:
                    item.setBackground(QtGui.QColor(200, 255, 200))  # Light green
        
        # ✅ IMPROVED: Deleted table with coordinate values
        self.deleted_table.setRowCount(len(changes['deleted']))
        for i, row in enumerate(changes['deleted']):
            self.deleted_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(row.get('cls', ''))))
            self.deleted_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(row.get('anchor_text', ''))))
            self.deleted_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(row.get('coord_text', ''))))
            
            # ✅ Show coordinate VALUE
            coord_val = row.get('coord_value')
            coord_val_str = f"{coord_val:.4f}" if coord_val is not None else ""
            self.deleted_table.setItem(i, 3, QtWidgets.QTableWidgetItem(coord_val_str))
            
            self.deleted_table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(row.get('page', ''))))
            
            # ✅ Highlight deleted items in red
            for col in range(5):
                item = self.deleted_table.item(i, col)
                if item:
                    item.setBackground(QtGui.QColor(255, 200, 200))  # Light red
        
        # ✅ IMPROVED: Modified table with field names
        mod_rows = []
        for item in changes['modified']:
            row_v1 = item['row_v1']
            row_v2 = item['row_v2']
            for field, diff in item['differences'].items():
                mod_rows.append((row_v2, field, diff))
        
        self.modified_table.setRowCount(len(mod_rows))
        for i, (row, field, diff) in enumerate(mod_rows):
            self.modified_table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(row.get('cls', ''))))
            self.modified_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(row.get('anchor_text', ''))))
            
            # ✅ Use display name instead of field key
            field_display = diff.get('display_name', field)
            self.modified_table.setItem(i, 2, QtWidgets.QTableWidgetItem(field_display))
            
            self.modified_table.setItem(i, 3, QtWidgets.QTableWidgetItem(str(diff['old'])))
            self.modified_table.setItem(i, 4, QtWidgets.QTableWidgetItem(str(diff['new'])))
            self.modified_table.setItem(i, 5, QtWidgets.QTableWidgetItem(str(row.get('page', ''))))
            
            # ✅ Highlight changed values in yellow
            for col in [3, 4]:  # Old and New columns
                item = self.modified_table.item(i, col)
                if item:
                    item.setBackground(QtGui.QColor(255, 255, 200))  # Light yellow
