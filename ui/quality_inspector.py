"""
Qualitätsprüfung (Quality Inspector) Dialog
Professional quality assurance system combining confidence analysis with validation
Designed for Siemens Mobility GmbH - Rail Infrastructure Quality Management
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Dict, Optional, List, TYPE_CHECKING
import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from ui.workspace_widget import WorkspaceWidget


class QualityInspectorDialog(QtWidgets.QDialog):
    """
    Professional Quality Inspector for rail infrastructure data.

    Features:
    - Risk-based prioritization
    - Confidence analysis
    - Quick validation status
    - Links to comprehensive validation
    - Jump to elements in UI
    """

    def __init__(self, workspace: 'WorkspaceWidget', parent=None):
        super().__init__(parent)
        self.workspace = workspace

        # ✅ FILTER: Exclude unlinked coordinates and weichen_block (per user request)
        df_filtered = workspace.df_all.copy()
        if 'cls' in df_filtered.columns:
            df_filtered = df_filtered[
                (df_filtered['cls'] != 'coordinate') &  # Exclude unlinked standalone coordinates
                (df_filtered['cls'] != 'weichen_block')  # Exclude weichen_block
            ]
        self.df_all = df_filtered

        # ✅ Load custom symbol configurations for proper risk assessment
        self.custom_symbol_config = self._load_custom_symbol_config()

        self.setWindowTitle(f"Erkennungsqualität prüfen - {workspace.layout_name}")
        self.resize(1400, 900)

        # Set window flags for independent window
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )

        # Calculate risk scores for all detections
        self._calculate_risk_scores()

        self._build_ui()
        self._populate_data()
        self._apply_theme()

    def _load_custom_symbol_config(self) -> Dict:
        """Load custom symbol configurations to check has_text and links_to_coordinate."""
        config = {}
        try:
            from core.symbol_detector import NewSymbolDetector
            detector = NewSymbolDetector()
            for name, symbol in detector.symbols.items():
                config[name] = {
                    'has_text': symbol.has_text,
                    'links_to_coordinate': symbol.links_to_coordinate,
                    'text_position': symbol.text_position
                }
        except Exception as e:
            print(f"⚠️ Could not load custom symbol config: {e}")
        return config

    def _calculate_risk_scores(self):
        """
        Calculate risk score for each detection.

        Risk = Confidence Risk (40%) + Missing Data (30%) + Duplicates (15%) + Size (15%)
        """
        self.df_all['risk_score'] = 0.0
        self.df_all['risk_factors'] = ''

        for idx, row in self.df_all.iterrows():
            risk = 0.0
            factors = []

            # Factor 1: Confidence Risk (40% weight)
            conf = row.get('conf', 1.0)
            if pd.notna(conf):
                conf_risk = (1.0 - conf) * 0.4
                risk += conf_risk
                if conf < 0.6:
                    factors.append('Unsichere Texterkennung')

            # Factor 2: Missing Required Data (30% weight)
            cls = row.get('cls', '')
            is_custom = row.get('is_custom_symbol', False) == True

            # Determine if this symbol should have coordinate/text based on type
            needs_coordinate = False
            needs_text = False

            if is_custom and cls in self.custom_symbol_config:
                # Custom symbol - check configuration
                sym_config = self.custom_symbol_config[cls]
                needs_coordinate = sym_config.get('links_to_coordinate', False)
                needs_text = sym_config.get('has_text', False)
            else:
                # YOLO symbol - use hardcoded lists
                needs_coordinate = cls in ['signal', 'gks_gesteuert', 'gks_festkodiert',
                                           'prellblock', 'haltepunkt', 'sverbinder']
                needs_text = cls in ['signal', 'gks_gesteuert', 'gks_festkodiert']

            # Check for missing coordinate link
            if needs_coordinate:
                if pd.isna(row.get('coord_text')) or not str(row.get('coord_text', '')).strip():
                    risk += 0.3
                    factors.append('Koordinate fehlt')

            # Check for missing text
            if needs_text:
                if pd.isna(row.get('anchor_text')) or not str(row.get('anchor_text', '')).strip():
                    risk += 0.15
                    factors.append('Bezeichnung fehlt')

            # Factor 3: Potential Duplicate (15% weight)
            # Check if there are nearby detections of same class
            if 'xc' in row and 'yc' in row and pd.notna(row.get('xc')) and pd.notna(row.get('yc')):
                same_class = self.df_all[
                    (self.df_all['cls'] == cls) &
                    (self.df_all['row_id'] != row.get('row_id')) &
                    (self.df_all['page'] == row.get('page'))
                ]

                for _, other in same_class.iterrows():
                    if pd.notna(other.get('xc')) and pd.notna(other.get('yc')):
                        dist = np.sqrt((row['xc'] - other['xc'])**2 + (row['yc'] - other['yc'])**2)
                        if dist < 50:  # Within 50 pixels
                            risk += 0.15
                            factors.append('Evtl. doppelt erkannt')
                            break

            # Factor 4: Size Anomaly (10% weight) - very basic check
            if 'w' in row and 'h' in row and pd.notna(row.get('w')) and pd.notna(row.get('h')):
                area = row['w'] * row['h']
                if area < 100 or area > 50000:  # Very small or very large
                    risk += 0.10
                    factors.append('Auffällige Größe')

            # ✅ NEW Factor 5: Invalid Coordinate Start (20% weight)
            # Only check linked coordinates (cls != 'coordinate')
            if cls != 'coordinate' and pd.notna(row.get('coord_text')):
                coord_text = str(row.get('coord_text', '')).strip()
                if coord_text and not (coord_text[0].isdigit() or coord_text[0] == '-'):
                    risk += 0.20
                    factors.append('Ungültige Koordinate')

            # ✅ NEW Factor 6: GKS Contains Letters (15% weight)
            if cls in ['gks_gesteuert', 'gks_festkodiert']:
                gks_text = str(row.get('anchor_text', '')).strip()
                if gks_text:
                    # Remove common formatting
                    cleaned = gks_text.replace(' ', '').replace('-', '')
                    if not cleaned.isdigit():
                        risk += 0.15
                        factors.append('GKS enthält Buchstaben')

            # ✅ NEW Factor 7: Multiple Spaces (5% weight)
            anchor_text = str(row.get('anchor_text', ''))
            # Only check coord_text for linked coordinates
            coord_text = str(row.get('coord_text', '')) if cls != 'coordinate' else ''
            if '  ' in coord_text or '  ' in anchor_text:  # Two or more spaces
                risk += 0.05
                factors.append('Formatierungsfehler')

            self.df_all.at[idx, 'risk_score'] = min(risk, 1.0)  # Cap at 100%
            self.df_all.at[idx, 'risk_factors'] = ', '.join(factors) if factors else 'OK'

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

                # ✅ FIX: Set inactive selection colors to match active ones
                # This prevents the green color when clicking outside the dialog
                palette.setColor(QtGui.QPalette.Inactive, QtGui.QPalette.Highlight,
                                palette.color(QtGui.QPalette.Active, QtGui.QPalette.Highlight))
                palette.setColor(QtGui.QPalette.Inactive, QtGui.QPalette.HighlightedText,
                                palette.color(QtGui.QPalette.Active, QtGui.QPalette.HighlightedText))

                self.setPalette(palette)
                self.table.setPalette(palette)
        except Exception as e:
            # If theme application fails, just continue
            pass

    def _build_ui(self):
        """Build the UI"""
        layout = QtWidgets.QVBoxLayout(self)

        # ========================================================================
        # HEADER: Enhanced Statistics Section
        # ========================================================================
        stats_group = QtWidgets.QGroupBox("📊 Erkennungsqualität - Übersicht")
        stats_layout = QtWidgets.QGridLayout(stats_group)

        # Calculate statistics
        stats = self._calculate_statistics()

        # Row 0: Total detections
        stats_layout.addWidget(QtWidgets.QLabel("Erkannte Elemente:"), 0, 0)
        total_label = QtWidgets.QLabel(str(stats['total']))
        total_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        stats_layout.addWidget(total_label, 0, 1)

        # Row 1: Average confidence
        stats_layout.addWidget(QtWidgets.QLabel("Durchschn. Erkennungsgenauigkeit:"), 1, 0)
        avg_label = QtWidgets.QLabel(f"{stats['avg_confidence']:.1%}")
        avg_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        stats_layout.addWidget(avg_label, 1, 1)

        # Add spacer
        stats_layout.setColumnMinimumWidth(1, 120)

        # Priority explanation header
        priority_header = QtWidgets.QLabel("🔍 Prüfbedarf:")
        priority_header.setStyleSheet("font-weight: bold; font-size: 11pt;")
        stats_layout.addWidget(priority_header, 0, 2, 1, 4)

        # Risk Statistics (Right side) - with clearer labels
        stats_layout.addWidget(QtWidgets.QLabel("❌ Sofort prüfen:"), 1, 2)
        high_risk_label = QtWidgets.QLabel(f"{stats['high_risk']} Elemente ({stats['high_risk_pct']:.1%})")
        high_risk_label.setStyleSheet("color: #ff0000; font-weight: bold; font-size: 11pt;")
        high_risk_label.setToolTip("Elemente mit niedriger Erkennungsqualität oder fehlenden Daten - dringend überprüfen!")
        stats_layout.addWidget(high_risk_label, 1, 3)

        stats_layout.addWidget(QtWidgets.QLabel("⚠️ Bald prüfen:"), 2, 2)
        med_risk_label = QtWidgets.QLabel(f"{stats['medium_risk']} Elemente ({stats['medium_risk_pct']:.1%})")
        med_risk_label.setStyleSheet("color: #ff8800; font-weight: bold;")
        med_risk_label.setToolTip("Elemente mit mittlerer Qualität - bei Gelegenheit kontrollieren")
        stats_layout.addWidget(med_risk_label, 2, 3)

        stats_layout.addWidget(QtWidgets.QLabel("✅ Gut erkannt:"), 3, 2)
        low_risk_label = QtWidgets.QLabel(f"{stats['low_risk']} Elemente ({stats['low_risk_pct']:.1%})")
        low_risk_label.setStyleSheet("color: #44ff44; font-weight: bold;")
        low_risk_label.setToolTip("Elemente mit hoher Erkennungsqualität - keine Prüfung nötig")
        stats_layout.addWidget(low_risk_label, 3, 3)

        layout.addWidget(stats_group)

        # ========================================================================
        # HELP INFO BOX
        # ========================================================================
        help_box = QtWidgets.QGroupBox("ℹ️ Was macht diese Prüfung?")
        help_layout = QtWidgets.QVBoxLayout(help_box)
        help_text = QtWidgets.QLabel(
            "<b>Diese Ansicht zeigt, welche Elemente Sie kontrollieren sollten:</b><br>"
            "• <b style='color: #ff0000;'>❌ Sofort prüfen</b> = Texterkennung unsicher oder Daten fehlen → Jetzt korrigieren<br>"
            "• <b style='color: #ff8800;'>⚠️ Bald prüfen</b> = Mittlere Qualität → Bei Gelegenheit kontrollieren<br>"
            "• <b style='color: #44ff44;'>✅ Gut erkannt</b> = Hohe Qualität → Normalerweise OK<br><br>"
            "<i>Tipp: Doppelklick auf eine Zeile → Springt direkt zum Element im Gleisplan</i>"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("padding: 8px; background-color: rgba(100, 150, 255, 0.1); border-radius: 4px;")
        help_layout.addWidget(help_text)
        layout.addWidget(help_box)

        # ========================================================================
        # FILTER CONTROLS
        # ========================================================================
        filter_group = QtWidgets.QGroupBox("🔍 Filter")
        filter_layout = QtWidgets.QHBoxLayout(filter_group)

        # Class filter
        filter_layout.addWidget(QtWidgets.QLabel("Klasse:"))
        self.class_filter = QtWidgets.QComboBox()
        self.class_filter.addItem("Alle Klassen")
        classes = sorted(self.df_all['cls'].dropna().unique())
        self.class_filter.addItems(classes)
        self.class_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.class_filter)

        # Risk filter
        filter_layout.addWidget(QtWidgets.QLabel("Prüfbedarf:"))
        self.risk_filter = QtWidgets.QComboBox()
        self.risk_filter.addItems([
            "Alle",
            "❌ Sofort prüfen (>20%)",
            "⚠️ Bald prüfen (10-20%)",
            "✅ Gut erkannt (<10%)"
        ])
        self.risk_filter.setToolTip("Filter nach Dringlichkeit der Überprüfung")
        self.risk_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.risk_filter)

        # Confidence filter
        filter_layout.addWidget(QtWidgets.QLabel("Erkennungsqualität:"))
        self.conf_filter = QtWidgets.QComboBox()
        self.conf_filter.addItems([
            "Alle",
            "Niedrig (<60%)",
            "Mittel (60-80%)",
            "Hoch (≥80%)"
        ])
        self.conf_filter.setToolTip("Filter nach OCR-Erkennungsgenauigkeit")
        self.conf_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.conf_filter)

        # Page filter
        filter_layout.addWidget(QtWidgets.QLabel("Seite:"))
        self.page_filter = QtWidgets.QComboBox()
        self.page_filter.addItem("Alle Seiten")
        pages = sorted(self.df_all['page'].dropna().unique())
        self.page_filter.addItems([str(int(p)) for p in pages])
        self.page_filter.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.page_filter)

        # Text search
        filter_layout.addWidget(QtWidgets.QLabel("Suche:"))
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Text suchen...")
        self.search_input.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_input)

        # Clear filters button
        btn_clear = QtWidgets.QPushButton("Filter löschen")
        btn_clear.clicked.connect(self._clear_filters)
        filter_layout.addWidget(btn_clear)

        layout.addWidget(filter_group)

        # ========================================================================
        # TABLE with Risk Score
        # ========================================================================
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Typ", "Text/Bezeichnung", "Erkennungs-\ngenauigkeit", "Prüf-\nbedarf", "Status",
            "Was prüfen?", "Seite", "Koordinate"
        ])

        # Set column widths
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 250)
        self.table.setColumnWidth(7, 60)
        self.table.setColumnWidth(8, 100)

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

        # Full validation button
        btn_full_validation = QtWidgets.QPushButton("→ Detaillierte Datenprüfung öffnen")
        btn_full_validation.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        btn_full_validation.setStyleSheet("QPushButton { background-color: #2196F3; color: white; padding: 8px; font-weight: bold; }")
        btn_full_validation.setToolTip("Öffnet die ausführliche Datenvalidierung mit Auto-Korrektur-Funktionen")
        btn_full_validation.clicked.connect(self._open_full_validation)
        button_layout.addWidget(btn_full_validation)

        button_layout.addStretch()

        # Export button
        btn_export = QtWidgets.QPushButton("📄 Bericht exportieren")
        btn_export.setToolTip("Exportiert die aktuelle Ansicht als CSV-Datei für Excel")
        btn_export.clicked.connect(self._export_to_csv)
        button_layout.addWidget(btn_export)

        # Info label
        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("color: #666; font-style: italic;")
        button_layout.addWidget(self.info_label)

        button_layout.addStretch()

        # Close button
        btn_close = QtWidgets.QPushButton("Schließen")
        btn_close.clicked.connect(self.reject)
        button_layout.addWidget(btn_close)

        layout.addLayout(button_layout)

    def _calculate_statistics(self) -> Dict:
        """Calculate quality statistics"""
        df = self.df_all.copy()

        # Filter out rows without confidence
        df = df[df['conf'].notna()]

        total = len(df)
        if total == 0:
            return {
                'total': 0, 'avg_confidence': 0.0,
                'high_risk': 0, 'high_risk_pct': 0.0,
                'medium_risk': 0, 'medium_risk_pct': 0.0,
                'low_risk': 0, 'low_risk_pct': 0.0
            }

        avg_confidence = df['conf'].mean()

        # Debug: Check if risk_score column exists and has valid values
        if 'risk_score' not in df.columns:
            print("⚠️ WARNING: risk_score column does not exist!")
            return {
                'total': total, 'avg_confidence': avg_confidence,
                'high_risk': 0, 'high_risk_pct': 0.0,
                'medium_risk': 0, 'medium_risk_pct': 0.0,
                'low_risk': total, 'low_risk_pct': 1.0
            }

        # Filter out rows with null/NaN risk_score
        df_with_risk = df[df['risk_score'].notna()]
        print(f"📊 Statistics debug:")
        print(f"   Total rows: {total}")
        print(f"   Rows with risk_score: {len(df_with_risk)}")
        print(f"   Risk score range: {df_with_risk['risk_score'].min():.3f} - {df_with_risk['risk_score'].max():.3f}")
        print(f"   Risk score mean: {df_with_risk['risk_score'].mean():.3f}")

        # Adjusted thresholds for high-confidence datasets
        high_risk = len(df_with_risk[df_with_risk['risk_score'] > 0.20])
        medium_risk = len(df_with_risk[(df_with_risk['risk_score'] >= 0.10) & (df_with_risk['risk_score'] <= 0.20)])
        low_risk = len(df_with_risk[df_with_risk['risk_score'] < 0.10])

        print(f"   High risk (>0.20): {high_risk}")
        print(f"   Medium risk (0.10-0.20): {medium_risk}")
        print(f"   Low risk (<0.10): {low_risk}")

        return {
            'total': total,
            'avg_confidence': avg_confidence,
            'high_risk': high_risk,
            'high_risk_pct': high_risk / total if total > 0 else 0,
            'medium_risk': medium_risk,
            'medium_risk_pct': medium_risk / total if total > 0 else 0,
            'low_risk': low_risk,
            'low_risk_pct': low_risk / total if total > 0 else 0
        }

    def _populate_data(self):
        """Populate the table with detection data"""
        df = self.df_all.copy()

        # Filter out rows without confidence
        df = df[df['conf'].notna()]

        # Sort by risk score (highest first)
        df = df.sort_values('risk_score', ascending=False)

        self.table.setSortingEnabled(False)  # Disable during population
        self.table.setRowCount(len(df))

        for row_idx, (_, row) in enumerate(df.iterrows()):
            # Row ID
            row_id_item = QtWidgets.QTableWidgetItem(str(int(row['row_id'])))
            row_id_item.setData(QtCore.Qt.UserRole, int(row['row_id']))
            self.table.setItem(row_idx, 0, row_id_item)

            # Class (with indicator for custom symbols)
            cls_name = str(row.get('cls', ''))
            is_custom = row.get('is_custom_symbol', False) == True
            if is_custom:
                cls_display = f"📦 {cls_name}"
            else:
                cls_display = cls_name
            cls_item = QtWidgets.QTableWidgetItem(cls_display)
            if is_custom:
                cls_item.setForeground(QtGui.QColor('#ff00ff'))  # Magenta for custom
            self.table.setItem(row_idx, 1, cls_item)

            # Text/Label
            text = str(row.get('anchor_text', ''))
            if not text.strip():
                text = str(row.get('coord_text', ''))
            text_item = QtWidgets.QTableWidgetItem(text)
            self.table.setItem(row_idx, 2, text_item)

            # Confidence (color-coded)
            conf = float(row['conf'])
            conf_item = QtWidgets.QTableWidgetItem(f"{conf:.1%}")
            conf_item.setData(QtCore.Qt.UserRole, conf)

            if conf < 0.6:
                conf_item.setForeground(QtGui.QColor('#ff4444'))
            elif conf < 0.8:
                conf_item.setForeground(QtGui.QColor('#ff8800'))
            else:
                conf_item.setForeground(QtGui.QColor('#44ff44'))

            self.table.setItem(row_idx, 3, conf_item)

            # Risk Score (color-coded and sortable) - Adjusted thresholds
            risk = float(row['risk_score'])
            risk_item = QtWidgets.QTableWidgetItem(f"{risk:.0%}")
            risk_item.setData(QtCore.Qt.UserRole, risk)

            if risk > 0.20:  # High priority (>20%)
                risk_item.setBackground(QtGui.QColor(255, 100, 100))
                risk_item.setForeground(QtGui.QColor(255, 255, 255))
                risk_item.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Bold))
            elif risk >= 0.10:  # Medium priority (10-20%)
                risk_item.setBackground(QtGui.QColor(255, 200, 100))
                risk_item.setForeground(QtGui.QColor(0, 0, 0))
            else:  # Low priority (<10%)
                risk_item.setForeground(QtGui.QColor(100, 200, 100))

            self.table.setItem(row_idx, 4, risk_item)

            # Status Icon - Adjusted thresholds
            risk_factors = str(row.get('risk_factors', 'OK'))
            if risk > 0.20:
                status = "❌"
            elif risk >= 0.10:
                status = "⚠️"
            else:
                status = "✅"

            status_item = QtWidgets.QTableWidgetItem(status)
            status_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row_idx, 5, status_item)

            # Problems/Risk Factors
            problems_item = QtWidgets.QTableWidgetItem(risk_factors)
            self.table.setItem(row_idx, 6, problems_item)

            # Page
            page_item = QtWidgets.QTableWidgetItem(str(int(row.get('page', 1))))
            page_item.setData(QtCore.Qt.UserRole, int(row.get('page', 1)))
            self.table.setItem(row_idx, 7, page_item)

            # Coordinate Text
            coord_text_item = QtWidgets.QTableWidgetItem(str(row.get('coord_text', '')))
            self.table.setItem(row_idx, 8, coord_text_item)

        self.table.setSortingEnabled(True)  # Re-enable sorting

        # Sort by risk (column 4) descending by default
        self.table.sortItems(4, QtCore.Qt.DescendingOrder)

        self._update_info_label(len(df), len(df))

    def _apply_filters(self):
        """Apply filters to the table"""
        class_filter = self.class_filter.currentText()
        risk_filter = self.risk_filter.currentText()
        conf_filter = self.conf_filter.currentText()
        page_filter = self.page_filter.currentText()
        search_text = self.search_input.text().lower()

        total_rows = self.table.rowCount()
        visible_count = 0

        for row in range(total_rows):
            show = True

            # Class filter
            if class_filter != "Alle Klassen":
                cls_item = self.table.item(row, 1)
                if not cls_item or cls_item.text() != class_filter:
                    show = False

            # Risk filter - Adjusted thresholds
            if show and risk_filter != "Alle":
                risk_item = self.table.item(row, 4)
                if risk_item:
                    risk = risk_item.data(QtCore.Qt.UserRole)
                    if risk_filter == "❌ Sofort prüfen (>20%)" and risk <= 0.20:
                        show = False
                    elif risk_filter == "⚠️ Bald prüfen (10-20%)" and (risk < 0.10 or risk > 0.20):
                        show = False
                    elif risk_filter == "✅ Gut erkannt (<10%)" and risk >= 0.10:
                        show = False

            # Confidence filter
            if show and conf_filter != "Alle":
                conf_item = self.table.item(row, 3)
                if conf_item:
                    conf = conf_item.data(QtCore.Qt.UserRole)
                    if conf_filter == "Niedrig (<60%)" and conf >= 0.6:
                        show = False
                    elif conf_filter == "Mittel (60-80%)" and (conf < 0.6 or conf >= 0.8):
                        show = False
                    elif conf_filter == "Hoch (≥80%)" and conf < 0.8:
                        show = False

            # Page filter
            if show and page_filter != "Alle Seiten":
                page_item = self.table.item(row, 7)
                if not page_item or page_item.text() != page_filter:
                    show = False

            # Search filter
            if show and search_text:
                text_item = self.table.item(row, 2)
                coord_item = self.table.item(row, 8)
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
        self.risk_filter.setCurrentIndex(0)
        self.conf_filter.setCurrentIndex(0)
        self.page_filter.setCurrentIndex(0)
        self.search_input.clear()

    def _update_info_label(self, visible: int, total: int):
        """Update the info label"""
        if visible == total:
            self.info_label.setText(f"Zeige {total} Erkennungen")
        else:
            self.info_label.setText(f"Zeige {visible} von {total} Erkennungen")

    def _on_row_double_clicked(self, row: int, column: int):
        """Handle double-click on a table row - jump to element in UI"""
        row_id_item = self.table.item(row, 0)
        page_item = self.table.item(row, 7)

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
        self.workspace._set_status(f"→ Row ID {row_id} auf Seite {page}")

    def _open_full_validation(self):
        """Open the full validation dialog"""
        self.close()  # Close quick inspector
        self.workspace._run_validation()  # Trigger existing full validation

    def _export_to_csv(self):
        """Export the current (filtered) table to CSV"""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Prüfbericht exportieren",
            "erkennungsqualitaet_bericht.csv",
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
                "Export erfolgreich",
                f"Prüfbericht erfolgreich exportiert.\n\nDatei: {filename}\n\nSie können diese Datei jetzt in Excel öffnen."
            )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Export fehlgeschlagen",
                f"Fehler beim Exportieren:\n{str(e)}"
            )
