from PyQt5 import QtWidgets, QtCore, QtGui
from typing import List
from data_validator import ValidationResult

class ValidationResultsDialog(QtWidgets.QDialog):
    """Dialog to display validation results"""
    
    def __init__(self, results: List[ValidationResult], summary: dict, parent=None):
        super().__init__(parent)
        self.results = results
        self.summary = summary
        
        self.setWindowTitle("Datenvalidierung - Ergebnisse")
        self.resize(1000, 700)
        
        self._build_ui()
    
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Summary
        summary_text = f"""
        <h2>Validierungszusammenfassung</h2>
        <p><b>Gesamt:</b> {self.summary['total_checks']} Prüfungen</p>
        <p style="color: red;"><b>Fehler:</b> {self.summary['errors']}</p>
        <p style="color: orange;"><b>Warnungen:</b> {self.summary['warnings']}</p>
        <p style="color: blue;"><b>Hinweise:</b> {self.summary['info']}</p>
        """
        
        summary_label = QtWidgets.QLabel(summary_text)
        layout.addWidget(summary_label)
        
        # Filter controls
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("Filter:"))
        
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(["Alle", "Nur Fehler", "Nur Warnungen", "Nur Hinweise"])
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_combo)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # Results table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Schweregrad", "Nachricht", "Row ID", "Details"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.btn_export = QtWidgets.QPushButton("📊 Als CSV exportieren")
        self.btn_export.clicked.connect(self._export_results)
        button_layout.addWidget(self.btn_export)
        
        button_layout.addStretch()
        
        self.btn_close = QtWidgets.QPushButton("Schließen")
        self.btn_close.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)
        
        # Populate table
        self._populate_table(self.results)
    
    def _populate_table(self, results: List[ValidationResult]):
        """Populate results table"""
        self.table.setRowCount(len(results))
        
        for i, result in enumerate(results):
            # Severity
            severity_item = QtWidgets.QTableWidgetItem(result.severity)
            if result.severity == 'ERROR':
                severity_item.setForeground(QtGui.QColor('red'))
            elif result.severity == 'WARNING':
                severity_item.setForeground(QtGui.QColor('orange'))
            else:
                severity_item.setForeground(QtGui.QColor('blue'))
            self.table.setItem(i, 0, severity_item)
            
            # Message
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(result.message))
            
            # Row ID
            row_id_str = str(result.row_id) if result.row_id is not None else ""
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(row_id_str))
            
            # Details
            details_str = str(result.details) if result.details else ""
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(details_str))
        
        self.table.resizeColumnsToContents()
    
    def _apply_filter(self, filter_text: str):
        """Apply severity filter"""
        if filter_text == "Alle":
            filtered = self.results
        elif filter_text == "Nur Fehler":
            filtered = [r for r in self.results if r.severity == 'ERROR']
        elif filter_text == "Nur Warnungen":
            filtered = [r for r in self.results if r.severity == 'WARNING']
        else:  # Nur Hinweise
            filtered = [r for r in self.results if r.severity == 'INFO']
        
        self._populate_table(filtered)
    
    def _export_results(self):
        """Export results to CSV"""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Validierungsergebnisse exportieren",
            "validation_results.csv",
            "CSV Files (*.csv)"
        )
        
        if not filename:
            return
        
        try:
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Schweregrad', 'Nachricht', 'Row ID', 'Details'])
                
                for result in self.results:
                    writer.writerow([
                        result.severity,
                        result.message,
                        result.row_id if result.row_id is not None else '',
                        str(result.details)
                    ])
            
            QtWidgets.QMessageBox.information(
                self,
                "Exportiert",
                f"Ergebnisse exportiert nach:\n{filename}"
            )
        
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export-Fehler",
                f"Fehler beim Exportieren:\n{str(e)}"
            )