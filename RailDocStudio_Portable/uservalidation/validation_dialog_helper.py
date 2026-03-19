# validation_dialog_helper.py
"""
Helper to enhance your existing validation_dialog2.py with jump-to-detection

Add this to your AuditingWindow to enable "jump to detection" feature
when user double-clicks on YOLO issues.
"""

from PyQt5 import QtWidgets, QtCore
from typing import Optional, Tuple
from uservalidation.validation_dialog2 import EnhancedValidationResultsDialog
from uservalidation.data_validator2 import ValidationResult, ValidationIssue


class ValidationDialogWithJump(EnhancedValidationResultsDialog):
    """
    Enhanced validation dialog that can jump to detections.
    
    Extends your existing dialog with:
    - Double-click to jump to detection
    - Highlight detection in image viewer
    - Scroll to row in tree view
    """
    
    # Signal emitted when user wants to jump to a detection
    jump_to_detection = QtCore.pyqtSignal(int, tuple)  # row_id, (x, y) position
    
    def __init__(self, result: ValidationResult, parent=None):
        super().__init__(result, parent)
        
        # Connect double-click on all tables
        self._connect_jump_signals()
    
    def _connect_jump_signals(self):
        """Connect double-click to jump functionality"""
        tables = [
            self.all_issues_table,
            self.correctable_table,
            self.errors_table,
            self.warnings_table,
            self.info_table
        ]
        
        for table in tables:
            table.doubleClicked.connect(self._on_issue_double_clicked)
    
    def _on_issue_double_clicked(self, index):
        """Handle double-click on issue - jump to detection"""
        # Get the table
        table = self.sender()
        row = index.row()
        
        # Find the issue for this row
        issue = self._get_issue_for_row(table, row)
        
        if issue and issue.context.get('can_jump'):
            # Get position from context
            position = issue.context.get('position')
            
            if position and issue.row_id >= 0:
                # Emit signal to jump
                self.jump_to_detection.emit(issue.row_id, position)
                
                # Show feedback
                QtWidgets.QMessageBox.information(
                    self,
                    "Sprung zur Erkennung",
                    f"Springe zu Zeile {issue.row_id} bei Position ({position[0]:.0f}, {position[1]:.0f})",
                    QtWidgets.QMessageBox.Ok
                )
    
    def _get_issue_for_row(self, table, row) -> Optional[ValidationIssue]:
        """Get the ValidationIssue for a table row"""
        # The row index corresponds to the issue index in the result
        # This is a simple implementation - adjust based on your table structure
        
        if table == self.all_issues_table:
            if row < len(self.result.issues):
                return self.result.issues[row]
        
        elif table == self.errors_table:
            errors = [i for i in self.result.issues if i.severity.lower() == 'error']
            if row < len(errors):
                return errors[row]
        
        elif table == self.warnings_table:
            warnings = [i for i in self.result.issues if i.severity.lower() == 'warning']
            if row < len(warnings):
                return warnings[row]
        
        return None


# ============================================================================
# INTEGRATION WITH YOUR AUDITINGWINDOW
# ============================================================================

