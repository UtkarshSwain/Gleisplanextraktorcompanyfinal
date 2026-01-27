from PyQt5 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.auditing_window import AuditingWindow

class DraggableTabBar(QtWidgets.QTabBar):
    """Custom tab bar that supports drag-to-pop-out"""
    
    # Signal emitted when a tab is dragged out
    tab_detached = QtCore.pyqtSignal(int, QtCore.QPoint)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setAcceptDrops(True)
        self.setElideMode(QtCore.Qt.ElideRight)
        self.setSelectionBehaviorOnRemove(QtWidgets.QTabBar.SelectLeftTab)
        self.setMovable(True)
        
        self.drag_start_pos = None
        self.drag_initiated = False
        self.drag_threshold = 30  # pixels to drag before pop-out
        
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Start tracking drag"""
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.drag_initiated = False
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Detect drag-out gesture"""
        if not (event.buttons() & QtCore.Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        
        if self.drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        
        # Check if dragged beyond threshold
        if not self.drag_initiated:
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            
            if distance > self.drag_threshold:
                tab_index = self.tabAt(self.drag_start_pos)
                
                if tab_index >= 0:
                    # Check if this tab can be detached (not a placeholder)
                    tab_text = self.tabText(tab_index)
                    
                    if not tab_text.startswith("🪟"):  # Not a placeholder
                        self.drag_initiated = True
                        
                        # Emit signal with global position
                        global_pos = self.mapToGlobal(event.pos())
                        self.tab_detached.emit(tab_index, global_pos)
                        
                        # Reset drag state
                        self.drag_start_pos = None
                        return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """Reset drag state"""
        self.drag_start_pos = None
        self.drag_initiated = False
        super().mouseReleaseEvent(event)

class DraggableTabWidget(QtWidgets.QTabWidget):
    """Tab widget with draggable tabs that can be popped out"""
    
    def __init__(self, parent: 'AuditingWindow'):
        super().__init__(parent)
        
        self.parent_window = parent
        
        # Replace default tab bar with custom one
        self.custom_tab_bar = DraggableTabBar(self)
        self.setTabBar(self.custom_tab_bar)
        
        # Connect signals
        self.custom_tab_bar.tab_detached.connect(self._on_tab_detached)
    
    def _on_tab_detached(self, tab_index: int, global_pos: QtCore.QPoint):
        """Handle tab being dragged out"""
        print(f"[TAB_WIDGET] Tab {tab_index} detached at {global_pos}")
        
        # Pop out the workspace
        if hasattr(self.parent_window, 'pop_out_workspace_tab'):
            self.parent_window.pop_out_workspace_tab(tab_index, detach_pos=global_pos)