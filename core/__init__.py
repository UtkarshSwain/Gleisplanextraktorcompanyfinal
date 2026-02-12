# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Core - Kernverarbeitungslogik fuer Gleisplanerkennung

Dieses Paket enthaelt die zentralen Verarbeitungsmodule fuer die
automatische Erkennung und Extraktion von Gleisplansymbolen.

Module:
    pipelineworker: Haupt-Verarbeitungsthread (PDF/Bild -> Erkennungen)
    yolo_detection: YOLOv8 OBB Objekterkennung mit Kachelung
    ocr_engine: PaddleOCR/Tesseract Texterkennung
    linking: Symbol-Koordinaten-Verknuepfung und Fahrtrichtungserkennung
    image_processing: Bildverarbeitungsfunktionen (Crop, Rotation, Enhancement)
    symbol_detector: Benutzerdefinierte Symbolerkennung (Template-Matching)
    pipeline_integration: Integration benutzerdefinierter Symbole in Pipeline

Typischer Ablauf:
    1. PipelineWorker laedt PDF/Bild und konvertiert zu BGR
    2. run_yolo_on_page() erkennt Symbole mit YOLO
    3. OCR-Funktionen extrahieren Text aus Erkennungen
    4. Linking-Funktionen verknuepfen Symbole mit Koordinaten
    5. Ergebnisse werden als DataFrame zurueckgegeben

Abhaengigkeiten:
    ultralytics, paddleocr, cv2, numpy, pandas, PyQt5
"""
from .yolo_detection import run_yolo_on_page
from .ocr_engine import ocr_coordinate_unified, ocr_signal_name
from .linking import link_anchor_to_coord
