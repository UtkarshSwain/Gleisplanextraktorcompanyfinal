"""
Context menu for bounding box items
Allows quick actions: change class, re-run OCR, delete, etc.
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING, Optional
import pandas as pd

if TYPE_CHECKING:
    from ui.workspace_widget import WorkspaceWidget


class BBoxContextMenu:
    """Context menu handler for bounding box items"""

    # All YOLO classes for rail infrastructure (matching model training)
    COMMON_CLASSES = [
        'signal',
        'gm_block',
        'gks_festkodiert',
        'gks_gesteuert',
        'weichen_block',
        'isolierstoß',
        'haltepunkt',
        'sverbinder',
        'coordinate',
        'prellbock',
        'haltetafel',
        'weichenende',
        'weichengruppenende',
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
        # Try to get row_id from the item's attribute first, fallback to data(0)
        row_id = getattr(bbox_item, 'row_id', None) or bbox_item.data(0)
        if row_id is None:
            print(f"Warning: No row_id found for bbox_item {bbox_item}")
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
        """
        Change the class of a detection and re-run OCR.

        This method:
        1. Updates the class in df_all and page_dfs
        2. Re-runs OCR with new class parameters and saves result to dataframe
        3. Refreshes tree and overlay (tree is rebuilt from updated dataframe)
        """
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
                f"OCR wird automatisch mit der neuen Klasse ausgeführt.\n"
                f"Die Überlagerung und Tabelle werden aktualisiert.",
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
            print(f" Updated cls in df_all: {old_class} → {new_class}")

            # Update in page_dfs
            page = int(self.workspace.df_all.loc[row_idx, 'page'])
            if page in self.workspace.page_dfs:
                page_mask = self.workspace.page_dfs[page]['row_id'] == row_id
                if page_mask.any():
                    page_idx = self.workspace.page_dfs[page][page_mask].index[0]
                    self.workspace.page_dfs[page].loc[page_idx, 'cls'] = new_class
                    print(f" Updated cls in page_dfs[{page}]")

            # Re-run OCR with new class parameters and SAVE to dataframe
            print(f" Running OCR with new class '{new_class}'...")
            self._rerun_ocr_and_save(row_id, row_idx, new_class, page)

            # Refresh graphics - rebuild overlay with new class styling
            # Note: on_page_changed also calls _populate_tree which rebuilds the tree
            # from page_dfs (which now has the updated class)
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

    def _rerun_ocr_and_save(self, row_id: int, row_idx, new_class: str, page: int):
        """
        Re-run OCR with new class parameters and save result to dataframe.

        Unlike workspace.on_rerun_ocr which only updates tree display,
        this method also persists the OCR result to df_all and page_dfs.
        """
        from core.ocr_engine import (
            ocr_coordinate_horizontal, ocr_signal_name,
            ocr_numeric_cardinal_box, ocr_generic_name, NUMERIC_OK
        )

        try:
            if self.workspace.current_page_bgr_array is None:
                print(" No BGR array available, skipping OCR")
                return

            row = self.workspace.df_all.loc[row_idx]
            det = self.workspace._reconstruct_det_from_row(row)

            # Override class in det with new class
            det['cls'] = new_class
            det['name'] = new_class

            new_text = ""
            is_coord = False

            if new_class == "coordinate":
                is_coord = True
                new_text = ocr_coordinate_horizontal(det, self.workspace.current_page_bgr_array, "paddleocr", debug_class="coordinate")
            elif new_class == "signal":
                new_text = ocr_signal_name(det, self.workspace.current_page_bgr_array, "paddleocr", debug_class="signal")
            elif new_class in {"gks_gesteuert", "gks_festkodiert"}:
                new_text = ocr_numeric_cardinal_box(det, self.workspace.current_page_bgr_array, debug_class=new_class)
            else:
                # Use larger padding for high-DPI profiles (Antwerp 800 DPI needs ~16, Wien 500 DPI uses 8)
                ocr_pad = 8  # Default for Wien (500 DPI)
                layout_config = self.workspace._get_layout_config()
                if layout_config and hasattr(layout_config, 'rendering') and layout_config.rendering:
                    dpi = getattr(layout_config.rendering, 'dpi', 500)
                    if dpi >= 700:  # High-DPI profile (like Antwerp 800 DPI)
                        ocr_pad = 16
                new_text = ocr_generic_name(det, self.workspace.current_page_bgr_array, "paddleocr",
                                           allow_numeric=(new_class in NUMERIC_OK), cls_name=new_class, debug_class=new_class, pad=ocr_pad)

            print(f" OCR result for {new_class}: '{new_text}'")

            # Determine which column to update
            if is_coord:
                col_to_update = 'coord_text'
            else:
                col_to_update = 'anchor_text'

            # Update dataframe
            self.workspace.df_all.loc[row_idx, col_to_update] = new_text

            # Update page_dfs
            if page in self.workspace.page_dfs:
                page_mask = self.workspace.page_dfs[page]['row_id'] == row_id
                if page_mask.any():
                    page_idx = self.workspace.page_dfs[page][page_mask].index[0]
                    self.workspace.page_dfs[page].loc[page_idx, col_to_update] = new_text

            print(f" Saved OCR result to dataframe: {col_to_update}='{new_text}'")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f" OCR failed: {e}")

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
