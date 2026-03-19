"""
UI - Benutzeroberflaeche fuer RailDoc Studio

Dieses Paket enthaelt alle PyQt5-basierten UI-Komponenten fuer die
Gleisplanextraktion und -bearbeitung.

Hauptfenster:
    SetupAndRunWindow: Startfenster fuer PDF-Auswahl und Analyse
    AuditingWindow: Bearbeitungsfenster mit Tab-Verwaltung

Wichtige Widgets:
    WorkspaceWidget: Haupt-Bearbeitungsbereich pro Layout
    InteractiveGraphicsView: Zoombare Bildansicht mit Erkennungsoverlays
    AuditingTreeWidget: Tabelle aller Erkennungen mit Bearbeitung

Dialoge:
    QualityInspectorDialog: Qualitaetsanalyse und Risikobewertung
    OCRAdjustmentDialog: Manuelle OCR-Korrektur mit Auto-Learning
    NewSymbolDialog: Definition benutzerdefinierter Symbole
    EnhancedValidationResultsDialog: Validierungsergebnisse

Themes:
    DARK_QSS, LIGHT_QSS: Stylesheet-Definitionen

Abhaengigkeiten:
    PyQt5, pandas, numpy
"""
from .setup_window import SetupAndRunWindow
from .auditing_window import AuditingWindow
