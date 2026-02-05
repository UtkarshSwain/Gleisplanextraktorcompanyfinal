"""
Context menu for bounding box items
Allows quick actions: change class, re-run OCR, delete, etc.
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ui.workspace_widget import WorkspaceWidget


class BBoxContextMenu:
    """Context menu handler for bounding box items"""

    # Common YOLO classes for rail infrastructure
    COMMON_CLASSES = [
        'coordinate',
        'signal',
        'gks_gesteuert',
        'gks_festkodiert',
        'weiche',
        'weichen_block',
        'sverbinder',
        'haltepunkt',
        'prellblock',
        'gks_nicht_gesteuert',
    ]

    def __init__(self, workspace: 'WorkspaceWidget'):
        self.workspace = workspace

    def show_context_menu(self, bbox_item, pos: QtCore.QPoint):
        """
        Show context menu for bbox item.

        Args:
            bbox_item: The graphics item (ResizableBBoxItem or ResizablePolygonBBoxItem)
            pos: Global position for menu
        """
        row_id = bbox_item.data(0)
        if row_id is None:
            return

        # Get current class
        row_mask = self.workspace.df_all['row_id'] == row_id
        if not row_mask.any():
            return

        row = self.workspace.df_all[row_mask].iloc[0]
        current_class = row.get('cls', '')
        current_text = row.get('anchor_text') or row.get('coord_text', '')
        conf = row.get('conf', 0.0)

        # Create menu
        menu = QtWidgets.QMenu(self.workspace)

        # Header with detection info
        header = menu.addAction(f" {current_class} ({conf:.0%})")
        header.setEnabled(False)
        if current_text:
            text_info = menu.addAction(f"   '{current_text}'")
            text_info.setEnabled(False)

        menu.addSeparator()

        # Quick actions
        ocr_menu = menu.addMenu(" OCR erneut ausführen")
        ocr_horizontal = ocr_menu.addAction(" Horizontal")
        ocr_horizontal.triggered.connect(
            lambda: self.workspace.on_rerun_ocr(row_id, 'horizontal')
        )
        ocr_angular = ocr_menu.addAction(" Angular")
        ocr_angular.triggered.connect(
            lambda: self.workspace.on_rerun_ocr(row_id, 'angular')
        )

        menu.addSeparator()

        # Change class submenu
        class_menu = menu.addMenu(" Klasse ändern")

        for cls in self.COMMON_CLASSES:
            if cls == current_class:
                # Show current class with checkmark
                action = class_menu.addAction(f" {cls}")
                action.setEnabled(False)
            else:
                action = class_menu.addAction(f"   {cls}")
                action.triggered.connect(
                    lambda checked, new_cls=cls: self._change_class(row_id, new_cls)
                )

        menu.addSeparator()

        # Jump to in tree
        jump_action = menu.addAction(" In Tabelle anzeigen")
        jump_action.triggered.connect(lambda: self._jump_to_tree(row_id))

        menu.addSeparator()

        # Delete
        delete_action = menu.addAction(" Erkennung löschen")
        delete_action.triggered.connect(lambda: self._delete_detection(row_id))

        # Show menu
        menu.exec_(pos)

    def _change_class(self, row_id: int, new_class: str):
        """Change the class of a detection and re-run OCR"""
        try:
            # Find row
            row_mask = self.workspace.df_all['row_id'] == row_id
            if not row_mask.any():
                return

            row_idx = self.workspace.df_all[row_mask].index[0]
            old_class = self.workspace.df_all.loc[row_idx, 'cls']

            # Ask for confirmation
            reply = QtWidgets.QMessageBox.question(
                self.workspace,
                "Klasse ändern",
                f"Klasse von '{old_class}' zu '{new_class}' ändern?\n\n"
                f"OCR wird automatisch mit der neuen Klasse ausgeführt.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if reply != QtWidgets.QMessageBox.Yes:
                return

            # Save state for undo
            self.workspace._save_edit_state(
                row_ids=[row_id],
                action=f"Class change: {old_class} → {new_class}"
            )

            # Update class in dataframe
            self.workspace.df_all.loc[row_idx, 'cls'] = new_class

            # Update in page_dfs
            page = int(self.workspace.df_all.loc[row_idx, 'page'])
            if page in self.workspace.page_dfs:
                page_mask = self.workspace.page_dfs[page]['row_id'] == row_id
                if page_mask.any():
                    page_idx = self.workspace.page_dfs[page][page_mask].index[0]
                    self.workspace.page_dfs[page].loc[page_idx, 'cls'] = new_class

            # Update tree widget
            item = self.workspace.row_id_to_tree_item.get(row_id)
            if item:
                # Update tree item appearance based on new class
                self.workspace.tree.blockSignals(True)
                # The tree structure might need to change based on class
                # For now, just update the display
                self.workspace.tree.blockSignals(False)

            # Re-run OCR with new class
            print(f" Class changed: {old_class} → {new_class}, running OCR...")
            self.workspace.on_rerun_ocr(row_id, 'horizontal')

            # Refresh graphics
            self.workspace._rebuild_row_specs_for_current_page()
            self.workspace.on_page_changed(self.workspace.current_page)

            self.workspace._set_status(f" Klasse geändert: {old_class} → {new_class}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self.workspace,
                "Fehler",
                f"Fehler beim Ändern der Klasse:\n{str(e)}"
            )

    def _jump_to_tree(self, row_id: int):
        """Jump to detection in tree widget"""
        item = self.workspace.row_id_to_tree_item.get(row_id)
        if item:
            self.workspace.tree.setCurrentItem(item)
            self.workspace.tree.scrollToItem(item)
            self.workspace._set_status(f" Zu Row {row_id} gesprungen")

    def _delete_detection(self, row_id: int):
        """Delete a detection"""
        try:
            # Find row
            row_mask = self.workspace.df_all['row_id'] == row_id
            if not row_mask.any():
                return

            row = self.workspace.df_all[row_mask].iloc[0]
            cls = row.get('cls', '')
            text = row.get('anchor_text') or row.get('coord_text', '')

            # Ask for confirmation
            display_text = f" '{text}'" if text else ""
            reply = QtWidgets.QMessageBox.question(
                self.workspace,
                "Erkennung löschen",
                f"Erkennung wirklich löschen?\n\n"
                f"Klasse: {cls}{display_text}\n"
                f"Row ID: {row_id}",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if reply != QtWidgets.QMessageBox.Yes:
                return

            # Find tree item
            item = self.workspace.row_id_to_tree_item.get(row_id)
            if item:
                # Select the item so the delete function works
                self.workspace.tree.setCurrentItem(item)

                # Call the existing delete function
                self.workspace.on_delete_selected_table_rows()

                self.workspace._set_status(f" Erkennung gelöscht: {cls}{display_text}")
            else:
                QtWidgets.QMessageBox.warning(
                    self.workspace,
                    "Fehler",
                    "Erkennung nicht in Tabelle gefunden."
                )

        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self.workspace,
                "Fehler",
                f"Fehler beim Löschen:\n{str(e)}"
            )
