from PyQt5 import QtCore, QtGui, QtWidgets
from core.pipelineworker import NO_OCR_CLASSES
from ui.auditing_window import AuditingWindow
from table_editor import (
    TableEditorDelegate, 
    HeaderEditDialog, 
    ColumnManagerDialog, 
    FindReplaceDialog
)
class AuditingTreeWidget(QtWidgets.QTreeWidget):
    
    """Replaces AuditingTableView"""
    def __init__(self, auditing_window_ref: 'AuditingWindow', *a, **kw):
        super().__init__(*a, **kw)
        self.auditing_window_ref = auditing_window_ref
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        #Set custom delegate for better editing
        self.setItemDelegate(TableEditorDelegate(self))
        
        #Track column visibility and headers
        self._column_visibility = [True, True, True, True]  # 4 columns
        self._original_headers = ["Text/Nummer", "Koordinatentext", "Fahrtrichtung", "Seite"]
        self._display_headers = self._original_headers.copy()

    def _show_menu(self, pos: QtCore.QPoint):
            m = QtWidgets.QMenu(self)
            # Edit menu
            edit_menu = m.addMenu("✏️ Bearbeiten")
            
            act_copy = edit_menu.addAction("Kopieren (Ctrl+C)")
            act_copy.triggered.connect(self.copy_selection)
            
            act_paste = edit_menu.addAction("Einfügen (Ctrl+V)")
            act_paste.triggered.connect(self.paste_from_clipboard)
            
            edit_menu.addSeparator()
            
            act_find = edit_menu.addAction("Suchen und Ersetzen... (Ctrl+F)")
            act_find.triggered.connect(self.find_replace)
            
            # Column menu
            column_menu = m.addMenu("📊 Spalten")
            
            act_edit_headers = column_menu.addAction("Überschriften bearbeiten...")
            act_edit_headers.triggered.connect(self.edit_headers)
            
            act_manage_columns = column_menu.addAction("Spalten verwalten...")
            act_manage_columns.triggered.connect(self.manage_columns)
            
            m.addSeparator()
            # Pop-out/Dock actions
            # --- THIS IS THE FIX ---
            if self.auditing_window_ref.tree_window is None:
                m.addAction("Tabelle auskoppeln", self.auditing_window_ref.on_pop_out_tree)
            else:
                m.addAction("Tabelle andocken", self.auditing_window_ref.on_redock_tree)
            # --- END OF FIX ---
            
            m.addSeparator()

            # Re-OCR actions
            selected = self.selectedItems()
            item = selected[0] if selected else None
            
            # ✅ Only show Re-OCR if a valid child item AND valid column is selected
            if item and item.childCount() == 0:
                row_id = item.data(0, QtCore.Qt.UserRole)
                current_column = self.currentColumn()
                
                # ✅ Only columns 0 and 1 can be re-OCR'd (not Fahrtrichtung or Page)
                if row_id is not None and current_column in [0, 1]:
                    cls = self.auditing_window_ref.get_class_for_row_id(row_id)
                    
                    # Only show for classes that have OCR
                    if cls and cls not in NO_OCR_CLASSES:
                        act_h = m.addAction("Re-OCR (Horizontal/Cardinal)")
                        act_a = m.addAction("Re-OCR (Angular/Tilted)")
                        
                        act_h.triggered.connect(lambda: self.auditing_window_ref.on_rerun_ocr(row_id, 'horizontal'))
                        act_a.triggered.connect(lambda: self.auditing_window_ref.on_rerun_ocr(row_id, 'angular'))
                        
                        m.addSeparator()

            act_del = m.addAction("Ausgewählte Zeilen löschen", self.auditing_window_ref.on_delete_selected_table_rows)
            act_del.setEnabled(len(selected) > 0)
            m.exec_(self.mapToGlobal(pos))
        # ✅ NEW: Table editing methods
    
    def edit_headers(self):
        """Show header edit dialog"""
        dialog = HeaderEditDialog(self._display_headers, self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_headers = dialog.get_new_headers()
            self._display_headers = new_headers
            self.setHeaderLabels(new_headers)
            return True
        
        return False
    
    def manage_columns(self):
        """Show column manager dialog"""
        dialog = ColumnManagerDialog(
            self._display_headers,
            self._column_visibility,
            self
        )
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_visibility = dialog.get_visible_columns()
            
            # Apply visibility changes
            for i, visible in enumerate(new_visibility):
                self.setColumnHidden(i, not visible)
                self._column_visibility[i] = visible
            
            return True
        
        return False
    
    def find_replace(self):
        """Show find/replace dialog"""
        dialog = FindReplaceDialog(self)
        
        # Connect signals
        dialog.btn_find_next.clicked.connect(lambda: self._find_next(dialog))
        dialog.btn_replace.clicked.connect(lambda: self._replace_current(dialog))
        dialog.btn_replace_all.clicked.connect(lambda: self._replace_all(dialog))
        
        dialog.exec_()
    
    def _find_next(self, dialog: FindReplaceDialog):
        """Find next occurrence"""
        search_text = dialog.find_input.text()
        if not search_text:
            return
        
        case_sensitive = dialog.case_sensitive.isChecked()
        use_regex = dialog.regex_mode.isChecked()
        all_columns = dialog.all_columns.isChecked()
        
        # Get current selection
        current_item = self.currentItem()
        current_col = self.currentColumn()
        
        # Start search from current position
        start_item = current_item if current_item else self.topLevelItem(0)
        start_col = current_col + 1 if current_item else 0
        
        # Search
        found = self._search_from(
            start_item, start_col, search_text,
            case_sensitive, use_regex, all_columns
        )
        
        if found:
            item, col = found
            self.setCurrentItem(item)
            self.scrollToItem(item)
            self.setCurrentColumn(col)
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Suche",
                f"'{search_text}' nicht gefunden."
            )
    
    def _search_from(self, start_item, start_col, search_text, 
                    case_sensitive, use_regex, all_columns):
        """Search from given position"""
        
        # Prepare search pattern
        if use_regex:
            try:
                pattern = re.compile(
                    search_text,
                    0 if case_sensitive else re.IGNORECASE
                )
            except re.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Regex-Fehler",
                    "Ungültiger regulärer Ausdruck"
                )
                return None
        else:
            if not case_sensitive:
                search_text = search_text.lower()
        
        # Get all child items (skip parent category items)
        all_items = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                all_items.append(parent.child(j))
        
        # Find start index
        try:
            start_idx = all_items.index(start_item)
        except ValueError:
            start_idx = 0
        
        # Search from start position
        col_count = self.columnCount()
        
        for i in range(start_idx, len(all_items)):
            item = all_items[i]
            
            # Determine columns to search
            if all_columns:
                cols = range(col_count)
            else:
                cols = [start_col] if i == start_idx else range(col_count)
            
            for col in cols:
                text = item.text(col)
                
                # Match
                if use_regex:
                    if pattern.search(text):
                        return (item, col)
                else:
                    compare_text = text if case_sensitive else text.lower()
                    if search_text in compare_text:
                        return (item, col)
        
        return None
    
    def _replace_current(self, dialog: FindReplaceDialog):
        """Replace current selection"""
        current_item = self.currentItem()
        current_col = self.currentColumn()
        
        if not current_item or current_item.childCount() > 0:
            QtWidgets.QMessageBox.information(
                self,
                "Ersetzen",
                "Bitte wählen Sie eine Zelle aus."
            )
            return
        
        search_text = dialog.find_input.text()
        replace_text = dialog.replace_input.text()
        
        if not search_text:
            return
        
        # Get current text
        current_text = current_item.text(current_col)
        
        # Replace
        if dialog.regex_mode.isChecked():
            try:
                pattern = re.compile(
                    search_text,
                    0 if dialog.case_sensitive.isChecked() else re.IGNORECASE
                )
                new_text = pattern.sub(replace_text, current_text)
            except re.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Regex-Fehler",
                    "Ungültiger regulärer Ausdruck"
                )
                return
        else:
            if dialog.case_sensitive.isChecked():
                new_text = current_text.replace(search_text, replace_text)
            else:
                # Case-insensitive replace
                pattern = re.compile(re.escape(search_text), re.IGNORECASE)
                new_text = pattern.sub(replace_text, current_text)
        
        # Update
        current_item.setText(current_col, new_text)
        
        # Find next
        self._find_next(dialog)
    
    def _replace_all(self, dialog: FindReplaceDialog):
        """Replace all occurrences"""
        search_text = dialog.find_input.text()
        replace_text = dialog.replace_input.text()
        
        if not search_text:
            return
        
        case_sensitive = dialog.case_sensitive.isChecked()
        use_regex = dialog.regex_mode.isChecked()
        all_columns = dialog.all_columns.isChecked()
        
        # Prepare pattern
        if use_regex:
            try:
                pattern = re.compile(
                    search_text,
                    0 if case_sensitive else re.IGNORECASE
                )
            except re.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Regex-Fehler",
                    "Ungültiger regulärer Ausdruck"
                )
                return
        
        # Count replacements
        count = 0
        
        # Get all child items
        all_items = []
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                all_items.append(parent.child(j))
        
        # Replace in all items
        col_count = self.columnCount()
        
        for item in all_items:
            cols = range(col_count) if all_columns else [self.currentColumn()]
            
            for col in cols:
                text = item.text(col)
                
                # Replace
                if use_regex:
                    new_text = pattern.sub(replace_text, text)
                else:
                    if case_sensitive:
                        new_text = text.replace(search_text, replace_text)
                    else:
                        temp_pattern = re.compile(re.escape(search_text), re.IGNORECASE)
                        new_text = temp_pattern.sub(replace_text, text)
                
                if new_text != text:
                    item.setText(col, new_text)
                    count += 1
        
        QtWidgets.QMessageBox.information(
            self,
            "Ersetzen abgeschlossen",
            f"{count} Ersetzung(en) durchgeführt."
        )
    
    def copy_selection(self):
        """Copy selected cells to clipboard"""
        selected = self.selectedItems()
        if not selected:
            return
        
        # Filter out parent items
        child_items = [item for item in selected if item.childCount() == 0]
        if not child_items:
            return
        
        # Get selection as text (tab-separated)
        rows = {}
        for item in child_items:
            parent = item.parent()
            if not parent:
                continue
            
            row_idx = parent.indexOfChild(item)
            
            if row_idx not in rows:
                rows[row_idx] = []
            
            # Get all column values
            for col in range(self.columnCount()):
                rows[row_idx].append(item.text(col))
        
        # Build clipboard text
        clipboard_text = []
        for row_idx in sorted(rows.keys()):
            clipboard_text.append('\t'.join(rows[row_idx]))
        
        # Copy to clipboard
        QtWidgets.QApplication.clipboard().setText('\n'.join(clipboard_text))
    
    def paste_from_clipboard(self):
        """Paste from clipboard"""
        current_item = self.currentItem()
        if not current_item or current_item.childCount() > 0:
            QtWidgets.QMessageBox.information(
                self,
                "Einfügen",
                "Bitte wählen Sie eine Zelle aus."
            )
            return
        
        clipboard = QtWidgets.QApplication.clipboard()
        text = clipboard.text()
        
        if not text:
            return
        
        # Parse clipboard (tab-separated values)
        rows = text.split('\n')
        
        # Get starting position
        parent = current_item.parent()
        if not parent:
            return
        
        start_row = parent.indexOfChild(current_item)
        start_col = self.currentColumn()
        
        # Paste data
        for i, row_text in enumerate(rows):
            if not row_text.strip():
                continue
            
            row_idx = start_row + i
            if row_idx >= parent.childCount():
                break
            
            item = parent.child(row_idx)
            values = row_text.split('\t')
            
            for j, value in enumerate(values):
                col = start_col + j
                if col >= self.columnCount():
                    break
                
                item.setText(col, value)