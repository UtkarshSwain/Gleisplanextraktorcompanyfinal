"""
Database viewer dialogs for Gleisplanextraktor.
Provides UI for viewing and managing saved workspaces and database contents.
"""
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QTabWidget, QWidget, QHeaderView, QMessageBox,
    QGroupBox, QFormLayout, QSplitter, QTextEdit, QComboBox, QLineEdit,
    QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Optional, List, Dict
import json
import shutil
from pathlib import Path
from utils.dpi_utils import get_adaptive_window_size, center_window


class SavedWorkspacesDialog(QDialog):
    """
    Simple dialog for quickly loading a saved workspace.
    Accessed from File Menu -> "Gespeicherte Arbeit laden..."
    """

    # Signal emitted when user wants to load a workspace
    workspace_selected = pyqtSignal(str)  # layout_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gespeicherte Arbeit laden")

        # Adaptive sizing for different DPI settings
        w, h = get_adaptive_window_size(500, 400, max_screen_pct=0.50)
        self.setMinimumSize(w, h)
        center_window(self)

        # Enable standard window features: minimize, maximize, close buttons
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )

        # Make window resizable
        self.setSizeGripEnabled(True)

        self.selected_layout = None
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Wählen Sie einen gespeicherten Arbeitsbereich:")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        # Table for workspaces
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Layout Name", "Letzte Änderung", "Erkennungen", "Status"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Enable user-adjustable columns
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Info panel
        self.info_label = QLabel("Wählen Sie einen Eintrag aus der Liste.")
        self.info_label.setStyleSheet("color: gray; padding: 5px;")
        layout.addWidget(self.info_label)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.clicked.connect(self._load_data)
        btn_layout.addWidget(self.btn_refresh)

        btn_layout.addStretch()

        self.btn_delete = QPushButton("Löschen")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_layout.addWidget(self.btn_delete)

        self.btn_load = QPushButton("Laden")
        self.btn_load.setEnabled(False)
        self.btn_load.setDefault(True)
        self.btn_load.clicked.connect(self._on_load)
        btn_layout.addWidget(self.btn_load)

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _load_data(self):
        """Load workspace data from database."""
        self.table.setRowCount(0)

        try:
            from database_sqlite import get_connection

            conn = get_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT t.layout_name, w.last_modified,
                           LENGTH(w.edited_data_json) as data_size,
                           w.edited_data_json,
                           CASE WHEN w.track_skeleton IS NOT NULL THEN 1 ELSE 0 END as has_skeleton
                    FROM workspaces w
                    JOIN track_layouts t ON w.layout_id = t.id
                    ORDER BY w.last_modified DESC
                """)

                rows = cursor.fetchall()
            finally:
                conn.close()

            if not rows:
                self.info_label.setText("Keine gespeicherten Arbeitsbereiche gefunden.")
                return

            self.table.setRowCount(len(rows))

            for i, row in enumerate(rows):
                # Layout name
                name_item = QTableWidgetItem(row['layout_name'])
                name_item.setData(Qt.UserRole, row['layout_name'])
                self.table.setItem(i, 0, name_item)

                # Last modified
                last_mod = row['last_modified'] or "Unbekannt"
                if isinstance(last_mod, str) and len(last_mod) > 16:
                    last_mod = last_mod[:16]  # Trim to date + time
                self.table.setItem(i, 1, QTableWidgetItem(last_mod))

                # Detection count
                try:
                    data = json.loads(row['edited_data_json'])
                    count = len(data) if isinstance(data, list) else 0
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    pass  # Silent fail for malformed JSON
                    count = 0
                self.table.setItem(i, 2, QTableWidgetItem(str(count)))

                # Status
                status_parts = []
                if row['has_skeleton']:
                    status_parts.append("Track")
                if count > 0:
                    status_parts.append(f"{count} Obj.")
                status = ", ".join(status_parts) if status_parts else "-"
                self.table.setItem(i, 3, QTableWidgetItem(status))

            self.info_label.setText(f"{len(rows)} gespeicherte Arbeitsbereiche gefunden.")

        except Exception as e:
            self.info_label.setText(f"Fehler beim Laden: {e}")

    def _on_selection_changed(self):
        """Handle selection change."""
        selected = self.table.selectedItems()
        has_selection = len(selected) > 0
        self.btn_load.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

        if has_selection:
            row = self.table.currentRow()
            name = self.table.item(row, 0).data(Qt.UserRole)
            self.selected_layout = name
            self.info_label.setText(f"Ausgewählt: {name}")

    def _on_double_click(self):
        """Handle double-click to load."""
        self._on_load()

    def _on_load(self):
        """Load selected workspace."""
        if self.selected_layout:
            self.workspace_selected.emit(self.selected_layout)
            self.accept()

    def _on_delete(self):
        """Delete selected workspace."""
        if not self.selected_layout:
            return

        reply = QMessageBox.question(
            self,
            "Löschen bestätigen",
            f"Möchten Sie '{self.selected_layout}' wirklich löschen?\n\n"
            "Alle gespeicherten Daten gehen verloren!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                from database_sqlite import delete_workspace_data
                delete_workspace_data(self.selected_layout)
                self._load_data()
                self.selected_layout = None
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Löschen fehlgeschlagen: {e}")


class DatabaseManagerDialog(QDialog):
    """
    Full database manager dialog with tabs for all tables.
    Accessed from Tools Menu -> "Datenbank-Manager..."
    """

    workspace_selected = pyqtSignal(str)  # layout_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datenbank-Manager")

        # Adaptive sizing for different DPI settings
        w, h = get_adaptive_window_size(800, 600, max_screen_pct=0.70)
        self.setMinimumSize(w, h)
        center_window(self)

        # Enable standard window features: minimize, maximize, close buttons
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )

        # Make window resizable
        self.setSizeGripEnabled(True)

        self._setup_ui()
        self._load_all_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Database info header
        info_layout = QHBoxLayout()
        self.db_path_label = QLabel()
        self.db_path_label.setStyleSheet("color: gray;")
        info_layout.addWidget(self.db_path_label)
        info_layout.addStretch()

        self.db_size_label = QLabel()
        self.db_size_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.db_size_label)
        layout.addLayout(info_layout)

        # Tab widget for different tables
        self.tabs = QTabWidget()

        # Tab 1: Workspaces (main)
        self.workspaces_tab = self._create_workspaces_tab()
        self.tabs.addTab(self.workspaces_tab, "Arbeitsbereiche")

        # Tab 2: Custom Symbols
        self.symbols_tab = self._create_symbols_tab()
        self.tabs.addTab(self.symbols_tab, "Eigene Symbole")

        # Tab 3: Validation Log
        self.validation_tab = self._create_validation_tab()
        self.tabs.addTab(self.validation_tab, "Validierung")

        # Tab 4: Manual Corrections
        self.corrections_tab = self._create_corrections_tab()
        self.tabs.addTab(self.corrections_tab, "Korrekturen")

        # Tab 5: Statistics
        self.stats_tab = self._create_stats_tab()
        self.tabs.addTab(self.stats_tab, "Statistiken")

        layout.addWidget(self.tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        btn_refresh = QPushButton("Aktualisieren")
        btn_refresh.clicked.connect(self._load_all_data)
        btn_layout.addWidget(btn_refresh)

        btn_layout.addStretch()

        btn_clear_all = QPushButton("Alle Daten löschen")
        btn_clear_all.setStyleSheet("background-color: #d9534f; color: white;")
        btn_clear_all.setToolTip("Löscht ALLE Daten aus der Datenbank!")
        btn_clear_all.clicked.connect(self._on_clear_all)
        btn_layout.addWidget(btn_clear_all)

        btn_close = QPushButton("Schließen")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _create_workspaces_tab(self) -> QWidget:
        """Create the workspaces tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Table
        self.workspaces_table = QTableWidget()
        self.workspaces_table.setColumnCount(6)
        self.workspaces_table.setHorizontalHeaderLabels([
            "Layout Name", "Letzte Änderung", "Datengröße",
            "Erkennungen", "Track Skeleton", "Dimensionen"
        ])
        self.workspaces_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.workspaces_table.setSelectionMode(QTableWidget.SingleSelection)
        self.workspaces_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Enable user-adjustable columns
        self.workspaces_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.workspaces_table.horizontalHeader().setStretchLastSection(True)
        self.workspaces_table.horizontalHeader().setSortIndicatorShown(True)
        self.workspaces_table.setSortingEnabled(True)
        self.workspaces_table.doubleClicked.connect(self._on_workspace_double_click)
        layout.addWidget(self.workspaces_table)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_load = QPushButton("Laden")
        btn_load.clicked.connect(self._on_load_workspace)
        btn_layout.addWidget(btn_load)

        btn_export = QPushButton("Als JSON exportieren")
        btn_export.clicked.connect(self._on_export_workspace)
        btn_layout.addWidget(btn_export)

        btn_layout.addStretch()

        btn_delete = QPushButton("Löschen")
        btn_delete.clicked.connect(self._on_delete_workspace)
        btn_layout.addWidget(btn_delete)

        layout.addLayout(btn_layout)

        return widget

    def _create_symbols_tab(self) -> QWidget:
        """Create the custom symbols tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.symbols_table = QTableWidget()
        self.symbols_table.setColumnCount(5)
        self.symbols_table.setHorizontalHeaderLabels([
            "Symbol Name", "Hat Text", "Text Position", "Erstellt", "Aktualisiert"
        ])
        self.symbols_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.symbols_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Enable user-adjustable columns
        self.symbols_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.symbols_table.horizontalHeader().setStretchLastSection(True)
        self.symbols_table.horizontalHeader().setSortIndicatorShown(True)
        self.symbols_table.setSortingEnabled(True)
        layout.addWidget(self.symbols_table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_delete_sym = QPushButton("Symbol löschen")
        btn_delete_sym.clicked.connect(self._on_delete_symbol)
        btn_layout.addWidget(btn_delete_sym)

        layout.addLayout(btn_layout)

        return widget

    def _create_validation_tab(self) -> QWidget:
        """Create the validation log tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Layout:"))
        self.validation_filter = QComboBox()
        self.validation_filter.currentTextChanged.connect(self._load_validation_data)
        filter_layout.addWidget(self.validation_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.validation_table = QTableWidget()
        self.validation_table.setColumnCount(5)
        self.validation_table.setHorizontalHeaderLabels([
            "Typ", "Schweregrad", "Nachricht", "Zeile", "Erstellt"
        ])
        self.validation_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.validation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Enable user-adjustable columns
        self.validation_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.validation_table.horizontalHeader().setStretchLastSection(True)
        self.validation_table.horizontalHeader().setSortIndicatorShown(True)
        self.validation_table.setSortingEnabled(True)
        layout.addWidget(self.validation_table)

        return widget

    def _create_corrections_tab(self) -> QWidget:
        """Create the manual corrections tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Layout:"))
        self.corrections_filter = QComboBox()
        self.corrections_filter.currentTextChanged.connect(self._load_corrections_data)
        filter_layout.addWidget(self.corrections_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.corrections_table = QTableWidget()
        self.corrections_table.setColumnCount(6)
        self.corrections_table.setHorizontalHeaderLabels([
            "Zeile", "Spalte", "Alt", "Neu", "Typ", "Datum"
        ])
        self.corrections_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.corrections_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # Enable user-adjustable columns
        self.corrections_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.corrections_table.horizontalHeader().setStretchLastSection(True)
        self.corrections_table.horizontalHeader().setSortIndicatorShown(True)
        self.corrections_table.setSortingEnabled(True)
        layout.addWidget(self.corrections_table)

        return widget

    def _create_stats_tab(self) -> QWidget:
        """Create the statistics tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Stats display
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setStyleSheet("font-family: monospace;")
        layout.addWidget(self.stats_text)

        return widget

    def _load_all_data(self):
        """Load data for all tabs."""
        self._update_db_info()
        self._load_workspaces_data()
        self._load_symbols_data()
        self._load_layout_filters()
        self._load_stats_data()

    def _update_db_info(self):
        """Update database info labels."""
        try:
            from database_sqlite import DB_PATH
            db_path = Path(DB_PATH)

            self.db_path_label.setText(f"Pfad: {db_path}")

            if db_path.exists():
                size_kb = db_path.stat().st_size / 1024
                if size_kb > 1024:
                    self.db_size_label.setText(f"Größe: {size_kb/1024:.1f} MB")
                else:
                    self.db_size_label.setText(f"Größe: {size_kb:.1f} KB")
            else:
                self.db_size_label.setText("Datenbank nicht gefunden")
        except Exception as e:
            self.db_path_label.setText(f"Fehler: {e}")

    def _load_workspaces_data(self):
        """Load workspaces table data."""
        self.workspaces_table.setRowCount(0)

        try:
            from database_sqlite import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT t.layout_name, w.last_modified,
                       LENGTH(w.edited_data_json) as data_size,
                       w.edited_data_json,
                       CASE WHEN w.track_skeleton IS NOT NULL THEN 'Ja' ELSE 'Nein' END as has_skeleton,
                       CASE WHEN w.image_dimensions IS NOT NULL THEN 'Ja' ELSE 'Nein' END as has_dims
                FROM workspaces w
                JOIN track_layouts t ON w.layout_id = t.id
                ORDER BY w.last_modified DESC
            """)

            rows = cursor.fetchall()
            conn.close()

            self.workspaces_table.setRowCount(len(rows))

            for i, row in enumerate(rows):
                # Layout name
                name_item = QTableWidgetItem(row['layout_name'])
                name_item.setData(Qt.UserRole, row['layout_name'])
                self.workspaces_table.setItem(i, 0, name_item)

                # Last modified
                last_mod = row['last_modified'] or "-"
                if isinstance(last_mod, str) and len(last_mod) > 16:
                    last_mod = last_mod[:16]
                self.workspaces_table.setItem(i, 1, QTableWidgetItem(last_mod))

                # Data size
                size_kb = (row['data_size'] or 0) / 1024
                self.workspaces_table.setItem(i, 2, QTableWidgetItem(f"{size_kb:.1f} KB"))

                # Detection count (with custom symbol breakdown)
                try:
                    data = json.loads(row['edited_data_json'])
                    if isinstance(data, list):
                        total_count = len(data)
                        # Count custom symbols
                        custom_count = sum(1 for d in data if d.get('is_custom_symbol') == True)
                        if custom_count > 0:
                            count_text = f"{total_count} ({custom_count} eigene)"
                        else:
                            count_text = str(total_count)
                    else:
                        count_text = "0"
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    pass  # Silent fail for malformed JSON
                    count_text = "0"
                self.workspaces_table.setItem(i, 3, QTableWidgetItem(count_text))

                # Track skeleton
                self.workspaces_table.setItem(i, 4, QTableWidgetItem(row['has_skeleton']))

                # Dimensions
                self.workspaces_table.setItem(i, 5, QTableWidgetItem(row['has_dims']))

        except Exception as e:
            print(f"Error loading workspaces: {e}")

    def _load_symbols_data(self):
        """Load custom symbols table data."""
        self.symbols_table.setRowCount(0)

        try:
            from database_sqlite import get_all_custom_symbols

            symbols = get_all_custom_symbols()

            self.symbols_table.setRowCount(len(symbols))

            for i, sym in enumerate(symbols):
                name = sym['symbol_name']
                config = sym['config'] or {}

                # Symbol name
                name_item = QTableWidgetItem(name)
                name_item.setData(Qt.UserRole, name)
                self.symbols_table.setItem(i, 0, name_item)

                # Has text
                has_text = "Ja" if config.get('has_text', False) else "Nein"
                self.symbols_table.setItem(i, 1, QTableWidgetItem(has_text))

                # Text position
                text_pos = config.get('text_position', [])
                if isinstance(text_pos, list):
                    text_pos = ", ".join(text_pos)
                self.symbols_table.setItem(i, 2, QTableWidgetItem(str(text_pos)))

                # Created/Updated (not available in current schema, placeholder)
                self.symbols_table.setItem(i, 3, QTableWidgetItem("-"))
                self.symbols_table.setItem(i, 4, QTableWidgetItem("-"))

        except Exception as e:
            print(f"Error loading symbols: {e}")

    def _load_layout_filters(self):
        """Load layout names for filter dropdowns."""
        try:
            from database_sqlite import get_connection

            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT layout_name FROM track_layouts ORDER BY layout_name")
                layouts = [row['layout_name'] for row in cursor.fetchall()]
            finally:
                conn.close()

            # Update validation filter
            self.validation_filter.clear()
            self.validation_filter.addItem("(Alle)")
            self.validation_filter.addItems(layouts)

            # Update corrections filter
            self.corrections_filter.clear()
            self.corrections_filter.addItem("(Alle)")
            self.corrections_filter.addItems(layouts)

        except Exception as e:
            print(f"Error loading layout filters: {e}")

    def _load_validation_data(self):
        """Load validation log data."""
        self.validation_table.setRowCount(0)

        try:
            from database_sqlite import get_connection

            layout_filter = self.validation_filter.currentText()

            conn = get_connection()
            try:
                cursor = conn.cursor()

                if layout_filter and layout_filter != "(Alle)":
                    cursor.execute("""
                        SELECT v.validation_type, v.severity, v.message, v.row_id, v.created_at
                        FROM validation_log v
                        JOIN track_layouts t ON v.layout_id = t.id
                        WHERE t.layout_name = ?
                        ORDER BY v.created_at DESC
                        LIMIT 500
                    """, (layout_filter,))
                else:
                    cursor.execute("""
                        SELECT v.validation_type, v.severity, v.message, v.row_id, v.created_at
                        FROM validation_log v
                        ORDER BY v.created_at DESC
                        LIMIT 500
                    """)

                rows = cursor.fetchall()
            finally:
                conn.close()

            self.validation_table.setRowCount(len(rows))

            for i, row in enumerate(rows):
                self.validation_table.setItem(i, 0, QTableWidgetItem(row['validation_type'] or "-"))

                severity_item = QTableWidgetItem(row['severity'] or "-")
                if row['severity'] == 'ERROR':
                    severity_item.setForeground(QtGui.QColor('red'))
                elif row['severity'] == 'WARNING':
                    severity_item.setForeground(QtGui.QColor('orange'))
                self.validation_table.setItem(i, 1, severity_item)

                self.validation_table.setItem(i, 2, QTableWidgetItem(row['message'] or "-"))
                self.validation_table.setItem(i, 3, QTableWidgetItem(str(row['row_id']) if row['row_id'] else "-"))

                created = row['created_at'] or "-"
                if isinstance(created, str) and len(created) > 16:
                    created = created[:16]
                self.validation_table.setItem(i, 4, QTableWidgetItem(created))

        except Exception as e:
            print(f"Error loading validation data: {e}")

    def _load_corrections_data(self):
        """Load manual corrections data."""
        self.corrections_table.setRowCount(0)

        try:
            from database_sqlite import get_connection

            layout_filter = self.corrections_filter.currentText()

            conn = get_connection()
            try:
                cursor = conn.cursor()

                if layout_filter and layout_filter != "(Alle)":
                    cursor.execute("""
                        SELECT mc.row_id, mc.column_name, mc.old_value, mc.new_value,
                               mc.correction_type, mc.created_at
                        FROM manual_corrections mc
                        JOIN track_layouts t ON mc.layout_id = t.id
                        WHERE t.layout_name = ?
                        ORDER BY mc.created_at DESC
                        LIMIT 500
                    """, (layout_filter,))
                else:
                    cursor.execute("""
                        SELECT mc.row_id, mc.column_name, mc.old_value, mc.new_value,
                               mc.correction_type, mc.created_at
                        FROM manual_corrections mc
                        ORDER BY mc.created_at DESC
                        LIMIT 500
                    """)

                rows = cursor.fetchall()
            finally:
                conn.close()

            self.corrections_table.setRowCount(len(rows))

            for i, row in enumerate(rows):
                self.corrections_table.setItem(i, 0, QTableWidgetItem(str(row['row_id'])))
                self.corrections_table.setItem(i, 1, QTableWidgetItem(row['column_name'] or "-"))
                self.corrections_table.setItem(i, 2, QTableWidgetItem(row['old_value'] or "-"))
                self.corrections_table.setItem(i, 3, QTableWidgetItem(row['new_value'] or "-"))
                self.corrections_table.setItem(i, 4, QTableWidgetItem(row['correction_type'] or "-"))

                created = row['created_at'] or "-"
                if isinstance(created, str) and len(created) > 16:
                    created = created[:16]
                self.corrections_table.setItem(i, 5, QTableWidgetItem(created))

        except Exception as e:
            print(f"Error loading corrections data: {e}")

    def _load_stats_data(self):
        """Load and display statistics."""
        stats_lines = []

        try:
            from database_sqlite import get_connection, DB_PATH

            conn = get_connection()
            try:
                cursor = conn.cursor()

                stats_lines.append("=" * 50)
                stats_lines.append("DATENBANK-STATISTIKEN")
                stats_lines.append("=" * 50)
                stats_lines.append("")

                # Database size
                db_path = Path(DB_PATH)
                if db_path.exists():
                    size_kb = db_path.stat().st_size / 1024
                    stats_lines.append(f"Datenbankgröße: {size_kb:.1f} KB")

                # Count layouts
                cursor.execute("SELECT COUNT(*) as count FROM track_layouts")
                layout_count = cursor.fetchone()['count']
                stats_lines.append(f"Gespeicherte Layouts: {layout_count}")

                # Count workspaces
                cursor.execute("SELECT COUNT(*) as count FROM workspaces")
                workspace_count = cursor.fetchone()['count']
                stats_lines.append(f"Arbeitsbereiche: {workspace_count}")

                # Count custom symbols
                cursor.execute("SELECT COUNT(*) as count FROM custom_symbols")
                symbol_count = cursor.fetchone()['count']
                stats_lines.append(f"Eigene Symbole: {symbol_count}")

                # Count validations
                cursor.execute("SELECT COUNT(*) as count FROM validation_log")
                validation_count = cursor.fetchone()['count']
                stats_lines.append(f"Validierungseinträge: {validation_count}")

                # Count corrections
                cursor.execute("SELECT COUNT(*) as count FROM manual_corrections")
                correction_count = cursor.fetchone()['count']
                stats_lines.append(f"Manuelle Korrekturen: {correction_count}")

                stats_lines.append("")
                stats_lines.append("-" * 50)
                stats_lines.append("ARBEITSBEREICHE DETAILS")
                stats_lines.append("-" * 50)

                # Workspace details
                cursor.execute("""
                    SELECT t.layout_name, w.last_modified,
                           LENGTH(w.edited_data_json) as data_size
                    FROM workspaces w
                    JOIN track_layouts t ON w.layout_id = t.id
                    ORDER BY w.last_modified DESC
                """)

                for row in cursor.fetchall():
                    size_kb = (row['data_size'] or 0) / 1024
                    last_mod = row['last_modified'] or "?"
                    if isinstance(last_mod, str) and len(last_mod) > 16:
                        last_mod = last_mod[:16]
                    stats_lines.append(f"  {row['layout_name']}: {size_kb:.1f} KB ({last_mod})")

                if symbol_count > 0:
                    stats_lines.append("")
                    stats_lines.append("-" * 50)
                    stats_lines.append("EIGENE SYMBOLE")
                    stats_lines.append("-" * 50)

                    cursor.execute("SELECT symbol_name, config_json FROM custom_symbols")
                    for row in cursor.fetchall():
                        config = json.loads(row['config_json']) if row['config_json'] else {}
                        has_text = "mit Text" if config.get('has_text') else "ohne Text"
                        stats_lines.append(f"  {row['symbol_name']}: {has_text}")
            finally:
                conn.close()

        except Exception as e:
            print(f"Error loading stats: {e}")
            stats_lines.append(f"Fehler beim Laden der Statistiken: {e}")

        self.stats_text.setPlainText("\n".join(stats_lines))

    def _on_workspace_double_click(self):
        """Handle double-click on workspace."""
        self._on_load_workspace()

    def _on_load_workspace(self):
        """Load selected workspace."""
        selected = self.workspaces_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie einen Arbeitsbereich aus.")
            return

        row = self.workspaces_table.currentRow()
        layout_name = self.workspaces_table.item(row, 0).data(Qt.UserRole)

        self.workspace_selected.emit(layout_name)
        self.accept()

    def _on_export_workspace(self):
        """Export selected workspace as JSON."""
        selected = self.workspaces_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie einen Arbeitsbereich aus.")
            return

        row = self.workspaces_table.currentRow()
        layout_name = self.workspaces_table.item(row, 0).data(Qt.UserRole)

        # Get save path
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Arbeitsbereich exportieren",
            f"{layout_name}_export.json",
            "JSON Files (*.json)"
        )

        if not file_path:
            return

        try:
            from database_sqlite import get_workspace_data

            result = get_workspace_data(layout_name)
            if result:
                # Handle both old format (3 values) and new format (5 values)
                if len(result) == 3:
                    data, skeleton, dimensions = result
                else:
                    data, skeleton, dimensions, _, _ = result

                export_data = {
                    'layout_name': layout_name,
                    'detections': data,
                    'has_track_skeleton': skeleton is not None,
                    'image_dimensions': dimensions
                }

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)

                QMessageBox.information(self, "Erfolg", f"Exportiert nach:\n{file_path}")
            else:
                QMessageBox.warning(self, "Fehler", "Keine Daten gefunden.")

        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Export fehlgeschlagen: {e}")

    def _on_delete_workspace(self):
        """Delete selected workspace."""
        selected = self.workspaces_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie einen Arbeitsbereich aus.")
            return

        row = self.workspaces_table.currentRow()
        layout_name = self.workspaces_table.item(row, 0).data(Qt.UserRole)

        reply = QMessageBox.question(
            self,
            "Löschen bestätigen",
            f"Möchten Sie '{layout_name}' wirklich löschen?\n\n"
            "Alle gespeicherten Daten gehen verloren!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                from database_sqlite import delete_workspace_data
                delete_workspace_data(layout_name)
                self._load_all_data()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Löschen fehlgeschlagen: {e}")

    def _on_delete_symbol(self):
        """Delete selected custom symbol."""
        selected = self.symbols_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Hinweis", "Bitte wählen Sie ein Symbol aus.")
            return

        row = self.symbols_table.currentRow()
        symbol_name = self.symbols_table.item(row, 0).data(Qt.UserRole)

        reply = QMessageBox.question(
            self,
            "Symbol löschen",
            f"Möchten Sie das Symbol '{symbol_name}' wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                from database_sqlite import delete_custom_symbol
                delete_custom_symbol(symbol_name)
                self._load_symbols_data()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Löschen fehlgeschlagen: {e}")

    def _on_clear_all(self):
        """Clear ALL data from the database."""
        # First confirmation
        reply = QMessageBox.warning(
            self,
            "Alle Daten löschen?",
            "ACHTUNG: Dies löscht ALLE gespeicherten Daten!\n\n"
            "• Alle Arbeitsbereiche\n"
            "• Alle eigenen Symbole\n"
            "• Alle Validierungsprotokolle\n"
            "• Alle Korrekturhistorien\n\n"
            "Diese Aktion kann NICHT rückgängig gemacht werden!\n\n"
            "Sind Sie sicher?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Second confirmation with typed confirmation
        text, ok = QInputDialog.getText(
            self,
            "Bestätigung erforderlich",
            "Geben Sie 'LÖSCHEN' ein, um zu bestätigen:"
        )

        if not ok or text.strip().upper() != "LÖSCHEN":
            QMessageBox.information(self, "Abgebrochen", "Löschvorgang abgebrochen.")
            return

        # Perform deletion
        try:
            from database_sqlite import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # Delete all data (order matters due to foreign keys)
            cursor.execute("DELETE FROM manual_corrections")
            cursor.execute("DELETE FROM quality_metrics")
            cursor.execute("DELETE FROM validation_log")
            cursor.execute("DELETE FROM workspaces")
            cursor.execute("DELETE FROM custom_symbols")
            cursor.execute("DELETE FROM track_layouts")

            conn.commit()
            conn.close()

            # Also delete local symbol files
            base_path = Path(__file__).parent.parent  # Gleisplanextraktorv3 folder

            # Delete custom_symbols.json
            json_path = base_path / "custom_symbols.json"
            if json_path.exists():
                json_path.unlink()
                print("Deleted custom_symbols.json")

            # Delete custom_symbol_templates folder
            templates_dir = base_path / "custom_symbol_templates"
            if templates_dir.exists():
                shutil.rmtree(templates_dir)
                print("Deleted custom_symbol_templates folder")

            QMessageBox.information(
                self,
                "Erfolgreich",
                "Alle Daten wurden gelöscht (inkl. lokale Symbol-Dateien)."
            )

            self._load_all_data()

        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Löschen fehlgeschlagen: {e}")
