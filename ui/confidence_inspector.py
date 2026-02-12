# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Confidence Inspector Dialog
Shows a detailed list of all detections with confidence scores
Highlights low-confidence items and links to UI elements
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Dict, Optional, List, TYPE_CHECKING
import pandas as pd
from utils.dpi_utils import get_adaptive_window_size, center_window

if TYPE_CHECKING:
    from ui.workspace_widget import WorkspaceWidget


class ConfidenceInspectorDialog(QtWidgets.QDialog):
    """
    Dialog that displays all detections with their confidence scores
    in a sortable, filterable table. Highlights low-confidence items
    and allows jumping to elements in the main UI.
    """

    def __init__(self, workspace: 'WorkspaceWidget', parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.df_all = workspace.df_all.copy()

        self.setWindowTitle(f"Confidence Inspector - {workspace.layout_name}")

        # Adaptive sizing for different DPI settings
        w, h = get_adaptive_window_size(1200, 800, max_screen_pct=0.85)
        self.resize(w, h)
        center_window(self)

        # Set window flags for independent window
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )

        self._build_ui()
        self._populate_data()
        self._apply_theme()

    def _apply_theme(self):
        """Apply the parent's theme to this dialog"""
        try:
            if hasattr(self.workspace, '_get_theme_colors'):
                normal_color, highlight_color, hover_color, text_color, bg_color = self.workspace._get_theme_colors()

                # Apply to dialog
                palette = self.palette()
                palette.setColor(QtGui.QPalette.Window, bg_color)
                palette.setColor(QtGui.QPalette.WindowText, text_color)
                palette.setColor(QtGui.QPalette.Base, bg_color)
                palette.setColor(QtGui.QPalette.Text, text_color)
                palette.setColor(QtGui.QPalette.AlternateBase, bg_color)

                self.setPalette(palette)
                self.table.setPalette(palette)
        except Exception as e:
            # If theme application fails, just continue
            pass

    def _build_ui(self):
        """Build the UI"""
        layout = QtWidgets.QVBoxLayout(self)

        # ========================================================================
        # HEADER: Statistics Section
        # ========================================================================
        stats_group = QtWidgets.QGroupBox(" Confidence Statistics")
        stats_layout = QtWidgets.QGridLayout(stats_group)

        # Calculate statistics
        stats = self._calculate_statistics()

        # Row 0: Total detections
        stats_layout.addWidget(QtWidgets.QLabel("Total Detections:"), 0, 0)
        total_label = QtWidgets.QLabel(str(stats['total']))
        total_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        stats_layout.addWidget(total_label, 0, 1)

        # Row 1: Average confidence
        stats_layout.addWidget(QtWidgets.QLabel("Average Confidence:"), 1, 0)
        avg_label = QtWidgets.QLabel(f"{stats['average']:.1%}")
        avg_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        stats_layout.addWidget(avg_label, 1, 1)

        # High confidence (≥90%)
        stats_layout.addWidget(QtWidgets.QLabel("High (≥90%):"), 0, 2)
        high_label = QtWidgets.QLabel(f"{stats['high']} ({stats['high_pct']:.1%})")
        high_label.setStyleSheet("color: #00aa00; font-weight: bold;")
        stats_layout.addWidget(high_label, 0, 3)

        # Medium confidence (60-90%)
        stats_layout.addWidget(QtWidgets.QLabel("Medium (60-90%):"), 1, 2)
        med_label = QtWidgets.QLabel(f"{stats['medium']} ({stats['medium_pct']:.1%})")
        med_label.setStyleSheet("color: #cc8800; font-weight: bold;")
        stats_layout.addWidget(med_label, 1, 3)

        # Low confidence (<60%)
        stats_layout.addWidget(QtWidgets.QLabel(" Low (<60%):"), 0, 4)
        low_label = QtWidgets.QLabel(f"{stats['low']} ({stats['low_pct']:.1%})")
        low_label.setStyleSheet("color: #cc0000; font-weight: bold; font-size: 12pt;")
        stats_layout.addWidget(low_label, 0, 5)

        # Very low confidence (<40%)
        if stats['very_low'] > 0:
            stats_layout.addWidget(QtWidgets.QLabel(" Very Low (<40%):"), 1, 4)
            vlow_label = QtWidgets.QLabel(f"{stats['very_low']} ({stats['very_low_pct']:.1%})")
            vlow_label.setStyleSheet("color: #ff0000; font-weight: bold; font-size: 12pt;")
            stats_layout.addWidget(vlow_label, 1, 5)

        layout.addWidget(stats_group)

        # ========================================================================
        # FILTER CONTROLS
        # ========================================================================
        filter_group = QtWidgets.QGroupBox(" Filters")
        filter_layout = QtWidgets.QHBoxLayout(filter_group)

        # Class filter
        filter_layout.addWidget(QtWidgets.QLabel("Class:"))
        self.class_filter = QtWidgets.QComboBox()
        self.class_filter.addItem("All Classes")
        classes = sorted(self.df_all['cls'].dropna().unique()) if 'cls' in self.df_all.columns else []
        self.class_filter.addItems(classes)
        self.class_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.class_filter)

        # Confidence range filter
        filter_layout.addWidget(QtWidgets.QLabel("Confidence:"))
        self.conf_filter = QtWidgets.QComboBox()
        self.conf_filter.addItems([
            "All",
            "Low (<60%)",
            "Very Low (<40%)",
            "Medium (60-90%)",
            "High (≥90%)"
        ])
        self.conf_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.conf_filter)

        # Page filter
        filter_layout.addWidget(QtWidgets.QLabel("Page:"))
        self.page_filter = QtWidgets.QComboBox()
        self.page_filter.addItem("All Pages")
        pages = sorted(self.df_all['page'].dropna().unique())
        self.page_filter.addItems([str(int(p)) for p in pages])
        self.page_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.page_filter)

        # Text search
        filter_layout.addWidget(QtWidgets.QLabel("Search:"))
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search text...")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input)

        # Clear filters button
        btn_clear = QtWidgets.QPushButton("Clear Filters")
        btn_clear.clicked.connect(self._clear_filters)
        filter_layout.addWidget(btn_clear)

        layout.addWidget(filter_group)

        # ========================================================================
        # TABLE
        # ========================================================================
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Row ID", "Class", "Text/Label", "Confidence", "Page", "Coord Text", "Coord Value"
        ])

        # Set column widths
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 120)

        # Table settings
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)  # Use existing theme background
        self.table.horizontalHeader().setStretchLastSection(True)

        # Connect double-click to jump to element
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        layout.addWidget(self.table)

        # ========================================================================
        # BUTTONS
        # ========================================================================
        button_layout = QtWidgets.QHBoxLayout()

        # Export button
        btn_export = QtWidgets.QPushButton(" Export to CSV")
        btn_export.clicked.connect(self._export_to_csv)
        button_layout.addWidget(btn_export)

        button_layout.addStretch()

        # Info label
        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("color: #666; font-style: italic;")
        button_layout.addWidget(self.info_label)

        button_layout.addStretch()

        # Close button
        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        button_layout.addWidget(btn_close)

        layout.addLayout(button_layout)

    def _calculate_statistics(self) -> Dict:
        """Calculate confidence statistics"""
        df = self.df_all.copy()

        # Filter out rows without confidence
        df = df[df['conf'].notna()]

        total = len(df)
        if total == 0:
            return {
                'total': 0, 'average': 0.0,
                'high': 0, 'high_pct': 0.0,
                'medium': 0, 'medium_pct': 0.0,
                'low': 0, 'low_pct': 0.0,
                'very_low': 0, 'very_low_pct': 0.0
            }

        average = df['conf'].mean()

        high = len(df[df['conf'] >= 0.9])
        medium = len(df[(df['conf'] >= 0.6) & (df['conf'] < 0.9)])
        low = len(df[df['conf'] < 0.6])
        very_low = len(df[df['conf'] < 0.4])

        return {
            'total': total,
            'average': average,
            'high': high,
            'high_pct': high / total if total > 0 else 0,
            'medium': medium,
            'medium_pct': medium / total if total > 0 else 0,
            'low': low,
            'low_pct': low / total if total > 0 else 0,
            'very_low': very_low,
            'very_low_pct': very_low / total if total > 0 else 0
        }

    def _populate_data(self):
        """Populate the table with detection data"""
        df = self.df_all.copy()

        # Filter out rows without confidence
        df = df[df['conf'].notna()]

        # Sort by confidence (lowest first) to highlight problematic detections
        df = df.sort_values('conf', ascending=True)

        self.table.setSortingEnabled(False)  # Disable during population
        self.table.setRowCount(len(df))

        for row_idx, (_, row) in enumerate(df.iterrows()):
            # Row ID
            row_id_item = QtWidgets.QTableWidgetItem(str(int(row['row_id'])))
            row_id_item.setData(QtCore.Qt.UserRole, int(row['row_id']))  # Store for filtering
            self.table.setItem(row_idx, 0, row_id_item)

            # Class
            cls_item = QtWidgets.QTableWidgetItem(str(row.get('cls', '')))
            self.table.setItem(row_idx, 1, cls_item)

            # Text/Label
            text = str(row.get('anchor_text', ''))
            if not text.strip():
                text = str(row.get('coord_text', ''))
            text_item = QtWidgets.QTableWidgetItem(text)
            self.table.setItem(row_idx, 2, text_item)

            # Confidence (color-coded and sortable)
            conf = float(row['conf'])
            conf_item = QtWidgets.QTableWidgetItem(f"{conf:.2%}")
            conf_item.setData(QtCore.Qt.UserRole, conf)  # Store numeric value for sorting

            # Color-code by confidence
            if conf < 0.4:
                # Very low - red background
                conf_item.setBackground(QtGui.QColor(255, 100, 100))
                conf_item.setForeground(QtGui.QColor(255, 255, 255))
                conf_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            elif conf < 0.6:
                # Low - orange background
                conf_item.setBackground(QtGui.QColor(255, 180, 100))
                conf_item.setForeground(QtGui.QColor(0, 0, 0))
                conf_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            elif conf < 0.9:
                # Medium - yellow background
                conf_item.setBackground(QtGui.QColor(255, 255, 150))
                conf_item.setForeground(QtGui.QColor(0, 0, 0))
            else:
                # High - green background
                conf_item.setBackground(QtGui.QColor(150, 255, 150))
                conf_item.setForeground(QtGui.QColor(0, 0, 0))

            self.table.setItem(row_idx, 3, conf_item)

            # Page
            page_item = QtWidgets.QTableWidgetItem(str(int(row.get('page', 1))))
            page_item.setData(QtCore.Qt.UserRole, int(row.get('page', 1)))
            self.table.setItem(row_idx, 4, page_item)

            # Coord Text
            coord_text_item = QtWidgets.QTableWidgetItem(str(row.get('coord_text', '')))
            self.table.setItem(row_idx, 5, coord_text_item)

            # Coord Value
            coord_val = row.get('coord_value')
            coord_val_str = f"{coord_val:.4f}" if pd.notna(coord_val) else ""
            coord_val_item = QtWidgets.QTableWidgetItem(coord_val_str)
            if pd.notna(coord_val):
                coord_val_item.setData(QtCore.Qt.UserRole, float(coord_val))
            self.table.setItem(row_idx, 6, coord_val_item)

        self.table.setSortingEnabled(True)  # Re-enable sorting

        # Sort by confidence (column 3) ascending by default
        self.table.sortItems(3, QtCore.Qt.AscendingOrder)

        self._update_info_label(len(df), len(df))

    def _apply_filters(self):
        """Apply filters to the table"""
        class_filter = self.class_filter.currentText()
        conf_filter = self.conf_filter.currentText()
        page_filter = self.page_filter.currentText()
        search_text = self.search_input.text().lower()

        total_rows = self.table.rowCount()
        visible_count = 0

        for row in range(total_rows):
            show = True

            # Class filter
            if class_filter != "All Classes":
                cls_item = self.table.item(row, 1)
                if not cls_item or cls_item.text() != class_filter:
                    show = False

            # Confidence filter
            if show and conf_filter != "All":
                conf_item = self.table.item(row, 3)
                if conf_item:
                    conf = conf_item.data(QtCore.Qt.UserRole)
                    if conf_filter == "Low (<60%)" and conf >= 0.6:
                        show = False
                    elif conf_filter == "Very Low (<40%)" and conf >= 0.4:
                        show = False
                    elif conf_filter == "Medium (60-90%)" and (conf < 0.6 or conf >= 0.9):
                        show = False
                    elif conf_filter == "High (≥90%)" and conf < 0.9:
                        show = False

            # Page filter
            if show and page_filter != "All Pages":
                page_item = self.table.item(row, 4)
                if not page_item or page_item.text() != page_filter:
                    show = False

            # Search filter
            if show and search_text:
                text_item = self.table.item(row, 2)
                coord_item = self.table.item(row, 5)
                text_match = text_item and search_text in text_item.text().lower()
                coord_match = coord_item and search_text in coord_item.text().lower()
                if not (text_match or coord_match):
                    show = False

            self.table.setRowHidden(row, not show)
            if show:
                visible_count += 1

        self._update_info_label(visible_count, total_rows)

    def _clear_filters(self):
        """Clear all filters"""
        self.class_filter.setCurrentIndex(0)
        self.conf_filter.setCurrentIndex(0)
        self.page_filter.setCurrentIndex(0)
        self.search_input.clear()

    def _update_info_label(self, visible: int, total: int):
        """Update the info label"""
        if visible == total:
            self.info_label.setText(f"Showing {total} detection(s)")
        else:
            self.info_label.setText(f"Showing {visible} of {total} detection(s)")

    def _on_row_double_clicked(self, row: int, column: int):
        """Handle double-click on a table row - jump to element in UI"""
        row_id_item = self.table.item(row, 0)
        page_item = self.table.item(row, 4)

        if not row_id_item or not page_item:
            return

        row_id = row_id_item.data(QtCore.Qt.UserRole)
        page = page_item.data(QtCore.Qt.UserRole)

        # Switch to the correct page in the workspace
        if self.workspace.current_page != page:
            self.workspace.page_spin.setValue(page)

        # Highlight in graphics view
        self.workspace.highlight_row_graphics(row_id, highlight=True, hover=False)

        # Select in tree view
        if hasattr(self.workspace, 'tree') and self.workspace.tree:
            tree_item = self.workspace.row_id_to_tree_item.get(row_id)
            if tree_item:
                self.workspace.tree.clearSelection()
                tree_item.setSelected(True)
                self.workspace.tree.scrollToItem(tree_item)

        # Flash a message
        self.workspace._set_status(f"Jumped to Row ID {row_id} on Page {page}")

        # Optionally, you can minimize this dialog or keep it open
        # self.showMinimized()

    def _export_to_csv(self):
        """Export the current (filtered) table to CSV"""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Confidence Report",
            "confidence_report.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if not filename:
            return

        try:
            import csv

            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                headers = [
                    self.table.horizontalHeaderItem(i).text()
                    for i in range(self.table.columnCount())
                ]
                writer.writerow(headers)

                # Data (only visible rows)
                for row in range(self.table.rowCount()):
                    if not self.table.isRowHidden(row):
                        row_data = [
                            self.table.item(row, col).text() if self.table.item(row, col) else ''
                            for col in range(self.table.columnCount())
                        ]
                        writer.writerow(row_data)

            QtWidgets.QMessageBox.information(
                self,
                "Export Successful",
                f"Confidence report exported to:\n{filename}"
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export report:\n{str(e)}"
            )
