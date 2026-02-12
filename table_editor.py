# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Complete Excel-like table editing features.
"""
from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Optional, Tuple, Dict, Any
import pandas as pd
import re
import csv
from datetime import datetime

class TableEditorDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate for enhanced cell editing"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, 
                    index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        """Create editor widget based on column type"""
        
        tree = self.parent()
        if not isinstance(tree, QtWidgets.QTreeWidget):
            return super().createEditor(parent, option, index)
        
        column = index.column()
        
        if column == 2:  # Fahrtrichtung
            editor = QtWidgets.QComboBox(parent)
            editor.addItems(['', 'A', 'B'])
            return editor
        elif column == 3:  # Seite
            editor = QtWidgets.QSpinBox(parent)
            editor.setMinimum(1)
            editor.setMaximum(9999)
            return editor
        else:
            editor = QtWidgets.QLineEdit(parent)
            editor.setFrame(False)
            return editor
    
    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        """Set editor data from model"""
        tree = self.parent()
        if not isinstance(tree, QtWidgets.QTreeWidget):
            return super().setEditorData(editor, index)
        
        item = tree.itemFromIndex(index)
        if not item:
            return
        
        value = item.text(index.column())
        
        if isinstance(editor, QtWidgets.QSpinBox):
            try:
                editor.setValue(int(value) if value else 1)
            except ValueError:
                editor.setValue(1)
        elif isinstance(editor, QtWidgets.QComboBox):
            editor.setCurrentText(str(value) if value else '')
        elif isinstance(editor, QtWidgets.QLineEdit):
            editor.setText(str(value) if value else '')
    
    def setModelData(self, editor: QtWidgets.QWidget, model: QtCore.QAbstractItemModel, 
                    index: QtCore.QModelIndex):
        """Set model data from editor"""
        tree = self.parent()
        if not isinstance(tree, QtWidgets.QTreeWidget):
            return super().setModelData(editor, model, index)
        
        item = tree.itemFromIndex(index)
        if not item:
            return
        
        if isinstance(editor, QtWidgets.QSpinBox):
            item.setText(index.column(), str(editor.value()))
        elif isinstance(editor, QtWidgets.QComboBox):
            item.setText(index.column(), editor.currentText())
        elif isinstance(editor, QtWidgets.QLineEdit):
            item.setText(index.column(), editor.text())


class AddRowDialog(QtWidgets.QDialog):
    """Dialog for adding new rows"""
    
    def __init__(self, categories: List[str], column_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zeile hinzufügen")
        self.resize(500, 400)
        
        self.categories = categories
        self.column_count = column_count
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Category selection
        cat_layout = QtWidgets.QFormLayout()
        
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.addItems(self.categories)
        cat_layout.addRow("Kategorie:", self.category_combo)
        
        layout.addLayout(cat_layout)
        
        # Position
        pos_group = QtWidgets.QGroupBox("Position")
        pos_layout = QtWidgets.QVBoxLayout(pos_group)
        
        self.pos_end = QtWidgets.QRadioButton("Am Ende hinzufügen")
        self.pos_end.setChecked(True)
        pos_layout.addWidget(self.pos_end)
        
        self.pos_before = QtWidgets.QRadioButton("Vor ausgewählter Zeile einfügen")
        pos_layout.addWidget(self.pos_before)
        
        self.pos_after = QtWidgets.QRadioButton("Nach ausgewählter Zeile einfügen")
        pos_layout.addWidget(self.pos_after)
        
        layout.addWidget(pos_group)
        
        # Data input
        data_group = QtWidgets.QGroupBox("Daten")
        data_layout = QtWidgets.QFormLayout(data_group)
        
        self.data_inputs = []
        column_names = ["Text/Nummer", "Koordinatentext", "Fahrtrichtung", "Seite"]
        
        for i in range(min(self.column_count, len(column_names))):
            line_edit = QtWidgets.QLineEdit()
            data_layout.addRow(f"{column_names[i]}:", line_edit)
            self.data_inputs.append(line_edit)
        
        layout.addWidget(data_group)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_data(self) -> Tuple[str, str, List[str]]:
        """Get entered data"""
        category = self.category_combo.currentText()
        
        if self.pos_end.isChecked():
            position = 'end'
        elif self.pos_before.isChecked():
            position = 'before'
        else:
            position = 'after'
        
        data = [edit.text() for edit in self.data_inputs]
        
        return category, position, data


class AddColumnDialog(QtWidgets.QDialog):
    """Dialog for adding new columns"""
    
    def __init__(self, current_columns: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spalte hinzufügen")
        self.resize(400, 300)
        
        self.current_columns = current_columns
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Column name
        name_layout = QtWidgets.QFormLayout()
        
        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("z.B. 'Bemerkungen'")
        name_layout.addRow("Spaltenname:", self.name_input)
        
        layout.addLayout(name_layout)
        
        # Position
        pos_group = QtWidgets.QGroupBox("Position")
        pos_layout = QtWidgets.QVBoxLayout(pos_group)
        
        self.pos_end = QtWidgets.QRadioButton("Am Ende hinzufügen")
        self.pos_end.setChecked(True)
        pos_layout.addWidget(self.pos_end)
        
        self.pos_before = QtWidgets.QRadioButton("Vor ausgewählter Spalte einfügen")
        pos_layout.addWidget(self.pos_before)
        
        self.pos_after = QtWidgets.QRadioButton("Nach ausgewählter Spalte einfügen")
        pos_layout.addWidget(self.pos_after)
        
        layout.addWidget(pos_group)
        
        # Default value
        default_layout = QtWidgets.QFormLayout()
        
        self.default_input = QtWidgets.QLineEdit()
        self.default_input.setPlaceholderText("(leer lassen für keine Vorgabe)")
        default_layout.addRow("Standardwert:", self.default_input)
        
        layout.addLayout(default_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_data(self) -> Tuple[str, str, str]:
        """Get entered data"""
        name = self.name_input.text().strip()
        
        if self.pos_end.isChecked():
            position = 'end'
        elif self.pos_before.isChecked():
            position = 'before'
        else:
            position = 'after'
        
        default = self.default_input.text()
        
        return name, position, default


class HeaderEditDialog(QtWidgets.QDialog):
    """Dialog for editing column headers"""
    
    def __init__(self, current_headers: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spaltenüberschriften bearbeiten")
        self.resize(500, 400)
        
        self.current_headers = current_headers
        self.new_headers = current_headers.copy()
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            "Bearbeiten Sie die Spaltenüberschriften.\n"
            "Hinweis: Dies ändert nur die Anzeige, nicht die internen Daten."
        )
        layout.addWidget(info)
        
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Original", "Neue Bezeichnung"])
        self.table.setRowCount(len(self.current_headers))
        
        for i, header in enumerate(self.current_headers):
            orig_item = QtWidgets.QTableWidgetItem(header)
            orig_item.setFlags(orig_item.flags() & ~QtCore.Qt.ItemIsEditable)
            orig_item.setBackground(QtGui.QColor(240, 240, 240))
            self.table.setItem(i, 0, orig_item)
            
            edit_item = QtWidgets.QTableWidgetItem(header)
            self.table.setItem(i, 1, edit_item)
        
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_new_headers(self) -> List[str]:
        """Get edited headers"""
        new_headers = []
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            new_headers.append(item.text() if item else self.current_headers[i])
        return new_headers


class ColumnManagerDialog(QtWidgets.QDialog):
    """Dialog for showing/hiding columns"""
    
    def __init__(self, columns: List[str], visible_columns: List[bool], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spalten verwalten")
        self.resize(400, 500)
        
        self.columns = columns
        self.visible_columns = visible_columns.copy()
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel("Wählen Sie die anzuzeigenden Spalten:")
        layout.addWidget(info)
        
        self.list_widget = QtWidgets.QListWidget()
        
        for i, col in enumerate(self.columns):
            item = QtWidgets.QListWidgetItem(col)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if self.visible_columns[i] else QtCore.Qt.Unchecked)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        
        action_layout = QtWidgets.QHBoxLayout()
        
        btn_all = QtWidgets.QPushButton("Alle auswählen")
        btn_all.clicked.connect(self._select_all)
        action_layout.addWidget(btn_all)
        
        btn_none = QtWidgets.QPushButton("Keine auswählen")
        btn_none.clicked.connect(self._select_none)
        action_layout.addWidget(btn_none)
        
        btn_invert = QtWidgets.QPushButton("Auswahl umkehren")
        btn_invert.clicked.connect(self._invert_selection)
        action_layout.addWidget(btn_invert)
        
        layout.addLayout(action_layout)
        
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _select_all(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(QtCore.Qt.Checked)
    
    def _select_none(self):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(QtCore.Qt.Unchecked)
    
    def _invert_selection(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(
                QtCore.Qt.Unchecked if item.checkState() == QtCore.Qt.Checked 
                else QtCore.Qt.Checked
            )
    
    def get_visible_columns(self) -> List[bool]:
        """Get list of visible column flags"""
        visible = []
        for i in range(self.list_widget.count()):
            visible.append(self.list_widget.item(i).checkState() == QtCore.Qt.Checked)
        return visible


class FindReplaceDialog(QtWidgets.QDialog):
    """Find and replace dialog for table data"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suchen und Ersetzen")
        self.resize(450, 300)
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Find section
        find_group = QtWidgets.QGroupBox("Suchen")
        find_layout = QtWidgets.QFormLayout(find_group)
        
        self.find_input = QtWidgets.QLineEdit()
        self.find_input.setPlaceholderText("Suchtext eingeben...")
        find_layout.addRow("Suchen nach:", self.find_input)
        
        self.case_sensitive = QtWidgets.QCheckBox("Groß-/Kleinschreibung beachten")
        find_layout.addRow("", self.case_sensitive)
        
        self.regex_mode = QtWidgets.QCheckBox("Regex verwenden")
        find_layout.addRow("", self.regex_mode)
        
        self.whole_word = QtWidgets.QCheckBox("Nur ganze Wörter")
        find_layout.addRow("", self.whole_word)
        
        layout.addWidget(find_group)
        
        # Replace section
        replace_group = QtWidgets.QGroupBox("Ersetzen")
        replace_layout = QtWidgets.QFormLayout(replace_group)
        
        self.replace_input = QtWidgets.QLineEdit()
        self.replace_input.setPlaceholderText("Ersetzungstext eingeben...")
        replace_layout.addRow("Ersetzen durch:", self.replace_input)
        
        layout.addWidget(replace_group)
        
        # Column selection
        column_group = QtWidgets.QGroupBox("Bereich")
        column_layout = QtWidgets.QVBoxLayout(column_group)
        
        self.all_columns = QtWidgets.QRadioButton("Alle Spalten")
        self.all_columns.setChecked(True)
        column_layout.addWidget(self.all_columns)
        
        self.current_column = QtWidgets.QRadioButton("Nur aktuelle Spalte")
        column_layout.addWidget(self.current_column)
        
        layout.addWidget(column_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.btn_find_next = QtWidgets.QPushButton("Weiter suchen")
        self.btn_replace = QtWidgets.QPushButton("Ersetzen")
        self.btn_replace_all = QtWidgets.QPushButton("Alle ersetzen")
        btn_close = QtWidgets.QPushButton("Schließen")
        
        button_layout.addWidget(self.btn_find_next)
        button_layout.addWidget(self.btn_replace)
        button_layout.addWidget(self.btn_replace_all)
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        
        layout.addLayout(button_layout)
        
        btn_close.clicked.connect(self.reject)


class SortDialog(QtWidgets.QDialog):
    """Dialog for sorting table data"""
    
    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sortieren")
        self.resize(400, 300)
        
        self.columns = columns
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel("Wählen Sie die Sortierspalte:")
        layout.addWidget(info)
        
        # Primary sort
        primary_group = QtWidgets.QGroupBox("Primäre Sortierung")
        primary_layout = QtWidgets.QFormLayout(primary_group)
        
        self.primary_column = QtWidgets.QComboBox()
        self.primary_column.addItems(self.columns)
        primary_layout.addRow("Spalte:", self.primary_column)
        
        self.primary_order = QtWidgets.QComboBox()
        self.primary_order.addItems(["Aufsteigend", "Absteigend"])
        primary_layout.addRow("Reihenfolge:", self.primary_order)
        
        layout.addWidget(primary_group)
        
        # Secondary sort (optional)
        secondary_group = QtWidgets.QGroupBox("Sekundäre Sortierung (optional)")
        secondary_layout = QtWidgets.QFormLayout(secondary_group)
        
        self.use_secondary = QtWidgets.QCheckBox("Sekundäre Sortierung verwenden")
        secondary_layout.addRow("", self.use_secondary)
        
        self.secondary_column = QtWidgets.QComboBox()
        self.secondary_column.addItems(self.columns)
        self.secondary_column.setEnabled(False)
        secondary_layout.addRow("Spalte:", self.secondary_column)
        
        self.secondary_order = QtWidgets.QComboBox()
        self.secondary_order.addItems(["Aufsteigend", "Absteigend"])
        self.secondary_order.setEnabled(False)
        secondary_layout.addRow("Reihenfolge:", self.secondary_order)
        
        layout.addWidget(secondary_group)
        
        # Connect checkbox
        self.use_secondary.toggled.connect(self.secondary_column.setEnabled)
        self.use_secondary.toggled.connect(self.secondary_order.setEnabled)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_sort_params(self) -> List[Tuple[int, bool]]:
        """Get sort parameters as list of (column_index, ascending) tuples"""
        params = []
        
        # Primary sort
        col_idx = self.primary_column.currentIndex()
        ascending = self.primary_order.currentIndex() == 0
        params.append((col_idx, ascending))
        
        # Secondary sort
        if self.use_secondary.isChecked():
            col_idx = self.secondary_column.currentIndex()
            ascending = self.secondary_order.currentIndex() == 0
            params.append((col_idx, ascending))
        
        return params


class FilterDialog(QtWidgets.QDialog):
    """Dialog for filtering table data"""
    
    def __init__(self, columns: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter")
        self.resize(450, 350)
        
        self.columns = columns
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel("Definieren Sie Filterkriterien:")
        layout.addWidget(info)
        
        # Filter criteria
        filter_group = QtWidgets.QGroupBox("Kriterien")
        filter_layout = QtWidgets.QFormLayout(filter_group)
        
        self.column_combo = QtWidgets.QComboBox()
        self.column_combo.addItems(self.columns)
        filter_layout.addRow("Spalte:", self.column_combo)
        
        self.operator_combo = QtWidgets.QComboBox()
        self.operator_combo.addItems([
            "enthält",
            "enthält nicht",
            "ist gleich",
            "ist nicht gleich",
            "beginnt mit",
            "endet mit",
            "ist leer",
            "ist nicht leer"
        ])
        filter_layout.addRow("Operator:", self.operator_combo)
        
        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Filterwert...")
        filter_layout.addRow("Wert:", self.value_input)
        
        # Disable value input for "is empty" operators
        self.operator_combo.currentTextChanged.connect(self._on_operator_changed)
        
        layout.addWidget(filter_group)
        
        # Options
        options_group = QtWidgets.QGroupBox("Optionen")
        options_layout = QtWidgets.QVBoxLayout(options_group)
        
        self.case_sensitive = QtWidgets.QCheckBox("Groß-/Kleinschreibung beachten")
        options_layout.addWidget(self.case_sensitive)
        
        self.regex_mode = QtWidgets.QCheckBox("Regex verwenden")
        options_layout.addWidget(self.regex_mode)
        
        layout.addWidget(options_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.btn_apply = QtWidgets.QPushButton("Anwenden")
        self.btn_clear = QtWidgets.QPushButton("Filter löschen")
        btn_close = QtWidgets.QPushButton("Schließen")
        
        button_layout.addWidget(self.btn_apply)
        button_layout.addWidget(self.btn_clear)
        button_layout.addStretch()
        button_layout.addWidget(btn_close)
        
        layout.addLayout(button_layout)
        
        btn_close.clicked.connect(self.reject)
    
    def _on_operator_changed(self, text: str):
        """Enable/disable value input based on operator"""
        needs_value = text not in ["ist leer", "ist nicht leer"]
        self.value_input.setEnabled(needs_value)
    
    def get_filter_params(self) -> Optional[Tuple[int, str, str, bool, bool]]:
        """Get filter parameters"""
        column = self.column_combo.currentIndex()
        operator = self.operator_combo.currentText()
        value = self.value_input.text()
        case_sensitive = self.case_sensitive.isChecked()
        use_regex = self.regex_mode.isChecked()
        
        return (column, operator, value, case_sensitive, use_regex)


class StatisticsDialog(QtWidgets.QDialog):
    """Dialog showing table statistics"""
    
    def __init__(self, stats: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tabellenstatistik")
        self.resize(500, 400)
        
        self.stats = stats
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Statistics text
        text_edit = QtWidgets.QPlainTextEdit()
        text_edit.setReadOnly(True)
        
        stats_text = self._format_statistics()
        text_edit.setPlainText(stats_text)
        
        layout.addWidget(text_edit)
        
        # Close button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _format_statistics(self) -> str:
        """Format statistics as text"""
        lines = []
        lines.append("═" * 60)
        lines.append("TABELLENSTATISTIK")
        lines.append("═" * 60)
        lines.append("")
        
        # General stats
        lines.append("ALLGEMEIN:")
        lines.append(f"  Gesamtzeilen: {self.stats.get('total_rows', 0)}")
        lines.append(f"  Spalten: {self.stats.get('total_columns', 0)}")
        lines.append(f"  Kategorien: {self.stats.get('total_categories', 0)}")
        lines.append("")
        
        # Category breakdown
        if 'category_counts' in self.stats:
            lines.append("NACH KATEGORIE:")
            for cat, count in sorted(self.stats['category_counts'].items()):
                lines.append(f"  {cat}: {count}")
            lines.append("")
        
        # Column stats
        if 'column_stats' in self.stats:
            lines.append("SPALTENSTATISTIK:")
            for col_name, col_stats in self.stats['column_stats'].items():
                lines.append(f"  {col_name}:")
                lines.append(f"    Gefüllt: {col_stats.get('filled', 0)}")
                lines.append(f"    Leer: {col_stats.get('empty', 0)}")
                if 'unique' in col_stats:
                    lines.append(f"    Eindeutig: {col_stats['unique']}")
            lines.append("")
        
        lines.append("═" * 60)
        
        return "\n".join(lines)


class BulkEditDialog(QtWidgets.QDialog):
    """Dialog for bulk editing cells"""
    
    def __init__(self, selected_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Massenbearbeitung")
        self.resize(400, 250)
        
        self.selected_count = selected_count
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            f"Massenbearbeitung für {self.selected_count} ausgewählte Zelle(n)"
        )
        layout.addWidget(info)
        
        # Operation
        op_group = QtWidgets.QGroupBox("Operation")
        op_layout = QtWidgets.QVBoxLayout(op_group)
        
        self.op_set = QtWidgets.QRadioButton("Wert setzen")
        self.op_set.setChecked(True)
        op_layout.addWidget(self.op_set)
        
        self.op_append = QtWidgets.QRadioButton("Text anhängen")
        op_layout.addWidget(self.op_append)
        
        self.op_prepend = QtWidgets.QRadioButton("Text voranstellen")
        op_layout.addWidget(self.op_prepend)
        
        self.op_clear = QtWidgets.QRadioButton("Leeren")
        op_layout.addWidget(self.op_clear)
        
        layout.addWidget(op_group)
        
        # Value
        value_layout = QtWidgets.QFormLayout()
        
        self.value_input = QtWidgets.QLineEdit()
        self.value_input.setPlaceholderText("Wert eingeben...")
        value_layout.addRow("Wert:", self.value_input)
        
        layout.addLayout(value_layout)
        
        # Connect radio buttons
        self.op_clear.toggled.connect(lambda checked: self.value_input.setEnabled(not checked))
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_operation(self) -> Tuple[str, str]:
        """Get operation and value"""
        if self.op_set.isChecked():
            op = 'set'
        elif self.op_append.isChecked():
            op = 'append'
        elif self.op_prepend.isChecked():
            op = 'prepend'
        else:
            op = 'clear'
        
        value = self.value_input.text()
        
        return op, value