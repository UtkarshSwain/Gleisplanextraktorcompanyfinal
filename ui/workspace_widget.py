from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Dict, Tuple, Optional, Any
import pandas as pd 
from ui.themes import LIGHT_QSS, DARK_QSS
from core.linking import parse_coord
import os 
import numpy as np
from validation_dialog2 import EnhancedValidationResultsDialog, ValidationIssue
from data_validator2 import EnhancedDataValidator
from core.pipelineworker import NO_OCR_CLASSES
import math 
import re
from core.ocr_engine import manual_angular_ocr, ocr_coordinate_horizontal, ocr_coordinate_angular, ocr_signal_name
import cv2
from ui.graphics_view import InteractiveGraphicsView
from core.ocr_engine import paddleocr_recognize, ocr_numeric_cardinal_box, ocr_numeric_tilted_box, ocr_generic_name, NUMERIC_OK
from config import ZOOM_SIZE
from utils.helpers import _is_deleted
from core.image_processing import qpolygonf_from_pts
from PIL import Image, ImageFile
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.auditing_window import AuditingWindow

# ============================================================================
# WORKSPACE WIDGET - Single PDF workspace
# ============================================================================ 
class WorkspaceWidget(QtWidgets.QWidget):

    """Single PDF workspace - contains all UI for one document"""

    def __init__(self, parent_auditing: 'AuditingWindow', layout_name: str):
        from ui.dialogs import TreeWindow, GraphicsWindow
        super().__init__()
        self.parent_auditing = parent_auditing
        self.layout_name = layout_name
        self.tree_window: Optional[TreeWindow] = None
        # Copy ALL instance variables from original AuditingWindow
        self.df_all = pd.DataFrame()
        self.all_page_row_specs: Dict[int, Dict[int, Dict[str, object]]] = {}
        self.current_row_items: Dict[int, List[QtWidgets.QGraphicsItem]] = {}
        self.row_id_to_tree_item: Dict[int, QtWidgets.QTreeWidgetItem] = {}
        self.current_page = 1
        self._class_confidence_thresholds: Dict[str, float] = {'__all__': 0.0}
        self._active_class_for_threshold_setting: str = '__all__'
        self.page_base_pix: Dict[int, QtGui.QPixmap] = {}
        self.page_dfs: Dict[int, pd.DataFrame] = {}
        self._last_hovered_row_id: Optional[int] = None
        self._is_selecting_from_scene = False
        self.page_bgr_arrays: Dict[int, np.ndarray] = {}
        self.current_page_bgr_array: Optional[np.ndarray] = None
        self.is_drawing_mode = False
        self.draw_ocr_target_item: Optional[QtWidgets.QTreeWidgetItem] = None
        self.draw_ocr_target_column: Optional[int] = None
        self.draw_ocr_mode: str = 'horizontal'
        self.is_manual_linking_mode = False
        self.link_source_row_id = None
        self.link_drag_line = None
        
        # Undo/Redo stacks
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        self.max_undo_steps = 50
        self.graphics_window: Optional[GraphicsWindow] = None
        self.is_manual_linking_mode = False
        self.link_source_row_id = None
        self.link_drag_line = None
        
        # Undo/Redo stacks
        self.undo_stack: List[Dict] = []
        self.redo_stack: List[Dict] = []
        self.max_undo_steps = 50
        self._is_undoing_or_redoing = False
        self._is_loading_data = False 

        self.graphics_window: Optional[GraphicsWindow] = None
        
        # Placeholder widgets
        self.tree_placeholder: Optional[QtWidgets.QWidget] = None
        self.graphics_placeholder: Optional[QtWidgets.QWidget] = None

        # Track overlay
        self.track_skeleton = None
        self.track_overlay_items = []
        
        self._build_ui()

    def _set_status(self, message: str):
        """Safely update status bar"""
        try:
            if self.parent_auditing and hasattr(self.parent_auditing, 'statusBar'):
                self.parent_auditing.statusBar().showMessage(message)
            else:
                print(f"[STATUS] {message}")
        except Exception as e:
            print(f"[STATUS ERROR] {message} ({e})")

    def _build_ui(self):
        from ui.tree_widget import AuditingTreeWidget

        """Build the workspace UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Top controls
        top_layout = QtWidgets.QHBoxLayout()
        # ADD UNDO/REDO BUTTONS
        self.btn_undo = QtWidgets.QPushButton("↶ Rückgängig")
        self.btn_undo.setToolTip("Letzte Aktion rückgängig machen (Strg+Z)")
        self.btn_undo.clicked.connect(self.undo)
        top_layout.addWidget(self.btn_undo)
        
        self.btn_redo = QtWidgets.QPushButton("↷ Wiederholen")
        self.btn_redo.setToolTip("Rückgängig gemachte Aktion wiederholen (Strg+Y)")
        self.btn_redo.clicked.connect(self.redo)
        top_layout.addWidget(self.btn_redo)
        
        top_layout.addWidget(QtWidgets.QLabel("|"))  # Separator
        # Page controls
        top_layout.addWidget(QtWidgets.QLabel("Seite:"))
        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self.on_page_changed)
        top_layout.addWidget(self.page_spin)
        top_layout.addStretch(1)
        
        # Layout name label
        short_name = os.path.basename(self.layout_name)
        self.layout_label = QtWidgets.QLabel(f"📄 {short_name}")
        self.layout_label.setStyleSheet("font-weight: bold; color: #0078d7;")
        top_layout.addWidget(self.layout_label)
        
        layout.addLayout(top_layout)
        
        # Confidence controls
        conf = QtWidgets.QHBoxLayout()
        conf.addWidget(QtWidgets.QLabel("Klasse auswählen:"))
        self.class_selector_combo = QtWidgets.QComboBox()

        # --- ADD THIS LINE ---
        self.class_selector_combo.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        self.class_selector_combo.currentTextChanged.connect(self.on_class_selector_changed)
        conf.addWidget(self.class_selector_combo)
        conf.addStretch(1)

        # Validation button
        self.btn_validate = QtWidgets.QPushButton("✓ Daten validieren")
        self.btn_validate.setToolTip("Führt umfassende Datenvalidierung durch")
        self.btn_validate.clicked.connect(self.run_validation)
        conf.addWidget(self.btn_validate)
        # Manual linking button
        self.btn_manual_link = QtWidgets.QPushButton("📌 Koordinate manuell verknüpfen")
        self.btn_manual_link.setCheckable(True)
        self.btn_manual_link.setToolTip("Klicken Sie auf ein Ankerelement, dann auf eine Koordinate")
        self.btn_manual_link.toggled.connect(self.on_manual_link_toggled)
        conf.addWidget(self.btn_manual_link)
        
        # Manual OCR buttons
        self.btn_manual_ocr = QtWidgets.QPushButton("Manuelles OCR (Horizontal)")
        self.btn_manual_ocr.setCheckable(True)
        self.btn_manual_ocr.toggled.connect(lambda checked: self.on_manual_ocr_toggled(checked, 'horizontal'))
        conf.addWidget(self.btn_manual_ocr)
        
        self.btn_manual_ocr_angular = QtWidgets.QPushButton("Manuelles OCR (Angular)")
        self.btn_manual_ocr_angular.setCheckable(True)
        self.btn_manual_ocr_angular.toggled.connect(lambda checked: self.on_manual_ocr_toggled(checked, 'angular'))
        conf.addWidget(self.btn_manual_ocr_angular)
        
        # Track overlay toggle button
        self.btn_toggle_tracks = QtWidgets.QPushButton("🛤️ Gleise anzeigen")
        self.btn_toggle_tracks.setCheckable(True)
        self.btn_toggle_tracks.setEnabled(False)
        self.btn_toggle_tracks.setToolTip("Zeigt die erkannten Hauptgleise als rote Linie")
        self.btn_toggle_tracks.toggled.connect(self.on_toggle_track_overlay)
        conf.addWidget(self.btn_toggle_tracks)
        
        layout.addLayout(conf)
        
        # Graphics view
        self.view = InteractiveGraphicsView(self)
        self.scene = QtWidgets.QGraphicsScene()
        self.view.setScene(self.scene)
        
        # Item details
        self.item_details_notes = QtWidgets.QPlainTextEdit()
        self.item_details_notes.setPlaceholderText("Details zum ausgewählten Element / Notizen...")
        self.item_details_notes.setMaximumHeight(150) 
        self.item_details_notes.textChanged.connect(self.on_item_notes_changed)
        
        # Filter inputs
        self.filter_class_input = QtWidgets.QLineEdit()
        self.filter_class_input.setPlaceholderText("Filter Klasse (Regex)")
        self.filter_text_input = QtWidgets.QLineEdit()
        self.filter_text_input.setPlaceholderText("Filter Text (Regex)")
        table_filter = QtWidgets.QHBoxLayout()
        table_filter.addWidget(self.filter_class_input)
        table_filter.addWidget(self.filter_text_input)
        
        # Tree widget
        self.tree = AuditingTreeWidget(self)
        self.tree.setHeaderLabels(["Text/Nummer", "Koordinatentext", "Fahrtrichtung", "Seite"])
        self.tree.setSortingEnabled(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        self.tree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
        self.tree.header().resizeSection(0, 200)
        self.tree.header().resizeSection(1, 150)
        self.tree.header().resizeSection(2, 100)
        self.tree.header().resizeSection(3, 80)
        self.tree.header().setStretchLastSection(True)
        self.tree.setMouseTracking(True)
        self.tree.itemEntered.connect(self.on_tree_item_hovered)
        self.tree.viewport().installEventFilter(self)
        # Setup keyboard shortcuts for table editing
        self._setup_table_shortcuts()
        # Splitter layout
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        self.graphics_original_layout = left_layout 
        left_layout.addWidget(self.view)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.addWidget(QtWidgets.QLabel("Item Details / Notes:"))
        right_layout.addWidget(self.item_details_notes)
        right_layout.addLayout(table_filter)
        self.tree_original_layout = right_layout
        right_layout.addWidget(self.tree)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([800, 500])
        
        layout.addWidget(splitter)
        
        # Connect signals
        self.filter_class_input.textChanged.connect(self._apply_all_filters)
        self.filter_text_input.textChanged.connect(self._apply_all_filters)
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        self.view.rect_drawn.connect(self.on_rect_drawn)
        self.view.rotated_rect_drawn.connect(self.on_rotated_rect_drawn)
        self.scene.selectionChanged.connect(self.on_scene_selection)
        self._setup_undo_redo_shortcuts()

    def _setup_table_shortcuts(self):
        """Setup keyboard shortcuts for table editing"""
        # Copy
        copy_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+C"), self.tree)
        copy_shortcut.activated.connect(self.tree.copy_selection)
        
        # Paste
        paste_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+V"), self.tree)
        paste_shortcut.activated.connect(self.tree.paste_from_clipboard)
        
        # Find
        find_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+F"), self.tree)
        find_shortcut.activated.connect(self.tree.find_replace)

    def on_pop_out_tree(self):
        from ui.dialogs import TreeWindow
        """Pop out the tree widget into its own window."""
        if self.tree_window is not None:
            return
        # CREATE PLACEHOLDER before removing tree
        self.tree_placeholder = QtWidgets.QWidget()
        self.tree_placeholder.setMinimumHeight(self.tree.height())

        # Get the tree's current index in the layout
        tree_index = self.tree_original_layout.indexOf(self.tree)
        
        # Replace tree with placeholder
        self.tree_original_layout.removeWidget(self.tree)
        self.tree_original_layout.insertWidget(tree_index, self.tree_placeholder)

        # Create the new window. The TreeWindow constructor will reparent self.tree
        self.tree_window = TreeWindow(self, self.tree)
        
        # Apply the current theme to the new window
        if self.parent_auditing.main_app_ref._current_theme == "dark":
            self.tree_window.setStyleSheet(DARK_QSS)
        else:
            self.tree_window.setStyleSheet(LIGHT_QSS)
            
        self.tree_window.show()

    def on_pop_out_graphics(self):
        from ui.dialogs import GraphicsWindow
        """Pop out the graphics view into its own window."""
        if self.graphics_window is not None:
            return
        
        # ✅ CREATE PLACEHOLDER before removing view
        self.graphics_placeholder = QtWidgets.QWidget()
        self.graphics_placeholder.setMinimumSize(self.view.size())
        
        # Get the view's current index in the layout
        view_index = self.graphics_original_layout.indexOf(self.view)
        
        # Replace view with placeholder
        self.graphics_original_layout.removeWidget(self.view)
        self.graphics_original_layout.insertWidget(view_index, self.graphics_placeholder)
        
        # Create the new window (this will reparent self.view)
        self.graphics_window = GraphicsWindow(self, self.view)
        
        # Apply theme
        if self.parent_auditing.main_app_ref._current_theme == "dark":
            self.graphics_window.setStyleSheet(DARK_QSS)
        else:
            self.graphics_window.setStyleSheet(LIGHT_QSS)
        
        self.graphics_window.show()

    def on_redock_graphics(self):
        """Redock the graphics view back into the main view."""
        if self.graphics_window is None:
            return
        
        # Closing the window will trigger the _on_graphics_window_closed callback
        self.graphics_window.close()

    def _on_graphics_window_closed(self):
        """Callback when the popped-out graphics window is closed."""
        if self.graphics_window is None:
            return
        
        # ✅ REPLACE PLACEHOLDER with view
        if self.graphics_placeholder:
            placeholder_index = self.graphics_original_layout.indexOf(self.graphics_placeholder)
            
            # Remove placeholder
            self.graphics_original_layout.removeWidget(self.graphics_placeholder)
            self.graphics_placeholder.deleteLater()
            self.graphics_placeholder = None
            
            # Re-insert view at same position
            self.view.setParent(None)
            self.graphics_original_layout.insertWidget(placeholder_index, self.view)
        else:
            # Fallback: just add at end
            self.view.setParent(None)
            self.graphics_original_layout.addWidget(self.view)
        
        self.graphics_window = None

    def on_redock_tree(self):
        """Redock the tree widget back into the main view."""
        if self.tree_window is None:
            return
        
        # Closing the window will trigger the _on_tree_window_closed callback
        self.tree_window.close()

    def _on_tree_window_closed(self):
        """Callback when the popped-out tree window is closed."""
        if self.tree_window is None:
            return
        
        # ✅ REPLACE PLACEHOLDER with tree
        if self.tree_placeholder:
            placeholder_index = self.tree_original_layout.indexOf(self.tree_placeholder)
            
            # Remove placeholder
            self.tree_original_layout.removeWidget(self.tree_placeholder)
            self.tree_placeholder.deleteLater()
            self.tree_placeholder = None
            
            # Re-insert tree at same position
            self.tree.setParent(None)
            self.tree_original_layout.insertWidget(placeholder_index, self.tree)
        else:
            # Fallback: just add at end
            self.tree.setParent(None)
            self.tree_original_layout.addWidget(self.tree)
        
        # Reconnect signals
        self.tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.tree_window = None

    def on_delete_selected_table_rows(self):
        """
        Deletes the currently selected rows from the tree and dataframes.
        (This is the fix for the 'Delete' action)
        """
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Zeilen löschen",
            f"Möchten Sie die {len(selected_items)} ausgewählten Zeilen wirklich löschen?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return
            
        self.tree.blockSignals(True)
        
        row_ids_to_delete = []
        items_to_remove = []

        for item in selected_items:
            # Collect child items if a parent is selected
            if item.childCount() > 0:
                for i in range(item.childCount()):
                    child = item.child(i)
                    row_id = child.data(0, QtCore.Qt.UserRole)
                    if row_id is not None:
                        row_ids_to_delete.append(row_id)
                        items_to_remove.append(child)
            else:
                # Collect single child item
                row_id = item.data(0, QtCore.Qt.UserRole)
                if row_id is not None:
                    row_ids_to_delete.append(row_id)
                    items_to_remove.append(item)

        if not row_ids_to_delete:
            self.tree.blockSignals(False)
            return
        self._save_state(f"{len(row_ids_to_delete)} Zeilen gelöscht", row_ids_to_delete)

        try:
            # 1. Remove from DataFrames
            if self.df_all is not None and not self.df_all.empty:
                self.df_all.drop(
                    self.df_all[self.df_all['row_id'].isin(row_ids_to_delete)].index, 
                    inplace=True
                )
            
            df_page = self.page_dfs.get(self.current_page)
            if df_page is not None and not df_page.empty:
                df_page.drop(
                    df_page[df_page['row_id'].isin(row_ids_to_delete)].index, 
                    inplace=True
                )
            
            # 2. Remove from helper dictionaries and scene
            for row_id in row_ids_to_delete:
                if row_id in self.row_id_to_tree_item:
                    del self.row_id_to_tree_item[row_id]
                
                graphics_items = self.current_row_items.pop(row_id, [])
                for g_item in graphics_items:
                    if g_item and g_item.scene():
                        self.scene.removeItem(g_item)

            # 3. Remove from Tree widget
            for item in items_to_remove:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
            
            # Use the parent's status bar
            self._set_status(f"{len(row_ids_to_delete)} Zeilen gelöscht.")
            self.tree._update_row_count()
            self.tree._update_selection_count()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler beim Löschen", str(e))
        finally:
            self.tree.blockSignals(False)
            self.item_details_notes.clear()
            
    def load_data(self, df_all: pd.DataFrame, page_base_pix: Dict, 
                page_dfs: Dict, page_bgr_arrays: Dict, track_skeleton: Optional[np.ndarray] = None):
        """Load data into workspace - with database check"""
        
        # ✅ SET FLAG TO PREVENT STATE SAVING DURING LOAD
        self._is_loading_data = True
        
        try:
            incoming_track_skeleton = track_skeleton

            # Check if there's saved data in database
            from database3 import get_workspace_data
            saved_result = get_workspace_data(self.layout_name)
            
            if saved_result:
                saved_data, saved_track_skeleton = saved_result
                
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Gespeicherte Daten gefunden",
                    f"Es gibt gespeicherte Daten für '{os.path.basename(self.layout_name)}'.\n\n"
                    "Möchten Sie die gespeicherten Daten laden statt der neuen Verarbeitung?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                
                if reply == QtWidgets.QMessageBox.Yes:
                    # Load from database
                    df_all = pd.DataFrame(saved_data)
                    
                    # Use saved track skeleton instead of new one
                    track_skeleton = saved_track_skeleton
                    
                    # Rebuild page_dfs from df_all
                    page_dfs = {}
                    for page_num in df_all['page'].unique():
                        page_dfs[int(page_num)] = df_all[df_all['page'] == page_num].copy()
            
            # ✅ CLEAR UNDO/REDO STACKS ON NEW LOAD
            self.undo_stack.clear()
            self.redo_stack.clear()
            
            # Load data into workspace
            self.df_all = df_all
            self.page_base_pix = page_base_pix
            self.page_dfs = page_dfs
            self.page_bgr_arrays = page_bgr_arrays
            
            # Fill class selector
            self.class_selector_combo.clear()
            self.class_selector_combo.addItem("Alle Klassen")
            all_classes = sorted(self.df_all['cls'].unique().tolist())
            for cls in all_classes:
                self.class_selector_combo.addItem(cls)
                self._class_confidence_thresholds.setdefault(cls, 0.0)
            self._class_confidence_thresholds.setdefault('__all__', 0.0)
            self.class_selector_combo.setCurrentText("Alle Klassen")
            self.on_class_selector_changed("Alle Klassen")
            
            # Build row specs per page
            self.all_page_row_specs.clear()
            for pidx, df_page in self.page_dfs.items():
                specs = {}
                for _, row in df_page.iterrows():
                    label = f"{row['cls']} {row.get('conf','')}"
                    if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                        label += f" | {row['anchor_text']}"
                    if pd.notna(row.get('coord_text')) and row['coord_text']:
                        label += f" | {row['coord_text']}"
                    if 'angle' in df_page.columns and pd.notna(row.get('angle')):
                        try:
                            label += f" θ={float(row['angle']):.1f}°"
                        except Exception:
                            pass
                    
                    spec = {"label": label, "is_poly": False}
                    poly = row.get("poly", None)
                    
                    if isinstance(poly, (list, tuple)) and len(poly) == 4:
                        try:
                            pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                            spec.update({"is_poly": True, "pts": pts})
                            specs[int(row['row_id'])] = spec
                            continue
                        except Exception:
                            pass
                    
                    if row['cls'] == 'coordinate':
                        x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
                    else:
                        x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']
                    
                    if pd.isna(x1) or x1 is None:
                        continue
                    
                    w = int(x2 - x1)
                    h = int(y2 - y1)
                    spec.update({"rect": (int(x1), int(y1), w, h)})
                    specs[int(row['row_id'])] = spec
                
                self.all_page_row_specs[pidx] = specs
            
            max_page = max(self.page_dfs.keys()) if self.page_dfs else 1
            self.page_spin.setMaximum(max_page)
            self.page_spin.setValue(1)
            
            # Store track skeleton
            self.track_skeleton = track_skeleton
            if track_skeleton is not None:
                self.btn_toggle_tracks.setEnabled(True)
                self._set_status(f"✓ Track detection verfügbar: {self.layout_name}")
            
            self.on_page_changed(1)
            
            # ✅ UPDATE UNDO/REDO BUTTON STATES
            if hasattr(self, '_update_undo_redo_buttons'):
                self._update_undo_redo_buttons()
        
        finally:
            # ✅ ALWAYS CLEAR FLAG AFTER LOADING
            self._is_loading_data = False

    def on_toggle_track_overlay(self, checked: bool):
        """Toggle track centerline overlay (7px thick FLASHY RED line)"""
        # Clear existing overlay
        for item in self.track_overlay_items:
            if item and item.scene():
                self.scene.removeItem(item)
        self.track_overlay_items.clear()
        
        if not checked or self.track_skeleton is None:
            self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
            return
        
        try:
            h, w = self.track_skeleton.shape
            
            # Thicken skeleton to 7px
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            thick_skel = cv2.dilate(self.track_skeleton, kernel, iterations=1)
            
            # Create FLASHY RED overlay with full opacity
            overlay = np.zeros((h, w, 4), dtype=np.uint8)
            overlay[thick_skel > 0] = (255, 0, 0, 255)  # BRIGHT RED, fully opaque
            
            # Convert to QPixmap
            qimg = QtGui.QImage(overlay.data, w, h, w * 4, QtGui.QImage.Format_RGBA8888).copy()
            overlay_pix = QtGui.QPixmap.fromImage(qimg)
            
            # Add to scene above everything else
            overlay_item = self.scene.addPixmap(overlay_pix)
            overlay_item.setZValue(1000)  # Above all other items
            overlay_item.setOpacity(1.0)  # FULL OPACITY - NO TRANSPARENCY
            self.track_overlay_items.append(overlay_item)
            
            self._set_status("🛤️ Gleise sichtbar (7px FLASHY ROT)")
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Overlay-Fehler", f"Konnte Gleis-Overlay nicht erstellen:\n{e}")
            self.btn_toggle_tracks.setChecked(False)
        
    
    def save_to_db(self):
        """Save this workspace to database (including track skeleton)"""
        if self.df_all is None or self.df_all.empty:
            return
        
        try:
            df_cleaned = self.df_all.replace({np.nan: None, pd.NaT: None})
            data_list = df_cleaned.to_dict("records")
            
            from database3 import save_workspace_data
            save_workspace_data(self.layout_name, data_list, self.track_skeleton)
            
            print(f"✅ Saved {self.layout_name} (with track skeleton: {self.track_skeleton is not None})")
            
        except Exception as e:
            print(f"❌ Save failed: {e}")
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))
    
    def _get_theme_colors(self):
        """Get theme colors from parent"""
        return self.parent_auditing.main_app_ref._get_theme_colors()
    
    def _update_graphics_theme(self):
        """Update graphics theme"""
        if self.scene is None:
            return
        
        # --- ADD THIS BLOCK ---
        # Repopulate the tree to update item-level styles
        # (like the dark category backgrounds)
        if self.current_page in self.page_dfs:
            self.tree.clearSelection() # Clear selection before rebuilding
            self.item_details_notes.clear()
            self._populate_tree(self.current_page)
        # --- END ADD ---
        _, _, _, _, bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(bg))
        if self.current_page in self.page_base_pix:
            for it in list(self.scene.items()):
                if not isinstance(it, QtWidgets.QGraphicsPixmapItem):
                    self.scene.removeItem(it)
            self.current_row_items.clear()
            self._create_items_for_page(self.current_page)
    
    def eventFilter(self, source: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if source == self.tree.viewport() and event.type() == QtCore.QEvent.Leave:
            self.on_table_leave()
        return super().eventFilter(source, event)
    
    def on_page_changed(self, pidx: int):
        """Handle page change"""
        if pidx not in self.page_base_pix:
            return
        self.current_page = pidx
        self.current_page_bgr_array = self.page_bgr_arrays.get(pidx, None)
        
        # Repopulate tree
        self._populate_tree(pidx)
        
        # Rebuild graphics
        self.scene.clear()
        _, _, _, _, bg = self._get_theme_colors()
        self.scene.setBackgroundBrush(QtGui.QBrush(bg))
        self.scene.addPixmap(self.page_base_pix[pidx])
        self.scene.setSceneRect(QtCore.QRectF(self.page_base_pix[pidx].rect()))
        self._create_items_for_page(pidx)
    
    def _populate_tree(self, pidx: int):
        """Populate tree widget for given page"""
        self.tree.clear()
        self.row_id_to_tree_item.clear()
        
        df_page = self.page_dfs.get(pidx)
        if df_page is None:
            return
        
        # Get and sort class list
        classes = sorted(df_page['cls'].unique())
        if 'coordinate' in classes:
            classes.remove('coordinate')
            classes.append('coordinate')
        
        for cls_name in classes:
            parent_item = QtWidgets.QTreeWidgetItem(self.tree)
            parent_item.setText(0, cls_name)
            parent_item.setExpanded(True)
            
            # Style parent
            font = parent_item.font(0)
            font.setBold(True)
            parent_item.setFont(0, font)
            parent_item.setFlags(parent_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            bg_brush = self.palette().window().color().lighter(115)
            for col in range(4):
                parent_item.setBackground(col, bg_brush)
            
            df_class = df_page[df_page['cls'] == cls_name]
            item_counter = 1
            is_no_ocr_class = cls_name in NO_OCR_CLASSES
            
            for _, row in df_class.iterrows():
                row_id = int(row['row_id'])
                
                # Determine primary and secondary text
                if cls_name == 'coordinate':
                    primary_text = str(row.get('coord_text', ''))
                    secondary_text = ""
                    fahrtrichtung_text = ""
                elif is_no_ocr_class:
                    # --- FIX START ---
                    # Check if anchor_text was already populated by the pipeline 
                    # (e.g., for haltepunkt or weichenende)
                    existing_anchor_text = row.get('anchor_text', '')
                    
                    if existing_anchor_text:
                        # Use the pre-formatted text from the pipeline
                        primary_text = str(existing_anchor_text)
                    else:
                        # Fallback for other NO_OCR_CLASSES (like isolierstoß)
                        primary_text = f"{cls_name} {item_counter}"
                        item_counter += 1 # Only increment if we use the counter
                    
                    secondary_text = str(row.get('coord_text', ''))
                    fahrtrichtung_text = ""
                    # --- FIX END ---
                else:
                    primary_text = str(row.get('anchor_text', ''))
                    secondary_text = str(row.get('coord_text', ''))
                    
                    if cls_name == "signal" and pd.notna(row.get('fahrtrichtung')):
                        fahrtrichtung_text = str(row['fahrtrichtung'])
                    else:
                        fahrtrichtung_text = ""
                
                page_str = str(row.get('page', ''))
                child_item = QtWidgets.QTreeWidgetItem(parent_item)
                child_item.setText(0, primary_text)
                child_item.setText(1, secondary_text)
                child_item.setText(2, fahrtrichtung_text)
                child_item.setText(3, page_str)
                
                child_item.setFlags(child_item.flags() | QtCore.Qt.ItemIsEditable)
                child_item.setData(0, QtCore.Qt.UserRole, row_id)
                self.row_id_to_tree_item[row_id] = child_item
        
        self._apply_all_filters()
        self.tree._update_row_count()
        self.tree._update_selection_count()


    def _apply_all_filters(self):
        """Apply all filters to tree"""
        self.tree.blockSignals(True)
        
        class_filter_re = None
        text_filter_re = None
        
        try:
            class_filter_re = re.compile(self.filter_class_input.text(), re.IGNORECASE)
        except re.error:
            pass
        
        try:
            text_filter_re = re.compile(self.filter_text_input.text(), re.IGNORECASE)
        except re.error:
            pass
        
        selected_class = self._active_class_for_threshold_setting
        show_all_classes = (selected_class == "Alle Klassen")
        
        for i in range(self.tree.topLevelItemCount()):
            parent_item = self.tree.topLevelItem(i)
            class_name = parent_item.text(0)
            
            # Class selector filter
            if not show_all_classes and class_name != selected_class:
                parent_item.setHidden(True)
                continue
            
            # Class name filter
            class_visible = True
            if class_filter_re:
                if not class_filter_re.search(class_name):
                    class_visible = False
            
            visible_child_count = 0
            for j in range(parent_item.childCount()):
                child_item = parent_item.child(j)
                row_id = child_item.data(0, QtCore.Qt.UserRole)
                
                if row_id is None:
                    child_item.setHidden(True)
                    continue
                
                row_data_list = self.df_all[self.df_all['row_id'] == row_id]
                if row_data_list.empty:
                    child_item.setHidden(True)
                    continue
                
                row = row_data_list.iloc[0]
                
                # ✅ Initialize child_visible immediately
                child_visible = True
                
                # Confidence filter
                conf = row.get('conf', 0.0)
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(class_name, 0.0)
                if conf < g or conf < c:
                    child_visible = False
                
                # Text filter
                if child_visible and text_filter_re:
                    text_col0 = child_item.text(0)
                    text_col1 = child_item.text(1)
                    text_col2 = child_item.text(2)
                    
                    if not (text_filter_re.search(text_col0) or 
                            text_filter_re.search(text_col1) or 
                            text_filter_re.search(text_col2)):
                        child_visible = False
                
                child_item.setHidden(not child_visible)
                if child_visible:
                    visible_child_count += 1
            
            parent_item.setHidden(visible_child_count == 0 or not class_visible)
        
        self.tree.blockSignals(False)
        self.clear_hover_highlight()
    
    def _create_items_for_page(self, pidx: int):
        """Create graphics items for page"""
        self.current_row_items.clear()
        
        text_brush = QtGui.QBrush(QtCore.Qt.black)
        normal, highlight, hover, _, _ = self._get_theme_colors()
        pen = QtGui.QPen(normal, 2)
        specs = self.all_page_row_specs.get(pidx, {})
        
        selected_class = self._active_class_for_threshold_setting
        show_all_classes = (selected_class == "Alle Klassen")
        
        for row_id, spec in specs.items():
            dfp = self.page_dfs.get(pidx)
            if dfp is not None:
                m = dfp[dfp['row_id'] == row_id]
                if m.empty:
                    continue
                
                conf = m['conf'].iloc[0]
                cls = m['cls'].iloc[0]
                
                if not show_all_classes and cls != selected_class:
                    continue
                
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(cls, 0.0)
                if conf < g or conf < c:
                    continue
            
            label = spec["label"]
            
            if spec.get("is_poly", False):
                pts = spec["pts"]
                poly_item = QtWidgets.QGraphicsPolygonItem(qpolygonf_from_pts(pts))
                poly_item.setPen(pen)
                poly_item.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                poly_item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                poly_item.setData(0, int(row_id))
                
                x_pos, y_pos = float(pts[:, 0].min()), float(pts[:, 1].min())
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x_pos, y_pos - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                self.scene.addItem(poly_item)
                self.scene.addItem(ti)
                self.current_row_items[int(row_id)] = [poly_item, ti]
            else:
                x1, y1, w, h = spec["rect"]
                rect = QtWidgets.QGraphicsRectItem(x1, y1, w, h)
                rect.setPen(pen)
                rect.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
                rect.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
                rect.setData(0, int(row_id))
                
                ti = QtWidgets.QGraphicsSimpleTextItem(label)
                ti.setBrush(text_brush)
                ti.setPos(x1, y1 - 20)
                ti.setData(0, int(row_id))
                ti.setAcceptedMouseButtons(QtCore.Qt.NoButton)
                ti.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                self.scene.addItem(rect)
                self.scene.addItem(ti)
                self.current_row_items[int(row_id)] = [rect, ti]
    
    def highlight_row_graphics(self, row_id: int, highlight: bool = True, hover: bool = False):
        """Highlight graphics for row"""
        items = self.current_row_items.get(row_id)
        if not items:
            return
        normal, hi, hov, _, _ = self._get_theme_colors()
        color = hov if hover else (hi if highlight else normal)
        pen = QtGui.QPen(color, 3 if (highlight or hover) else 2)
        for it in list(items):
            try:
                if isinstance(it, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem)):
                    it.setPen(pen)
            except RuntimeError:
                try:
                    items.remove(it)
                except Exception:
                    pass
    
    def zoom_to_row(self, row_id: int):
        """Zoom to row in graphics"""
        if row_id not in self.current_row_items:
            return
        item = next((i for i in self.current_row_items[row_id] 
                    if isinstance(i, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem))), None)
        if not item:
            return
        srect = item.sceneBoundingRect()
        c = srect.center()
        zr = QtCore.QRectF(c.x() - ZOOM_SIZE/2, c.y() - ZOOM_SIZE/2, ZOOM_SIZE, ZOOM_SIZE).intersected(self.scene.sceneRect())
        self.view.setTransform(QtGui.QTransform())
        self.view.fitInView(zr, QtCore.Qt.KeepAspectRatioByExpanding)
        self.view.centerOn(c)
    
    def on_tree_selection_changed(self):
        """Handle tree selection change"""
        if self._is_selecting_from_scene:
            return
        
        self.clear_hover_highlight()
        
        for rid in self.current_row_items.keys():
            self.highlight_row_graphics(rid, highlight=False)
        
        items = self.tree.selectedItems()
        if not items:
            self.item_details_notes.clear()
            return
        
        selected_item = items[0]
        
        if selected_item.childCount() > 0:
            self.item_details_notes.clear()
            return
        
        row_id = selected_item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            self.item_details_notes.clear()
            return
        
        self.highlight_row_graphics(row_id, True)
        self.zoom_to_row(row_id)
        
        row_data_list = self.df_all[self.df_all['row_id'] == row_id]
        if row_data_list.empty:
            return
        row = row_data_list.iloc[0]
        
        details = (
            f"Klasse: {row.get('cls','')}\n"
            f"Konfidenz: {row.get('conf','')}\n"
            f"Anker Text: {row.get('anchor_text','')}\n"
            f"Koord Text: {row.get('coord_text','')}\n"
        )
        
        if row.get('cls') == 'signal' and pd.notna(row.get('fahrtrichtung')):
            details += f"Fahrtrichtung: {row.get('fahrtrichtung','')}\n"
        
        details += f"Seite: {row.get('page','')}\n"
        details += f"--- Notizen ---\n{row.get('notes','')}"
        
        self.item_details_notes.blockSignals(True)
        self.item_details_notes.setPlainText(details)
        self.item_details_notes.blockSignals(False)
    
    def on_tree_item_hovered(self, item, column):
        """Handle tree item hover"""
        self.clear_hover_highlight()
        
        if item is None or item.childCount() > 0:
            return
        
        row_id = item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            return
        
        if not item.isSelected():
            self.highlight_row_graphics(row_id, highlight=False, hover=True)
            self._last_hovered_row_id = row_id
    
    def on_table_leave(self):
        """Handle mouse leaving table"""
        self.clear_hover_highlight()
    
    def clear_hover_highlight(self):
        """Clear hover highlight"""
        if self._last_hovered_row_id is not None:
            item = self.row_id_to_tree_item.get(self._last_hovered_row_id)
            is_sel = item.isSelected() if item else False
            
            if not is_sel:
                self.highlight_row_graphics(self._last_hovered_row_id, highlight=False)
            self._last_hovered_row_id = None
    
    def on_scene_selection(self):
        """Handle scene selection"""
        if _is_deleted(self.scene):
            return
        try:
            sel = [it for it in self.scene.selectedItems() if it is not None]
        except RuntimeError:
            return
        
        for rid in list(self.current_row_items.keys()):
            self.highlight_row_graphics(rid, False)
        
        if not sel:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.blockSignals(False)
            self.item_details_notes.clear()
            return
        
        rid = None
        for it in sel:
            try:
                data = it.data(0)
                if data is not None:
                    rid = int(data)
                    break
            except Exception:
                continue
        
        if rid is None:
            return
        
        self.highlight_row_graphics(rid, True)
        
        self._is_selecting_from_scene = True
        item = self.row_id_to_tree_item.get(rid)
        if item:
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            item.setSelected(True)
            self.tree.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
            self.tree.blockSignals(False)
        self._is_selecting_from_scene = False
        
        row_data_list = self.df_all[self.df_all['row_id'] == rid]
        if row_data_list.empty:
            return
        row = row_data_list.iloc[0]
        
        details = (
            f"Klasse: {row.get('cls','')}\n"
            f"Konfidenz: {row.get('conf','')}\n"
            f"Anker Text: {row.get('anchor_text','')}\n"
            f"Koord Text: {row.get('coord_text','')}\n"
        )
        
        if row.get('cls') == 'signal' and pd.notna(row.get('fahrtrichtung')):
            details += f"Fahrtrichtung: {row.get('fahrtrichtung','')}\n"
        
        details += f"Seite: {row.get('page','')}\n"
        details += f"--- Notizen ---\n{row.get('notes','')}"
        
        self.item_details_notes.blockSignals(True)
        self.item_details_notes.setPlainText(details)
        self.item_details_notes.blockSignals(False)
    
    def on_item_notes_changed(self):
        """Handle notes change"""
        sel = self.tree.selectedItems()
        if not sel:
            return
        
        item = sel[0]
        if item.childCount() > 0:
            return
        
        row_id = item.data(0, QtCore.Qt.UserRole)
        if row_id is None:
            return
        
        full_text = self.item_details_notes.toPlainText()
        notes_marker = "--- Notizen ---\n"
        notes_only = ""
        if notes_marker in full_text:
            try:
                notes_only = full_text.split(notes_marker, 1)[1]
            except Exception:
                pass
        
        idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
        if idx_list:
            idx = idx_list[0]
            if self.df_all.at[idx, 'notes'] != notes_only:
                self.df_all.at[idx, 'notes'] = notes_only
    
    def on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handle tree item edit"""
        self.tree.blockSignals(True)
        
        try:
            if not item or item.childCount() > 0:
                self.tree.blockSignals(False)
                return
            
            row_id = item.data(0, QtCore.Qt.UserRole)
            if row_id is None:
                self.tree.blockSignals(False)
                return
            self._save_state("Zelle bearbeitet", [row_id])

            new_text = item.text(column)
            cls = self.get_class_for_row_id(row_id)
            is_coord_class = (cls == 'coordinate')
            
            col_to_update = None
            is_coord_update = False
            
            if is_coord_class:
                if column == 0:
                    col_to_update = 'coord_text'
                    is_coord_update = True
            else:
                if column == 0:
                    col_to_update = 'anchor_text'
                elif column == 1:
                    col_to_update = 'coord_text'
                    is_coord_update = True
                elif column == 2 and cls == 'signal':
                    col_to_update = 'fahrtrichtung'
            
            if col_to_update:
                idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
                if idx_list:
                    idx = idx_list[0]
                    self.df_all.loc[idx, col_to_update] = new_text
                    
                    if is_coord_update:
                        val, gi = parse_coord(new_text)
                        self.df_all.loc[idx, 'coord_value'] = val
                        self.df_all.loc[idx, 'gi_gl'] = gi
                
                df_page = self.page_dfs.get(self.current_page)
                if df_page is not None:
                    idx_list_page = df_page.index[df_page['row_id'] == row_id].tolist()
                    if idx_list_page:
                        idx_p = idx_list_page[0]
                        df_page.loc[idx_p, col_to_update] = new_text
                        if is_coord_update:
                            val, gi = parse_coord(new_text)
                            df_page.loc[idx_p, 'coord_value'] = val
                            df_page.loc[idx_p, 'gi_gl'] = gi
            
            if self.tree.currentItem() is item:
                self.on_tree_selection_changed()
        
        except Exception as e:
            print(f"Error in on_tree_item_changed: {e}")
        finally:
            self.tree.blockSignals(False)
    
    def on_class_selector_changed(self, class_name: str):
        """Handle class selector change"""
        self._active_class_for_threshold_setting = class_name
        
        self._apply_all_filters()
        if self.current_page in self.page_base_pix:
            self._create_items_for_page(self.current_page)
        
        self.clear_hover_highlight()
    
    def get_class_for_row_id(self, row_id: int) -> Optional[str]:
        """Get class for row ID"""
        if self.df_all is None:
            return None
        row_list = self.df_all[self.df_all['row_id'] == row_id]
        if not row_list.empty:
            return row_list.iloc[0].get('cls')
        return None
    
    def _reconstruct_det_from_row(self, row: pd.Series) -> dict:
        """Rebuild detection dict from row"""
        if row.get("cls") == "coordinate":
            x1, y1, x2, y2 = row.get("cx1"), row.get("cy1"), row.get("cx2"), row.get("cy2")
        else:
            x1, y1, x2, y2 = row.get("ax1"), row.get("ay1"), row.get("ax2"), row.get("ay2")
        
        return {
            "cls": row.get("cls"),
            "name": row.get("cls"),
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "angle": row.get("angle"),
            "angle_raw": row.get("angle_raw", row.get("angle")),
            "obb_cx": row.get("obb_cx"),
            "obb_cy": row.get("obb_cy"),
            "obb_w": row.get("obb_w"),
            "obb_h": row.get("obb_h"),
            "poly": np.array(row.get("poly")) if isinstance(row.get("poly"), (list, tuple)) else None,
        }
    
    def on_rerun_ocr(self, row_id: int, ocr_type: str):
        """Re-run OCR on detection"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            if self.current_page_bgr_array is None:
                raise Exception("BGR array not found")
            
            row_list = self.df_all[self.df_all['row_id'] == row_id]
            if row_list.empty:
                raise Exception(f"Row {row_id} not found")
            
            row = row_list.iloc[0]
            det = self._reconstruct_det_from_row(row)
            cls = det.get("cls")
            
            new_text = ""
            is_coord = False
            
            if cls == "coordinate":
                is_coord = True
                if ocr_type == 'horizontal':
                    new_text = ocr_coordinate_horizontal(det, self.current_page_bgr_array, "paddleocr")
                else:
                    new_text = ocr_coordinate_angular(det, self.current_page_bgr_array, "paddleocr")
            elif cls == "signal":
                new_text = ocr_signal_name(det, self.current_page_bgr_array, "paddleocr")
            elif cls in {"gks_gesteuert", "gks_festkodiert"}:
                if ocr_type == 'horizontal':
                    new_text = ocr_numeric_cardinal_box(det, self.current_page_bgr_array)
                else:
                    new_text = ocr_numeric_tilted_box(det, self.current_page_bgr_array)
            else:
                new_text = ocr_generic_name(det, self.current_page_bgr_array, "paddleocr",
                                           allow_numeric=(cls in NUMERIC_OK), cls_name=cls)
            
            item = self.row_id_to_tree_item.get(row_id)
            if item:
                col_to_update = 0
                if is_coord and cls != 'coordinate':
                    col_to_update = 1
                item.setText(col_to_update, new_text)
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Re-OCR Error", str(e))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    
    def on_manual_ocr_toggled(self, checked: bool, mode: str = 'horizontal'):
            """Toggle manual OCR mode"""
            if checked:
                if mode == 'horizontal' and self.btn_manual_ocr_angular.isChecked():
                    self.btn_manual_ocr_angular.setChecked(False)
                elif mode == 'angular' and self.btn_manual_ocr.isChecked():
                    self.btn_manual_ocr.setChecked(False)
                
                if self.current_page_bgr_array is None:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Kein BGR-Bild geladen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                item = self.tree.currentItem()
                col = self.tree.currentColumn()
                
                if not item or item.childCount() > 0:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte Zelle auswählen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                if col not in [0, 1]:
                    QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte Spalte 'Text/Nummer' oder 'Koordinatentext' auswählen")
                    if mode == 'horizontal': self.btn_manual_ocr.setChecked(False)
                    else: self.btn_manual_ocr_angular.setChecked(False)
                    
                    # --- ADD THIS ---
                    self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                    # --- END ADD ---
                    return
                
                self.draw_ocr_target_item = item
                self.draw_ocr_target_column = col
                self.draw_ocr_mode = mode
                
                self.is_drawing_mode = True
                is_rotated = (mode == 'angular')
                self.view.toggle_drawing_mode(True, rotated=is_rotated)

                # --- ADD THIS (logic for different messages) ---
                if mode == 'angular':
                    self._set_status(
                        "📐 Manuelles OCR (Angular): 1. Zelle auswählen. 2. Klicken Sie Start- & Endpunkt der Text-Basislinie. 3. Klicken Sie ein drittes Mal, um die Höhe festzulegen."
                    )
                else:
                    self._set_status(
                        "📏 Manuelles OCR (Horizontal): 1. Zelle in Tabelle auswählen. 2. Ziehen Sie ein horizontales Rechteck auf dem Bild."
                    )
                # --- END ADD ---

            else:
                # --- ADD THIS (for toggling off) ---
                self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                # --- END ADD ---

                self.is_drawing_mode = False
                self.view.toggle_drawing_mode(False)
                self.draw_ocr_target_item = None
                self.draw_ocr_target_column = None
                self.draw_ocr_mode = 'horizontal'
    
    def on_rect_drawn(self, rect: QtCore.QRectF):
        """Handle rectangle drawn for manual OCR"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        item_to_update = self.draw_ocr_target_item
        col_to_update = self.draw_ocr_target_column
        original_mode = self.draw_ocr_mode
        
        self.draw_ocr_target_item = None
        self.draw_ocr_target_column = None
        self.draw_ocr_mode = 'horizontal'
        
        try:
            if not item_to_update or col_to_update is None:
                raise Exception("No target element")
            
            row_id = item_to_update.data(0, QtCore.Qt.UserRole)
            
            cls = self.get_class_for_row_id(row_id)
            if cls is None:
                raise Exception("Class not found")
            
            x1 = int(rect.left())
            y1 = int(rect.top())
            x2 = int(rect.right())
            y2 = int(rect.bottom())
            
            if x2 <= x1 or y2 <= y1 or self.current_page_bgr_array is None:
                raise Exception("Invalid rectangle")
            
            h, w = self.current_page_bgr_array.shape[:2]
            box_w = x2 - x1
            box_h = y2 - y1
            box_min_side = min(box_w, box_h)
            
            if original_mode == 'angular':
                if box_min_side < 70:
                    pad = 18
                elif box_min_side < 100:
                    pad = 16
                else:
                    pad = 14
            else:
                pad = max(10, min(16, int(box_min_side * 0.15)))
            
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)
            
            crop_bgr = self.current_page_bgr_array[y1:y2, x1:x2]
            
            if original_mode == 'angular':
                new_text, conf = manual_angular_ocr(crop_bgr, cls)
            else:
                crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
                new_text, conf = paddleocr_recognize(crop_pil, cls_name=cls, whitelist=None)
            
            QtWidgets.QApplication.restoreOverrideCursor()
            
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("OCR Ergebnis")
            msg.setIcon(QtWidgets.QMessageBox.Question)
            msg.setText(f"OCR Ergebnis:\n\n'{new_text}'\n\nKonfidenz: {conf:.2f}\n\nÜbernehmen?")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            
            result = msg.exec_()
            
            if result == QtWidgets.QMessageBox.Yes:
                row_id = item_to_update.data(0, QtCore.Qt.UserRole)
        
                if row_id:
                    self._save_state("Manuelles OCR", [row_id])
                item_to_update.setText(col_to_update, new_text)
        
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Manual OCR Error", str(e))
        finally:
            self.btn_manual_ocr.setChecked(False)
            self.btn_manual_ocr_angular.setChecked(False)
            self.view.toggle_drawing_mode(False)
    
    def on_rotated_rect_drawn(self, rect: QtCore.QRectF, angle: float):
        """Handle rotated rectangle for angular OCR"""
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        item_to_update = self.draw_ocr_target_item
        col_to_update = self.draw_ocr_target_column
        
        self.draw_ocr_target_item = None
        self.draw_ocr_target_column = None
        self.draw_ocr_mode = 'horizontal'
        
        try:
            if not item_to_update or col_to_update is None:
                raise Exception("No target")
            
            row_id = item_to_update.data(0, QtCore.Qt.UserRole)
            cls = self.get_class_for_row_id(row_id)
            if cls is None:
                raise Exception("Class not found")
            
            h, w = self.current_page_bgr_array.shape[:2]
            
            center_x = rect.center().x()
            center_y = rect.center().y()
            width = int(rect.width())
            height = int(rect.height())
            
            if width < 10 or height < 10:
                raise Exception("Rectangle too small")
            
            MAX_DIM = 5000
            if width > MAX_DIM or height > MAX_DIM:
                raise Exception(f"Rectangle too large ({width}x{height})")
            
            box_min_side = min(width, height)
            if box_min_side < 70:
                pad = 30
            elif box_min_side < 100:
                pad = 25
            else:
                pad = 20
            
            width_pad = max(pad, int(width * 0.15))
            height_pad = max(pad, int(height * 0.25))
            
            expanded_width = width + 2 * width_pad
            expanded_height = height + 2 * height_pad
            
            angle_rad = math.radians(angle)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            
            half_w = expanded_width / 2
            half_h = expanded_height / 2
            
            corners = [
                (center_x + (-half_w * cos_a - -half_h * sin_a), 
                 center_y + (-half_w * sin_a + -half_h * cos_a)),
                (center_x + (half_w * cos_a - -half_h * sin_a), 
                 center_y + (half_w * sin_a + -half_h * cos_a)),
                (center_x + (half_w * cos_a - half_h * sin_a), 
                 center_y + (half_w * sin_a + half_h * cos_a)),
                (center_x + (-half_w * cos_a - half_h * sin_a), 
                 center_y + (-half_w * sin_a + half_h * cos_a)),
            ]
            
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            bbox_x1 = max(0, int(min(xs)))
            bbox_y1 = max(0, int(min(ys)))
            bbox_x2 = min(w, int(max(xs)))
            bbox_y2 = min(h, int(max(ys)))
            
            if bbox_x2 <= bbox_x1 or bbox_y2 <= bbox_y1:
                raise Exception("Rectangle outside image")
            
            cropped = self.current_page_bgr_array[bbox_y1:bbox_y2, bbox_x1:bbox_x2]
            
            if cropped.size == 0:
                raise Exception("Empty crop")
            
            adjusted_center_x = center_x - bbox_x1
            adjusted_center_y = center_y - bbox_y1
            
            M = cv2.getRotationMatrix2D((adjusted_center_x, adjusted_center_y), angle, 1.0)
            
            crop_h, crop_w = cropped.shape[:2]
            rotated = cv2.warpAffine(cropped, M, (crop_w, crop_h),
                                    flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REPLICATE)
            
            x1 = int(adjusted_center_x - expanded_width / 2)
            y1 = int(adjusted_center_y - expanded_height / 2)
            x2 = int(adjusted_center_x + expanded_width / 2)
            y2 = int(adjusted_center_y + expanded_height / 2)
            
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(crop_w, x2)
            y2 = min(crop_h, y2)
            
            final_crop = rotated[y1:y2, x1:x2]
            
            if final_crop.size == 0:
                raise Exception("Final crop empty")
            
            new_text, conf = manual_angular_ocr(final_crop, cls)
            
            QtWidgets.QApplication.restoreOverrideCursor()
            
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("OCR Ergebnis")
            msg.setIcon(QtWidgets.QMessageBox.Question)
            msg.setText(f"OCR Ergebnis:\n\n'{new_text}'\n\nKonfidenz: {conf:.2f}\n\nÜbernehmen?")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.Yes)
            
            result = msg.exec_()
            
            if result == QtWidgets.QMessageBox.Yes:
                row_id = item_to_update.data(0, QtCore.Qt.UserRole)
        
            if row_id:
                self._save_state("Manuelles OCR", [row_id])
            item_to_update.setText(col_to_update, new_text)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Manual OCR Error", str(e))
        finally:
            self.btn_manual_ocr.setChecked(False)
            self.btn_manual_ocr_angular.setChecked(False)
            self.view.toggle_drawing_mode(False)
    
    def on_manual_link_toggled(self, checked: bool):
            """Toggle manual linking mode"""
            self.is_manual_linking_mode = checked
            
            if checked:
                # --- ADD THIS ---
                self._set_status(
                    "Verknüpfungsmodus: 1. Klicken Sie auf ein Ankerelement (z.B. Signal). 2. Klicken Sie auf die zugehörige Koordinate."
                )
                # --- END ADD ---

                if self.btn_manual_ocr.isChecked():
                    self.btn_manual_ocr.setChecked(False)
                if self.btn_manual_ocr_angular.isChecked():
                    self.btn_manual_ocr_angular.setChecked(False)
                
                self.view.setCursor(QtCore.Qt.CrossCursor)
                self.link_source_row_id = None
                if self.link_drag_line and self.link_drag_line.scene():
                    self.scene.removeItem(self.link_drag_line)
                self.link_drag_line = None
            else:
                # --- ADD THIS ---
                self._set_status(f"Bereit: {os.path.basename(self.layout_name)}")
                # --- END ADD ---
                
                self.view.setCursor(QtCore.Qt.ArrowCursor)
                self.link_source_row_id = None
                if self.link_drag_line and self.link_drag_line.scene():
                    self.scene.removeItem(self.link_drag_line)
                self.link_drag_line = None
    
    def on_linking_click(self, scene_pos: QtCore.QPointF):
        """Handle click during linking mode"""
        clicked_items = self.scene.items(scene_pos)
        
        clicked_row_id = None
        for item in clicked_items:
            try:
                data = item.data(0)
                if data is not None:
                    clicked_row_id = int(data)
                    break
            except:
                continue
        
        if clicked_row_id is None:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte auf ein Element klicken")
            return
        
        row_list = self.df_all[self.df_all['row_id'] == clicked_row_id]
        if row_list.empty:
            return
        
        clicked_class = row_list.iloc[0].get('cls')
        
        if self.link_source_row_id is None:
            if clicked_class == 'coordinate':
                QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte zuerst Ankerelement klicken")
                return
            
            self.link_source_row_id = clicked_row_id
            
            items = self.current_row_items.get(clicked_row_id)
            if items:
                pen = QtGui.QPen(QtGui.QColor("#ffff00"), 4)
                for it in items:
                    if isinstance(it, (QtWidgets.QGraphicsRectItem, QtWidgets.QGraphicsPolygonItem)):
                        it.setPen(pen)
        else:
            if clicked_class != 'coordinate':
                QtWidgets.QMessageBox.warning(self, "Fehler", "Bitte auf Koordinate klicken")
                return
            
            coord_row_id = clicked_row_id
            anchor_row_id = self.link_source_row_id
            
            self._link_anchor_to_coordinate(anchor_row_id, coord_row_id)
            
            self.link_source_row_id = None
            self._refresh_page_graphics()
            self.btn_manual_link.setChecked(False)
    
    def _link_anchor_to_coordinate(self, anchor_row_id: int, coord_row_id: int):
        """Link anchor to coordinate"""
        anchor_rows = self.df_all[self.df_all['row_id'] == anchor_row_id]
        if anchor_rows.empty:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Anchor not found")
            return
        
        anchor_row = anchor_rows.iloc[0]
        anchor_class = anchor_row.get('cls')
        anchor_text = anchor_row.get('anchor_text', '')
        
        coord_rows = self.df_all[self.df_all['row_id'] == coord_row_id]
        if coord_rows.empty:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Coordinate not found")
            return
        
        coord_row = coord_rows.iloc[0]
        coord_text = coord_row.get('coord_text', '')
        coord_value = coord_row.get('coord_value')
        gi_gl = coord_row.get('gi_gl')
        cx1, cy1 = coord_row.get('cx1'), coord_row.get('cy1')
        cx2, cy2 = coord_row.get('cx2'), coord_row.get('cy2')
        
        if not coord_text:
            QtWidgets.QMessageBox.warning(self, "Fehler", "Coordinate has no text")
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Verknüpfung bestätigen",
            f"Verknüpfen?\n\nAnker: {anchor_class} '{anchor_text}'\nKoordinate: {coord_text}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._save_state("Koordinate verknüpft", [anchor_row_id])

        anchor_idx_list = self.df_all.index[self.df_all['row_id'] == anchor_row_id].tolist()
        if anchor_idx_list:
            idx = anchor_idx_list[0]
            self.df_all.at[idx, 'coord_text'] = coord_text
            self.df_all.at[idx, 'coord_value'] = coord_value
            self.df_all.at[idx, 'gi_gl'] = gi_gl
            self.df_all.at[idx, 'cx1'] = cx1
            self.df_all.at[idx, 'cy1'] = cy1
            self.df_all.at[idx, 'cx2'] = cx2
            self.df_all.at[idx, 'cy2'] = cy2
        
        df_page = self.page_dfs.get(self.current_page)
        if df_page is not None:
            page_idx_list = df_page.index[df_page['row_id'] == anchor_row_id].tolist()
            if page_idx_list:
                idx_p = page_idx_list[0]
                df_page.at[idx_p, 'coord_text'] = coord_text
                df_page.at[idx_p, 'coord_value'] = coord_value
                df_page.at[idx_p, 'gi_gl'] = gi_gl
                df_page.at[idx_p, 'cx1'] = cx1
                df_page.at[idx_p, 'cy1'] = cy1
                df_page.at[idx_p, 'cx2'] = cx2
                df_page.at[idx_p, 'cy2'] = cy2
        
        anchor_tree_item = self.row_id_to_tree_item.get(anchor_row_id)
        if anchor_tree_item:
            anchor_tree_item.setText(1, coord_text)
        
        specs = self.all_page_row_specs.get(self.current_page, {})
        if anchor_row_id in specs:
            label = specs[anchor_row_id]['label']
            if '|' in label:
                parts = label.split('|')
                parts[1] = f" {coord_text}"
                label = '|'.join(parts)
            else:
                label += f" | {coord_text}"
            specs[anchor_row_id]['label'] = label
        
        self.on_page_changed(self.current_page)
    
    def _refresh_page_graphics(self):
        """Refresh graphics overlays"""
        if self.current_page not in self.page_base_pix:
            return
        
        for items in self.current_row_items.values():
            for item in items:
                if item.scene():
                    self.scene.removeItem(item)
        
        self.current_row_items.clear()
        self._create_items_for_page(self.current_page)
    
    def on_export_excel(self):
        """Export to Excel with advanced user configuration"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(self, "Keine Daten", "Nichts zu exportieren")
            return
        
        # Import the dialog
        from excelexport import AdvancedExcelExportDialog
        
        # Show advanced configuration dialog
        dialog = AdvancedExcelExportDialog(self)
        
        # Apply theme if you have one (FIXED VERSION)
        try:
            # Try to apply theme if available
            if hasattr(self, 'parent_auditing') and self.parent_auditing is not None:
                if hasattr(self.parent_auditing, 'main_app_ref') and self.parent_auditing.main_app_ref is not None:
                    if hasattr(self.parent_auditing.main_app_ref, '_current_theme'):
                        current_theme = self.parent_auditing.main_app_ref._current_theme
                        
                        # Check if you have DARK_QSS and LIGHT_QSS defined in your main file
                        if current_theme == "dark" and 'DARK_QSS' in globals():
                            dialog.setStyleSheet(DARK_QSS)
                        elif current_theme == "light" and 'LIGHT_QSS' in globals():
                            dialog.setStyleSheet(LIGHT_QSS)
        except Exception as e:
            # If theme application fails, just continue without theme
            print(f"Could not apply theme: {e}")
        
        # Show dialog
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return  # User cancelled
        
        # Get export configuration
        export_config = dialog.get_export_config()
        
        if not export_config['classes']:
            QtWidgets.QMessageBox.warning(
                self,
                "Keine Auswahl",
                "Bitte wählen Sie mindestens eine Klasse mit Spalten aus."
            )
            return
        
        # Ask for save location
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Excel speichern",
            f"{os.path.splitext(self.layout_name)[0]}_export.xlsx",
            "Excel (*.xlsx)"
        )
        
        if not fn:
            return
        
        try:
            # Perform export
            self._execute_excel_export(fn, export_config)
            
            QtWidgets.QMessageBox.information(
                self,
                "Gespeichert",
                f"Excel erfolgreich exportiert nach:\n{fn}"
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "Export-Fehler", str(e))

    def _execute_excel_export(self, filename: str, config: dict):
        """Execute the Excel export with given configuration"""
        
        # Get base DataFrame (with or without filters)
        if config['options']['apply_filters']:
            df_base = self._get_filtered_dataframe()
        else:
            df_base = self.df_all.copy()
        
        if df_base.empty:
            raise Exception("Keine Daten zum Exportieren (möglicherweise alle gefiltert)")
        
        # Apply sorting
        sort_by = config['options']['sort_by']
        if sort_by == "Nach Klasse":
            df_base = df_base.sort_values('cls')
        elif sort_by == "Nach Seite":
            df_base = df_base.sort_values('page')
        elif sort_by == "Nach Koordinatenwert":
            df_base = df_base.sort_values('coord_value', na_position='last')
        elif sort_by == "Nach Text/Nummer":
            df_base = df_base.sort_values('anchor_text', na_position='last')
        
        # Create Excel writer
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            
            if config['options']['separate_sheets']:
                # Separate sheet per class
                for cls_name, cls_config in config['classes'].items():
                    self._export_class_to_sheet(
                        writer,
                        df_base,
                        cls_name,
                        cls_config,
                        config['options']
                    )
            else:
                # Single sheet with all classes
                all_data = []
                
                for cls_name, cls_config in config['classes'].items():
                    df_class = df_base[df_base['cls'] == cls_name].copy()
                    
                    if df_class.empty:
                        continue
                    
                    # Select and rename columns
                    df_export = self._prepare_dataframe_for_export(
                        df_class,
                        cls_config,
                        config['options']['include_empty']
                    )
                    
                    if not df_export.empty:
                        all_data.append(df_export)
                
                if all_data:
                    df_combined = pd.concat(all_data, ignore_index=True)
                    df_combined.to_excel(writer, index=False, sheet_name='Alle Klassen')
                    
                    if config['options']['auto_width']:
                        self._auto_adjust_columns(writer, 'Alle Klassen', df_combined)
                    
                    if config['options']['freeze_header']:
                        self._freeze_header(writer, 'Alle Klassen')

    def _export_class_to_sheet(self, writer, df_base: pd.DataFrame, cls_name: str,
                            cls_config: dict, options: dict):
        """Export a single class to its own sheet"""
        df_class = df_base[df_base['cls'] == cls_name].copy()
        
        if df_class.empty:
            return
        
        # Prepare DataFrame
        df_export = self._prepare_dataframe_for_export(
            df_class,
            cls_config,
            options['include_empty']
        )
        
        if df_export.empty:
            return
        
        # Write to Excel
        sheet_name = cls_name[:31]  # Excel sheet name limit
        df_export.to_excel(writer, index=False, sheet_name=sheet_name)
        
        # Apply formatting
        if options['auto_width']:
            self._auto_adjust_columns(writer, sheet_name, df_export)
        
        if options['freeze_header']:
            self._freeze_header(writer, sheet_name)

    def _prepare_dataframe_for_export(self, df: pd.DataFrame, cls_config: dict,
                                    include_empty: bool) -> pd.DataFrame:
        """Prepare DataFrame for export with user-defined columns and names"""
        
        # Get columns in user-defined order
        columns = cls_config['columns']
        display_names = cls_config['display_names']
        
        # Filter to only existing columns
        available_cols = [c for c in columns if c in df.columns]
        
        if not available_cols:
            return pd.DataFrame()
        
        # Select columns
        df_export = df[available_cols].copy()
        
        # Rename to display names
        rename_map = {col: display_names.get(col, col) for col in available_cols}
        df_export = df_export.rename(columns=rename_map)
        
        # Handle empty cells
        if not include_empty:
            # Replace NaN/None with empty string for better readability
            df_export = df_export.fillna('')
        
        return df_export

    def _get_filtered_dataframe(self) -> pd.DataFrame:
        """Get DataFrame with current filters applied"""
        df_filtered = self.df_all.copy()
        
        # Apply confidence thresholds
        keep_rows = []
        for _, row in df_filtered.iterrows():
            conf = row.get('conf', 0.0)
            cls = row.get('cls', '')
            g = self._class_confidence_thresholds.get('__all__', 0.0)
            c = self._class_confidence_thresholds.get(cls, 0.0)
            if conf >= g and conf >= c:
                keep_rows.append(row)
        
        return pd.DataFrame(keep_rows) if keep_rows else pd.DataFrame()

    def _auto_adjust_columns(self, writer, sheet_name: str, df: pd.DataFrame):
        """Auto-adjust column widths in Excel"""
        try:
            from openpyxl.utils import get_column_letter
            
            worksheet = writer.sheets[sheet_name]
            
            for idx, col in enumerate(df.columns):
                # Calculate max length
                max_length = max(
                    df[col].astype(str).map(len).max(),  # Max in data
                    len(str(col))  # Column name length
                )
                
                # Add padding and cap
                adjusted_width = min(max_length + 2, 50)
                
                # Set width
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = adjusted_width
        
        except Exception as e:
            print(f"Warning: Could not auto-adjust columns: {e}")

    def _freeze_header(self, writer, sheet_name: str):
        """Freeze the header row"""
        try:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = 'A2'  # Freeze first row
        except Exception as e:
            print(f"Warning: Could not freeze header: {e}")

    def on_export_json(self):
        """Export to JSON"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(self, "Keine Daten", "Nichts zu exportieren")
            return
        
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "JSON speichern",
            f"{os.path.splitext(self.layout_name)[0]}_export.json",
            "JSON (*.json)"
        )
        if not fn:
            return
        
        try:
            df_base = self.df_all.copy()
            keep = []
            for _, row in df_base.iterrows():
                conf = row.get('conf', 0.0)
                cls = row.get('cls', '')
                g = self._class_confidence_thresholds.get('__all__', 0.0)
                c = self._class_confidence_thresholds.get(cls, 0.0)
                if conf >= g and conf >= c:
                    keep.append(row)
            
            if not keep:
                QtWidgets.QMessageBox.information(self, "Keine Daten", "Keine Daten nach Filter")
                return
            
            df_out = pd.DataFrame(keep)
            
            output_data = {}
            classes = sorted(df_out['cls'].unique())
            if 'coordinate' in classes:
                classes.remove('coordinate')
                classes.append('coordinate')
            
            for cls_name in classes:
                df_class = df_out[df_out['cls'] == cls_name].copy()
                
                if cls_name == 'coordinate':
                    cols_to_keep = ['coord_text', 'coord_value', 'gi_gl', 'page', 'notes', 'conf']
                    col_rename = {
                        'coord_text': 'Text',
                        'coord_value': 'Wert',
                        'gi_gl': 'GI/GL',
                        'page': 'Seite',
                        'notes': 'Notizen',
                        'conf': 'Konfidenz'
                    }
                else:
                    cols_to_keep = ['anchor_text', 'coord_text', 'coord_value', 'gi_gl', 'page', 'notes', 'conf']
                    col_rename = {
                        'anchor_text': 'Text/Nummer',
                        'coord_text': 'Koordinatentext',
                        'coord_value': 'Koordinatenwert',
                        'gi_gl': 'GI/GL',
                        'page': 'Seite',
                        'notes': 'Notizen',
                        'conf': 'Konfidenz'
                    }
                    if cls_name == 'signal':
                        cols_to_keep.append('fahrtrichtung')
                        col_rename['fahrtrichtung'] = 'Fahrtrichtung'
                
                cols_to_keep = [c for c in cols_to_keep if c in df_class.columns]
                if not cols_to_keep:
                    continue
                
                df_sheet = df_class[cols_to_keep].copy()
                df_sheet.rename(columns=col_rename, inplace=True)
                output_data[cls_name] = df_sheet.to_dict('records')
            
            import json
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            QtWidgets.QMessageBox.information(self, "Gespeichert", f"JSON exportiert nach:\n{fn}")
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Fehler", str(e))

    def _save_state(self, action_name: str, affected_row_ids: List[int]):
        """
        Save current state to undo stack
        
        Args:
            action_name: Description of the action
            affected_row_ids: List of row IDs that were modified
        """

        if self._is_undoing_or_redoing:
            return
        
        if self._is_loading_data:
            return
        
        if not affected_row_ids:
            return        
        
        # Get current state of affected rows
        state = {
            'action': action_name,
            'timestamp': pd.Timestamp.now(),
            'rows': {}
        }
        
        for row_id in affected_row_ids:
            row_data = self.df_all[self.df_all['row_id'] == row_id]
            if not row_data.empty:
                # Store complete row as dict
                row_dict = row_data.iloc[0].to_dict()
                
                # Filter out numpy arrays (convert to lists)
                filtered_dict = {}
                for col, value in row_dict.items():
                    if isinstance(value, np.ndarray):
                        try:
                            filtered_dict[col] = value.tolist()
                        except:
                            continue
                    else:
                        filtered_dict[col] = value
                
                state['rows'][row_id] = filtered_dict
        
        # Add to undo stack
        self.undo_stack.append(state)
        
        # Limit stack size
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        
        # Clear redo stack (new action invalidates redo history)
        self.redo_stack.clear()
        
        self._set_status(f"💾 {action_name} - Rückgängig: Strg+Z")
        
        # Update button states
        if hasattr(self, '_update_undo_redo_buttons'):
            self._update_undo_redo_buttons()


    def undo(self):
        """Undo last action"""
        
        if not self.undo_stack:
            self._set_status("⚠️ Nichts rückgängig zu machen")
            QtWidgets.QMessageBox.information(
                self,
                "Rückgängig",
                "Keine Aktionen zum Rückgängigmachen vorhanden."
            )
            return
        
        # ✅ SET FLAG TO PREVENT STATE SAVING
        self._is_undoing_or_redoing = True
        
        try:
            # Pop last state
            state = self.undo_stack.pop()
            
            # Save current state to redo stack BEFORE undoing
            redo_state = {
                'action': f"Redo: {state['action']}",
                'timestamp': pd.Timestamp.now(),
                'rows': {}
            }
            
            for row_id in state['rows'].keys():
                row_data = self.df_all[self.df_all['row_id'] == row_id]
                if not row_data.empty:
                    row_dict = row_data.iloc[0].to_dict()
                    
                    # Filter out numpy arrays
                    filtered_dict = {}
                    for col, value in row_dict.items():
                        if isinstance(value, np.ndarray):
                            try:
                                filtered_dict[col] = value.tolist()
                            except:
                                continue
                        else:
                            filtered_dict[col] = value
                    
                    redo_state['rows'][row_id] = filtered_dict
            
            self.redo_stack.append(redo_state)
            
            # Restore old state
            for row_id, row_dict in state['rows'].items():
                # Update df_all
                mask = self.df_all['row_id'] == row_id
                if mask.any():
                    idx = self.df_all[mask].index[0]
                    
                    for col, value in row_dict.items():
                        if col not in self.df_all.columns:
                            continue
                        
                        try:
                            # Convert lists back to numpy arrays if needed
                            if col == 'poly' and isinstance(value, list):
                                value = np.array(value)
                            
                            self.df_all.at[idx, col] = value
                        except Exception as e:
                            print(f"⚠️ Could not restore column '{col}': {e}")
                
                # Update page_dfs
                page = row_dict.get('page')
                if page in self.page_dfs:
                    page_mask = self.page_dfs[page]['row_id'] == row_id
                    if page_mask.any():
                        page_idx = self.page_dfs[page][page_mask].index[0]
                        
                        for col, value in row_dict.items():
                            if col not in self.page_dfs[page].columns:
                                continue
                            
                            try:
                                # Convert lists back to numpy arrays if needed
                                if col == 'poly' and isinstance(value, list):
                                    value = np.array(value)
                                
                                self.page_dfs[page].at[page_idx, col] = value
                            except Exception as e:
                                print(f"⚠️ Could not restore page column '{col}': {e}")
                
                # Update tree widget (block signals to prevent triggering _save_state)
                tree_item = self.row_id_to_tree_item.get(row_id)
                if tree_item:
                    self.tree.blockSignals(True)
                    
                    cls = row_dict.get('cls')
                    
                    if cls == 'coordinate':
                        tree_item.setText(0, str(row_dict.get('coord_text', '')))
                    else:
                        tree_item.setText(0, str(row_dict.get('anchor_text', '')))
                        tree_item.setText(1, str(row_dict.get('coord_text', '')))
                        
                        if cls == 'signal' and pd.notna(row_dict.get('fahrtrichtung')):
                            tree_item.setText(2, str(row_dict.get('fahrtrichtung', '')))
                    
                    self.tree.blockSignals(False)
            
            # Rebuild graphics
            self._rebuild_row_specs_for_current_page()
            self.on_page_changed(self.current_page)
            
            self._set_status(f"↶ Rückgängig: {state['action']} - Wiederholen: Strg+Y")
            
            # Update button states
            self._update_undo_redo_buttons()
            
        
        finally:
            # ✅ ALWAYS CLEAR FLAG
            self._is_undoing_or_redoing = False

    def redo(self):
        """Redo last undone action"""        
        if not self.redo_stack:
            self._set_status("⚠️ Nichts wiederherzustellen")
            QtWidgets.QMessageBox.information(
                self,
                "Wiederholen",
                "Keine Aktionen zum Wiederherstellen vorhanden."
            )
            return
        
        # ✅ SET FLAG TO PREVENT STATE SAVING
        self._is_undoing_or_redoing = True
        
        try:
            # Pop from redo stack
            state = self.redo_stack.pop()            
            # Save current state to undo stack
            undo_state = {
                'action': state['action'].replace('Redo: ', ''),
                'timestamp': pd.Timestamp.now(),
                'rows': {}
            }
            
            for row_id in state['rows'].keys():
                row_data = self.df_all[self.df_all['row_id'] == row_id]
                if not row_data.empty:
                    row_dict = row_data.iloc[0].to_dict()
                    
                    # Filter out numpy arrays
                    filtered_dict = {}
                    for col, value in row_dict.items():
                        if isinstance(value, np.ndarray):
                            try:
                                filtered_dict[col] = value.tolist()
                            except:
                                continue
                        else:
                            filtered_dict[col] = value
                    
                    undo_state['rows'][row_id] = filtered_dict
            
            self.undo_stack.append(undo_state)
            
            # Restore redo state
            for row_id, row_dict in state['rows'].items():
                # Update df_all
                mask = self.df_all['row_id'] == row_id
                if mask.any():
                    idx = self.df_all[mask].index[0]
                    
                    for col, value in row_dict.items():
                        if col not in self.df_all.columns:
                            continue
                        
                        try:
                            # Convert lists back to numpy arrays if needed
                            if col == 'poly' and isinstance(value, list):
                                value = np.array(value)
                            
                            self.df_all.at[idx, col] = value
                        except Exception as e:
                            print(f"⚠️ Could not restore column '{col}': {e}")
                
                # Update page_dfs
                page = row_dict.get('page')
                if page in self.page_dfs:
                    page_mask = self.page_dfs[page]['row_id'] == row_id
                    if page_mask.any():
                        page_idx = self.page_dfs[page][page_mask].index[0]
                        
                        for col, value in row_dict.items():
                            if col not in self.page_dfs[page].columns:
                                continue
                            
                            try:
                                # Convert lists back to numpy arrays if needed
                                if col == 'poly' and isinstance(value, list):
                                    value = np.array(value)
                                
                                self.page_dfs[page].at[page_idx, col] = value
                            except Exception as e:
                                print(f"⚠️ Could not restore page column '{col}': {e}")
                
                # Update tree widget (block signals to prevent triggering _save_state)
                tree_item = self.row_id_to_tree_item.get(row_id)
                if tree_item:
                    self.tree.blockSignals(True)
                    
                    cls = row_dict.get('cls')
                    
                    if cls == 'coordinate':
                        tree_item.setText(0, str(row_dict.get('coord_text', '')))
                    else:
                        tree_item.setText(0, str(row_dict.get('anchor_text', '')))
                        tree_item.setText(1, str(row_dict.get('coord_text', '')))
                        
                        if cls == 'signal' and pd.notna(row_dict.get('fahrtrichtung')):
                            tree_item.setText(2, str(row_dict.get('fahrtrichtung', '')))
                    
                    self.tree.blockSignals(False)
            
            # Rebuild graphics
            self._rebuild_row_specs_for_current_page()
            self.on_page_changed(self.current_page)
            
            self._set_status(f"↷ Wiederhergestellt: {state['action']}")
            
            # Update button states
            self._update_undo_redo_buttons()
            
        
        finally:
            # ✅ ALWAYS CLEAR FLAG
            self._is_undoing_or_redoing = False


    def run_validation(self):
        """Run enhanced validation with auto-correction support"""
        if self.df_all is None or self.df_all.empty:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Daten",
                "Keine Daten zum Validieren vorhanden."
            )
            return
        
        # Show progress dialog
        progress = QtWidgets.QProgressDialog(
            "Validiere Daten...",
            "Abbrechen",
            0, 0,
            self
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()
        
        try:
            # Run validation
            from data_validator2 import EnhancedDataValidator
            
            validator = EnhancedDataValidator(self.df_all)
            result = validator.validate_all(auto_correct=False)
            
            progress.close()
            
            # Show validation dialog
            dialog = EnhancedValidationResultsDialog(result, self)
            
            # ✅ Connect to the correction handler
            dialog.corrections_accepted.connect(
                lambda corrections: self._apply_corrections(validator, corrections)
            )
            
            dialog.exec_()
        
        except Exception as e:
            progress.close()
            QtWidgets.QMessageBox.critical(
                self,
                "Validierungsfehler",
                f"Fehler bei der Validierung:\n{str(e)}"
            )

    def _apply_corrections(self, validator: 'EnhancedDataValidator', corrections: List['ValidationIssue']):
        """Apply selected corrections to DataFrame AND update linked elements"""
        try:
            affected_row_ids = [issue.row_id for issue in corrections]
            self._save_state(f"{len(corrections)} Validierungskorrekturen", affected_row_ids)
            corrections_count = 0
            coordinate_updates = {}
            
            # STEP 1: Apply corrections
            for issue in corrections:
                mask = self.df_all['row_id'] == issue.row_id
                
                if mask.any():
                    old_value = self.df_all.loc[mask, issue.field].iloc[0]
                    self.df_all.loc[mask, issue.field] = issue.suggested_value
                    corrections_count += 1
                    
                    # Track coordinate text changes
                    if issue.field == 'coord_text':
                        cls = self.df_all.loc[mask, 'cls'].iloc[0]
                        
                        if cls == 'coordinate':
                            new_val, new_gi = parse_coord(issue.suggested_value)
                            self.df_all.loc[mask, 'coord_value'] = new_val
                            self.df_all.loc[mask, 'gi_gl'] = new_gi
                            
                            coordinate_updates[issue.row_id] = (
                                str(old_value),
                                str(issue.suggested_value),
                                new_val,
                                new_gi
                            )
                    
                    # Update page_dfs
                    page = self.df_all.loc[mask, 'page'].iloc[0]
                    if page in self.page_dfs:
                        page_mask = self.page_dfs[page]['row_id'] == issue.row_id
                        if page_mask.any():
                            self.page_dfs[page].loc[page_mask, issue.field] = issue.suggested_value
                            
                            if issue.field == 'coord_text':
                                cls = self.page_dfs[page].loc[page_mask, 'cls'].iloc[0]
                                if cls == 'coordinate':
                                    new_val, new_gi = parse_coord(issue.suggested_value)
                                    self.page_dfs[page].loc[page_mask, 'coord_value'] = new_val
                                    self.page_dfs[page].loc[page_mask, 'gi_gl'] = new_gi
            
            # STEP 2: Propagate coordinate changes
            linked_updates = 0
            if coordinate_updates:
                linked_updates = self._propagate_coordinate_changes(coordinate_updates)
            
            # STEP 3: Rebuild row specs
            self._rebuild_row_specs_for_current_page()
            
            # STEP 4: Refresh display
            self.on_page_changed(self.current_page)
            
            # STEP 5: Ask to re-validate
            msg = f"{corrections_count} Korrekturen wurden erfolgreich angewendet.\n\n"
            if coordinate_updates:
                msg += f"📌 {len(coordinate_updates)} Koordinaten korrigiert\n"
                msg += f"🔗 {linked_updates} verknüpfte Elemente aktualisiert\n\n"
            
            reply = QtWidgets.QMessageBox.question(
                self,
                "Korrekturen angewendet",
                msg + "Möchten Sie die Validierung erneut ausführen?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            
            if reply == QtWidgets.QMessageBox.Yes:
                # Re-run validation
                QtCore.QTimer.singleShot(100, self.run_validation)
            else:
                self._set_status(
                    f"✏️ {corrections_count} Korrekturen angewendet - Nicht gespeichert!"
                )
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                f"Fehler beim Anwenden der Korrekturen:\n{str(e)}"
            )

    def _propagate_coordinate_changes(self, coordinate_updates: Dict) -> int:
        """
        Propagate coordinate corrections to all linked elements.
        
        Args:
            coordinate_updates: Dict of {coord_row_id: (old_text, new_text, new_value, new_gi)}
        
        Returns:
            Number of linked elements updated
        """
        updated_count = 0
        
        for coord_row_id, (old_text, new_text, new_value, new_gi) in coordinate_updates.items():
            # Find the coordinate's bounding box
            coord_rows = self.df_all[self.df_all['row_id'] == coord_row_id]
            if coord_rows.empty:
                continue
            
            coord_row = coord_rows.iloc[0]
            coord_page = coord_row.get('page')
            
            # Get coordinate position
            cx1 = coord_row.get('cx1')
            cy1 = coord_row.get('cy1')
            cx2 = coord_row.get('cx2')
            cy2 = coord_row.get('cy2')
            
            if cx1 is None or cy1 is None:
                continue
            
            # ✅ Find all elements on the same page that reference this OLD coordinate text
            same_page_mask = (self.df_all['page'] == coord_page) & (self.df_all['cls'] != 'coordinate')
            
            for idx, row in self.df_all[same_page_mask].iterrows():
                # Check if this element is linked to the corrected coordinate
                # Method 1: Check if coord_text matches the OLD value
                if str(row.get('coord_text', '')).strip() == old_text.strip():
                    # Update to new coordinate text
                    self.df_all.at[idx, 'coord_text'] = new_text
                    self.df_all.at[idx, 'coord_value'] = new_value
                    self.df_all.at[idx, 'gi_gl'] = new_gi
                    
                    # Also update the bounding box reference
                    self.df_all.at[idx, 'cx1'] = cx1
                    self.df_all.at[idx, 'cy1'] = cy1
                    self.df_all.at[idx, 'cx2'] = cx2
                    self.df_all.at[idx, 'cy2'] = cy2
                    
                    updated_count += 1
                    
                    # Update in page_dfs too
                    if coord_page in self.page_dfs:
                        element_row_id = row['row_id']
                        page_mask = self.page_dfs[coord_page]['row_id'] == element_row_id
                        
                        if page_mask.any():
                            self.page_dfs[coord_page].loc[page_mask, 'coord_text'] = new_text
                            self.page_dfs[coord_page].loc[page_mask, 'coord_value'] = new_value
                            self.page_dfs[coord_page].loc[page_mask, 'gi_gl'] = new_gi
                            self.page_dfs[coord_page].loc[page_mask, 'cx1'] = cx1
                            self.page_dfs[coord_page].loc[page_mask, 'cy1'] = cy1
                            self.page_dfs[coord_page].loc[page_mask, 'cx2'] = cx2
                            self.page_dfs[coord_page].loc[page_mask, 'cy2'] = cy2
                    
                    # ✅ Update tree widget display
                    tree_item = self.row_id_to_tree_item.get(row['row_id'])
                    if tree_item:
                        tree_item.setText(1, new_text)  # Column 1 is coord_text
                    
                    print(f"✅ Updated linked element: {row.get('cls')} '{row.get('anchor_text')}' → '{new_text}'")
        
        return updated_count

    def _rebuild_row_specs_for_current_page(self):
        """
        Rebuild the row_specs for the current page after corrections.
        This ensures graphics overlays show updated text.
        """
        pidx = self.current_page
        df_page = self.page_dfs.get(pidx)
        
        if df_page is None:
            return
        
        specs = {}
        
        for _, row in df_page.iterrows():
            # Rebuild label with updated datak
            label = f"{row['cls']} {row.get('conf','')}"
            if pd.notna(row.get('anchor_text')) and row['anchor_text']:
                label += f" | {row['anchor_text']}"
            if pd.notna(row.get('coord_text')) and row['coord_text']:
                label += f" | {row['coord_text']}"  # ✅ This will now show corrected coordinate
            if 'angle' in df_page.columns and pd.notna(row.get('angle')):
                try:
                    label += f" θ={float(row['angle']):.1f}°"
                except Exception:
                    pass
            
            spec = {"label": label, "is_poly": False}
            poly = row.get("poly", None)
            
            # Handle polygon
            if isinstance(poly, (list, tuple)) and len(poly) == 4:
                try:
                    pts = np.array(poly, dtype=np.float32).reshape(4, 2)
                    spec.update({"is_poly": True, "pts": pts})
                    specs[int(row['row_id'])] = spec
                    continue
                except Exception:
                    pass
            
            # Handle bounding box
            if row['cls'] == 'coordinate':
                x1, y1, x2, y2 = row['cx1'], row['cy1'], row['cx2'], row['cy2']
            else:
                x1, y1, x2, y2 = row['ax1'], row['ay1'], row['ax2'], row['ay2']
            
            if pd.isna(x1) or x1 is None:
                continue
            
            w = int(x2 - x1)
            h = int(y2 - y1)
            spec.update({"rect": (int(x1), int(y1), w, h)})
            specs[int(row['row_id'])] = spec
        
        # Update the specs dictionary
        self.all_page_row_specs[pidx] = specs

    def _setup_undo_redo_shortcuts(self):
        """Setup undo/redo keyboard shortcuts"""
        # Undo: Ctrl+Z
        self.undo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence.Undo, self)
        self.undo_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.undo_shortcut.activated.connect(self._on_undo_shortcut)
        
        # Redo: Ctrl+Y (Windows) and Ctrl+Shift+Z (Mac/Linux)
        self.redo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence.Redo, self)
        self.redo_shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.redo_shortcut.activated.connect(self._on_redo_shortcut)
        
        # Alternative Redo: Ctrl+Shift+Z
        self.redo_shortcut2 = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut2.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
        self.redo_shortcut2.activated.connect(self._on_redo_shortcut)
        
        print("✅ Undo/Redo shortcuts initialized")

    def _on_undo_shortcut(self):
        """Handle undo shortcut activation"""
        print("🔵 Undo shortcut triggered (Ctrl+Z)")
        self.undo()

    def _on_redo_shortcut(self):
        """Handle redo shortcut activation"""
        print("🔵 Redo shortcut triggered (Ctrl+Y)")
        self.redo()

    def _update_undo_redo_buttons(self):
        """Update undo/redo button states"""
        if hasattr(self, 'btn_undo'):
            has_undo = len(self.undo_stack) > 0
            self.btn_undo.setEnabled(has_undo)
            
            if has_undo:
                last_action = self.undo_stack[-1]['action']
                self.btn_undo.setToolTip(f"Rückgängig: {last_action} (Strg+Z)")
                self.btn_undo.setText(f"↶ Rückgängig ({len(self.undo_stack)})")
            else:
                self.btn_undo.setToolTip("Nichts rückgängig zu machen")
                self.btn_undo.setText("↶ Rückgängig")
        
        if hasattr(self, 'btn_redo'):
            has_redo = len(self.redo_stack) > 0
            self.btn_redo.setEnabled(has_redo)
            
            if has_redo:
                last_action = self.redo_stack[-1]['action']
                self.btn_redo.setToolTip(f"Wiederholen: {last_action} (Strg+Y)")
                self.btn_redo.setText(f"↷ Wiederholen ({len(self.redo_stack)})")
            else:
                self.btn_redo.setToolTip("Nichts wiederherzustellen")
                self.btn_redo.setText("↷ Wiederholen")