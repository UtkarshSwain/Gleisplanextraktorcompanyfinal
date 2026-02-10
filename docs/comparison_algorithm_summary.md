# Vergleichsalgorithmus - Zusammenfassung

## Ungarischer Algorithmus (Hungarian Algorithm)

Der Vergleichsalgorithmus verwendet den **Ungarischen Algorithmus** zur optimalen Zuordnung von Elementen zwischen zwei Gleisplanversionen.

### Vorteile gegenüber Greedy-Matching

| Aspekt | Greedy | Ungarisch |
|--------|--------|-----------|
| Duplikat-Behandlung | Reihenfolge-abhängig | **Optimal** |
| Falsche GELÖSCHT/HINZUGEFÜGT | Häufig | **Eliminiert** |
| Korrektheit | Lokales Optimum | **Globales Optimum** |

---

## Matching-Parameter

### OCR-Klassen (signal, gks_gesteuert, gks_festkodiert)

- **Basis-Score:** 0.6 (GKS) / 0.7 (Signal)
- **Koordinaten-Bonus:** 0.02 - 0.15 (basierend auf km-Differenz)
- **Räumlicher Bonus:** 0.10 - 0.30 (basierend auf Pixel-Abstand)
- **Kein harter Cutoff** - gleicher Name = gleiches Element

### Nicht-OCR-Klassen (sverbinder, gm_block, isolierstoß, etc.)

- **Koordinaten-Score:** 0.70 - 0.85 (basierend auf km-Differenz)
- **Räumlicher Bonus:** 0.02 - 0.15
- **Harter Cutoff: ±50m (100m gesamt)** - Elemente >100m entfernt = verschiedene Elemente

---

## Schwellenwerte

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| Match-Schwelle | 0.7 | Mindest-Score für Zuordnung |
| Koordinaten-Toleranz | ±50m | Für Nicht-OCR-Klassen |
| Seiten-Toleranz | ±1 | Nur benachbarte Seiten |

---

## Änderungserkennung

| Änderungstyp | Bedingung | Schweregrad |
|--------------|-----------|-------------|
| HINZUGEFÜGT | Element neu | MAJOR |
| GELÖSCHT | Element entfernt | MAJOR |
| VERSCHOBEN | coord_value geändert | MINOR (<5m), MODERATE (5-20m), MAJOR (>20m) |
| MODIFIZIERT | Andere Felder geändert | Variabel |

---

## Implementierung

```python
from scipy.optimize import linear_sum_assignment

# Kostenmatrix erstellen (negative Scores)
cost_matrix[i, j] = -score(old_i, new_j)

# Optimale Zuordnung finden
row_ind, col_ind = linear_sum_assignment(cost_matrix)

# Nur Matches mit Score > 0.7 akzeptieren
for i, j in zip(row_ind, col_ind):
    if -cost_matrix[i, j] > 0.7:
        matches[old_id] = new_id
```

---

## Zeitkomplexität

- **UUID-Matching:** O(n)
- **Ungarischer Algorithmus:** O(n³) pro Klasse
- **Gesamt:** O(k × n³), k = Anzahl Klassen
