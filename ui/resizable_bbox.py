# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Resizable Bounding Box Graphics Items
Allows user to resize detection bboxes with automatic OCR re-run
Includes context menu for quick actions (change class, re-run OCR, delete)
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from typing import Optional, Tuple, TYPE_CHECKING
import numpy as np
from config import debug_print

if TYPE_CHECKING:
    from ui.workspace_widget import WorkspaceWidget


class ResizeHandle(QtWidgets.QGraphicsRectItem):
    """Corner/edge handle for resizing bboxes"""

    def __init__(self, handle_type: str, parent_item: 'ResizableBBoxItem'):
        """
        Args:
            handle_type: 'top_left', 'top_right', 'bottom_left', 'bottom_right',
                        'top', 'bottom', 'left', 'right'
            parent_item: The resizable bbox this handle belongs to
        """
        # Make edge handles larger and rectangular for easier grabbing
        if handle_type in ['top', 'bottom']:
            # Horizontal edge handles: wide rectangles
            super().__init__(-16, -4, 32, 8)  # 32x8 (wide)
        elif handle_type in ['left', 'right']:
            # Vertical edge handles: tall rectangles
            super().__init__(-4, -16, 8, 32)  # 8x32 (tall)
        else:
            # Corner handles: small squares
            super().__init__(-4, -4, 8, 8)  # 8x8

        self.handle_type = handle_type
        self.parent_bbox = parent_item

        # Style - edge handles are slightly different color
        if handle_type in ['top', 'bottom', 'left', 'right']:
            self.setBrush(QtGui.QBrush(QtGui.QColor(0, 150, 255)))  # Lighter blue for edges
        else:
            self.setBrush(QtGui.QBrush(QtGui.QColor(0, 120, 215)))  # Darker blue for corners

        self.setPen(QtGui.QPen(QtCore.Qt.white, 1))
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(self._get_cursor())
        self.setZValue(1000)  # Always on top

    def _get_cursor(self) -> QtCore.Qt.CursorShape:
        """Get appropriate cursor for this handle"""
        cursors = {
            'top_left': QtCore.Qt.SizeFDiagCursor,
            'top_right': QtCore.Qt.SizeBDiagCursor,
            'bottom_left': QtCore.Qt.SizeBDiagCursor,
            'bottom_right': QtCore.Qt.SizeFDiagCursor,
            'top': QtCore.Qt.SizeVerCursor,
            'bottom': QtCore.Qt.SizeVerCursor,
            'left': QtCore.Qt.SizeHorCursor,
            'right': QtCore.Qt.SizeHorCursor,
        }
        return cursors.get(self.handle_type, QtCore.Qt.ArrowCursor)

    def itemChange(self, change, value):
        """Handle position changes"""
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            # Constrain handle movement and update parent bbox
            new_pos = value
            debug_print('ui_bbox', f"Handle {self.handle_type} moved to {new_pos}")
            self.parent_bbox.handle_moved(self.handle_type, new_pos)
            return new_pos
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Notify parent bbox when handle is released to trigger OCR"""
        super().mouseReleaseEvent(event)
        debug_print('ui_bbox', f"Handle {self.handle_type} released - triggering parent OCR")
        # Trigger OCR on parent bbox
        self.parent_bbox.on_handle_released()


class ResizableBBoxItem(QtWidgets.QGraphicsRectItem):
    """
    Resizable bounding box with corner and edge handles.
    When resizing is complete, triggers automatic OCR.
    """

    def __init__(self, x: float, y: float, w: float, h: float,
                 row_id: int, workspace: 'WorkspaceWidget'):
        super().__init__(x, y, w, h)
        self.row_id = row_id
        self.workspace = workspace
        self.handles = {}
        self.is_resizing = False
        self.original_rect = QtCore.QRectF(x, y, w, h)

        # Make selectable
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

        # Create handles (hidden by default)
        self._create_handles()
        self._update_handle_positions()
        self._hide_handles()

    def _create_handles(self):
        """Create 8 resize handles (4 corners + 4 edges)"""
        handle_types = [
            'top_left', 'top_right', 'bottom_left', 'bottom_right',
            'top', 'bottom', 'left', 'right'
        ]

        for handle_type in handle_types:
            handle = ResizeHandle(handle_type, self)
            handle.setParentItem(self)
            self.handles[handle_type] = handle

    def _update_handle_positions(self):
        """Position handles at corners and edges of the bbox"""
        rect = self.rect()
        x1, y1 = rect.x(), rect.y()
        x2, y2 = rect.right(), rect.bottom()
        cx, cy = rect.center().x(), rect.center().y()

        positions = {
            'top_left': (x1, y1),
            'top_right': (x2, y1),
            'bottom_left': (x1, y2),
            'bottom_right': (x2, y2),
            'top': (cx, y1),
            'bottom': (cx, y2),
            'left': (x1, cy),
            'right': (x2, cy),
        }

        # Temporarily disable geometry change signals to prevent recursion
        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, False)

        for handle_type, (x, y) in positions.items():
            self.handles[handle_type].setPos(x, y)

        # Re-enable geometry change signals
        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

    def _show_handles(self):
        """Show resize handles when selected"""
        debug_print('ui_bbox', f"Showing {len(self.handles)} handles for row_id {self.row_id}")
        for handle_type, handle in self.handles.items():
            handle.setVisible(True)
            debug_print('ui_bbox', f"{handle_type}: visible={handle.isVisible()}, pos={handle.pos()}")

    def _hide_handles(self):
        """Hide resize handles when not selected"""
        debug_print('ui_bbox', f"Hiding handles for row_id {self.row_id}")
        for handle in self.handles.values():
            handle.setVisible(False)

    def itemChange(self, change, value):
        """Handle selection and scene changes"""
        if change == QtWidgets.QGraphicsItem.ItemSelectedChange:
            if value:  # Selected
                self._show_handles()
            else:  # Deselected
                self._hide_handles()
        elif change == QtWidgets.QGraphicsItem.ItemSceneChange:
            if value is None:  # Being removed from scene
                self.handles.clear()
                # Stop any pending OCR timer to prevent callbacks on deleted item
                if hasattr(self, '_ocr_timer'):
                    self._ocr_timer.stop()
                    self._pending_rect = None
        return super().itemChange(change, value)

    def handle_moved(self, handle_type: str, new_pos: QtCore.QPointF):
        """Called when a handle is moved - update bbox geometry"""
        if not self.is_resizing:
            self.is_resizing = True
            self.original_rect = self.rect()

        rect = self.rect()
        x1, y1 = rect.x(), rect.y()
        x2, y2 = rect.right(), rect.bottom()

        # Update bbox based on which handle moved
        if 'left' in handle_type:
            x1 = new_pos.x()
        if 'right' in handle_type:
            x2 = new_pos.x()
        if 'top' in handle_type:
            y1 = new_pos.y()
        if 'bottom' in handle_type:
            y2 = new_pos.y()

        # Ensure minimum size (10x10 pixels)
        if x2 - x1 < 10:
            if 'left' in handle_type:
                x1 = x2 - 10
            else:
                x2 = x1 + 10

        if y2 - y1 < 10:
            if 'top' in handle_type:
                y1 = y2 - 10
            else:
                y2 = y1 + 10

        # Update rectangle
        new_rect = QtCore.QRectF(
            QtCore.QPointF(x1, y1),
            QtCore.QPointF(x2, y2)
        ).normalized()

        self.setRect(new_rect)
        self._update_handle_positions()

    def on_handle_released(self):
        """Called when a handle is released - trigger OCR if bbox changed (debounced)"""
        if self.is_resizing:
            self.is_resizing = False
            new_rect = self.rect()

            # Check if bbox actually changed
            if new_rect != self.original_rect:
                debug_print('ui_bbox', f"Bbox resized for row_id {self.row_id}")
                debug_print('ui_bbox', f"Old: {self.original_rect}")
                debug_print('ui_bbox', f"New: {new_rect}")

                # Store pending update for debounced OCR
                self._pending_rect = new_rect

                # Debounce: Use timer to delay OCR (prevents UI freeze during rapid adjustments)
                if not hasattr(self, '_ocr_timer'):
                    self._ocr_timer = QtCore.QTimer()
                    self._ocr_timer.setSingleShot(True)
                    self._ocr_timer.timeout.connect(self._do_ocr_update)

                self._ocr_timer.stop()  # Cancel any pending OCR
                self._ocr_timer.start(300)  # 300ms debounce delay
            else:
                debug_print('ui_bbox', f"Bbox unchanged, skipping OCR")

    def _do_ocr_update(self):
        """Execute OCR update after debounce delay"""
        # Safety check: only proceed if item is still in scene and has valid workspace
        if not self.scene() or not hasattr(self, 'workspace') or self.workspace is None:
            self._pending_rect = None
            return
        if hasattr(self, '_pending_rect') and self._pending_rect is not None:
            rect = self._pending_rect
            self.workspace.on_bbox_resized(
                self.row_id,
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height()
            )
            self._pending_rect = None

    def mouseReleaseEvent(self, event):
        """When mouse released after resizing, trigger OCR"""
        super().mouseReleaseEvent(event)
        self.on_handle_released()

    def contextMenuEvent(self, event):
        """Show context menu on right-click"""
        # Import here to avoid circular import
        from ui.bbox_context_menu import BBoxContextMenu

        menu_handler = BBoxContextMenu(self.workspace)
        menu_handler.show_context_menu(self, event.screenPos())
        event.accept()


class OCRRegionResizeHandle(QtWidgets.QGraphicsRectItem):
    """Corner/edge handle for resizing OCR regions - dark blue colored"""

    def __init__(self, handle_type: str, parent_item: 'ResizableOCRBBoxItem'):
        """
        Args:
            handle_type: 'top_left', 'top_right', 'bottom_left', 'bottom_right',
                        'top', 'bottom', 'left', 'right'
            parent_item: The resizable OCR bbox this handle belongs to
        """
        # Make edge handles larger and rectangular for easier grabbing
        if handle_type in ['top', 'bottom']:
            # Horizontal edge handles: wide rectangles
            super().__init__(-16, -4, 32, 8)  # 32x8 (wide)
        elif handle_type in ['left', 'right']:
            # Vertical edge handles: tall rectangles
            super().__init__(-4, -16, 8, 32)  # 8x32 (tall)
        else:
            # Corner handles: small squares
            super().__init__(-4, -4, 8, 8)  # 8x8

        self.handle_type = handle_type
        self.parent_bbox = parent_item

        # Style - dark blue colors for OCR region handles
        if handle_type in ['top', 'bottom', 'left', 'right']:
            self.setBrush(QtGui.QBrush(QtGui.QColor(50, 120, 220)))  # Lighter blue for edges
        else:
            self.setBrush(QtGui.QBrush(QtGui.QColor(0, 100, 200)))  # Darker blue for corners

        self.setPen(QtGui.QPen(QtCore.Qt.white, 1))
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(self._get_cursor())
        self.setZValue(1001)  # Slightly above symbol bbox handles

    def _get_cursor(self) -> QtCore.Qt.CursorShape:
        """Get appropriate cursor for this handle"""
        cursors = {
            'top_left': QtCore.Qt.SizeFDiagCursor,
            'top_right': QtCore.Qt.SizeBDiagCursor,
            'bottom_left': QtCore.Qt.SizeBDiagCursor,
            'bottom_right': QtCore.Qt.SizeFDiagCursor,
            'top': QtCore.Qt.SizeVerCursor,
            'bottom': QtCore.Qt.SizeVerCursor,
            'left': QtCore.Qt.SizeHorCursor,
            'right': QtCore.Qt.SizeHorCursor,
        }
        return cursors.get(self.handle_type, QtCore.Qt.ArrowCursor)

    def itemChange(self, change, value):
        """Handle position changes"""
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            # Constrain handle movement and update parent bbox
            new_pos = value
            debug_print('ui_bbox', f"OCR Handle {self.handle_type} moved to {new_pos}")
            self.parent_bbox.handle_moved(self.handle_type, new_pos)
            return new_pos
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Notify parent bbox when handle is released to trigger OCR"""
        super().mouseReleaseEvent(event)
        debug_print('ui_bbox', f"OCR Handle {self.handle_type} released - triggering OCR re-run")
        # Trigger OCR on parent bbox
        self.parent_bbox.on_handle_released()


