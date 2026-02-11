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
6. [Daten exportieren](#6-daten-exportieren)
7. [Qualitaetspruefung und Validierung](#7-qualitaetspruefung-und-validierung)
8. [Arbeitsbereich speichern/laden](#8-arbeitsbereich-speichernladen)
9. [Gleisplaene vergleichen](#9-gleisplaene-vergleichen)
10. [Eigene Symbole](#10-eigene-symbole)
11. [Erkannte Symbolklassen](#11-erkannte-symbolklassen)
12. [Tastaturkuerzel](#12-tastaturkuerzel)
13. [Fehlerbehebung](#13-fehlerbehebung)

---

# 1. EINFUEHRUNG

## 1.1 Was ist Gleisplanextraktor?

Der Gleisplanextraktor ist ein KI-gestuetztes Werkzeug zur automatischen Extraktion und Analyse von Eisenbahn-Gleisplaenen. Das System verwendet moderne Computer-Vision-Technologien (YOLO, PaddleOCR) um Symbole, Signale, Koordinaten und andere relevante Informationen aus technischen PDF-Dokumenten zu erkennen.

### Hauptfunktionen

| Funktion | Beschreibung |
|----------|--------------|
| **Automatische Erkennung** | 13 verschiedene Symbolklassen werden automatisch erkannt |
| **OCR-Texterkennung** | Extrahiert Signalnamen, Koordinaten und andere Textinformationen |
| **Intelligente Verknuepfung** | Verknuepft Symbole automatisch mit zugehoerigen Koordinaten |
| **Fahrtrichtungserkennung** | Bestimmt die Fahrtrichtung basierend auf Gleisskelett |
| **Interaktive Bearbeitung** | Manuelle Korrektur und Feinabstimmung der Ergebnisse |
| **Gleisplan-Vergleich** | Vergleicht zwei Versionen eines Gleisplans |
| **Excel-Export** | Strukturierter Export fuer Weiterverarbeitung |
| **Datenbank-Speicherung** | Persistente Speicherung von Arbeitsbereichen |

## 1.2 Systemanforderungen

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

## 1.3 Installation

```
1. Python 3.11.x installieren
2. Virtuelle Umgebung erstellen: py -m venv venv
3. Aktivieren: .\venv\Scripts\activate
4. Abhaengigkeiten installieren: py -m pip install -r requirements.txt
5. Starten: py main.py
```

---

# 2. SCHNELLSTART

## 2.1 Anwendung starten

1. Oeffnen Sie PowerShell oder Eingabeaufforderung
2. Navigieren Sie zum Projektordner
3. Aktivieren Sie die virtuelle Umgebung: `.\venv\Scripts\activate`
4. Starten Sie die Anwendung: `py main.py`

Das Setup-Fenster erscheint.

## 2.2 PDF laden und verarbeiten

1. **PDF auswaehlen:** Klicken Sie auf "DURCHSUCHEN" im Bereich "01 GLEISPLAN" oder ziehen Sie eine PDF-Datei direkt in das Fenster (Drag & Drop)
2. **Modell pruefen:** Das KI-Modell wird automatisch geladen. Bei Bedarf koennen Sie ein anderes Modell waehlen.
3. **Analyse starten:** Klicken Sie auf "ANALYSE STARTEN"
4. **Warten:** Die Verarbeitung zeigt einen Fortschrittsbalken

Nach Abschluss oeffnet sich automatisch das Bearbeitungsfenster.

## 2.3 Ergebnisse exportieren

1. Im Bearbeitungsfenster: Klicken Sie auf "Excel Export" in der Werkzeugleiste
2. Waehlen Sie Exportoptionen und Speicherort
3. Fertig!

---

# 3. HAUPTFENSTER - SETUP

Das Setup-Fenster ist der Einstiegspunkt der Anwendung.

## 3.1 Benutzeroberflaeche

Das Fenster ist in drei Bereiche unterteilt:

| Bereich | Beschreibung |
|---------|--------------|
| **01 GLEISPLAN** | PDF oder Bild auswaehlen |
| **02 KI-MODELL** | YOLO-Modell auswaehlen (Standard ist voreingestellt) |
| **03 AUSFUEHREN** | Analyse starten |

Darunter befindet sich:
- Eine Vorschau des geladenen Dokuments
- Ein Fortschrittsbalken
- Ein Log-Bereich fuer Statusmeldungen

## 3.2 PDF-Datei auswaehlen

### Methode 1: Dateiauswahl-Dialog

1. Klicken Sie auf **"DURCHSUCHEN"** im Bereich "01 GLEISPLAN"
2. Navigieren Sie zum Speicherort
3. Waehlen Sie die Datei aus
4. Klicken Sie auf **"Oeffnen"**

### Methode 2: Drag & Drop

1. Oeffnen Sie den Windows Explorer
2. Ziehen Sie die PDF-Datei direkt in das Anwendungsfenster
3. Lassen Sie die Maustaste los

Die Vorschau zeigt die erste Seite des Dokuments an.

### Unterstuetzte Formate

| Format | Dateierweiterung | Hinweise |
|--------|------------------|----------|
| PDF | .pdf | Empfohlen, mehrere Seiten moeglich |
| PNG | .png | Einzelbild, min. 300 DPI empfohlen |
| JPEG | .jpg, .jpeg | Einzelbild |
| TIFF | .tif, .tiff | Einzelbild |
| BMP | .bmp | Einzelbild |

## 3.3 Modell auswaehlen

Das YOLO-Modell ist fuer die Objekterkennung verantwortlich. Das Standardmodell wird automatisch geladen.

**Standardmodell:** `yolomodel/best.pt`

### Modell wechseln (optional)

1. Klicken Sie auf **"DURCHSUCHEN"** im Bereich "02 KI-MODELL"
2. Navigieren Sie zum Modell-Ordner
3. Waehlen Sie eine `.pt`-Datei aus

> **Hinweis:** Verwenden Sie nur kompatible OBB-Modelle (Oriented Bounding Box).

## 3.4 Verarbeitung starten

1. Stellen Sie sicher, dass eine Datei geladen ist
2. Optional: Aktivieren Sie "Vollstaendige Neuanalyse" um den Cache zu ignorieren
3. Klicken Sie auf **"ANALYSE STARTEN"**

### Verarbeitungsschritte

1. **PDF-Rendering** - Seiten werden in Bilder konvertiert (500 DPI)
2. **Tiling** - Grosse Bilder werden in Kacheln unterteilt
3. **YOLO-Erkennung** - Symbole werden erkannt
4. **OCR** - Text wird mit PaddleOCR extrahiert
5. **Linking** - Symbole werden mit Koordinaten verknuepft
6. **Fahrtrichtung** - Richtung wird basierend auf Gleisskelett bestimmt

---

# 4. HAUPTFENSTER - BEARBEITUNG

Nach erfolgreicher Verarbeitung oeffnet sich das Bearbeitungsfenster (RailDoc Studio - Bearbeitung & Korrektur).

## 4.1 Uebersicht der Benutzeroberflaeche

Das Fenster besteht aus:

- **Menueleiste:** Datei, Bearbeiten, Daten, Vergleichen, Ansicht, Symbole, Hilfe
- **Werkzeugleiste:** Schnellzugriff auf wichtige Funktionen
- **Tab-Leiste:** Mehrere Gleisplaene gleichzeitig oeffnen
- **Hauptbereich:** Baumansicht links, Grafikansicht rechts, Tabelle unten
- **Statusleiste:** Zeilenanzeige und Auswahlinfo

## 4.2 Menueleiste

### Datei-Menue

| Aktion | Tastenkuerzel | Beschreibung |
|--------|---------------|--------------|
| Speichern | Strg+S | Speichert den aktuellen Plan |
| Alle speichern | Strg+Shift+S | Speichert alle geoeffneten Plaene |
| Excel Export | Strg+E | Exportiert als Excel-Datei |
| JSON Export | Strg+J | Exportiert als JSON-Datei |
| Tab schliessen | Strg+W | Schliesst den aktuellen Tab |

### Bearbeiten-Menue

| Aktion | Tastenkuerzel | Beschreibung |
|--------|---------------|--------------|
| Suchen | Strg+F | Sucht und ersetzt Text |
| Kopieren | Strg+C | Kopiert ausgewaehlte Zellen |
| Einfuegen | Strg+V | Fuegt kopierte Daten ein |
| Zeile hinzufuegen | Strg+Shift+N | Fuegt neuen Eintrag hinzu |
| Zeilen loeschen | Strg+D | Loescht ausgewaehlte Eintraege |
| Massenbearbeitung | - | Bearbeitet mehrere Zeilen gleichzeitig |

### Daten-Menue

| Aktion | Beschreibung |
|--------|--------------|
| Sortieren | Sortiert Daten nach Spalte |
| Filter | Filtert Daten nach Kriterien |
| Statistik | Zeigt Statistiken ueber die Daten |
| Datenbank-Manager | Verwaltet gespeicherte Arbeitsbereiche |

### Vergleichen-Menue

| Aktion | Beschreibung |
|--------|--------------|
| Zwei Gleisplaene vergleichen | Vergleicht zwei geoeffnete Gleisplaene |

### Symbole-Menue

| Aktion | Beschreibung |
|--------|--------------|
| Neues Symbol definieren | Definiert ein neues Symbol ohne Modell-Training |
| Template Matching | Sucht nach definierten Symbolen im Layout |

## 4.3 Werkzeugleiste

Die Werkzeugleiste bietet Schnellzugriff auf haeufig verwendete Funktionen:

| Button | Beschreibung |
|--------|--------------|
| Speichern | Speichert den aktuellen Plan |
| Alle | Speichert alle Plaene |
| Kopieren | Kopiert ausgewaehlte Zellen |
| Einfuegen | Fuegt ein |
| Suchen | Oeffnet Suchen/Ersetzen |
| Sortieren | Sortiert die Tabelle |
| Filter | Filtert die Anzeige |
| Excel Export | Exportiert nach Excel |
| JSON | Exportiert nach JSON |
| Mehrere aendern | Massenbearbeitung |
| Plaene vergleichen | Vergleicht zwei Plaene |
| Neuer Eintrag | Fuegt neue Zeile hinzu |
| Entfernen | Loescht ausgewaehlte Zeilen |

## 4.4 Tab-Verwaltung

Sie koennen mehrere PDF-Dateien gleichzeitig oeffnen. Jeder Gleisplan erscheint als eigener Tab.

| Aktion | Beschreibung |
|--------|--------------|
| Tab anklicken | Wechselt zwischen Dokumenten |
| X-Symbol | Schliesst den Tab (mit Speicherabfrage) |
| Tab ziehen | Aendert die Tab-Reihenfolge |

## 4.5 Baumansicht (links)

Die Baumansicht zeigt alle erkannten Elemente hierarchisch an:

```
├─ Seite 1
│  ├─ signal (5)
│  │  ├─ A101 @ 15.492
│  │  └─ B202 @ 16.123
│  ├─ gks_gesteuert (3)
│  └─ coordinate (8)
└─ Seite 2
   └─ ...
```

- Klicken Sie auf ein Element, um es in der Grafikansicht hervorzuheben
- Die Zahl in Klammern zeigt die Anzahl der Elemente

## 4.6 Grafikansicht (rechts)

Die Grafikansicht zeigt das Gleisplan-Bild mit ueberlagerten Erkennungsrahmen.

### Navigation

| Aktion | Bedienung |
|--------|-----------|
| Zoomen | Mausrad drehen |
| Verschieben | Rechte Maustaste + Ziehen |
| Element auswaehlen | Linksklick auf Rahmen |

### Farben der Erkennungsrahmen

Jede Symbolklasse hat eine eigene Farbe zur besseren Unterscheidung.

## 4.7 Tabelle (unten)

Die Tabelle zeigt alle erkannten Elemente mit ihren Eigenschaften.

### Spalten

| Spalte | Beschreibung |
|--------|--------------|
| cls | Symbolklasse |
| anchor_text | Erkannter Text (Bezeichnung) |
| coord_text | Verknuepfte Koordinate |
| fahrtrichtung | Fahrtrichtung (A oder B) |
| conf | Erkennungskonfidenz |

### Zellen bearbeiten

1. Doppelklicken Sie auf eine Zelle
2. Geben Sie den neuen Wert ein
3. Druecken Sie Enter zum Bestaetigen

---

# 5. ERKANNTE SYMBOLE BEARBEITEN

## 5.1 Element auswaehlen

- **In der Baumansicht:** Klicken Sie auf das Element
- **In der Grafikansicht:** Klicken Sie auf den Erkennungsrahmen
- **In der Tabelle:** Klicken Sie auf die Zeile

Das ausgewaehlte Element wird in allen Ansichten hervorgehoben.

## 5.2 Textwerte korrigieren

### In der Tabelle

1. Doppelklicken Sie auf die Zelle (anchor_text oder coord_text)
2. Geben Sie den korrekten Wert ein
3. Druecken Sie Enter

### Massenbearbeitung

1. Klicken Sie auf "Mehrere aendern" in der Werkzeugleiste
2. Waehlen Sie die zu aendernden Zeilen
3. Geben Sie die neuen Werte ein

## 5.3 Eintraege loeschen

1. Waehlen Sie die Zeile(n) in der Tabelle
2. Klicken Sie auf "Entfernen" oder druecken Sie Strg+D
3. Bestaetigen Sie die Aktion

## 5.4 Neue Eintraege hinzufuegen

1. Klicken Sie auf "Neuer Eintrag" oder druecken Sie Strg+Shift+N
2. Fuellen Sie die erforderlichen Felder aus
3. Bestaetigen Sie mit OK

## 5.5 Erkennungsrahmen anpassen (Bbox Resize)

Wenn der Text nicht vollstaendig erkannt wurde, koennen Sie den Erkennungsrahmen direkt im Bild anpassen.

### Rahmen vergroessern/verkleinern

1. Klicken Sie auf ein erkanntes Element in der Grafikansicht
2. Der Erkennungsrahmen zeigt blaue Anfasser an den Ecken und Kanten
3. Ziehen Sie einen Anfasser, um den Rahmen anzupassen:
   - **Ecken:** Diagonal vergroessern/verkleinern
   - **Kanten:** Horizontal oder vertikal verschieben
4. Nach dem Loslassen wird automatisch eine neue OCR-Erkennung gestartet (1.5 Sekunden Verzoegerung)

### Tipp

Wenn ein Signalname wie "A10" statt "A101" erkannt wurde, vergroessern Sie den Rahmen nach rechts, um die fehlende Ziffer einzuschliessen.

## 5.6 Kontextmenue (Rechtsklick)

Klicken Sie mit der rechten Maustaste auf einen Erkennungsrahmen fuer schnelle Aktionen:

| Aktion | Beschreibung |
|--------|--------------|
| **OCR erneut ausfuehren** | Fuehrt Texterkennung nochmal aus |
| - Horizontal | Fuer horizontale Texte |
| - Angular | Fuer schraege/gedrehte Texte |
| **Klasse aendern** | Aendert den Symboltyp (z.B. Signal zu GKS) |
| **In Tabelle anzeigen** | Springt zur Zeile in der Tabelle |
| **Erkennung loeschen** | Entfernt das Element vollstaendig |

## 5.7 Manuelle OCR-Erkennung

Fuer Texte die nicht automatisch erkannt wurden:

### Horizontaler Text

1. Klicken Sie auf "Text erkennen" in der Werkzeugleiste
2. Zeichnen Sie ein Rechteck um den Text im Bild
3. Der erkannte Text wird automatisch eingefuegt

### Schraeger Text

1. Klicken Sie auf "Schraeger Text" in der Werkzeugleiste
2. Zeichnen Sie ein Rechteck um den schraegen Text
3. Das System versucht den gedrehten Text zu erkennen

---

# 6. DATEN EXPORTIEREN

## 6.1 Excel-Export

1. Klicken Sie auf "Excel Export" in der Werkzeugleiste (oder Strg+E)
2. Der Export-Dialog oeffnet sich
3. Waehlen Sie die gewuenschten Optionen:
   - Welche Klassen exportiert werden sollen
   - Welche Spalten enthalten sein sollen
   - Sortierung und Filter
4. Klicken Sie auf "Exportieren"
5. Waehlen Sie den Speicherort

### Exportoptionen

| Option | Beschreibung |
|--------|--------------|
| Separate Blaetter | Jede Klasse auf eigenem Blatt |
| Filter anwenden | Nur gefilterte Daten exportieren |
| Spaltenbreite anpassen | Automatische Spaltenbreite |
| Kopfzeile fixieren | Erste Zeile beim Scrollen sichtbar |

### Export in bestehende Excel-Datei

Sie koennen Daten auch in eine bereits vorhandene Excel-Datei exportieren:
1. Waehlen Sie "In bestehende Datei"
2. Waehlen Sie die Zieldatei
3. Waehlen Sie Blatt und Startposition

## 6.2 JSON-Export

1. Klicken Sie auf "JSON" in der Werkzeugleiste (oder Strg+J)
2. Waehlen Sie den Speicherort
3. Die Daten werden als strukturiertes JSON gespeichert

---

# 7. QUALITAETSPRUEFUNG UND VALIDIERUNG

Das System bietet zwei leistungsfaehige Werkzeuge zur Qualitaetssicherung der erkannten Daten.

## 7.1 Qualitaetsinspektor (Erkennungsqualitaet pruefen)

Der Qualitaetsinspektor zeigt eine Uebersicht ueber die Erkennungsqualitaet aller Elemente.

### Oeffnen

1. Klicken Sie auf den "Qualitaet pruefen" Button in der Werkzeugleiste
2. Der Qualitaetsinspektor-Dialog oeffnet sich

### Funktionen

| Funktion | Beschreibung |
|----------|--------------|
| **Uebersicht** | Zeigt Gesamtstatistiken (Anzahl Erkennungen, Durchschnittskonfidenz) |
| **Risikobewertung** | Bewertet jedes Element nach Pruefbedarf |
| **Filter** | Filtert nach Klasse, Risikostufe, Konfidenz oder Seite |
| **Suche** | Sucht nach bestimmten Texten |
| **Springen** | Doppelklick auf eine Zeile springt zum Element im Bild |
| **Export** | Exportiert den Pruefbericht als CSV |

### Risikostufen

| Stufe | Beschreibung |
|-------|--------------|
| **Sofort pruefen (rot)** | Niedrige Erkennungsqualitaet oder fehlende Daten |
| **Bald pruefen (orange)** | Mittlere Qualitaet |
| **Gut erkannt (gruen)** | Hohe Qualitaet, keine Pruefung noetig |

### Risikofaktoren

Das System beruecksichtigt folgende Faktoren:

- Niedrige OCR-Konfidenz
- Fehlende Koordinatenverknuepfung
- Fehlender Text bei Elementen die Text benoetigen
- Potentielle Duplikate (nah beieinander)
- Ungewoehnliche Groesse
- Ungueltige Koordinatenformate
- GKS mit Buchstaben (sollte nur Ziffern haben)
- Formatierungsfehler (mehrere Leerzeichen)

## 7.2 Datenvalidierung

Die Datenvalidierung prueft alle erkannten Daten auf Fehler und bietet Auto-Korrektur.

### Oeffnen

1. Klicken Sie auf den "Validieren" Button in der Werkzeugleiste
2. Oder: Ueber den Qualitaetsinspektor → "Detaillierte Datenpruefung oeffnen"

### Validierungspruefungen

| Pruefung | Beschreibung | Auto-Korrektur |
|----------|--------------|----------------|
| Fehlende Koordinaten | Symbole ohne verknuepfte Koordinate | Nein |
| Signal-Format | Signalnamen (z.B. A101, BHR202) | Ja |
| GKS-Format | GKS-Nummern (3-4 Ziffern) | Ja |
| Fahrtrichtung | Gueltige Werte (A oder B) | Teilweise |
| Leere Textfelder | Pflichtfelder ohne Inhalt | Nein |
| Mehrfache Leerzeichen | OCR-Artefakte | Ja |
| Koordinaten-Struktur | Gueltiges Zahlenformat | Teilweise |
| Niedrige Konfidenz | Erkennungen unter 30% | Nein |

### Auto-Korrektur

Viele Fehler koennen automatisch korrigiert werden:

1. Im Validierungsdialog werden korrigierbare Fehler markiert
2. Klicken Sie auf "Auto-Korrektur anwenden"
3. Das System korrigiert automatisch:
   - O → 0, I → 1, S → 5 (OCR-Verwechslungen)
   - Mehrfache Leerzeichen → einzelnes Leerzeichen
   - Grossschreibung bei Signalnamen

### Manuelle Korrekturen

Fuer nicht automatisch korrigierbare Fehler:

- Doppelklick auf eine Zeile springt zum Element
- Bearbeiten Sie den Wert direkt in der Tabelle
- Oder verwenden Sie die vorgeschlagenen Aktionen:
  - **Bbox anpassen:** Erkennungsrahmen vergroessern/verkleinern
  - **Manuelles OCR:** Text neu erkennen lassen
  - **Loeschen:** Falscherkennung entfernen

---

# 8. ARBEITSBEREICH SPEICHERN/LADEN

## 8.1 In Datenbank speichern

1. Klicken Sie auf "Speichern" (oder Strg+S)
2. Der Speicherdialog oeffnet sich
3. Geben Sie einen Namen ein oder waehlen Sie ein bestehendes Layout
4. Klicken Sie auf "Speichern"

### Was wird gespeichert?

- Alle erkannten Elemente mit Koordinaten und Text
- Manuelle Korrekturen
- Gleisskelett-Daten
- Bildabmessungen

## 8.2 Aus Datenbank laden

1. Im Setup-Fenster: Waehlen Sie die PDF-Datei
2. Falls ein gespeicherter Arbeitsbereich existiert, wird dieser automatisch geladen
3. Alternativ: Daten-Menue → Datenbank-Manager

## 8.3 Datenbank-Manager

Oeffnen Sie den Datenbank-Manager ueber Daten → Datenbank-Manager:

- Alle gespeicherten Arbeitsbereiche anzeigen
- Arbeitsbereiche loeschen
- Arbeitsbereiche umbenennen

---

# 9. GLEISPLAENE VERGLEICHEN

Die Vergleichsfunktion ermoeglicht es, zwei Versionen eines Gleisplans zu vergleichen und Unterschiede zu identifizieren.

## 9.1 Vergleich starten

1. Oeffnen Sie beide Gleisplaene als Tabs
2. Klicken Sie auf "Plaene vergleichen" in der Werkzeugleiste
3. Oder: Vergleichen-Menue → Zwei Gleisplaene vergleichen
4. Waehlen Sie die beiden zu vergleichenden Plaene

## 9.2 Vergleichsergebnisse

Der Vergleich zeigt:
- **Neue Elemente:** In Plan B, aber nicht in Plan A
- **Entfernte Elemente:** In Plan A, aber nicht in Plan B
- **Geaenderte Elemente:** Unterschiedliche Werte zwischen den Plaenen
- **Verschobene Elemente:** Gleiche Elemente an anderer Position

---

# 10. EIGENE SYMBOLE

Das System unterstuetzt benutzerdefinierte Symbole durch Template-Matching.

## 10.1 Neues Symbol definieren

1. Oeffnen Sie Symbole → Neues Symbol definieren
2. Geben Sie einen Namen fuer das Symbol ein
3. Markieren Sie Beispiele des Symbols im Bild
4. Konfigurieren Sie die OCR-Region (falls das Symbol Text hat)
5. Speichern Sie das Symbol

## 10.2 Template Matching ausfuehren

1. Nach dem Definieren eines Symbols: Symbole → Template Matching
2. Das System sucht nach allen Vorkommen des definierten Symbols
3. Gefundene Symbole werden zur Ergebnisliste hinzugefuegt

---

# 11. ERKANNTE SYMBOLKLASSEN

Das System erkennt 13 verschiedene Symbolklassen:

| Klasse | Beschreibung | Hat Text |
|--------|--------------|----------|
| signal | Eisenbahnsignal (z.B. A101, B202) | Ja |
| gm_block | Gleismagnet-Block | Ja (GM) |
| gks_festkodiert | Festkodierter Gleiskontaktschalter | Ja (4 Ziffern) |
| gks_gesteuert | Gesteuerter Gleiskontaktschalter | Ja (4 Ziffern) |
| weichen_block | Weichensteuerungseinheit | Ja |
| isolierstoss | Elektrische Trennung im Gleis | Nein |
| haltepunkt | Bahnhof oder Haltestelle | Ja |
| sverbinder | Schienenverbinder | Nein |
| coordinate | Streckenkilometer | Ja |
| prellbock | Gleisabschluss / Puffer | Nein |
| haltetafel | Haltesignal / Tafel | Nein |
| weichenende | Ende eines Weichenbereichs | Nein |
| weichengruppenende | Ende einer Weichengruppe | Nein |

---

# 12. TASTATURKUERZEL

## Dateioperationen

| Kuerzel | Aktion |
|---------|--------|
| Strg+S | Speichern |
| Strg+Shift+S | Alle speichern |
| Strg+E | Excel Export |
| Strg+J | JSON Export |
| Strg+W | Tab schliessen |

## Bearbeitung

| Kuerzel | Aktion |
|---------|--------|
| Strg+C | Kopieren |
| Strg+V | Einfuegen |
| Strg+F | Suchen/Ersetzen |
| Strg+D | Ausgewaehlte Zeilen loeschen |
| Strg+Shift+N | Neuen Eintrag hinzufuegen |

## Navigation

| Kuerzel | Aktion |
|---------|--------|
| Mausrad | Zoomen |
| Rechte Maustaste + Ziehen | Bild verschieben |

---

# 13. FEHLERBEHEBUNG

## 13.1 Anwendung startet nicht

**Loesungen:**
1. Pruefen Sie, ob die virtuelle Umgebung aktiviert ist: `.\venv\Scripts\activate`
2. Pruefen Sie die Python-Version: `py --version` (sollte 3.11.x sein)
3. Installieren Sie Abhaengigkeiten neu: `py -m pip install -r requirements.txt`

## 13.2 PDF wird nicht geladen

**Loesungen:**
1. Pruefen Sie das Dateiformat (muss .pdf sein)
2. Versuchen Sie, die PDF in einem anderen Programm zu oeffnen
3. Stellen Sie sicher, dass Sie Leserechte haben

## 13.3 Verarbeitung ist langsam

**Loesungen:**
1. Schliessen Sie andere ressourcenintensive Programme
2. Fuer grosse A0-Plaene ist laengere Verarbeitung normal (15-20 Minuten)
3. Stellen Sie sicher, dass genuegend RAM verfuegbar ist (min. 8 GB)

## 13.4 OCR-Fehler

**Haeufige Verwechslungen:**

| Falsch | Richtig | Erklaerung |
|--------|---------|------------|
| O | 0 | Buchstabe O vs. Ziffer Null |
| I, l | 1 | Buchstabe I/l vs. Ziffer Eins |
| S | 5 | Buchstabe S vs. Ziffer Fuenf |

Das System korrigiert viele dieser Fehler automatisch in Zahlenfeldern.

## 13.5 Export-Fehler

**"Datei nicht lesbar" oder "MergedCell"-Fehler:**
- Stellen Sie sicher, dass die Ziel-Excel-Datei nicht geoeffnet ist
- Pruefen Sie Schreibrechte im Zielordner

---

## Kontakt & Support

**Entwickler:** Utkarsh Swain
**Organisation:** Siemens Mobility GmbH

---

```
================================================================================
        Ende des Benutzerhandbuchs
        Gleisplanextraktor v3 - RailDoc Studio
================================================================================
```
