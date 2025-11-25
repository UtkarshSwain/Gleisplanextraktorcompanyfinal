import os
import json
from PyQt5 import QtWidgets, QtCore, QtGui
import pandas as pd

class HelpDialog(QtWidgets.QDialog):
    def __init__(self, title: str, content_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)
        
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        
        layout = QtWidgets.QVBoxLayout(self)
        
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(content_html)
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        layout.addWidget(text_edit)
        
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
class AdvancedExcelExportDialog(QtWidgets.QDialog):
    """
    Advanced Excel export dialog with full user control:
    - Select classes to export
    - Choose and reorder columns
    - Rename columns
    - Configure formatting
    - Save/load templates
    """
    
    def __init__(self, parent: 'WorkspaceWidget'):
        super().__init__(parent)
        self.workspace = parent
        self.setWindowTitle("Excel Export - Erweiterte Konfiguration")
        self.resize(900, 700)
        
        # ADD THESE LINES: Enable maximize button
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        
        # Template manager
        self.template_manager = ExportTemplateManager()
        
        self._build_ui()
        self._load_default_config()
    
    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        # --- HILFE-BUTTON HINZUFÜGEN (KORRIGIERTE PLATZIERUNG) ---
        # Erstellen Sie einen Container für die Überschrift und den Hilfe-Button
        header_container = QtWidgets.QWidget()
        header_layout = QtWidgets.QHBoxLayout(header_container)
        header_layout.setContentsMargins(0, 0, 0, 0) # Entfernt Standard-Ränder des Layouts

        help_button = QtWidgets.QPushButton("?")
        help_button.setFixedSize(24, 24)
        help_button.setToolTip("Hilfe zu diesem Dialog")
        help_button.clicked.connect(self._show_help)
        
        header_layout.addWidget(QtWidgets.QLabel("<h2>Excel Export Konfiguration</h2>"))
        header_layout.addStretch() # Sorgt dafür, dass der Button nach rechts geschoben wird
        header_layout.addWidget(help_button)
        
        main_layout.addWidget(header_container) # Fügen Sie den Container zum Hauptlayout hinzu
        # --- ENDE HILFE-BUTTON ---

        # ============================================================
        # SECTION 1: Template Management
        # ============================================================
        template_group = QtWidgets.QGroupBox("📋 Vorlagen")
        template_layout = QtWidgets.QHBoxLayout(template_group)
        
        template_layout.addWidget(QtWidgets.QLabel("Vorlage:"))
        
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.setMinimumWidth(200)
        self.template_combo.addItem("(Neue Konfiguration)")
        
        # Load saved templates
        for template_name in self.template_manager.list_templates():
            self.template_combo.addItem(template_name)
        
        self.template_combo.currentTextChanged.connect(self._on_template_changed)
        template_layout.addWidget(self.template_combo)
        
        self.btn_load_template = QtWidgets.QPushButton("Laden")
        self.btn_load_template.clicked.connect(self._load_template)
        template_layout.addWidget(self.btn_load_template)
        
        self.btn_save_template = QtWidgets.QPushButton("Speichern als...")
        self.btn_save_template.clicked.connect(self._save_template)
        template_layout.addWidget(self.btn_save_template)
        
        self.btn_delete_template = QtWidgets.QPushButton("Löschen")
        self.btn_delete_template.clicked.connect(self._delete_template)
        template_layout.addWidget(self.btn_delete_template)
        
        template_layout.addStretch()
        main_layout.addWidget(template_group) 
        
        # ============================================================
        # SECTION 2: Class Selection and Column Configuration
        # ============================================================
        config_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Class list
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QtWidgets.QLabel("Klassen auswählen:"))
        
        self.class_list = QtWidgets.QListWidget()
        self.class_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.class_list.currentRowChanged.connect(self._on_class_selected)
        left_layout.addWidget(self.class_list)
        
        # Buttons for class selection
        class_btn_layout = QtWidgets.QHBoxLayout()
        self.btn_select_all_classes = QtWidgets.QPushButton("Alle")
        self.btn_select_all_classes.clicked.connect(self._select_all_classes)
        class_btn_layout.addWidget(self.btn_select_all_classes)
        
        self.btn_deselect_all_classes = QtWidgets.QPushButton("Keine")
        self.btn_deselect_all_classes.clicked.connect(self._deselect_all_classes)
        class_btn_layout.addWidget(self.btn_deselect_all_classes)
        
        left_layout.addLayout(class_btn_layout)
        
        config_splitter.addWidget(left_widget)
        
        # Right: Column configuration for selected class
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_class_label = QtWidgets.QLabel("Spalten für die ausgewählte Klasse konfigurieren:")
        self.current_class_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.current_class_label)
        
        # Column configuration table
        self.column_table = QtWidgets.QTableWidget()
        self.column_table.setColumnCount(4)
        self.column_table.setHorizontalHeaderLabels([
            "Exportieren", "Spaltenname (Daten)", "Anzeigename (Excel)", "Reihenfolge"
        ])
        self.column_table.horizontalHeader().setStretchLastSection(False)
        self.column_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.column_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.column_table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.column_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.column_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        right_layout.addWidget(self.column_table)
        
        # Column control buttons
        col_btn_layout = QtWidgets.QHBoxLayout()
        
        self.btn_select_all_cols = QtWidgets.QPushButton("Alle auswählen")
        self.btn_select_all_cols.clicked.connect(self._select_all_columns)
        col_btn_layout.addWidget(self.btn_select_all_cols)
        
        self.btn_deselect_all_cols = QtWidgets.QPushButton("Alle abwählen")
        self.btn_deselect_all_cols.clicked.connect(self._deselect_all_columns)
        col_btn_layout.addWidget(self.btn_deselect_all_cols)
        
        col_btn_layout.addStretch()
        
        self.btn_move_up = QtWidgets.QPushButton("↑ Nach oben")
        self.btn_move_up.clicked.connect(self._move_column_up)
        col_btn_layout.addWidget(self.btn_move_up)
        
        self.btn_move_down = QtWidgets.QPushButton("↓ Nach unten")
        self.btn_move_down.clicked.connect(self._move_column_down)
        col_btn_layout.addWidget(self.btn_move_down)
        
        right_layout.addLayout(col_btn_layout)
        
        config_splitter.addWidget(right_widget)
        config_splitter.setSizes([250, 650])
        
        main_layout.addWidget(config_splitter) 
        
        # ============================================================
        # SECTION 3: Export Options
        # ============================================================
        options_group = QtWidgets.QGroupBox("⚙ Export-Optionen")
        options_layout = QtWidgets.QGridLayout(options_group)
        
        # Row 0: Sheet organization
        self.radio_separate_sheets = QtWidgets.QRadioButton("Separate Arbeitsblätter pro Klasse")
        self.radio_separate_sheets.setChecked(True)
        options_layout.addWidget(self.radio_separate_sheets, 0, 0, 1, 2)
        
        self.radio_single_sheet = QtWidgets.QRadioButton("Alle Klassen in einem Arbeitsblatt")
        options_layout.addWidget(self.radio_single_sheet, 1, 0, 1, 2)
        
        # Row 2: Filters
        self.check_apply_filters = QtWidgets.QCheckBox("Aktuelle Filter anwenden (Konfidenz, Sichtbarkeit)")
        self.check_apply_filters.setChecked(True)
        options_layout.addWidget(self.check_apply_filters, 2, 0, 1, 2)
        
        # Row 3: Empty cells
        self.check_include_empty = QtWidgets.QCheckBox("Leere Zellen einschließen")
        self.check_include_empty.setChecked(False)
        options_layout.addWidget(self.check_include_empty, 3, 0, 1, 2)
        
        # Row 4: Formatting
        self.check_auto_width = QtWidgets.QCheckBox("Spaltenbreite automatisch anpassen")
        self.check_auto_width.setChecked(True)
        options_layout.addWidget(self.check_auto_width, 4, 0)
        
        self.check_freeze_header = QtWidgets.QCheckBox("Kopfzeile fixieren")
        self.check_freeze_header.setChecked(True)
        options_layout.addWidget(self.check_freeze_header, 4, 1)
        
        # Row 5: Sorting
        options_layout.addWidget(QtWidgets.QLabel("Sortierung:"), 5, 0)
        self.sort_combo = QtWidgets.QComboBox()
        self.sort_combo.addItems([
            "Keine Sortierung",
            "Nach Klasse",
            "Nach Seite",
            "Nach Koordinatenwert",
            "Nach Text/Nummer"
        ])
        options_layout.addWidget(self.sort_combo, 5, 1)
        
        main_layout.addWidget(options_group) 
        
        # ============================================================
        # SECTION 4: Preview
        # ============================================================
        preview_group = QtWidgets.QGroupBox("👁 Vorschau")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        
        self.preview_text = QtWidgets.QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(100)
        preview_layout.addWidget(self.preview_text)
        
        self.btn_update_preview = QtWidgets.QPushButton("Vorschau aktualisieren")
        self.btn_update_preview.clicked.connect(self._update_preview)
        preview_layout.addWidget(self.btn_update_preview)
        
        main_layout.addWidget(preview_group) 
        
        # ============================================================
        # SECTION 5: Action Buttons
        # ============================================================
        button_layout = QtWidgets.QHBoxLayout()
        
        self.btn_export = QtWidgets.QPushButton("📊 Exportieren")
        self.btn_export.setStyleSheet("font-weight: bold; padding: 8px;")
        self.btn_export.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_export)
        
        self.btn_cancel = QtWidgets.QPushButton("Abbrechen")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)
        
        main_layout.addLayout(button_layout) 
        
        # Initialize class list
        self._populate_class_list()
    
    def _populate_class_list(self):
        """Populate the class list with checkboxes"""
        self.class_list.clear()
        self.class_items = {}
        
        if self.workspace.df_all is None or self.workspace.df_all.empty:
            return
        
        classes = sorted(self.workspace.df_all['cls'].unique())
        
        # Move 'coordinate' to end
        if 'coordinate' in classes:
            classes.remove('coordinate')
            classes.append('coordinate')
        
        for cls_name in classes:
            item = QtWidgets.QListWidgetItem(cls_name)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)  # Default: all checked
            self.class_list.addItem(item)
            self.class_items[cls_name] = item
        
        # Select first class
        if self.class_list.count() > 0:
            self.class_list.setCurrentRow(0)
    
    def _on_class_selected(self, row: int):
        """When a class is selected, show its column configuration"""
        if row < 0:
            return
        
        item = self.class_list.item(row)
        cls_name = item.text()
        
        self.current_class_label.setText(f"Spalten für '{cls_name}' konfigurieren:")
        self._populate_column_table(cls_name)
    
    def _populate_column_table(self, cls_name: str):
        """Populate column configuration table for a class"""
        self.column_table.setRowCount(0)
        
        df_class = self.workspace.df_all[self.workspace.df_all['cls'] == cls_name]
        if df_class.empty:
            return
        
        # Get available columns
        available_columns = self._get_available_columns(cls_name, df_class)
        
        # Default selected columns
        default_selected = self._get_default_columns(cls_name)
        
        # Populate table
        for idx, (col_key, col_display) in enumerate(available_columns.items()):
            row = self.column_table.rowCount()
            self.column_table.insertRow(row)
            
            # Column 0: Checkbox
            check_widget = QtWidgets.QWidget()
            check_layout = QtWidgets.QHBoxLayout(check_widget)
            check_layout.setContentsMargins(0, 0, 0, 0)
            check_layout.setAlignment(QtCore.Qt.AlignCenter)
            
            check = QtWidgets.QCheckBox()
            check.setChecked(col_key in default_selected)
            check_layout.addWidget(check)
            
            self.column_table.setCellWidget(row, 0, check_widget)
            
            # Column 1: Data column name (read-only)
            item_key = QtWidgets.QTableWidgetItem(col_key)
            item_key.setFlags(item_key.flags() & ~QtCore.Qt.ItemIsEditable)
            item_key.setData(QtCore.Qt.UserRole, col_key)  # Store original key
            self.column_table.setItem(row, 1, item_key)
            
            # Column 2: Display name (editable)
            item_display = QtWidgets.QTableWidgetItem(col_display)
            self.column_table.setItem(row, 2, item_display)
            
            # Column 3: Order (read-only, auto-updated)
            item_order = QtWidgets.QTableWidgetItem(str(idx + 1))
            item_order.setFlags(item_order.flags() & ~QtCore.Qt.ItemIsEditable)
            item_order.setTextAlignment(QtCore.Qt.AlignCenter)
            self.column_table.setItem(row, 3, item_order)
    
    def _get_available_columns(self, cls_name: str, df_class: pd.DataFrame) -> dict:
        """Get available columns for a class with display names"""
        if cls_name == 'coordinate':
            all_columns = {
                'coord_text': 'Koordinatentext',
                'coord_value': 'Koordinatenwert',
                'gi_gl': 'GI/GL',
                'page': 'Seite',
                'conf': 'Konfidenz',
                'color': 'Farbe',
                'notes': 'Notizen',
                'cx1': 'X1', 'cy1': 'Y1', 'cx2': 'X2', 'cy2': 'Y2',
                'angle': 'Winkel (normalisiert)',
                'angle_raw': 'Winkel (roh)',
                'obb_cx': 'OBB Center X',
                'obb_cy': 'OBB Center Y',
                'obb_w': 'OBB Breite',
                'obb_h': 'OBB Höhe',
            }
        else:
            all_columns = {
                'anchor_text': 'Text/Nummer',
                'coord_text': 'Koordinatentext',
                'coord_value': 'Koordinatenwert',
                'gi_gl': 'GI/GL',
                'page': 'Seite',
                'conf': 'Konfidenz',
                'color': 'Farbe',
                'notes': 'Notizen',
                'ax1': 'Anker X1', 'ay1': 'Anker Y1',
                'ax2': 'Anker X2', 'ay2': 'Anker Y2',
                'cx1': 'Koord X1', 'cy1': 'Koord Y1',
                'cx2': 'Koord X2', 'cy2': 'Koord Y2',
                'angle': 'Winkel (normalisiert)',
                'angle_raw': 'Winkel (roh)',
                'obb_cx': 'OBB Center X',
                'obb_cy': 'OBB Center Y',
                'obb_w': 'OBB Breite',
                'obb_h': 'OBB Höhe',
            }
            
            if cls_name == 'signal':
                all_columns['fahrtrichtung'] = 'Fahrtrichtung'
            
            if cls_name == 'weichen_block':
                all_columns['weichen_coordinates'] = 'Weichen Koordinaten'
        
        # Filter to only existing columns
        return {k: v for k, v in all_columns.items() if k in df_class.columns}
    
    def _get_default_columns(self, cls_name: str) -> list:
        """Get default selected columns for a class"""
        defaults = {
            'coordinate': ['coord_text', 'coord_value', 'gi_gl', 'page'],
            'signal': ['anchor_text', 'coord_text', 'coord_value', 'fahrtrichtung', 'page'],
            'gks_gesteuert': ['anchor_text', 'coord_text', 'coord_value', 'page'],
            'gks_festkodiert': ['anchor_text', 'coord_text', 'coord_value', 'page'],
            'weichen_block': ['anchor_text', 'weichen_coordinates', 'page'],
        }
        
        return defaults.get(cls_name, ['anchor_text', 'coord_text', 'page'])
    
    def _select_all_classes(self):
        """Select all classes"""
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            item.setCheckState(QtCore.Qt.Checked)
    
    def _deselect_all_classes(self):
        """Deselect all classes"""
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            item.setCheckState(QtCore.Qt.Unchecked)
    
    def _select_all_columns(self):
        """Select all columns in current table"""
        for row in range(self.column_table.rowCount()):
            widget = self.column_table.cellWidget(row, 0)
            if widget:
                check = widget.findChild(QtWidgets.QCheckBox)
                if check:
                    check.setChecked(True)
    
    def _deselect_all_columns(self):
        """Deselect all columns in current table"""
        for row in range(self.column_table.rowCount()):
            widget = self.column_table.cellWidget(row, 0)
            if widget:
                check = widget.findChild(QtWidgets.QCheckBox)
                if check:
                    check.setChecked(False)
    
    def _move_column_up(self):
        """Move selected column up"""
        current_row = self.column_table.currentRow()
        if current_row <= 0:
            return
        
        self._swap_rows(current_row, current_row - 1)
        self.column_table.setCurrentCell(current_row - 1, 0)
        self._update_order_numbers()
    
    def _move_column_down(self):
        """Move selected column down"""
        current_row = self.column_table.currentRow()
        if current_row < 0 or current_row >= self.column_table.rowCount() - 1:
            return
        
        self._swap_rows(current_row, current_row + 1)
        self.column_table.setCurrentCell(current_row + 1, 0)
        self._update_order_numbers()
    
    def _swap_rows(self, row1: int, row2: int):
        """Swap two rows in the column table"""
        for col in range(self.column_table.columnCount()):
            if col == 0:  # Checkbox column
                widget1 = self.column_table.cellWidget(row1, col)
                widget2 = self.column_table.cellWidget(row2, col)
                
                check1 = widget1.findChild(QtWidgets.QCheckBox)
                check2 = widget2.findChild(QtWidgets.QCheckBox)
                
                state1 = check1.isChecked()
                state2 = check2.isChecked()
                
                check1.setChecked(state2)
                check2.setChecked(state1)
            else:
                item1 = self.column_table.item(row1, col)
                item2 = self.column_table.item(row2, col)
                
                if item1 and item2:
                    text1 = item1.text()
                    text2 = item2.text()
                    data1 = item1.data(QtCore.Qt.UserRole)
                    data2 = item2.data(QtCore.Qt.UserRole)
                    
                    item1.setText(text2)
                    item2.setText(text1)
                    item1.setData(QtCore.Qt.UserRole, data2)
                    item2.setData(QtCore.Qt.UserRole, data1)
    
    def _update_order_numbers(self):
        """Update order numbers in column 3"""
        for row in range(self.column_table.rowCount()):
            item = self.column_table.item(row, 3)
            if item:
                item.setText(str(row + 1))
    
    def _update_preview(self):
        """Update export preview"""
        config = self.get_export_config()
        
        preview_lines = []
        preview_lines.append("=" * 60)
        preview_lines.append("EXPORT-VORSCHAU")
        preview_lines.append("=" * 60)
        preview_lines.append("")
        
        # Classes
        if config['classes']:
            preview_lines.append(f"Klassen ({len(config['classes'])}):")
            for cls_name, col_config in config['classes'].items():
                preview_lines.append(f"  • {cls_name}: {len(col_config['columns'])} Spalten")
        else:
            preview_lines.append("⚠ Keine Klassen ausgewählt!")
        
        preview_lines.append("")
        
        # Options
        preview_lines.append("Optionen:")
        opts = config['options']
        preview_lines.append(f"  • Organisation: {'Separate Arbeitsblätter' if opts['separate_sheets'] else 'Ein Arbeitsblatt'}")
        preview_lines.append(f"  • Filter anwenden: {'Ja' if opts['apply_filters'] else 'Nein'}")
        preview_lines.append(f"  • Leere Zellen: {'Einschließen' if opts['include_empty'] else 'Ausschließen'}")
        preview_lines.append(f"  • Spaltenbreite: {'Automatisch' if opts['auto_width'] else 'Standard'}")
        preview_lines.append(f"  • Kopfzeile fixieren: {'Ja' if opts['freeze_header'] else 'Nein'}")
        preview_lines.append(f"  • Sortierung: {opts['sort_by']}")
        
        preview_lines.append("")
        preview_lines.append("=" * 60)
        
        self.preview_text.setPlainText("\n".join(preview_lines))
    
    def _load_default_config(self):
        """Load default configuration"""
        # Already done in _populate_class_list and _populate_column_table
        pass
    
    def _on_template_changed(self, template_name: str):
        """Handle template selection change"""
        if template_name == "(Neue Konfiguration)":
            self.btn_delete_template.setEnabled(False)
        else:
            self.btn_delete_template.setEnabled(True)
    
    def _load_template(self):
        """Load selected template"""
        template_name = self.template_combo.currentText()
        if template_name == "(Neue Konfiguration)":
            QtWidgets.QMessageBox.information(
                self,
                "Keine Vorlage",
                "Bitte wählen Sie eine gespeicherte Vorlage aus."
            )
            return
        
        config = self.template_manager.get_template(template_name)
        if not config:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                f"Vorlage '{template_name}' konnte nicht geladen werden."
            )
            return
        
        self._apply_config(config)
        QtWidgets.QMessageBox.information(
            self,
            "Geladen",
            f"Vorlage '{template_name}' wurde geladen."
        )
    
    def _save_template(self):
        """Save current configuration as template"""
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Vorlage speichern",
            "Name der Vorlage:",
            text=self.template_combo.currentText() if self.template_combo.currentText() != "(Neue Konfiguration)" else ""
        )
        
        if not ok or not name.strip():
            return
        
        name = name.strip()
        
        # Check if overwriting
        if name in self.template_manager.list_templates():
            reply = QtWidgets.QMessageBox.question(
                self,
                "Überschreiben?",
                f"Vorlage '{name}' existiert bereits. Überschreiben?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            
            if reply != QtWidgets.QMessageBox.Yes:
                return
        
        config = self.get_export_config()
        self.template_manager.save_template(name, config)
        
        # Add to combo if new
        if self.template_combo.findText(name) == -1:
            self.template_combo.addItem(name)
        
        self.template_combo.setCurrentText(name)
        
        QtWidgets.QMessageBox.information(
            self,
            "Gespeichert",
            f"Vorlage '{name}' wurde gespeichert."
        )
    
    def _delete_template(self):
        """Delete selected template"""
        template_name = self.template_combo.currentText()
        if template_name == "(Neue Konfiguration)":
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Löschen?",
            f"Vorlage '{template_name}' wirklich löschen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        self.template_manager.delete_template(template_name)
        
        # Remove from combo
        idx = self.template_combo.findText(template_name)
        if idx >= 0:
            self.template_combo.removeItem(idx)
        
        self.template_combo.setCurrentIndex(0)
        
        QtWidgets.QMessageBox.information(
            self,
            "Gelöscht",
            f"Vorlage '{template_name}' wurde gelöscht."
        )
    
    def _apply_config(self, config: dict):
        """Apply a configuration to the UI"""
        # Apply class selections
        for cls_name, item in self.class_items.items():
            if cls_name in config.get('classes', {}):
                item.setCheckState(QtCore.Qt.Checked)
            else:
                item.setCheckState(QtCore.Qt.Unchecked)
        
        # Apply options
        opts = config.get('options', {})
        
        if opts.get('separate_sheets', True):
            self.radio_separate_sheets.setChecked(True)
        else:
            self.radio_single_sheet.setChecked(True)
        
        self.check_apply_filters.setChecked(opts.get('apply_filters', True))
        self.check_include_empty.setChecked(opts.get('include_empty', False))
        self.check_auto_width.setChecked(opts.get('auto_width', True))
        self.check_freeze_header.setChecked(opts.get('freeze_header', True))
        
        sort_text = opts.get('sort_by', 'Keine Sortierung')
        idx = self.sort_combo.findText(sort_text)
        if idx >= 0:
            self.sort_combo.setCurrentIndex(idx)
        
        # Refresh current class column config
        current_row = self.class_list.currentRow()
        if current_row >= 0:
            self._on_class_selected(current_row)
    
    def get_export_config(self) -> dict:
        """
        Get the complete export configuration.
        
        Returns dict with structure:
        {
            'classes': {
                'class_name': {
                    'columns': ['col1', 'col2', ...],
                    'display_names': {'col1': 'Display 1', ...},
                    'order': [0, 1, 2, ...]
                }
            },
            'options': {
                'separate_sheets': bool,
                'apply_filters': bool,
                'include_empty': bool,
                'auto_width': bool,
                'freeze_header': bool,
                'sort_by': str
            }
        }
        """
        config = {
            'classes': {},
            'options': {
                'separate_sheets': self.radio_separate_sheets.isChecked(),
                'apply_filters': self.check_apply_filters.isChecked(),
                'include_empty': self.check_include_empty.isChecked(),
                'auto_width': self.check_auto_width.isChecked(),
                'freeze_header': self.check_freeze_header.isChecked(),
                'sort_by': self.sort_combo.currentText(),
            }
        }
        
        # Get configuration for each selected class
        for i in range(self.class_list.count()):
            item = self.class_list.item(i)
            if item.checkState() != QtCore.Qt.Checked:
                continue
            
            cls_name = item.text()
            
            # Temporarily switch to this class to get its config
            # (This is important to ensure column_table is populated correctly for the class)
            current_class_list_row = self.class_list.currentRow()
            self.class_list.setCurrentRow(i) 
            
            columns = []
            display_names = {}
            # order is implicitly handled by the order of 'columns' list
            
            for row in range(self.column_table.rowCount()):
                # Check if column is selected
                widget = self.column_table.cellWidget(row, 0)
                if not widget:
                    continue
                
                check = widget.findChild(QtWidgets.QCheckBox)
                if not check or not check.isChecked():
                    continue
                
                # Get column key
                item_key = self.column_table.item(row, 1)
                if not item_key:
                    continue
                
                col_key = item_key.data(QtCore.Qt.UserRole)
                if not col_key:
                    col_key = item_key.text()
                
                # Get display name
                item_display = self.column_table.item(row, 2)
                display_name = item_display.text() if item_display else col_key
                
                columns.append(col_key)
                display_names[col_key] = display_name
            
            if columns:
                config['classes'][cls_name] = {
                    'columns': columns,
                    'display_names': display_names,
                }
            
            # Restore original class selection
            self.class_list.setCurrentRow(current_class_list_row)
        
        return config
    
    def _show_help(self):
        """Show help for the AdvancedExcelExportDialog"""
        help_text = """
        <h2>Excel Export Konfiguration - Hilfe</h2>
        
        <h3>Zweck</h3>
        <p>Dieser Dialog ermöglicht Ihnen die detaillierte Konfiguration des Exports Ihrer extrahierten Daten nach Excel.</p>
        
        <h3>1. Vorlagen</h3>
        <ul>
            <li><b>Vorlage wählen:</b> Wählen Sie eine gespeicherte Vorlage aus der Dropdown-Liste.</li>
            <li><b>Laden:</b> Lädt die ausgewählte Vorlage und wendet ihre Einstellungen an.</li>
            <li><b>Speichern als...:</b> Speichert die aktuellen Einstellungen als neue Vorlage.</li>
            <li><b>Löschen:</b> Löscht die ausgewählte Vorlage.</li>
        </ul>

        <h3>2. Klassen & Spalten konfigurieren</h3>
        <h4>Linke Seite: Klassen auswählen</h4>
        <ul>
            <li>Wählen Sie die Klassen (z.B. Signal, Koordinate), die Sie in den Export aufnehmen möchten, indem Sie die Kontrollkästchen aktivieren/deaktivieren.</li>
            <li><b>Alle / Keine:</b> Buttons zum schnellen Auswählen oder Abwählen aller Klassen.</li>
        </ul>
        <h4>Rechte Seite: Spalten für die ausgewählte Klasse konfigurieren</h4>
        <ul>
            <li>Wählen Sie eine Klasse auf der linken Seite aus, um ihre Spalten hier zu konfigurieren.</li>
            <li><b>Exportieren:</b> Aktivieren/Deaktivieren Sie das Kontrollkästchen, um die Spalte in den Export aufzunehmen.</li>
            <li><b>Spaltenname (Daten):</b> Der interne Name des Datenfeldes (nicht bearbeitbar).</li>
            <li><b>Anzeigename (Excel):</b> Der Text, der als Spaltenüberschrift in Excel verwendet wird (bearbeitbar).</li>
            <li><b>Reihenfolge:</b> Zeigt die aktuelle Position der Spalte an. Verwenden Sie die Pfeil-Buttons (<b>↑ Nach oben / ↓ Nach unten</b>), um die Reihenfolge der Spalten im Export anzupassen.</li>
            <li><b>Alle auswählen / Alle abwählen:</b> Buttons zum schnellen Auswählen oder Abwählen aller Spalten für die aktuelle Klasse.</li>
        </ul>
        
        <h3>3. Export-Optionen</h3>
        <ul>
            <li><b>Separate Arbeitsblätter pro Klasse:</b>
                <ul>
                    <li><b>Aktiviert:</b> Jede ausgewählte Klasse wird in ein eigenes Arbeitsblatt in der Excel-Datei exportiert.</li>
                    <li><b>Deaktiviert:</b> Alle ausgewählten Daten werden in einem einzigen Arbeitsblatt zusammengeführt.</li>
                </ul>
            </li>
            <li><b>Aktuelle Filter anwenden:</b> Wenn aktiviert, werden nur die Elemente exportiert, die den aktuell im Auditing-Fenster eingestellten Filtern (Klasse, Text, Konfidenz) entsprechen.</li>
            <li><b>Leere Zellen einschließen:</b> Wenn deaktiviert, werden leere Werte als leere Zeichenketten exportiert.</li>
            <li><b>Spaltenbreite automatisch anpassen:</b> Versucht, die Spaltenbreite in Excel automatisch an den Inhalt anzupassen.</li>
            <li><b>Kopfzeile fixieren:</b> Friert die erste Zeile (Spaltenüberschriften) in Excel ein, sodass diese beim Scrollen sichtbar bleibt.</li>
            <li><b>Sortierung:</b> Legt die primäre Sortierreihenfolge der Daten im Excel-Export fest.</li>
        </ul>
        
        <h3>4. Vorschau</h3>
        <p>Zeigt eine Zusammenfassung Ihrer aktuellen Export-Einstellungen an. Klicken Sie auf <b>"Vorschau aktualisieren"</b>, um die Anzeige zu aktualisieren.</p>

        <h3>Export starten</h3>
        <p>Klicken Sie auf <b>"📊 Exportieren"</b>, um den Export zu starten. Sie werden dann aufgefordert, einen Speicherort und Dateinamen für Ihre Excel-Datei auszuwählen.</p>
        """
        
        # Verwenden Sie den neuen HelpDialog
        help_dialog = HelpDialog("Hilfe - Excel Export Konfiguration", help_text, self)
        help_dialog.exec_()

class ExportTemplateManager:
    """Manage export templates with JSON persistence"""
    
    def __init__(self):
        self.templates_file = "export_templates.json"
        self.templates = self._load_templates()
    
    def _load_templates(self) -> dict:
        """Load templates from file"""
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to load templates: {e}")
                return {}
        return {}
    
    def _save_templates(self):
        """Save templates to file"""
        try:
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save templates: {e}")
    
    def save_template(self, name: str, config: dict):
        """Save a template"""
        self.templates[name] = config
        self._save_templates()
    
    def get_template(self, name: str) -> dict:
        """Get a template by name"""
        return self.templates.get(name, {})
    
    def delete_template(self, name: str):
        """Delete a template"""
        if name in self.templates:
            del self.templates[name]
            self._save_templates()
    
    def list_templates(self) -> list:
        """List all template names"""
        return list(self.templates.keys())