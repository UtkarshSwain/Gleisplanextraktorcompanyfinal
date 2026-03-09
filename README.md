# RailDoc Studio - Gleisplan-Modul

Intelligente Eisenbahndokument-Analyse mit automatischer Symbolerkennung und Textextraktion aus Gleisplänen.

## Beschreibung

Der Gleisplanextraktor ist ein spezialisiertes Tool zur automatischen Erkennung und Extraktion von Symbolen aus technischen Eisenbahn-Gleisplänen (PDF). Die Software kombiniert modernste KI-Technologien für Objekterkennung und Texterkennung.

### Hauptfunktionen

- **Symbolerkennung**: YOLOv8-OBB (Oriented Bounding Box) für präzise Erkennung rotierter Symbole
- **Textextraktion**: PaddleOCR für zuverlässige OCR auf technischen Zeichnungen
- **Multi-Page PDF**: Verarbeitung mehrseitiger Gleispläne
- **Interaktive Prüfung**: PyQt5-basierte GUI zur Validierung und Korrektur
- **Datenexport**: Export nach Excel mit konfigurierbaren Spalten
- **Datenbankunterstützung**: SQLite-basierte Speicherung für Projektmanagement

## Technologie-Stack

| Komponente | Technologie |
|------------|-------------|
| Objekterkennung | YOLOv8-OBB (Ultralytics) |
| Textextraktion | PaddleOCR |
| PDF-Verarbeitung | PyMuPDF (fitz) |
| Bildverarbeitung | OpenCV, Pillow, scikit-image |
| Benutzeroberfläche | PyQt5 |
| Datenverarbeitung | Polars, Pandas, NumPy |
| Datenbank | SQLite |

## Installation

Detaillierte Installationsanleitung siehe [installation_guide.txt](installation_guide.txt).

### Schnellstart

```powershell
# 1. Virtual Environment erstellen
py -m venv venv

# 2. Aktivieren
.\venv\Scripts\activate

# 3. PyTorch installieren (CPU)
py -m pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu

# 4. Abhängigkeiten installieren
py -m pip install -r requirements.txt

# 5. Anwendung starten
py main.py
```

## Systemanforderungen

- Windows 10/11 (64-bit)
- Python 3.11.x
- Minimum 8GB RAM (16GB empfohlen)
- 5GB freier Speicherplatz

## Verwendung

1. Anwendung starten: `py main.py`
2. PDF-Gleisplan laden
3. Verarbeitung starten
4. Ergebnisse im Audit-Fenster prüfen und korrigieren
5. Nach Excel exportieren

---

**Entwickelt von:** Utkarsh Swain
**Unternehmen:** Siemens Mobility GmbH
**Version:** 3.0
**Jahr:** 2026

*Nur für internen Gebrauch bei Siemens*
