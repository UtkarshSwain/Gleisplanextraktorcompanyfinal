===============================================================================
                    RailDoc Studio - Gleisplan-Modul
===============================================================================

INSTALLATION
------------
1. Entpacken Sie diesen Ordner an einen beliebigen Ort
   (z.B. Desktop oder C:\Programme\)

2. Doppelklicken Sie auf "Start_RailDocStudio.bat" um die Anwendung zu starten

HINWEIS: Es ist KEINE Python-Installation erforderlich!
         Alles Notwendige ist bereits im Ordner enthalten.


ERSTER START
------------
- Beim ersten Start kann es 1-2 Minuten dauern
- Das Programm laedt automatisch OCR-Sprachmodelle (~200 MB)
- Dies passiert nur einmal - danach startet die App schnell


BENUTZUNG
---------
1. Klicken Sie auf "PDF laden" um eine Gleisplan-PDF zu oeffnen
2. Waehlen Sie das passende Profil (z.B. "Antwerp" fuer belgische Plaene)
3. Klicken Sie auf "Erkennung starten"
4. Nach der Erkennung koennen Sie die Ergebnisse pruefen und exportieren


VERFUEGBARE PROFILE
-------------------
- Wien (schwarz/weiss)     : Oesterreichische Gleisplaene
- Wien (farbig)            : Oesterreichische Gleisplaene (Farbe)
- Antwerp                  : Belgische Gleisplaene (Infrabel)


WICHTIG: PDF-DATEINAMEN
-----------------------
- Der PDF-Dateiname wird als Layoutname in der Datenbank gespeichert
- Verwenden Sie EINDEUTIGE und BESCHREIBENDE Namen
- Beispiel: "Antwerpen_Centraal_Gleis1.pdf" statt "scan.pdf"
- Aendern Sie den Dateinamen NICHT nachdem Sie ihn geladen haben


DATENBANK TEILEN
----------------
Ihre Arbeit wird in der Datei "data/gleisplanextraktor.db" gespeichert.

Um Ihre Ergebnisse zu teilen:
1. Schliessen Sie die Anwendung
2. Kopieren Sie die Datei: data/gleisplanextraktor.db
3. Senden Sie diese Datei per E-Mail oder USB-Stick

Um eine Datenbank zu empfangen:
1. Schliessen Sie die Anwendung
2. Ersetzen Sie: data/gleisplanextraktor.db mit der erhaltenen Datei
3. Starten Sie die Anwendung neu
4. Ihre Layouts erscheinen in der Liste


EXCEL EXPORT
------------
- Klicken Sie auf "Export" um die Ergebnisse als Excel-Datei zu speichern
- Die Excel-Datei enthaelt alle erkannten Symbole und Koordinaten
- Jedes Layout wird als separates Arbeitsblatt exportiert


TIPPS FUER BESTE ERGEBNISSE
---------------------------
- Verwenden Sie hochaufloesende PDFs (mindestens 300 DPI)
- Stellen Sie sicher, dass der Plan gut lesbar ist
- Bei schlechter Erkennung: Pruefen Sie ob das richtige Profil gewaehlt ist
- Grosse Plaene (>10 Seiten) benoetigen mehr Zeit und Speicher


IHRE DATEN
----------
- Alle Daten werden im Ordner "data/" gespeichert:
    data/gleisplanextraktor.db  = Datenbank mit allen Layouts
- Behalten Sie diesen Ordner wenn Sie die Anwendung verschieben
- Machen Sie regelmaessig Backups der .db Datei!


SYSTEMANFORDERUNGEN
-------------------
- Windows 10 oder 11 (64-bit)
- Mindestens 8 GB RAM (16 GB empfohlen)
- 5 GB freier Festplattenspeicher
- Bildschirmaufloesung mindestens 1920x1080


BEI PROBLEMEN
-------------
- Stellen Sie sicher, dass genug Arbeitsspeicher frei ist
- Grosse PDFs (>50 MB) benoetigen mehr Zeit
- Falls die App nicht startet: Fuehren Sie Start_RailDocStudio.bat aus
  (nicht main.py direkt)
- Bei Fragen wenden Sie sich an den Entwickler


VERSIONSHINWEISE
----------------
Version: 2.0
Datum: Maerz 2026
Entwickler: [Ihr Name]

===============================================================================
