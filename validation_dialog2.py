"""
Enhanced Validation Results Dialog
✅ NEW: Auto-correction UI with confidence indicators and batch correction
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import List, Dict, Optional
from data_validator2 import ValidationResult, ValidationIssue, EnhancedDataValidator
import csv

class EnhancedValidationResultsDialog(QtWidgets.QDialog):
    """
    ✅ UPGRADED: Dialog with auto-correction support
    
    NEW FEATURES:
    - Tabbed interface (All Issues, Auto-Corrections, Errors, Warnings)
    - Checkbox selection for corrections
    - Confidence indicators (color-coded)
    - Batch correction application
    - Export validation reports
    """
    
    # ✅ NEW: Signal emitted when user accepts corrections
    corrections_accepted = QtCore.pyqtSignal(list)  # List[ValidationIssue]
    
    def __init__(self, result: ValidationResult, parent=None):
        super().__init__(parent)
        self.result = result
        self.selected_corrections = []
        
        self.setWindowTitle("Datenvalidierung - Ergebnisse")
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
        summary_group = QtWidgets.QGroupBox("📊 Zusammenfassung")
        summary_layout = QtWidgets.QGridLayout(summary_group)

        stats = self.result.get_summary()

        # Row 0: Total
        summary_layout.addWidget(QtWidgets.QLabel("Gesamt:"), 0, 0)
        total_label = QtWidgets.QLabel(str(stats['total_issues']))
        total_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        summary_layout.addWidget(total_label, 0, 1)

        # Row 1: Errors
        summary_layout.addWidget(QtWidgets.QLabel("Fehler:"), 1, 0)
        error_label = QtWidgets.QLabel(str(stats['errors']))
        error_label.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 12pt;")
        summary_layout.addWidget(error_label, 1, 1)

        # Row 2: Warnings
        summary_layout.addWidget(QtWidgets.QLabel("Warnungen:"), 2, 0)
        warning_label = QtWidgets.QLabel(str(stats['warnings']))
        warning_label.setStyleSheet("color: #ffaa00; font-weight: bold; font-size: 12pt;")
        summary_layout.addWidget(warning_label, 2, 1)

        # Row 3: Info
        summary_layout.addWidget(QtWidgets.QLabel("Hinweise:"), 3, 0)
        info_label = QtWidgets.QLabel(str(stats['info']))
        info_label.setStyleSheet("color: #4444ff; font-size: 12pt;")
        summary_layout.addWidget(info_label, 3, 1)

        # ✅ Auto-correctable count
        summary_layout.addWidget(QtWidgets.QLabel("Auto-korrigierbar:"), 0, 2)
        auto_label = QtWidgets.QLabel(str(stats['auto_correctable']))
        auto_label.setStyleSheet("color: #44ff44; font-weight: bold; font-size: 14pt;")
        summary_layout.addWidget(auto_label, 0, 3)

        # ✅ High confidence fixes
        if stats['high_confidence_fixes'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel("Hohe Konfidenz (≥80%):"), 1, 2)
            high_conf_label = QtWidgets.QLabel(str(stats['high_confidence_fixes']))
            high_conf_label.setStyleSheet("color: #00cc00; font-weight: bold;")
            summary_layout.addWidget(high_conf_label, 1, 3)

        # ✅ Medium confidence fixes
        if stats['medium_confidence_fixes'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel("Mittlere Konfidenz (60-80%):"), 2, 2)
            med_conf_label = QtWidgets.QLabel(str(stats['medium_confidence_fixes']))
            med_conf_label.setStyleSheet("color: #ccaa00;")
            summary_layout.addWidget(med_conf_label, 2, 3)

        # ✅ Corrections applied
        if stats['corrections_applied'] > 0:
            summary_layout.addWidget(QtWidgets.QLabel("Angewendet:"), 3, 2)
            applied_label = QtWidgets.QLabel(str(stats['corrections_applied']))
            applied_label.setStyleSheet("color: #44ff44; font-weight: bold;")
            summary_layout.addWidget(applied_label, 3, 3)

        layout.addWidget(summary_group)
        
        # ========================================================================
        # TABBED INTERFACE (New)
        # ========================================================================
        self.tabs = QtWidgets.QTabWidget()
        
        # Tab 1: All Issues
        self.all_issues_table = self._create_issues_table()
        self.tabs.addTab(self.all_issues_table, "📋 Alle Probleme")
        
        # ✅ Tab 2: Auto-Correctable Issues (NEW)
        self.correctable_table = self._create_correctable_table()
        self.tabs.addTab(self.correctable_table, "✨ Auto-Korrekturen")
        
        # Tab 3: Errors Only
        self.errors_table = self._create_issues_table()
        self.tabs.addTab(self.errors_table, "❌ Fehler")
        
        # Tab 4: Warnings Only
        self.warnings_table = self._create_issues_table()
        self.tabs.addTab(self.warnings_table, "⚠️ Warnungen")
        
        # Tab 5: Info Only
        self.info_table = self._create_issues_table()
        self.tabs.addTab(self.info_table, "ℹ️ Hinweise")
        
        layout.addWidget(self.tabs)
        
        # ========================================================================
        # BUTTON SECTION (Enhanced)
        # ========================================================================
        button_layout = QtWidgets.QHBoxLayout()
        
        # ✅ NEW: Apply selected corrections button
        self.btn_apply_selected = QtWidgets.QPushButton("✓ Ausgewählte Korrekturen anwenden")
        self.btn_apply_selected.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton))
        self.btn_apply_selected.clicked.connect(self.on_apply_selected)
        self.btn_apply_selected.setEnabled(False)
        self.btn_apply_selected.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 8px; }")
        button_layout.addWidget(self.btn_apply_selected)
        
        # ✅ NEW: Apply all corrections button
        self.btn_apply_all = QtWidgets.QPushButton("✓ Alle Korrekturen anwenden")
        self.btn_apply_all.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.btn_apply_all.clicked.connect(self.on_apply_all)
        self.btn_apply_all.setEnabled(stats['auto_correctable'] > 0)
        self.btn_apply_all.setStyleSheet("QPushButton { background-color: #2196F3; color: white; padding: 8px; }")
        button_layout.addWidget(self.btn_apply_all)
        
        button_layout.addStretch()
        
        # Export button
        self.btn_export = QtWidgets.QPushButton("📄 Bericht exportieren")
        self.btn_export.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton))
        self.btn_export.clicked.connect(self.on_export_report)
        button_layout.addWidget(self.btn_export)
        
        # Close button
        self.btn_close = QtWidgets.QPushButton("Schließen")
        self.btn_close.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton))
        self.btn_close.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)
    
    def _create_issues_table(self) -> QtWidgets.QTableWidget:
        """Create standard issues table"""
        table = QtWidgets.QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Schwere", "Kategorie", "Zeile", "Feld", "Problem", "Aktueller Wert"
        ])
        
        # Set column widths
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 60)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(4, 300)
        
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        
        return table
    
    def _create_correctable_table(self) -> QtWidgets.QTableWidget:
        """
        ✅ NEW: Create table for auto-correctable issues
        
        Columns: Checkbox, Category, Row, Field, Current, Suggested, Confidence
        """
        table = QtWidgets.QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "☑", "Kategorie", "Zeile", "Feld", "Aktuell", "Vorschlag", "Konfidenz"
        ])
        
        # Set column widths
        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 60)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(4, 200)
        table.setColumnWidth(5, 200)
        table.setColumnWidth(6, 100)
        
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        
        # Connect selection change
        table.itemChanged.connect(self.on_correction_selection_changed)
        
        return table
    
    def _populate_data(self):
        """Populate all tables with data"""
        # All issues
        self._populate_issues_table(self.all_issues_table, self.result.issues)
        
        # ✅ FIX: Use lowercase severity values (matching ValidationIssue)
        # Errors only
        errors = [i for i in self.result.issues if i.severity.lower() == 'error']
        self._populate_issues_table(self.errors_table, errors)
        
        # Warnings only
        warnings = [i for i in self.result.issues if i.severity.lower() == 'warning']
        self._populate_issues_table(self.warnings_table, warnings)
        
        # Info only
        info = [i for i in self.result.issues if i.severity.lower() == 'info']
        self._populate_issues_table(self.info_table, info)
        
        # ✅ Auto-correctable issues
        correctable = [i for i in self.result.issues if i.auto_correctable]  # ✅ CHANGED: use can_auto_correct
        self._populate_correctable_table(correctable)
        
        # ✅ NEW: Update tab labels with counts
        self.tabs.setTabText(0, f"📋 Alle Probleme ({len(self.result.issues)})")
        self.tabs.setTabText(1, f"✨ Auto-Korrekturen ({len(correctable)})")
        self.tabs.setTabText(2, f"❌ Fehler ({len(errors)})")
        self.tabs.setTabText(3, f"⚠️ Warnungen ({len(warnings)})")
        self.tabs.setTabText(4, f"ℹ️ Hinweise ({len(info)})")
    
    def _populate_issues_table(self, table: QtWidgets.QTableWidget, issues: List[ValidationIssue]):
        """Populate a standard issues table"""
        table.setRowCount(len(issues))
        
        for row, issue in enumerate(issues):
            # ✅ FIX: Use lowercase comparison
            severity_upper = issue.severity.upper()
            
            # Severity
            severity_item = QtWidgets.QTableWidgetItem(severity_upper)
            
            if issue.severity.lower() == 'error':  # ✅ CHANGED
                severity_item.setForeground(QtGui.QColor('#ff4444'))
                severity_item.setBackground(QtGui.QColor(255, 200, 200))
            elif issue.severity.lower() == 'warning':  # ✅ CHANGED
                severity_item.setForeground(QtGui.QColor('#ff8800'))
                severity_item.setBackground(QtGui.QColor(255, 240, 200))
            else:  # info/hint
                severity_item.setForeground(QtGui.QColor('#4444ff'))
                severity_item.setBackground(QtGui.QColor(200, 220, 255))
            
            severity_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            table.setItem(row, 0, severity_item)
            
            # Category (extract from message)
            category = issue.message.split(':')[0] if ':' in issue.message else issue.message[:20]
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(category))
            
            # Row ID
            row_id_str = str(issue.row_id) if issue.row_id is not None else ""
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(row_id_str))
            
            # Field
            field_str = issue.field if issue.field else ""
            table.setItem(row, 3, QtWidgets.QTableWidgetItem(field_str))
            
            # Message
            table.setItem(row, 4, QtWidgets.QTableWidgetItem(issue.message))
            
            # Current value
            current_str = str(issue.current_value) if issue.current_value is not None else ""
            table.setItem(row, 5, QtWidgets.QTableWidgetItem(current_str))
    
    def _populate_correctable_table(self, issues: List[ValidationIssue]):
        """
        ✅ NEW: Populate auto-correctable issues table
        """
        self.correctable_table.setRowCount(len(issues))
        
        # ✅ Block signals during population
        self.correctable_table.blockSignals(True)
        
        for row, issue in enumerate(issues):
            # ✅ Column 0: Checkbox
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(True)
            checkbox.setProperty('issue', issue)
            
            # ✅ Connect checkbox to update button state
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
            
            # Column 4: Current value (red background)
            current_item = QtWidgets.QTableWidgetItem(str(issue.current_value))
            current_item.setBackground(QtGui.QColor(255, 200, 200))
            current_item.setFont(QtGui.QFont("Courier New", 9))
            self.correctable_table.setItem(row, 4, current_item)
            
            # Column 5: Suggested value (green background)
            suggested_item = QtWidgets.QTableWidgetItem(str(issue.suggested_value))
            suggested_item.setBackground(QtGui.QColor(200, 255, 200))
            suggested_item.setFont(QtGui.QFont("Courier New", 9, QtGui.QFont.Bold))
            self.correctable_table.setItem(row, 5, suggested_item)
            
            # Column 6: Confidence (color-coded)
            # ✅ Use issue.confidence (not correction_confidence)
            confidence_pct = f"{issue.confidence:.0%}"
            confidence_item = QtWidgets.QTableWidgetItem(confidence_pct)
            
            # Color code by confidence level
            if issue.confidence >= 0.8:
                confidence_item.setForeground(QtGui.QColor(0, 150, 0))  # Dark green
                confidence_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            elif issue.confidence >= 0.6:
                confidence_item.setForeground(QtGui.QColor(200, 150, 0))  # Orange
            else:
                confidence_item.setForeground(QtGui.QColor(200, 0, 0))  # Red
            
            self.correctable_table.setItem(row, 6, confidence_item)
        
        # ✅ Unblock signals and trigger initial update
        self.correctable_table.blockSignals(False)
        self.on_correction_selection_changed()
    
    def on_correction_selection_changed(self):
        """
        ✅ NEW: Update button state when correction selection changes
        """
        selected_count = self._count_selected_corrections()
        
        self.btn_apply_selected.setEnabled(selected_count > 0)
        
        if selected_count > 0:
            self.btn_apply_selected.setText(f"✓ {selected_count} Korrekturen anwenden")
        else:
            self.btn_apply_selected.setText("✓ Ausgewählte Korrekturen anwenden")
    
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
        ✅ NEW: Apply only selected corrections
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
        high_conf = sum(1 for i in correctable if i.confidence >= 0.8)
        med_conf = sum(1 for i in correctable if 0.6 <= i.confidence < 0.8)
        low_conf = sum(1 for i in correctable if i.confidence < 0.6)
        
        msg = f"Möchten Sie alle {len(correctable)} Auto-Korrekturen anwenden?\n\n"
        msg += f"• Hohe Konfidenz (≥80%): {high_conf}\n"
        msg += f"• Mittlere Konfidenz (60-80%): {med_conf}\n"
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
        ✅ ENHANCED: Export comprehensive validation report
        
        Formats: TXT (detailed), CSV (tabular)
        """
        # Ask for format
        format_dialog = QtWidgets.QDialog(self)
        format_dialog.setWindowTitle("Export-Format wählen")
        
        layout = QtWidgets.QVBoxLayout(format_dialog)
        layout.addWidget(QtWidgets.QLabel("Wählen Sie das Export-Format:"))
        
        btn_txt = QtWidgets.QPushButton("📄 Detaillierter Bericht (TXT)")
        btn_txt.clicked.connect(lambda: self._export_txt(format_dialog))
        layout.addWidget(btn_txt)
        
        btn_csv = QtWidgets.QPushButton("📊 Tabelle (CSV)")
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


# ============================================================================
# BACKWARD COMPATIBILITY ALIAS
# ============================================================================

# Keep old class name for backward compatibility
ValidationResultsDialog = EnhancedValidationResultsDialog