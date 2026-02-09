# BENUTZERHANDBUCH - Gleisplanextraktor v3

**RailDoc Studio - Gleisplan-Modul**

```
================================================================================
        Intelligente Eisenbahndokument-Analyse
        Version 1.0 | Stand: Februar 2026
================================================================================
```

**Entwickler:** Utkarsh Swain
**Organisation:** Siemens Mobility GmbH
**Copyright:** 2025-2026

---

## INHALTSVERZEICHNIS

1. [Einfuehrung](#1-einfuehrung)
2. [Schnellstart](#2-schnellstart)
3. [Hauptfenster - Setup](#3-hauptfenster---setup)
4. [Hauptfenster - Bearbeitung](#4-hauptfenster---bearbeitung)
5. [Erkannte Symbole bearbeiten](#5-erkannte-symbole-bearbeiten)
6. [Datenvalidierung](#6-datenvalidierung)
7. [Qualitaetsinspektor](#7-qualitaetsinspektor)
8. [Daten exportieren](#8-daten-exportieren)
9. [Arbeitsbereich speichern/laden](#9-arbeitsbereich-speichernladen)
10. [Eigene Symbole](#10-eigene-symbole)
11. [Design und Einstellungen](#11-design-und-einstellungen)
12. [Erkannte Symbolklassen](#12-erkannte-symbolklassen)
13. [Glossar](#13-glossar)
14. [Fehlerbehebung](#14-fehlerbehebung)
15. [Anhang](#15-anhang)

---

# 1. EINFUEHRUNG

## 1.1 Was ist Gleisplanextraktor?

Der Gleisplanextraktor ist ein KI-gestuetztes Werkzeug zur automatischen Extraktion und Analyse von Eisenbahn-Gleisplaenen. Das System verwendet moderne Computer-Vision-Technologien (YOLO, PaddleOCR) um Symbole, Signale, Koordinaten und andere relevante Informationen aus technischen PDF-Dokumenten zu erkennen.

### Hauptanwendungsfaelle

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GLEISPLANEXTRAKTOR v3                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   PDF-Gleisplan  ──►  KI-Analyse  ──►  Strukturierte Daten         │
│                                                                     │
│   ┌─────────┐       ┌─────────┐       ┌─────────────────────┐      │
│   │ Signale │       │  YOLO   │       │ Excel-Export        │      │
│   │ Weichen │  ──►  │  OCR    │  ──►  │ Datenbank-Speicher  │      │
│   │ Coords  │       │ Linking │       │ Validierungsbericht │      │
│   └─────────┘       └─────────┘       └─────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 1.2 Hauptfunktionen

| Funktion | Beschreibung |
|----------|--------------|
| **Automatische Erkennung** | 13 verschiedene Symbolklassen werden automatisch erkannt |
| **OCR-Texterkennung** | Extrahiert Signalnamen, Koordinaten und andere Textinformationen |
| **Intelligente Verknuepfung** | Verknuepft Symbole automatisch mit zugehoerigen Koordinaten |
| **Fahrtrichtungserkennung** | Bestimmt die Fahrtrichtung basierend auf Gleisskelett |
| **Interaktive Bearbeitung** | Manuelle Korrektur und Feinabstimmung der Ergebnisse |
| **Datenvalidierung** | Automatische Pruefung auf Fehler und Inkonsistenzen |
| **Excel-Export** | Strukturierter Export fuer Weiterverarbeitung |
| **Datenbank-Speicherung** | Persistente Speicherung von Arbeitsbereichen |

## 1.3 Systemanforderungen

### Minimale Anforderungen

| Komponente | Anforderung |
|------------|-------------|
| **Betriebssystem** | Windows 10/11 (64-bit) |
| **Python** | Version 3.11.x |
| **RAM** | 8 GB (16 GB empfohlen) |
| **Festplatte** | 5 GB freier Speicher |
| **Bildschirm** | 1920x1080 (Full HD) empfohlen |

### Unterstuetzte Dateiformate

- **PDF-Dateien** (.pdf) - Primaerformat
- **Bilder** (.png, .jpg, .jpeg, .tiff, .bmp)

## 1.4 Installation

Fuer die Installation folgen Sie bitte der separaten Anleitung:

**Datei:** `installation_guide.txt`

**Kurzuebersicht:**
```
1. Python 3.11.x installieren
2. Virtuelle Umgebung erstellen: py -m venv venv
3. Aktivieren: .\venv\Scripts\activate
4. Abhaengigkeiten installieren: py -m pip install -r requirements.txt
5. Starten: py main.py
```

---

# 2. SCHNELLSTART

Dieser Abschnitt fuehrt Sie durch den typischen Arbeitsablauf in wenigen Minuten.

## 2.1 Anwendung starten

```
┌────────────────────────────────────────────────────────────────────┐
│  SCHRITT 1: Anwendung starten                                      │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. Oeffnen Sie PowerShell oder Eingabeaufforderung               │
│  2. Navigieren Sie zum Projektordner                               │
│  3. Aktivieren Sie die virtuelle Umgebung:                         │
│                                                                    │
│     > .\venv\Scripts\activate                                      │
│                                                                    │
│  4. Starten Sie die Anwendung:                                     │
│                                                                    │
│     > py main.py                                                   │
│                                                                    │
│  Das Setup-Fenster erscheint.                                      │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 2.2 PDF laden

```
┌────────────────────────────────────────────────────────────────────┐
│  SCHRITT 2: PDF-Datei laden                                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Option A: Drag & Drop                                             │
│  ─────────────────────                                             │
│  Ziehen Sie die PDF-Datei direkt in das Fenster                    │
│                                                                    │
│  Option B: Dateiauswahl                                            │
│  ─────────────────────                                             │
│  1. Klicken Sie auf "PDF waehlen..."                              │
│  2. Navigieren Sie zur Datei                                       │
│  3. Klicken Sie auf "Oeffnen"                                     │
│                                                                    │
│  Die erste Seite wird als Vorschau angezeigt.                      │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 2.3 Verarbeitung starten

```
┌────────────────────────────────────────────────────────────────────┐
│  SCHRITT 3: Verarbeitung starten                                   │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. Waehlen Sie das YOLO-Modell (Standard ist voreingestellt)     │
│                                                                    │
│  2. Waehlen Sie die OCR-Engine:                                   │
│     - PaddleOCR (empfohlen fuer deutsche Texte)                    │
│     - Tesseract (Alternative)                                      │
│                                                                    │
│  3. Klicken Sie auf "Verarbeiten"                                  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │ Fortschritt: ████████████░░░░░░░░  60%                   │      │
│  │ Status: Seite 2/3 - OCR laeuft...                       │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                    │
│  Nach Abschluss oeffnet sich das Bearbeitungsfenster.             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## 2.4 Ergebnisse ueberpruefen und exportieren

```
┌────────────────────────────────────────────────────────────────────┐
│  SCHRITT 4: Ergebnisse exportieren                                 │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Im Bearbeitungsfenster:                                           │
│                                                                    │
│  1. Pruefen Sie die erkannten Symbole in der Baumansicht          │
│  2. Korrigieren Sie bei Bedarf falsche Werte                       │
│  3. Klicken Sie auf "Validieren" zur Qualitaetspruefung           │
│  4. Klicken Sie auf "Exportieren" fuer Excel-Export               │
│                                                                    │
│  Fertig! Sie haben erfolgreich einen Gleisplan analysiert.        │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Kompletter Arbeitsablauf (Uebersicht)

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. PDF LADEN    │ ──► │  2. VERARBEITEN  │ ──► │  3. BEARBEITEN   │
│  (Setup-Fenster) │     │  (KI-Pipeline)   │     │ (Bearbeitungs-   │
│                  │     │                  │     │     fenster)     │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                                           │
                                                           ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  6. SPEICHERN    │ ◄── │  5. EXPORTIEREN  │ ◄── │  4. VALIDIEREN   │
│  (Datenbank)     │     │  (Excel)         │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

---

# 3. HAUPTFENSTER - SETUP

Das Setup-Fenster ist der Einstiegspunkt der Anwendung. Hier laden und verarbeiten Sie Ihre Gleisplan-Dokumente.

## 3.1 Benutzeroberflaeche

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RailDoc Studio - Gleisplan-Modul                              [─][□][X]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                                                                   │  │
│  │                    PDF/BILD HIER ABLEGEN                          │  │
│  │                                                                   │  │
│  │              ┌─────────────────────────────────┐                  │  │
│  │              │                                 │                  │  │
│  │              │     [Vorschau der ersten       │                  │  │
│  │              │          Seite]                 │                  │  │
│  │              │                                 │                  │  │
│  │              └─────────────────────────────────┘                  │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  Datei: C:\Pfad\zur\datei.pdf                                          │
│                                                                         │
│  ┌────────────────────┐  ┌────────────────────┐                        │
│  │ PDF waehlen...     │  │ Modell waehlen...  │                        │
│  └────────────────────┘  └────────────────────┘                        │
│                                                                         │
│  OCR-Engine: [PaddleOCR          ▼]                                    │
│                                                                         │
│  [□] Gleisskelett-Erkennung aktivieren                                 │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Fortschritt: ░░░░░░░░░░░░░░░░░░░░  0%                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Status: Bereit                                                         │
│                                                                         │
│           ┌──────────────────┐    ┌──────────────────┐                 │
│           │   Verarbeiten    │    │   Abbrechen      │                 │
│           └──────────────────┘    └──────────────────┘                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3.2 PDF-Datei auswaehlen (Drag & Drop)

### Methode 1: Drag & Drop

1. Oeffnen Sie den Windows Explorer
2. Navigieren Sie zu Ihrer PDF-Datei
3. Ziehen Sie die Datei in das Anwendungsfenster
4. Lassen Sie die Maustaste los

Der Vorschaubereich zeigt die erste Seite des Dokuments an.

### Methode 2: Dateiauswahl-Dialog

1. Klicken Sie auf **"PDF waehlen..."**
2. Navigieren Sie zum Speicherort
3. Waehlen Sie die Datei aus
4. Klicken Sie auf **"Oeffnen"**

### Unterstuetzte Formate

| Format | Dateierweiterung | Hinweise |
|--------|------------------|----------|
| PDF | .pdf | Empfohlen, mehrere Seiten moeglich |
| PNG | .png | Einzelbild |
| JPEG | .jpg, .jpeg | Einzelbild |
| TIFF | .tif, .tiff | Einzelbild |
| BMP | .bmp | Einzelbild |

## 3.3 Modell auswaehlen

Das YOLO-Modell ist fuer die Objekterkennung verantwortlich. In der Regel ist das Standardmodell voreingestellt.

**Standardmodell:** `yolomodel/best.pt`

### Modell wechseln

1. Klicken Sie auf **"Modell waehlen..."**
2. Navigieren Sie zum Modell-Ordner
3. Waehlen Sie eine `.pt`-Datei aus

> **Hinweis:** Verwenden Sie nur kompatible OBB-Modelle (Oriented Bounding Box).

## 3.4 OCR-Engine auswaehlen

Die OCR-Engine erkennt Text in den gefundenen Symbolen.

| Engine | Vorteile | Nachteile |
|--------|----------|-----------|
| **PaddleOCR** | Besser fuer deutsche Umlaute, schneller | Groessere Installation |
| **Tesseract** | Weit verbreitet, stabil | Manchmal ungenauer |

**Empfehlung:** PaddleOCR fuer deutsche Gleisplaene

## 3.5 Verarbeitung starten/abbrechen

### Verarbeitung starten

1. Stellen Sie sicher, dass eine Datei geladen ist
2. Pruefen Sie die Einstellungen (Modell, OCR-Engine)
3. Klicken Sie auf **"Verarbeiten"**

### Verarbeitung abbrechen

- Klicken Sie auf **"Abbrechen"** um die Verarbeitung zu stoppen
- Bereits verarbeitete Seiten gehen verloren

## 3.6 Fortschrittsanzeige

Waehrend der Verarbeitung zeigt die Anwendung:

```
┌─────────────────────────────────────────────────────────────────┐
│ Fortschritt: ████████████░░░░░░░░  60%                          │
└─────────────────────────────────────────────────────────────────┘

Status: Seite 2/3 - YOLO-Erkennung laeuft...
```

### Verarbeitungsschritte

1. **PDF-Rendering** - Seiten werden in Bilder konvertiert (500 DPI)
2. **Tiling** - Grosse Bilder werden in Kacheln unterteilt
3. **YOLO-Erkennung** - Symbole werden erkannt
4. **OCR** - Text wird extrahiert
5. **Linking** - Symbole werden mit Koordinaten verknuepft
6. **Fahrtrichtung** - Richtung wird bestimmt

---

# 4. HAUPTFENSTER - BEARBEITUNG

Nach erfolgreicher Verarbeitung oeffnet sich das Bearbeitungsfenster (Auditing Window).

## 4.1 Uebersicht der Benutzeroberflaeche

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Datei  Bearbeiten  Werkzeuge  Ansicht  Hilfe                     [─][□][X]│
├─────────────────────────────────────────────────────────────────────────────┤
│  [💾][📤][✓][🔍][↩][↪]                                                      │
├──────────────────┬──────────────────────────────────────────────────────────┤
│                  │                                                          │
│  BAUMANSICHT     │              GRAFIKANSICHT                               │
│                  │                                                          │
│  ├─ Seite 1      │    ┌──────────────────────────────────────────────┐     │
│  │  ├─ signal    │    │                                              │     │
│  │  │  ├─ A101   │    │     [Gleisplan-Bild mit Markierungen]       │     │
│  │  │  └─ B202   │    │                                              │     │
│  │  ├─ gks       │    │         ┌───┐                                │     │
│  │  │  └─ 1234   │    │    ──●──│A1 │──●──                          │     │
│  │  └─ coord     │    │         └───┘                                │     │
│  │     └─ 15.492 │    │                                              │     │
│  └─ Seite 2      │    └──────────────────────────────────────────────┘     │
│     └─ ...       │                                                          │
│                  │    ◄ Seite 1 von 3 ►                                    │
│                  │                                                          │
├──────────────────┴──────────────────────────────────────────────────────────┤
│  Datei: gleisplan.pdf | Zeilen: 45 | Auswahl: A101 (Signal)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 4.2 Tab-Verwaltung (mehrere PDFs)

Sie koennen mehrere PDF-Dateien gleichzeitig oeffnen:

```
┌───────────────┬───────────────┬───────────────┬─────┐
│ gleisplan.pdf │ dokument2.pdf │ test.pdf      │  +  │
└───────────────┴───────────────┴───────────────┴─────┘
```

### Aktionen

| Aktion | Beschreibung |
|--------|--------------|
| **Tab anklicken** | Zwischen Dokumenten wechseln |
| **Tab schliessen** | X-Symbol auf dem Tab klicken |
| **Tab verschieben** | Tab ziehen um Position zu aendern |

## 4.3 Seitennavigation

Bei mehrseitigen Dokumenten:

```
    ┌─────┐                           ┌─────┐
    │  ◄  │    Seite 2 von 5         │  ►  │
    └─────┘                           └─────┘
    Zurueck                           Weiter
```

### Tastaturkuerzel

| Taste | Aktion |
|-------|--------|
| `Bild↑` | Vorherige Seite |
| `Bild↓` | Naechste Seite |
| `Pos1` | Erste Seite |
| `Ende` | Letzte Seite |

## 4.4 Baumansicht (Tree View)

Die Baumansicht zeigt alle erkannten Elemente hierarchisch an:

```
├─ Seite 1                          ← Seitenebene
│  ├─ signal (5)                    ← Klassenebene (Anzahl)
│  │  ├─ 🟢 A101 @ 15.492          ← Element (Risiko, Name, Koordinate)
│  │  ├─ 🟡 B202 @ 16.123
│  │  └─ 🔴 C303 @ ?               ← Rot = Problem
│  ├─ gks_gesteuert (3)
│  │  └─ ...
│  └─ coordinate (8)
│     └─ ...
└─ Seite 2
   └─ ...
```

### Risikoindikatoren

| Symbol | Bedeutung | Handlung erforderlich |
|--------|-----------|----------------------|
| 🟢 | Gut erkannt (Risiko 0.0-0.3) | Keine |
| 🟡 | Pruefung empfohlen (0.3-0.6) | Ueberpruefen |
| 🔴 | Problem erkannt (0.6-1.0) | Korrektur noetig |

### Element auswaehlen

1. Klicken Sie auf ein Element in der Baumansicht
2. Das Element wird in der Grafikansicht hervorgehoben
3. Die Details erscheinen im Eigenschafts-Panel

## 4.5 Grafikansicht (Graphics View)

Die Grafikansicht zeigt das Gleisplan-Bild mit ueberlagerten Erkennungsrahmen.

### Navigation

| Aktion | Maus/Tastatur |
|--------|---------------|
| **Zoomen** | Mausrad drehen |
| **Verschieben** | Rechte Maustaste + Ziehen |
| **Element auswaehlen** | Linksklick auf Rahmen |
| **Zoom zuruecksetzen** | Doppelklick |

### Farben der Erkennungsrahmen

| Farbe | Symbolklasse |
|-------|--------------|
| Gruen | Signal |
| Blau | GKS (gesteuert/festkodiert) |
| Orange | Weichenblock |
| Rot | Coordinate |
| Cyan | Haltepunkt |
| Magenta | Eigene Symbole |

## 4.6 Tabellen-Editor

Unter der Grafikansicht befindet sich eine editierbare Tabelle mit allen erkannten Elementen.

```
┌──────┬──────────┬─────────────┬────────────┬──────────────┬─────────┐
│ ID   │ Klasse   │ Bezeichnung │ Koordinate │ Fahrtrichtung│ Konfidenz│
├──────┼──────────┼─────────────┼────────────┼──────────────┼─────────┤
│ 1    │ signal   │ A101        │ 15.492     │ A            │ 0.95    │
│ 2    │ signal   │ B202        │ 16.123     │ B            │ 0.87    │
│ 3    │ gks      │ 1234        │ 15.500     │ -            │ 0.92    │
└──────┴──────────┴─────────────┴────────────┴──────────────┴─────────┘
```

### Zellen bearbeiten

1. Doppelklicken Sie auf eine Zelle
2. Geben Sie den neuen Wert ein
3. Druecken Sie `Enter` zum Bestaetigen

### Editierbare Spalten

| Spalte | Editierbar | Beschreibung |
|--------|------------|--------------|
| Klasse | Nein | Symboltyp |
| Bezeichnung | Ja | OCR-Text (anchor_text) |
| Koordinate | Ja | Koordinatenwert (coord_text) |
| Fahrtrichtung | Ja | A oder B |

## 4.7 Eigenschaften-Panel

Bei Auswahl eines Elements erscheinen detaillierte Eigenschaften:

```
┌─────────────────────────────────────┐
│  EIGENSCHAFTEN                      │
├─────────────────────────────────────┤
│  Klasse:        signal              │
│  Bezeichnung:   A101                │
│  Koordinate:    15.492              │
│  Fahrtrichtung: A                   │
│  Konfidenz:     95.2%               │
│  Position:      (1234, 567)         │
│  Winkel:        0°                  │
│  Farbe:         rot                 │
└─────────────────────────────────────┘
```

---

# 5. ERKANNTE SYMBOLE BEARBEITEN

## 5.1 Symbole im Baum auswaehlen

### Einzelauswahl

- Klicken Sie auf ein Element in der Baumansicht
- Das Element wird in der Grafikansicht hervorgehoben

### Mehrfachauswahl

- `Strg` + Klick: Einzelne Elemente hinzufuegen
- `Shift` + Klick: Bereich auswaehlen

## 5.2 Bounding-Boxen anpassen

Die Bounding-Box definiert den Erkennungsbereich eines Symbols.

### Groesse aendern

1. Waehlen Sie das Element aus
2. In der Grafikansicht erscheinen Anfasser (kleine Quadrate)
3. Ziehen Sie einen Anfasser um die Groesse anzupassen

```
    ■─────────────────■
    │                 │
    │    [Symbol]     │
    │                 │
    ■─────────────────■
    ↑                 ↑
    Anfasser zum Ziehen
```

### Position aendern

1. Klicken Sie in die Mitte der Box
2. Ziehen Sie die Box an die neue Position

## 5.3 OCR-Regionen feinabstimmen

Bei eigenen Symbolen (Template-Matching) koennen Sie die OCR-Region anpassen:

### OCR-Region erkennen

OCR-Regionen werden mit gestrichelten Linien angezeigt:

```
    ┌────┐         ┏╍╍╍╍╍╍╍┓
    │ W1 │ ←────→  ╏ VMB142╏   ← Gestrichelte OCR-Region
    └────┘         ┗╍╍╍╍╍╍╍┛
    Symbol         Text-Bereich
```

### OCR-Region anpassen

1. Klicken Sie auf die gestrichelte Box
2. Anfasser erscheinen an den Ecken
3. Ziehen Sie die Anfasser um die Region anzupassen
4. Nach dem Loslassen erscheint ein Dialog:

```
┌─────────────────────────────────────────────────────────┐
│  OCR-Region anpassen                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐    ┌─────────────┐                    │
│  │   VORHER    │    │   NACHHER   │                    │
│  │   [Bild]    │    │   [Bild]    │                    │
│  │  "WB142"    │    │  "VMB142"   │                    │
│  │  ❌         │    │  ✓         │                    │
│  └─────────────┘    └─────────────┘                    │
│                                                         │
│  Aenderung: ◄ 15px links, ▼ 5px unten                  │
│                                                         │
│  ( ) Nur diese Instanz                                  │
│  (●) Alle Instanzen in diesem Plan                     │
│  [✓] Dauerhaft speichern                               │
│                                                         │
│         [Abbrechen]      [Uebernehmen]                 │
└─────────────────────────────────────────────────────────┘
```

### Optionen

| Option | Beschreibung |
|--------|--------------|
| Nur diese Instanz | Aendert nur das aktuelle Element |
| Alle Instanzen | Wendet die Aenderung auf alle gleichen Symbole an |
| Dauerhaft speichern | Speichert die Einstellung fuer zukuenftige Plaene |

## 5.4 Textwerte korrigieren

### Methode 1: Tabelle bearbeiten

1. Finden Sie das Element in der Tabelle
2. Doppelklicken Sie auf die Zelle
3. Geben Sie den korrekten Wert ein
4. Druecken Sie `Enter`

### Methode 2: Manuelles OCR

Wenn der Text komplett falsch ist:

1. Waehlen Sie das Element aus
2. Klicken Sie auf **"Manuelles OCR (Horizontal)"** in der Werkzeugleiste
3. Zeichnen Sie ein Rechteck um den Text im Bild
4. Das System erkennt den Text neu

### Methode 3: Manuelles OCR (Schraeg)

Fuer schraegenText:

1. Waehlen Sie das Element aus
2. Klicken Sie auf **"Manuelles OCR (Angular)"**
3. Zeichnen Sie eine Basislinie entlang des Textes
4. Bestimmen Sie die Texthoehe

## 5.5 Koordinaten zuweisen

### Automatische Verknuepfung

Das System verknuepft Symbole automatisch mit naheliegenden Koordinaten.

### Manuelle Verknuepfung

Wenn die automatische Verknuepfung fehlschlaegt:

1. Klicken Sie auf **"Koordinate manuell verknuepfen"**
2. Klicken Sie auf das Symbol (Anker)
3. Klicken Sie auf die zugehoerige Koordinate
4. Die Verknuepfung wird erstellt

```
    Schritt 1:          Schritt 2:
    ┌───┐               ┌───┐
    │ A │ ← Klick 1     │ A │────┐
    └───┘               └───┘    │
                                 │
    15.492 ← Klick 2    15.492 ◄─┘
                        (Verknuepft)
```

## 5.6 Detektionen loeschen

### Element loeschen

1. Waehlen Sie das Element aus
2. Druecken Sie `Entf` oder
3. Rechtsklick → **"Loeschen"**

### Mehrere Elemente loeschen

1. Waehlen Sie mehrere Elemente aus (Strg+Klick)
2. Druecken Sie `Entf`
3. Bestaetigen Sie die Aktion

> **Achtung:** Geloeschte Elemente koennen mit `Strg+Z` wiederhergestellt werden.

---

# 6. DATENVALIDIERUNG

Die Validierung prueft die erkannten Daten auf Fehler und Inkonsistenzen.

## 6.1 Validierung starten

1. Klicken Sie auf **"Validieren"** in der Werkzeugleiste (✓-Symbol)
2. Der Validierungsdialog oeffnet sich

```
┌────────────────────────────────────────────────────────────────────────┐
│  Validierungsergebnisse                                       [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Zusammenfassung:                                                      │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  🔴 Fehler:     5                                              │   │
│  │  🟡 Warnungen: 12                                              │   │
│  │  🟢 Info:       3                                              │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─────────┬──────────┬─────────────────────────────────┬──────────┐  │
│  │Prioritaet│ Typ      │ Beschreibung                    │ Aktion   │  │
│  ├─────────┼──────────┼─────────────────────────────────┼──────────┤  │
│  │ 🔴 Hoch │ Format   │ Signal "A1O1": Buchstabe O statt│ [Korr.]  │  │
│  │         │          │ Ziffer 0                        │          │  │
│  │ 🔴 Hoch │ Fehlend  │ Signal "B202" ohne Koordinate   │ [Springen]│ │
│  │ 🟡 Mittel│ Duplikat │ Doppelte Erkennung bei (123,456)│ [Korr.]  │  │
│  └─────────┴──────────┴─────────────────────────────────┴──────────┘  │
│                                                                        │
│                    [Alle korrigieren]    [Schliessen]                 │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## 6.2 Fehlertypen verstehen

### Formatfehler

| Fehler | Beschreibung | Beispiel |
|--------|--------------|----------|
| Grossbuchstaben | Koordinate mit Kleinbuchstaben | `gl.15.492` → `GL.15.492` |
| Falsche Zeichen | OCR-Verwechslung O/0, I/1 | `A1O1` → `A101` |
| Dezimalzeichen | Komma statt Punkt | `15,492` → `15.492` |
| Klammern | Fehlende oder falsche Klammern | `15.492(GL` → `15.492(GL)` |

### Fehlende Daten

| Fehler | Beschreibung |
|--------|--------------|
| Fehlende Koordinate | Symbol ohne verknuepfte Koordinate |
| Fehlender Text | OCR hat keinen Text erkannt |
| Fehlende Fahrtrichtung | Signal ohne Richtungsangabe |

### Strukturfehler

| Fehler | Beschreibung |
|--------|--------------|
| Weichenformat | Weichenblock beginnt nicht mit "W" |
| GKS-Format | GKS enthält Buchstaben statt Ziffern |
| Doppelte Erkennung | Gleiches Element mehrfach erkannt |

## 6.3 Risikobewertung (Traffic Light)

Jedes Element erhaelt einen Risikowert basierend auf mehreren Faktoren:

### Risikofaktoren

| Faktor | Gewichtung |
|--------|------------|
| Konfidenz | 40% |
| Fehlende Koordinate | 30% |
| Fehlender Text | 20% |
| Formatfehler | 10% |

### Risikostufen

```
┌──────────────────────────────────────────────────────────────────┐
│                     RISIKOBEWERTUNG                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   🟢 NIEDRIG (0.0 - 0.3)                                        │
│   ────────────────────────                                       │
│   "Gut erkannt" - Keine Pruefung erforderlich                   │
│   Hohe Konfidenz, alle Daten vollstaendig                       │
│                                                                  │
│   🟡 MITTEL (0.3 - 0.6)                                         │
│   ────────────────────────                                       │
│   "Bald pruefen" - Ueberprufung empfohlen                      │
│   Mittlere Konfidenz oder kleinere Probleme                     │
│                                                                  │
│   🔴 HOCH (0.6 - 1.0)                                           │
│   ────────────────────────                                       │
│   "Sofort pruefen" - Korrektur erforderlich                    │
│   Niedrige Konfidenz oder fehlende kritische Daten              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 6.4 Fehler beheben

### Automatische Korrektur

Fuer bestimmte Fehler bietet das System automatische Korrekturen:

1. Klicken Sie auf **[Korr.]** neben dem Fehler
2. Das System schlaegt eine Korrektur vor
3. Bestaetigen Sie mit **"Uebernehmen"**

### Manuelle Korrektur

1. Klicken Sie auf **[Springen]** um zum Element zu navigieren
2. Korrigieren Sie den Wert manuell (siehe Abschnitt 5)
3. Fuehren Sie die Validierung erneut aus

### Verfuegbare Korrekturen

| Fehlertyp | Automatisch korrigierbar |
|-----------|-------------------------|
| Kleinbuchstaben → Grossbuchstaben | Ja |
| O → 0 in Signalnummern | Ja |
| Komma → Punkt in Koordinaten | Ja |
| Fehlende Koordinate | Nein (manuell) |
| Falsche Bounding Box | Nein (manuell) |

---

# 7. QUALITAETSINSPEKTOR

Der Qualitaetsinspektor bietet detaillierte Statistiken ueber die Erkennungsqualitaet.

## 7.1 Qualitaetsmetriken verstehen

Oeffnen Sie den Inspektor ueber **Werkzeuge → Qualitaetsinspektor** oder das Lupen-Symbol.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Qualitaetsinspektor                                          [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  UEBERSICHT                                                            │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│  Gesamtqualitaet:  ████████████████████░░░░  82%                      │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │  Erkannte Elemente:       156                                  │   │
│  │  Vollstaendige Datensaetze: 134 (86%)                         │   │
│  │  Fehlende Koordinaten:      12 (8%)                            │   │
│  │  Fehlende Texte:            10 (6%)                            │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  KONFIDENZVERTEILUNG                                                   │
│  ──────────────────────────────────────────────────────────────────   │
│                                                                        │
│   90-100%: ████████████████████████  (95 Elemente)                    │
│   80-90%:  ██████████████            (42 Elemente)                    │
│   70-80%:  ███████                   (15 Elemente)                    │
│   <70%:    ██                        (4 Elemente)                     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## 7.2 Konfidenzverteilung

Die Konfidenz zeigt wie sicher das YOLO-Modell bei der Erkennung war:

| Konfidenz | Interpretation |
|-----------|----------------|
| 90-100% | Sehr zuverlaessig |
| 80-90% | Zuverlaessig |
| 70-80% | Pruefung empfohlen |
| <70% | Manuelle Pruefung erforderlich |

## 7.3 Fehlende Daten identifizieren

Der Inspektor listet alle unvollstaendigen Datensaetze auf:

```
┌────────────────────────────────────────────────────────────────────────┐
│  FEHLENDE DATEN                                                        │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Signale ohne Koordinate:                                              │
│  ├─ A101 (Seite 1, Position 1234,567)                                 │
│  ├─ C303 (Seite 2, Position 2345,678)                                 │
│  └─ D404 (Seite 3, Position 3456,789)                                 │
│                                                                        │
│  Elemente ohne Text:                                                   │
│  ├─ GKS bei (4567,890) - Seite 1                                      │
│  └─ Weichenblock bei (5678,901) - Seite 2                             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

# 8. DATEN EXPORTIEREN

## 8.1 Excel-Export

So exportieren Sie die Daten nach Excel:

1. Klicken Sie auf **"Exportieren"** in der Werkzeugleiste
2. Der Export-Dialog oeffnet sich
3. Waehlen Sie eine Vorlage
4. Pruefen Sie die Vorschau
5. Klicken Sie auf **"Exportieren"**
6. Waehlen Sie den Speicherort

```
┌────────────────────────────────────────────────────────────────────────┐
│  Excel-Export                                                 [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  VORLAGE WAEHLEN                                                      │
│  ───────────────                                                       │
│                                                                        │
│  (●) Techniker      [ ] Basic         [ ] Technical                   │
│      (3 Spalten)        (8 Spalten)       (Alle Spalten)              │
│                                                                        │
│  VORSCHAU                                                              │
│  ─────────                                                             │
│  ┌──────────────┬────────────┬──────────────┐                         │
│  │ Bezeichnung  │ Koordinate │ Fahrtrichtung│                         │
│  ├──────────────┼────────────┼──────────────┤                         │
│  │ A101         │ 15.492     │ A            │                         │
│  │ B202         │ 16.123     │ B            │                         │
│  │ ...          │ ...        │ ...          │                         │
│  └──────────────┴────────────┴──────────────┘                         │
│                                                                        │
│  STATISTIK                                                             │
│  ──────────                                                            │
│  Zeilen: 156 | Spalten: 3 | Klassen: 5                                │
│                                                                        │
│                              [Abbrechen]    [Exportieren]              │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

## 8.2 Exportvorlagen

### Techniker-Vorlage (Empfohlen fuer Feldarbeit)

| Spalte | Beschreibung |
|--------|--------------|
| Bezeichnung | Signalname, GKS-Code, etc. |
| Koordinate | Verknuepfter Koordinatenwert |
| Fahrtrichtung | A oder B |

### Basic-Vorlage (Standarduebersicht)

| Spalte | Beschreibung |
|--------|--------------|
| Seite | Seitennummer |
| Klasse | Symboltyp |
| Bezeichnung | OCR-Text |
| Koordinate | Koordinatenwert |
| Fahrtrichtung | A/B |
| Konfidenz | Erkennungssicherheit |
| Risiko | Risikostufe |
| Position | X, Y im Bild |

### Technical-Vorlage (Fuer Entwickler)

Alle verfuegbaren Spalten inkl. interner IDs, Winkel, Farben, etc.

## 8.3 Spaltenauswahl

Sie koennen individuelle Spalten auswaehlen:

1. Klicken Sie auf **"Spalten anpassen"**
2. Aktivieren/Deaktivieren Sie die gewuenschten Spalten
3. Sortieren Sie per Drag & Drop

## 8.4 Datenvorschau

Die Vorschau zeigt die ersten 20 Zeilen der Exportdaten:

- Pruefen Sie die Formatierung
- Ueberpruefen Sie die Vollstaendigkeit
- Kontrollieren Sie die Sortierung

---

# 9. ARBEITSBEREICH SPEICHERN/LADEN

## 9.1 In Datenbank speichern

So speichern Sie Ihren aktuellen Arbeitsbereich:

1. Klicken Sie auf **"Speichern"** (💾) oder `Strg+S`
2. Der Speicherdialog oeffnet sich:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Arbeitsbereich speichern                                     [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Name des Layouts:                                                     │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ Gleisplan_Abschnitt_A_2026-01-15                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ( ) Neues Layout erstellen                                            │
│  (●) Bestehendes Layout ueberschreiben                                │
│                                                                        │
│  Bestehende Layouts:                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ ► Gleisplan_Abschnitt_A_2026-01-10                               │ │
│  │   Gleisplan_Abschnitt_B_2026-01-08                               │ │
│  │   Test_Layout_2025-12-20                                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│                              [Abbrechen]    [Speichern]                │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

3. Geben Sie einen Namen ein oder waehlen Sie ein bestehendes Layout
4. Klicken Sie auf **"Speichern"**

### Was wird gespeichert?

| Daten | Beschreibung |
|-------|--------------|
| Erkennungsdaten | Alle Symbole mit Koordinaten und Text |
| Gleisskelett | Track-Skelett (falls erkannt) |
| Bildgroesse | Abmessungen des Originalbilds |
| Manuelle Korrekturen | Historie aller Aenderungen |
| Validierungsergebnisse | Letzte Validierung |

## 9.2 Aus Datenbank laden

1. Klicken Sie auf **Datei → Oeffnen aus Datenbank**
2. Der Ladedialog zeigt alle gespeicherten Layouts:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Arbeitsbereich laden                                         [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Verfuegbare Layouts:                                                 │
│  ┌─────────────────────────────────┬────────────────┬───────────────┐ │
│  │ Name                            │ Letzte Aenderung│ Zeilen       │ │
│  ├─────────────────────────────────┼────────────────┼───────────────┤ │
│  │ Gleisplan_Abschnitt_A_2026-01-15│ 15.01.2026     │ 156           │ │
│  │ Gleisplan_Abschnitt_B_2026-01-08│ 08.01.2026     │ 203           │ │
│  │ Test_Layout_2025-12-20          │ 20.12.2025     │ 45            │ │
│  └─────────────────────────────────┴────────────────┴───────────────┘ │
│                                                                        │
│  [Loeschen]                         [Abbrechen]    [Laden]            │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

3. Waehlen Sie ein Layout aus
4. Klicken Sie auf **"Laden"**

## 9.3 Manuelle Korrekturen verfolgen

Das System protokolliert alle manuellen Aenderungen:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Korrekturhistorie                                                     │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────┬───────────┬───────────┬───────────┬───────────────┐ │
│  │ Zeitpunkt    │ Element   │ Feld      │ Alt       │ Neu           │ │
│  ├──────────────┼───────────┼───────────┼───────────┼───────────────┤ │
│  │ 10:15:23     │ A101      │ coord_text│ 15.49     │ 15.492        │ │
│  │ 10:16:45     │ B202      │ anchor    │ B2O2      │ B202          │ │
│  │ 10:18:12     │ [GKS]     │ anchor    │ 12A4      │ 1234          │ │
│  └──────────────┴───────────┴───────────┴───────────┴───────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

Diese Historie wird mit dem Layout gespeichert und kann zur Qualitaetssicherung verwendet werden.

---

# 10. EIGENE SYMBOLE

Das System unterstuetzt benutzerdefinierte Symbole durch Template-Matching.

## 10.1 Neues Symbol trainieren

1. Oeffnen Sie **Werkzeuge → Neues Symbol trainieren**
2. Der Trainingsassistent oeffnet sich:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Neues Symbol trainieren                                      [─][□][X]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  SCHRITT 1: Symbol benennen                                            │
│  ────────────────────────────                                          │
│                                                                        │
│  Name: [weichen_left                    ]                              │
│                                                                        │
│  SCHRITT 2: Beispiele markieren                                        │
│  ─────────────────────────────────                                     │
│                                                                        │
│  Zeichnen Sie Rechtecke um Beispiele des Symbols im Bild.              │
│  Mindestens 3 Beispiele werden empfohlen.                              │
│                                                                        │
│  [Bild mit Markierungswerkzeug]                                        │
│                                                                        │
│  Beispiele erfasst: 5                                                  │
│                                                                        │
│  SCHRITT 3: Textposition angeben                                       │
│  ─────────────────────────────────                                     │
│                                                                        │
│  Hat das Symbol zugehoerigen Text?                                    │
│  (●) Ja, Text ist [links ▼] vom Symbol                                │
│  ( ) Nein, kein Text                                                   │
│                                                                        │
│                              [Abbrechen]    [Speichern]                │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Empfehlungen fuer gutes Training

- Mindestens 3-5 Beispiele pro Symbol
- Beispiele aus verschiedenen Positionen im Dokument
- Beispiele mit unterschiedlichen Drehwinkeln (falls vorhanden)
- Klare, nicht ueberlappende Markierungen

## 10.2 Template-Matching konfigurieren

Nach dem Speichern koennen Sie das Symbol konfigurieren:

| Einstellung | Beschreibung | Empfehlung |
|-------------|--------------|------------|
| Aehnlichkeitsschwelle | Wie aehnlich muss ein Treffer sein? | 0.75 (75%) |
| Textposition | Links, rechts, oben, unten | Je nach Symbol |
| Textversatz | Abstand zwischen Symbol und Text | Automatisch |

## 10.3 OCR-Einstellungen anpassen

Fuer jedes eigene Symbol koennen Sie OCR-Parameter festlegen:

```
┌────────────────────────────────────────────────────────────────────────┐
│  OCR-Einstellungen fuer: weichen_left                                 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Textposition:     [Links           ▼]                                │
│                                                                        │
│  Versatz X:        [ -15 ] Pixel                                      │
│  Versatz Y:        [   5 ] Pixel                                      │
│                                                                        │
│  Region-Breite:    [ 100 ] Pixel                                      │
│  Region-Hoehe:     [  30 ] Pixel                                      │
│                                                                        │
│  [Vorschau aktualisieren]                                              │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ [Vorschau der OCR-Region auf aktuellem Bild]                    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│                              [Abbrechen]    [Speichern]                │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

# 11. DESIGN UND EINSTELLUNGEN

## 11.1 Dunkles/Helles Design

Die Anwendung unterstuetzt zwei Farbthemen:

### Design wechseln

1. Klicken Sie auf **Ansicht → Design**
2. Waehlen Sie **Dunkel** oder **Hell**

```
Dunkles Design (Standard):        Helles Design:
┌─────────────────────────┐       ┌─────────────────────────┐
│ ███████████████████████ │       │                         │
│ ███ Dunkler Hintergrund │       │   Heller Hintergrund    │
│ ███ Helle Schrift       │       │   Dunkle Schrift        │
│ ███████████████████████ │       │                         │
└─────────────────────────┘       └─────────────────────────┘
```

### Vorteile je Design

| Design | Vorteile |
|--------|----------|
| **Dunkel** | Weniger Augenbelastung, besser in dunklen Umgebungen |
| **Hell** | Bessere Lesbarkeit bei hellem Umgebungslicht |

## 11.2 Tastaturkuerzel

### Allgemeine Kuerzel

| Tastenkombination | Aktion |
|-------------------|--------|
| `Strg+O` | Datei oeffnen |
| `Strg+S` | Speichern |
| `Strg+Shift+S` | Speichern unter |
| `Strg+E` | Exportieren |
| `Strg+Z` | Rueckgaengig |
| `Strg+Y` | Wiederholen |
| `Strg+Q` | Beenden |

### Navigations-Kuerzel

| Tastenkombination | Aktion |
|-------------------|--------|
| `Bild↑` | Vorherige Seite |
| `Bild↓` | Naechste Seite |
| `Pos1` | Erste Seite |
| `Ende` | Letzte Seite |
| `+` / `-` | Zoomen |
| `Leertaste` | Zoom zuruecksetzen |

### Bearbeitungs-Kuerzel

| Tastenkombination | Aktion |
|-------------------|--------|
| `Entf` | Ausgewaehltes Element loeschen |
| `F2` | Zelle bearbeiten |
| `Esc` | Auswahl aufheben / Abbrechen |
| `Enter` | Eingabe bestaetigen |

---

# 12. ERKANNTE SYMBOLKLASSEN

Das System erkennt 13 verschiedene Symbolklassen. Hier eine detaillierte Uebersicht:

## 12.1 Signal

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SIGNAL                                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Eisenbahnsignal (Haupt-/Vorsignal)                     │
│  OCR-Feld:      Signalname (z.B. "A101", "BHR201")                     │
│  Format:        1-4 Buchstaben + 1-4 Ziffern                           │
│  Beispiele:     A101, B202, WAHR918, V12                               │
│                                                                         │
│  Zugehoerige Daten:                                                    │
│  - Koordinate (verknuepft)                                             │
│  - Fahrtrichtung (A oder B)                                            │
│  - Farbe (rot/gelb)                                                    │
│                                                                         │
│  Typische Konfidenz: 98-99%                                            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.2 GM-Block

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GM-BLOCK (Gleismagnet-Block)                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Gleismagnet zur Zugbeeinflussung                       │
│  OCR-Feld:      Meist "GM" (fester Text)                               │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.3 GKS (festkodiert)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GKS_FESTKODIERT (Gleiskontakt-Steuerung)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Festkodierter Gleiskontaktschalter                     │
│  OCR-Feld:      4-stelliger Zahlencode                                 │
│  Format:        Genau 4 Ziffern (z.B. "0502", "1234")                  │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 98%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.4 GKS (gesteuert)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  GKS_GESTEUERT (Gleiskontakt-Steuerung)                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Gesteuerter Gleiskontaktschalter                       │
│  OCR-Feld:      4-stelliger Zahlencode                                 │
│  Unterschied:   Oft mit Farbmarkierung (rot/gelb)                      │
│  Zugehoeriges:  Koordinate, Farbe                                      │
│                                                                         │
│  Typische Konfidenz: 97%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.5 Weichen-Block

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WEICHEN-BLOCK                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Weichensteuerungseinheit                               │
│  OCR-Feld:      Weichenbezeichnung (z.B. "WAHR921")                    │
│  Format:        Beginnt mit "W" + Buchstaben + Ziffern                 │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 98%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.6 Isolierstoss

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ISOLIERSTOSS                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Elektrische Trennung im Gleis                          │
│  OCR-Feld:      Meist ohne Text                                        │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.7 Haltepunkt

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HALTEPUNKT                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Bahnhof oder Haltestelle                               │
│  OCR-Feld:      Haltestellenname                                       │
│  Zugehoeriges:  Koordinate, verknuepfte Signale                       │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.8 S-Verbinder

```
┌─────────────────────────────────────────────────────────────────────────┐
│  S-VERBINDER                                                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Schienenverbinder                                      │
│  OCR-Feld:      Meist ohne Text                                        │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.9 Coordinate

```
┌─────────────────────────────────────────────────────────────────────────┐
│  COORDINATE                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Streckenkilometer / Koordinatenangabe                  │
│  OCR-Feld:      Koordinatenwert                                        │
│  Format:        X.XXX oder X.XXX(GL.XXX)                               │
│  Beispiele:     15.492, 0.0734(Gl.112)                                 │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.10 Prellbock

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PRELLBOCK                                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Gleisabschluss / Puffer                                │
│  OCR-Feld:      Meist ohne Text                                        │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.11 Haltetafel

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HALTETAFEL                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Haltesignal / Tafel                                    │
│  OCR-Feld:      Meist ohne Text                                        │
│  Zugehoeriges:  Koordinate, verknuepftes GKS                          │
│                                                                         │
│  Typische Konfidenz: 97%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 12.12 Weichenende / Weichengruppenende

```
┌─────────────────────────────────────────────────────────────────────────┐
│  WEICHENENDE / WEICHENGRUPPENENDE                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Beschreibung:  Ende eines Weichenbereichs                             │
│  OCR-Feld:      Meist ohne Text                                        │
│  Zugehoeriges:  Koordinate                                             │
│                                                                         │
│  Typische Konfidenz: 99%                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Uebersichtstabelle

| Klasse | mAP50 | Hat Text | Benoetigt Koordinate |
|--------|-------|----------|---------------------|
| signal | 98.9% | Ja | Ja |
| gm_block | 99.5% | Ja (GM) | Ja |
| gks_festkodiert | 98.5% | Ja (4 Ziffern) | Ja |
| gks_gesteuert | 97.3% | Ja (4 Ziffern) | Ja |
| weichen_block | 97.9% | Ja | Ja |
| isolierstoss | 99.4% | Nein | Ja |
| haltepunkt | 99.5% | Ja | Ja |
| sverbinder | 98.8% | Nein | Ja |
| coordinate | 99.3% | Ja | - |
| prellbock | 99.5% | Nein | Ja |
| haltetafel | 96.6% | Nein | Ja |
| weichenende | 99.5% | Nein | Ja |
| weichengruppenende | 99.5% | Nein | Ja |

---

# 13. GLOSSAR

## Fachbegriffe (Alphabetisch)

| Begriff | Erklaerung |
|---------|------------|
| **Anchor** | Ankerelement - das Symbol, dem eine Koordinate zugeordnet wird |
| **Bounding Box** | Umrandungsrechteck um ein erkanntes Element |
| **Confidence / Konfidenz** | Prozentuale Sicherheit der KI-Erkennung (0-100%) |
| **DPI** | Dots Per Inch - Aufloesung beim PDF-Rendering (Standard: 500) |
| **Fahrtrichtung** | Richtung A oder B entlang des Gleises |
| **GKS** | Gleiskontakt-Steuerung |
| **Gleisplan** | Technische Zeichnung des Schienennetzes |
| **Gleisskelett** | Vereinfachte Darstellung der Gleismittellinien |
| **IoU** | Intersection over Union - Mass fuer Ueberlappung |
| **Linking** | Verknuepfung von Symbolen mit Koordinaten |
| **mAP** | Mean Average Precision - Qualitaetsmass fuer Erkennung |
| **NMS** | Non-Maximum Suppression - Entfernung doppelter Erkennungen |
| **OBB** | Oriented Bounding Box - gedrehtes Rechteck |
| **OCR** | Optical Character Recognition - Texterkennung |
| **PaddleOCR** | Open-Source OCR-Engine von Baidu |
| **Prellbock** | Gleisabschluss / Puffer am Stumpfgleis |
| **Risiko** | Bewertung der Erkennungsqualitaet (0.0-1.0) |
| **Template-Matching** | Mustererkennung durch Vorlagenvergleich |
| **Tesseract** | Open-Source OCR-Engine von Google |
| **Tiling** | Unterteilung grosser Bilder in Kacheln |
| **TTA** | Test-Time Augmentation - Mehrfache Erkennung fuer Genauigkeit |
| **YOLO** | You Only Look Once - Objekterkennungs-Algorithmus |

## Abkuerzungen

| Abkuerzung | Bedeutung |
|------------|-----------|
| **DB** | Datenbank |
| **Gl.** | Gleis (in Koordinaten) |
| **GM** | Gleismagnet |
| **GKS** | Gleiskontakt-Steuerung |
| **PDF** | Portable Document Format |
| **UI** | User Interface (Benutzeroberflaeche) |

---

# 14. FEHLERBEHEBUNG

## 14.1 Haeufige Probleme

### Problem: Anwendung startet nicht

```
Symptom: Fehlermeldung beim Start oder schwarzes Fenster

Loesungen:
1. Pruefen Sie, ob die virtuelle Umgebung aktiviert ist:
   > .\venv\Scripts\activate

2. Pruefen Sie die Python-Version:
   > py --version
   (Sollte 3.11.x sein)

3. Installieren Sie Abhaengigkeiten neu:
   > py -m pip install -r requirements.txt

4. Pruefen Sie PyTorch:
   > py -c "import torch; print(torch.__version__)"
```

### Problem: PDF wird nicht geladen

```
Symptom: "Datei kann nicht geoeffnet werden" oder keine Vorschau

Loesungen:
1. Pruefen Sie das Dateiformat (muss .pdf sein)
2. Versuchen Sie, die PDF in einem anderen Programm zu oeffnen
3. Pruefen Sie, ob die Datei beschaedigt ist
4. Stellen Sie sicher, dass Sie Leserechte haben
```

### Problem: Verarbeitung bricht ab

```
Symptom: Fortschrittsbalken stoppt, keine Ergebnisse

Loesungen:
1. Pruefen Sie den verfuegbaren Arbeitsspeicher (min. 8 GB)
2. Schliessen Sie andere Programme
3. Bei sehr grossen PDFs: Teilen Sie die Datei auf
4. Pruefen Sie die Konsole auf Fehlermeldungen
```

## 14.2 Fehlerhafte Erkennung

### Symbol wird nicht erkannt

```
Moegliche Ursachen:
- Symbol ist zu klein oder unscharf
- Symbol ist von Linien ueberlagert
- Ungewoehnliche Symbolvariante

Loesungen:
1. Pruefen Sie die PDF-Qualitaet (mindestens 300 DPI)
2. Trainieren Sie ein eigenes Symbol (Abschnitt 10)
3. Passen Sie die Konfidenz-Schwelle an
```

### Falsche Symbolklasse erkannt

```
Moegliche Ursachen:
- Aehnliche Symbole werden verwechselt
- Modell ist nicht fuer diesen Plantyp optimiert

Loesungen:
1. Korrigieren Sie manuell in der Tabelle
2. Melden Sie das Problem fuer Modellverbesserung
```

## 14.3 OCR-Fehler

### Text wird nicht erkannt

```
Moegliche Ursachen:
- Text ist zu klein oder unscharf
- Text ist stark gedreht
- Ungewoehnliche Schriftart

Loesungen:
1. Verwenden Sie "Manuelles OCR" mit groesserem Bereich
2. Probieren Sie "Manuelles OCR (Angular)" fuer schraegen Text
3. Wechseln Sie die OCR-Engine (PaddleOCR ↔ Tesseract)
```

### Haeufige OCR-Verwechslungen

| Falsch | Richtig | Erklaerung |
|--------|---------|------------|
| O | 0 | Buchstabe O vs. Ziffer Null |
| I, l | 1 | Buchstabe I/l vs. Ziffer Eins |
| S | 5 | Buchstabe S vs. Ziffer Fuenf |
| B | 8 | Buchstabe B vs. Ziffer Acht |
| Z | 2 | Buchstabe Z vs. Ziffer Zwei |
| G | 6 | Buchstabe G vs. Ziffer Sechs |

Das System korrigiert viele dieser Fehler automatisch in Zahlenfeldern.

## 14.4 Speicherfehler

### Datenbank-Fehler beim Speichern

```
Symptom: "Fehler beim Speichern" Meldung

Loesungen:
1. Pruefen Sie freien Festplattenspeicher
2. Pruefen Sie Schreibrechte im data-Ordner
3. Schliessen Sie die Anwendung und starten Sie neu
4. Bei persistenten Problemen: Loeschen Sie die DB und erstellen Sie neu
```

## 14.5 Leistungsprobleme

### Verarbeitung ist sehr langsam

```
Symptome:
- Verarbeitung dauert mehrere Minuten pro Seite
- Anwendung reagiert langsam

Loesungen:
1. Schliessen Sie andere ressourcenintensive Programme
2. Prufen Sie den Arbeitsspeicher (Task-Manager)
3. Fuer grosse A0-Plaene ist laengere Verarbeitung normal
4. Deaktivieren Sie TTA (Test-Time Augmentation) fuer schnellere Verarbeitung
```

### Anwendung friert ein

```
Loesungen:
1. Warten Sie - grosse PDFs benoetigen Zeit
2. Pruefen Sie die Fortschrittsanzeige in der Konsole
3. Bei echtem Einfrieren: Task-Manager → Beenden
4. Reduzieren Sie die DPI-Einstellung (config.py)
```

---

# 15. ANHANG

## A. Tastaturkuerzel (Vollstaendige Liste)

### Dateioperationen

| Kuerzel | Aktion |
|---------|--------|
| `Strg+N` | Neue Datei |
| `Strg+O` | Datei oeffnen |
| `Strg+S` | Speichern |
| `Strg+Shift+S` | Speichern unter |
| `Strg+E` | Exportieren |
| `Strg+W` | Tab schliessen |
| `Strg+Q` | Beenden |

### Bearbeitung

| Kuerzel | Aktion |
|---------|--------|
| `Strg+Z` | Rueckgaengig |
| `Strg+Y` | Wiederholen |
| `Strg+A` | Alles auswaehlen |
| `Entf` | Loeschen |
| `F2` | Umbenennen/Bearbeiten |

### Navigation

| Kuerzel | Aktion |
|---------|--------|
| `Bild↑` | Vorherige Seite |
| `Bild↓` | Naechste Seite |
| `Pos1` | Erste Seite |
| `Ende` | Letzte Seite |
| `Strg+F` | Suchen |

### Ansicht

| Kuerzel | Aktion |
|---------|--------|
| `+` | Hineinzoomen |
| `-` | Herauszoomen |
| `Strg+0` | Zoom zuruecksetzen |
| `F11` | Vollbild |

## B. Dateiformate

### Eingabeformate

| Format | Erweiterung | Bemerkungen |
|--------|-------------|-------------|
| PDF | .pdf | Primaerformat, mehrere Seiten |
| PNG | .png | Verlustfrei, empfohlen fuer Scans |
| JPEG | .jpg, .jpeg | Komprimiert, fuer Fotos |
| TIFF | .tif, .tiff | Professionelle Scans |
| BMP | .bmp | Windows Bitmap |

### Ausgabeformate

| Format | Erweiterung | Verwendung |
|--------|-------------|------------|
| Excel | .xlsx | Datenexport |
| JSON | .json | Programmierbare Nutzung |

### Interne Formate

| Datei | Inhalt |
|-------|--------|
| gleisplanextraktor.db | SQLite-Datenbank mit Arbeitsbereichen |
| custom_symbols.json | Eigene Symboldefinitionen |
| ocr_adjustments.json | OCR-Lernhistorie |

## C. Technische Spezifikationen

### Verarbeitungsparameter

| Parameter | Standardwert | Beschreibung |
|-----------|--------------|--------------|
| DPI | 500 | Rendering-Aufloesung |
| Tile-Groesse | 2048 px | Kachelgroesse |
| Ueberlappung | 40% | Kachelueberlappung |
| YOLO-Bildgroesse | 1024 px | Eingabegroesse fuer Modell |

### Systemgrenzen

| Limit | Wert |
|-------|------|
| Maximale PDF-Seiten | Unbegrenzt (sequentiell) |
| Maximale Bildgroesse | ~50.000 x 50.000 px |
| Maximale Erkennungen/Seite | 1500 |

### Qualitaetsmetriken (YOLO-Modell)

| Klasse | mAP50 | mAP50-95 |
|--------|-------|----------|
| signal | 0.989 | 0.750 |
| gm_block | 0.995 | 0.780 |
| gks_festkodiert | 0.985 | 0.720 |
| gks_gesteuert | 0.973 | 0.690 |
| weichen_block | 0.979 | 0.710 |
| isolierstoss | 0.994 | 0.770 |
| haltepunkt | 0.995 | 0.780 |
| sverbinder | 0.988 | 0.740 |
| coordinate | 0.993 | 0.760 |
| prellbock | 0.995 | 0.780 |
| haltetafel | 0.966 | 0.650 |
| weichenende | 0.995 | 0.780 |
| weichengruppenende | 0.995 | 0.780 |

---

## Dokumenthistorie

| Version | Datum | Aenderungen |
|---------|-------|-------------|
| 1.0 | Februar 2026 | Erstversion des Benutzerhandbuchs |

---

## Kontakt & Support

Bei Fragen oder Problemen wenden Sie sich an:

**Entwickler:** Utkarsh Swain
**Organisation:** Siemens Mobility GmbH

Fuer technische Dokumentation siehe auch:
- `docs/VALIDATION_CRITERIA_AND_AUTO_CORRECTIONS.md`
- `docs/OCR_ADJUSTMENT_SYSTEM.md`
- `docs/HOW_TO_USE_OCR_ADJUSTMENT.md`

---

```
================================================================================
        Ende des Benutzerhandbuchs
        Gleisplanextraktor v3 - RailDoc Studio
================================================================================
```