class ResizableOCRBBoxItem(QtWidgets.QGraphicsRectItem):
    """
    Resizable OCR region bounding box with dark blue dashed border.
    When resizing is complete, triggers automatic OCR re-run for the parent symbol.
    """

    def __init__(self, x: float, y: float, w: float, h: float,
                 row_id: int, workspace: 'WorkspaceWidget'):
        super().__init__(x, y, w, h)
        self.row_id = row_id
        self.workspace = workspace
        self.handles = {}
        self.is_resizing = False
        self.original_rect = QtCore.QRectF(x, y, w, h)

        # Make selectable
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

        # Create handles (hidden by default)
        self._create_handles()
        self._update_handle_positions()
        self._hide_handles()

    def _create_handles(self):
        """Create 8 resize handles (4 corners + 4 edges)"""
        handle_types = [
            'top_left', 'top_right', 'bottom_left', 'bottom_right',
            'top', 'bottom', 'left', 'right'
        ]

        for handle_type in handle_types:
            handle = OCRRegionResizeHandle(handle_type, self)
            handle.setParentItem(self)
            self.handles[handle_type] = handle

    def _update_handle_positions(self):
        """Position handles at corners and edges of the bbox"""
        rect = self.rect()
        x1, y1 = rect.x(), rect.y()
        x2, y2 = rect.right(), rect.bottom()
        cx, cy = rect.center().x(), rect.center().y()

        positions = {
            'top_left': (x1, y1),
            'top_right': (x2, y1),
            'bottom_left': (x1, y2),
            'bottom_right': (x2, y2),
            'top': (cx, y1),
            'bottom': (cx, y2),
            'left': (x1, cy),
            'right': (x2, cy),
        }

        # Temporarily disable geometry change signals to prevent recursion
        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, False)

        for handle_type, (x, y) in positions.items():
            self.handles[handle_type].setPos(x, y)

        # Re-enable geometry change signals
        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

    def _show_handles(self):
        """Show resize handles when selected"""
        print(f" Showing OCR region handles for row_id {self.row_id}")
        for handle_type, handle in self.handles.items():
            handle.setVisible(True)
            print(f"{handle_type}: visible={handle.isVisible()}, pos={handle.pos()}")

    def _hide_handles(self):
        """Hide resize handles when not selected"""
        print(f" Hiding OCR region handles for row_id {self.row_id}")
        for handle in self.handles.values():
            handle.setVisible(False)

    def itemChange(self, change, value):
        """Handle selection and scene changes"""
        if change == QtWidgets.QGraphicsItem.ItemSelectedChange:
            if value:  # Selected
                self._show_handles()
            else:  # Deselected
                self._hide_handles()
        elif change == QtWidgets.QGraphicsItem.ItemSceneChange:
            if value is None:  # Being removed from scene
                self.handles.clear()
        return super().itemChange(change, value)

    def handle_moved(self, handle_type: str, new_pos: QtCore.QPointF):
        """Called when a handle is moved - update bbox geometry"""
        if not self.is_resizing:
            self.is_resizing = True
            self.original_rect = self.rect()
            self.workspace.cancel_pending_ocr_resize()

        rect = self.rect()
        x1, y1 = rect.x(), rect.y()
        x2, y2 = rect.right(), rect.bottom()

        # Update bbox based on which handle moved
        if 'left' in handle_type:
            x1 = new_pos.x()
        if 'right' in handle_type:
            x2 = new_pos.x()
        if 'top' in handle_type:
            y1 = new_pos.y()
        if 'bottom' in handle_type:
            y2 = new_pos.y()

        # Ensure minimum size (10x10 pixels)
        if x2 - x1 < 10:
            if 'left' in handle_type:
                x1 = x2 - 10
            else:
                x2 = x1 + 10

        if y2 - y1 < 10:
            if 'top' in handle_type:
                y1 = y2 - 10
            else:
                y2 = y1 + 10

        # Update rectangle
        new_rect = QtCore.QRectF(
            QtCore.QPointF(x1, y1),
            QtCore.QPointF(x2, y2)
        ).normalized()

        self.setRect(new_rect)
        self._update_handle_positions()

    def on_handle_released(self):
        """Called when a handle is released - queue OCR re-run with delay"""
        if self.is_resizing:
            self.is_resizing = False
            new_rect = self.rect()

            # Check if bbox actually changed
            if new_rect != self.original_rect:
                print(f" OCR region resized for row_id {self.row_id}")
                print(f"Old: {self.original_rect}")
                print(f"New: {new_rect}")

                # Queue OCR re-run with delay (allows adjusting multiple edges)
                self.workspace.queue_ocr_bbox_resize(
                    self.row_id,
                    new_rect.x(),
                    new_rect.y(),
                    new_rect.width(),
                    new_rect.height()
                )

                # Update original rect so subsequent adjustments are tracked correctly
                self.original_rect = new_rect
            else:
                print(f"OCR region unchanged, skipping OCR re-run")

    def mouseReleaseEvent(self, event):
        """When mouse released after resizing, trigger OCR re-run"""
        super().mouseReleaseEvent(event)
        self.on_handle_released()

    def contextMenuEvent(self, event):
        """Show context menu on right-click"""
        # For now, just accept the event without showing menu
        # Can add OCR-specific menu later
        event.accept()


