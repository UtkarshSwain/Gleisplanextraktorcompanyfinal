# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Theme Stylesheets for dark and light modes.
"""
DARK_QSS = """
QMainWindow, QWidget { background-color: #2b2b2b; color: #cccccc; }
QPushButton { background-color: #4a4a4a; color: #ffffff; border: 1px solid #555555; border-radius: 4px; padding: 5px 10px; }
QPushButton:hover { background-color: #5a5a5a; }
QPushButton:pressed { background-color: #3a3a3a; }
QLabel { color: #cccccc; }
QComboBox { background-color: #4a4a4a; color: #ffffff; border: 1px solid #555555; border-radius: 4px; padding: 1px 0 1px 3px; selection-background-color: #009999; selection-color: #ffffff; }
QComboBox::drop-down { border: 0px; width: 20px; }
QComboBox QAbstractItemView { background-color: #4a4a4a; color: #ffffff; selection-background-color: #009999; }
QProgressBar { background-color: #4a4a4a; color: #ffffff; border: 1px solid #555555; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background-color: #009999; border-radius: 4px; }
QTableView { background-color: #3c3c3c; color: #cccccc; gridline-color: #555555; selection-background-color: #009999; selection-color: #ffffff; border: 1px solid #4a4a4a; }
QHeaderView::section { background-color: #4a4a4a; color: #ffffff; padding: 4px; border: 1px solid #555555; border-bottom: 1px solid #3c3c3c; }
QTreeWidget { background-color: #3c3c3c; color: #cccccc; gridline-color: #555555; selection-background-color: #009999; selection-color: #ffffff; border: 1px solid #4a4a4a; }
QTreeWidget::item:selected { background-color: #009999; color: #ffffff; }
QTreeWidget::item:hover { background-color: #4a4a4a; }
QPlainTextEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #4a4a4a; }
QGraphicsView { border: 1px solid #4a4a4a; }
QSpinBox, QSlider { background-color: #4a4a4a; color: #ffffff; border: 1px solid #555555; border-radius: 4px; padding: 1px 0 1px 3px; }
QSpinBox::up-button, QSpinBox::down-button { background-color: #5a5a5a; border: 1px solid #666666; border-radius: 2px; }
QSlider::groove:horizontal { border: 1px solid #555555; height: 8px; background: #4a4a4a; margin: 2px 0; border-radius: 4px; }
QSlider::handle:horizontal { background: #009999; border: 1px solid #009999; width: 18px; margin: -5px 0; border-radius: 9px; }
QSplitter::handle { background-color: #555555; }
QSplitter::handle:hover { background-color: #009999; }
QMenuBar { background-color: #2b2b2b; color: #cccccc; }
QMenuBar::item:selected { background-color: #009999; color: #ffffff; }
QMenu { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; }
QMenu::item:selected { background-color: #009999; color: #ffffff; }

QTabWidget::pane {
    /* This is the container for the tab content */
    border-top: 1px solid #4a4a4a;
}

QTabBar::tab {
    /* This is the inactive tab */
    background-color: #4a4a4a;
    color: #cccccc;
    border: 1px solid #555555;
    border-bottom: 0; /* No bottom border on inactive tabs */
    padding: 5px 15px; /* Give it some space */
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    /* This is the active/selected tab */
    background-color: #2b2b2b; /* Match the main window background */
    color: #ffffff; /* Make the active tab text brighter */
    border: 1px solid #4a4a4a;
    border-bottom-color: #2b2b2b; /* "Connects" the tab to the pane below */
}

QTabBar::tab:hover:!selected {
    /* This is the hover state for inactive tabs */
    background-color: #5a5a5a;
}
/* --- ADD THIS NEW STYLE FOR THE INFO BOX --- */
#compareInfoLabel {
    background-color: #3c3c3c; /* Dark info box background */
    color: #cccccc;
    padding: 10px;
    border: 1px solid #555555;
    border-radius: 5px;
}
/* --- END OF NEW STYLE --- */
"""

LIGHT_QSS = """
QMainWindow, QWidget { background-color: #f0f0f0; color: #333333; }
QPushButton { background-color: #e0e0e0; color: #000000; border: 1px solid #c0c0c0; border-radius: 4px; padding: 5px 10px; }
QPushButton:hover { background-color: #d0d0d0; }
QPushButton:pressed { background-color: #c0c0c0; }
QLabel { color: #333333; }
QComboBox { background-color: #e0e0e0; color: #000000; border: 1px solid #c0c0c0; border-radius: 4px; padding: 1px 0 1px 3px; selection-background-color: #80e0e0; selection-color: #000000; }
QComboBox::drop-down { border: 0px; width: 20px; }
QComboBox QAbstractItemView { background-color: #e0e0e0; color: #000000; selection-background-color: #80e0e0; }
QProgressBar { background-color: #e0e0e0; color: #333333; border: 1px solid #c0c0c0; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background-color: #80e0e0; border-radius: 4px; }
QTableView { background-color: #ffffff; color: #333333; gridline-color: #e0e0e0; selection-background-color: #80e0e0; selection-color: #000000; border: 1px solid #c0c0c0; }
QHeaderView::section { background-color: #e0e0e0; color: #000000; padding: 4px; border: 1px solid #c0c0c0; border-bottom: 1px solid #ffffff; }
QTreeWidget { background-color: #ffffff; color: #333333; gridline-color: #e0e0e0; selection-background-color: #80e0e0; selection-color: #000000; border: 1px solid #c0c0c0; }
QTreeWidget::item:selected { background-color: #80e0e0; color: #000000; }
QTreeWidget::item:hover { background-color: #f0f0f0; }
QPlainTextEdit { background-color: #ffffff; color: #333333; border: 1px solid #c0c0c0; }
QGraphicsView { border: 1px solid #c0c0c0; }
QSpinBox, QSlider { background-color: #e0e0e0; color: #000000; border: 1px solid #c0c0c0; border-radius: 4px; padding: 1px 0 1px 3px; }
QSpinBox::up-button, QSpinBox::down-button { background-color: #d0d0d0; border: 1px solid #c0c0c0; border-radius: 2px; }
QSlider::groove:horizontal { border: 1px solid #c0c0c0; height: 8px; background: #e0e0e0; margin: 2px 0; border-radius: 4px; }
QSlider::handle:horizontal { background: #80e0e0; border: 1px solid #80e0e0; width: 18px; margin: -5px 0; border-radius: 9px; }
QSplitter::handle { background-color: #c0c0c0; }
QSplitter::handle:hover { background-color: #80e0e0; }
QMenuBar { background-color: #f0f0f0; color: #333333; }
QMenuBar::item:selected { background-color: #80e0e0; color: #000000; }
QMenu { background-color: #ffffff; color: #333333; border: 1px solid #c0c0c0; }
/* --- ADD ALL THESE STYLES TO THE END --- */
QTabWidget::pane {
    /* This is the container for the tab content */
    border-top: 1px solid #c0c0c0;
}

QTabBar::tab {
    /* This is the inactive tab */
    background-color: #e0e0e0;
    color: #333333;
    border: 1px solid #c0c0c0;
    border-bottom: 0; /* No bottom border on inactive tabs */
    padding: 5px 15px; /* Give it some space */
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    /* This is the active/selected tab */
    background-color: #f0f0f0; /* Match main light background */
    color: #000000;
    border-bottom-color: #f0f0f0; /* "Connects" the tab to the pane below */
}

QTabBar::tab:hover:!selected {
    /* This is the hover state for inactive tabs */
    background-color: #d0d0d0;
}
/* --- ADD THIS NEW STYLE FOR THE INFO BOX --- */
#compareInfoLabel {
    background-color: #e8f4f8; /* Original light blue */
    color: #333333;
    padding: 10px;
    border: 1px solid #c0c0c0;
    border-radius: 5px;
}
/* --- END OF NEW STYLE --- */
"""