def integrate_jump_functionality():
    """
    Example integration into your AuditingWindow.
    
    Add this to your AuditingWindow class:
    """
    example_code = '''
# In your AuditingWindow class:

def _run_validation(self):
    """Run validation with jump-to-detection support."""
    workspace = self.get_current_workspace()
    if not workspace or workspace.df_all.empty:
        return
    
    # Run validation
    from yolo_quality_checker import validate_with_yolo_quality
    from validation_dialog_helper import ValidationDialogWithJump
    
    result = validate_with_yolo_quality(workspace.df_all)
    
    # Show enhanced dialog
    dialog = ValidationDialogWithJump(result, self)
    
    # Connect jump signal
    dialog.jump_to_detection.connect(self._jump_to_detection)
    
    # Connect corrections signal (if you want auto-corrections)
    dialog.corrections_accepted.connect(self._apply_corrections)
    
    dialog.exec_()

def _jump_to_detection(self, row_id: int, position: tuple):
    """
    Jump to a specific detection in the view.
    
    Args:
        row_id: The row_id in df_all
        position: (x, y) coordinates
    """
    workspace = self.get_current_workspace()
    if not workspace:
        return
    
    # 1. Select row in tree view
    self._select_row_in_tree(row_id)
    
    # 2. Highlight in image viewer (if you have one)
    if hasattr(self, 'image_viewer'):
        self._highlight_detection(position)
    
    # 3. Scroll to make visible
    if hasattr(workspace, 'tree'):
        workspace.tree.scrollToItem(workspace.tree.currentItem())

def _select_row_in_tree(self, row_id: int):
    """Select a row in the tree view by row_id."""
    workspace = self.get_current_workspace()
    if not workspace or not hasattr(workspace, 'tree'):
        return
    
    # Find the tree item with this row_id
    for i in range(workspace.tree.topLevelItemCount()):
        item = workspace.tree.topLevelItem(i)
        
        # Assuming you store row_id in item data
        item_row_id = item.data(0, QtCore.Qt.UserRole)
        
        if item_row_id == row_id:
            workspace.tree.setCurrentItem(item)
            workspace.tree.scrollToItem(item)
            
            # Highlight it
            item.setBackground(0, QtGui.QColor(255, 255, 200))  # Yellow highlight
            
            # Flash effect (optional)
            QtCore.QTimer.singleShot(1000, lambda: item.setBackground(0, QtGui.QColor(255, 255, 255)))
            
            break

def _highlight_detection(self, position: tuple):
    """
    Highlight a detection in the image viewer.
    
    This assumes you have an image viewer widget.
    Adjust based on your actual image viewer implementation.
    """
    x, y = position
    
    # If you have a QGraphicsView or similar:
    # self.image_viewer.centerOn(x, y)
    # self.image_viewer.highlight_bbox(x, y, 100, 80)  # Adjust size
    
    # Or if you have a custom viewer:
    # self.image_viewer.scroll_to(x, y)
    # self.image_viewer.draw_highlight_circle(x, y, radius=50)
    
    pass  # Implement based on your viewer
    '''
    
    return example_code


# ============================================================================
# VISUAL HIGHLIGHTING HELPERS
# ============================================================================

class DetectionHighlighter:
    """
    Helper class for highlighting detections in image viewers.
    
    Use this if you have a QGraphicsView-based image viewer.
    """
    
    @staticmethod
    def create_highlight_circle(x: float, y: float, radius: float = 50):
        """Create a highlight circle for QGraphicsScene"""
        from PyQt5.QtWidgets import QGraphicsEllipseItem
        from PyQt5.QtGui import QPen, QColor
        from PyQt5.QtCore import Qt
        
        circle = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
        
        # Red highlight with transparency
        pen = QPen(QColor(255, 0, 0, 200))
        pen.setWidth(3)
        circle.setPen(pen)
        
        # No fill
        circle.setBrush(Qt.NoBrush)
        
        return circle
    
    @staticmethod
    def create_highlight_rect(x: float, y: float, w: float, h: float):
        """Create a highlight rectangle for QGraphicsScene"""
        from PyQt5.QtWidgets import QGraphicsRectItem
        from PyQt5.QtGui import QPen, QBrush, QColor
        from PyQt5.QtCore import Qt
        
        rect = QGraphicsRectItem(x - w/2, y - h/2, w, h)
        
        # Red highlight with transparency
        pen = QPen(QColor(255, 0, 0, 200))
        pen.setWidth(3)
        rect.setPen(pen)
        
        # Semi-transparent yellow fill
        brush = QBrush(QColor(255, 255, 0, 50))
        rect.setBrush(brush)
        
        return rect
    
    @staticmethod
    def flash_item(item, duration_ms: int = 1000):
        """Make an item flash for a duration"""
        from PyQt5.QtCore import QTimer
        from PyQt5.QtGui import QPen, QColor

        original_pen = item.pen()
        
        # Flash red
        flash_pen = QPen(original_pen)
        flash_pen.setColor(QColor(255, 0, 0, 255))
        flash_pen.setWidth(5)
        item.setPen(flash_pen)
        
        # Restore after duration
        QTimer.singleShot(duration_ms, lambda: item.setPen(original_pen))


# ============================================================================
# SIMPLE INTEGRATION EXAMPLE
# ============================================================================

if __name__ == '__main__':
    print("Validation Dialog Helper - Integration Example\n")
    print(integrate_jump_functionality())
