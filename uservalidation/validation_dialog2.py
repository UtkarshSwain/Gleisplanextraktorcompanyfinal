"""
Enhanced Validation Results Dialog
 NEW: Auto-correction UI with confidence indicators and batch correction
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import List, Dict, Optional
from uservalidation.data_validator2 import ValidationResult, ValidationIssue, EnhancedDataValidator
import csv
import pandas as pd

class EnhancedValidationResultsDialog(QtWidgets.QDialog):
    """
     UPGRADED: Dialog with auto-correction support
    
    NEW FEATURES:
    - Tabbed interface (All Issues, Auto-Corrections, Errors, Warnings)
    - Checkbox selection for corrections
    - Confidence indicators (color-coded)
    - Batch correction application
    - Export validation reports
    """
    
    #  NEW: Signal emitted when user accepts corrections
    corrections_accepted = QtCore.pyqtSignal(list)  # List[ValidationIssue]
    jump_to_detection = QtCore.pyqtSignal(int, tuple)

    #  NEW: Signals to activate manual correction tools directly
    activate_manual_ocr = QtCore.pyqtSignal(str)  # 'horizontal' or 'angular'
    activate_manual_link = QtCore.pyqtSignal()
    activate_bbox_resize = QtCore.pyqtSignal()
    delete_row = QtCore.pyqtSignal(int)  # row_id to delete

    # Signal for jumping to uncertain detection position
    jump_to_position = QtCore.pyqtSignal(tuple)  # (x, y) position to jump to

    def __init__(self, result: ValidationResult, uncertain_detections: List[dict] = None, parent=None):
        super().__init__(parent)
        self.result = result
        self.selected_corrections = []
        self.uncertain_detections = uncertain_detections or []
        
        self.setWindowTitle("Datenprüfung - Ergebnisse")
        self.resize(1400, 900)
        
        # Set window flags
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        
        self._build_ui()
        self._populate_data()
    
    def _build_ui(self):
        """Build the enhanced UI"""
        layout = QtWidgets.QVBoxLayout(self)
        
        # ========================================================================
        # SUMMARY SECTION (Enhanced)
        # ========================================================================
        summary_group = QtWidgets.QGroupBox(" Gefundene Probleme - Übersicht")
        summary_layout = QtWidgets.QGridLayout(summary_group)

        stats = self.result.get_summary()

        # Row 0: Total
        summary_layout.addWidget(QtWidgets.QLabel("Gefundene Probleme:"), 0, 0)
        total_label = QtWidgets.QLabel(str(stats['total_issues']))
        total_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        total_label.setToolTip("Gesamtzahl aller gefundenen Probleme in den Daten")
        summary_layout.addWidget(total_label, 0, 1)

        # Row 1: Errors
        summary_layout.addWidget(QtWidgets.QLabel(" Fehler (schwerwiegend):"), 1, 0)
        error_label = QtWidgets.QLabel(str(stats['errors']))
        error_label.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 12pt;")
        error_label.setToolTip("Schwerwiegende Fehler - sollten korrigiert werden")
        summary_layout.addWidget(error_label, 1, 1)

        # Row 2: Warnings
        summary_layout.addWidget(QtWidgets.QLabel(" Warnungen (prüfen):"), 2, 0)
        warning_label = QtWidgets.QLabel(str(stats['warnings']))
        warning_label.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 12pt;")
        warning_label.setToolTip("Mögliche Probleme - sollten geprüft werden")
        summary_layout.addWidget(warning_label, 2, 1)

        # Row 3: Info
        summary_layout.addWidget(QtWidgets.QLabel(" Hinweise:"), 3, 0)
        info_label = QtWidgets.QLabel(str(stats['info']))
        info_label.setStyleSheet("color: #4444ff; font-size: 12pt;")
        info_label.setToolTip("Informationen zur Datenqualität")
        summary_layout.addWidget(info_label, 3, 1)

        # Add spacer
        summary_layout.setColumnMinimumWidth(1, 80)

        #  Auto-correctable count
        summary_layout.addWidget(QtWidgets.QLabel(" Automatisch behebbar:"), 0, 2)
        auto_label = QtWidgets.QLabel(str(stats['auto_correctable']))
        auto_label.setStyleSheet("color: #44ff44; font-weight: bold; font-size: 14pt;")
        auto_label.setToolTip("Probleme, die automatisch korrigiert werden können")
        summary_layout.addWidget(auto_label, 0, 3)

        #  High confidence fixes
        if stats['high_confidence_fixes'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel("  - Hohe Sicherheit (≥90%):"), 1, 2)
            high_conf_label = QtWidgets.QLabel(str(stats['high_confidence_fixes']))
            high_conf_label.setStyleSheet("color: #00cc00; font-weight: bold;")
            high_conf_label.setToolTip("Korrekturen mit hoher Zuverlässigkeit")
            summary_layout.addWidget(high_conf_label, 1, 3)

        #  Medium confidence fixes
        if stats['medium_confidence_fixes'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel("  - Mittlere Sicherheit (60-90%):"), 2, 2)
            med_conf_label = QtWidgets.QLabel(str(stats['medium_confidence_fixes']))
            med_conf_label.setStyleSheet("color: #ccaa00;")
            med_conf_label.setToolTip("Korrekturen sollten geprüft werden")
            summary_layout.addWidget(med_conf_label, 2, 3)

        #  Corrections applied
        if stats['corrections_applied'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel(" Bereits korrigiert:"), 3, 2)
            applied_label = QtWidgets.QLabel(str(stats['corrections_applied']))
            applied_label.setStyleSheet("color: #44ff44; font-weight: bold;")
            applied_label.setToolTip("Anzahl bereits angewendeter Korrekturen")
            summary_layout.addWidget(applied_label, 3, 3)

        layout.addWidget(summary_group)
        
        # ========================================================================
        # TABBED INTERFACE (New)
        # ========================================================================
        self.tabs = QtWidgets.QTabWidget()
        
        # Tab 1: All Issues
        self.all_issues_table = self._create_issues_table()
        self.tabs.addTab(self.all_issues_table, " Alle Probleme")
        
        #  Tab 2: Auto-Correctable Issues (NEW)
        self.correctable_table = self._create_correctable_table()
        self.tabs.addTab(self.correctable_table, " Auto-Korrekturen")
        
        # Tab 3: Errors Only
        self.errors_table = self._create_issues_table()
        self.tabs.addTab(self.errors_table, " Fehler")
        
        # Tab 4: Warnings Only
        self.warnings_table = self._create_issues_table()
        self.tabs.addTab(self.warnings_table, " Warnungen")
        
        # Tab 5: Info Only
        self.info_table = self._create_issues_table()
        self.tabs.addTab(self.info_table, " Hinweise")

        # Tab 6: Uncertain Detections (NEW)
        self.uncertain_widget = QtWidgets.QWidget()
        self.uncertain_layout = QtWidgets.QVBoxLayout(self.uncertain_widget)
        self._setup_uncertain_tab()
        uncertain_count = len(self.uncertain_detections)
        self.tabs.addTab(self.uncertain_widget, f"🔍 Unsicher ({uncertain_count})")

        layout.addWidget(self.tabs)
        
        # ========================================================================
        # BUTTON SECTION (Enhanced)
        # ========================================================================
        button_layout = QtWidgets.QHBoxLayout()
        # ADD TOGGLE CHECKBOX FOR MISSING DETECTIONS (NEW)
        self.toggle_missing_checkbox = QtWidgets.QCheckBox(" Fehlende Elemente im Plan anzeigen")
        self.toggle_missing_checkbox.setChecked(True)  # Show by default
        self.toggle_missing_checkbox.setToolTip("Zeigt rot markierte Bereiche im Gleisplan, wo möglicherweise Elemente fehlen")
        self.toggle_missing_checkbox.stateChanged.connect(self._on_toggle_missing_detections)
        button_layout.addWidget(self.toggle_missing_checkbox)

        button_layout.addStretch()
        #  NEW: Apply selected corrections button
        self.btn_apply_selected = QtWidgets.QPushButton(" Ausgewählte Korrekturen übernehmen")
        self.btn_apply_selected.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton))
        self.btn_apply_selected.clicked.connect(self.on_apply_selected)
        self.btn_apply_selected.setEnabled(False)
        self.btn_apply_selected.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 8px; }")
        self.btn_apply_selected.setToolTip("Wendet nur die markierten Korrekturen an")
        button_layout.addWidget(self.btn_apply_selected)

        #  NEW: Apply all corrections button
        self.btn_apply_all = QtWidgets.QPushButton(" Alle Korrekturen übernehmen")
        self.btn_apply_all.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.btn_apply_all.clicked.connect(self.on_apply_all)
        self.btn_apply_all.setEnabled(stats['auto_correctable'] > 0)
        self.btn_apply_all.setStyleSheet("QPushButton { background-color: #2196F3; color: white; padding: 8px; }")
        self.btn_apply_all.setToolTip("Wendet alle automatischen Korrekturen auf einmal an")
        button_layout.addWidget(self.btn_apply_all)

        button_layout.addStretch()

        # Export button
        self.btn_export = QtWidgets.QPushButton(" Bericht exportieren (Excel)")
        self.btn_export.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton))
        self.btn_export.setToolTip("Exportiert den Prüfbericht als CSV-Datei für Excel")
        self.btn_export.clicked.connect(self.on_export_report)
        button_layout.addWidget(self.btn_export)
        
        # Close button
        self.btn_close = QtWidgets.QPushButton("Schließen")
        self.btn_close.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton))
        self.btn_close.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)

    def _on_toggle_missing_detections(self, state):
        """Handle toggle of missing detection overlays"""
        show = (state == QtCore.Qt.Checked)
        
        # Emit signal to parent workspace to toggle overlays
        if self.parent() and hasattr(self.parent(), 'toggle_missing_detection_overlays'):
            self.parent().toggle_missing_detection_overlays(show)

    def _create_issues_table(self) -> QtWidgets.QTableWidget:
        """Create standard issues table"""
        table = QtWidgets.QTableWidget()
        table.setColumnCount(9)  #  CHANGED: 8 → 9 (added Korrektur column)
        table.setHorizontalHeaderLabels([
            "Dringlichkeit", "Art", "Typ", "ID", "Feld", "Problem-Beschreibung", "Aktueller Wert", " Zeigen", " Korrektur"
        ])

        # Set column widths
        table.setColumnWidth(0, 80)   # Schwere
        table.setColumnWidth(1, 100)  # Kategorie (OCR/YOLO)
        table.setColumnWidth(2, 120)  # Klasse (signal, coordinate, etc.)
        table.setColumnWidth(3, 60)   # Zeile
        table.setColumnWidth(4, 100)  # Feld
        table.setColumnWidth(5, 300)  # Problem
        table.setColumnWidth(6, 150)  # Aktueller Wert
        table.setColumnWidth(7, 100)  # Zeigen (Jump)
        table.setColumnWidth(8, 200)  # Korrektur (Action buttons)

        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        #  Disable alternating row colors to match dark theme
        table.setAlternatingRowColors(False)

        #  Set dark theme background
        table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                alternate-background-color: #2b2b2b;
                gridline-color: #3d3d3d;
            }
            QTableWidget::item {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #3d5a80;
            }
        """)

        return table
    
    def _create_correctable_table(self) -> QtWidgets.QTableWidget:
        """Create table for auto-correctable issues"""
        table = QtWidgets.QTableWidget()
        table.setColumnCount(8)  #  CHANGED: 7 → 8 (added Action column)
        table.setHorizontalHeaderLabels([
            "", "Art", "ID", "Feld", "Aktueller Wert", "Korrektur-Vorschlag", "Sicherheit", "Aktion"
        ])
        
        # Set column widths
        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 60)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(4, 200)
        table.setColumnWidth(5, 200)
        table.setColumnWidth(6, 100)
        table.setColumnWidth(7, 100)  #  ADDED: Action column
        
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        
        # Connect selection change
        table.itemChanged.connect(self.on_correction_selection_changed)

        return table

    def _setup_uncertain_tab(self):
        """Setup the uncertain detections display tab (read-only)."""
        if not self.uncertain_detections:
            label = QtWidgets.QLabel("Keine unsicheren Erkennungen gefunden.")
            label.setStyleSheet("color: #888888; font-size: 12pt; padding: 20px;")
            self.uncertain_layout.addWidget(label)
            return

        # Instructions
        info = QtWidgets.QLabel(
            "Diese Erkennungen haben niedrige Konfidenz.\n"
            "Klicken Sie 'Zeigen' um zur Position zu springen."
        )
        info.setStyleSheet("color: #aaaaaa; padding: 10px;")
        self.uncertain_layout.addWidget(info)

        # Table for uncertain detections (display only)
        self.uncertain_table = QtWidgets.QTableWidget()
        self.uncertain_table.setColumnCount(5)
        self.uncertain_table.setHorizontalHeaderLabels([
            "Klasse", "Konfidenz", "Position", "Seite", "Zeigen"
        ])
        self.uncertain_table.setRowCount(len(self.uncertain_detections))

        # Set column widths
        self.uncertain_table.setColumnWidth(0, 150)  # Class
        self.uncertain_table.setColumnWidth(1, 100)  # Confidence
        self.uncertain_table.setColumnWidth(2, 150)  # Position
        self.uncertain_table.setColumnWidth(3, 60)   # Page
        self.uncertain_table.setColumnWidth(4, 55)   # Show

        self.uncertain_table.horizontalHeader().setStretchLastSection(True)
        self.uncertain_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.uncertain_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        # Dark theme
        self.uncertain_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                gridline-color: #3d3d3d;
            }
            QTableWidget::item {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #3d5a80;
            }
        """)

        for row, det in enumerate(self.uncertain_detections):
            # Class name
            class_item = QtWidgets.QTableWidgetItem(det.get('name', ''))
            self.uncertain_table.setItem(row, 0, class_item)

            # Confidence (color-coded)
            conf = det.get('conf', 0)
            conf_item = QtWidgets.QTableWidgetItem(f"{conf:.1%}")
            conf_item.setBackground(QtGui.QColor(255, 200, 100))  # Orange for uncertain
            conf_item.setForeground(QtGui.QColor(0, 0, 0))  # Black text
            self.uncertain_table.setItem(row, 1, conf_item)

            # Position
            pos = f"({det.get('cx', 0):.0f}, {det.get('cy', 0):.0f})"
            self.uncertain_table.setItem(row, 2, QtWidgets.QTableWidgetItem(pos))

            # Page
            page = det.get('page', 1)
            self.uncertain_table.setItem(row, 3, QtWidgets.QTableWidgetItem(str(page)))

            # Show button (jumps to location)
            show_btn = QtWidgets.QPushButton("Zeigen")
            show_btn.setStyleSheet("background-color: #4a90d9; color: white;")
            show_btn.clicked.connect(lambda checked, d=det: self._show_uncertain(d))
            self.uncertain_table.setCellWidget(row, 4, show_btn)

        self.uncertain_layout.addWidget(self.uncertain_table)

    def _show_uncertain(self, det):
        """Jump to uncertain detection location."""
        pos = (det.get('cx', 0), det.get('cy', 0))
        self.jump_to_position.emit(pos)

    def _populate_data(self):
        """Populate all tables with data"""
        # All issues
        self._populate_issues_table(self.all_issues_table, self.result.issues)
        
        #  FIX: Use lowercase severity values (matching ValidationIssue)
        # Errors only
        errors = [i for i in self.result.issues if i.severity.lower() == 'error']
        self._populate_issues_table(self.errors_table, errors)
        
        # Warnings only
        warnings = [i for i in self.result.issues if i.severity.lower() == 'warning']
        self._populate_issues_table(self.warnings_table, warnings)
        
        # Info only
        info = [i for i in self.result.issues if i.severity.lower() == 'info']
        self._populate_issues_table(self.info_table, info)
        
        #  Auto-correctable issues
        correctable = [i for i in self.result.issues if i.auto_correctable]  #  CHANGED: use can_auto_correct
        self._populate_correctable_table(correctable)
        
        #  NEW: Update tab labels with counts
        self.tabs.setTabText(0, f" Alle Probleme ({len(self.result.issues)})")
        self.tabs.setTabText(1, f" Auto-Korrekturen ({len(correctable)})")
        self.tabs.setTabText(2, f" Fehler ({len(errors)})")
        self.tabs.setTabText(3, f" Warnungen ({len(warnings)})")
        self.tabs.setTabText(4, f" Hinweise ({len(info)})")
    
    def _populate_issues_table(self, table: QtWidgets.QTableWidget, issues: List[ValidationIssue]):
        """Populate a standard issues table"""
        table.setRowCount(len(issues))

        for row, issue in enumerate(issues):
            # Column 0: Severity
            severity_upper = issue.severity.upper()
            severity_item = QtWidgets.QTableWidgetItem(severity_upper)

            if issue.severity.lower() == 'error':
                severity_item.setForeground(QtGui.QColor('#ff4444'))
                severity_item.setBackground(QtGui.QColor(80, 40, 40))
            elif issue.severity.lower() == 'warning':
                severity_item.setForeground(QtGui.QColor('#ff8800'))
                severity_item.setBackground(QtGui.QColor(80, 60, 40))
            else:  # info/hint
                severity_item.setForeground(QtGui.QColor('#4444ff'))
                severity_item.setBackground(QtGui.QColor(40, 50, 80))

            severity_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            table.setItem(row, 0, severity_item)

            # Column 1: Kategorie (OCR, YOLO, or Template)
            # Determine the type of issue
            category_type = "YOLO"  # Default

            # Check for Template Matching issues first
            if issue.category.startswith('template_') or issue.message.startswith("Template"):
                category_type = "Template"
            # Check for OCR issues
            elif issue.category in ['format', 'duplicate', 'missing_data', 'confidence']:
                category_type = "OCR"
            elif any(keyword in issue.message.lower() for keyword in ['format', 'ungültig', 'doppelt']):
                category_type = "OCR"
            # Check for YOLO issues
            elif issue.message.startswith("YOLO:") or "yolo" in issue.category.lower():
                category_type = "YOLO"

            table.setItem(row, 1, QtWidgets.QTableWidgetItem(category_type))

            # Column 2: Klasse (actual class name or template symbol name)
            # Extract class from context or message
            class_name = issue.context.get('class', '')

            # For template symbols, extract the symbol name from the message
            if category_type == "Template" and not class_name:
                # Extract from "Template 'Hauptsignal': ..." format
                if "Template '" in issue.message:
                    start = issue.message.index("Template '") + len("Template '")
                    end = issue.message.index("'", start)
                    class_name = issue.message[start:end]

            # If not in context, extract from message (for YOLO/OCR)
            if not class_name and ':' in issue.message:
                # For "YOLO: isolierstoß niedrige Konfidenz" -> extract "isolierstoß"
                message_part = issue.message.split(':', 1)[1].strip()  # Get part after ":"
                class_name = message_part.split()[0] if message_part else ''  # Get first word

                # Clean up if it's not a class name
                if class_name.lower() in ['sehr', 'niedrige', 'keine', 'fehlender']:
                    class_name = issue.context.get('class', '')

            table.setItem(row, 2, QtWidgets.QTableWidgetItem(class_name))

            # Column 3: Row ID (Zeile)
            row_id_str = str(issue.row_id) if issue.row_id is not None and issue.row_id >= 0 else ""
            table.setItem(row, 3, QtWidgets.QTableWidgetItem(row_id_str))

            # Column 4: Field (Feld)
            field_str = issue.field if issue.field else ""
            table.setItem(row, 4, QtWidgets.QTableWidgetItem(field_str))

            # Column 5: Problem (message)
            table.setItem(row, 5, QtWidgets.QTableWidgetItem(issue.message))

            # Column 6: Current value (Aktueller Wert)
            current_str = str(issue.current_value) if issue.current_value is not None else ""
            table.setItem(row, 6, QtWidgets.QTableWidgetItem(current_str))

            # Column 7: Action (Aktion - Jump button)
            action_widget = QtWidgets.QWidget()
            action_layout = QtWidgets.QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)

            # Check if jumping is possible
            can_jump = issue.context.get('can_jump', False)
            has_position = 'position' in issue.context
            row_id_valid = issue.row_id is not None and issue.row_id >= 0

            #  Allow jump if either has position OR has valid row_id
            if (can_jump and has_position) or row_id_valid:
                jump_btn = QtWidgets.QPushButton(" Zeigen")
                jump_btn.setToolTip("Zur Erkennung/Position springen")

                #  Capture variables in lambda
                row_id = issue.row_id
                pos = issue.context.get('position', None)

                jump_btn.clicked.connect(
                    lambda checked, r=row_id, p=pos: self._on_jump_clicked(r, p)
                )
                action_layout.addWidget(jump_btn)
            else:
                # Add placeholder
                no_jump_label = QtWidgets.QLabel("—")
                no_jump_label.setAlignment(QtCore.Qt.AlignCenter)
                action_layout.addWidget(no_jump_label)

            action_layout.addStretch()
            table.setCellWidget(row, 7, action_widget)

            #  NEW Column 8: Korrektur (Correction Action Buttons)
            correction_widget = self._create_correction_button(issue)
            table.setCellWidget(row, 8, correction_widget)
    
    def _populate_correctable_table(self, issues: List[ValidationIssue]):
        """
         NEW: Populate auto-correctable issues table
        """
        self.correctable_table.setRowCount(len(issues))
        
        #  Block signals during population
        self.correctable_table.blockSignals(True)
        
        for row, issue in enumerate(issues):
            #  Column 0: Checkbox
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(True)
            checkbox.setProperty('issue', issue)
            
            #  Connect checkbox to update button state
            checkbox.stateChanged.connect(self.on_correction_selection_changed)
            
            checkbox_widget = QtWidgets.QWidget()
            checkbox_layout = QtWidgets.QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(QtCore.Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            
            self.correctable_table.setCellWidget(row, 0, checkbox_widget)
            
            # Column 1: Category
            category = issue.message.split(':')[0] if ':' in issue.message else "Allgemein"
            self.correctable_table.setItem(row, 1, QtWidgets.QTableWidgetItem(category))
            
            # Column 2: Row ID
            row_id_str = str(issue.row_id) if issue.row_id is not None else ""
            self.correctable_table.setItem(row, 2, QtWidgets.QTableWidgetItem(row_id_str))
            
            # Column 3: Field
            field_str = issue.field if issue.field else ""
            self.correctable_table.setItem(row, 3, QtWidgets.QTableWidgetItem(field_str))
            
            # Column 4: Current value (red background with BLACK text)
            current_item = QtWidgets.QTableWidgetItem(str(issue.current_value))
            current_item.setBackground(QtGui.QColor(255, 200, 200))
            current_item.setForeground(QtGui.QColor(0, 0, 0))  #  Black text for visibility
            current_item.setFont(QtGui.QFont("Courier New", 9))
            self.correctable_table.setItem(row, 4, current_item)

            # Column 5: Suggested value (green background with BLACK text)
            suggested_item = QtWidgets.QTableWidgetItem(str(issue.suggested_value))
            suggested_item.setBackground(QtGui.QColor(200, 255, 200))
            suggested_item.setForeground(QtGui.QColor(0, 0, 0))  #  Black text for visibility
            suggested_item.setFont(QtGui.QFont("Courier New", 9, QtGui.QFont.Bold))
            self.correctable_table.setItem(row, 5, suggested_item)
            
            # Column 6: Confidence (color-coded)
            #  Use issue.confidence (not correction_confidence)
            confidence_pct = f"{issue.confidence:.0%}"
            confidence_item = QtWidgets.QTableWidgetItem(confidence_pct)
            
            # Color code by confidence level
            if issue.confidence >= 0.9:
                confidence_item.setForeground(QtGui.QColor(0, 150, 0))  # Dark green
                confidence_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            elif issue.confidence >= 0.6:
                confidence_item.setForeground(QtGui.QColor(200, 150, 0))  # Orange
            else:
                confidence_item.setForeground(QtGui.QColor(200, 0, 0))  # Red
            
            self.correctable_table.setItem(row, 6, confidence_item)
            #  NEW: Column 7 - Action (Jump button)
            action_widget = QtWidgets.QWidget()
            action_layout = QtWidgets.QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            
            # Check if jumping is possible
            can_jump = issue.context.get('can_jump', False)
            has_position = 'position' in issue.context
            
            if can_jump and has_position:
                jump_btn = QtWidgets.QPushButton("")
                jump_btn.setToolTip("Zur Position springen")
                jump_btn.setMaximumWidth(40)
                
                # Capture variables
                row_id = issue.row_id
                pos = issue.context['position']
                
                jump_btn.clicked.connect(
                    lambda checked, r=row_id, p=pos: self._on_jump_clicked(r, p)
                )
                action_layout.addWidget(jump_btn)
            
            action_layout.addStretch()
            self.correctable_table.setCellWidget(row, 7, action_widget)

        #  Unblock signals and trigger initial update
        self.correctable_table.blockSignals(False)
        self.on_correction_selection_changed()
    
    def on_correction_selection_changed(self):
        """
         NEW: Update button state when correction selection changes
        """
        selected_count = self._count_selected_corrections()
        
        self.btn_apply_selected.setEnabled(selected_count > 0)
        
        if selected_count > 0:
            self.btn_apply_selected.setText(f" {selected_count} Korrekturen anwenden")
        else:
            self.btn_apply_selected.setText(" Ausgewählte Korrekturen anwenden")
    
    def _count_selected_corrections(self) -> int:
        """Count how many corrections are selected"""
        count = 0
        
        for row in range(self.correctable_table.rowCount()):
            checkbox_widget = self.correctable_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QtWidgets.QCheckBox)
                if checkbox and checkbox.isChecked():
                    count += 1
        
        return count
    
    def on_apply_selected(self):
        """
         NEW: Apply only selected corrections
        """
        corrections = []
        
        for row in range(self.correctable_table.rowCount()):
            checkbox_widget = self.correctable_table.cellWidget(row, 0)
            if not checkbox_widget:
                continue
            
            checkbox = checkbox_widget.findChild(QtWidgets.QCheckBox)
            if not checkbox or not checkbox.isChecked():
                continue
            
            issue = checkbox.property('issue')
            if issue:
                corrections.append(issue)
        
        if not corrections:
            return
        
        # Confirmation dialog
        reply = QtWidgets.QMessageBox.question(
            self,
            "Korrekturen anwenden",
            f"Möchten Sie {len(corrections)} Korrekturen anwenden?\n\n"
            "Die Änderungen werden sofort in der Tabelle sichtbar.\n"
            "Vergessen Sie nicht, danach zu speichern!",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.corrections_accepted.emit(corrections)
            self.accept()
    
    def on_apply_all(self):
        """Apply all auto-corrections"""
        correctable = [i for i in self.result.issues if i.auto_correctable]
        
        if not correctable:
            QtWidgets.QMessageBox.information(
                self,
                "Keine Korrekturen",
                "Es gibt keine Auto-Korrekturen zum Anwenden."
            )
            return
        
        # Show detailed confirmation - use issue.confidence
        high_conf = sum(1 for i in correctable if i.confidence >= 0.9)
        med_conf = sum(1 for i in correctable if 0.6 <= i.confidence < 0.9)
        low_conf = sum(1 for i in correctable if i.confidence < 0.6)

        msg = f"Möchten Sie alle {len(correctable)} Auto-Korrekturen anwenden?\n\n"
        msg += f"• Hohe Konfidenz (≥90%): {high_conf}\n"
        msg += f"• Mittlere Konfidenz (60-90%): {med_conf}\n"
        msg += f"• Niedrige Konfidenz (<60%): {low_conf}\n\n"
        msg += "Die Änderungen werden sofort sichtbar.\n"
        msg += "Vergessen Sie nicht, danach zu speichern!"
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Alle Korrekturen anwenden",
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.corrections_accepted.emit(correctable)
            self.accept()
    
    def on_export_report(self):
        """
         ENHANCED: Export comprehensive validation report
        
        Formats: TXT (detailed), CSV (tabular)
        """
        # Ask for format
        format_dialog = QtWidgets.QDialog(self)
        format_dialog.setWindowTitle("Export-Format wählen")
        
        layout = QtWidgets.QVBoxLayout(format_dialog)
        layout.addWidget(QtWidgets.QLabel("Wählen Sie das Export-Format:"))
        
        btn_txt = QtWidgets.QPushButton(" Detaillierter Bericht (TXT)")
        btn_txt.clicked.connect(lambda: self._export_txt(format_dialog))
        layout.addWidget(btn_txt)
        
        btn_csv = QtWidgets.QPushButton(" Tabelle (CSV)")
        btn_csv.clicked.connect(lambda: self._export_csv(format_dialog))
        layout.addWidget(btn_csv)
        
        btn_cancel = QtWidgets.QPushButton("Abbrechen")
        btn_cancel.clicked.connect(format_dialog.reject)
        layout.addWidget(btn_cancel)
        
        format_dialog.exec_()
    
    def _export_txt(self, parent_dialog):
        """Export as detailed text report"""
        parent_dialog.accept()
        
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Bericht speichern",
            "validation_report.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 80 + "\n")
                f.write("VALIDIERUNGSBERICHT\n")
                f.write("=" * 80 + "\n\n")
                
                # Summary
                f.write("ZUSAMMENFASSUNG\n")
                f.write("-" * 80 + "\n")
                for key, value in self.result.stats.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")
                
                # Auto-corrections applied
                if self.result.auto_corrections:
                    f.write("\nANGEWENDETE KORREKTUREN\n")
                    f.write("-" * 80 + "\n")
                    for row_id, field, old, new in self.result.auto_corrections:
                        f.write(f"Zeile {row_id} - {field}: '{old}' → '{new}'\n")
                    f.write("\n")
                
                # Issues by category
                categories = {}
                for issue in self.result.issues:
                    cat = issue.message.split(':')[0] if ':' in issue.message else "Allgemein"
                    categories.setdefault(cat, []).append(issue)
                
                for category, issues in sorted(categories.items()):
                    f.write(f"\n{category.upper()}\n")
                    f.write("-" * 80 + "\n")
                    
                    for issue in issues:
                        f.write(f"[{issue.severity}] Zeile {issue.row_id}\n")
                        f.write(f"  Feld: {issue.field}\n")
                        f.write(f"  Problem: {issue.message}\n")
                        f.write(f"  Aktuell: {issue.current_value}\n")
                        
                        if issue.suggested_value is not None:
                            f.write(f"  Vorschlag: {issue.suggested_value} ({issue.correction_confidence:.0%} Konfidenz)\n")
                        
                        f.write("\n")
            
            QtWidgets.QMessageBox.information(
                self,
                "Export erfolgreich",
                f"Bericht gespeichert:\n{filename}"
            )
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export fehlgeschlagen",
                f"Fehler beim Exportieren:\n{str(e)}"
            )
    
    def _export_csv(self, parent_dialog):
        """Export as CSV table"""
        parent_dialog.accept()
        
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "CSV speichern",
            "validation_results.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    'Schweregrad', 'Kategorie', 'Zeile', 'Feld', 
                    'Problem', 'Aktueller Wert', 'Vorschlag', 'Konfidenz'
                ])
                
                # Data
                for issue in self.result.issues:
                    category = issue.message.split(':')[0] if ':' in issue.message else "Allgemein"
                    
                    writer.writerow([
                        issue.severity,
                        category,
                        issue.row_id if issue.row_id is not None else '',
                        issue.field if issue.field else '',
                        issue.message,
                        str(issue.current_value) if issue.current_value is not None else '',
                        str(issue.suggested_value) if issue.suggested_value is not None else '',
                        f"{issue.correction_confidence:.0%}" if issue.auto_correctable else ''
                    ])
            
            QtWidgets.QMessageBox.information(
                self,
                "Export erfolgreich",
                f"CSV gespeichert:\n{filename}"
            )
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export fehlgeschlagen",
                f"Fehler beim Exportieren:\n{str(e)}"
            )
    def _on_jump_clicked(self, row_id: int, position: tuple):
        """Handle jump button click"""
        print(f"Jump button clicked: row_id={row_id}, position={position}")  # DEBUG

        #  If position is None, try to get it from dataframe using row_id
        if position is None and row_id is not None and row_id >= 0:
            try:
                df = self.result.df
                if df is not None and 'row_id' in df.columns:
                    row_data = df[df['row_id'] == row_id]
                    if not row_data.empty and 'xc' in row_data.columns and 'yc' in row_data.columns:
                        xc = row_data.iloc[0]['xc']
                        yc = row_data.iloc[0]['yc']
                        if not pd.isna(xc) and not pd.isna(yc):
                            position = (float(xc), float(yc))
                            print(f"Found position from row_id: {position}")
            except Exception as e:
                print(f" Could not get position from row_id: {e}")

        # Emit signal to parent workspace
        self.jump_to_detection.emit(row_id, position)

        # Optional: Show status in parent
        if self.parent():
            # Try to call parent's status bar
            if hasattr(self.parent(), '_set_status'):
                if position:
                    self.parent()._set_status(
                        f" Springe zu Position ({position[0]:.0f}, {position[1]:.0f})"
                    )
                else:
                    self.parent()._set_status(f" Springe zu Zeile {row_id}")

    # ========================================================================
    #  NEW: MANUAL CORRECTION ACTION BUTTONS
    # ========================================================================

    def _create_correction_button(self, issue: ValidationIssue) -> QtWidgets.QWidget:
        """
        Create correction action button/menu based on issue type

        Returns:
            - Auto-fix button for auto-correctable issues
            - Manual action button + menu for manual corrections
            - Empty widget if no actions available
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Check if auto-correctable
        if issue.auto_correctable and issue.suggested_value is not None:
            # Show auto-fix button
            confidence_pct = int(issue.confidence * 100)
            btn = QtWidgets.QPushButton(f" Auto-Fix ({confidence_pct}%)")
            btn.setToolTip(f"Automatische Korrektur mit {confidence_pct}% Sicherheit:\n{issue.context.get('suggestion', '')}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2d5016;
                    color: #90ee90;
                    border: 1px solid #4a7c2d;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #3a6b1e;
                }
            """)
            btn.clicked.connect(lambda: self._apply_single_correction(issue))
            layout.addWidget(btn)

        elif issue.context and issue.context.get('suggested_action'):
            # Show manual action button + menu
            suggested_action = issue.context.get('suggested_action')
            alternative_actions = issue.context.get('alternative_actions', [])

            # Map action IDs to button labels
            action_labels = {
                'manual_ocr_horizontal': ' OCR Horizontal',
                'manual_ocr_angular': ' OCR Angular',
                'manual_link': ' Verknüpfen',
                'bbox_resize': ' Bbox anpassen',
                'manual_edit': ' Bearbeiten',
                'delete': ' Löschen',
                'review': ' Prüfen'
            }

            # Primary action button
            label = action_labels.get(suggested_action, suggested_action)
            btn = QtWidgets.QPushButton(label)
            btn.setToolTip(issue.context.get('action_description', ''))
            btn.clicked.connect(lambda: self._trigger_manual_action(issue, suggested_action))
            layout.addWidget(btn)

            # Alternative actions menu
            if alternative_actions:
                menu_btn = QtWidgets.QPushButton("⋮")
                menu_btn.setFixedWidth(30)
                menu_btn.setToolTip("Weitere Korrektur-Optionen")

                menu = QtWidgets.QMenu()
                for alt_action in alternative_actions:
                    alt_label = action_labels.get(alt_action, alt_action)
                    action = menu.addAction(alt_label)
                    action.triggered.connect(lambda checked, a=alt_action, i=issue: self._trigger_manual_action(i, a))

                menu_btn.setMenu(menu)
                layout.addWidget(menu_btn)

        else:
            # No actions available
            no_action_label = QtWidgets.QLabel("—")
            no_action_label.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(no_action_label)

        layout.addStretch()
        return widget

    def _apply_single_correction(self, issue: ValidationIssue):
        """Apply a single auto-correction immediately"""
        try:
            # Apply correction to the dataframe
            mask = self.result.df['row_id'] == issue.row_id
            if mask.any():
                old_value = self.result.df.loc[mask, issue.field].iloc[0]
                self.result.df.loc[mask, issue.field] = issue.suggested_value

                # Log the correction
                if self.result.auto_corrections is None:
                    self.result.auto_corrections = []

                self.result.auto_corrections.append((
                    issue.row_id,
                    issue.field,
                    old_value,
                    issue.suggested_value
                ))

                # Mark as corrected
                issue.context['corrected'] = True

                # Show confirmation
                QtWidgets.QMessageBox.information(
                    self,
                    "Korrektur angewendet",
                    f" Korrektur erfolgreich:\n\n"
                    f"Feld: {issue.field}\n"
                    f"Alt: '{old_value}'\n"
                    f"Neu: '{issue.suggested_value}'\n\n"
                    f"Sicherheit: {int(issue.confidence * 100)}%"
                )

                # Emit signal to parent to refresh display
                if hasattr(self, 'corrections_accepted'):
                    self.corrections_accepted.emit([issue])

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Korrektur fehlgeschlagen",
                f"Fehler beim Anwenden der Korrektur:\n{str(e)}"
            )

    def _trigger_manual_action(self, issue: ValidationIssue, action: str):
        """
         UPGRADED: Trigger manual correction tool directly (no instruction popups)

        Actions:
        - manual_ocr_horizontal: Jump + activate horizontal OCR tool
        - manual_ocr_angular: Jump + activate angular OCR tool
        - manual_link: Jump + activate manual linking tool
        - bbox_resize: Jump + activate bbox resize mode
        - manual_edit: Jump only (user edits in table)
        - review: Jump only
        - delete: Jump + confirm deletion
        """
        # 1. Jump to the element first
        if issue.context and issue.context.get('can_jump'):
            position = issue.context.get('position')
            if position:
                self.jump_to_detection.emit(issue.row_id, position)

        # 2. Activate the appropriate tool directly
        if action == 'manual_ocr_horizontal':
            self.activate_manual_ocr.emit('horizontal')

        elif action == 'manual_ocr_angular':
            self.activate_manual_ocr.emit('angular')

        elif action == 'manual_link':
            self.activate_manual_link.emit()

        elif action == 'bbox_resize':
            self.activate_bbox_resize.emit()

        elif action == 'delete':
            # Show confirmation dialog then delete automatically
            msg = QtWidgets.QMessageBox(self)
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.setWindowTitle("Element löschen")
            msg.setText(f"<b>Element löschen?</b>")
            msg.setInformativeText(f"Möchten Sie dieses Element wirklich löschen?\n\n{issue.message}")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.No)

            if msg.exec_() == QtWidgets.QMessageBox.Yes:
                #  Emit signal to delete the row automatically
                self.delete_row.emit(issue.row_id)

        # For manual_edit and review: just jump to element (no tool activation needed)

# ============================================================================
# BACKWARD COMPATIBILITY ALIAS
# ============================================================================

# Keep old class name for backward compatibility
ValidationResultsDialog = EnhancedValidationResultsDialog