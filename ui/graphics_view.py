from PyQt5 import QtCore, QtGui, QtWidgets
from typing import List, Dict, Tuple, Optional, Any
import math

class InteractiveGraphicsView(QtWidgets.QGraphicsView):
    zoomChanged = QtCore.pyqtSignal(float)
    rect_drawn = QtCore.pyqtSignal(QtCore.QRectF)
    rotated_rect_drawn = QtCore.pyqtSignal(QtCore.QRectF, float)  # rect, angle
    
    def __init__(self, parent_widget: Any, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_widget = parent_widget
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self._zoom = 1.0
        self.setToolTip("Strg+Mausrad: Zoom • Umschalt+Mausrad: Horizontal scrollen • Ziehen: Verschieben")
        
        if hasattr(parent_widget, 'on_pop_out_graphics') and hasattr(parent_widget, 'on_redock_graphics'):
            self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self._show_graphics_context_menu)
        else:
            self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        
        # Drawing mode variables
        self.is_drawing_mode = False
        self.is_rotated_mode = False
        self.start_pos = None
        self.current_pos = None
        self.draw_rect_item = None
        self.draw_poly_item = None
        self.temp_line_items = []
        self.rotation_stage = 0

    def _show_graphics_context_menu(self, pos: QtCore.QPoint):
        menu = QtWidgets.QMenu(self)
        if getattr(self.parent_widget, "graphics_window", None) is None:
            a = menu.addAction("Grafik auskoppeln")
            a.triggered.connect(self.parent_widget.on_pop_out_graphics)
        else:
            a = menu.addAction("Grafik andocken")
            a.triggered.connect(self.parent_widget.on_redock_graphics)
        menu.exec_(self.mapToGlobal(pos))

    def wheelEvent(self, event: QtGui.QWheelEvent):
        mods = QtWidgets.QApplication.keyboardModifiers()
        dy, dx = event.angleDelta().y(), event.angleDelta().x()
        if mods & QtCore.Qt.ControlModifier:
            delta = dy if dy != 0 else dx
            self._apply_zoom(1.25 if delta > 0 else 1/1.25)
            event.accept()
            return
        elif mods & QtCore.Qt.ShiftModifier:
            delta = dy if dy != 0 else dx
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta)
            event.accept()
            return
        super().wheelEvent(event)

    def _apply_zoom(self, factor: float):
        self._zoom *= factor
        self.scale(factor, factor)
        self.zoomChanged.emit(self._zoom)

    def zoom_in(self):
        self._apply_zoom(1.25)

    def zoom_out(self):
        self._apply_zoom(1/1.25)

    def fit_to_view(self):
        r = self.sceneRect()
        if not r.isNull():
            self.setTransform(QtGui.QTransform())
            self._zoom = 1.0
            self.fitInView(r.marginsAdded(QtCore.QMarginsF(2, 2, 2, 2)), QtCore.Qt.KeepAspectRatio)

    def actual_size(self):
        self.setTransform(QtGui.QTransform())
        self._zoom = 1.0
        self.centerOn(self.sceneRect().center())

    def toggle_drawing_mode(self, enabled: bool, rotated: bool = False):
        self.is_drawing_mode = enabled
        self.is_rotated_mode = rotated
        
        if self.is_drawing_mode:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.setCursor(QtCore.Qt.CrossCursor)
            self.rotation_stage = 0
            self.start_pos = None
            self.current_pos = None
        else:
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.start_pos = None
            self.current_pos = None
            self.rotation_stage = 0
            
            if self.draw_rect_item and self.draw_rect_item.scene():
                self.scene().removeItem(self.draw_rect_item)
                self.draw_rect_item = None
            
            if self.draw_poly_item and self.draw_poly_item.scene():
                self.scene().removeItem(self.draw_poly_item)
                self.draw_poly_item = None
            
            for item in self.temp_line_items:
                if item.scene():
                    self.scene().removeItem(item)
            self.temp_line_items.clear()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        # ✅ CHECK: Manual linking mode
        if hasattr(self.parent_widget, 'is_manual_linking_mode') and self.parent_widget.is_manual_linking_mode:
            if event.button() == QtCore.Qt.LeftButton:
                self.parent_widget.on_linking_click(self.mapToScene(event.pos()))
                event.accept()
                return
        
        # ✅ CHECK: Drawing mode (existing)
        if not self.is_drawing_mode:
            super().mousePressEvent(event)
            return
            if not self.is_drawing_mode:
                super().mousePressEvent(event)
                return

        if event.button() == QtCore.Qt.LeftButton:
            pos = self.mapToScene(event.pos())
            
            if self.is_rotated_mode:
                if self.rotation_stage == 0:
                    self.start_pos = pos
                    self.rotation_stage = 1
                    
                    marker = self.scene().addEllipse(
                        pos.x() - 3, pos.y() - 3, 6, 6,
                        QtGui.QPen(QtCore.Qt.red, 2),
                        QtGui.QBrush(QtCore.Qt.red)
                    )
                    self.temp_line_items.append(marker)
                    
                elif self.rotation_stage == 1:
                    self.current_pos = pos
                    self.rotation_stage = 2
                    
                    marker = self.scene().addEllipse(
                        pos.x() - 3, pos.y() - 3, 6, 6,
                        QtGui.QPen(QtCore.Qt.red, 2),
                        QtGui.QBrush(QtCore.Qt.red)
                    )
                    self.temp_line_items.append(marker)
                    self._update_rotated_rectangle(pos)
            else:
                self.start_pos = pos
                
                if self.draw_rect_item and self.draw_rect_item.scene():
                    self.scene().removeItem(self.draw_rect_item)
                
                pen = QtGui.QPen(QtCore.Qt.red, 3, QtCore.Qt.SolidLine)
                brush = QtGui.QBrush(QtGui.QColor(255, 0, 0, 80))
                
                self.draw_rect_item = QtWidgets.QGraphicsRectItem()
                self.draw_rect_item.setPen(pen)
                self.draw_rect_item.setBrush(brush)
                self.scene().addItem(self.draw_rect_item)
            
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if not self.is_drawing_mode:
            super().mouseMoveEvent(event)
            return
        
        pos = self.mapToScene(event.pos())
        
        if self.is_rotated_mode and self.rotation_stage == 2:
            self._update_rotated_rectangle(pos)
            event.accept()
        elif not self.is_rotated_mode:
            if event.buttons() & QtCore.Qt.LeftButton and self.start_pos and self.draw_rect_item:
                current_pos = pos
                rect = QtCore.QRectF(self.start_pos, current_pos).normalized()
                self.draw_rect_item.setRect(rect)
                event.accept()
        else:
            super().mouseMoveEvent(event)

    def _update_rotated_rectangle(self, mouse_pos: QtCore.QPointF):
        """Update the visual rotated rectangle - height adjusts in mouse direction"""
        if not self.start_pos or not self.current_pos:
            return
        
        # Remove old items
        if self.draw_poly_item and self.draw_poly_item.scene():
            self.scene().removeItem(self.draw_poly_item)
        
        # Remove old guide lines (keep only corner markers)
        items_to_remove = [item for item in self.temp_line_items if isinstance(item, QtWidgets.QGraphicsLineItem)]
        for item in items_to_remove:
            if item in self.temp_line_items:
                self.temp_line_items.remove(item)
            if item.scene():
                self.scene().removeItem(item)
        
        # Calculate the diagonal vector
        diagonal_dx = self.current_pos.x() - self.start_pos.x()
        diagonal_dy = self.current_pos.y() - self.start_pos.y()
        diagonal_length = math.sqrt(diagonal_dx**2 + diagonal_dy**2)
        
        if diagonal_length < 1:
            return
        
        # Draw baseline
        baseline = self.scene().addLine(
            self.start_pos.x(), self.start_pos.y(),
            self.current_pos.x(), self.current_pos.y(),
            QtGui.QPen(QtCore.Qt.blue, 2, QtCore.Qt.DashLine)
        )
        self.temp_line_items.append(baseline)
        
        # Calculate signed perpendicular distance
        signed_distance = ((diagonal_dy * (mouse_pos.x() - self.start_pos.x()) - 
                            diagonal_dx * (mouse_pos.y() - self.start_pos.y())) / diagonal_length)
        
        # ✅ FIX: Use signed distance directly (don't take absolute value yet)
        # This preserves the direction information
        height = signed_distance
        if abs(height) < 20:
            height = 20 if height >= 0 else -20  # Minimum height with sign
        
        # Perpendicular unit vector (rotated 90 degrees from diagonal)
        perp_x = -diagonal_dy / diagonal_length
        perp_y = diagonal_dx / diagonal_length
        
        # Calculate 4 corners - baseline is one edge
        corners = [
            QtCore.QPointF(self.start_pos.x(), self.start_pos.y()),
            QtCore.QPointF(self.current_pos.x(), self.current_pos.y()),
            QtCore.QPointF(self.current_pos.x() + height * perp_x,
                        self.current_pos.y() + height * perp_y),
            QtCore.QPointF(self.start_pos.x() + height * perp_x,
                        self.start_pos.y() + height * perp_y),
        ]
        
        # Create polygon
        polygon = QtGui.QPolygonF(corners)
        self.draw_poly_item = QtWidgets.QGraphicsPolygonItem(polygon)
        self.draw_poly_item.setPen(QtGui.QPen(QtCore.Qt.red, 3))
        self.draw_poly_item.setBrush(QtGui.QBrush(QtGui.QColor(255, 0, 0, 80)))
        self.scene().addItem(self.draw_poly_item)
        
        # Add height indicator
        center_x = (self.start_pos.x() + self.current_pos.x()) / 2
        center_y = (self.start_pos.y() + self.current_pos.y()) / 2
        indicator_end_x = center_x + height * perp_x
        indicator_end_y = center_y + height * perp_y
        
        height_indicator = self.scene().addLine(
            center_x, center_y,
            indicator_end_x, indicator_end_y,
            QtGui.QPen(QtCore.Qt.green, 2, QtCore.Qt.DotLine)
        )
        self.temp_line_items.append(height_indicator)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if not self.is_drawing_mode:
            super().mouseReleaseEvent(event)
            return
        
        if self.is_rotated_mode and self.rotation_stage == 2 and event.button() == QtCore.Qt.LeftButton:
            pos = self.mapToScene(event.pos())
            
            # Calculate final parameters
            diagonal_dx = self.current_pos.x() - self.start_pos.x()
            diagonal_dy = self.current_pos.y() - self.start_pos.y()
            diagonal_length = math.sqrt(diagonal_dx**2 + diagonal_dy**2)
            
            if diagonal_length < 10:
                # Rectangle too small, abort
                for item in self.temp_line_items:
                    if item.scene():
                        self.scene().removeItem(item)
                self.temp_line_items.clear()
                
                if self.draw_poly_item and self.draw_poly_item.scene():
                    self.scene().removeItem(self.draw_poly_item)
                    self.draw_poly_item = None
                
                self.rotation_stage = 0
                self.start_pos = None
                self.current_pos = None
                self.parent_widget.on_manual_ocr_toggled(False)
                event.accept()
                return
            
            width = diagonal_length
            
            # Calculate height from perpendicular distance (one-sided)
            signed_distance = ((diagonal_dy * (pos.x() - self.start_pos.x()) - 
                            diagonal_dx * (pos.y() - self.start_pos.y())) / diagonal_length)

            # Use absolute value only for final rectangle
            height = abs(signed_distance)
            if height < 20:
                height = 20
            
            # Calculate angle
            angle = math.degrees(math.atan2(diagonal_dy, diagonal_dx))
            
            # Clean up temporary items
            for item in self.temp_line_items:
                if item.scene():
                    self.scene().removeItem(item)
            self.temp_line_items.clear()
            
            if self.draw_poly_item and self.draw_poly_item.scene():
                self.scene().removeItem(self.draw_poly_item)
                self.draw_poly_item = None
            
            # Calculate center (offset from diagonal center by height/2)
            diagonal_center_x = (self.start_pos.x() + self.current_pos.x()) / 2
            diagonal_center_y = (self.start_pos.y() + self.current_pos.y()) / 2
            
            # Perpendicular direction
            side = 1 if signed_distance >= 0 else -1
            perp_x = -diagonal_dy / diagonal_length * side
            perp_y = diagonal_dx / diagonal_length * side
            
            # Center is offset by half height
            center_x = diagonal_center_x + (height / 2) * perp_x
            center_y = diagonal_center_y + (height / 2) * perp_y
            
            # Create final rectangle
            rect = QtCore.QRectF(0, 0, width, height)
            rect.moveCenter(QtCore.QPointF(center_x, center_y))
            
            # Emit signal
            if width > 10 and height > 10:
                self.rotated_rect_drawn.emit(rect, angle)
            
            # Reset state
            self.rotation_stage = 0
            self.start_pos = None
            self.current_pos = None
            self.parent_widget.on_manual_ocr_toggled(False)
            event.accept()
            
        elif not self.is_rotated_mode:
            # Normal rectangle release
            if self.start_pos and event.button() == QtCore.Qt.LeftButton:
                if not self.draw_rect_item:
                    self.start_pos = None
                    return

                final_rect = self.draw_rect_item.rect()
                
                if self.draw_rect_item.scene():
                    self.scene().removeItem(self.draw_rect_item)
                self.draw_rect_item = None
                self.start_pos = None
                
                if final_rect.width() > 5 and final_rect.height() > 5:
                    self.rect_drawn.emit(final_rect)
                
                self.parent_widget.on_manual_ocr_toggled(False)
                event.accept()
        else:
            super().mouseReleaseEvent(event)