class ResizablePolygonBBoxItem(QtWidgets.QGraphicsPolygonItem):
    """
    Resizable rotated bounding box (polygon).
    For angular text - allows rotation and resize.
    """

    def __init__(self, polygon: QtGui.QPolygonF, row_id: int,
                 workspace: 'WorkspaceWidget', angle: float = 0.0):
        super().__init__(polygon)
        self.row_id = row_id
        self.workspace = workspace
        self.angle = angle
        self.handles = {}
        self.is_resizing = False
        self.original_polygon = polygon

        # Make selectable
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)

        # Create handles at 4 corners
        self._create_handles()
        self._hide_handles()

    def _create_handles(self):
        """Create 4 corner handles + 4 edge handles for rotated bbox"""
        poly = self.polygon()
        if poly.count() != 4:
            return

        # Create corner handles
        for i in range(4):
            handle = ResizeHandle(f'corner_{i}', self)
            handle.setParentItem(self)
            handle.setPos(poly.at(i))
            self.handles[f'corner_{i}'] = handle

        # Create edge handles (at midpoint of each edge)
        for i in range(4):
            p1 = poly.at(i)
            p2 = poly.at((i + 1) % 4)
            midpoint = QtCore.QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)

            handle = ResizeHandle(f'edge_{i}', self)
            handle.setParentItem(self)
            handle.setPos(midpoint)
            self.handles[f'edge_{i}'] = handle

    def _show_handles(self):
        """Show resize handles"""
        for handle in self.handles.values():
            handle.setVisible(True)

    def _hide_handles(self):
        """Hide resize handles"""
        for handle in self.handles.values():
            handle.setVisible(False)

    def itemChange(self, change, value):
        """Handle selection and scene changes"""
        if change == QtWidgets.QGraphicsItem.ItemSelectedChange:
            if value:
                self._show_handles()
            else:
                self._hide_handles()
        elif change == QtWidgets.QGraphicsItem.ItemSceneChange:
            if value is None:  # Being removed from scene
                self.handles.clear()
                # Stop any pending OCR timer to prevent callbacks on deleted item
                if hasattr(self, '_ocr_timer'):
                    self._ocr_timer.stop()
                    self._pending_polygon = None
        return super().itemChange(change, value)

    def handle_moved(self, handle_type: str, new_pos: QtCore.QPointF):
        """Update polygon when handle moves"""
        if not self.is_resizing:
            self.is_resizing = True
            self.original_polygon = self.polygon()

        poly = self.polygon()
        handle_idx = int(handle_type.split('_')[1])

        if handle_type.startswith('corner_'):
            # Move single corner
            poly.replace(handle_idx, new_pos)
        elif handle_type.startswith('edge_'):
            # Move entire edge (both corners of that edge)
            # edge_0 is between corner_0 and corner_1, etc.
            corner1_idx = handle_idx
            corner2_idx = (handle_idx + 1) % 4

            # Calculate offset from old midpoint to new position
            old_p1 = poly.at(corner1_idx)
            old_p2 = poly.at(corner2_idx)
            old_midpoint = QtCore.QPointF((old_p1.x() + old_p2.x()) / 2,
                                          (old_p1.y() + old_p2.y()) / 2)
            offset = new_pos - old_midpoint

            # Move both corners by this offset
            poly.replace(corner1_idx, old_p1 + offset)
            poly.replace(corner2_idx, old_p2 + offset)

        self.setPolygon(poly)

        # Update all handle positions - temporarily disable geometry signals to prevent recursion
        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, False)

        # Update corner handles
        for i in range(4):
            handle_name = f'corner_{i}'
            if handle_name in self.handles:
                self.handles[handle_name].setPos(poly.at(i))

        # Update edge handles (at midpoint of each edge)
        for i in range(4):
            p1 = poly.at(i)
            p2 = poly.at((i + 1) % 4)
            midpoint = QtCore.QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            handle_name = f'edge_{i}'
            if handle_name in self.handles:
                self.handles[handle_name].setPos(midpoint)

        for handle in self.handles.values():
            handle.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)

    def on_handle_released(self):
        """Called when a handle is released - trigger OCR if polygon changed (debounced)"""
        if self.is_resizing:
            self.is_resizing = False
            new_poly = self.polygon()

            if new_poly != self.original_polygon:
                debug_print('ui_bbox', f"Rotated bbox resized for row_id {self.row_id}")

                # Store pending update for debounced OCR
                self._pending_polygon = new_poly

                # Debounce: Use timer to delay OCR (prevents UI freeze during rapid adjustments)
                if not hasattr(self, '_ocr_timer'):
                    self._ocr_timer = QtCore.QTimer()
                    self._ocr_timer.setSingleShot(True)
                    self._ocr_timer.timeout.connect(self._do_ocr_update)

                self._ocr_timer.stop()  # Cancel any pending OCR
                self._ocr_timer.start(300)  # 300ms debounce delay
            else:
                debug_print('ui_bbox', f"Polygon unchanged, skipping OCR")

    def _do_ocr_update(self):
        """Execute OCR update after debounce delay"""
        # Safety check: only proceed if item is still in scene and has valid workspace
        if not self.scene() or not hasattr(self, 'workspace') or self.workspace is None:
            self._pending_polygon = None
            return
        if hasattr(self, '_pending_polygon') and self._pending_polygon is not None:
            new_poly = self._pending_polygon

            # Get actual polygon points (4 corners)
            poly_points = [(new_poly.at(i).x(), new_poly.at(i).y()) for i in range(4)]

            # Get bounding rect of polygon
            rect = new_poly.boundingRect()

            # Trigger OCR update with actual polygon points
            self.workspace.on_bbox_resized(
                self.row_id,
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height(),
                is_rotated=True,
                angle=self.angle,
                poly_points=poly_points
            )
            self._pending_polygon = None

    def mouseReleaseEvent(self, event):
        """Trigger OCR when done resizing"""
        super().mouseReleaseEvent(event)
        self.on_handle_released()

    def contextMenuEvent(self, event):
        """Show context menu on right-click"""
        # Import here to avoid circular import
        from ui.bbox_context_menu import BBoxContextMenu

        menu_handler = BBoxContextMenu(self.workspace)
        menu_handler.show_context_menu(self, event.screenPos())
        event.accept()
