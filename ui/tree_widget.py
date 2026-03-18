from PyQt5 import QtCore, QtGui, QtWidgets
from core.pipelineworker import NO_OCR_CLASSES
from core.config_models import DEFAULT_UI_CONFIG
from typing import List, Dict, Tuple, Optional, Any, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from ui.auditing_window import AuditingWindow
    from ui.workspace_widget import WorkspaceWidget

from table_editor import (
    TableEditorDelegate,
    HeaderEditDialog,
    ColumnManagerDialog,
    FindReplaceDialog,
    AddRowDialog,
    AddColumnDialog,
    SortDialog,
    FilterDialog,
    StatisticsDialog
)

class AuditingTreeWidget(QtWidgets.QTreeWidget):
    """Enhanced tree widget for auditing with advanced editing features"""
    
    def __init__(self, workspace_ref: 'WorkspaceWidget'):
        super().__init__()
        self.workspace_ref = workspace_ref
        
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        
        # Set custom delegate for better editing
        self.setItemDelegate(TableEditorDelegate(self))

        # Track column visibility and headers - get from workspace UI config
        ui_config = self._get_ui_config()
        num_cols = ui_config.get_column_count()
        self._column_visibility = [True] * num_cols
        self._original_headers = ui_config.get_column_headers()
        self._display_headers = self._original_headers.copy()
        self.setSortingEnabled(False)  # We'll handle sorting manually
        
        # Filter state
        self._active_filter = None
        self._filtered_items = set()
        
        # Connect selection changed signal
        self.itemSelectionChanged.connect(self._update_selection_count)
        
        # Connect item changed signal for row count updates
        self.model().rowsInserted.connect(self._update_row_count)
        self.model().rowsRemoved.connect(self._update_row_count)
    
    def _set_status(self, message: str):
        """Safely set status message"""
        try:
            if self.workspace_ref and hasattr(self.workspace_ref, '_set_status'):
                self.workspace_ref._set_status(message)
            else:
                print(f"[TREE STATUS] {message}")
        except Exception as e:
            print(f"[TREE STATUS ERROR] {message} ({e})")

    def _get_ui_config(self):
        """Get UI configuration from workspace's profile config."""
        try:
            if self.workspace_ref and hasattr(self.workspace_ref, '_get_ui_config'):
                return self.workspace_ref._get_ui_config()
        except Exception as e:
            print(f"[TREE] Failed to get UI config: {e}")
        return DEFAULT_UI_CONFIG
    
    def _show_menu(self, pos: QtCore.QPoint):
        """Show context menu"""
        m = QtWidgets.QMenu(self)
        selected = self.selectedItems()
        has_selection = len(selected) > 0
        
        # EDIT MENU
        edit_menu = m.addMenu(" Bearbeiten")
        
        act_copy = edit_menu.addAction("Kopieren (Ctrl+C)")
        act_copy.setEnabled(has_selection)
        act_copy.triggered.connect(self.copy_selection)
        
        act_cut = edit_menu.addAction("Ausschneiden (Ctrl+X)")
        act_cut.setEnabled(has_selection)
        act_cut.triggered.connect(self.cut_selection)
        
        act_paste = edit_menu.addAction("Einfügen (Ctrl+V)")
        act_paste.triggered.connect(self.paste_from_clipboard)
        
        edit_menu.addSeparator()

        act_find = edit_menu.addAction("Suchen und Ersetzen... (Ctrl+F)")
        act_find.triggered.connect(self.find_replace)
        
        # INSERT MENU
        insert_menu = m.addMenu(" Einfügen")
        
        act_add_row = insert_menu.addAction("Zeile hinzufügen...")
        act_add_row.triggered.connect(self.add_row)
        
        act_add_col = insert_menu.addAction("Spalte hinzufügen...")
        act_add_col.triggered.connect(self.add_column)
        
        # DELETE MENU
        delete_menu = m.addMenu(" Löschen")
        
        act_del_rows = delete_menu.addAction("Ausgewählte Zeilen löschen")
        act_del_rows.setEnabled(has_selection)
        act_del_rows.triggered.connect(self.workspace_ref.on_delete_selected_table_rows)
        
        act_del_col = delete_menu.addAction("Spalte löschen...")
        act_del_col.triggered.connect(self.delete_column)
        
        delete_menu.addSeparator()
        
        act_clear_cells = delete_menu.addAction("Zelleninhalt löschen")
        act_clear_cells.setEnabled(has_selection)
        act_clear_cells.triggered.connect(self.clear_cells)
        
        # COLUMN MENU
        column_menu = m.addMenu(" Spalten")
        
        act_edit_headers = column_menu.addAction("Überschriften bearbeiten...")
        act_edit_headers.triggered.connect(self.edit_headers)
        
        act_manage_columns = column_menu.addAction("Spalten verwalten...")
        act_manage_columns.triggered.connect(self.manage_columns)
        
        column_menu.addSeparator()
        
        act_resize = column_menu.addAction("Spaltenbreite anpassen")
        act_resize.triggered.connect(self.resize_columns_to_contents)
        
        # DATA MENU
        data_menu = m.addMenu(" Daten")
        
        act_sort = data_menu.addAction("Sortieren...")
        act_sort.triggered.connect(self.show_sort_dialog)
        
        act_filter = data_menu.addAction("Filter...")
        act_filter.triggered.connect(self.show_filter_dialog)
        
        data_menu.addSeparator()
        
        act_stats = data_menu.addAction("Statistik anzeigen")
        act_stats.triggered.connect(self.show_statistics)
        
        m.addSeparator()
        
        # Pop-out/Dock actions
        if self.workspace_ref.tree_window is None:
            m.addAction("Tabelle auskoppeln", self.workspace_ref.on_pop_out_tree)
        else:
            m.addAction("Tabelle andocken", self.workspace_ref.on_redock_tree)
        
        m.addSeparator()
        
        # Re-OCR actions
        item = selected[0] if selected else None
        
        # Only show Re-OCR if a valid child item AND valid column is selected
        if item and item.childCount() == 0:
            row_id = item.data(0, QtCore.Qt.UserRole)
            current_column = self.currentColumn()
            
            # Only columns 0 and 1 can be re-OCR'd
            if row_id is not None and current_column in [0, 1]:
                cls = self.workspace_ref.get_class_for_row_id(row_id)
                
                # Only show for classes that have OCR
                if cls and cls not in NO_OCR_CLASSES:
                    act_h = m.addAction("Re-OCR (Horizontal/Cardinal)")
                    act_a = m.addAction("Re-OCR (Angular/Tilted)")
                    
                    act_h.triggered.connect(lambda: self.workspace_ref.on_rerun_ocr(row_id, 'horizontal'))
                    act_a.triggered.connect(lambda: self.workspace_ref.on_rerun_ocr(row_id, 'angular'))
                    
                    m.addSeparator()
        
        act_del = m.addAction("Ausgewählte Zeilen löschen", self.workspace_ref.on_delete_selected_table_rows)
        act_del.setEnabled(len(selected) > 0)
        
        m.exec_(self.mapToGlobal(pos))
    
    # ============================================================================
    # ADD/DELETE OPERATIONS
    # ============================================================================
    
    def add_row(self):
        """Add new row"""
        categories = []
        for i in range(self.topLevelItemCount()):
            categories.append(self.topLevelItem(i).text(0))

        if not categories:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Kategorien",
                "Keine Kategorien vorhanden."
            )
            return

        # Get column names from profile config
        ui_config = self._get_ui_config()
        column_names = ui_config.get_column_headers()
        dialog = AddRowDialog(categories, self.columnCount(), self, column_names=column_names)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            category, position, data = dialog.get_data()
            
            # Find category parent
            parent = None
            for i in range(self.topLevelItemCount()):
                if self.topLevelItem(i).text(0) == category:
                    parent = self.topLevelItem(i)
                    break
            
            if not parent:
                return
            
            # Create new item
            new_item = QtWidgets.QTreeWidgetItem()
            for col, value in enumerate(data):
                new_item.setText(col, value)
            
            new_item.setFlags(new_item.flags() | QtCore.Qt.ItemIsEditable)
            
            # Insert at position
            if position == 'end':
                parent.addChild(new_item)
            elif position == 'before':
                current = self.currentItem()
                if current and current.parent() == parent:
                    index = parent.indexOfChild(current)
                    parent.insertChild(index, new_item)
                else:
                    parent.addChild(new_item)
            else:  # after
                current = self.currentItem()
                if current and current.parent() == parent:
                    index = parent.indexOfChild(current)
                    parent.insertChild(index + 1, new_item)
                else:
                    parent.addChild(new_item)
            
            # Expand parent and select new item
            parent.setExpanded(True)
            self.setCurrentItem(new_item)
    
    def add_column(self):
        """Add new column"""
        dialog = AddColumnDialog(self._display_headers, self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            name, position, default = dialog.get_data()
            
            if not name:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Fehler",
                    "Bitte geben Sie einen Spaltennamen ein."
                )
                return
            
            # Determine insert position
            if position == 'end':
                col_index = self.columnCount()
            elif position == 'before':
                col_index = self.currentColumn()
            else:  # after
                col_index = self.currentColumn() + 1
            
            # Insert column
            self.setColumnCount(self.columnCount() + 1)
            
            # Shift existing columns if needed
            if col_index < self.columnCount() - 1:
                for i in range(self.topLevelItemCount()):
                    parent = self.topLevelItem(i)
                    for j in range(parent.childCount()):
                        item = parent.child(j)
                        # Shift values
                        for c in range(self.columnCount() - 1, col_index, -1):
                            item.setText(c, item.text(c - 1))
                        item.setText(col_index, default)
            
            # Update headers
            self._display_headers.insert(col_index, name)
            self._original_headers.insert(col_index, name)
            self._column_visibility.insert(col_index, True)
            self.setHeaderLabels(self._display_headers)
    
    def delete_column(self):
        """Delete a column"""
        if self.columnCount() <= 1:
            QtWidgets.QMessageBox.warning(
                self,
                "Fehler",
                "Mindestens eine Spalte muss vorhanden bleiben."
            )
            return
        
        # Ask which column
        col_name, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Spalte löschen",
            "Wählen Sie die zu löschende Spalte:",
            self._display_headers,
            0,
            False
        )
        
        if not ok:
            return
        
        col_index = self._display_headers.index(col_name)
        
        # Confirm
        reply = QtWidgets.QMessageBox.question(
            self,
            "Spalte löschen",
            f"Möchten Sie die Spalte '{col_name}' wirklich löschen?\n\n"
            "Diese Aktion kann nicht rückgängig gemacht werden.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Remove column data
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                item = parent.child(j)
                # Shift values left
                for c in range(col_index, self.columnCount() - 1):
                    item.setText(c, item.text(c + 1))
                item.setText(self.columnCount() - 1, "")
        
        # Remove column
        self.setColumnCount(self.columnCount() - 1)
        
        # Update headers
        del self._display_headers[col_index]
        del self._original_headers[col_index]
        del self._column_visibility[col_index]
        self.setHeaderLabels(self._display_headers)
    
    def clear_cells(self):
        """Clear content of selected cells"""
        selected = self.selectedItems()
        if not selected:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Zelleninhalt löschen",
            f"Möchten Sie den Inhalt von {len(selected)} Zelle(n) löschen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        for item in selected:
            if item.childCount() == 0:  # Only child items
                for col in range(self.columnCount()):
                    item.setText(col, "")
    
    def cut_selection(self):
        """Cut selected cells"""
        self.copy_selection()
        self.clear_cells()

    # ============================================================================
    # COLUMN OPERATIONS
    # ============================================================================
    
    def resize_columns_to_contents(self):
        """Auto-resize all columns"""
        for i in range(self.columnCount()):
            self.resizeColumnToContents(i)
    
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
    
    # ============================================================================
    # SORT/FILTER OPERATIONS
    # ============================================================================
    
    def show_sort_dialog(self):
        """Show sort dialog"""
        dialog = SortDialog(self._display_headers, self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            sort_params = dialog.get_sort_params()
            self.sort_by_columns(sort_params)
    
    def sort_by_columns(self, params: List[Tuple[int, bool]]):
        """Sort tree by multiple columns"""
        if not params:
            return
        
        # Sort each category separately
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            
            # Get all child items
            items = []
            for j in range(parent.childCount()):
                items.append(parent.child(j))
            
            # Remove from tree
            for item in items:
                parent.removeChild(item)
            
            # Sort items
            def sort_key(item):
                keys = []
                for col_idx, ascending in params:
                    text = item.text(col_idx)
                    # Try numeric sort
                    try:
                        keys.append(float(text))
                    except ValueError:
                        keys.append(text.lower())
                return tuple(keys)
            
            items.sort(key=sort_key, reverse=not params[0][1])
            
            # Re-add sorted items
            for item in items:
                parent.addChild(item)
    
    def show_filter_dialog(self):
        """Show filter dialog"""
        dialog = FilterDialog(self._display_headers, self)
        
        # Connect buttons
        dialog.btn_apply.clicked.connect(lambda: self._apply_filter(dialog))
        dialog.btn_clear.clicked.connect(self.clear_filter)
    
    def _apply_filter(self, dialog: FilterDialog):
        """Apply filter"""
        params = dialog.get_filter_params()
        if not params:
            return
        
        col_idx, operator, value, case_sensitive, use_regex = params
        
        # Prepare pattern
        if use_regex:
            try:
                pattern = re.compile(value, 0 if case_sensitive else re.IGNORECASE)
            except re.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Regex-Fehler",
                    "Ungültiger regulärer Ausdruck"
                )
                return
        
        # Filter items
        self._filtered_items.clear()
        
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            
            for j in range(parent.childCount()):
                item = parent.child(j)
                text = item.text(col_idx)
                
                # Apply operator
                match = False
                
                if operator == "enthält":
                    if use_regex:
                        match = bool(pattern.search(text))
                    else:
                        compare_text = text if case_sensitive else text.lower()
                        compare_value = value if case_sensitive else value.lower()
                        match = compare_value in compare_text
                
                elif operator == "enthält nicht":
                    if use_regex:
                        match = not bool(pattern.search(text))
                    else:
                        compare_text = text if case_sensitive else text.lower()
                        compare_value = value if case_sensitive else value.lower()
                        match = compare_value not in compare_text
                
                elif operator == "ist gleich":
                    compare_text = text if case_sensitive else text.lower()
                    compare_value = value if case_sensitive else value.lower()
                    match = compare_text == compare_value
                
                elif operator == "ist nicht gleich":
                    compare_text = text if case_sensitive else text.lower()
                    compare_value = value if case_sensitive else value.lower()
                    match = compare_text != compare_value
                
                elif operator == "beginnt mit":
                    compare_text = text if case_sensitive else text.lower()
                    compare_value = value if case_sensitive else value.lower()
                    match = compare_text.startswith(compare_value)
                
                elif operator == "endet mit":
                    compare_text = text if case_sensitive else text.lower()
                    compare_value = value if case_sensitive else value.lower()
                    match = compare_text.endswith(compare_value)
                
                elif operator == "ist leer":
                    match = not text.strip()
                
                elif operator == "ist nicht leer":
                    match = bool(text.strip())
                
                # Hide/show item
                item.setHidden(not match)
                
                if not match:
                    self._filtered_items.add(id(item))
        
        self._active_filter = params
        dialog.accept()
    
    def clear_filter(self):
        """Clear active filter"""
        # Show all items
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            for j in range(parent.childCount()):
                parent.child(j).setHidden(False)
        
        self._filtered_items.clear()
        self._active_filter = None
    
    # ============================================================================
    # STATISTICS
    # ============================================================================
    
    def show_statistics(self):
        """Show table statistics"""
        stats = self._calculate_statistics()
        
        dialog = StatisticsDialog(stats, self)
        dialog.exec_()
    
    def _calculate_statistics(self) -> Dict[str, Any]:
        """Calculate table statistics"""
        stats = {}
        
        # Count rows and categories
        total_rows = 0
        category_counts = {}
        
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            cat_name = parent.text(0)
            count = parent.childCount()
            
            category_counts[cat_name] = count
            total_rows += count
        
        stats['total_rows'] = total_rows
        stats['total_categories'] = self.topLevelItemCount()
        stats['total_columns'] = self.columnCount()
        stats['category_counts'] = category_counts
        
        # Column statistics
        column_stats = {}
        
        for col in range(self.columnCount()):
            col_name = self._display_headers[col]
            filled = 0
            empty = 0
            unique_values = set()
            
            for i in range(self.topLevelItemCount()):
                parent = self.topLevelItem(i)
                for j in range(parent.childCount()):
                    item = parent.child(j)
                    text = item.text(col)
                    
                    if text.strip():
                        filled += 1
                        unique_values.add(text)
                    else:
                        empty += 1
            
            column_stats[col_name] = {
                'filled': filled,
                'empty': empty,
                'unique': len(unique_values)
            }
        
        stats['column_stats'] = column_stats
        
        return stats
    
    # ============================================================================
    # FIND/REPLACE
    # ============================================================================
    
    def find_replace(self):
        """Show find/replace dialog"""
        dialog = FindReplaceDialog(self)
        
        # Connect signals
        dialog.btn_find_next.clicked.connect(lambda: self._find_next(dialog))
        dialog.btn_replace.clicked.connect(lambda: self._replace_current(dialog))
        dialog.btn_replace_all.clicked.connect(lambda: self._replace_all(dialog))
        
        dialog.exec_()
    
    def _find_next(self, dialog: 'FindReplaceDialog'):
        """Find next occurrence"""
        search_text = dialog.find_input.text()
        if not search_text:
            return
        
        case_sensitive = dialog.case_sensitive.isChecked()
        whole_word = dialog.whole_word.isChecked()
        use_regex = dialog.regex_mode.isChecked()
        
        # Get current position
        current = self.currentItem()
        
        # Start search from next item
        iterator = QtWidgets.QTreeWidgetItemIterator(
            self,
            QtWidgets.QTreeWidgetItemIterator.NoChildren  # Only child items
        )
        
        # Skip to current position
        if current:
            while iterator.value() and iterator.value() != current:
                iterator += 1
            iterator += 1  # Move to next
        
        # Search forward
        while iterator.value():
            item = iterator.value()
            
            # Search all columns
            for col in range(self.columnCount()):
                text = item.text(col)
                
                if self._matches(text, search_text, case_sensitive, whole_word, use_regex):
                    # Found match
                    self.setCurrentItem(item)
                    self.scrollToItem(item)
                    item.setSelected(True)
                    
                    # Update status
                    self._set_status(f"Gefunden: '{search_text}'")
                    return
            
            iterator += 1
        
        # Not found - wrap around?
        reply = QtWidgets.QMessageBox.question(
            self,
            "Suche",
            f"'{search_text}' nicht gefunden.\n\nVon Anfang an suchen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Reset iterator to beginning
            iterator = QtWidgets.QTreeWidgetItemIterator(
                self,
                QtWidgets.QTreeWidgetItemIterator.NoChildren
            )
            
            # Search from beginning
            while iterator.value():
                item = iterator.value()
                
                for col in range(self.columnCount()):
                    text = item.text(col)
                    
                    if self._matches(text, search_text, case_sensitive, whole_word, use_regex):
                        self.setCurrentItem(item)
                        self.scrollToItem(item)
                        item.setSelected(True)
                        return
                
                iterator += 1
            
            # Still not found
            QtWidgets.QMessageBox.information(
                self,
                "Suche",
                f"'{search_text}' wurde nicht gefunden."
            )
    
    def _replace_current(self, dialog: 'FindReplaceDialog'):
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
    
    def _replace_all(self, dialog: 'FindReplaceDialog'):
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
    
    # ============================================================================
    # CLIPBOARD OPERATIONS
    # ============================================================================
    
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
    
    # ============================================================================
    # HELPER METHODS
    # ============================================================================
    
    def _matches(self, text: str, search_text: str, case_sensitive: bool, 
                whole_word: bool, use_regex: bool) -> bool:
        """Check if text matches search criteria"""
        if not text or not search_text:
            return False
        
        try:
            if use_regex:
                # Regex matching
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(search_text, flags)
                return pattern.search(text) is not None
            
            elif whole_word:
                # Whole word matching
                if case_sensitive:
                    pattern = r'\b' + re.escape(search_text) + r'\b'
                    return re.search(pattern, text) is not None
                else:
                    pattern = r'\b' + re.escape(search_text) + r'\b'
                    return re.search(pattern, text, re.IGNORECASE) is not None
            
            else:
                # Simple substring matching
                if case_sensitive:
                    return search_text in text
                else:
                    return search_text.lower() in text.lower()
        
        except re.error as e:
            QtWidgets.QMessageBox.warning(
                self,
                "Ungültiger regulärer Ausdruck",
                f"Fehler im regulären Ausdruck:\n{str(e)}"
            )
            return False
    
    def _update_selection_count(self):
        """Update selection count in status bar"""
        selected_count = len(self.selectedItems())
        self._set_status(f"Auswahl: {selected_count} Zeile(n)")
    
    def _update_row_count(self):
        """Update total row count in status bar"""
        total_rows = self._count_data_rows()
        self._set_status(f"Gesamt: {total_rows} Zeile(n)")
    
    def _count_data_rows(self) -> int:
        """Count total number of data rows (excluding category headers)"""
        count = 0
        
        for i in range(self.topLevelItemCount()):
            category_item = self.topLevelItem(i)
            count += category_item.childCount()
        
        return count
    
        # ============================================================================
    # HIGHLIGHT METHODS (for comparison dialog integration)
    # ============================================================================

    def highlight_row(self, row_id: int):
        """
        Highlight a specific row by its row_id.
        Used by the comparison dialog to show changed elements.
        
        Args:
            row_id: The row_id stored in the item's UserRole data
        """
        if row_id is None:
            return
        
        # Find the item with this row_id
        target_item = None
        
        for i in range(self.topLevelItemCount()):
            parent = self.topLevelItem(i)
            
            for j in range(parent.childCount()):
                item = parent.child(j)
                item_row_id = item.data(0, QtCore.Qt.UserRole)
                
                if item_row_id == row_id:
                    target_item = item
                    break
            
            if target_item:
                break
        
        if not target_item:
            print(f"[TREE] Row ID {row_id} not found in tree")
            return
        
        # Expand parent category
        parent = target_item.parent()
        if parent:
            parent.setExpanded(True)
        
        # Clear previous selection
        self.clearSelection()
        
        # Select and scroll to item
        target_item.setSelected(True)
        self.setCurrentItem(target_item)
        self.scrollToItem(target_item, QtWidgets.QAbstractItemView.PositionAtCenter)
        
        # Optional: Flash the item to draw attention
        self._flash_item(target_item)
        
        print(f"[TREE] Highlighted row_id {row_id}")

    def _flash_item(self, item: QtWidgets.QTreeWidgetItem):
        """
        Flash an item briefly to draw attention.
        
        Args:
            item: The tree widget item to flash
        """
        # Store original background
        original_bg = item.background(0)
        
        # Create flash color (light blue)
        flash_color = QtGui.QColor(135, 206, 250, 150)  # Light sky blue with transparency
        
        # Flash sequence
        def restore_bg():
            try:
                # Check if item still exists (may have been deleted on page change)
                for col in range(self.columnCount()):
                    item.setBackground(col, original_bg)
            except RuntimeError:
                # Item was deleted before timer fired - ignore
                pass
        
        # Set flash color
        for col in range(self.columnCount()):
            item.setBackground(col, flash_color)
        
        # Restore after 500ms
        QtCore.QTimer.singleShot(500, restore_bg)