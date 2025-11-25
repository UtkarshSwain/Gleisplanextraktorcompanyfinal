# table_editor.py - Table editing features (helpers only)
from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List
import re

class TableEditorDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate for enhanced cell editing"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem, 
                    index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        """Create editor widget based on column type"""
        
        # Get the tree widget to access column info
        tree = self.parent()
        if not isinstance(tree, QtWidgets.QTreeWidget):
            return super().createEditor(parent, option, index)
        
        column = index.column()
        
        # Column 0: Text/Nummer - line edit (default)
        # Column 1: Koordinatentext - line edit (default)
        # Column 2: Fahrtrichtung - combobox
        # Column 3: Seite - spinbox
        
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
            # Default line edit
            editor = QtWidgets.QLineEdit(parent)
            editor.setFrame(False)
            return editor
    
    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex):
        """Set editor data from model"""
        # Get the item
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
        
        # Instructions
        info = QtWidgets.QLabel(
            "Bearbeiten Sie die Spaltenüberschriften.\n"
            "Hinweis: Dies ändert nur die Anzeige, nicht die internen Daten."
        )
        layout.addWidget(info)
        
        # Table for editing headers
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Original", "Neue Bezeichnung"])
        self.table.setRowCount(len(self.current_headers))
        
        for i, header in enumerate(self.current_headers):
            # Original (read-only)
            orig_item = QtWidgets.QTableWidgetItem(header)
            orig_item.setFlags(orig_item.flags() & ~QtCore.Qt.ItemIsEditable)
            orig_item.setBackground(QtGui.QColor(240, 240, 240))
            self.table.setItem(i, 0, orig_item)
            
            # Editable
            edit_item = QtWidgets.QTableWidgetItem(header)
            self.table.setItem(i, 1, edit_item)
        
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        
        # Buttons
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
        
        # Instructions
        info = QtWidgets.QLabel("Wählen Sie die anzuzeigenden Spalten:")
        layout.addWidget(info)
        
        # List widget with checkboxes
        self.list_widget = QtWidgets.QListWidget()
        
        for i, col in enumerate(self.columns):
            item = QtWidgets.QListWidgetItem(col)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if self.visible_columns[i] else QtCore.Qt.Unchecked)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        
        # Quick actions
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
        
        # Buttons
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
        self.resize(450, 250)
        
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